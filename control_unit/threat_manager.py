"""
Threat Escalation and Mission Alert Manager for CUAS.
Maintains defense condition (DEFCON) state, alerts queue, and engagement lifecycle.
"""

from collections import deque
from dataclasses import dataclass, field
import time
from typing import Dict, List, Optional, Any

from utils.logger import get_logger
from ai_core.response_engine import ThreatEvaluation

logger = get_logger("CUAS.ThreatManager")

@dataclass
class ThreatEvent:
    event_id: str
    target_id: int
    threat_level: str
    timestamp: float
    description: str
    acknowledged: bool = False


class ThreatManager:
    """Coordinates threat tracking, defense condition levels, and active audio/visual alerts."""
    def __init__(self):
        self.active_threats: Dict[int, ThreatEvaluation] = {}
        self.alert_history: deque = deque(maxlen=200)
        self.overall_threat_level: str = "SAFE"
        self.total_detections: int = 0
        self.neutralized_count: int = 0

    def update_threat(self, evaluation: ThreatEvaluation) -> None:
        """Registers or updates a threat evaluation from the AI response engine."""
        tid = evaluation.target_id
        is_new = tid not in self.active_threats
        self.active_threats[tid] = evaluation

        if is_new:
            self.total_detections += 1
            event = ThreatEvent(
                event_id=f"EVT-{int(time.time())}-{tid}",
                target_id=tid,
                threat_level=evaluation.threat_level,
                timestamp=time.time(),
                description=f"New target detected: {evaluation.rationale}"
            )
            self.alert_history.appendleft(event)
            logger.info(f"Threat Registered [ID {tid}]: Level {evaluation.threat_level} - {evaluation.rationale}")

        self._reevaluate_overall_defcon()

    def _reevaluate_overall_defcon(self):
        """Calculates system-wide threat status based on highest threat track."""
        if not self.active_threats:
            self.overall_threat_level = "SAFE"
            return

        levels = [t.threat_level for t in self.active_threats.values()]
        if "CRITICAL" in levels:
            self.overall_threat_level = "CRITICAL"
        elif "HIGH" in levels:
            self.overall_threat_level = "HIGH"
        elif "ELEVATED" in levels:
            self.overall_threat_level = "ELEVATED"
        elif "ADVISORY" in levels:
            self.overall_threat_level = "ADVISORY"
        else:
            self.overall_threat_level = "SAFE"

    def clear_threat(self, target_id: int, neutralized: bool = False):
        if target_id in self.active_threats:
            del self.active_threats[target_id]
            if neutralized:
                self.neutralized_count += 1
            self._reevaluate_overall_defcon()

    def get_summary(self) -> Dict[str, Any]:
        return {
            "overall_threat_level": self.overall_threat_level,
            "active_threat_count": len(self.active_threats),
            "total_detections": self.total_detections,
            "neutralized_count": self.neutralized_count,
            "active_threats": [
                {
                    "target_id": t.target_id,
                    "threat_level": t.threat_level,
                    "score": t.numerical_threat_score,
                    "distance_m": t.distance_to_base_m,
                    "zone": t.geofence_zone,
                    "recommended_countermeasure": t.recommended_countermeasure
                }
                for t in self.active_threats.values()
            ]
        }
