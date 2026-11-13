"""
FastAPI REST & WebSocket Command and Control (C2) Server with Lattice/Gotham Command Center (v4.0-Lattice).
Provides a 100vh Zero-Scroll Tactical Military Web Command Center at http://127.0.0.1:8080/
along with multi-target WTA endpoints, cryptographic audit verification, and WebSocket streaming telemetry.
"""

from typing import Dict, List, Optional, Any
import time
import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from utils.logger import get_logger
from control_unit.threat_manager import ThreatManager
from control_unit.neutralization import CountermeasureController, CountermeasureType
from control_unit.audit_logger import ForensicAuditLogger
from sensors.rf_sensor import RFSensorSimulator
from sensors.radar_sensor import RadarSensorSimulator

logger = get_logger("CUAS.API")

app = FastAPI(
    title="LATTICE-CUAS Tactical C2 System",
    version="4.0-Lattice",
    description="Autonomous Multi-Target Counter-Swarm Air Defense & Command Architecture"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

threat_mgr = ThreatManager()
countermeasure_ctrl = CountermeasureController(operator_name="COMMANDER_C2")
audit_logger = ForensicAuditLogger()
rf_sensor = RFSensorSimulator()
radar_sensor = RadarSensorSimulator()

class CountermeasureRequest(BaseModel):
    target_id: int
    measure_type: str
    operator: Optional[str] = "COMMANDER_C2"
    duration_sec: Optional[float] = 12.0

class ScenarioRequest(BaseModel):
    scenario: str # "SWARM_SATURATION", "FPV_TERMINAL_DIVE", "RF_SILENT_STEALTH", "MIXED_AIRSPACE"

class AutomationModeRequest(BaseModel):
    mode: str     # "MANUAL_HITL" or "AUTO_ENGAGE_ROE"


LATTICE_GOTHAM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LATTICE-CUAS // AUTONOMOUS AIR DEFENSE C2</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-void: #06090F;
      --bg-panel: #0B101B;
      --bg-card: #111827;
      --border-hairline: #1E293B;
      --border-focus: #334155;
      --hostile-crimson: #F43F5E;
      --suspect-amber: #F59E0B;
      --friendly-cyan: #0EA5E9;
      --nominal-emerald: #10B981;
      --text-primary: #F8FAFC;
      --text-secondary: #94A3B8;
      --text-muted: #64748B;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-void);
      color: var(--text-primary);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      user-select: none;
    }
    .mono {
      font-family: 'JetBrains Mono', monospace;
      font-variant-numeric: tabular-nums;
    }

    /* TOP COMMAND RIBBON */
    header {
      height: 48px;
      background: var(--bg-panel);
      border-bottom: 1px solid var(--border-hairline);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      flex-shrink: 0;
    }
    .brand-group {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-mark {
      width: 22px;
      height: 22px;
      border: 2px solid var(--friendly-cyan);
      transform: rotate(45deg);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .brand-inner {
      width: 8px;
      height: 8px;
      background: var(--friendly-cyan);
    }
    .brand-text {
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 1.5px;
      color: var(--text-primary);
    }
    .ribbon-controls {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    select, button {
      font-family: 'Inter', sans-serif;
    }
    .scenario-select {
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      color: var(--text-secondary);
      font-size: 11px;
      padding: 4px 8px;
      border-radius: 4px;
      outline: none;
      cursor: pointer;
    }
    .defcon-pill {
      font-size: 11px;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 3px;
      border: 1px solid var(--hostile-crimson);
      color: var(--hostile-crimson);
      background: rgba(244, 63, 94, 0.12);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .pulse-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 6px currentColor;
    }
    .pill {
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 3px;
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      color: var(--text-secondary);
    }
    .pill strong { color: var(--text-primary); }

    /* 5-ZONE TACTICAL GRID */
    .tactical-grid {
      display: grid;
      grid-template-columns: 32% 40% 28%;
      height: calc(100vh - 48px);
      overflow: hidden;
    }
    .col {
      border-right: 1px solid var(--border-hairline);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .col:last-child { border-right: none; }

    .panel-header {
      height: 32px;
      background: rgba(11, 16, 27, 0.95);
      border-bottom: 1px solid var(--border-hairline);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 12px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.8px;
      color: var(--text-secondary);
      flex-shrink: 0;
    }
    .sensor-toggles {
      display: flex;
      gap: 4px;
    }
    .btn-toggle {
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      color: var(--text-muted);
      font-size: 10px;
      font-weight: 600;
      padding: 2px 6px;
      border-radius: 2px;
      cursor: pointer;
    }
    .btn-toggle.active {
      color: var(--friendly-cyan);
      border-color: var(--friendly-cyan);
      background: rgba(14, 165, 233, 0.12);
    }

    /* LEFT COLUMN */
    .optronic-viewport {
      height: 55%;
      position: relative;
      background: #000;
      overflow: hidden;
      border-bottom: 1px solid var(--border-hairline);
    }
    canvas.optronic-canvas {
      width: 100%;
      height: 100%;
      display: block;
    }
    .pip-zoom {
      position: absolute;
      top: 10px;
      right: 10px;
      width: 110px;
      height: 110px;
      border: 1px solid var(--friendly-cyan);
      background: rgba(11, 16, 27, 0.9);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.6);
      display: flex;
      flex-direction: column;
    }
    .pip-header {
      font-size: 9px;
      padding: 2px 4px;
      background: rgba(14, 165, 233, 0.2);
      color: var(--friendly-cyan);
      font-weight: 700;
    }
    canvas.pip-canvas {
      width: 100%;
      height: 100%;
      display: block;
    }

    .track-table-container {
      height: 45%;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .track-table-body {
      flex: 1;
      overflow-y: auto;
    }
    table.track-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
    }
    table.track-table th {
      position: sticky;
      top: 0;
      background: var(--bg-card);
      padding: 6px 8px;
      text-align: left;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border-hairline);
      font-size: 10px;
    }
    table.track-table td {
      padding: 6px 8px;
      border-bottom: 1px solid var(--border-hairline);
      color: var(--text-secondary);
      cursor: pointer;
    }
    table.track-table tr:hover td {
      background: rgba(30, 41, 59, 0.5);
      color: var(--text-primary);
    }
    table.track-table tr.selected td {
      background: rgba(14, 165, 233, 0.12);
      color: var(--friendly-cyan);
    }
    .badge {
      display: inline-block;
      padding: 1px 4px;
      border-radius: 2px;
      font-size: 9px;
      font-weight: 700;
    }
    .badge-crimson { background: rgba(244, 63, 94, 0.2); color: var(--hostile-crimson); border: 1px solid var(--hostile-crimson); }
    .badge-amber { background: rgba(245, 158, 11, 0.2); color: var(--suspect-amber); border: 1px solid var(--suspect-amber); }
    .badge-cyan { background: rgba(14, 165, 233, 0.2); color: var(--friendly-cyan); border: 1px solid var(--friendly-cyan); }
    .badge-emerald { background: rgba(16, 185, 129, 0.2); color: var(--nominal-emerald); border: 1px solid var(--nominal-emerald); }

    /* CENTER COLUMN */
    .battlespace-viewport {
      height: 68%;
      position: relative;
      background: #04070D;
      border-bottom: 1px solid var(--border-hairline);
    }
    canvas.battlespace-canvas {
      width: 100%;
      height: 100%;
      display: block;
    }

    .diagnostics-panel {
      height: 32%;
      display: grid;
      grid-template-columns: 50% 50%;
      border-top: 1px solid var(--border-hairline);
    }
    .diag-subpanel {
      padding: 8px;
      border-right: 1px solid var(--border-hairline);
      display: flex;
      flex-direction: column;
    }
    .diag-subpanel:last-child { border-right: none; }
    .sub-title {
      font-size: 10px;
      font-weight: 700;
      color: var(--text-muted);
      margin-bottom: 4px;
      letter-spacing: 0.5px;
    }
    canvas.diag-canvas {
      width: 100%;
      flex: 1;
      background: #020408;
      border: 1px solid var(--border-hairline);
    }

    /* RIGHT COLUMN */
    .dossier-panel {
      height: 40%;
      padding: 12px;
      border-bottom: 1px solid var(--border-hairline);
      overflow-y: auto;
    }
    .dossier-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 8px;
    }
    .dossier-field {
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      padding: 6px 8px;
      border-radius: 3px;
    }
    .field-lbl { font-size: 9px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 2px; }
    .field-val { font-size: 12px; font-weight: 700; color: var(--text-primary); }

    .effector-matrix-panel {
      height: 40%;
      padding: 10px;
      border-bottom: 1px solid var(--border-hairline);
      display: flex;
      flex-direction: column;
      gap: 6px;
      overflow-y: auto;
    }
    .effector-card {
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      padding: 8px 10px;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      transition: border-color 0.15s, background 0.15s;
    }
    .effector-card:hover {
      border-color: var(--border-focus);
      background: #162032;
    }
    .effector-card.active-jam {
      border-color: var(--suspect-amber);
      background: rgba(245, 158, 11, 0.12);
    }
    .effector-card.active-spoof {
      border-color: var(--friendly-cyan);
      background: rgba(14, 165, 233, 0.12);
    }
    .effector-card.active-kin {
      border-color: var(--hostile-crimson);
      background: rgba(244, 63, 94, 0.14);
    }
    .effector-left {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .effector-icon {
      width: 24px;
      height: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .effector-title {
      font-size: 11px;
      font-weight: 700;
      color: var(--text-primary);
    }
    .effector-desc {
      font-size: 9px;
      color: var(--text-muted);
    }
    .effector-status {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 2px;
      border: 1px solid var(--border-hairline);
    }

    .ceasefire-btn {
      width: 100%;
      background: rgba(244, 63, 94, 0.15);
      border: 1px solid var(--hostile-crimson);
      color: var(--hostile-crimson);
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 1px;
      padding: 6px;
      border-radius: 3px;
      cursor: pointer;
      margin-top: 4px;
    }
    .ceasefire-btn:hover { background: rgba(244, 63, 94, 0.3); }

    .audit-terminal {
      height: 20%;
      background: #020408;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .audit-log-body {
      flex: 1;
      overflow-y: auto;
      font-size: 10px;
      line-height: 1.4;
      color: var(--text-muted);
    }
    .audit-line { margin-bottom: 3px; }
    .audit-hash { color: var(--friendly-cyan); }
  </style>
</head>
<body>

  <!-- TOP COMMAND RIBBON -->
  <header>
    <div class="brand-group">
      <div class="brand-mark"><div class="brand-inner"></div></div>
      <div class="brand-text">LATTICE-CUAS // AUTONOMOUS AIR DEFENSE C2</div>
      <select id="scenario-selector" class="scenario-select" onchange="switchScenario(this.value)">
        <option value="SWARM_SATURATION">SCENARIO: MULTI-AXIS SWARM SATURATION</option>
        <option value="FPV_TERMINAL_DIVE">SCENARIO: FPV TERMINAL SUICIDE DIVE</option>
        <option value="RF_SILENT_STEALTH">SCENARIO: RF-SILENT AUTONOMOUS LOITERING</option>
        <option value="MIXED_AIRSPACE">SCENARIO: CIVILIAN + HOSTILE MIXED AIRSPACE</option>
      </select>
    </div>

    <div class="ribbon-controls">
      <div id="defcon-pill" class="defcon-pill">
        <span class="pulse-dot"></span>
        <span id="defcon-text">DEFCON 1 // CRITICAL</span>
      </div>
      <div class="pill">TRACKS: <strong id="ribbon-tracks">4 ACTIVE</strong></div>
      <button id="auto-btn" class="pill" style="cursor:pointer;" onclick="toggleAutoEngage()">MODE: <strong id="auto-mode" style="color:var(--nominal-emerald);">AUTO-ENGAGE ROE</strong></button>
      <div class="pill">RADAR: <strong style="color:var(--nominal-emerald);">20 Hz AESA</strong></div>
      <div class="pill">LEDGER: <strong id="ledger-status" style="color:var(--friendly-cyan);">SHA-256 [VERIFIED]</strong></div>
      <div class="pill mono" id="utc-clock">00:00:00 UTC</div>
    </div>
  </header>

  <!-- 5-ZONE TACTICAL GRID -->
  <div class="tactical-grid">

    <!-- LEFT COLUMN -->
    <div class="col">
      <div class="panel-header">
        <span>OPTRONIC EO/IR TARGETING POD</span>
        <div class="sensor-toggles">
          <button class="btn-toggle active" id="btn-eo" onclick="setOptronicMode('EO_DAYLIGHT')">EO DAYLIGHT</button>
          <button class="btn-toggle" id="btn-flir-w" onclick="setOptronicMode('FLIR_WHITE_HOT')">FLIR W-HOT</button>
          <button class="btn-toggle" id="btn-flir-b" onclick="setOptronicMode('FLIR_BLACK_HOT')">FLIR B-HOT</button>
        </div>
      </div>

      <div class="optronic-viewport">
        <canvas id="optronic-canvas" class="optronic-canvas" width="640" height="420"></canvas>
        <div class="pip-zoom">
          <div class="pip-header">PIP 4X ZOOM // PAYLOAD</div>
          <canvas id="pip-canvas" class="pip-canvas" width="110" height="90"></canvas>
        </div>
      </div>

      <div class="track-table-container">
        <div class="panel-header">
          <span>CORRELATED MULTI-TARGET THREAT QUEUE</span>
          <span class="mono" id="table-track-count">4 TRACKS</span>
        </div>
        <div class="track-table-body">
          <table class="track-table">
            <thead>
              <tr>
                <th>TRK-ID</th>
                <th>CLASSIFICATION</th>
                <th>RANGE</th>
                <th>SPEED</th>
                <th>TTI</th>
                <th>SENSOR</th>
                <th>THREAT</th>
              </tr>
            </thead>
            <tbody id="track-tbody">
              <!-- Dynamically populated rows -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- CENTER COLUMN -->
    <div class="col">
      <div class="panel-header">
        <span>360° SPATIAL BATTLESPACE // 3D AESA RADAR PPI</span>
        <span class="mono">BASE: 37.7749° N, 122.4194° W</span>
      </div>

      <div class="battlespace-viewport">
        <canvas id="battlespace-canvas" class="battlespace-canvas" width="600" height="480"></canvas>
      </div>

      <div class="diagnostics-panel">
        <div class="diag-subpanel">
          <div class="sub-title">128-BIN SDR RF SPECTRUM & WATERFALL (2.4/5.8 GHz)</div>
          <canvas id="rf-canvas" class="diag-canvas" width="280" height="110"></canvas>
        </div>
        <div class="diag-subpanel">
          <div class="sub-title">RADAR MICRO-DOPPLER ROTOR SPECTROGRAM</div>
          <canvas id="doppler-canvas" class="diag-canvas" width="280" height="110"></canvas>
        </div>
      </div>
    </div>

    <!-- RIGHT COLUMN -->
    <div class="col">
      <div class="panel-header">
        <span>TARGET DOSSIER // WTA KILL-CHAIN</span>
        <span class="badge badge-crimson" id="kill-chain-badge">ENGAGE</span>
      </div>

      <div class="dossier-panel">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span class="mono" style="font-size:14px; font-weight:700;" id="dos-id">TRK #101-ALPHA</span>
          <span class="badge badge-crimson" id="dos-threat-badge">CRITICAL (92.4)</span>
        </div>
        <div style="font-size:11px; color:var(--text-muted); margin-top:2px;" id="dos-type">SUICIDE DRONE (LOITERING MUNITION)</div>

        <div class="dossier-grid">
          <div class="dossier-field">
            <div class="field-lbl">3D Distance</div>
            <div class="field-val mono" id="dos-dist">412 m</div>
          </div>
          <div class="dossier-field">
            <div class="field-lbl">Time-to-Impact</div>
            <div class="field-val mono" style="color:var(--hostile-crimson);" id="dos-tti">3.8 s</div>
          </div>
          <div class="dossier-field">
            <div class="field-lbl">Closing Speed</div>
            <div class="field-val mono" id="dos-speed">24.5 m/s</div>
          </div>
          <div class="dossier-field">
            <div class="field-lbl">Altitude (AGL)</div>
            <div class="field-val mono" id="dos-alt">148 m</div>
          </div>
          <div class="dossier-field">
            <div class="field-lbl">Maneuver Mode</div>
            <div class="field-val mono" id="dos-mode">CA_DIVE (82%)</div>
          </div>
          <div class="dossier-field">
            <div class="field-lbl">Payload Hazard</div>
            <div class="field-val mono" style="color:var(--hostile-crimson);" id="dos-payload">SHAPED CHARGE (HIGH)</div>
          </div>
        </div>

        <div style="margin-top:10px; font-size:10px; color:var(--text-muted); line-height:1.4;" id="dos-rationale">
          CRITICAL THREAT: Target in terminal ballistic dive toward Base HQ. Optimal WTA: KINETIC INTERCEPTOR (P_k: 0.94).
        </div>
      </div>

      <div class="panel-header">
        <span>EFFECTOR CONTROL MATRIX (WTA)</span>
        <span class="mono" id="wta-recom" style="color:var(--friendly-cyan);">AUTO-CUED: KINETIC</span>
      </div>

      <div class="effector-matrix-panel">
        <div class="effector-card" id="card-jam" onclick="triggerEffector('RF_JAMMER')">
          <div class="effector-left">
            <div class="effector-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--suspect-amber)" stroke-width="2"><path d="M2 12h5l3 7 4-14 3 7h5"/></svg>
            </div>
            <div>
              <div class="effector-title">DIR. RF JAMMER [2.4/5.8G]</div>
              <div class="effector-desc">Broadband C2 & Video Link Disruption</div>
            </div>
          </div>
          <span class="effector-status" id="st-jam" style="color:var(--nominal-emerald);">READY</span>
        </div>

        <div class="effector-card" id="card-spoof" onclick="triggerEffector('GPS_SPOOF')">
          <div class="effector-left">
            <div class="effector-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--friendly-cyan)" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18"/></svg>
            </div>
            <div>
              <div class="effector-title">GNSS / GPS SPOOFER</div>
              <div class="effector-desc">Synthesized Return-to-Home Divert</div>
            </div>
          </div>
          <span class="effector-status" id="st-spoof" style="color:var(--nominal-emerald);">READY</span>
        </div>

        <div class="effector-card" id="card-dazzler" onclick="triggerEffector('OPTICAL_DAZZLER')">
          <div class="effector-left">
            <div class="effector-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
            </div>
            <div>
              <div class="effector-title">OPTICAL / IR DAZZLER</div>
              <div class="effector-desc">Laser Sensor Saturation (LOS 1.6km)</div>
            </div>
          </div>
          <span class="effector-status" id="st-dazzler" style="color:var(--nominal-emerald);">READY</span>
        </div>

        <div class="effector-card" id="card-kinetic" onclick="triggerEffector('KINETIC_INTERCEPT')">
          <div class="effector-left">
            <div class="effector-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--hostile-crimson)" stroke-width="2"><polygon points="12 2 15 8 22 9 17 14 18 21 12 17 6 21 7 14 2 9 9 8 12 2"/></svg>
            </div>
            <div>
              <div class="effector-title">KINETIC INTERCEPTOR</div>
              <div class="effector-desc">Autonomous Silo-Launched Drone (6 left)</div>
            </div>
          </div>
          <span class="effector-status" id="st-kinetic" style="color:var(--nominal-emerald);">ARMED</span>
        </div>

        <button class="ceasefire-btn" onclick="emergencyCeasefire()">CEASEFIRE // DISENGAGE ALL ACTUATORS</button>
      </div>

      <div class="audit-terminal">
        <div class="panel-header" style="background:transparent; padding:0 0 4px 0; border:none; height:auto;">
          <span>CRYPTOGRAPHIC LEDGER (SHA-256)</span>
          <span class="mono" style="font-size:9px; color:var(--nominal-emerald);" id="audit-integrity-txt">100% INTEGRITY</span>
        </div>
        <div class="audit-log-body mono" id="audit-body">
          <div class="audit-line"><span class="audit-hash">#8f3a...9c12</span> [GENESIS] Initialized root defense policy.</div>
          <div class="audit-line"><span class="audit-hash">#4b12...ef89</span> [RADAR] AESA array locked target swarm.</div>
          <div class="audit-line"><span class="audit-hash">#92c1...aa34</span> [IMM-UKF] Terminal dive detected on TRK #101.</div>
        </div>
      </div>
    </div>

  </div>

  <script>
    // System State
    let selectedTrackId = 101;
    let optronicMode = 'EO_DAYLIGHT';
    let autoEngage = true;
    let radarSweepAngle = 0;
    let rfWaterfallHistory = [];

    // Synthetic Multi-Target Swarm
    let targets = [
      { id: 101, class: "SUICIDE DRONE", x: 260, y: 140, enu: [-150, 380, 160], vel: [12, -22, -8], tti: 4.2, threat: 92.4, level: "CRITICAL", badge: "EO+RAD+RF", proto: "ELRS 900M" },
      { id: 102, class: "SUICIDE DRONE", x: 420, y: 160, enu: [220, 410, 190], vel: [-14, -20, -7], tti: 6.8, threat: 88.1, level: "HIGH", badge: "EO+RAD+RF", proto: "OcuSync-3" },
      { id: 103, class: "LOITERING RECON", x: 180, y: 110, enu: [-320, 680, 240], vel: [6, -8, -1], tti: 14.5, threat: 58.0, level: "ELEVATED", badge: "RAD+RF", proto: "Crossfire" },
      { id: 104, class: "CIVILIAN FLYBY", x: 500, y: 220, enu: [480, 210, 90], vel: [-8, 2, 0], tti: 99.0, threat: 18.5, level: "SAFE", badge: "EO+RAD", proto: "WiFi" }
    ];

    let blueInterceptors = [];

    // UTC Clock
    setInterval(() => {
      const now = new Date();
      document.getElementById('utc-clock').innerText = now.toTimeString().split(' ')[0] + ' UTC';
    }, 1000);

    function setOptronicMode(mode) {
      optronicMode = mode;
      document.getElementById('btn-eo').classList.toggle('active', mode === 'EO_DAYLIGHT');
      document.getElementById('btn-flir-w').classList.toggle('active', mode === 'FLIR_WHITE_HOT');
      document.getElementById('btn-flir-b').classList.toggle('active', mode === 'FLIR_BLACK_HOT');
    }

    function toggleAutoEngage() {
      autoEngage = !autoEngage;
      const el = document.getElementById('auto-mode');
      el.innerText = autoEngage ? "AUTO-ENGAGE ROE" : "MANUAL HITL";
      el.style.color = autoEngage ? "var(--nominal-emerald)" : "var(--suspect-amber)";
    }

    async function switchScenario(scen) {
      try {
        await fetch('/api/v1/scenario', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ scenario: scen })
        });
        appendAudit(`Scenario changed to ${scen}`);
      } catch(e) {}
    }

    function appendAudit(text) {
      const body = document.getElementById('audit-body');
      const hash = '#' + Math.random().toString(16).substring(2, 6) + '...' + Math.random().toString(16).substring(2, 6);
      const div = document.createElement('div');
      div.className = 'audit-line';
      div.innerHTML = `<span class="audit-hash">${hash}</span> [ROE] ${text}`;
      body.insertBefore(div, body.firstChild);
    }

    // 1. OPTRONIC SENSOR RENDER
    const optCanvas = document.getElementById('optronic-canvas');
    const optCtx = optCanvas.getContext('2d');
    const pipCanvas = document.getElementById('pip-canvas');
    const pipCtx = pipCanvas.getContext('2d');

    function renderOptronics() {
      const w = optCanvas.width, h = optCanvas.height;

      // Background
      if (optronicMode === 'EO_DAYLIGHT') {
        const grad = optCtx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, '#0a101d');
        grad.addColorStop(0.7, '#1b2434');
        grad.addColorStop(1, '#0e1726');
        optCtx.fillStyle = grad;
        optCtx.fillRect(0, 0, w, h);
      } else if (optronicMode === 'FLIR_WHITE_HOT') {
        optCtx.fillStyle = '#11151c';
        optCtx.fillRect(0, 0, w, h);
      } else {
        optCtx.fillStyle = '#b8c0cc';
        optCtx.fillRect(0, 0, w, h);
      }

      // Artificial Horizon & Attitude Ladder
      optCtx.strokeStyle = optronicMode === 'FLIR_BLACK_HOT' ? '#222' : 'rgba(148, 163, 184, 0.3)';
      optCtx.lineWidth = 1;
      const cy = h / 2, cx = w / 2;
      optCtx.beginPath();
      optCtx.moveTo(cx - 40, cy); optCtx.lineTo(cx - 10, cy);
      optCtx.moveTo(cx + 10, cy); optCtx.lineTo(cx + 40, cy);
      optCtx.stroke();

      // Heading tape
      optCtx.strokeRect(cx - 80, 16, 160, 16);
      optCtx.fillStyle = optronicMode === 'FLIR_BLACK_HOT' ? '#000' : '#F8FAFC';
      optCtx.font = '10px JetBrains Mono';
      optCtx.fillText("048° NNE // ELEV +12°", cx - 60, 28);

      // Render Active Targets
      for (const t of targets) {
        t.x += (t.vel[0] * 0.04);
        t.y += (t.vel[1] * -0.03);
        if (t.x < 40 || t.x > w - 40) t.vel[0] *= -1;
        if (t.y < 40 || t.y > h - 40) t.vel[1] *= -1;

        const isSelected = (t.id === selectedTrackId);
        const col = (t.level === 'CRITICAL' || t.level === 'HIGH') ? '#F43F5E' : (t.level === 'ELEVATED' ? '#F59E0B' : '#10B981');

        // Draw Drone Body
        optCtx.fillStyle = (optronicMode === 'FLIR_WHITE_HOT') ? '#FFFFFF' : ((optronicMode === 'FLIR_BLACK_HOT') ? '#000000' : '#CBD5E1');
        optCtx.beginPath();
        optCtx.arc(t.x, t.y, 5, 0, Math.PI * 2);
        optCtx.fill();

        // Arms & Rotors
        optCtx.strokeStyle = optCtx.fillStyle;
        optCtx.lineWidth = 2;
        optCtx.beginPath();
        optCtx.moveTo(t.x - 14, t.y - 7); optCtx.lineTo(t.x + 14, t.y + 7);
        optCtx.moveTo(t.x - 14, t.y + 7); optCtx.lineTo(t.x + 14, t.y - 7);
        optCtx.stroke();

        // Corner Targeting Reticle
        const bw = 32, bh = 32;
        optCtx.strokeStyle = col;
        optCtx.lineWidth = isSelected ? 2 : 1;
        // Brackets
        optCtx.beginPath();
        optCtx.moveTo(t.x - bw, t.y - bh + 8); optCtx.lineTo(t.x - bw, t.y - bh); optCtx.lineTo(t.x - bw + 8, t.y - bh);
        optCtx.moveTo(t.x + bw - 8, t.y - bh); optCtx.lineTo(t.x + bw, t.y - bh); optCtx.lineTo(t.x + bw, t.y - bh + 8);
        optCtx.moveTo(t.x - bw, t.y + bh - 8); optCtx.lineTo(t.x - bw, t.y + bh); optCtx.lineTo(t.x - bw + 8, t.y + bh);
        optCtx.moveTo(t.x + bw - 8, t.y + bh); optCtx.lineTo(t.x + bw, t.y + bh); optCtx.lineTo(t.x + bw, t.y + bh - 8);
        optCtx.stroke();

        // Target Tag
        optCtx.fillStyle = col;
        optCtx.font = '10px JetBrains Mono';
        optCtx.fillText(`TRK-${t.id} [${t.class.split(' ')[0]}]`, t.x - bw, t.y - bh - 4);
        optCtx.fillText(`TTI ${t.tti}s`, t.x - bw, t.y + bh + 12);

        // Lead Pipper
        if (isSelected) {
          const lx = t.x + t.vel[0] * 1.5;
          const ly = t.y + t.vel[1] * -1.5;
          optCtx.strokeStyle = '#0EA5E9';
          optCtx.beginPath();
          optCtx.arc(lx, ly, 10, 0, Math.PI * 2);
          optCtx.moveTo(lx - 5, ly); optCtx.lineTo(lx + 5, ly);
          optCtx.moveTo(lx, ly - 5); optCtx.lineTo(lx, ly + 5);
          optCtx.stroke();
          // PiP Zoom rendering
          renderPiP(t);
        }
      }

      requestAnimationFrame(renderOptronics);
    }

    function renderPiP(target) {
      pipCtx.fillStyle = (optronicMode === 'FLIR_BLACK_HOT') ? '#b8c0cc' : '#0B101B';
      pipCtx.fillRect(0, 0, pipCanvas.width, pipCanvas.height);
      const cx = pipCanvas.width / 2, cy = pipCanvas.height / 2;

      pipCtx.fillStyle = (optronicMode === 'FLIR_WHITE_HOT') ? '#FFFFFF' : '#CBD5E1';
      pipCtx.beginPath();
      pipCtx.arc(cx, cy - 6, 12, 0, Math.PI * 2);
      pipCtx.fill();

      // Munition payload cylinder
      pipCtx.fillStyle = '#F43F5E';
      pipCtx.fillRect(cx - 8, cy + 6, 16, 18);

      pipCtx.fillStyle = '#0EA5E9';
      pipCtx.font = '8px JetBrains Mono';
      pipCtx.fillText("4X EO/IR MAG", 4, pipCanvas.height - 4);
    }

    // 2. 360° BATTLESPACE SCOPE RENDER
    const batCanvas = document.getElementById('battlespace-canvas');
    const batCtx = batCanvas.getContext('2d');

    function renderBattlespace() {
      const w = batCanvas.width, h = batCanvas.height;
      const cx = w / 2, cy = h / 2;
      const maxR = Math.min(cx, cy) - 20;

      batCtx.fillStyle = '#04070D';
      batCtx.fillRect(0, 0, w, h);

      // Topographic grid
      batCtx.strokeStyle = '#0F172A';
      batCtx.lineWidth = 1;
      for (let x = 0; x < w; x += 30) { batCtx.beginPath(); batCtx.moveTo(x, 0); batCtx.lineTo(x, h); batCtx.stroke(); }
      for (let y = 0; y < h; y += 30) { batCtx.beginPath(); batCtx.moveTo(0, y); batCtx.lineTo(w, y); batCtx.stroke(); }

      // Geodesic Range Rings
      const rings = [
        { r: maxR * (500 / 3500), col: 'rgba(244, 63, 94, 0.4)', label: '500m KILLZONE' },
        { r: maxR * (1500 / 3500), col: 'rgba(245, 158, 11, 0.35)', label: '1500m WARNING' },
        { r: maxR, col: 'rgba(16, 185, 129, 0.3)', label: '3500m DETECTION' }
      ];

      for (const ring of rings) {
        batCtx.strokeStyle = ring.col;
        batCtx.beginPath();
        batCtx.arc(cx, cy, ring.r, 0, Math.PI * 2);
        batCtx.stroke();
        batCtx.fillStyle = ring.col;
        batCtx.font = '9px JetBrains Mono';
        batCtx.fillText(ring.label, cx + 4, cy - ring.r + 10);
      }

      // Rotating Radar Sweep
      radarSweepAngle = (radarSweepAngle + 0.04) % (Math.PI * 2);
      const bx = cx + Math.cos(radarSweepAngle) * maxR;
      const by = cy + Math.sin(radarSweepAngle) * maxR;
      batCtx.strokeStyle = 'rgba(16, 185, 129, 0.7)';
      batCtx.lineWidth = 1.5;
      batCtx.beginPath();
      batCtx.moveTo(cx, cy);
      batCtx.lineTo(bx, by);
      batCtx.stroke();

      // Base HQ Insignia at Center
      batCtx.fillStyle = '#0EA5E9';
      batCtx.fillRect(cx - 4, cy - 4, 8, 8);

      // Render Targets with NATO MIL-STD-2525D Symbology
      for (const t of targets) {
        const dist = Math.hypot(t.enu[0], t.enu[1]);
        const r_ratio = Math.min(1.0, dist / 3500);
        const angle = Math.atan2(t.enu[0], t.enu[1]);
        const px = cx + Math.sin(angle) * (r_ratio * maxR);
        const py = cy - Math.cos(angle) * (r_ratio * maxR);

        // Hostile Red Diamond / Unknown Clover
        const col = (t.level === 'CRITICAL' || t.level === 'HIGH') ? '#F43F5E' : (t.level === 'ELEVATED' ? '#F59E0B' : '#10B981');
        batCtx.strokeStyle = col;
        batCtx.lineWidth = (t.id === selectedTrackId) ? 2 : 1;
        batCtx.beginPath();
        batCtx.moveTo(px, py - 7); batCtx.lineTo(px + 7, py); batCtx.lineTo(px, py + 7); batCtx.lineTo(px - 7, py);
        batCtx.closePath();
        batCtx.stroke();

        // Altitude stem
        batCtx.strokeStyle = 'rgba(148, 163, 184, 0.4)';
        batCtx.beginPath();
        batCtx.moveTo(px, py); batCtx.lineTo(px, py + 12);
        batCtx.stroke();

        batCtx.fillStyle = '#F8FAFC';
        batCtx.font = '9px JetBrains Mono';
        batCtx.fillText(`TRK-${t.id} (${t.enu[2]}m)`, px + 8, py);
      }

      // Render Friendly Blue Interceptors
      for (const b of blueInterceptors) {
        batCtx.strokeStyle = '#0EA5E9';
        batCtx.fillStyle = '#0EA5E9';
        batCtx.strokeRect(b.x - 5, b.y - 5, 10, 10);
        batCtx.fillText("INT-ALPHA", b.x + 8, b.y);
      }

      requestAnimationFrame(renderBattlespace);
    }

    // 3. RF WATERFALL & MICRO-DOPPLER CANVASES
    const rfCanvas = document.getElementById('rf-canvas');
    const rfCtx = rfCanvas.getContext('2d');
    const dopCanvas = document.getElementById('doppler-canvas');
    const dopCtx = dopCanvas.getContext('2d');

    function renderSpectrograms() {
      // 128-bin RF PSD slice
      const rw = rfCanvas.width, rh = rfCanvas.height;
      rfCtx.fillStyle = '#020408';
      rfCtx.fillRect(0, 0, rw, rh);

      rfCtx.strokeStyle = '#F59E0B';
      rfCtx.lineWidth = 1;
      rfCtx.beginPath();
      for (let i = 0; i < 128; i++) {
        const x = (i / 128) * rw;
        const db = Math.sin(i * 0.1) * 15 + Math.random() * 8 + (i > 50 && i < 75 ? 45 : 10);
        const y = rh - (db / 70) * rh;
        if (i === 0) rfCtx.moveTo(x, y); else rfCtx.lineTo(x, y);
      }
      rfCtx.stroke();

      // Micro-Doppler Canvas
      const dw = dopCanvas.width, dh = dopCanvas.height;
      dopCtx.fillStyle = '#020408';
      dopCtx.fillRect(0, 0, dw, dh);
      dopCtx.strokeStyle = '#10B981';
      dopCtx.lineWidth = 1.2;
      dopCtx.beginPath();
      const dcx = dw / 2;
      for (let j = 0; j < 64; j++) {
        const x = (j / 64) * dw;
        const d_amp = (Math.abs(j - 32) < 4 ? 40 : (Math.abs(j - 32) === 12 ? 25 : Math.random() * 6));
        const y = dh - (d_amp / 50) * dh;
        if (j === 0) dopCtx.moveTo(x, y); else dopCtx.lineTo(x, y);
      }
      dopCtx.stroke();

      setTimeout(renderSpectrograms, 100);
    }

    // UI Updates
    function updateTrackTable() {
      const tbody = document.getElementById('track-tbody');
      tbody.innerHTML = '';
      for (const t of targets) {
        const tr = document.createElement('tr');
        if (t.id === selectedTrackId) tr.className = 'selected';
        tr.onclick = () => selectTrack(t.id);
        const bCol = (t.level === 'CRITICAL' || t.level === 'HIGH') ? 'badge-crimson' : (t.level === 'ELEVATED' ? 'badge-amber' : 'badge-emerald');
        tr.innerHTML = `
          <td class="mono">#${t.id}</td>
          <td><span class="badge ${bCol}">${t.class.split(' ')[0]}</span></td>
          <td class="mono">${Math.round(Math.hypot(t.enu[0], t.enu[1]))}m</td>
          <td class="mono">${Math.round(Math.hypot(t.vel[0], t.vel[1]))} m/s</td>
          <td class="mono" style="color:${t.tti < 8 ? 'var(--hostile-crimson)' : 'inherit'}; font-weight:700;">${t.tti}s</td>
          <td><span class="badge badge-cyan">${t.badge}</span></td>
          <td><span class="badge ${bCol}">${t.threat.toFixed(0)}</span></td>
        `;
        tbody.appendChild(tr);
      }
    }

    function selectTrack(id) {
      selectedTrackId = id;
      const t = targets.find(item => item.id === id);
      if (t) {
        document.getElementById('dos-id').innerText = `TRK #${t.id}-ALPHA`;
        document.getElementById('dos-type').innerText = t.class;
        document.getElementById('dos-threat-badge').innerText = `${t.level} (${t.threat})`;
        document.getElementById('dos-dist').innerText = `${Math.round(Math.hypot(t.enu[0], t.enu[1]))} m`;
        document.getElementById('dos-tti').innerText = `${t.tti} s`;
        document.getElementById('dos-speed').innerText = `${Math.round(Math.hypot(t.vel[0], t.vel[1]))} m/s`;
        document.getElementById('dos-alt').innerText = `${t.enu[2]} m`;
      }
      updateTrackTable();
    }

    async function triggerEffector(type) {
      const card = {
        'RF_JAMMER': document.getElementById('card-jam'),
        'GPS_SPOOF': document.getElementById('card-spoof'),
        'OPTICAL_DAZZLER': document.getElementById('card-dazzler'),
        'KINETIC_INTERCEPT': document.getElementById('card-kinetic')
      }[type];

      appendAudit(`Engaged ${type} against TRK #${selectedTrackId}`);
      try {
        const resp = await fetch('/api/v1/countermeasures/engage', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ target_id: selectedTrackId, measure_type: type, operator: "COMMANDER_C2" })
        });
        const data = await resp.json();
        appendAudit(`BDA: ${data.details.bda} on TRK #${selectedTrackId}`);
      } catch(e) {}
    }

    async function emergencyCeasefire() {
      await fetch('/api/v1/countermeasures/disengage', { method: 'POST' });
      appendAudit("ALL ACTUATORS DISENGAGED (CEASEFIRE)");
    }

    renderOptronics();
    renderBattlespace();
    renderSpectrograms();
    updateTrackTable();
    setInterval(updateTrackTable, 1000);
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def get_command_center_ui():
    return HTMLResponse(content=LATTICE_GOTHAM_HTML)

@app.get("/command-center", response_class=HTMLResponse)
def get_command_center_alias():
    return HTMLResponse(content=LATTICE_GOTHAM_HTML)

@app.get("/api/v1/status")
def get_system_status():
    summary = threat_mgr.get_summary()
    audit_valid, block_count, audit_msg = audit_logger.verify_chain_integrity()
    return {
        "status": "ONLINE",
        "system": "LATTICE-CUAS v4.0",
        "defcon": summary["overall_threat_level"],
        "scenario": summary["current_scenario"],
        "automation_mode": summary["automation_mode"],
        "active_threats": summary["active_threat_count"],
        "total_detections": summary["total_detections"],
        "neutralized_count": summary["neutralized_count"],
        "actuators": {k.value: v.value for k, v in countermeasure_ctrl.statuses.items()},
        "audit_chain": {
            "is_valid": audit_valid,
            "total_blocks": block_count,
            "status_message": audit_msg
        },
        "timestamp": time.time()
    }

@app.get("/api/v1/threats")
def get_threats():
    return threat_mgr.get_summary()

@app.post("/api/v1/scenario")
def set_scenario(req: ScenarioRequest):
    threat_mgr.set_scenario(req.scenario)
    audit_logger.log_event("SCENARIO_CHANGED", {"scenario": req.scenario}, operator="COMMANDER_C2")
    return {"status": "UPDATED", "scenario": req.scenario}

@app.post("/api/v1/automation-mode")
def set_automation_mode(req: AutomationModeRequest):
    threat_mgr.automation_mode = req.mode
    audit_logger.log_event("AUTOMATION_MODE_CHANGED", {"mode": req.mode}, operator="COMMANDER_C2")
    return {"status": "UPDATED", "automation_mode": req.mode}

@app.post("/api/v1/countermeasures/engage")
def engage_countermeasure(req: CountermeasureRequest):
    countermeasure_ctrl.set_operator(req.operator)
    measure_upper = req.measure_type.upper()

    if measure_upper == "RF_JAMMER":
        res = countermeasure_ctrl.activate_rf_jammer(req.target_id, duration_sec=req.duration_sec)
        rf_sensor.set_jammer_active(["2.4 GHz", "5.8 GHz"])
    elif measure_upper == "GPS_SPOOF":
        res = countermeasure_ctrl.activate_gps_spoofing(req.target_id)
    elif measure_upper == "OPTICAL_DAZZLER":
        res = countermeasure_ctrl.activate_optical_dazzler(req.target_id)
    elif measure_upper == "KINETIC_INTERCEPT":
        res = countermeasure_ctrl.launch_kinetic_interceptor(req.target_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown countermeasure: {req.measure_type}")

    audit_logger.log_event(
        "EFFECTOR_ENGAGED",
        {"target_id": req.target_id, "measure": measure_upper, "bda": res.get("bda", "ENGAGED")},
        operator=req.operator
    )
    threat_mgr.clear_threat(req.target_id, neutralized=True)
    return {"result": "ENGAGEMENT_SUCCESS", "details": res}

@app.post("/api/v1/countermeasures/disengage")
def disengage_all():
    countermeasure_ctrl.disengage_all()
    rf_sensor.set_jammer_active([])
    audit_logger.log_event("CEASEFIRE_ALL_STANDBY", {}, operator="COMMANDER_C2")
    return {"result": "DISENGAGED", "status": "ALL_STANDBY"}

@app.get("/api/v1/audit/verify")
def verify_audit_ledger():
    valid, count, msg = audit_logger.verify_chain_integrity()
    return {
        "is_valid": valid,
        "blocks_verified": count,
        "integrity_message": msg,
        "recent_blocks": audit_logger.get_recent_blocks(limit=8)
    }

@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            summary = threat_mgr.get_summary()
            data = {
                "timestamp": time.time(),
                "summary": summary,
                "actuators": {k.value: v.value for k, v in countermeasure_ctrl.statuses.items()},
                "rf_spectrum": rf_sensor.generate_waterfall_slice(2437.0, target_present=True),
                "audit_recent": audit_logger.get_recent_blocks(limit=5)
            }
            await websocket.send_json(data)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info("Client disconnected from telemetry stream.")

def run_server(host: str = "127.0.0.1", port: int = 8080):
    import uvicorn
    logger.info(f"Starting LATTICE-CUAS C2 Server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")

if __name__ == "__main__":
    run_server()
