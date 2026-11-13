"""
Radio Frequency (RF) Signal Detection & Spectrum Analyzer for CUAS.
Scans civilian and military ISM bands, fingerprints drone C2 protocol telemetry,
and computes angle of arrival (AoA) and RSSI triangulation.
"""

from dataclasses import dataclass
import random
import time
from typing import List, Optional, Dict, Any

from utils.logger import get_logger

logger = get_logger("CUAS.RFSensor")

@dataclass
class RFEmission:
    frequency_mhz: float
    bandwidth_mhz: float
    rssi_dbm: float                    # Received Signal Strength Indicator (-100 to -20 dBm)
    snr_db: float                      # Signal-to-Noise Ratio
    protocol: str                      # "OcuSync-3", "Lightbridge", "ExpressLRS", "Crossfire", "WiFi"
    mac_address_oui: str               # Manufacturer ID / MAC prefix
    bearing_deg: float                 # Estimated Angle of Arrival (AoA)
    estimated_distance_m: float
    detected_timestamp: float


class RFSensorSimulator:
    """Simulates multi-channel Software Defined Radio (SDR) receiver."""
    def __init__(
        self,
        scan_frequencies_mhz: Optional[List[float]] = None,
        antenna_count: int = 3
    ):
        self.frequencies = scan_frequencies_mhz or [2412.0, 2437.0, 2462.0, 5745.0, 5805.0]
        self.antenna_count = antenna_count
        self.noise_floor_dbm = -95.0
        self.active_emissions: Dict[str, RFEmission] = {}

    def scan_spectrum(self, simulated_target_bearing: Optional[float] = None, distance_m: Optional[float] = None) -> List[RFEmission]:
        """Scans RF spectrum and returns detected RF emissions."""
        now = time.time()
        emissions = []

        # If a drone target is in range, generate realistic RF signature
        if simulated_target_bearing is not None and distance_m is not None and distance_m < 4000.0:
            # Free-space path loss model for RSSI
            freq_ghz = 2.45
            # FSPL = 20log10(d) + 20log10(f) + 32.44
            fspl = 20 * random.uniform(0.95, 1.05) * (1.0 + (distance_m / 4000.0) * 2.0)
            tx_power_dbm = 23.0  # standard 200mW drone transmitter
            rssi = max(-92.0, min(-35.0, tx_power_dbm - 40.0 - (distance_m / 60.0)))

            protocols = ["OcuSync-3", "ExpressLRS", "TBS-Crossfire", "Lightbridge"]
            chosen_proto = protocols[0]

            emission = RFEmission(
                frequency_mhz=2437.0,
                bandwidth_mhz=20.0,
                rssi_dbm=round(rssi, 1),
                snr_db=round(rssi - self.noise_floor_dbm, 1),
                protocol=chosen_proto,
                mac_address_oui="60:60:1F (DJI Innovations)",
                bearing_deg=round((simulated_target_bearing + random.uniform(-2.0, 2.0)) % 360.0, 1),
                estimated_distance_m=round(distance_m * random.uniform(0.9, 1.1), 1),
                detected_timestamp=now
            )
            emissions.append(emission)

        return emissions
