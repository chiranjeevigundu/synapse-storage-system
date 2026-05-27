import os
import json
from pathlib import Path
from datetime import datetime
from loguru import logger
from config import settings
from utils import calculate_sha256

LEDGER_PATH = settings.ledger_file_path
REPORT_DIR = Path(settings.NAS_BASE_PATH) / "05_SYSTEM" / "Audit_Reports"

class IntegrityAuditor:
    def __init__(self):
        self.ledger_path = LEDGER_PATH
        if not REPORT_DIR.exists():
            REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def load_ledger(self):
        if not self.ledger_path.exists():
            return {}
        try:
            with open(self.ledger_path, "r") as f:
                data = json.load(f)
                return data.get("entries", {})
        except json.JSONDecodeError:
            logger.error("Failed to read ledger for audit.")
            return {}

    def run_audit(self):
        logger.info("Starting System-Wide Data Integrity Audit (Bit-Rot Check)...")
        entries = self.load_ledger()
        if not entries:
            logger.warning("No entries in ledger to audit.")
            return

        missing_files = []
        corrupted_files = []
        passed = 0

        for original_hash, metadata in entries.items():
            target_path_str = metadata.get("target_path")
            if not target_path_str:
                continue
                
            target_path = Path(target_path_str)
            
            if not target_path.exists():
                if settings.DRY_RUN:
                    logger.warning(f"File not curated yet (DRY RUN): {target_path.name}")
                    continue
                missing_files.append(str(target_path))
                logger.critical(f"MISSING FILE: {target_path}")
                continue
                
            try:
                current_hash = calculate_sha256(target_path)
                if current_hash != original_hash:
                    corrupted_files.append({"path": str(target_path), "expected": original_hash, "actual": current_hash})
                    logger.critical(f"BIT-ROT DETECTED: {target_path} (Hash Mismatch)")
                else:
                    passed += 1
            except Exception as e:
                logger.error(f"Failed to read {target_path} during audit: {e}")
                missing_files.append(str(target_path))

        logger.info(f"Audit Complete. Passed: {passed}, Missing: {len(missing_files)}, Corrupted: {len(corrupted_files)}")
        
        if missing_files or corrupted_files:
            self._generate_report(missing_files, corrupted_files)

    def _generate_report(self, missing: list, corrupted: list):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_path = REPORT_DIR / f"Corruption_Report_{timestamp}.md"
        
        content = [
            "# 🚨 UGREEN NAS Data Corruption Report",
            f"**Date Generated:** {datetime.now().isoformat()}",
            "\n## CRITICAL ALERT: Data Integrity Compromised",
            "The Sentinel Auditor detected discrepancies during the routine Bit-Rot check.",
        ]
        
        if missing:
            content.append("\n### Missing Files")
            for f in missing:
                content.append(f"- `{f}`")
                
        if corrupted:
            content.append("\n### Corrupted Files (Hash Mismatch)")
            for c in corrupted:
                content.append(f"- **Path:** `{c['path']}`\n  - Expected: `{c['expected']}`\n  - Actual: `{c['actual']}`")
                
        content.append("\n## Recommended Action")
        content.append("Please instruct the agent to initiate the `Restore from Backup` maintenance protocol immediately.")
        
        with open(report_path, "w") as f:
            f.write("\n".join(content))
            
        logger.critical(f"Data Corruption Report generated at {report_path}")

if __name__ == "__main__":
    auditor = IntegrityAuditor()
    auditor.run_audit()
