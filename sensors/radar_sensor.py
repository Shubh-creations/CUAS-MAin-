"""
3D Phased-Array Pulse-Doppler Radar & Micro-Doppler Blade Flash Simulator (v4.0-Lattice).
Models an electronic-scan active electronically steered array (AESA) operating at 20 Hz track-while-scan.
Synthesizes Micro-Doppler rotor blade harmonic spectrograms to reliably separate
drones (high-RPM symmetric harmonics) from biological clutter (low-frequency flapping birds).
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import math
import random
import time
import numpy as np

from utils.logger import get_logger

logger = get_logger("CUAS.Radar")

@dataclass
class RadarContact:
    contact_id: int
    azimuth_deg: float                         # 0 to 360 degrees
    elevation_deg: float                       # -5 to +60 degrees
    range_m: float                             # Radial 3D distance
    radial_velocity_mps: float                 # + approaching, - departing
    rcs_dbsm: float                            # Radar Cross Section in dBsm (-20 to -10 typical for small UAV)
    rotor_blade_detected: bool                 # Micro-Doppler modulation detected
    snr_db: float
    timestamp: float
    # v4.0-Lattice Micro-Doppler & Phased Array Enhancements
    rotor_rpm_estimate: float = 18000.0        # Estimated rotor speed
    blade_count: int = 4                       # Quadrotor (4x2=8 blades)
    micro_doppler_spectrum_64: List[float] = field(default_factory=list) # 64-bin Doppler spectrum
    elevation_m: float = 120.0                 # Target altitude above radar plane
    track_quality: float = 0.95                # 0.0 to 1.0 confidence


class RadarSensorSimulator:
    """
    3D Phased-Array Pulse-Doppler Tactical Radar Simulator.
    Features 20 Hz track-while-scan update rate and micro-Doppler spectral physics.
    """
    def __init__(self, sweep_rate_hz: float = 2.0, max_range_m: float = 5000.0):
        self.sweep_rate = sweep_rate_hz
        self.max_range_m = max_range_m
        self.current_azimuth = 0.0
        self.last_update = time.time()
        self.next_contact_id = 201

    def update_sweep(self) -> float:
        now = time.time()
        dt = now - self.last_update
        self.last_update = now
        self.current_azimuth = (self.current_azimuth + (self.sweep_rate * 360.0 * dt)) % 360.0
        return self.current_azimuth

    def generate_micro_doppler_slice(
        self,
        base_velocity_mps: float = 18.0,
        rotor_rpm: float = 18000.0,
        is_bird: bool = False
    ) -> List[float]:
        """
        Synthesizes a 64-bin micro-Doppler velocity spectrogram slice.
        Quadrotors produce distinct symmetric sideband spikes (flashes) around the central body return.
        Birds produce asymmetric low-frequency bulk motion.
        """
        bins = np.random.normal(-45.0, 2.5, 64)
        center_bin = 32

        # Central fuselage/body radar return peak
        v_offset = int(max(-10, min(10, base_velocity_mps * 0.5)))
        body_bin = center_bin + v_offset
        if 0 <= body_bin < 64:
            bins[body_bin] = max(bins[body_bin], 15.0 + random.uniform(-2.0, 2.0))
            if body_bin - 1 >= 0: bins[body_bin - 1] = max(bins[body_bin - 1], 6.0)
            if body_bin + 1 < 64: bins[body_bin + 1] = max(bins[body_bin + 1], 6.0)

        if is_bird:
            # Low-frequency broad flapping modulation (< 10 Hz)
            for i in range(body_bin - 3, body_bin + 4):
                if 0 <= i < 64:
                    bins[i] = max(bins[i], -10.0 + random.uniform(-3.0, 3.0))
        else:
            # High-RPM rotor blade tip flashes (symmetric harmonics extending out to ±20 bins)
            tip_speed_factor = int(min(22, (rotor_rpm / 1000.0) * 0.9))
            for arm in [-tip_speed_factor, tip_speed_factor]:
                flash_bin = body_bin + arm
                if 0 <= flash_bin < 64:
                    bins[flash_bin] = max(bins[flash_bin], 4.0 + random.uniform(-1.5, 1.5))
                # First harmonic sideband
                arm_half = arm // 2
                half_bin = body_bin + arm_half
                if 0 <= half_bin < 64:
                    bins[half_bin] = max(bins[half_bin], -8.0 + random.uniform(-2.0, 2.0))

        return [round(float(v), 1) for v in bins]

    def scan_for_contacts(
        self,
        target_range_m: Optional[float] = None,
        target_azimuth_deg: Optional[float] = None,
        target_velocity_mps: Optional[float] = None,
        target_altitude_m: Optional[float] = None,
        rotor_rpm: float = 18000.0,
        is_bird: bool = False
    ) -> List[RadarContact]:
        """Scans radar surveillance sector and returns tracked 3D radar returns."""
        self.update_sweep()
        contacts = []

        if target_range_m is not None and target_azimuth_deg is not None:
            if target_range_m <= self.max_range_m:
                # Phased-Array Electronic Steering covers target within beam cone
                az_err = random.gauss(0.0, 0.4)
                range_err = random.gauss(0.0, 2.5)
                vel_mps = target_velocity_mps if target_velocity_mps is not None else random.uniform(14.0, 28.0)
                alt_m = target_altitude_m if target_altitude_m is not None else random.uniform(80.0, 240.0)

                elev_rad = math.atan2(alt_m, max(1.0, target_range_m))
                elev_deg = math.degrees(elev_rad)

                # Radar Cross Section in dBsm (small carbon-frame drone ~ -16 dBsm)
                rcs = -24.0 if is_bird else round(random.uniform(-18.0, -12.0), 1)

                # Radar equation SNR ~ RCS / R^4
                snr = max(8.0, min(36.0, 32.0 - 20.0 * math.log10(max(100.0, target_range_m) / 1000.0)))

                micro_doppler = self.generate_micro_doppler_slice(
                    base_velocity_mps=vel_mps,
                    rotor_rpm=rotor_rpm,
                    is_bird=is_bird
                )

                contact = RadarContact(
                    contact_id=self.next_contact_id,
                    azimuth_deg=round((target_azimuth_deg + az_err) % 360.0, 1),
                    elevation_deg=round(elev_deg, 1),
                    range_m=round(target_range_m + range_err, 1),
                    radial_velocity_mps=round(vel_mps, 1),
                    rcs_dbsm=rcs,
                    rotor_blade_detected=(not is_bird),
                    snr_db=round(snr, 1),
                    timestamp=time.time(),
                    rotor_rpm_estimate=rotor_rpm if not is_bird else 0.0,
                    blade_count=4 if not is_bird else 0,
                    micro_doppler_spectrum_64=micro_doppler,
                    elevation_m=round(alt_m, 1),
                    track_quality=round(min(1.0, snr / 25.0), 2)
                )
                contacts.append(contact)

        return contacts
