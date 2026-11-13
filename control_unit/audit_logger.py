"""
Forensic Audit Trail & Cryptographic Mission Logging for CUAS.
Maintains a tamper-evident event log with SHA-256 block hash chaining
for military and defense incident compliance.
"""

import hashlib
import json
import os
import time
from typing import Dict, List, Optional, Any

from utils.logger import get_logger

logger = get_logger("CUAS.Audit")

class ForensicAuditLogger:
    """Tamper-evident audit logger for C2 incident records."""
    def __init__(self, log_dir: str = "logs/audit"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.chain_file = os.path.join(self.log_dir, "mission_audit_chain.jsonl")
        self.last_hash = self._get_genesis_hash()

    def _get_genesis_hash(self) -> str:
        if os.path.exists(self.chain_file) and os.path.getsize(self.chain_file) > 0:
            with open(self.chain_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    last_record = json.loads(lines[-1].strip())
                    return last_record.get("block_hash", "0" * 64)
        return "0" * 64

    def log_event(self, event_type: str, details: Dict[str, Any], operator: str = "SYSTEM") -> str:
        """Appends a new cryptographically secured log block."""
        timestamp = time.time()
        record_payload = {
            "timestamp": timestamp,
            "event_type": event_type,
            "operator": operator,
            "details": details,
            "previous_hash": self.last_hash
        }

        # Calculate block hash
        payload_str = json.dumps(record_payload, sort_keys=True)
        block_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        record_payload["block_hash"] = block_hash

        # Write to file
        with open(self.chain_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_payload) + "\n")

        self.last_hash = block_hash
        logger.debug(f"Audit block written: {event_type} [Hash: {block_hash[:12]}...]")
        return block_hash

    def export_mission_report(self, output_path: str = "logs/mission_report.json") -> bool:
        """Exports full mission history for after-action review."""
        if not os.path.exists(self.chain_file):
            return False

        records = []
        with open(self.chain_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line.strip()))

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "report_title": "CUAS Tactical Incident After-Action Report",
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_events": len(records),
                "events": records
            }, f, indent=2)

        logger.info(f"Exported mission report to {output_path}")
        return True
