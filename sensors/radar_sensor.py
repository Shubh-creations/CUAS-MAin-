"""
3D Pulse-Doppler Radar Simulator for CUAS.
Models 360-degree radar sweeps, micro-Doppler rotor signatures,
azimuth/elevation angles, and Radar Cross Section (RCS) estimation.
"""

from dataclasses import dataclass
import math
import random
import time
from typing import List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger("CUAS.Radar")

@dataclass
class RadarContact:
    contact_id: int
    azimuth_deg: float          # 0 to 360 degrees
    elevation_deg: float        # -5 to +60 degrees
    range_m: float              # Radial distance
    radial_velocity_mps: float  # + approaching, - departing
    rcs_dbsm: float             # Radar Cross Section in dBsm (small drone: -20 to -10 dBsm)
    rotor_blade_detected: bool  # Micro-Doppler signature
    snr_db: float
    timestamp: float


class RadarSensorSimulator:
    """Simulates a tactical 3D Counter-UAS radar with rotating azimuth scan."""
    def __init__(self, sweep_rate_hz: float = 2.0, max_range_m: float = 5000.0):
        self.sweep_rate = sweep_rate_hz
        self.max_range_m = max_range_m
        self.current_azimuth = 0.0
        self.last_update = time.time()
        self.next_contact_id = 101

    def update_sweep(self) -> float:
        """Advances radar beam azimuth."""
        now = time.time()
        dt = now - self.last_update
        self.last_update = now
        self.current_azimuth = (self.current_azimuth + (self.sweep_rate * 360.0 * dt)) % 360.0
        return self.current_azimuth

    def scan_for_contacts(
        self,
        target_range_m: Optional[float] = None,
        target_azimuth_deg: Optional[float] = None,
        target_velocity_mps: Optional[float] = None
    ) -> List[RadarContact]:
        """Detects contacts illuminated by the radar antenna beam."""
        self.update_sweep()
        contacts = []

        if target_range_m is not None and target_azimuth_deg is not None:
            # Check if beam aligns with target within 15 degree beamwidth
            az_diff = abs(self.current_azimuth - target_azimuth_deg)
            if az_diff > 180.0:
                az_diff = 360.0 - az_diff

            if az_diff <= 25.0 and target_range_m <= self.max_range_m:
                contact = RadarContact(
                    contact_id=self.next_contact_id,
                    azimuth_deg=round((target_azimuth_deg + random.uniform(-0.5, 0.5)) % 360.0, 1),
                    elevation_deg=round(random.uniform(5.0, 15.0), 1),
                    range_m=round(target_range_m + random.uniform(-5.0, 5.0), 1),
                    radial_velocity_mps=round(target_velocity_mps or random.uniform(-18.0, 22.0), 1),
                    rcs_dbsm=round(random.uniform(-18.0, -12.0), 1),  # Typical drone RCS
                    rotor_blade_detected=True,
                    snr_db=round(random.uniform(14.0, 28.0), 1),
                    timestamp=time.time()
                )
                contacts.append(contact)

        return contacts
