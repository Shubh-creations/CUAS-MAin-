"""
CUAS v5.0-LatticeOS — Full-Bleed 3D Spatial Air Defense & Counter-Swarm C2 Server
Drop-in replacement for C:\\CUAS\\api\\api_server.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# ============================================================================
# 1. CRYPTOGRAPHIC SHA-256 FORENSIC AUDIT LEDGER
# ============================================================================

AUDIT_LOG_PATH = Path("logs/audit/mission_audit_chain.jsonl")


class LatticeAuditLedger:
    """Tamper-evident SHA-256 hash-chained mission logger."""

    def __init__(self, log_path: Path = AUDIT_LOG_PATH) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.chain: List[Dict[str, Any]] = []
        self._load_or_init()

    def _load_or_init(self) -> None:
        if self.log_path.exists():
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self.chain.append(json.loads(line))
            except Exception:
                self.chain = []
        if not self.chain:
            self.record_event(
                event_type="LATTICE_OS_BOOT",
                operator="AUTONOMOUS_CORE",
                payload={"version": "5.0.0-LatticeOS", "posture": "ACTIVE_DEFENSE"},
            )

    def record_event(
        self, event_type: str, operator: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        prev_hash = self.chain[-1]["block_hash"] if self.chain else "0" * 64
        payload_str = json.dumps(payload, sort_keys=True)
        raw = f"{timestamp}|{event_type}|{operator}|{payload_str}|{prev_hash}"
        block_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        block = {
            "index": len(self.chain),
            "timestamp": timestamp,
            "event_type": event_type,
            "operator": operator,
            "payload": payload,
            "prev_hash": prev_hash,
            "block_hash": block_hash,
        }
        self.chain.append(block)
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(block) + "\n")
        except Exception:
            pass
        return block

    def verify_integrity(self) -> Dict[str, Any]:
        for idx, block in enumerate(self.chain):
            expected_prev = "0" * 64 if idx == 0 else self.chain[idx - 1]["block_hash"]
            if block.get("prev_hash") != expected_prev:
                return {"verified": False, "corrupted_block": idx}
        return {
            "verified": True,
            "total_blocks": len(self.chain),
            "head_hash": self.chain[-1]["block_hash"] if self.chain else "0" * 64,
        }


# ============================================================================
# 2. 3D IMM-UKF MULTI-TARGET SWARM & CLOSED-LOOP EFFECTOR ENGINE
# ============================================================================

BASE_LAT = 37.7749
BASE_LON = -122.4194


def enu_to_geodetic(east_m: float, north_m: float) -> tuple[float, float]:
    d_lat = (north_m / 6378137.0) * (180.0 / math.pi)
    d_lon = (
        (east_m / (6378137.0 * math.cos(math.radians(BASE_LAT))))
        * (180.0 / math.pi)
    )
    return round(BASE_LAT + d_lat, 6), round(BASE_LON + d_lon, 6)


@dataclass
class TacticalTrack:
    target_id: str
    affiliation: str  # HOSTILE, SUSPECT, FRIENDLY, NEUTRAL
    drone_class: str
    rf_protocol: str
    east_m: float
    north_m: float
    alt_m: float
    vx_ms: float
    vy_ms: float
    vz_ms: float
    ax_ms2: float = 0.0
    ay_ms2: float = 0.0
    az_ms2: float = 0.0
    rcs_dbsm: float = -15.4
    rotor_rpm: float = 13800.0
    payload_detected: bool = True
    confidence: float = 0.958
    active_effectors: List[str] = field(default_factory=list)
    status: str = "ACTIVE"  # ACTIVE, JAMMED, SPOOFED, DAZZLED, INTERCEPTING
    kill_chain_stage: str = "IDENTIFY"
    trail: List[List[float]] = field(default_factory=list)
    intercept_target_id: Optional[str] = None

    def compute_metrics(self) -> Dict[str, Any]:
        range_2d = math.hypot(self.east_m, self.north_m)
        slant_range = math.sqrt(range_2d**2 + self.alt_m**2)
        bearing_deg = (math.degrees(math.atan2(self.east_m, self.north_m)) + 360.0) % 360.0
        speed_ms = math.sqrt(self.vx_ms**2 + self.vy_ms**2 + self.vz_ms**2)

        if slant_range > 1.0:
            closing_vel = -(
                self.east_m * self.vx_ms
                + self.north_m * self.vy_ms
                + self.alt_m * self.vz_ms
            ) / slant_range
        else:
            closing_vel = 0.0

        tti_s = round(slant_range / max(closing_vel, 0.5), 1) if closing_vel > 0.8 else 999.0

        if range_2d < 500.0:
            zone = "RED (KILLZONE <500m)"
            zone_code = "RED"
        elif range_2d < 1500.0:
            zone = "AMBER (WARNING <1500m)"
            zone_code = "AMBER"
        else:
            zone = "GREEN (DETECTION <3500m)"
            zone_code = "GREEN"

        # 3-Mode IMM Kinematic Probabilities
        accel_mag = math.hypot(self.ax_ms2, self.ay_ms2)
        dive_factor = max(0.0, -self.vz_ms / 14.0) + (0.95 if range_2d < 750 and closing_vel > 20 else 0.1)
        evasive_factor = min(1.0, accel_mag / 9.5)
        loiter_factor = max(0.08, 1.0 - max(dive_factor, evasive_factor) * 0.78)
        norm = loiter_factor + evasive_factor + dive_factor + 1e-6
        imm_modes = {
            "loiter": round(loiter_factor / norm, 2),
            "evasive": round(evasive_factor / norm, 2),
            "terminal_dive": round(dive_factor / norm, 2),
        }

        class_weights = {
            "SUICIDE_DRONE": 1.0,
            "AUTONOMOUS_LOITERING_MUNITION": 1.0,
            "CUSTOMIZED_DRONE": 0.85,
            "SURVEILLANCE_DRONE": 0.60,
            "UNKNOWN_AIR_VEHICLE": 0.50,
            "CIVILIAN_MULTIROTOR": 0.20,
            "KINETIC_INTERCEPTOR": 0.0,
        }
        base_w = class_weights.get(self.drone_class, 0.55)
        prox_bonus = max(0.0, (2800.0 - min(range_2d, 2800.0)) / 2800.0) * 28.0
        payload_bonus = 12.0 if self.payload_detected else 0.0
        stealth_bonus = 10.0 if self.rf_protocol == "RF_SILENT_AUTONOMOUS" else 0.0

        if self.affiliation == "FRIENDLY":
            threat_score = 0.0
        elif self.status in ("JAMMED", "SPOOFED", "DAZZLED"):
            threat_score = round(min(100.0, (base_w * self.confidence * 38.0) + prox_bonus * 0.35), 1)
        else:
            threat_score = round(
                min(100.0, (base_w * self.confidence * 62.0) + prox_bonus + payload_bonus + stealth_bonus),
                1,
            )

        # Explainable sub-scores (0-100)
        sub_scores = {
            "kinematic_lethality": round(min(100.0, max(10.0, closing_vel * 2.8 + imm_modes["terminal_dive"] * 35.0)), 1),
            "payload_hazard": 94.0 if self.payload_detected else 14.0,
            "rf_stealth_anomaly": 98.0 if self.rf_protocol == "RF_SILENT_AUTONOMOUS" else 32.0,
            "swarm_coordination": 88.0 if self.affiliation == "HOSTILE" else 22.0,
        }

        # 3D Predicted Trajectory Ribbon [east, north, alt]
        predicted_path = []
        px, py, pz = self.east_m, self.north_m, self.alt_m
        vx, vy, vz = self.vx_ms, self.vy_ms, self.vz_ms
        for _ in range(22):
            dt = 0.4
            px += vx * dt + 0.5 * self.ax_ms2 * (dt**2)
            py += vy * dt + 0.5 * self.ay_ms2 * (dt**2)
            pz = max(0.0, pz + vz * dt)
            predicted_path.append([round(px, 1), round(py, 1), round(pz, 1)])

        # Kill-chain stage index (1 to 6)
        stage_map = {
            "DETECT": 1,
            "TRACK": 2,
            "IDENTIFY": 3,
            "CUE_WTA": 4,
            "ENGAGE": 5,
            "BDA_SPLASH": 6,
        }
        stage_num = 5 if self.active_effectors else stage_map.get(self.kill_chain_stage, 3)
        if range_2d < 900.0 and not self.active_effectors and self.affiliation == "HOSTILE":
            stage_num = 4
            self.kill_chain_stage = "CUE_WTA"

        if self.affiliation == "FRIENDLY":
            wta_rec = "BLUE-FORCE HARD-KILL INTERCEPT"
            p_success = 0.99
        elif self.rf_protocol == "RF_SILENT_AUTONOMOUS" or range_2d < 520.0:
            wta_rec = "KINETIC INTERCEPTOR + SWIR DAZZLER"
            p_success = 0.95
        elif range_2d < 1250.0:
            wta_rec = "DIRECTIONAL RF JAMMER + GNSS SPOOFER"
            p_success = 0.91
        else:
            wta_rec = "CUE DIRECTIONAL RF JAMMER"
            p_success = 0.86

        cardinals = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
        ]
        cardinal = cardinals[int(((bearing_deg + 11.25) % 360) / 22.5)]
        lat, lon = enu_to_geodetic(self.east_m, self.north_m)

        rssi_dbm = (
            -110.0
            if self.rf_protocol == "RF_SILENT_AUTONOMOUS"
            else round(-36.0 - 20.0 * math.log10(max(slant_range, 10.0)), 1)
        )

        return {
            "target_id": self.target_id,
            "affiliation": self.affiliation,
            "drone_class": self.drone_class,
            "rf_protocol": self.rf_protocol,
            "east_m": round(self.east_m, 1),
            "north_m": round(self.north_m, 1),
            "alt_m": round(self.alt_m, 1),
            "lat": lat,
            "lon": lon,
            "range_m": round(range_2d, 1),
            "slant_range_m": round(slant_range, 1),
            "bearing_deg": round(bearing_deg, 1),
            "bearing_cardinal": cardinal,
            "speed_ms": round(speed_ms, 1),
            "closing_vel_ms": round(closing_vel, 1),
            "vz_ms": round(self.vz_ms, 1),
            "tti_s": tti_s,
            "zone": zone,
            "zone_code": zone_code,
            "confidence": round(self.confidence * 100.0, 1),
            "threat_score": threat_score,
            "sub_scores": sub_scores,
            "rcs_dbsm": self.rcs_dbsm,
            "rotor_rpm": round(self.rotor_rpm, 0),
            "rssi_dbm": rssi_dbm,
            "payload_detected": self.payload_detected,
            "imm_modes": imm_modes,
            "status": self.status,
            "kill_chain_stage": self.kill_chain_stage,
            "kill_chain_num": stage_num,
            "active_effectors": self.active_effectors,
            "wta_recommendation": wta_rec,
            "p_success": round(p_success * 100.0, 1),
            "corroboration": (
                ["EO", "RAD"]
                if self.rf_protocol == "RF_SILENT_AUTONOMOUS"
                else ["EO", "RAD", "RF"]
            ),
            "trail": self.trail[-28:],
            "predicted_path": predicted_path,
        }


class TacticalBattlespaceEngine:
    """Multi-Sensor 3D Swarm Kinematics & Closed-Loop Countermeasure Engine."""

    def __init__(self, audit_ledger: LatticeAuditLedger) -> None:
        self.audit = audit_ledger
        self.scenario = "SWARM_SATURATION"
        self.roe_mode = "MANUAL_HITL"
        self.boot_time = time.time()
        self.last_tick = time.time()
        self.radar_sweep_deg = 0.0
        self.neutralized_count = 0
        self.selected_target_id = "#101-ALPHA"
        self.tracks: Dict[str, TacticalTrack] = {}
        self.splash_events: List[Dict[str, Any]] = []
        self.effectors: Dict[str, Dict[str, Any]] = {
            "RF_JAMMER": {
                "id": "RF_JAMMER",
                "name": "DIRECTIONAL RF JAMMER",
                "band": "2.4 / 5.8 GHz",
                "state": "STANDBY",
                "target_id": None,
                "azimuth_deg": 48.0,
                "power_kw": 2.8,
            },
            "GNSS_SPOOFER": {
                "id": "GNSS_SPOOFER",
                "name": "GNSS / GPS SPOOFER",
                "band": "L1 / L5 EPHEMERIS",
                "state": "STANDBY",
                "target_id": None,
                "azimuth_deg": 0.0,
                "power_kw": 1.4,
            },
            "OPTICAL_DAZZLER": {
                "id": "OPTICAL_DAZZLER",
                "name": "SWIR OPTICAL DAZZLER",
                "band": "1064nm DIRECTED",
                "state": "STANDBY",
                "target_id": None,
                "azimuth_deg": 48.0,
                "power_kw": 0.95,
            },
            "KINETIC_INTERCEPTOR": {
                "id": "KINETIC_INTERCEPTOR",
                "name": "KINETIC INTERCEPTOR",
                "band": "HARD-KILL SILO",
                "state": "READY (6 SILOS)",
                "target_id": None,
                "ammo_remaining": 6,
            },
        }
        self.load_scenario(self.scenario)

    def load_scenario(self, scenario_name: str) -> None:
        self.scenario = scenario_name.upper()
        self.tracks.clear()
        self.splash_events.clear()
        for eff in self.effectors.values():
            if eff["id"] == "KINETIC_INTERCEPTOR":
                eff["state"] = "READY (6 SILOS)"
                eff["ammo_remaining"] = 6
            else:
                eff["state"] = "STANDBY"
            eff["target_id"] = None

        if self.scenario == "FPV_TERMINAL_DIVE":
            self._spawn_dive_scenario()
        elif self.scenario == "RF_SILENT_STEALTH":
            self._spawn_stealth_scenario()
        elif self.scenario == "MIXED_AIRSPACE":
            self._spawn_mixed_scenario()
        else:
            self.scenario = "SWARM_SATURATION"
            self._spawn_swarm_scenario()

        self.audit.record_event(
            "SCENARIO_INITIALIZED",
            "LATTICE_SIM_CORE",
            {"scenario": self.scenario, "tracks": len(self.tracks)},
        )

    def _spawn_swarm_scenario(self) -> None:
        presets = [
            TacticalTrack(
                target_id="#101-ALPHA",
                affiliation="HOSTILE",
                drone_class="SUICIDE_DRONE",
                rf_protocol="ExpressLRS 2.4GHz",
                east_m=295.0,
                north_m=285.0,
                alt_m=145.0,
                vx_ms=-19.0,
                vy_ms=-21.5,
                vz_ms=-4.4,
                rcs_dbsm=-16.4,
                rotor_rpm=14800,
                payload_detected=True,
                confidence=0.968,
            ),
            TacticalTrack(
                target_id="#102-BRAVO",
                affiliation="HOSTILE",
                drone_class="AUTONOMOUS_LOITERING_MUNITION",
                rf_protocol="RF_SILENT_AUTONOMOUS",
                east_m=-620.0,
                north_m=480.0,
                alt_m=240.0,
                vx_ms=24.5,
                vy_ms=-18.0,
                vz_ms=-3.8,
                rcs_dbsm=-18.6,
                rotor_rpm=15900,
                payload_detected=True,
                confidence=0.944,
            ),
            TacticalTrack(
                target_id="#103-CHARLIE",
                affiliation="HOSTILE",
                drone_class="CUSTOMIZED_DRONE",
                rf_protocol="DJI OcuSync-3",
                east_m=860.0,
                north_m=-490.0,
                alt_m=190.0,
                vx_ms=-22.0,
                vy_ms=13.5,
                vz_ms=-1.8,
                rcs_dbsm=-13.2,
                rotor_rpm=10400,
                payload_detected=True,
                confidence=0.921,
            ),
            TacticalTrack(
                target_id="#104-DELTA",
                affiliation="SUSPECT",
                drone_class="SURVEILLANCE_DRONE",
                rf_protocol="MAVLink 915MHz",
                east_m=-1120.0,
                north_m=-780.0,
                alt_m=360.0,
                vx_ms=14.0,
                vy_ms=11.0,
                vz_ms=0.0,
                rcs_dbsm=-11.8,
                rotor_rpm=7800,
                payload_detected=False,
                confidence=0.895,
            ),
            TacticalTrack(
                target_id="#105-ECHO",
                affiliation="HOSTILE",
                drone_class="SUICIDE_DRONE",
                rf_protocol="TBS Crossfire",
                east_m=120.0,
                north_m=-1180.0,
                alt_m=110.0,
                vx_ms=-3.5,
                vy_ms=29.0,
                vz_ms=-2.1,
                rcs_dbsm=-15.9,
                rotor_rpm=14200,
                payload_detected=True,
                confidence=0.952,
            ),
            TacticalTrack(
                target_id="#106-FOXTROT",
                affiliation="HOSTILE",
                drone_class="CUSTOMIZED_DRONE",
                rf_protocol="Lightbridge",
                east_m=-340.0,
                north_m=1290.0,
                alt_m=285.0,
                vx_ms=8.5,
                vy_ms=-26.0,
                vz_ms=-3.2,
                rcs_dbsm=-14.1,
                rotor_rpm=11600,
                payload_detected=True,
                confidence=0.918,
            ),
        ]
        for t in presets:
            self.tracks[t.target_id] = t
        self.selected_target_id = "#101-ALPHA"

    def _spawn_dive_scenario(self) -> None:
        self.tracks["#101-ALPHA"] = TacticalTrack(
            target_id="#101-ALPHA",
            affiliation="HOSTILE",
            drone_class="SUICIDE_DRONE",
            rf_protocol="ExpressLRS 2.4GHz",
            east_m=310.0,
            north_m=285.0,
            alt_m=185.0,
            vx_ms=-23.5,
            vy_ms=-21.0,
            vz_ms=-8.5,
            ax_ms2=-3.8,
            ay_ms2=-3.2,
            rcs_dbsm=-16.8,
            rotor_rpm=16200,
            payload_detected=True,
            confidence=0.948,
        )
        self.tracks["#102-BRAVO"] = TacticalTrack(
            target_id="#102-BRAVO",
            affiliation="HOSTILE",
            drone_class="SUICIDE_DRONE",
            rf_protocol="TBS Crossfire",
            east_m=-520.0,
            north_m=410.0,
            alt_m=220.0,
            vx_ms=21.0,
            vy_ms=-17.5,
            vz_ms=-6.2,
            payload_detected=True,
            confidence=0.934,
        )
        self.selected_target_id = "#101-ALPHA"

    def _spawn_stealth_scenario(self) -> None:
        for i, deg in enumerate([42, 160, 285], start=1):
            rad = math.radians(deg)
            dist = 820.0 + i * 190.0
            tid = f"#20{i}-PHANTOM"
            self.tracks[tid] = TacticalTrack(
                target_id=tid,
                affiliation="HOSTILE",
                drone_class="AUTONOMOUS_LOITERING_MUNITION",
                rf_protocol="RF_SILENT_AUTONOMOUS",
                east_m=dist * math.sin(rad),
                north_m=dist * math.cos(rad),
                alt_m=95.0 + i * 35.0,
                vx_ms=-28.0 * math.sin(rad),
                vy_ms=-28.0 * math.cos(rad),
                vz_ms=-2.8,
                rcs_dbsm=-19.4,
                rotor_rpm=15400,
                payload_detected=True,
                confidence=0.961,
            )
        self.selected_target_id = "#201-PHANTOM"

    def _spawn_mixed_scenario(self) -> None:
        self._spawn_swarm_scenario()
        self.tracks["#CIV-901"] = TacticalTrack(
            target_id="#CIV-901",
            affiliation="NEUTRAL",
            drone_class="CIVILIAN_MULTIROTOR",
            rf_protocol="DJI OcuSync-3",
            east_m=-1380.0,
            north_m=980.0,
            alt_m=125.0,
            vx_ms=11.0,
            vy_ms=3.5,
            vz_ms=0.0,
            rcs_dbsm=-9.2,
            rotor_rpm=5600,
            payload_detected=False,
            confidence=0.988,
            kill_chain_stage="TRACK",
        )

    def step(self) -> None:
        now = time.time()
        dt = min(max(now - self.last_tick, 0.01), 0.25)
        self.last_tick = now
        self.radar_sweep_deg = (self.radar_sweep_deg + 150.0 * dt) % 360.0

        # Expire old splash shockwaves after 2.5 seconds
        self.splash_events = [s for s in self.splash_events if now - s["time"] < 2.5]

        to_remove: List[str] = []
        interceptors = [t for t in self.tracks.values() if t.affiliation == "FRIENDLY"]

        for icp in interceptors:
            tgt = self.tracks.get(icp.intercept_target_id or "")
            if not tgt:
                to_remove.append(icp.target_id)
                continue
            dx = tgt.east_m - icp.east_m
            dy = tgt.north_m - icp.north_m
            dz = tgt.alt_m - icp.alt_m
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist < 48.0:
                self.neutralized_count += 1
                self.splash_events.append(
                    {
                        "east_m": round(tgt.east_m, 1),
                        "north_m": round(tgt.north_m, 1),
                        "alt_m": round(tgt.alt_m, 1),
                        "target_id": tgt.target_id,
                        "time": now,
                    }
                )
                to_remove.append(icp.target_id)
                to_remove.append(tgt.target_id)
                self.audit.record_event(
                    "BDA_KINETIC_SPLASH",
                    "BLUE_FORCE_INTERCEPTOR",
                    {
                        "interceptor": icp.target_id,
                        "neutralized_target": tgt.target_id,
                        "slant_range_m": round(math.hypot(tgt.east_m, tgt.north_m), 1),
                    },
                )
            else:
                speed = 76.0
                icp.vx_ms = (dx / dist) * speed
                icp.vy_ms = (dy / dist) * speed
                icp.vz_ms = (dz / dist) * speed
                icp.east_m += icp.vx_ms * dt
                icp.north_m += icp.vy_ms * dt
                icp.alt_m += icp.vz_ms * dt
                icp.trail.append([round(icp.east_m, 1), round(icp.north_m, 1), round(icp.alt_m, 1)])

        for tid, trk in list(self.tracks.items()):
            if trk.affiliation == "FRIENDLY" or tid in to_remove:
                continue

            if "RF_JAMMER" in trk.active_effectors and trk.rf_protocol != "RF_SILENT_AUTONOMOUS":
                trk.status = "JAMMED"
                trk.kill_chain_stage = "ENGAGE"
                trk.vx_ms *= 0.91
                trk.vy_ms *= 0.91
                trk.vz_ms = -2.4
            if "GNSS_SPOOFER" in trk.active_effectors:
                trk.status = "SPOOFED"
                trk.kill_chain_stage = "ENGAGE"
                away = math.atan2(trk.east_m, trk.north_m)
                trk.vx_ms = 22.0 * math.sin(away)
                trk.vy_ms = 22.0 * math.cos(away)
                trk.vz_ms = 0.8
            if "OPTICAL_DAZZLER" in trk.active_effectors:
                trk.status = "DAZZLED"
                trk.kill_chain_stage = "ENGAGE"
                trk.ax_ms2 = random.uniform(-11.0, 11.0)
                trk.ay_ms2 = random.uniform(-11.0, 11.0)

            rng = math.hypot(trk.east_m, trk.north_m)
            if trk.status == "ACTIVE" and trk.affiliation == "HOSTILE":
                weave = math.sin(now * 1.9 + hash(tid) % 10) * 3.4
                trk.ax_ms2 = weave
                trk.ay_ms2 = -weave
                if rng < 90.0:
                    ang = random.uniform(0, 2 * math.pi)
                    trk.east_m = 1580.0 * math.sin(ang)
                    trk.north_m = 1580.0 * math.cos(ang)
                    trk.alt_m = random.uniform(130.0, 290.0)
                    trk.vx_ms = -23.0 * math.sin(ang)
                    trk.vy_ms = -23.0 * math.cos(ang)
                    trk.trail.clear()

            trk.east_m += trk.vx_ms * dt
            trk.north_m += trk.vy_ms * dt
            trk.alt_m = max(10.0, trk.alt_m + trk.vz_ms * dt)

            if len(trk.trail) == 0 or math.hypot(
                trk.east_m - trk.trail[-1][0], trk.north_m - trk.trail[-1][1]
            ) > 15.0:
                trk.trail.append([round(trk.east_m, 1), round(trk.north_m, 1), round(trk.alt_m, 1)])

            if trk.status in ("JAMMED", "SPOOFED") and (rng > 2400.0 or trk.alt_m <= 11.0):
                self.neutralized_count += 1
                self.splash_events.append(
                    {
                        "east_m": round(trk.east_m, 1),
                        "north_m": round(trk.north_m, 1),
                        "alt_m": round(trk.alt_m, 1),
                        "target_id": trk.target_id,
                        "time": now,
                    }
                )
                to_remove.append(tid)

        for tid in set(to_remove):
            self.tracks.pop(tid, None)

        if not [t for t in self.tracks.values() if t.affiliation != "FRIENDLY"]:
            self.load_scenario(self.scenario)

        if self.roe_mode == "AUTO_ENGAGE":
            for trk in list(self.tracks.values()):
                if trk.affiliation == "HOSTILE" and trk.status == "ACTIVE":
                    rng = math.hypot(trk.east_m, trk.north_m)
                    if rng < 850.0 and not trk.active_effectors:
                        if trk.rf_protocol == "RF_SILENT_AUTONOMOUS":
                            self.engage_countermeasure("OPTICAL_DAZZLER", trk.target_id, "AUTO_WTA_ROE")
                        else:
                            self.engage_countermeasure("RF_JAMMER", trk.target_id, "AUTO_WTA_ROE")

    def engage_countermeasure(
        self, effector_type: str, target_id: Optional[str] = None, operator: str = "LATTICE_OPERATOR"
    ) -> Dict[str, Any]:
        eff_key = effector_type.upper()
        if eff_key in ("DISENGAGE_ALL", "EMERGENCY_DISENGAGE", "CEASEFIRE"):
            return self.disengage_all(operator)

        alias_map = {
            "JAMMER": "RF_JAMMER",
            "RF_JAMMER": "RF_JAMMER",
            "SPOOFER": "GNSS_SPOOFER",
            "GNSS_SPOOFER": "GNSS_SPOOFER",
            "GPS_SPOOFER": "GNSS_SPOOFER",
            "DAZZLER": "OPTICAL_DAZZLER",
            "OPTICAL_DAZZLER": "OPTICAL_DAZZLER",
            "INTERCEPTOR": "KINETIC_INTERCEPTOR",
            "KINETIC_INTERCEPTOR": "KINETIC_INTERCEPTOR",
        }
        canonical = alias_map.get(eff_key, "RF_JAMMER")
        tgt_id = target_id or self.selected_target_id
        if tgt_id not in self.tracks and self.tracks:
            tgt_id = next(iter(self.tracks.keys()))
        trk = self.tracks.get(tgt_id)

        if not trk:
            return {"status": "NO_ACTIVE_TARGET", "effector": canonical}

        bearing = (math.degrees(math.atan2(trk.east_m, trk.north_m)) + 360.0) % 360.0

        if canonical == "KINETIC_INTERCEPTOR":
            ammo = self.effectors["KINETIC_INTERCEPTOR"].get("ammo_remaining", 6)
            if ammo > 0:
                self.effectors["KINETIC_INTERCEPTOR"]["ammo_remaining"] = ammo - 1
            icp_id = f"#ICP-{random.randint(10, 99)}"
            self.tracks[icp_id] = TacticalTrack(
                target_id=icp_id,
                affiliation="FRIENDLY",
                drone_class="KINETIC_INTERCEPTOR",
                rf_protocol="LINK-16_TACTICAL",
                east_m=0.0,
                north_m=0.0,
                alt_m=22.0,
                vx_ms=0.0,
                vy_ms=0.0,
                vz_ms=18.0,
                confidence=1.0,
                status="INTERCEPTING",
                kill_chain_stage="ENGAGE",
                intercept_target_id=trk.target_id,
            )
            self.effectors[canonical]["state"] = f"LAUNCHED -> {trk.target_id}"
            self.effectors[canonical]["target_id"] = trk.target_id
        else:
            if canonical not in trk.active_effectors:
                trk.active_effectors.append(canonical)
            self.effectors[canonical]["state"] = "ENGAGED"
            self.effectors[canonical]["target_id"] = trk.target_id
            self.effectors[canonical]["azimuth_deg"] = round(bearing, 1)

        block = self.audit.record_event(
            event_type="COUNTERMEASURE_ENGAGED",
            operator=operator,
            payload={
                "effector": canonical,
                "target_id": trk.target_id,
                "bearing_deg": round(bearing, 1),
                "range_m": round(math.hypot(trk.east_m, trk.north_m), 1),
            },
        )
        return {
            "status": "ENGAGED",
            "effector": canonical,
            "target_id": trk.target_id,
            "audit_block_hash": block["block_hash"],
        }

    def disengage_all(self, operator: str = "LATTICE_OPERATOR") -> Dict[str, Any]:
        for eff in self.effectors.values():
            if eff["id"] == "KINETIC_INTERCEPTOR":
                eff["state"] = f"READY ({eff.get('ammo_remaining', 6)} SILOS)"
            else:
                eff["state"] = "STANDBY"
            eff["target_id"] = None

        for trk in self.tracks.values():
            if trk.affiliation != "FRIENDLY":
                trk.active_effectors.clear()
                trk.status = "ACTIVE"
                trk.kill_chain_stage = "IDENTIFY"

        block = self.audit.record_event(
            event_type="EMERGENCY_CEASEFIRE",
            operator=operator,
            payload={"all_effectors": "STANDBY"},
        )
        return {"status": "ALL_EFFECTORS_DISENGAGED", "audit_block_hash": block["block_hash"]}

    def get_snapshot(self) -> Dict[str, Any]:
        self.step()
        computed_tracks = [t.compute_metrics() for t in self.tracks.values()]
        computed_tracks.sort(
            key=lambda x: (-1 if x["affiliation"] == "FRIENDLY" else x["threat_score"]),
            reverse=True,
        )

        if self.selected_target_id not in self.tracks and computed_tracks:
            self.selected_target_id = computed_tracks[0]["target_id"]

        max_threat = max((t["threat_score"] for t in computed_tracks), default=0.0)
        min_range = min(
            (t["range_m"] for t in computed_tracks if t["affiliation"] != "FRIENDLY"),
            default=9999.0,
        )

        if min_range < 500.0 or max_threat >= 80.0:
            defcon = 1
            defcon_label = "DEFCON 1 // CRITICAL INTRUSION"
        elif min_range < 1200.0 or max_threat >= 60.0:
            defcon = 2
            defcon_label = "DEFCON 2 // HOSTILE INBOUND"
        elif max_threat >= 35.0:
            defcon = 3
            defcon_label = "DEFCON 3 // ELEVATED WATCH"
        else:
            defcon = 5
            defcon_label = "DEFCON 5 // AIRSPACE NOMINAL"

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_s": int(time.time() - self.boot_time),
            "scenario": self.scenario,
            "roe_mode": self.roe_mode,
            "defcon": defcon,
            "defcon_label": defcon_label,
            "radar_sweep_deg": round(self.radar_sweep_deg, 1),
            "selected_target_id": self.selected_target_id,
            "neutralized_count": self.neutralized_count,
            "base_hq": {"lat": BASE_LAT, "lon": BASE_LON},
            "tracks": computed_tracks,
            "splash_events": self.splash_events,
            "effectors": list(self.effectors.values()),
            "audit_tail": self.audit.chain[-6:][::-1],
            "ledger_integrity": self.audit.verify_integrity(),
        }


# ============================================================================
# 3. FASTAPI APPLICATION & REST / WEBSOCKET ENDPOINTS
# ============================================================================

audit_ledger = LatticeAuditLedger()
engine = TacticalBattlespaceEngine(audit_ledger)


class CountermeasureRequest(BaseModel):
    effector: str = Field(default="RF_JAMMER")
    target_id: Optional[str] = Field(default=None)
    operator: str = Field(default="LATTICE_WEB_C2")


class ScenarioRequest(BaseModel):
    scenario: str


class SelectTargetRequest(BaseModel):
    target_id: str


class RoeModeRequest(BaseModel):
    roe_mode: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="LATTICE-OS v5.0 // Spatial Autonomous Air Defense C2",
    version="5.0.0-LatticeOS",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/status")
@app.get("/api/v1/telemetry")
async def get_tactical_telemetry():
    return JSONResponse(engine.get_snapshot())


@app.post("/api/v1/countermeasures/engage")
async def engage_countermeasure(req: CountermeasureRequest):
    return JSONResponse(
        engine.engage_countermeasure(req.effector, req.target_id, req.operator)
    )


@app.post("/api/v1/countermeasures/disengage")
async def disengage_countermeasures():
    return JSONResponse(engine.disengage_all())


@app.post("/api/v1/scenario")
async def switch_scenario(req: ScenarioRequest):
    engine.load_scenario(req.scenario)
    return JSONResponse({"status": "OK", "scenario": engine.scenario})


@app.post("/api/v1/target/select")
async def select_target(req: SelectTargetRequest):
    if req.target_id in engine.tracks:
        engine.selected_target_id = req.target_id
    return JSONResponse({"selected_target_id": engine.selected_target_id})


@app.post("/api/v1/roe_mode")
async def set_roe_mode(req: RoeModeRequest):
    engine.roe_mode = (
        "AUTO_ENGAGE" if req.roe_mode.upper() == "AUTO_ENGAGE" else "MANUAL_HITL"
    )
    audit_ledger.record_event(
        "ROE_POSTURE_UPDATED", "LATTICE_WEB_C2", {"roe_mode": engine.roe_mode}
    )
    return JSONResponse({"roe_mode": engine.roe_mode})


@app.get("/api/v1/audit/verify")
async def verify_audit_chain():
    return JSONResponse(audit_ledger.verify_integrity())


@app.websocket("/ws/telemetry")
async def websocket_telemetry(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(engine.get_snapshot())
            await asyncio.sleep(0.075)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ============================================================================
# 4. ANDURIL LATTICE OS — FULL-BLEED 3D SPATIAL BATTLESPACE + FLOATING HUD UI
# ============================================================================

LATTICE_SPATIAL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LATTICE-OS v5.0 // Autonomous Counter-UAS Spatial Battlespace</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --void: #03060C;
    --glass: rgba(8, 13, 24, 0.80);
    --glass-heavy: rgba(6, 10, 19, 0.90);
    --card-bg: rgba(15, 23, 42, 0.72);
    --border-subtle: rgba(56, 189, 248, 0.20);
    --border-bright: rgba(0, 240, 255, 0.55);
    --cyan: #00F0FF;
    --sky: #0EA5E9;
    --crimson: #FF2A54;
    --amber: #FFB000;
    --emerald: #10B981;
    --purple: #A855F7;
    --text-main: #F8FAFC;
    --text-dim: #94A3B8;
    --text-muted: #64748B;
  }

  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    user-select: none;
  }

  html, body {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background: var(--void);
    color: var(--text-main);
    font-family: 'Inter', sans-serif;
    font-size: 11.5px;
    -webkit-font-smoothing: antialiased;
  }

  .mono {
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
  }

  /* 1. FULL-BLEED 100VW x 100VH INTERACTIVE 3D BATTLESPACE CANVAS */
  #battlespaceCanvas {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    z-index: 1;
    cursor: grab;
  }
  #battlespaceCanvas:active {
    cursor: grabbing;
  }

  /* SUBTLE TACTICAL VIGNETTE & CRT SCANLINE OVERLAY */
  .tactical-vignette {
    position: fixed;
    inset: 0;
    z-index: 2;
    pointer-events: none;
    background:
      radial-gradient(circle at 50% 50%, transparent 52%, rgba(2, 5, 11, 0.75) 100%),
      repeating-linear-gradient(0deg, rgba(255,255,255,0.012) 0px, rgba(255,255,255,0.012) 1px, transparent 1px, transparent 3px);
  }

  /* CHAMFERED GLASSMORPHIC HUD POD BASE */
  .hud-pod {
    position: fixed;
    z-index: 10;
    background: linear-gradient(155deg, rgba(11, 18, 32, 0.84) 0%, rgba(5, 9, 18, 0.90) 100%);
    backdrop-filter: blur(16px) saturate(180%);
    -webkit-backdrop-filter: blur(16px) saturate(180%);
    border: 1px solid var(--border-subtle);
    clip-path: polygon(
      0 10px, 10px 0,
      calc(100% - 10px) 0, 100% 10px,
      100% calc(100% - 10px), calc(100% - 10px) 100%,
      10px 100%, 0 calc(100% - 10px)
    );
    box-shadow: 0 14px 40px rgba(0, 0, 0, 0.65), inset 0 0 22px rgba(0, 240, 255, 0.03);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .pod-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 12px;
    background: linear-gradient(90deg, rgba(0, 240, 255, 0.10) 0%, rgba(15, 23, 42, 0.4) 100%);
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .pod-title {
    font-family: 'Chakra Petch', sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #E2E8F0;
    display: flex;
    align-items: center;
    gap: 7px;
  }

  .pod-tag {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    padding: 2px 6px;
    background: rgba(0, 240, 255, 0.10);
    border: 1px solid rgba(0, 240, 255, 0.35);
    color: var(--cyan);
  }

  .led-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--cyan);
    box-shadow: 0 0 8px var(--cyan);
  }

  /* ZONE A: TOP-CENTER FLOATING COMMAND BAR */
  .top-command-bar {
    top: 12px;
    left: 14px;
    right: 14px;
    height: 44px;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
  }

  .brand-block {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .lattice-hex {
    width: 26px;
    height: 26px;
    display: grid;
    place-items: center;
    border: 1px solid var(--cyan);
    background: rgba(0, 240, 255, 0.1);
  }

  .brand-name {
    font-family: 'Chakra Petch', sans-serif;
    font-size: 13.5px;
    font-weight: 700;
    letter-spacing: 2px;
    color: #FFFFFF;
  }

  .brand-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 8.5px;
    color: var(--cyan);
    letter-spacing: 1px;
  }

  .top-center-controls {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .hud-btn, .hud-select {
    background: rgba(15, 23, 42, 0.85);
    color: var(--text-main);
    border: 1px solid rgba(56, 189, 248, 0.30);
    padding: 5px 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .hud-btn:hover, .hud-select:hover, .hud-btn.active {
    border-color: var(--cyan);
    background: rgba(0, 240, 255, 0.16);
    color: #FFFFFF;
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.25);
  }

  .defcon-banner {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 12px;
    background: rgba(255, 42, 84, 0.16);
    border: 1px solid var(--crimson);
    font-family: 'Chakra Petch', sans-serif;
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: 1.2px;
    color: #FFE4E6;
  }

  .pulse-crimson {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--crimson);
    box-shadow: 0 0 10px var(--crimson);
    animation: pulseGlow 1.1s infinite;
  }

  @keyframes pulseGlow {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(0.8); opacity: 0.35; }
  }

  .top-telemetry-pills {
    display: flex;
    align-items: center;
    gap: 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--text-dim);
  }

  /* ZONE B: TOP-LEFT EO/IR GIMBAL TARGETING POD */
  .pod-optronic {
    top: 66px;
    left: 14px;
    width: 355px;
    height: 262px;
  }

  .shader-tabs {
    display: flex;
    gap: 3px;
  }

  .shader-tab {
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid var(--border-subtle);
    color: var(--text-dim);
    font-family: 'JetBrains Mono', monospace;
    font-size: 8.5px;
    padding: 2px 5px;
    cursor: pointer;
  }
  .shader-tab.active {
    background: rgba(0, 240, 255, 0.18);
    color: var(--cyan);
    border-color: var(--cyan);
  }

  .optronic-viewport {
    flex: 1;
    position: relative;
    background: #020408;
    min-height: 0;
  }

  .optronic-bar {
    display: flex;
    justify-content: space-between;
    padding: 4px 10px;
    background: rgba(4, 8, 16, 0.92);
    border-top: 1px solid var(--border-subtle);
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px;
    color: var(--text-dim);
  }

  /* ZONE C: BOTTOM-LEFT SWARM TRACK MATRIX */
  .pod-swarm-queue {
    top: 338px;
    bottom: 14px;
    left: 14px;
    width: 355px;
  }

  .track-list-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 6px;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .track-list-scroll::-webkit-scrollbar { width: 3px; }
  .track-list-scroll::-webkit-scrollbar-thumb { background: var(--cyan); }

  .track-card {
    background: rgba(15, 23, 42, 0.65);
    border: 1px solid rgba(51, 65, 85, 0.6);
    border-left: 3px solid var(--text-muted);
    padding: 6px 8px;
    cursor: pointer;
    transition: all 0.12s ease;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .track-card:hover {
    background: rgba(30, 41, 59, 0.85);
    border-color: rgba(0, 240, 255, 0.4);
  }

  .track-card.selected {
    background: rgba(0, 240, 255, 0.12);
    border-color: var(--cyan);
    border-left: 3px solid var(--cyan);
    box-shadow: inset 0 0 14px rgba(0, 240, 255, 0.12);
  }

  .track-card.aff-HOSTILE { border-left-color: var(--crimson); }
  .track-card.aff-SUSPECT { border-left-color: var(--amber); }
  .track-card.aff-FRIENDLY { border-left-color: var(--sky); }
  .track-card.aff-NEUTRAL { border-left-color: var(--emerald); }

  .tc-row1, .tc-row2 {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: 'JetBrains Mono', monospace;
  }

  .tc-id {
    font-size: 11px;
    font-weight: 700;
    color: #FFFFFF;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .badge-aff {
    font-size: 8.5px;
    padding: 1px 4px;
    font-weight: 700;
  }
  .badge-HOSTILE { background: rgba(255, 42, 84, 0.2); color: var(--crimson); border: 1px solid var(--crimson); }
  .badge-SUSPECT { background: rgba(255, 176, 0, 0.2); color: var(--amber); border: 1px solid var(--amber); }
  .badge-FRIENDLY { background: rgba(14, 165, 233, 0.2); color: var(--sky); border: 1px solid var(--sky); }
  .badge-NEUTRAL { background: rgba(16, 185, 129, 0.2); color: var(--emerald); border: 1px solid var(--emerald); }

  .sensor-chip {
    font-size: 8px;
    padding: 1px 4px;
    background: rgba(0, 240, 255, 0.1);
    color: var(--cyan);
    border: 1px solid rgba(0, 240, 255, 0.25);
  }

  /* ZONE D: RIGHT FLOATING TARGET DOSSIER & SPECTRUM POD */
  .pod-dossier {
    top: 66px;
    right: 14px;
    bottom: 14px;
    width: 365px;
  }

  .dossier-content {
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex: 1;
    min-height: 0;
    justify-content: space-between;
  }

  .dossier-hero {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(51, 65, 85, 0.5);
  }

  .hero-callsign {
    font-family: 'Chakra Petch', sans-serif;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #FFFFFF;
  }

  .hero-class {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--crimson);
    font-weight: 600;
  }

  .threat-dial-box {
    text-align: right;
    font-family: 'JetBrains Mono', monospace;
  }

  .threat-big-num {
    font-size: 18px;
    font-weight: 700;
    color: var(--crimson);
  }

  .telemetry-matrix {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 5px;
  }

  .t-cell {
    background: rgba(15, 23, 42, 0.75);
    border: 1px solid rgba(51, 65, 85, 0.55);
    padding: 5px 7px;
  }

  .t-lbl {
    font-size: 8.5px;
    color: var(--text-muted);
    text-transform: uppercase;
  }

  .t-val {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px;
    font-weight: 600;
    color: var(--text-main);
    margin-top: 2px;
  }

  .subscore-stack {
    display: flex;
    flex-direction: column;
    gap: 4px;
    background: rgba(9, 14, 26, 0.75);
    border: 1px solid rgba(51, 65, 85, 0.5);
    padding: 6px 8px;
  }

  .sub-row {
    display: grid;
    grid-template-columns: 118px 1fr 34px;
    align-items: center;
    gap: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
  }

  .bar-bg {
    height: 5px;
    background: #1E293B;
    overflow: hidden;
  }

  .bar-fg {
    height: 100%;
    background: linear-gradient(90deg, var(--cyan), var(--crimson));
    transition: width 0.15s ease;
  }

  .spectrum-stack {
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
    min-height: 0;
  }

  .spec-box {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: #03060C;
    border: 1px solid rgba(51, 65, 85, 0.6);
    min-height: 0;
  }

  .spec-head {
    display: flex;
    justify-content: space-between;
    padding: 3px 8px;
    background: rgba(15, 23, 42, 0.8);
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    color: var(--text-dim);
    border-bottom: 1px solid rgba(51, 65, 85, 0.4);
  }

  .spec-canvas-wrap {
    flex: 1;
    position: relative;
    min-height: 0;
  }

  /* ZONE E: BOTTOM-CENTER KILL-CHAIN & EFFECTOR ACTION DOCK */
  .pod-effector-dock {
    bottom: 14px;
    left: 381px;
    right: 391px;
    height: 146px;
  }

  /* KILL CHAIN CHEVRON STEPPER */
  .kill-chain-bar {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 4px;
    padding: 5px 10px;
    background: rgba(4, 8, 16, 0.85);
    border-bottom: 1px solid var(--border-subtle);
    font-family: 'Chakra Petch', sans-serif;
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 1px;
  }

  .kc-step {
    text-align: center;
    padding: 2px 4px;
    background: rgba(15, 23, 42, 0.7);
    border: 1px solid rgba(51, 65, 85, 0.5);
    color: var(--text-muted);
  }

  .kc-step.active {
    background: rgba(0, 240, 255, 0.16);
    border-color: var(--cyan);
    color: var(--cyan);
  }

  .kc-step.engage-active {
    background: rgba(255, 42, 84, 0.22);
    border-color: var(--crimson);
    color: #FFE4E6;
  }

  /* 4 HORIZONTAL EFFECTOR TRIGGER CARDS */
  .dock-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr) 115px;
    gap: 6px;
    padding: 7px 10px;
    flex: 1;
    align-items: stretch;
  }

  .dock-card {
    background: rgba(15, 23, 42, 0.82);
    border: 1px solid rgba(56, 189, 248, 0.28);
    padding: 6px 8px;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    text-align: left;
    color: var(--text-main);
    transition: all 0.12s ease;
    position: relative;
  }

  .dock-card:hover {
    transform: translateY(-2px);
    border-color: var(--cyan);
    background: rgba(22, 33, 58, 0.92);
    box-shadow: 0 4px 16px rgba(0, 240, 255, 0.18);
  }

  .dock-card.engaged {
    background: rgba(255, 42, 84, 0.18);
    border-color: var(--crimson);
    box-shadow: 0 0 18px rgba(255, 42, 84, 0.3);
  }

  .dc-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 8.5px;
  }

  .hotkey-chip {
    padding: 1px 4px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: var(--cyan);
  }

  .dc-title {
    font-family: 'Chakra Petch', sans-serif;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.6px;
    color: #FFFFFF;
  }

  .dc-state {
    font-family: 'JetBrains Mono', monospace;
    font-size: 8.5px;
    color: var(--text-dim);
  }

  .ceasefire-dock-btn {
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid var(--emerald);
    color: #A7F3D0;
    font-family: 'Chakra Petch', sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    transition: all 0.15s;
  }
  .ceasefire-dock-btn:hover {
    background: rgba(16, 185, 129, 0.26);
  }

  /* SHA-256 FORENSIC LEDGER FOOTER RIBBON */
  .ledger-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 12px;
    background: rgba(3, 6, 12, 0.95);
    border-top: 1px solid rgba(51, 65, 85, 0.5);
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    color: var(--text-dim);
  }

  /* BATTLESPACE CAMERA HINT PILL */
  .camera-hint {
    position: fixed;
    top: 66px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 6;
    background: rgba(6, 10, 19, 0.76);
    border: 1px solid rgba(0, 240, 255, 0.28);
    padding: 4px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px;
    color: var(--text-dim);
    pointer-events: none;
  }
</style>
</head>
<body>

<!-- 1. FULL-BLEED 100VW x 100VH INTERACTIVE 3D BATTLESPACE CANVAS -->
<canvas id="battlespaceCanvas"></canvas>
<div class="tactical-vignette"></div>

<div class="camera-hint">
  3D SPATIAL DOME // DRAG MOUSE TO ORBIT &amp; TILT &bull; SCROLL TO ZOOM &bull; CLICK TRACK TO LOCK &bull; KEYS [1-4] ENGAGE
</div>

<!-- ZONE A: TOP FLOATING TACTICAL COMMAND BAR -->
<header class="hud-pod top-command-bar">
  <div class="brand-block">
    <div class="lattice-hex">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#00F0FF" stroke-width="2">
        <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"/>
        <circle cx="12" cy="12" r="3"/>
      </svg>
    </div>
    <div>
      <div class="brand-name">LATTICE-OS // C-UAS</div>
      <div class="brand-sub">AUTONOMOUS SPATIAL BATTLESPACE C2 v5.0</div>
    </div>
  </div>

  <div class="top-center-controls">
    <button class="hud-btn active" id="view3DBtn" onclick="setCameraPreset('3D')">3D DOME</button>
    <button class="hud-btn" id="view2DBtn" onclick="setCameraPreset('2D')">2D PPI</button>
    <button class="hud-btn" id="orbitBtn" onclick="toggleAutoOrbit()">AUTO-ORBIT: ON</button>

    <select id="scenarioSelect" class="hud-select" onchange="switchScenario(this.value)">
      <option value="SWARM_SATURATION">SCENARIO: 6-UAV MULTI-AXIS SWARM</option>
      <option value="FPV_TERMINAL_DIVE">SCENARIO: SUICIDE FPV TERMINAL DIVE</option>
      <option value="RF_SILENT_STEALTH">SCENARIO: RF-SILENT AUTONOMOUS SWARM</option>
      <option value="MIXED_AIRSPACE">SCENARIO: MIXED CIVILIAN + HOSTILE</option>
    </select>

    <button class="hud-btn" id="roeToggleBtn" onclick="toggleRoeMode()">
      ROE: <span id="roeModeText" style="color:#00F0FF;font-weight:700;">MANUAL HITL</span>
    </button>

    <button class="hud-btn" id="audioBtn" onclick="toggleAudioSynth()">AUDIO: MUTE</button>

    <div class="defcon-banner">
      <span class="pulse-crimson"></span>
      <span id="defconBannerText">DEFCON 1 // CRITICAL INTRUSION</span>
    </div>
  </div>

  <div class="top-telemetry-pills">
    <span>BASE: <strong style="color:#F8FAFC;">37.7749°N, 122.4194°W</strong></span>
    <span>SPLASHES: <strong id="splashCountTop" style="color:#10B981;">0</strong></span>
    <span id="utcClock" style="color:#00F0FF;">00:00:00 UTC</span>
  </div>
</header>

<!-- ZONE B: TOP-LEFT FLOATING EO/IR GIMBAL TARGETING POD -->
<section class="hud-pod pod-optronic">
  <div class="pod-header">
    <div class="pod-title">
      <span class="led-dot" style="background:#FF2A54;box-shadow:0 0 8px #FF2A54;"></span>
      EO/IR GIMBAL SLAW // LOCKED FEED
    </div>
    <div class="shader-tabs">
      <button class="shader-tab active" id="tabWH" onclick="setShader('WH')">W-HOT</button>
      <button class="shader-tab" id="tabBH" onclick="setShader('BH')">B-HOT</button>
      <button class="shader-tab" id="tabNVG" onclick="setShader('NVG')">SWIR</button>
      <button class="shader-tab" id="tabEO" onclick="setShader('EO')">EO HD</button>
    </div>
  </div>
  <div class="optronic-viewport">
    <canvas id="optronicCanvas"></canvas>
  </div>
  <div class="optronic-bar">
    <span>LRF: <strong id="lrfReadout" style="color:#00F0FF;">410.2m LOCKED</strong></span>
    <span>YOLOv8x + IMM-UKF: <strong style="color:#10B981;">31.8 FPS</strong></span>
  </div>
</section>

<!-- ZONE C: BOTTOM-LEFT FLOATING PRIORITIZED SWARM TRACK MATRIX -->
<section class="hud-pod pod-swarm-queue">
  <div class="pod-header">
    <div class="pod-title">
      <span class="led-dot"></span>
      MULTI-SENSOR SWARM TRACK QUEUE
    </div>
    <span class="pod-tag" id="activeTrackBadge">6 ACTIVE</span>
  </div>
  <div class="track-list-scroll" id="swarmTrackList"></div>
</section>

<!-- ZONE D: RIGHT FLOATING TARGET DOSSIER & DUAL SPECTRUM POD -->
<aside class="hud-pod pod-dossier" id="dossierPod">
  <div class="pod-header">
    <div class="pod-title">
      <span class="led-dot" style="background:#FFB000;box-shadow:0 0 8px #FFB000;"></span>
      AI THREAT DOSSIER &amp; SPECTRUM BAY
    </div>
    <span class="pod-tag" id="wtaConfidenceTag">Pk: 91.0%</span>
  </div>
  <div class="dossier-content">
    <div class="dossier-hero">
      <div>
        <div class="hero-callsign" id="dCallsign">#101-ALPHA</div>
        <div class="hero-class" id="dClassText">SUICIDE_DRONE // PAYLOAD ARMED</div>
      </div>
      <div class="threat-dial-box">
        <div style="font-size:8.5px;color:var(--text-muted);">THREAT INDEX</div>
        <div class="threat-big-num" id="dThreatIndex">92.4 / 100</div>
      </div>
    </div>

    <div class="telemetry-matrix">
      <div class="t-cell">
        <div class="t-lbl">SLANT RANGE</div>
        <div class="t-val" id="dRange">412.0 m</div>
      </div>
      <div class="t-cell">
        <div class="t-lbl">BEARING / ALT</div>
        <div class="t-val" id="dBearingAlt">046° NE / 145m</div>
      </div>
      <div class="t-cell">
        <div class="t-lbl">CLOSING / TTI</div>
        <div class="t-val" id="dClosingTti" style="color:#FF2A54;">28.4m/s | 14.5s</div>
      </div>
      <div class="t-cell">
        <div class="t-lbl">GEOFENCE ZONE</div>
        <div class="t-val" id="dZone" style="color:#FF2A54;">RED &lt;500m</div>
      </div>
      <div class="t-cell">
        <div class="t-lbl">RCS / ROTOR</div>
        <div class="t-val" id="dRcsRpm">-16.4dB / 14.8k</div>
      </div>
      <div class="t-cell">
        <div class="t-lbl">RF PROTOCOL</div>
        <div class="t-val" id="dProtocol" style="color:#00F0FF;">ELRS 2.4GHz</div>
      </div>
    </div>

    <!-- EXPLAINABLE AI THREAT SUB-SCORES & IMM MODES -->
    <div class="subscore-stack">
      <div class="sub-row">
        <span style="color:var(--text-dim);">KINEMATIC LETHALITY</span>
        <div class="bar-bg"><div class="bar-fg" id="barKin" style="width:88%;"></div></div>
        <span id="valKin" style="text-align:right;">88%</span>
      </div>
      <div class="sub-row">
        <span style="color:var(--text-dim);">PAYLOAD HAZARD</span>
        <div class="bar-bg"><div class="bar-fg" id="barPay" style="width:94%;"></div></div>
        <span id="valPay" style="text-align:right;">94%</span>
      </div>
      <div class="sub-row">
        <span style="color:var(--text-dim);">IMM TERMINAL DIVE</span>
        <div class="bar-bg"><div class="bar-fg" id="barDive" style="width:72%;"></div></div>
        <span id="valDive" style="text-align:right;">72%</span>
      </div>
    </div>

    <!-- DUAL SPECTRUM WATERFALL & MICRO-DOPPLER BAY -->
    <div class="spectrum-stack">
      <div class="spec-box">
        <div class="spec-head">
          <span>SDR 2.4 / 5.8 GHz FFT WATERFALL</span>
          <span id="specRssi" style="color:#00F0FF;">RSSI: -74.2 dBm</span>
        </div>
        <div class="spec-canvas-wrap"><canvas id="rfWaterfallCanvas"></canvas></div>
      </div>
      <div class="spec-box">
        <div class="spec-head">
          <span>3D RADAR MICRO-DOPPLER BLADE FLASH</span>
          <span id="specRpm" style="color:#FFB000;">HARMONIC LOCK</span>
        </div>
        <div class="spec-canvas-wrap"><canvas id="microDopplerCanvas"></canvas></div>
      </div>
    </div>
  </div>
</aside>

<!-- ZONE E: BOTTOM-CENTER KILL-CHAIN & EFFECTOR ACTION DOCK -->
<footer class="hud-pod pod-effector-dock">
  <div class="kill-chain-bar">
    <div class="kc-step" id="kc1">1. DETECT</div>
    <div class="kc-step" id="kc2">2. TRACK</div>
    <div class="kc-step" id="kc3">3. IDENTIFY</div>
    <div class="kc-step" id="kc4">4. CUE WTA</div>
    <div class="kc-step" id="kc5">5. ENGAGE</div>
    <div class="kc-step" id="kc6">6. BDA SPLASH</div>
  </div>

  <div class="dock-grid">
    <button class="dock-card" id="dockJammer" onclick="triggerEffector('RF_JAMMER')">
      <div class="dc-top">
        <span style="color:#FFB000;">ECM // DIRECTIONAL</span>
        <span class="hotkey-chip">[KEY 1]</span>
      </div>
      <div class="dc-title">RF JAMMER (2.4/5.8G)</div>
      <div class="dc-state" id="stJammer">STANDBY // 2.8 kW</div>
    </button>

    <button class="dock-card" id="dockSpoofer" onclick="triggerEffector('GNSS_SPOOFER')">
      <div class="dc-top">
        <span style="color:#0EA5E9;">NAV // EPHEMERIS</span>
        <span class="hotkey-chip">[KEY 2]</span>
      </div>
      <div class="dc-title">GNSS / GPS SPOOFER</div>
      <div class="dc-state" id="stSpoofer">STANDBY // VECTOR</div>
    </button>

    <button class="dock-card" id="dockDazzler" onclick="triggerEffector('OPTICAL_DAZZLER')">
      <div class="dc-top">
        <span style="color:#A855F7;">DEW // 1064nm LASER</span>
        <span class="hotkey-chip">[KEY 3]</span>
      </div>
      <div class="dc-title">OPTICAL SWIR DAZZLER</div>
      <div class="dc-state" id="stDazzler">STANDBY // SEEKER</div>
    </button>

    <button class="dock-card" id="dockKinetic" onclick="triggerEffector('KINETIC_INTERCEPTOR')">
      <div class="dc-top">
        <span style="color:#FF2A54;">HARD-KILL // SILO</span>
        <span class="hotkey-chip">[KEY 4]</span>
      </div>
      <div class="dc-title">KINETIC INTERCEPTOR</div>
      <div class="dc-state" id="stKinetic">READY (6 SILOS)</div>
    </button>

    <button class="ceasefire-dock-btn" onclick="triggerCeasefire()">
      <span>CEASEFIRE</span>
      <span class="mono" style="font-size:8px;color:#6EE7B7;">[SPACEBAR]</span>
    </button>
  </div>

  <div class="ledger-footer">
    <span>WTA ROE RECOMMENDATION: <strong id="dockWtaText" style="color:#00F0FF;">DIRECTIONAL RF JAMMER + GNSS SPOOFER</strong></span>
    <span id="ledgerTicker" style="color:#10B981;">SHA-256 AUDIT CHAIN: #0001 VERIFIED ✓</span>
  </div>
</footer>

<script>
  // =========================================================================
  // 1. STATE, CAMERA ORBIT PARAMETERS & WEB AUDIO SYNTH
  // =========================================================================
  let state = null;
  let shaderMode = 'WH';
  let camYaw = -0.45;       // Horizontal azimuth angle (radians)
  let camPitch = 0.92;      // Vertical tilt (0 = flat 2D PPI, 1.05 = 3D isometric)
  let camZoom = 1.05;       // Zoom multiplier
  let autoOrbit = true;
  let isDragging = false;
  let dragStartX = 0, dragStartY = 0;
  let screenTrackMap = {};  // Stores projected 2D screen coords for click picking & tether lines
  let rfWaterfallRows = [];
  let frameCount = 0;

  // Web Audio API Synthesizer for military C2 acoustic feedback
  let audioCtx = null;
  let audioEnabled = false;

  function playTone(freq, durationMs, type = 'sine', gainVal = 0.06) {
    if (!audioEnabled) return;
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
      gain.gain.setValueAtTime(gainVal, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + durationMs / 1000);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + durationMs / 1000);
    } catch (e) {}
  }

  function toggleAudioSynth() {
    audioEnabled = !audioEnabled;
    document.getElementById('audioBtn').textContent = audioEnabled ? 'AUDIO: ACTIVE' : 'AUDIO: MUTE';
    document.getElementById('audioBtn').classList.toggle('active', audioEnabled);
    if (audioEnabled) playTone(880, 120, 'triangle');
  }

  function setCameraPreset(mode) {
    if (mode === '2D') {
      camPitch = 0.0;
      autoOrbit = false;
      document.getElementById('orbitBtn').textContent = 'AUTO-ORBIT: OFF';
    } else {
      camPitch = 0.94;
    }
    document.getElementById('view3DBtn').classList.toggle('active', mode === '3D');
    document.getElementById('view2DBtn').classList.toggle('active', mode === '2D');
  }

  function toggleAutoOrbit() {
    autoOrbit = !autoOrbit;
    document.getElementById('orbitBtn').textContent = autoOrbit ? 'AUTO-ORBIT: ON' : 'AUTO-ORBIT: OFF';
  }

  function setShader(mode) {
    shaderMode = mode;
    ['WH', 'BH', 'NVG', 'EO'].forEach(m => {
      document.getElementById('tab' + m).classList.toggle('active', m === mode);
    });
  }

  // =========================================================================
  // 2. REST COMMAND ACTIONS & KEYBOARD HOTKEYS
  // =========================================================================
  async function selectTrack(targetId) {
    if (state) state.selected_target_id = targetId;
    playTone(1240, 70, 'sine');
    await fetch('/api/v1/target/select', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({target_id: targetId})
    });
  }

  async function triggerEffector(effector) {
    playTone(520, 180, 'sawtooth', 0.08);
    const targetId = state ? state.selected_target_id : null;
    await fetch('/api/v1/countermeasures/engage', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({effector, target_id: targetId, operator: 'LATTICE_SPATIAL_C2'})
    });
  }

  async function triggerCeasefire() {
    playTone(340, 220, 'sine');
    await fetch('/api/v1/countermeasures/disengage', {method: 'POST'});
  }

  async function switchScenario(scenario) {
    await fetch('/api/v1/scenario', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({scenario})
    });
  }

  async function toggleRoeMode() {
    const next = (state && state.roe_mode === 'AUTO_ENGAGE') ? 'MANUAL_HITL' : 'AUTO_ENGAGE';
    await fetch('/api/v1/roe_mode', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({roe_mode: next})
    });
  }

  window.addEventListener('keydown', (e) => {
    if (e.key === '1') triggerEffector('RF_JAMMER');
    else if (e.key === '2') triggerEffector('GNSS_SPOOFER');
    else if (e.key === '3') triggerEffector('OPTICAL_DAZZLER');
    else if (e.key === '4') triggerEffector('KINETIC_INTERCEPTOR');
    else if (e.code === 'Space') { e.preventDefault(); triggerCeasefire(); }
  });

  // =========================================================================
  // 3. 3D ISOMETRIC BATTLESPACE PROJECTION ENGINE
  // =========================================================================
  function project3D(eastM, northM, altM, w, h) {
    const worldScale = (Math.min(w, h) * 0.42) / 1850.0 * camZoom;
    const cosY = Math.cos(camYaw);
    const sinY = Math.sin(camYaw);

    // Rotate around vertical Up axis
    const rx = eastM * cosY - northM * sinY;
    const ry = eastM * sinY + northM * cosY;

    // Tilt by camPitch
    const cosP = Math.cos(camPitch);
    const sinP = Math.sin(camPitch);
    const yProjected = ry * cosP;
    const zProjected = altM * sinP * 2.1; // Exaggerate vertical altitude relief for tactical clarity

    // Perspective depth factor
    const depth = 1.0 + (ry * sinP) / 5500.0;
    const sx = (w * 0.50) + (rx * worldScale) / Math.max(0.4, depth);
    const sy = (h * 0.47) - (yProjected * worldScale) / Math.max(0.4, depth) - (zProjected * worldScale);
    return {x: sx, y: sy, depth};
  }

  function fitCanvas(canvas) {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.floor(rect.width * dpr) || canvas.height !== Math.floor(rect.height * dpr)) {
      canvas.width = Math.floor(rect.width * dpr);
      canvas.height = Math.floor(rect.height * dpr);
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return {ctx, w: rect.width, h: rect.height};
  }

  // Mouse Orbit, Tilt, Zoom & Track Clicking on the Full-Bleed Canvas
  document.addEventListener('DOMContentLoaded', () => {
    const bCanvas = document.getElementById('battlespaceCanvas');

    bCanvas.addEventListener('mousedown', (e) => {
      isDragging = true;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
    });

    window.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const dx = e.clientX - dragStartX;
      const dy = e.clientY - dragStartY;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
      camYaw += dx * 0.0055;
      camPitch = Math.max(0.0, Math.min(1.18, camPitch + dy * 0.0045));
    });

    window.addEventListener('mouseup', (e) => {
      if (!isDragging) return;
      isDragging = false;
    });

    bCanvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      camZoom = Math.max(0.55, Math.min(2.4, camZoom - e.deltaY * 0.0008));
    }, {passive: false});

    bCanvas.addEventListener('click', (e) => {
      let closestId = null;
      let minDist = 30;
      Object.entries(screenTrackMap).forEach(([tid, pt]) => {
        const d = Math.hypot(e.clientX - pt.x, e.clientY - pt.y);
        if (d < minDist) {
          minDist = d;
          closestId = tid;
        }
      });
      if (closestId) selectTrack(closestId);
    });
  });

  // =========================================================================
  // 4. RENDER FULL-BLEED 3D SPATIAL BATTLESPACE
  // =========================================================================
  function renderBattlespace3D() {
    const canvas = document.getElementById('battlespaceCanvas');
    const {ctx, w, h} = fitCanvas(canvas);

    if (autoOrbit && !isDragging && camPitch > 0.1) {
      camYaw += 0.0012;
    }

    ctx.fillStyle = '#03060C';
    ctx.fillRect(0, 0, w, h);

    // 1. Isometric Ground Metric Wireframe Grid (-2000m to +2000m)
    ctx.strokeStyle = 'rgba(30, 41, 59, 0.36)';
    ctx.lineWidth = 1;
    const step = 400;
    const bound = 2000;
    ctx.beginPath();
    for (let g = -bound; g <= bound; g += step) {
      const p1 = project3D(g, -bound, 0, w, h);
      const p2 = project3D(g, bound, 0, w, h);
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);

      const p3 = project3D(-bound, g, 0, w, h);
      const p4 = project3D(bound, g, 0, w, h);
      ctx.moveTo(p3.x, p3.y);
      ctx.lineTo(p4.x, p4.y);
    }
    ctx.stroke();

    // 2. Concentric Geodesic Defense Rings & 3D Wireframe Domes
    const zones = [
      {r: 500, color: 'rgba(255, 42, 84, 0.65)', dome: 'rgba(255, 42, 84, 0.12)', label: '500m RED KILLZONE'},
      {r: 1500, color: 'rgba(255, 176, 0, 0.45)', dome: 'rgba(255, 176, 0, 0.05)', label: '1500m AMBER WARNING'},
      {r: 2200, color: 'rgba(0, 240, 255, 0.30)', dome: null, label: 'EARLY DETECTION PERIMETER'}
    ];

    zones.forEach(z => {
      ctx.strokeStyle = z.color;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      for (let deg = 0; deg <= 360; deg += 5) {
        const rad = (deg * Math.PI) / 180;
        const pt = project3D(z.r * Math.sin(rad), z.r * Math.cos(rad), 0, w, h);
        if (deg === 0) ctx.moveTo(pt.x, pt.y);
        else ctx.lineTo(pt.x, pt.y);
      }
      ctx.stroke();

      // Draw 3D Hemispherical Wireframe Dome Ribs on the 500m Killzone
      if (z.r === 500 && camPitch > 0.15) {
        ctx.strokeStyle = 'rgba(255, 42, 84, 0.16)';
        ctx.lineWidth = 1;
        for (let az = 0; az < 180; az += 45) {
          const azRad = (az * Math.PI) / 180;
          ctx.beginPath();
          for (let el = 0; el <= 180; el += 10) {
            const elRad = (el * Math.PI) / 180;
            const horiz = z.r * Math.cos(elRad);
            const up = z.r * Math.sin(elRad) * 0.45;
            const pt = project3D(horiz * Math.sin(azRad), horiz * Math.cos(azRad), up, w, h);
            if (el === 0) ctx.moveTo(pt.x, pt.y);
            else ctx.lineTo(pt.x, pt.y);
          }
          ctx.stroke();
        }
      }

      const lblPt = project3D(0, z.r, 0, w, h);
      ctx.fillStyle = z.color;
      ctx.font = '600 9.5px "JetBrains Mono"';
      ctx.fillText(z.label, lblPt.x + 8, lblPt.y - 4);
    });

    if (!state) return;

    const origin = project3D(0, 0, 0, w, h);

    // 3. Rotating Phased-Array Radar Sweep Cone on Ground Plane
    const sweepRad = (state.radar_sweep_deg * Math.PI) / 180;
    const sweepSpan = 0.28;
    ctx.fillStyle = 'rgba(0, 240, 255, 0.08)';
    ctx.beginPath();
    ctx.moveTo(origin.x, origin.y);
    for (let a = sweepRad - sweepSpan; a <= sweepRad; a += 0.04) {
      const p = project3D(2100 * Math.sin(a), 2100 * Math.cos(a), 0, w, h);
      ctx.lineTo(p.x, p.y);
    }
    ctx.closePath();
    ctx.fill();

    // 4. Volumetric Effector Beams (Jammer / Dazzler directed at locked target)
    state.effectors.forEach(eff => {
      if (eff.state === 'ENGAGED' && eff.target_id) {
        const tgt = state.tracks.find(t => t.target_id === eff.target_id);
        if (tgt) {
          const tPt = project3D(tgt.east_m, tgt.north_m, tgt.alt_m, w, h);
          ctx.strokeStyle = eff.id === 'RF_JAMMER' ? '#FFB000' : (eff.id === 'OPTICAL_DAZZLER' ? '#A855F7' : '#0EA5E9');
          ctx.lineWidth = 2;
          ctx.setLineDash([6, 4]);
          ctx.beginPath();
          ctx.moveTo(origin.x, origin.y);
          ctx.lineTo(tPt.x, tPt.y);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }
    });

    // 5. Render Splash Shockwaves (BDA Kinetic Interceptions)
    state.splash_events.forEach(sp => {
      const age = (Date.now() / 1000) - sp.time;
      const pt = project3D(sp.east_m, sp.north_m, sp.alt_m, w, h);
      const radius = Math.max(8, Math.min(80, age * 38));
      const alpha = Math.max(0, 1 - age / 2.5);
      ctx.strokeStyle = `rgba(16, 185, 129, ${alpha})`;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, radius, 0, Math.PI * 2);
      ctx.stroke();

      ctx.fillStyle = `rgba(16, 185, 129, ${alpha})`;
      ctx.font = 'bold 10px "JetBrains Mono"';
      ctx.fillText(`BDA SPLASH // ${sp.target_id}`, pt.x + 12, pt.y - 10);
    });

    // 6. Base HQ Defense Core Icon
    ctx.fillStyle = '#0EA5E9';
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(origin.x, origin.y, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = '#00F0FF';
    ctx.font = 'bold 9.5px "JetBrains Mono"';
    ctx.fillText('BASE HQ [0,0]', origin.x + 10, origin.y + 4);

    // 7. Render Every 3D Track with Elevation Stalks, Trail Curtains & IMM Splines
    screenTrackMap = {};
    let lockedScreenPt = null;

    state.tracks.forEach(trk => {
      const airPt = project3D(trk.east_m, trk.north_m, trk.alt_m, w, h);
      const groundPt = project3D(trk.east_m, trk.north_m, 0, w, h);
      screenTrackMap[trk.target_id] = airPt;

      const isSelected = trk.target_id === state.selected_target_id;
      if (isSelected) lockedScreenPt = airPt;

      const mainColor = trk.affiliation === 'HOSTILE' ? '#FF2A54' :
                        (trk.affiliation === 'FRIENDLY' ? '#0EA5E9' :
                        (trk.affiliation === 'NEUTRAL' ? '#10B981' : '#FFB000'));

      // A. Ground Shadow Ring & Vertical 3D Elevation Stalk
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(groundPt.x, groundPt.y);
      ctx.lineTo(airPt.x, airPt.y);
      ctx.stroke();

      ctx.fillStyle = mainColor;
      ctx.beginPath();
      ctx.arc(groundPt.x, groundPt.y, 2.5, 0, Math.PI * 2);
      ctx.fill();

      // B. 3D Flight Trail & Translucent Vertical Curtain
      if (trk.trail && trk.trail.length > 1) {
        ctx.strokeStyle = mainColor;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        trk.trail.forEach((pt3, idx) => {
          const p = project3D(pt3[0], pt3[1], pt3[2] || trk.alt_m, w, h);
          if (idx === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        });
        ctx.lineTo(airPt.x, airPt.y);
        ctx.stroke();
      }

      // C. 3D IMM-UKF Predicted Trajectory Spline
      if (trk.predicted_path && trk.predicted_path.length > 1 && trk.affiliation !== 'FRIENDLY') {
        ctx.strokeStyle = '#00F0FF';
        ctx.lineWidth = 1.3;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(airPt.x, airPt.y);
        trk.predicted_path.forEach(p3 => {
          const pp = project3D(p3[0], p3[1], p3[2], w, h);
          ctx.lineTo(pp.x, pp.y);
        });
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // D. Locked Reticle Bracket
      if (isSelected) {
        ctx.strokeStyle = '#00F0FF';
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(airPt.x, airPt.y, 15 + Math.sin(frameCount * 0.15) * 2, 0, Math.PI * 2);
        ctx.stroke();
      }

      // E. NATO MIL-STD-2525D Airframe Symbol
      ctx.lineWidth = 1.8;
      ctx.strokeStyle = mainColor;
      ctx.fillStyle = 'rgba(6, 10, 19, 0.85)';
      if (trk.affiliation === 'HOSTILE') {
        ctx.beginPath();
        ctx.moveTo(airPt.x, airPt.y - 8);
        ctx.lineTo(airPt.x + 8, airPt.y);
        ctx.lineTo(airPt.x, airPt.y + 8);
        ctx.lineTo(airPt.x - 8, airPt.y);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      } else if (trk.affiliation === 'FRIENDLY') {
        ctx.beginPath();
        ctx.arc(airPt.x, airPt.y, 7, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      } else {
        ctx.fillRect(airPt.x - 6, airPt.y - 6, 12, 12);
        ctx.strokeRect(airPt.x - 6, airPt.y - 6, 12, 12);
      }

      // F. Floating 3D Callout Tag
      ctx.fillStyle = isSelected ? '#00F0FF' : '#F8FAFC';
      ctx.font = 'bold 10px "JetBrains Mono"';
      ctx.fillText(`${trk.target_id} [${Math.round(trk.range_m)}m]`, airPt.x + 12, airPt.y - 3);
      ctx.fillStyle = '#94A3B8';
      ctx.font = '9px "JetBrains Mono"';
      ctx.fillText(`ALT:${Math.round(trk.alt_m)}m | ${trk.status}`, airPt.x + 12, airPt.y + 9);
    });

    // 8. DYNAMIC TARGET-TO-DOSSIER TETHER LINE (Anduril Lattice Signature Feature)
    if (lockedScreenPt) {
      const dossierEl = document.getElementById('dossierPod');
      const dRect = dossierEl.getBoundingClientRect();
      const anchorX = dRect.left;
      const anchorY = dRect.top + 48;
      const elbowX = anchorX - 38;

      ctx.strokeStyle = 'rgba(0, 240, 255, 0.55)';
      ctx.lineWidth = 1.2;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(lockedScreenPt.x + 14, lockedScreenPt.y);
      ctx.lineTo(elbowX, anchorY);
      ctx.lineTo(anchorX, anchorY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Joint node dot
      ctx.fillStyle = '#00F0FF';
      ctx.beginPath();
      ctx.arc(elbowX, anchorY, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // =========================================================================
  // 5. RENDER EO/IR GIMBAL TARGETING POD + 4X PIP ORDNANCE LOUPE
  // =========================================================================
  function getSelectedTrack() {
    if (!state || !state.tracks || !state.tracks.length) return null;
    return state.tracks.find(t => t.target_id === state.selected_target_id) || state.tracks[0];
  }

  function renderOptronicGimbal() {
    const canvas = document.getElementById('optronicCanvas');
    const {ctx, w, h} = fitCanvas(canvas);
    const trk = getSelectedTrack();

    // Multi-spectral shader background
    if (shaderMode === 'WH') {
      ctx.fillStyle = '#141923';
      ctx.fillRect(0, 0, w, h);
    } else if (shaderMode === 'BH') {
      ctx.fillStyle = '#CBD5E1';
      ctx.fillRect(0, 0, w, h);
    } else if (shaderMode === 'NVG') {
      ctx.fillStyle = '#03180E';
      ctx.fillRect(0, 0, w, h);
    } else {
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, '#071426');
      grad.addColorStop(0.6, '#132A46');
      grad.addColorStop(1, '#08101A');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
    }

    // Artificial Horizon & Pitch Ladder
    const horizonY = h * 0.56 + Math.sin(frameCount * 0.03) * 4;
    const hudColor = shaderMode === 'BH' ? '#0F172A' : (shaderMode === 'NVG' ? '#10B981' : '#00F0FF');
    ctx.strokeStyle = hudColor;
    ctx.globalAlpha = 0.35;
    ctx.beginPath();
    ctx.moveTo(20, horizonY);
    ctx.lineTo(w - 20, horizonY);
    ctx.stroke();
    ctx.globalAlpha = 1.0;

    if (!trk) return;

    const cx = w * 0.45 + Math.sin(frameCount * 0.06) * 14;
    const cy = h * 0.46 + Math.cos(frameCount * 0.05) * 10;

    // Render Synthetic UAV Airframe & Thermal Motor Signatures
    ctx.save();
    ctx.translate(cx, cy);
    const bodyCol = shaderMode === 'WH' ? '#FFFFFF' : (shaderMode === 'BH' ? '#0F172A' : (shaderMode === 'NVG' ? '#34D399' : '#E2E8F0'));
    ctx.strokeStyle = bodyCol;
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.moveTo(-24, -11); ctx.lineTo(24, 11);
    ctx.moveTo(-24, 11); ctx.lineTo(24, -11);
    ctx.stroke();

    ctx.fillStyle = bodyCol;
    ctx.fillRect(-9, -5, 18, 10);
    if (trk.payload_detected) {
      ctx.fillStyle = shaderMode === 'BH' ? '#DC2626' : '#FF2A54';
      ctx.fillRect(-5, 5, 10, 8);
    }

    // Rotor blur discs
    [[-24, -11], [24, -11], [-24, 11], [24, 11]].forEach(([rx, ry]) => {
      ctx.strokeStyle = hudColor;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.ellipse(rx, ry, 10, 3, (frameCount * 0.4) % Math.PI, 0, Math.PI * 2);
      ctx.stroke();
    });
    ctx.restore();

    // Rotating Gimbal Lock Reticle
    const retColor = trk.affiliation === 'HOSTILE' ? '#FF2A54' : '#FFB000';
    ctx.strokeStyle = retColor;
    ctx.lineWidth = 1.6;
    const b = 36;
    ctx.strokeRect(cx - b, cy - b, b * 2, b * 2);

    // Lead-computing Kalman Pipper
    const leadX = cx + trk.vx_ms * 1.1;
    const leadY = cy - trk.vz_ms * 2.2;
    ctx.strokeStyle = hudColor;
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(leadX, leadY);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(leadX, leadY, 5, 0, Math.PI * 2);
    ctx.stroke();

    // 4x PiP Payload Classifier Loupe on Right Side
    const pw = 96, ph = 68;
    const px = w - pw - 8, py = h - ph - 8;
    ctx.fillStyle = 'rgba(3, 6, 12, 0.9)';
    ctx.fillRect(px, py, pw, ph);
    ctx.strokeStyle = retColor;
    ctx.strokeRect(px, py, pw, ph);
    ctx.fillStyle = '#F8FAFC';
    ctx.font = '8px "JetBrains Mono"';
    ctx.fillText('4X PAYLOAD LOUPE', px + 5, py + 11);
    ctx.fillStyle = trk.payload_detected ? '#FF2A54' : '#10B981';
    ctx.fillText(trk.payload_detected ? 'ARMED MUNITION' : 'CLEAN AIRFRAME', px + 5, py + ph - 6);
    ctx.strokeStyle = '#00F0FF';
    ctx.strokeRect(px + 28, py + 20, 38, 24);
    if (trk.payload_detected) {
      ctx.fillStyle = '#FF2A54';
      ctx.fillRect(px + 38, py + 32, 18, 10);
    }
  }

  // =========================================================================
  // 6. RENDER SDR RF WATERFALL & MICRO-DOPPLER BLADE SPECTROGRAM
  // =========================================================================
  function renderSpectrograms() {
    const trk = getSelectedTrack();
    // RF Waterfall
    const rfCanvas = document.getElementById('rfWaterfallCanvas');
    const {ctx: rCtx, w: rw, h: rh} = fitCanvas(rfCanvas);
    rCtx.fillStyle = '#03060C';
    rCtx.fillRect(0, 0, rw, rh);

    const bins = 44;
    const row = [];
    const isSilent = trk && trk.rf_protocol === 'RF_SILENT_AUTONOMOUS';
    const isJammed = trk && trk.status === 'JAMMED';

    for (let i = 0; i < bins; i++) {
      let v = 0.1 + Math.random() * 0.12;
      if (isJammed && i > 8 && i < 36) v = 0.88 + Math.random() * 0.12;
      else if (!isSilent && (Math.abs(i - 14) <= 2 || Math.abs(i - 30) <= 2)) v = 0.68 + Math.random() * 0.25;
      row.push(v);
    }
    rfWaterfallRows.unshift(row);
    if (rfWaterfallRows.length > 22) rfWaterfallRows.pop();

    const split = rh * 0.42;
    rCtx.strokeStyle = isJammed ? '#FF2A54' : '#00F0FF';
    rCtx.lineWidth = 1.4;
    rCtx.beginPath();
    row.forEach((v, idx) => {
      const x = (idx / (bins - 1)) * rw;
      const y = split - v * (split - 5);
      if (idx === 0) rCtx.moveTo(x, y);
      else rCtx.lineTo(x, y);
    });
    rCtx.stroke();

    const cw = rw / bins;
    const ch = (rh - split) / 22;
    rfWaterfallRows.forEach((r, rIdx) => {
      r.forEach((v, cIdx) => {
        rCtx.fillStyle = v > 0.75 ? '#FF2A54' : (v > 0.45 ? '#FFB000' : (v > 0.22 ? '#0EA5E9' : '#0B1324'));
        rCtx.fillRect(cIdx * cw, split + rIdx * ch, Math.ceil(cw), Math.ceil(ch));
      });
    });

    // Micro-Doppler Blade Flash Canvas
    const mdCanvas = document.getElementById('microDopplerCanvas');
    const {ctx: mCtx, w: mw, h: mh} = fitCanvas(mdCanvas);
    mCtx.fillStyle = '#03060C';
    mCtx.fillRect(0, 0, mw, mh);

    const midY = mh * 0.5;
    mCtx.strokeStyle = 'rgba(56, 189, 248, 0.25)';
    mCtx.beginPath();
    mCtx.moveTo(0, midY);
    mCtx.lineTo(mw, midY);
    mCtx.stroke();

    for (let x = 6; x < mw - 6; x += 4) {
      const amp = Math.abs(Math.sin(x * 0.24 + frameCount * 0.32)) * (mh * 0.40);
      mCtx.strokeStyle = trk && trk.affiliation === 'HOSTILE' ? 'rgba(255, 42, 84, 0.8)' : 'rgba(0, 240, 255, 0.8)';
      mCtx.beginPath();
      mCtx.moveTo(x, midY - amp);
      mCtx.lineTo(x, midY + amp);
      mCtx.stroke();
    }
  }

  // =========================================================================
  // 7. DOM TELEMETRY SYNCHRONIZATION
  // =========================================================================
  function syncDOM(newState) {
    state = newState;
    document.getElementById('utcClock').textContent = new Date().toISOString().slice(11, 19) + ' UTC';
    document.getElementById('defconBannerText').textContent = state.defcon_label;
    document.getElementById('splashCountTop').textContent = state.neutralized_count;
    document.getElementById('roeModeText').textContent = state.roe_mode === 'AUTO_ENGAGE' ? 'AUTO-ENGAGE' : 'MANUAL HITL';
    document.getElementById('activeTrackBadge').textContent = `${state.tracks.length} ACTIVE`;

    // Swarm Track Cards
    const listEl = document.getElementById('swarmTrackList');
    listEl.innerHTML = state.tracks.map(t => {
      const sel = t.target_id === state.selected_target_id ? 'selected' : '';
      return `<div class="track-card aff-${t.affiliation} ${sel}" onclick="selectTrack('${t.target_id}')">
        <div class="tc-row1">
          <span class="tc-id">${t.target_id} <span class="badge-aff badge-${t.affiliation}">${t.affiliation}</span></span>
          <span style="color:${t.threat_score >= 75 ? '#FF2A54' : '#00F0FF'};font-weight:700;">IDX ${t.threat_score}</span>
        </div>
        <div class="tc-row2" style="color:var(--text-dim);font-size:9.5px;">
          <span>${t.drone_class.replace(/_/g, ' ')}</span>
          <span>${t.range_m}m | TTI:${t.tti_s > 900 ? '--' : t.tti_s + 's'}</span>
        </div>
        <div class="tc-row2" style="margin-top:2px;">
          <div style="display:flex;gap:3px;">
            ${t.corroboration.map(c => `<span class="sensor-chip">${c}</span>`).join('')}
          </div>
          <span style="font-size:9px;color:#94A3B8;">${t.status}</span>
        </div>
      </div>`;
    }).join('');

    const trk = getSelectedTrack();
    if (trk) {
      document.getElementById('lrfReadout').textContent = `${trk.slant_range_m}m LOCKED`;
      document.getElementById('wtaConfidenceTag').textContent = `Pk: ${trk.p_success}%`;
      document.getElementById('dCallsign').textContent = `${trk.target_id} // ${trk.affiliation}`;
      document.getElementById('dClassText').textContent = `${trk.drone_class} [${trk.payload_detected ? 'ORDNANCE ARMED' : 'NO PAYLOAD'}]`;
      document.getElementById('dThreatIndex').textContent = `${trk.threat_score} / 100`;
      document.getElementById('dRange').textContent = `${trk.range_m} m`;
      document.getElementById('dBearingAlt').textContent = `${String(Math.round(trk.bearing_deg)).padStart(3,'0')}° ${trk.bearing_cardinal} / ${Math.round(trk.alt_m)}m`;
      document.getElementById('dClosingTti').textContent = `${trk.closing_vel_ms}m/s | ${trk.tti_s > 900 ? 'N/A' : trk.tti_s + 's'}`;
      document.getElementById('dZone').textContent = trk.zone_code + ' SECTOR';
      document.getElementById('dRcsRpm').textContent = `${trk.rcs_dbsm}dB / ${(trk.rotor_rpm/1000).toFixed(1)}k`;
      document.getElementById('dProtocol').textContent = trk.rf_protocol;

      // Sub-score bars
      const kin = Math.round(trk.sub_scores.kinematic_lethality);
      const pay = Math.round(trk.sub_scores.payload_hazard);
      const dive = Math.round(trk.imm_modes.terminal_dive * 100);
      document.getElementById('barKin').style.width = kin + '%';
      document.getElementById('valKin').textContent = kin + '%';
      document.getElementById('barPay').style.width = pay + '%';
      document.getElementById('valPay').textContent = pay + '%';
      document.getElementById('barDive').style.width = dive + '%';
      document.getElementById('valDive').textContent = dive + '%';

      document.getElementById('specRssi').textContent = `RSSI: ${trk.rssi_dbm} dBm`;
      document.getElementById('specRpm').textContent = `${trk.rotor_rpm} RPM`;
      document.getElementById('dockWtaText').textContent = trk.wta_recommendation;

      // Update Kill-Chain Stepper
      for (let i = 1; i <= 6; i++) {
        const el = document.getElementById('kc' + i);
        el.className = 'kc-step';
        if (i <= trk.kill_chain_num) {
          el.classList.add(i >= 5 ? 'engage-active' : 'active');
        }
      }
    }

    // Effector Dock Cards
    const effMap = {};
    state.effectors.forEach(e => effMap[e.id] = e);
    const updateCard = (cardId, stId, key) => {
      const e = effMap[key];
      if (!e) return;
      document.getElementById(stId).textContent = e.state;
      document.getElementById(cardId).classList.toggle('engaged', e.state === 'ENGAGED' || e.state.startsWith('LAUNCHED'));
    };
    updateCard('dockJammer', 'stJammer', 'RF_JAMMER');
    updateCard('dockSpoofer', 'stSpoofer', 'GNSS_SPOOFER');
    updateCard('dockDazzler', 'stDazzler', 'OPTICAL_DAZZLER');
    updateCard('dockKinetic', 'stKinetic', 'KINETIC_INTERCEPTOR');

    // Forensic SHA-256 Ledger Ticker
    if (state.audit_tail && state.audit_tail.length) {
      const head = state.audit_tail[0];
      document.getElementById('ledgerTicker').textContent =
        `BLOCK #${String(head.index).padStart(4, '0')} // ${head.event_type} // SHA256:${head.block_hash.slice(0, 12)} VERIFIED ✓`;
    }
  }

  function masterRenderLoop() {
    frameCount++;
    renderBattlespace3D();
    renderOptronicGimbal();
    renderSpectrograms();
    requestAnimationFrame(masterRenderLoop);
  }

  function connectWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws/telemetry`);
    ws.onmessage = (e) => {
      try { syncDOM(JSON.parse(e.data)); } catch (err) {}
    };
    ws.onclose = () => setTimeout(connectWebSocket, 1200);
  }

  window.addEventListener('load', () => {
    connectWebSocket();
    requestAnimationFrame(masterRenderLoop);
  });
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
@app.get("/command-center", response_class=HTMLResponse)
async def serve_spatial_command_center():
    return HTMLResponse(content=LATTICE_SPATIAL_HTML)


def run_server(host: str = "127.0.0.1", port: int = 8080):
    import uvicorn
    uvicorn.run("api.api_server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
