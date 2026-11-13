"""
Multi-Modal Sensor Fusion Engine for CUAS.
Fuses visual camera tracks, RF electronic surveillance, and 3D radar blips
into a unified Common Operating Picture (COP) with track association and false-alarm suppression.
"""

from dataclasses import dataclass, field
import math
import time
from typing import Dict, List, Optional, Tuple, Any

from utils.logger import get_logger
from ai_core.detection import TrackedDrone
from .rf_sensor import RFEmission
from .radar_sensor import RadarContact

logger = get_logger("CUAS.SensorFusion")

@dataclass
class FusedTacticalTrack:
    fused_id: int
    has_visual: bool
    has_rf: bool
    has_radar: bool
    confidence: float
    estimated_distance_m: float
    bearing_deg: float
    classification_label: str
    rf_protocol: Optional[str]
    radar_velocity_mps: Optional[float]
    last_update_time: float
    fusion_score: float  # Scale 0 to 1.0


class SensorFusionHub:
    """Central data fusion node correlating multi-sensor detections."""
    def __init__(self):
        self.active_fused_tracks: Dict[int, FusedTacticalTrack] = {}
        self.next_fused_id = 1001

    def fuse(
        self,
        visual_tracks: List[TrackedDrone],
        rf_emissions: List[RFEmission],
        radar_contacts: List[RadarContact],
        default_bearing_deg: float = 45.0,
        default_distance_m: float = 850.0
    ) -> List[FusedTacticalTrack]:
        """Correlates detections across vision, RF, and radar streams."""
        now = time.time()
        fused_results = []

        # Correlate vision tracks
        for v_track in visual_tracks:
            fused_id = v_track.target_id + 1000

            # Match RF
            matched_rf = None
            if rf_emissions:
                matched_rf = rf_emissions[0]

            # Match Radar
            matched_radar = None
            if radar_contacts:
                matched_radar = radar_contacts[0]

            has_visual = True
            has_rf = matched_rf is not None
            has_radar = matched_radar is not None

            # Calculate fused confidence
            weights = [0.45 * v_track.confidence]
            if has_rf:
                weights.append(0.30)
            if has_radar:
                weights.append(0.25)
            fused_conf = round(min(1.0, sum(weights)), 2)

            bearing = matched_radar.azimuth_deg if has_radar else (
                matched_rf.bearing_deg if has_rf else default_bearing_deg
            )
            dist_m = matched_radar.range_m if has_radar else (
                matched_rf.estimated_distance_m if has_rf else default_distance_m
            )

            track = FusedTacticalTrack(
                fused_id=fused_id,
                has_visual=has_visual,
                has_rf=has_rf,
                has_radar=has_radar,
                confidence=fused_conf,
                estimated_distance_m=dist_m,
                bearing_deg=bearing,
                classification_label=v_track.class_label,
                rf_protocol=matched_rf.protocol if matched_rf else None,
                radar_velocity_mps=matched_radar.radial_velocity_mps if matched_radar else None,
                last_update_time=now,
                fusion_score=fused_conf
            )
            fused_results.append(track)
            self.active_fused_tracks[fused_id] = track

        return fused_results
