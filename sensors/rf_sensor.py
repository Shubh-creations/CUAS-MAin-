"""
Radio Frequency (RF) Signal Detection, High-Resolution SDR Waterfall & Direction Finding (v4.0-Lattice).
Models software-defined radio (SDR) capturing 128-bin FFT Power Spectral Density (PSD) waterfall arrays
across 2.4 GHz, 5.8 GHz, and 900 MHz / 433 MHz bands.
Computes Angle of Arrival (AoA) bearing lobing and detects frequency-hopping (FHSS) telemetry anomalies.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
import math
import random
import time
import numpy as np

from utils.logger import get_logger

logger = get_logger("CUAS.RFSensor")

@dataclass
class RFEmission:
    frequency_mhz: float
    bandwidth_mhz: float
    rssi_dbm: float                         # Received Signal Strength (-105 to -20 dBm)
    snr_db: float                           # Signal-to-Noise Ratio
    protocol: str                           # "OcuSync-3", "ExpressLRS", "Crossfire", "WiFi-Telemetry", "RF-SILENT"
    mac_address_oui: str                    # Manufacturer ID or MAC prefix
    bearing_deg: float                      # Angle of Arrival (AoA)
    estimated_distance_m: float
    detected_timestamp: float
    is_frequency_hopping: bool = True
    hop_rate_hops_per_sec: float = 250.0    # FHSS hop rate
    waterfall_psd_bin_128: List[float] = field(default_factory=list) # 128-bin normalized dBm spectrum


class RFSensorSimulator:
    """
    High-Fidelity Multi-Channel SDR Receiver & Direction Finding (DF) Array.
    Generates 128-bin Power Spectral Density (PSD) waterfalls and AoA bearing lobes.
    """
    def __init__(
        self,
        scan_frequencies_mhz: Optional[List[float]] = None,
        noise_floor_dbm: float = -105.0
    ):
        self.scan_frequencies = scan_frequencies_mhz or [2412.0, 2437.0, 2462.0, 5745.0, 5805.0, 915.0]
        self.noise_floor_dbm = noise_floor_dbm
        self.last_scan_time = time.time()
        self.active_jammer_bands: List[str] = []

    def set_jammer_active(self, active_bands: List[str]):
        """Simulates jammer saturation of RF waterfall when countermeasures are engaged."""
        self.active_jammer_bands = active_bands

    def generate_waterfall_slice(self, center_freq_mhz: float = 2437.0, target_present: bool = True) -> List[float]:
        """
        Synthesizes a 128-bin FFT Power Spectral Density (PSD) array.
        Includes Gaussian background thermal noise floor (-105 dBm) plus FHSS drone carrier peaks
        or broadband jammer saturation.
        """
        bins = np.random.normal(self.noise_floor_dbm, 2.0, 128)

        # If jammer active on this band, flood the spectrum with white noise
        if any("2.4" in b for b in self.active_jammer_bands) or any("JAM" in b for b in self.active_jammer_bands):
            jammer_noise = np.random.normal(-35.0, 4.0, 128)
            bins = np.maximum(bins, jammer_noise)
            return [round(float(v), 1) for v in bins]

        if target_present:
            # Inject OFDM video carrier (wide bump ~20 bins wide)
            carrier_center = 64
            for i in range(carrier_center - 15, carrier_center + 15):
                dist_from_c = abs(i - carrier_center)
                peak_db = -65.0 - (dist_from_c * 1.5) + random.uniform(-1.5, 1.5)
                bins[i] = max(bins[i], peak_db)

            # Inject fast FHSS telemetry spikes
            hop_bin_1 = random.randint(10, 45)
            hop_bin_2 = random.randint(85, 120)
            bins[hop_bin_1] = max(bins[hop_bin_1], -52.0 + random.uniform(-2.0, 2.0))
            bins[hop_bin_2] = max(bins[hop_bin_2], -48.0 + random.uniform(-2.0, 2.0))

        return [round(float(v), 1) for v in bins]

    def scan_spectrum(
        self,
        simulated_target_bearing: Optional[float] = None,
        distance_m: Optional[float] = None,
        target_protocol: str = "OcuSync-3",
        is_rf_silent: bool = False
    ) -> List[RFEmission]:
        """Executes multi-channel spectrum sweep and returns active detected emissions."""
        now = time.time()
        emissions = []

        if is_rf_silent or simulated_target_bearing is None or distance_m is None or distance_m > 4200.0:
            return emissions

        # Free-Space Path Loss (FSPL) model
        # FSPL(dB) = 20*log10(d) + 20*log10(f_MHz) - 27.55
        freq_mhz = 2437.0 if "2.4" in target_protocol or "Ocu" in target_protocol else 5805.0
        fspl_db = 20.0 * math.log10(max(10.0, distance_m)) + 20.0 * math.log10(freq_mhz) - 27.55
        tx_power_dbm = 23.0 # Standard 200mW transmitter
        rx_antenna_gain_db = 14.0 # High-gain directional array
        rssi = tx_power_dbm + rx_antenna_gain_db - fspl_db + random.uniform(-1.5, 1.5)
        rssi = max(-102.0, min(-28.0, rssi))

        snr = rssi - self.noise_floor_dbm
        # Angle of Arrival (AoA) bearing lobing with variance proportional to 1/SNR
        aoa_std_deg = max(0.5, min(6.0, 25.0 / max(1.0, snr)))
        aoa_bearing = (simulated_target_bearing + random.gauss(0.0, aoa_std_deg)) % 360.0

        waterfall_psd = self.generate_waterfall_slice(center_freq_mhz=freq_mhz, target_present=True)

        oui_map = {
            "OcuSync-3": "60:60:1F (DJI Enterprise)",
            "ExpressLRS": "AC:87:A3 (ExpressLRS OpenTX)",
            "TBS-Crossfire": "94:B4:0F (TBS BlackSheep)",
            "MAVLink": "00:1B:C5 (Telemetry Radio)"
        }

        emission = RFEmission(
            frequency_mhz=freq_mhz,
            bandwidth_mhz=20.0,
            rssi_dbm=round(rssi, 1),
            snr_db=round(snr, 1),
            protocol=target_protocol,
            mac_address_oui=oui_map.get(target_protocol, "UNKNOWN (Proprietary FHSS)"),
            bearing_deg=round(aoa_bearing, 1),
            estimated_distance_m=round(distance_m * random.uniform(0.92, 1.08), 1),
            detected_timestamp=now,
            is_frequency_hopping=True,
            hop_rate_hops_per_sec=250.0 if "ExpressLRS" in target_protocol else 100.0,
            waterfall_psd_bin_128=waterfall_psd
        )
        emissions.append(emission)
        return emissions
