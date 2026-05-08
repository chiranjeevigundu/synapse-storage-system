import os
import json
import shutil
import argparse
from datetime import datetime
from pathlib import Path
from loguru import logger
from config import settings

LEDGER_PATH = Path(__file__).parent / "ledger.json"

def load_ledger():
    if not LEDGER_PATH.exists():
        return {}
    with open(LEDGER_PATH, "r") as f:
        data = json.load(f)
        return data.get("entries", {})

def save_ledger(entries):
    with open(LEDGER_PATH, "w") as f:
        json.dump({"entries": entries}, f, indent=4)

def show_recent():
    entries = load_ledger()
    sorted_entries = sorted(entries.values(), key=lambda x: x.get("timestamp", ""), reverse=True)[:20]
    
    print(f"{'HASH':<15} | {'ORIGINAL NAME':<30} | {'CATEGORY':<35} | {'TARGET PATH'}")
    print("-" * 110)
    for entry in sorted_entries:
        h = entry.get("file_hash", "UNKNOWN")[:12] + "..."
        name = entry.get("original_name", "N/A")[:28]
        cat = entry.get("category", "N/A")[:33]
        path = entry.get("target_path", "N/A")
        print(f"{h:<15} | {name:<30} | {cat:<35} | {path}")

def reclassify(file_hash: str, new_category: str):
    entries = load_ledger()
    
    target_hash = None
    for h in entries.keys():
        if h.startswith(file_hash):
            target_hash = h
            break
            
    if not target_hash:
        logger.error(f"Hash starting with {file_hash} not found in ledger.")
        return
        
    entry = entries[target_hash]
    old_path = Path(entry.get("target_path"))
    
    if not old_path.exists():
        logger.error(f"Original file not found at {old_path}. It may have been moved or deleted.")
        return
        
    base_nas = Path(settings.NAS_BASE_PATH)
    new_path = base_nas / new_category / old_path.name
    
    new_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Moving file from {old_path} to {new_path}")
    shutil.move(str(old_path), str(new_path))
    
    entry["category"] = new_category
    entry["target_path"] = str(new_path)
    entry["timestamp"] = datetime.now().isoformat()
    
    save_ledger(entries)
    logger.success(f"Successfully reclassified to {new_category}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universe HITL Review Tool")
    parser.add_argument("--recent", action="store_true", help="Show 20 most recent entries")
    parser.add_argument("--reclassify", metavar="HASH", type=str, help="Hash of the file to reclassify")
    parser.add_argument("--category", type=str, help="New category path (e.g., 03_PERSONAL/Archives)")
    
    args = parser.parse_args()
    
    if args.recent:
        show_recent()
    elif args.reclassify and args.category:
        reclassify(args.reclassify, args.category)
    else:
        parser.print_help()
