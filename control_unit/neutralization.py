"""
Drone Neutralization & Closed-Loop Tactical Actuator Subsystem (v4.0-Lattice).
Controls physical/electronic effectors (Directional RF Jammer, GNSS Constellation Spoofer,
Directed Optical Dazzler, Kinetic Interceptor Drone Silo) with explicit state machines:
STANDBY -> SLEWING -> ACTIVE_ENGAGEMENT -> THERMAL_COOLDOWN -> RELOADING.
Features closed-loop simulation feedback altering drone flight kinematics and generating
post-engagement Battle Damage Assessment (BDA: SPLASH / NEUTRALIZED).
"""

from dataclasses import dataclass, field
import enum
import math
import time
from typing import Dict, List, Optional, Any, Tuple

from utils.logger import get_logger

logger = get_logger("CUAS.Neutralization")

class CountermeasureType(str, enum.Enum):
    RF_JAMMER = "RF_JAMMER"
    GPS_SPOOF = "GPS_SPOOF"
    OPTICAL_DAZZLER = "OPTICAL_DAZZLER"
    KINETIC_INTERCEPT = "KINETIC_INTERCEPT"


class ActuatorStatus(str, enum.Enum):
    STANDBY = "STANDBY"
    SLEWING = "SLEWING"
    ACTIVE = "ACTIVE"
    COOLDOWN = "COOLDOWN"
    RELOADING = "RELOADING"
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
    bda_status: str = "PENDING"  # "PENDING", "TARGET_DIVERTED", "LINK_SEVERED", "SPLASH_CONFIRMED"


@dataclass
class InterceptorFlightState:
    interceptor_id: str
    target_id: int
    current_enu: Tuple[float, float, float]
    target_enu: Tuple[float, float, float]
    speed_mps: float = 40.0
    is_active: bool = True
    time_to_intercept_sec: float = 6.0


class CountermeasureController:
    """Tactical Effector Array Controller with Closed-Loop Physics Feedback."""
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
        self.active_interceptors: Dict[str, InterceptorFlightState] = {}
        self.neutralized_target_ids: set = set()

    def set_operator(self, name: str):
        self.operator_name = name

    def activate_rf_jammer(self, target_id: int, bands: Optional[List[str]] = None, duration_sec: float = 12.0) -> Dict[str, Any]:
        """Disrupts target command/telemetry link, forcing drone into failsafe hover/drift."""
        bands = bands or ["2.4 GHz C2", "5.8 GHz Video", "GNSS L1/L2"]
        eng_id = f"ENG-RF-{int(time.time())}-{target_id}"

        self.statuses[CountermeasureType.RF_JAMMER] = ActuatorStatus.ACTIVE
        logger.warning(f"TACTICAL ENGAGEMENT: Directional RF Jammer EMITTING on Target #{target_id}. Bands: {bands}")

        rec = EngagementRecord(
            engagement_id=eng_id,
            target_id=target_id,
            measure_type=CountermeasureType.RF_JAMMER,
            timestamp_start=time.time(),
            timestamp_end=time.time() + duration_sec,
            duration_sec=duration_sec,
            success=True,
            operator=self.operator_name,
            notes=f"Broadband noise emitted across {', '.join(bands)}. Drone C2 link severed. Target entering hover-drift.",
            bda_status="LINK_SEVERED"
        )
        self.active_engagements[eng_id] = rec
        self.history.append(rec)
        self.neutralized_target_ids.add(target_id)

        return {
            "status": "ACTIVE",
            "engagement_id": eng_id,
            "target_id": target_id,
            "measure": "RF_JAMMER",
            "bda": "LINK_SEVERED",
            "details": rec.notes
        }

    def activate_gps_spoofing(self, target_id: int, spoof_mode: str = "FORCED_RTH_DIVERT") -> Dict[str, Any]:
        """Transmits synthetic GNSS coordinates to steer target drone vector away from Base HQ."""
        eng_id = f"ENG-SPOOF-{int(time.time())}-{target_id}"
        self.statuses[CountermeasureType.GPS_SPOOF] = ActuatorStatus.ACTIVE
        logger.warning(f"TACTICAL ENGAGEMENT: GNSS Spoofing EMITTING on Target #{target_id}. Mode: {spoof_mode}")

        rec = EngagementRecord(
            engagement_id=eng_id,
            target_id=target_id,
            measure_type=CountermeasureType.GPS_SPOOF,
            timestamp_start=time.time(),
            timestamp_end=time.time() + 15.0,
            duration_sec=15.0,
            success=True,
            operator=self.operator_name,
            notes=f"Injecting falsified ephemeris. Target drone autopilot executing {spoof_mode}. Heading diverted 180 deg.",
            bda_status="TARGET_DIVERTED"
        )
        self.active_engagements[eng_id] = rec
        self.history.append(rec)
        self.neutralized_target_ids.add(target_id)

        return {
            "status": "ACTIVE",
            "engagement_id": eng_id,
            "target_id": target_id,
            "measure": "GPS_SPOOF",
            "bda": "TARGET_DIVERTED",
            "details": rec.notes
        }

    def activate_optical_dazzler(self, target_id: int) -> Dict[str, Any]:
        """Directs collimated optical/IR dazzler to saturate optical navigation sensors."""
        eng_id = f"ENG-DAZZLER-{int(time.time())}-{target_id}"
        self.statuses[CountermeasureType.OPTICAL_DAZZLER] = ActuatorStatus.ACTIVE
        logger.warning(f"TACTICAL ENGAGEMENT: Optical Dazzler EMITTING on Target #{target_id}")

        rec = EngagementRecord(
            engagement_id=eng_id,
            target_id=target_id,
            measure_type=CountermeasureType.OPTICAL_DAZZLER,
            timestamp_start=time.time(),
            timestamp_end=time.time() + 10.0,
            duration_sec=10.0,
            success=True,
            operator=self.operator_name,
            notes="High-intensity collimated optical dazzler beam tracking target. Electro-optical camera sensor saturated.",
            bda_status="SENSOR_BLINDED"
        )
        self.active_engagements[eng_id] = rec
        self.history.append(rec)
        self.neutralized_target_ids.add(target_id)

        return {
            "status": "ACTIVE",
            "engagement_id": eng_id,
            "target_id": target_id,
            "measure": "OPTICAL_DAZZLER",
            "bda": "SENSOR_BLINDED",
            "details": rec.notes
        }

    def launch_kinetic_interceptor(self, target_id: int, target_enu: Tuple[float, float, float] = (150.0, 350.0, 180.0)) -> Dict[str, Any]:
        """Spawns high-speed Blue-Force interceptor drone tracking towards target collision."""
        eng_id = f"ENG-KIN-{int(time.time())}-{target_id}"
        interceptor_callsign = f"BLUE-INTERCEPTOR-{target_id}"
        self.statuses[CountermeasureType.KINETIC_INTERCEPT] = ActuatorStatus.ACTIVE
        logger.critical(f"TACTICAL ENGAGEMENT: Kinetic Interceptor DISPATCHED against Target #{target_id}!")

        # Spawn flight track from Base HQ (0, 0, 0)
        self.active_interceptors[interceptor_callsign] = InterceptorFlightState(
            interceptor_id=interceptor_callsign,
            target_id=target_id,
            current_enu=(0.0, 0.0, 10.0),
            target_enu=target_enu,
            speed_mps=42.0,
            is_active=True,
            time_to_intercept_sec=4.5
        )

        rec = EngagementRecord(
            engagement_id=eng_id,
            target_id=target_id,
            measure_type=CountermeasureType.KINETIC_INTERCEPT,
            timestamp_start=time.time(),
            timestamp_end=time.time() + 20.0,
            duration_sec=20.0,
            success=True,
            operator=self.operator_name,
            notes=f"Autonomous kinetic interceptor {interceptor_callsign} dispatched from Silo Alpha. Collision intercept in 4.5s.",
            bda_status="INTERCEPT_IN_PROGRESS"
        )
        self.active_engagements[eng_id] = rec
        self.history.append(rec)
        self.neutralized_target_ids.add(target_id)

        return {
            "status": "ACTIVE",
            "engagement_id": eng_id,
            "target_id": target_id,
            "measure": "KINETIC_INTERCEPT",
            "interceptor_id": interceptor_callsign,
            "bda": "SPLASH_CONFIRMED",
            "details": rec.notes
        }

    def update_interceptor_simulation(self, dt: float = 0.033) -> List[Dict[str, Any]]:
        """Advances interceptor flight tracks toward targets and returns BDA events upon collision."""
        bda_events = []
        for callsign, state in list(self.active_interceptors.items()):
            if not state.is_active:
                continue

            state.time_to_intercept_sec -= dt
            # Move towards target
            dx = state.target_enu[0] - state.current_enu[0]
            dy = state.target_enu[1] - state.current_enu[1]
            dz = state.target_enu[2] - state.current_enu[2]
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)

            if dist > 5.0 and state.time_to_intercept_sec > 0:
                step = state.speed_mps * dt
                ratio = min(1.0, step / max(dist, 1e-3))
                state.current_enu = (
                    state.current_enu[0] + dx * ratio,
                    state.current_enu[1] + dy * ratio,
                    state.current_enu[2] + dz * ratio
                )
            else:
                # Collision / Neutralization confirmed
                state.is_active = False
                bda_events.append({
                    "interceptor_id": callsign,
                    "target_id": state.target_id,
                    "event": "SPLASH_CONFIRMED",
                    "timestamp": time.time(),
                    "location_enu": state.current_enu
                })
                logger.info(f"BDA: Target #{state.target_id} NEUTRALIZED by {callsign} (SPLASH CONFIRMED)")

        return bda_events

    def disengage_all(self):
        for k in self.statuses:
            self.statuses[k] = ActuatorStatus.STANDBY
        for interceptor in self.active_interceptors.values():
            interceptor.is_active = False
        logger.info("All countermeasure effectors returned to STANDBY.")
