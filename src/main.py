import os
import json
import time
import shutil
import signal
import threading
import schedule
from pathlib import Path
from datetime import datetime
from loguru import logger
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler
from prometheus_client import start_http_server, Counter, Gauge

from models import FileMetadata
from utils import calculate_sha256, generate_universe_path
from vision import VisionClassifier
from config import settings

# Metrics
AI_CATEGORIZATION_COUNTER = Counter('ai_categorization_count', 'Total number of files categorized by AI vision')
NAS_STORAGE_USAGE = Gauge('nas_storage_usage_percent', 'Current storage usage percentage of the NAS')

BASE_INGEST_PATH = Path(settings.NAS_BASE_PATH) / "00_INGEST"

LEDGER_PATH = settings.ledger_file_path

def update_disk_usage():
    try:
        path = BASE_INGEST_PATH.parent if BASE_INGEST_PATH.exists() else "/"
        total, used, free = shutil.disk_usage(path)
        percent = (used / total) * 100
        NAS_STORAGE_USAGE.set(percent)
    except Exception as e:
        logger.error(f"Failed to calculate disk usage: {e}")

class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.entries = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    data = json.load(f)
                    if "hashes" in data and isinstance(data["hashes"], list):
                        for h in data["hashes"]:
                            self.entries[h] = {"file_hash": h}
                    else:
                        self.entries = data.get("entries", {})
            except json.JSONDecodeError:
                logger.warning("Ledger is corrupted or empty. Starting fresh.")
                
    def save(self):
        temp_path = self.path.with_suffix(".tmp")
        try:
            with open(temp_path, "w") as f:
                json.dump({"entries": self.entries}, f, indent=4)
            os.replace(str(temp_path), str(self.path))
        except Exception as e:
            logger.error(f"Failed to atomically save ledger: {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def contains(self, file_hash: str) -> bool:
        return file_hash in self.entries

    def add_hash_only(self, file_hash: str):
        if file_hash not in self.entries:
            self.entries[file_hash] = {"file_hash": file_hash}
            self.save()
            
    def update_entry(self, file_hash: str, metadata_dict: dict):
        self.entries[file_hash] = metadata_dict
        self.save()

def wait_for_file_stability(file_path: Path, interval: float = 0.5, timeout: float = 10.0) -> bool:
    """Waits until a file's size is stable (fully written)."""
    if not file_path.exists():
        return False
    last_size = -1
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            current_size = file_path.stat().st_size
            if current_size == last_size and current_size >= 0:
                return True
            last_size = current_size
        except Exception:
            pass
        time.sleep(interval)
    return False

PROCESSING_FILES = set()
PROCESSING_LOCK = threading.Lock()

def process_file_safe(file_path: Path, handler):
    abs_path = str(file_path.absolute())
    with PROCESSING_LOCK:
        if abs_path in PROCESSING_FILES:
            return
        PROCESSING_FILES.add(abs_path)
    
    try:
        handler._process_file(file_path)
    finally:
        with PROCESSING_LOCK:
            PROCESSING_FILES.discard(abs_path)

class IngestHandler(FileSystemEventHandler):
    def __init__(self, ledger: Ledger):
        super().__init__()
        self.ledger = ledger
        self.vision_classifier = VisionClassifier()

    def on_created(self, event):
        if not event.is_directory:
            process_file_safe(Path(event.src_path), self)

    def on_moved(self, event):
        if not event.is_directory:
            process_file_safe(Path(event.dest_path), self)

    def _process_file(self, file_path: Path):
        logger.info(f"Event detected! Processing: {file_path}")
        
        # Ensure the file is fully written/stable before hashing
        if not wait_for_file_stability(file_path):
            logger.warning(f"File {file_path} size is unstable or not fully written. Skipping for next check.")
            return

        try:
            # 1. Calculate file hash
            file_hash = calculate_sha256(file_path)
            
            # 2. Check ledger for duplicates
            if self.ledger.contains(file_hash):
                logger.error(f"DUPLICATE DETECTED: File {file_path} matches existing hash {file_hash}. Skipping.")
                if not settings.DRY_RUN:
                    try:
                        logger.info(f"Removing duplicate file from ingest zone: {file_path}")
                        file_path.unlink()
                    except Exception as e:
                        logger.error(f"Failed to delete duplicate file {file_path}: {e}")
                return
                
            self.ledger.add_hash_only(file_hash)
            
            # 3. Extract basic metadata
            stat = file_path.stat()
            creation_date = datetime.fromtimestamp(stat.st_mtime)
            
            # Try to extract source device from filename or fallback
            filename_parts = file_path.name.split('_')
            source_device = filename_parts[0] if len(filename_parts) > 1 else "UnknownDevice"
            
            logger.info(f"Extracted Source Device: {source_device}")
            
            category = "03_PERSONAL/Archives"  # Default fallback category
            
            # AI Vision Tagging
            valid_extensions = {".jpg", ".jpeg", ".png", ".heic"}
            if file_path.suffix.lower() in valid_extensions:
                logger.info(f"Image detected ({file_path.suffix}). Triggering VisionClassifier for AI tagging...")
                category = self.vision_classifier.classify_image(str(file_path))
                AI_CATEGORIZATION_COUNTER.inc()
                logger.success(f"AI assigned category: {category}")
            
            metadata = FileMetadata(
                original_path=file_path,
                file_hash=file_hash,
                source_device=source_device,
                creation_date=creation_date,
                category=category
            )
            
            # 4. Generate final NAS destination
            target_path = generate_universe_path(metadata)
            metadata.target_path = target_path
            
            # 5. Move the file or log dry run intent
            if settings.DRY_RUN:
                logger.success(f"DRY RUN: Would move {file_path.name} -> {metadata.target_path}")
            else:
                logger.info(f"Moving file from {file_path} to {metadata.target_path}")
                metadata.target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(file_path), str(metadata.target_path))
                logger.success(f"Successfully moved {file_path.name} to {metadata.target_path}")
            
            # Update ledger with robust metadata for the HITL review tool
            self.ledger.update_entry(file_hash, {
                "file_hash": file_hash,
                "original_name": file_path.name,
                "category": category,
                "target_path": str(metadata.target_path),
                "timestamp": datetime.now().isoformat()
            })
            
            # Update disk usage metrics
            update_disk_usage()
            
        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

def run_sweep(event_handler, interval: float = 10.0):
    while True:
        try:
            if BASE_INGEST_PATH.exists():
                for file_path in BASE_INGEST_PATH.iterdir():
                    if file_path.is_file() and not file_path.name.startswith("."):
                        process_file_safe(file_path, event_handler)
        except Exception as e:
            logger.error(f"Error during directory sweep: {e}")
        time.sleep(interval)

def main():
    mode_str = "Dry Run" if settings.DRY_RUN else "Live Curation Mode"
    logger.info(f"Starting Universe Curator - Watchdog Background Service ({mode_str})")
    
    # Start Prometheus metrics server
    start_http_server(8001)
    logger.info("Metrics server started on port 8001")
    
    # Start Integrity Auditor
    from auditor import IntegrityAuditor
    auditor = IntegrityAuditor()
    schedule.every().sunday.at("02:00").do(auditor.run_audit)
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Integrity Auditor scheduled for Sunday at 02:00 AM.")
    
    if not BASE_INGEST_PATH.exists():
        logger.warning(f"Ingest path {BASE_INGEST_PATH} does not exist. Creating it.")
        BASE_INGEST_PATH.mkdir(parents=True, exist_ok=True)
        
    ledger = Ledger(LEDGER_PATH)
    logger.info(f"Ledger initialized with {len(ledger.entries)} entries.")
    
    event_handler = IngestHandler(ledger)
    observer = Observer()
    observer.schedule(event_handler, str(BASE_INGEST_PATH), recursive=True)
    
    observer.start()
    logger.info(f"Monitoring directory: {BASE_INGEST_PATH}")
    
    # Start periodic directory sweep
    sweep_thread = threading.Thread(target=run_sweep, args=(event_handler,), daemon=True)
    sweep_thread.start()
    logger.info("Periodic directory sweep thread started (interval: 10s).")
    
    # Initialize disk usage gauge
    update_disk_usage()
    
    # Graceful shutdown handler
    def shutdown_handler(signum, frame):
        logger.info("Termination signal received. Shutting down gracefully...")
        observer.stop()
        observer.join()
        logger.info("Shutdown complete.")
        os._exit(0)
        
    # Catch SIGINT (Ctrl+C) and SIGTERM
    try:
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
    except AttributeError:
        pass
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown_handler(signal.SIGINT, None)

if __name__ == "__main__":
    main()
