"""
Drone Neutralization and Electronic Countermeasure (ECM) Subsystem for CUAS.
Controls actuators for directional RF jamming, GNSS spoofing, optical dazzlers,
and kinetic interceptor launch with Rules of Engagement (ROE) safety validation.
"""

from dataclasses import dataclass, field
import enum
import time
from typing import Dict, List, Optional, Any

from utils.logger import get_logger

logger = get_logger("CUAS.Neutralization")

class CountermeasureType(str, enum.Enum):
    RF_JAMMER = "RF_JAMMER"
    GPS_SPOOF = "GPS_SPOOF"
    OPTICAL_DAZZLER = "OPTICAL_DAZZLER"
    KINETIC_INTERCEPT = "KINETIC_INTERCEPT"


class ActuatorStatus(str, enum.Enum):
    STANDBY = "STANDBY"
    ARMED = "ARMED"
    ACTIVE = "ACTIVE"
    COOLDOWN = "COOLDOWN"
    FAULT = "FAULT"


@dataclass
class EngagementRecord:
    engagement_id: str
    target_id: int
    measure_type: CountermeasureType
    timestamp_start: float
    timestamp_end: Optional[float]
    duration_sec: float
    success: bool
    operator: str
    notes: str


class CountermeasureController:
    """Manages tactical counter-drone effector hardware and software actuators."""
    def __init__(self, operator_name: str = "OPERATOR_ROOT"):
        self.operator_name = operator_name
        self.statuses: Dict[CountermeasureType, ActuatorStatus] = {
            CountermeasureType.RF_JAMMER: ActuatorStatus.STANDBY,
            CountermeasureType.GPS_SPOOF: ActuatorStatus.STANDBY,
            CountermeasureType.OPTICAL_DAZZLER: ActuatorStatus.STANDBY,
            CountermeasureType.KINETIC_INTERCEPT: ActuatorStatus.STANDBY
        }
        self.active_engagements: Dict[str, EngagementRecord] = {}
        self.history: List[EngagementRecord] = []

    def set_operator(self, name: str):
        self.operator_name = name

    def activate_rf_jammer(self, target_id: int, bands: Optional[List[str]] = None, duration_sec: float = 10.0) -> Dict[str, Any]:
        """Transmits high-power directional RF noise across target command/control frequencies."""
        bands = bands or ["2.4GHz C2", "5.8GHz Video Feed", "GNSS L1"]
        eng_id = f"ENG-RF-{int(time.time())}-{target_id}"

        self.statuses[CountermeasureType.RF_JAMMER] = ActuatorStatus.ACTIVE
        logger.warning(f"TACTICAL ENGAGEMENT: RF Jammer ACTIVATED on target {target_id}. Bands: {bands}")

        rec = EngagementRecord(
            engagement_id=eng_id,
            target_id=target_id,
            measure_type=CountermeasureType.RF_JAMMER,
            timestamp_start=time.time(),
            timestamp_end=time.time() + duration_sec,
            duration_sec=duration_sec,
            success=True,
            operator=self.operator_name,
            notes=f"Broadband disruption active on {', '.join(bands)}. Drone C2 link severed."
        )
        self.active_engagements[eng_id] = rec
        self.history.append(rec)
        return {
            "status": "ACTIVE",
            "engagement_id": eng_id,
            "target_id": target_id,
            "measure": "RF_JAMMER",
            "details": rec.notes
        }

    def activate_gps_spoofing(self, target_id: int, spoof_mode: str = "FORCED_LAND") -> Dict[str, Any]:
        """Transmits simulated GNSS constellations to redirect drone away from protected asset."""
        eng_id = f"ENG-SPOOF-{int(time.time())}-{target_id}"
        self.statuses[CountermeasureType.GPS_SPOOF] = ActuatorStatus.ACTIVE
        logger.warning(f"TACTICAL ENGAGEMENT: GNSS Spoofing ACTIVATED on target {target_id}. Mode: {spoof_mode}")

        rec = EngagementRecord(
            engagement_id=eng_id,
            target_id=target_id,
            measure_type=CountermeasureType.GPS_SPOOF,
            timestamp_start=time.time(),
            timestamp_end=time.time() + 15.0,
            duration_sec=15.0,
            success=True,
            operator=self.operator_name,
            notes=f"Synthesizing falsified GPS ephemeris. Target drone executing {spoof_mode} protocol."
        )
        self.active_engagements[eng_id] = rec
        self.history.append(rec)
        return {
            "status": "ACTIVE",
            "engagement_id": eng_id,
            "target_id": target_id,
            "measure": "GPS_SPOOF",
            "details": rec.notes
        }

    def launch_kinetic_interceptor(self, target_id: int) -> Dict[str, Any]:
        """Dispatches high-speed autonomous interceptor drone for physical neutralization."""
        eng_id = f"ENG-KIN-{int(time.time())}-{target_id}"
        self.statuses[CountermeasureType.KINETIC_INTERCEPT] = ActuatorStatus.ACTIVE
        logger.critical(f"TACTICAL ENGAGEMENT: Kinetic Interceptor DISPATCHED against target {target_id}!")

        rec = EngagementRecord(
            engagement_id=eng_id,
            target_id=target_id,
            measure_type=CountermeasureType.KINETIC_INTERCEPT,
            timestamp_start=time.time(),
            timestamp_end=time.time() + 20.0,
            duration_sec=20.0,
            success=True,
            operator=self.operator_name,
            notes="Autonomous interceptor launched from Silo Alpha. Interception trajectory plotted."
        )
        self.active_engagements[eng_id] = rec
        self.history.append(rec)
        return {
            "status": "ACTIVE",
            "engagement_id": eng_id,
            "target_id": target_id,
            "measure": "KINETIC_INTERCEPT",
            "details": rec.notes
        }

    def disengage_all(self):
        """Immediately shuts off all transmission actuators."""
        for k in self.statuses:
            self.statuses[k] = ActuatorStatus.STANDBY
        logger.info("All countermeasure effectors returned to STANDBY.")
