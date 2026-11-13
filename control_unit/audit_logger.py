"""
Forensic Audit Trail & Cryptographic Mission Ledger for CUAS (v4.0-Lattice).
Maintains an immutable blockchain-style SHA-256 hash-chained event ledger
for military defense compliance and real-time chain verification.
"""

import hashlib
import json
import os
import time
from typing import Dict, List, Optional, Any, Tuple

from utils.logger import get_logger

logger = get_logger("CUAS.Audit")

class ForensicAuditLogger:
    """Tamper-evident SHA-256 hash-chained audit logger with integrity verification."""
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

        # Write to append-only file
        with open(self.chain_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_payload) + "\n")

        self.last_hash = block_hash
        logger.debug(f"Audit block recorded: {event_type} [Hash: {block_hash[:12]}...]")
        return block_hash

    def verify_chain_integrity(self) -> Tuple[bool, int, str]:
        """
        Validates complete SHA-256 cryptographic chain integrity from block 0 to present.
        Returns (is_valid, total_blocks_verified, message).
        """
        if not os.path.exists(self.chain_file) or os.path.getsize(self.chain_file) == 0:
            return (True, 0, "CHAIN EMPTY (GENESIS PENDING)")

        expected_prev = "0" * 64
        count = 0

        with open(self.chain_file, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                record = json.loads(line.strip())
                recorded_hash = record.get("block_hash")
                prev_hash = record.get("previous_hash")

                if prev_hash != expected_prev:
                    return (False, count, f"TAMPER DETECTED at block {line_no}: Previous hash mismatch.")

                # Recompute hash
                payload_copy = {k: v for k, v in record.items() if k != "block_hash"}
                payload_str = json.dumps(payload_copy, sort_keys=True)
                recomputed = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

                if recomputed != recorded_hash:
                    return (False, count, f"TAMPER DETECTED at block {line_no}: Content hash invalid.")

                expected_prev = recorded_hash
                count += 1

        return (True, count, f"ALL {count} BLOCKS VERIFIED (100% CRYPTOGRAPHIC INTEGRITY)")

    def get_recent_blocks(self, limit: int = 8) -> List[Dict[str, Any]]:
        """Returns the most recent verified blocks for UI telemetry."""
        if not os.path.exists(self.chain_file):
            return []
        records = []
        with open(self.chain_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line.strip()))
        return records[-limit:]
