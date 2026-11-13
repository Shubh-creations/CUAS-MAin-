"""
Autonomous Threat Evaluation and Countermeasure Response Engine for CUAS.
Computes multi-factor threat scores, evaluates geofence breaches, and recommends
tactical neutralization measures (RF Jamming, GPS Spoofing, Laser, Kinetic Intercept).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

from utils.logger import get_logger
from utils.geo_utils import check_geofence_status
from .classifier import DroneClassificationResult
from .trajectory_predictor import TrajectoryPrediction

logger = get_logger("CUAS.ResponseEngine")

@dataclass
class ThreatEvaluation:
    target_id: int
    threat_level: str               # "SAFE", "ADVISORY", "ELEVATED", "HIGH", "CRITICAL"
    numerical_threat_score: float   # 0.0 - 100.0
    geofence_zone: str              # "CLEAR", "GREEN", "AMBER", "RED"
    distance_to_base_m: float
    bearing_from_base_deg: float
    recommended_countermeasure: str # "NONE", "RF_JAMMER", "GPS_SPOOF", "OPTICAL_DAZZLER", "KINETIC_INTERCEPT"
    countermeasure_probability_success: float # 0.0 - 1.0
    engagement_authorized: bool
    rationale: str


class ThreatResponseEngine:
    """Evaluates drone threat matrices and issues automated countermeasure recommendations."""
    def __init__(
        self,
        base_latitude: float = 37.7749,
        base_longitude: float = -122.4194,
        inner_killzone_m: float = 500.0,
        warning_perimeter_m: float = 1500.0,
        detection_boundary_m: float = 3500.0,
        auto_engagement_enabled: bool = False
    ):
        self.base_lat = base_latitude
        self.base_lon = base_longitude
        self.inner_killzone_m = inner_killzone_m
        self.warning_perimeter_m = warning_perimeter_m
        self.detection_boundary_m = detection_boundary_m
        self.auto_engagement = auto_engagement_enabled

    def evaluate_target(
        self,
        target_id: int,
        target_lat: float,
        target_lon: float,
        classification: Optional[DroneClassificationResult] = None,
        trajectory: Optional[TrajectoryPrediction] = None
    ) -> ThreatEvaluation:
        """Computes comprehensive threat evaluation and determines ROE countermeasure."""
        # 1. Geofence Analysis
        geo = check_geofence_status(
            target_lat=target_lat,
            target_lon=target_lon,
            base_lat=self.base_lat,
            base_lon=self.base_lon,
            inner_killzone_m=self.inner_killzone_m,
            warning_perimeter_m=self.warning_perimeter_m,
            detection_boundary_m=self.detection_boundary_m
        )

        zone = geo["zone"]
        dist_m = geo["distance_m"]
        bearing_deg = geo["bearing_deg"]

        # 2. Base score from distance proximity
        proximity_factor = max(0.0, 1.0 - (dist_m / max(self.detection_boundary_m, 1.0)))
        score = proximity_factor * 40.0

        # 3. Add classification score
        pred_class = classification.predicted_class if classification else "UNKNOWN_AIR_VEHICLE"
        cls_threat = classification.threat_score if classification else 40.0
        score += (cls_threat * 0.40)

        # 4. Trajectory and Kinematic factors
        if trajectory:
            if trajectory.is_diving_or_descending:
                score += 15.0  # High risk of dive attack / kamikaze
            if trajectory.is_evasive:
                score += 10.0  # Counter-maneuver avoidance detected
            if trajectory.speed > 25.0:
                score += 8.0   # High-speed approach

        # Clamp score to 100.0
        threat_score = round(min(100.0, max(0.0, score)), 1)

        # 5. Determine Threat Level & Response
        if zone == "RED" or threat_score >= 80.0:
            threat_level = "CRITICAL"
            if pred_class in ["SUICIDE_DRONE", "CUSTOMIZED_DRONE"] or (trajectory and trajectory.is_diving_or_descending):
                countermeasure = "KINETIC_INTERCEPT"
                p_success = 0.94
                rationale = "CRITICAL IMMINENT BREACH: HIGH-LETHALITY TARGET DIVE. KINETIC INTERCEPT AUTHORIZED."
            else:
                countermeasure = "RF_JAMMER"
                p_success = 0.88
                rationale = "INNER PERIMETER BREACH: ENGAGE HIGH-POWER MULTI-BAND RF JAMMER & FORCED LANDING."
            authorized = True if self.auto_engagement else False

        elif zone == "AMBER" or threat_score >= 55.0:
            threat_level = "HIGH"
            countermeasure = "GPS_SPOOF"
            p_success = 0.85
            rationale = "WARNING PERIMETER BREACH: INITIATE GNSS SPOOFING (FORCED RETURN-TO-HOME PROTOCOL)."
            authorized = False

        elif zone == "GREEN" or threat_score >= 35.0:
            threat_level = "ELEVATED"
            countermeasure = "OPTICAL_DAZZLER"
            p_success = 0.78
            rationale = "APPROACHING PERIMETER: ENGAGE DIRECTED OPTICAL DAZZLER TO BLIND SENSOR PAYLOAD."
            authorized = False

        else:
            threat_level = "ADVISORY" if threat_score >= 20.0 else "SAFE"
            countermeasure = "NONE"
            p_success = 0.0
            rationale = "TARGET OUTSIDE PERIMETER. MAINTAIN PASSIVE RADAR & RF SURVEILLANCE."
            authorized = False

        return ThreatEvaluation(
            target_id=target_id,
            threat_level=threat_level,
            numerical_threat_score=threat_score,
            geofence_zone=zone,
            distance_to_base_m=dist_m,
            bearing_from_base_deg=bearing_deg,
            recommended_countermeasure=countermeasure,
            countermeasure_probability_success=p_success,
            engagement_authorized=authorized,
            rationale=rationale
        )
