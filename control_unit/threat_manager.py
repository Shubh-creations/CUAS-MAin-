"""
Threat Escalation, Swarm Deconfliction & Priority Queue Manager (v4.0-Lattice).
Maintains multi-target priority queues sorted dynamically by Time-to-Impact (TTI)
and Threat Severity Index.
Provides tactical scenario presets (Swarm Saturation, FPV Terminal Dive, RF-Silent Stealth, Mixed Airspace).
"""

from collections import deque
from dataclasses import dataclass, field
import time
from typing import Dict, List, Optional, Any

from utils.logger import get_logger
from ai_core.response_engine import ThreatEvaluation, KillChainStage

logger = get_logger("CUAS.ThreatManager")

@dataclass
class ThreatEvent:
    event_id: str
    target_id: int
    threat_level: str
    timestamp: float
    description: str
    kill_chain_stage: str = "DETECT"
    acknowledged: bool = False


class ThreatManager:
    """Multi-Target Threat Deconfliction & DEFCON State Coordinator."""
    def __init__(self):
        self.active_threats: Dict[int, ThreatEvaluation] = {}
        self.alert_history: deque = deque(maxlen=200)
        self.overall_threat_level: str = "SAFE"
        self.total_detections: int = 0
        self.neutralized_count: int = 0
        self.current_scenario: str = "SWARM_SATURATION"
        self.automation_mode: str = "AUTO_ENGAGE_ROE" # "MANUAL_HITL" or "AUTO_ENGAGE_ROE"

    def set_scenario(self, scenario_name: str):
        self.current_scenario = scenario_name
        self.active_threats.clear()
        logger.info(f"Swarm scenario updated to: {scenario_name}")

    def update_threat(self, evaluation: ThreatEvaluation) -> None:
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
                description=evaluation.rationale,
                kill_chain_stage=evaluation.kill_chain_stage.value
            )
            self.alert_history.appendleft(event)
            logger.info(f"Target #{tid} Tracked [{evaluation.threat_level}] - Kill-Chain: {evaluation.kill_chain_stage.value}")

        self._reevaluate_overall_defcon()

    def _reevaluate_overall_defcon(self):
        if not self.active_threats:
            self.overall_threat_level = "SAFE"
            return

        levels = [t.threat_level for t in self.active_threats.values()]
        if "CRITICAL" in levels:
            self.overall_threat_level = "CRITICAL" # DEFCON 1
        elif "HIGH" in levels:
            self.overall_threat_level = "HIGH"     # DEFCON 2
        elif "ELEVATED" in levels:
            self.overall_threat_level = "ELEVATED" # DEFCON 3
        elif "ADVISORY" in levels:
            self.overall_threat_level = "ADVISORY" # DEFCON 4
        else:
            self.overall_threat_level = "SAFE"     # DEFCON 5

    def clear_threat(self, target_id: int, neutralized: bool = False):
        if target_id in self.active_threats:
            del self.active_threats[target_id]
            if neutralized:
                self.neutralized_count += 1
            self._reevaluate_overall_defcon()

    def get_prioritized_threats(self) -> List[ThreatEvaluation]:
        """Returns active threats sorted primarily by TTI (ascending), secondarily by score (descending)."""
        threat_list = list(self.active_threats.values())
        threat_list.sort(key=lambda t: (
            t.time_to_perimeter_sec if t.time_to_perimeter_sec is not None else 999.0,
            -t.numerical_threat_score
        ))
        for rank, threat in enumerate(threat_list, 1):
            threat.wta_priority_rank = rank
        return threat_list

    def get_summary(self) -> Dict[str, Any]:
        prioritized = self.get_prioritized_threats()
        return {
            "overall_threat_level": self.overall_threat_level,
            "current_scenario": self.current_scenario,
            "automation_mode": self.automation_mode,
            "active_threat_count": len(self.active_threats),
            "total_detections": self.total_detections,
            "neutralized_count": self.neutralized_count,
            "active_threats": [
                {
                    "target_id": t.target_id,
                    "threat_level": t.threat_level,
                    "score": t.numerical_threat_score,
                    "distance_m": t.distance_to_base_m,
                    "bearing_deg": t.bearing_from_base_deg,
                    "zone": t.geofence_zone,
                    "kill_chain_stage": t.kill_chain_stage.value,
                    "recommended_countermeasure": t.recommended_countermeasure,
                    "probability_success": t.countermeasure_probability_success,
                    "tti_sec": t.time_to_perimeter_sec,
                    "priority_rank": t.wta_priority_rank,
                    "rationale": t.rationale
                }
                for t in prioritized
            ],
            "recent_events": [
                {
                    "event_id": e.event_id,
                    "target_id": e.target_id,
                    "threat_level": e.threat_level,
                    "timestamp": e.timestamp,
                    "description": e.description,
                    "kill_chain_stage": e.kill_chain_stage
                }
                for e in list(self.alert_history)[:10]
            ]
        }
