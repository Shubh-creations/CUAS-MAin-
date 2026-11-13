"""
FastAPI REST & WebSocket Command and Control (C2) Server with Full-Bleed Spatial Battlespace OS (v4.0-Lattice).
Provides a 100vw x 100vh Full-Bleed Spatial Battlespace Operating System (Anduril Lattice OS Architecture)
with hardware-accelerated 2.5D/3D Isometric projection, chamfered glassmorphic HUD overlays,
8-drone multi-target swarm intelligence, multi-spectral EO/IR FLIR shaders, and optimal Weapon-Target Assignment (WTA).
"""

from typing import Dict, List, Optional, Any
import time
import asyncio
import json
import math

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
    description="Autonomous Multi-Target Counter-Swarm Air Defense & Command Architecture (Anduril Lattice OS)"
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


LATTICE_SPATIAL_OS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LATTICE // AUTONOMOUS AIR DEFENSE OS</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&family=JetBrains+Mono:wght@400;500;600;700&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-void: #04070B;
      --bg-panel: rgba(8, 14, 26, 0.88);
      --bg-card: rgba(15, 23, 42, 0.85);
      --border-cyan: rgba(0, 240, 255, 0.28);
      --border-hairline: rgba(51, 65, 85, 0.5);
      --hostile-crimson: #FF2A54;
      --hostile-glow: rgba(255, 42, 84, 0.4);
      --suspect-amber: #FFB000;
      --friendly-cyan: #00F0FF;
      --cyan-glow: rgba(0, 240, 255, 0.35);
      --nominal-emerald: #10B981;
      --text-primary: #F8FAFC;
      --text-secondary: #94A3B8;
      --text-muted: #64748B;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      width: 100vw;
      height: 100vh;
      overflow: hidden;
      background-color: var(--bg-void);
      color: var(--text-primary);
      font-family: 'Rajdhani', -apple-system, sans-serif;
      user-select: none;
      position: fixed;
      inset: 0;
    }
    .mono {
      font-family: 'JetBrains Mono', monospace;
      font-variant-numeric: tabular-nums;
    }
    .chakra {
      font-family: 'Chakra Petch', sans-serif;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }

    /* FULL-BLEED BATTLESPACE CANVAS (Z-INDEX 1) */
    #battlespace-canvas {
      position: fixed;
      inset: 0;
      width: 100vw;
      height: 100vh;
      z-index: 1;
      display: block;
      cursor: crosshair;
    }

    /* DYNAMIC TETHER LEADER SVG (Z-INDEX 5) */
    #tether-svg {
      position: fixed;
      inset: 0;
      width: 100vw;
      height: 100vh;
      z-index: 5;
      pointer-events: none;
    }

    /* SPATIAL HUD OVERLAYS ROOT (Z-INDEX 10) */
    .spatial-hud-root {
      position: fixed;
      inset: 0;
      z-index: 10;
      pointer-events: none;
    }

    /* PRECISION MILITARY CHAMFERED POD GEOMETRY */
    .hud-pod {
      pointer-events: auto;
      position: fixed;
      background: linear-gradient(135deg, rgba(8, 14, 26, 0.90) 0%, rgba(4, 7, 14, 0.95) 100%);
      backdrop-filter: blur(20px) saturate(190%);
      -webkit-backdrop-filter: blur(20px) saturate(190%);
      border: 1px solid var(--border-cyan);
      box-shadow: 0 16px 48px rgba(0, 0, 0, 0.8), inset 0 0 1px rgba(0, 240, 255, 0.4);
      clip-path: polygon(
        0 12px, 12px 0,
        calc(100% - 12px) 0, 100% 12px,
        100% calc(100% - 12px), calc(100% - 12px) 100%,
        12px 100%, 0 calc(100% - 12px)
      );
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .hud-pod:hover {
      border-color: rgba(0, 240, 255, 0.5);
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.9), inset 0 0 2px rgba(0, 240, 255, 0.6);
    }

    /* CORNER FIDUCIALS */
    .fiducial-tl, .fiducial-tr, .fiducial-bl, .fiducial-br {
      position: absolute;
      width: 8px;
      height: 8px;
      pointer-events: none;
    }
    .fiducial-tl { top: 3px; left: 3px; border-top: 1.5px solid var(--friendly-cyan); border-left: 1.5px solid var(--friendly-cyan); }
    .fiducial-tr { top: 3px; right: 3px; border-top: 1.5px solid var(--friendly-cyan); border-right: 1.5px solid var(--friendly-cyan); }
    .fiducial-bl { bottom: 3px; left: 3px; border-bottom: 1.5px solid var(--friendly-cyan); border-left: 1.5px solid var(--friendly-cyan); }
    .fiducial-br { bottom: 3px; right: 3px; border-bottom: 1.5px solid var(--friendly-cyan); border-right: 1.5px solid var(--friendly-cyan); }

    .pod-header {
      height: 32px;
      background: rgba(15, 23, 42, 0.7);
      border-bottom: 1px solid var(--border-cyan);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 14px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.12em;
      color: var(--friendly-cyan);
      flex-shrink: 0;
    }
    .pod-header .wm {
      font-size: 9px;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
    }

    /* ZONE A — TOP CENTER FLOATING COMMAND BAR */
    #zone-a-bar {
      top: 12px;
      left: 50%;
      transform: translateX(-50%);
      height: 48px;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0 18px;
      z-index: 100;
    }
    .brand-mark {
      width: 24px;
      height: 24px;
      border: 2px solid var(--friendly-cyan);
      transform: rotate(45deg);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 10px var(--cyan-glow);
    }
    .brand-inner {
      width: 8px;
      height: 8px;
      background: var(--friendly-cyan);
    }
    .brand-title {
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0.16em;
      color: var(--text-primary);
    }
    .defcon-pill {
      font-size: 11px;
      font-weight: 700;
      padding: 4px 12px;
      border-radius: 2px;
      border: 1px solid var(--hostile-crimson);
      color: var(--hostile-crimson);
      background: rgba(255, 42, 84, 0.15);
      display: flex;
      align-items: center;
      gap: 8px;
      box-shadow: 0 0 12px var(--hostile-glow);
      animation: pulseDefcon 1.8s infinite;
      cursor: pointer;
    }
    @keyframes pulseDefcon {
      0%, 100% { box-shadow: 0 0 8px var(--hostile-glow); }
      50% { box-shadow: 0 0 20px var(--hostile-glow); }
    }
    .pill-btn {
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      color: var(--text-secondary);
      font-family: 'Rajdhani', sans-serif;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      padding: 4px 10px;
      border-radius: 2px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .pill-btn:hover, .pill-btn.active {
      color: var(--friendly-cyan);
      border-color: var(--friendly-cyan);
      background: rgba(0, 240, 255, 0.12);
      box-shadow: 0 0 8px var(--cyan-glow);
    }
    .scenario-dropdown {
      background: var(--bg-card);
      border: 1px solid var(--border-cyan);
      color: var(--friendly-cyan);
      font-family: 'Rajdhani', sans-serif;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      padding: 4px 8px;
      border-radius: 2px;
      outline: none;
      cursor: pointer;
    }

    /* ZONE B — TOP-LEFT FLOATING EO/IR GIMBAL POD */
    #zone-b-pod {
      top: 68px;
      left: 16px;
      width: 370px;
      height: 290px;
      display: flex;
      flex-direction: column;
    }
    .optronic-viewport {
      flex: 1;
      position: relative;
      background: #000;
      overflow: hidden;
    }
    #optronic-canvas {
      width: 100%;
      height: 100%;
      display: block;
    }
    .pip-zoom-loupe {
      position: absolute;
      top: 10px;
      right: 10px;
      width: 100px;
      height: 100px;
      border: 1px solid var(--friendly-cyan);
      background: rgba(4, 7, 14, 0.85);
      box-shadow: 0 4px 16px rgba(0,0,0,0.8);
      display: flex;
      flex-direction: column;
    }
    .pip-label {
      font-size: 8px;
      font-weight: 700;
      background: rgba(0, 240, 255, 0.2);
      color: var(--friendly-cyan);
      padding: 2px 4px;
      letter-spacing: 0.5px;
    }
    #pip-canvas {
      width: 100%;
      flex: 1;
      display: block;
    }
    .sensor-mode-strip {
      display: flex;
      gap: 4px;
      padding: 6px 10px;
      background: rgba(8, 14, 26, 0.95);
      border-top: 1px solid var(--border-hairline);
    }
    .shader-btn {
      flex: 1;
      background: var(--bg-card);
      border: 1px solid var(--border-hairline);
      color: var(--text-muted);
      font-family: 'Rajdhani', sans-serif;
      font-size: 10px;
      font-weight: 700;
      padding: 3px 0;
      text-align: center;
      cursor: pointer;
      transition: all 0.15s;
    }
    .shader-btn:hover, .shader-btn.active {
      color: var(--friendly-cyan);
      border-color: var(--friendly-cyan);
      background: rgba(0, 240, 255, 0.15);
    }

    /* ZONE C — BOTTOM-LEFT FLOATING SWARM TRACK MATRIX */
    #zone-c-pod {
      bottom: 16px;
      left: 16px;
      width: 410px;
      height: 380px;
      display: flex;
      flex-direction: column;
    }
    .track-table-body {
      flex: 1;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--border-cyan) transparent;
    }
    table.track-matrix {
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
    }
    table.track-matrix th {
      position: sticky;
      top: 0;
      background: rgba(15, 23, 42, 0.92);
      padding: 6px 8px;
      text-align: left;
      font-weight: 700;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border-cyan);
      font-size: 10px;
      letter-spacing: 0.08em;
    }
    table.track-matrix td {
      padding: 6px 8px;
      border-bottom: 1px solid var(--border-hairline);
      color: var(--text-secondary);
      cursor: pointer;
      vertical-align: middle;
      transition: background 0.1s;
    }
    table.track-matrix tr:hover td {
      background: rgba(0, 240, 255, 0.08);
      color: var(--text-primary);
    }
    table.track-matrix tr.locked td {
      background: rgba(0, 240, 255, 0.16);
      color: var(--friendly-cyan);
      font-weight: 700;
    }
    .badge {
      display: inline-block;
      padding: 1px 5px;
      border-radius: 2px;
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 0.5px;
    }
    .badge-crimson { background: rgba(255, 42, 84, 0.2); color: var(--hostile-crimson); border: 1px solid var(--hostile-crimson); }
    .badge-amber { background: rgba(255, 176, 0, 0.2); color: var(--suspect-amber); border: 1px solid var(--suspect-amber); }
    .badge-cyan { background: rgba(0, 240, 255, 0.2); color: var(--friendly-cyan); border: 1px solid var(--friendly-cyan); }
    .badge-emerald { background: rgba(16, 185, 129, 0.2); color: var(--nominal-emerald); border: 1px solid var(--nominal-emerald); }

    .tti-bar-wrap {
      width: 48px;
      height: 6px;
      background: rgba(51, 65, 85, 0.5);
      border-radius: 2px;
      overflow: hidden;
      display: inline-block;
      vertical-align: middle;
      margin-left: 4px;
    }
    .tti-bar-fill {
      height: 100%;
      background: var(--hostile-crimson);
      transition: width 0.3s;
    }

    /* ZONE D — RIGHT FLOATING TARGET INTELLIGENCE DOSSIER */
    #zone-d-pod {
      top: 68px;
      right: 16px;
      width: 390px;
      bottom: 84px;
      display: flex;
      flex-direction: column;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--border-cyan) transparent;
    }
    .dossier-content {
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .dossier-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .threat-dial-row {
      display: flex;
      align-items: center;
      gap: 16px;
      background: rgba(15, 23, 42, 0.6);
      padding: 10px 14px;
      border: 1px solid var(--border-hairline);
      border-radius: 2px;
    }
    .dial-svg-wrap {
      width: 74px;
      height: 74px;
      position: relative;
      flex-shrink: 0;
    }
    .dial-svg-wrap svg {
      width: 100%;
      height: 100%;
      transform: rotate(-90deg);
    }
    .dial-num {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      font-weight: 700;
      color: var(--hostile-crimson);
    }
    .dial-subscores {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .subscore-line {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: var(--text-secondary);
    }
    .subscore-line strong { color: var(--text-primary); }

    .telemetry-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    .telem-box {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border-hairline);
      padding: 6px 10px;
      border-radius: 2px;
    }
    .telem-lbl {
      font-size: 9px;
      color: var(--text-muted);
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }
    .telem-val {
      font-size: 13px;
      font-weight: 700;
      color: var(--text-primary);
      margin-top: 2px;
    }

    .imm-mode-box {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border-hairline);
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .imm-bar-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 10px;
    }
    .imm-prog-bg {
      width: 130px;
      height: 6px;
      background: rgba(51, 65, 85, 0.5);
      border-radius: 2px;
      overflow: hidden;
    }
    .imm-prog-fill {
      height: 100%;
      background: var(--friendly-cyan);
      transition: width 0.3s;
    }

    .spectrogram-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .spec-box {
      background: #020408;
      border: 1px solid var(--border-cyan);
      padding: 6px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .spec-title {
      font-size: 9px;
      font-weight: 700;
      color: var(--text-secondary);
      letter-spacing: 0.5px;
    }
    canvas.spec-canvas {
      width: 100%;
      height: 70px;
      background: #000;
      display: block;
    }

    /* ZONE E — BOTTOM-CENTER AUTONOMOUS KILL-CHAIN DOCK */
    #zone-e-dock {
      bottom: 14px;
      left: 50%;
      transform: translateX(-50%);
      width: 740px;
      display: flex;
      flex-direction: column;
    }
    .killchain-stepper {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 16px;
      background: rgba(15, 23, 42, 0.7);
      border-bottom: 1px solid var(--border-cyan);
    }
    .kc-step {
      font-size: 10px;
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 0.1em;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .kc-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--text-muted);
    }
    .kc-step.active {
      color: var(--hostile-crimson);
    }
    .kc-step.active .kc-dot {
      background: var(--hostile-crimson);
      box-shadow: 0 0 8px var(--hostile-glow);
    }
    .kc-arrow {
      color: var(--border-cyan);
      font-size: 10px;
    }

    .effector-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr) 140px;
      gap: 8px;
      padding: 10px 14px;
      background: rgba(8, 14, 26, 0.95);
    }
    .effector-btn {
      background: rgba(15, 23, 42, 0.85);
      border: 1px solid var(--border-hairline);
      padding: 8px 10px;
      border-radius: 2px;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 3px;
      transition: all 0.15s;
    }
    .effector-btn:hover {
      border-color: var(--friendly-cyan);
      background: rgba(0, 240, 255, 0.1);
      box-shadow: 0 0 10px var(--cyan-glow);
    }
    .effector-btn.active {
      border-color: var(--hostile-crimson);
      background: rgba(255, 42, 84, 0.2);
      box-shadow: 0 0 12px var(--hostile-glow);
    }
    .eff-title {
      font-size: 11px;
      font-weight: 700;
      color: var(--text-primary);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .eff-sub {
      font-size: 9px;
      color: var(--text-muted);
    }
    .eff-status {
      font-size: 9px;
      font-weight: 700;
      color: var(--nominal-emerald);
      margin-top: 2px;
    }
    .ceasefire-pod-btn {
      background: rgba(255, 42, 84, 0.18);
      border: 1px solid var(--hostile-crimson);
      color: var(--hostile-crimson);
      font-family: 'Rajdhani', sans-serif;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.12em;
      border-radius: 2px;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 8px var(--hostile-glow);
      transition: all 0.15s;
    }
    .ceasefire-pod-btn:hover {
      background: rgba(255, 42, 84, 0.35);
      box-shadow: 0 0 16px var(--hostile-glow);
    }

    .audit-strip {
      background: #020408;
      border-top: 1px solid var(--border-cyan);
      padding: 4px 14px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 10px;
      color: var(--text-muted);
    }
    .audit-ticker {
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: var(--friendly-cyan);
    }

    /* CONTROLS HINT TOOLTIP (BOTTOM RIGHT) */
    .controls-hint {
      position: fixed;
      bottom: 16px;
      right: 16px;
      font-size: 9px;
      color: var(--text-muted);
      background: rgba(8, 14, 26, 0.7);
      padding: 4px 8px;
      border: 1px solid var(--border-hairline);
      border-radius: 2px;
      z-index: 100;
      pointer-events: none;
    }
  </style>
</head>
<body>

  <!-- FULL-BLEED BATTLESPACE 3D/2.5D CANVAS (Z-INDEX 1) -->
  <canvas id="battlespace-canvas"></canvas>

  <!-- DYNAMIC TETHER LEADER-LINE SVG (Z-INDEX 5) -->
  <svg id="tether-svg">
    <defs>
      <filter id="glow-line" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="3" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
    <path id="leader-path" d="" fill="none" stroke="var(--friendly-cyan)" stroke-width="1.5" stroke-dasharray="6,4" filter="url(#glow-line)" opacity="0.85"/>
    <circle id="leader-dot-tgt" cx="-100" cy="-100" r="4" fill="var(--hostile-crimson)" stroke="#fff" stroke-width="1.5"/>
    <circle id="leader-dot-card" cx="-100" cy="-100" r="3" fill="var(--friendly-cyan)"/>
  </svg>

  <!-- SPATIAL HUD OVERLAYS (Z-INDEX 10) -->
  <div class="spatial-hud-root">

    <!-- ZONE A: FLOATING TOP TACTICAL COMMAND BAR -->
    <div id="zone-a-bar" class="hud-pod">
      <div class="fiducial-tl"></div><div class="fiducial-tr"></div><div class="fiducial-bl"></div><div class="fiducial-br"></div>
      
      <div style="display:flex; align-items:center; gap:10px;">
        <div class="brand-mark"><div class="brand-inner"></div></div>
        <div>
          <div class="brand-title chakra">LATTICE-OS // C2</div>
          <div class="wm mono" style="font-size:8px; color:var(--friendly-cyan);">SPATIAL AIR DEFENSE v4.0</div>
        </div>
      </div>

      <div id="defcon-indicator" class="defcon-pill" onclick="cycleDefcon()">
        <span class="mono" id="defcon-text">DEFCON 1 // CRITICAL</span>
      </div>

      <div style="display:flex; gap:6px;">
        <button class="pill-btn active" id="btn-view-3d" onclick="setViewMode('3D_ISOMETRIC')">3D ISOMETRIC</button>
        <button class="pill-btn" id="btn-view-2d" onclick="setViewMode('2D_PLANAR')">2D PLANAR</button>
      </div>

      <select id="scenario-selector" class="scenario-dropdown" onchange="switchScenario(this.value)">
        <option value="SWARM_SATURATION">SCENARIO: SWARM SATURATION (8 UAVs)</option>
        <option value="FPV_TERMINAL_DIVE">SCENARIO: FPV TERMINAL SUICIDE DIVE</option>
        <option value="RF_SILENT_STEALTH">SCENARIO: RF-SILENT AUTONOMOUS MUNITION</option>
        <option value="MIXED_AIRSPACE">SCENARIO: MIXED CIVILIAN / HOSTILE</option>
      </select>

      <button id="btn-autonomy" class="pill-btn" onclick="toggleAutonomy()">
        ROE: <strong id="autonomy-txt" style="color:var(--nominal-emerald);">AUTO-ENGAGE</strong>
      </button>

      <button id="btn-audio" class="pill-btn" onclick="toggleAudioMaster()">
        AUDIO: <strong id="audio-txt" style="color:var(--friendly-cyan);">SYNTH ON</strong>
      </button>

      <div class="mono" id="utc-clock" style="font-size:12px; color:var(--text-primary); margin-left:6px;">00:00:00 UTC</div>
    </div>

    <!-- ZONE B: FLOATING EO/IR GIMBAL POD -->
    <div id="zone-b-pod" class="hud-pod">
      <div class="fiducial-tl"></div><div class="fiducial-tr"></div><div class="fiducial-bl"></div><div class="fiducial-br"></div>
      <div class="pod-header">
        <span>OPTRONIC EO/IR GIMBAL // TGT LOCK</span>
        <span class="wm mono" id="gimbal-fov-txt">FOV: 14.2° | 12X</span>
      </div>

      <div class="optronic-viewport">
        <canvas id="optronic-canvas" width="370" height="215"></canvas>
        <div class="pip-zoom-loupe">
          <div class="pip-label">PIP 4X LOUPE</div>
          <canvas id="pip-canvas" width="100" height="80"></canvas>
        </div>
      </div>

      <div class="sensor-mode-strip">
        <div class="shader-btn active" id="btn-sh-eo" onclick="setShaderMode('EO_DAYLIGHT')">EO DAYLIGHT</div>
        <div class="shader-btn" id="btn-sh-flir-w" onclick="setShaderMode('FLIR_WHITE_HOT')">FLIR W-HOT</div>
        <div class="shader-btn" id="btn-sh-flir-b" onclick="setShaderMode('FLIR_BLACK_HOT')">FLIR B-HOT</div>
        <div class="shader-btn" id="btn-sh-swir" onclick="setShaderMode('SWIR_NIGHT_VISION')">SWIR NV</div>
      </div>
    </div>

    <!-- ZONE C: FLOATING SWARM TRACK MATRIX -->
    <div id="zone-c-pod" class="hud-pod">
      <div class="fiducial-tl"></div><div class="fiducial-tr"></div><div class="fiducial-bl"></div><div class="fiducial-br"></div>
      <div class="pod-header">
        <span>ACTIVE SWARM TRACKS [8]</span>
        <span class="wm mono" id="matrix-swarm-index" style="color:var(--hostile-crimson);">THREAT INDEX: 94.2/100</span>
      </div>

      <div class="track-table-body">
        <table class="track-matrix">
          <thead>
            <tr>
              <th>TRK-ID</th>
              <th>CLASS</th>
              <th>RANGE</th>
              <th>SPEED</th>
              <th>TTI</th>
              <th>SENSORS</th>
              <th>ACT</th>
            </tr>
          </thead>
          <tbody id="track-matrix-tbody">
            <!-- Populated dynamically via JS -->
          </tbody>
        </table>
      </div>
    </div>

    <!-- ZONE D: FLOATING TARGET INTELLIGENCE DOSSIER -->
    <div id="zone-d-pod" class="hud-pod">
      <div class="fiducial-tl"></div><div class="fiducial-tr"></div><div class="fiducial-bl"></div><div class="fiducial-br"></div>
      <div class="pod-header">
        <span>TARGET DOSSIER // WTA</span>
        <span class="badge badge-crimson" id="dos-killchain-tag">ENGAGE [STAGE 5]</span>
      </div>

      <div class="dossier-content">
        <div class="dossier-top">
          <div>
            <div class="mono" style="font-size:16px; font-weight:700; color:var(--text-primary);" id="dos-track-id">TRK #101-ALPHA</div>
            <div style="font-size:11px; color:var(--text-muted);" id="dos-class-label">SUICIDE FPV LOITERING MUNITION</div>
          </div>
          <span class="badge badge-crimson" id="dos-severity-badge">CRITICAL (94.2)</span>
        </div>

        <!-- Threat Dial & Subscores -->
        <div class="threat-dial-row">
          <div class="dial-svg-wrap">
            <svg viewBox="0 0 36 36">
              <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="rgba(51, 65, 85, 0.4)" stroke-width="3.5" />
              <path id="dial-arc" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--hostile-crimson)" stroke-width="3.5" stroke-dasharray="94, 100" />
            </svg>
            <div class="dial-num mono" id="dial-score-num">94</div>
          </div>
          <div class="dial-subscores">
            <div class="subscore-line"><span>Kinematic Lethality:</span><strong class="mono" id="sub-kin">96%</strong></div>
            <div class="subscore-line"><span>Payload Hazard:</span><strong class="mono" id="sub-pay">92%</strong></div>
            <div class="subscore-line"><span>RF Stealth Anomaly:</span><strong class="mono" id="sub-rf">88%</strong></div>
            <div class="subscore-line"><span>Swarm Cohesion:</span><strong class="mono" id="sub-swm">95%</strong></div>
          </div>
        </div>

        <!-- 3D Coordinates & Telemetry Grid -->
        <div class="telemetry-grid">
          <div class="telem-box">
            <div class="telem-lbl">3D Distance (Slant)</div>
            <div class="telem-val mono" id="telem-dist">412 m</div>
          </div>
          <div class="telem-box">
            <div class="telem-lbl">Time-to-Impact (TTI)</div>
            <div class="telem-val mono" style="color:var(--hostile-crimson);" id="telem-tti">3.8 s</div>
          </div>
          <div class="telem-box">
            <div class="telem-lbl">Closing Velocity</div>
            <div class="telem-val mono" id="telem-vel">26.2 m/s</div>
          </div>
          <div class="telem-box">
            <div class="telem-lbl">Altitude (AGL / U)</div>
            <div class="telem-val mono" id="telem-alt">142 m</div>
          </div>
        </div>

        <!-- IMM Kinematic Mode Probabilities -->
        <div class="imm-mode-box">
          <div class="pod-header" style="height:auto; background:transparent; padding:0; border:none; margin-bottom:2px;">
            <span>IMM-UKF 3D KINEMATICS</span>
            <span class="wm mono">60-STEP FORECAST</span>
          </div>
          <div class="imm-bar-row">
            <span>CV (Loiter/Recon):</span>
            <div class="imm-prog-bg"><div class="imm-prog-fill" id="imm-bar-cv" style="width: 4%;"></div></div>
            <span class="mono" id="imm-txt-cv">4%</span>
          </div>
          <div class="imm-bar-row">
            <span>CTRV (Evasive Weave):</span>
            <div class="imm-prog-bg"><div class="imm-prog-fill" id="imm-bar-ctrv" style="width: 14%;"></div></div>
            <span class="mono" id="imm-txt-ctrv">14%</span>
          </div>
          <div class="imm-bar-row">
            <span>CA_DIVE (Suicide Dive):</span>
            <div class="imm-prog-bg"><div class="imm-prog-fill" id="imm-bar-dive" style="width: 82%; background:var(--hostile-crimson);"></div></div>
            <span class="mono" id="imm-txt-dive" style="color:var(--hostile-crimson);">82%</span>
          </div>
        </div>

        <!-- Dual Spectrograms: 128-Bin SDR RF + Micro-Doppler -->
        <div class="spectrogram-row">
          <div class="spec-box">
            <div class="spec-title">128-BIN SDR SPECTRUM (ELRS)</div>
            <canvas id="rf-spec-canvas" class="spec-canvas" width="160" height="70"></canvas>
          </div>
          <div class="spec-box">
            <div class="spec-title">ROTOR MICRO-DOPPLER (180Hz)</div>
            <canvas id="dop-spec-canvas" class="spec-canvas" width="160" height="70"></canvas>
          </div>
        </div>

        <!-- Ground Impact Point & CEP -->
        <div class="telem-box" style="border-color:rgba(255,42,84,0.4);">
          <div class="telem-lbl">Projected Ground Impact & CEP</div>
          <div class="mono" style="font-size:11px; color:var(--text-primary); margin-top:3px;" id="telem-cep">
            IMPACT: E -120m, N +85m | CEP Radius: 4.2m
          </div>
        </div>
      </div>
    </div>

    <!-- ZONE E: FLOATING AUTONOMOUS KILL-CHAIN DOCK -->
    <div id="zone-e-dock" class="hud-pod">
      <div class="fiducial-tl"></div><div class="fiducial-tr"></div><div class="fiducial-bl"></div><div class="fiducial-br"></div>
      
      <!-- 6-Stage Kill-Chain Stepper -->
      <div class="killchain-stepper">
        <div class="kc-step" id="kc-1"><span class="kc-dot"></span>DETECT</div>
        <span class="kc-arrow">&rarr;</span>
        <div class="kc-step" id="kc-2"><span class="kc-dot"></span>TRACK</div>
        <span class="kc-arrow">&rarr;</span>
        <div class="kc-step" id="kc-3"><span class="kc-dot"></span>IDENTIFY</div>
        <span class="kc-arrow">&rarr;</span>
        <div class="kc-step" id="kc-4"><span class="kc-dot"></span>CUE_EFFECTOR</div>
        <span class="kc-arrow">&rarr;</span>
        <div class="kc-step active" id="kc-5"><span class="kc-dot"></span>ENGAGE</div>
        <span class="kc-arrow">&rarr;</span>
        <div class="kc-step" id="kc-6"><span class="kc-dot"></span>ASSESS_BDA</div>
      </div>

      <!-- Effector Action Grid (Hotkeys [1] [2] [3] [4] + Ceasefire) -->
      <div class="effector-grid">
        <div class="effector-btn" id="eff-jam" onclick="fireEffector('RF_JAMMER')">
          <div class="eff-title"><span>[1] DIR RF JAMMER</span><span class="mono" style="color:var(--suspect-amber);">60°</span></div>
          <div class="eff-sub">2.4G / 5.8G C2 Link Disrupt</div>
          <div class="eff-status" id="st-jam">READY</div>
        </div>

        <div class="effector-btn" id="eff-spoof" onclick="fireEffector('GPS_SPOOF')">
          <div class="eff-title"><span>[2] GNSS SPOOFER</span><span class="mono" style="color:var(--friendly-cyan);">L1/L2</span></div>
          <div class="eff-sub">Synthesized Divert Orbit</div>
          <div class="eff-status" id="st-spoof">READY</div>
        </div>

        <div class="effector-btn" id="eff-dazzler" onclick="fireEffector('OPTICAL_DAZZLER')">
          <div class="eff-title"><span>[3] OPTICAL DAZZLER</span><span class="mono">532nm</span></div>
          <div class="eff-sub">Sensor Saturation (LOS)</div>
          <div class="eff-status" id="st-dazzler">READY</div>
        </div>

        <div class="effector-btn" id="eff-kinetic" onclick="fireEffector('KINETIC_INTERCEPT')">
          <div class="eff-title"><span>[4] KINETIC LAUNCH</span><span class="mono" style="color:var(--hostile-crimson);">P_k .95</span></div>
          <div class="eff-sub">Autonomous Interceptor</div>
          <div class="eff-status" id="st-kinetic">ARMED</div>
        </div>

        <button class="ceasefire-pod-btn" onclick="fireCeasefire()">
          <span style="font-size:12px;">CEASEFIRE</span>
          <span class="mono" style="font-size:8px; opacity:0.8;">[SPACEBAR]</span>
        </button>
      </div>

      <!-- Live Cryptographic SHA-256 Ledger Strip -->
      <div class="audit-strip mono">
        <span style="color:var(--nominal-emerald); font-weight:700;">SHA-256 LEDGER:</span>
        <div class="audit-ticker" id="audit-ticker-txt">#8f3a...9c12 [GENESIS] Initialized root defense policy | #4b12...ef89 [IMM-UKF] 3D track correlated.</div>
        <span id="audit-count-badge" class="badge badge-cyan">42 BLOCKS</span>
      </div>
    </div>

    <!-- HINT TOOLTIP -->
    <div class="controls-hint mono">
      DRAG: PAN | WHEEL: ZOOM (200m-5000m) | SHIFT+DRAG: 3D TILT | HOTKEYS: [1]-[4] EFFECTORS, [SPACE] CEASEFIRE, [V] 3D/2D
    </div>

  </div>

  <script>
    // --- 1. SPATIAL CAMERA & BATTLESPACE ENGINE ---
    const bCanvas = document.getElementById('battlespace-canvas');
    const bCtx = bCanvas.getContext('2d');
    const tetherSvg = document.getElementById('tether-svg');
    const leaderPath = document.getElementById('leader-path');
    const leaderDotTgt = document.getElementById('leader-dot-tgt');
    const leaderDotCard = document.getElementById('leader-dot-card');

    let camera = {
      yaw: 0.58,          // ~33 degrees azimuth rotation
      pitch: 0.78,        // ~45 degrees isometric tilt (0 in 2D Planar)
      targetPitch: 0.78,
      targetYaw: 0.58,
      zoom: 1.0,          // Range multiplier
      panX: 0,
      panY: 0,
      mode: '3D_ISOMETRIC'
    };

    let isDragging = false;
    let isRightDragging = false;
    let dragStartX = 0, dragStartY = 0;
    let selectedTrackId = 101;
    let audioEnabled = true;
    let autoEngage = true;
    let radarSweepRad = 0;
    let activeEffector = null;
    let effectorEndTime = 0;

    // Resize Full-Bleed
    function resizeCanvas() {
      bCanvas.width = window.innerWidth;
      bCanvas.height = window.innerHeight;
    }
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    // Mouse Interactions for 3D Camera Pan, Tilt, and Zoom
    bCanvas.addEventListener('mousedown', (e) => {
      isDragging = true;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
      if (e.button === 2 || e.shiftKey) {
        isRightDragging = true;
      }
    });

    window.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const dx = e.clientX - dragStartX;
      const dy = e.clientY - dragStartY;
      dragStartX = e.clientX;
      dragStartY = e.clientY;

      if (isRightDragging || (e.buttons === 2) || e.shiftKey) {
        // Tilt and Rotate
        camera.targetPitch = Math.max(0.0, Math.min(1.15, camera.targetPitch - dy * 0.005));
        camera.targetYaw += dx * 0.006;
      } else {
        // Pan
        camera.panX += dx;
        camera.panY += dy;
      }
    });

    window.addEventListener('mouseup', () => {
      isDragging = false;
      isRightDragging = false;
    });

    bCanvas.addEventListener('contextmenu', (e) => e.preventDefault());

    bCanvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY > 0 ? 0.90 : 1.11;
      camera.zoom = Math.max(0.35, Math.min(3.8, camera.zoom * zoomFactor));
    }, { passive: false });

    // 3D Projection Matrix to Screen Coordinates
    function project3D(E, N, U, w, h) {
      const cx = w / 2 + camera.panX;
      const cy = h / 2 + camera.panY;
      const baseScale = (Math.min(w, h) / 7200) * camera.zoom;

      const effYaw = (camera.mode === '2D_PLANAR') ? 0 : camera.yaw;
      const effPitch = (camera.mode === '2D_PLANAR') ? 0 : camera.pitch;

      const rotX = E * Math.cos(effYaw) - N * Math.sin(effYaw);
      const rotY = E * Math.sin(effYaw) + N * Math.cos(effYaw);

      const sx = cx + rotX * baseScale;
      const sy = cy - (rotY * Math.cos(effPitch) + U * Math.sin(effPitch)) * baseScale;
      return { x: sx, y: sy };
    }

    // --- 2. 8-DRONE MULTI-TARGET SWARM STATE ---
    let swarmTracks = [
      { id: 101, class: "SUICIDE FPV", enu: [-180, 420, 160], vel: [12, -24, -14], tti: 3.8, threat: 94.2, level: "CRITICAL", proto: "ELRS 900MHz", rpm: 24000, history: [] },
      { id: 102, class: "SUICIDE FPV", enu: [340, 480, 210], vel: [-16, -22, -12], tti: 5.6, threat: 91.5, level: "HIGH", proto: "OcuSync-3", rpm: 23500, history: [] },
      { id: 103, class: "RECON QUAD", enu: [-480, 780, 360], vel: [5, -8, -2], tti: 14.8, threat: 64.0, level: "ELEVATED", proto: "TBS Crossfire", rpm: 14500, history: [] },
      { id: 104, class: "CIVILIAN FLYBY", enu: [620, 310, 95], vel: [-7, 3, 0], tti: 99.0, threat: 14.5, level: "SAFE", proto: "WiFi 2.4GHz", rpm: 8800, history: [] },
      { id: 105, class: "SUICIDE FPV", enu: [-90, 280, 120], vel: [8, -28, -16], tti: 2.9, threat: 96.0, level: "CRITICAL", proto: "ELRS 2.4GHz", rpm: 25000, history: [] },
      { id: 106, class: "DECOY DRONE", enu: [520, 650, 280], vel: [-18, -12, -4], tti: 18.2, threat: 52.0, level: "ELEVATED", proto: "Dark / RF-Silent", rpm: 16000, history: [] },
      { id: 107, class: "RECON SPOTTER", enu: [150, 950, 420], vel: [-3, -6, -1], tti: 28.0, threat: 58.5, level: "ELEVATED", proto: "MAVLink 915MHz", rpm: 13000, history: [] },
      { id: 108, class: "AUTONOMOUS MUNITION", enu: [260, 380, 190], vel: [-15, -26, -18], tti: 3.4, threat: 98.2, level: "CRITICAL", proto: "Optical Nav (Dark)", rpm: 24500, history: [] }
    ];

    let blueInterceptors = [];

    // --- 3. WEB AUDIO API SYNTHESIZER ---
    let audioCtx = null;
    function initAudio() {
      if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
    }
    function playBeep(freq, duration, type='sine', gainVal=0.08) {
      if (!audioEnabled) return;
      try {
        initAudio();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = type;
        osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
        gain.gain.setValueAtTime(gainVal, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + duration);
      } catch(e) {}
    }
    function playLockChime() {
      playBeep(1800, 0.08, 'sine', 0.1);
      setTimeout(() => playBeep(2400, 0.12, 'sine', 0.1), 90);
    }
    function playRadarTick() {
      playBeep(880, 0.03, 'triangle', 0.02);
    }
    function playCautionAlarm() {
      playBeep(650, 0.15, 'sawtooth', 0.12);
    }

    // --- 4. RENDER 3D SPATIAL BATTLESPACE ---
    function renderBattlespaceOS() {
      const w = bCanvas.width, h = bCanvas.height;

      // Smooth camera interpolation
      camera.pitch += (camera.targetPitch - camera.pitch) * 0.12;
      camera.yaw += (camera.targetYaw - camera.yaw) * 0.12;

      // 1. Deep Void Canvas
      bCtx.fillStyle = '#04070B';
      bCtx.fillRect(0, 0, w, h);

      // 2. Isometric Ground Topographic Meter Grid
      bCtx.lineWidth = 1;
      const gridSize = 500;
      const gridExtent = 4000;
      bCtx.strokeStyle = 'rgba(15, 23, 42, 0.7)';
      for (let x = -gridExtent; x <= gridExtent; x += gridSize) {
        const p1 = project3D(x, -gridExtent, 0, w, h);
        const p2 = project3D(x, gridExtent, 0, w, h);
        bCtx.beginPath();
        bCtx.moveTo(p1.x, p1.y);
        bCtx.lineTo(p2.x, p2.y);
        bCtx.stroke();
      }
      for (let y = -gridExtent; y <= gridExtent; y += gridSize) {
        const p1 = project3D(-gridExtent, y, 0, w, h);
        const p2 = project3D(gridExtent, y, 0, w, h);
        bCtx.beginPath();
        bCtx.moveTo(p1.x, p1.y);
        bCtx.lineTo(p2.x, p2.y);
        bCtx.stroke();
      }

      // 3. Geodesic Defense Domes (Ground Rings + 3D Arches)
      const domes = [
        { r: 500, col: 'rgba(255, 42, 84, 0.65)', label: '500m CRIMSON KILLZONE' },
        { r: 1500, col: 'rgba(255, 176, 0, 0.50)', label: '1500m AMBER WARNING' },
        { r: 3500, col: 'rgba(0, 240, 255, 0.40)', label: '3500m CYAN DETECTION' }
      ];

      for (const d of domes) {
        // Ground circle
        bCtx.strokeStyle = d.col;
        bCtx.lineWidth = 1.2;
        bCtx.beginPath();
        const steps = 64;
        for (let i = 0; i <= steps; i++) {
          const ang = (i / steps) * Math.PI * 2;
          const gx = Math.cos(ang) * d.r;
          const gy = Math.sin(ang) * d.r;
          const pt = project3D(gx, gy, 0, w, h);
          if (i === 0) bCtx.moveTo(pt.x, pt.y); else bCtx.lineTo(pt.x, pt.y);
        }
        bCtx.stroke();

        // 3D Geodesic Hemispherical Arches (when in 3D mode)
        if (camera.mode === '3D_ISOMETRIC' && camera.pitch > 0.15) {
          bCtx.strokeStyle = d.col.replace(/[\d\.]+\)$/, '0.18)');
          bCtx.lineWidth = 1;
          for (const az of [0, Math.PI / 4, Math.PI / 2, 3 * Math.PI / 4]) {
            bCtx.beginPath();
            for (let j = 0; j <= 32; j++) {
              const el = (j / 32) * Math.PI;
              const ax = Math.cos(az) * Math.cos(el) * d.r;
              const ay = Math.sin(az) * Math.cos(el) * d.r;
              const az_u = Math.sin(el) * d.r;
              const pt = project3D(ax, ay, az_u, w, h);
              if (j === 0) bCtx.moveTo(pt.x, pt.y); else bCtx.lineTo(pt.x, pt.y);
            }
            bCtx.stroke();
          }
        }

        // Perimeter Label
        const lblPt = project3D(0, d.r, 0, w, h);
        bCtx.fillStyle = d.col;
        bCtx.font = '10px JetBrains Mono';
        bCtx.fillText(d.label, lblPt.x + 8, lblPt.y - 4);
      }

      // 4. Rotating AESA Radar Phased Array Sweep
      radarSweepRad = (radarSweepRad + 0.035) % (Math.PI * 2);
      const sweepMaxR = 3500;
      const sweepX = Math.cos(radarSweepRad) * sweepMaxR;
      const sweepY = Math.sin(radarSweepRad) * sweepMaxR;
      const basePt = project3D(0, 0, 0, w, h);
      const sweepPt = project3D(sweepX, sweepY, 0, w, h);

      bCtx.strokeStyle = 'rgba(0, 240, 255, 0.55)';
      bCtx.lineWidth = 1.5;
      bCtx.beginPath();
      bCtx.moveTo(basePt.x, basePt.y);
      bCtx.lineTo(sweepPt.x, sweepPt.y);
      bCtx.stroke();

      // Base HQ Citadel Mark at Center
      bCtx.fillStyle = '#00F0FF';
      bCtx.fillRect(basePt.x - 5, basePt.y - 5, 10, 10);
      bCtx.strokeStyle = '#FFFFFF';
      bCtx.strokeRect(basePt.x - 7, basePt.y - 7, 14, 14);
      bCtx.font = '10px JetBrains Mono';
      bCtx.fillText("BASE HQ // 37.7749° N, 122.4194° W", basePt.x + 12, basePt.y + 4);

      // 5. Volumetric Sensor & Effector Cones Originating from Base HQ
      const lockedTarget = swarmTracks.find(t => t.id === selectedTrackId);
      if (lockedTarget) {
        const tAir = project3D(lockedTarget.enu[0], lockedTarget.enu[1], lockedTarget.enu[2], w, h);

        // Volumetric EO/IR Viewing Frustum (Translucent Cyan Pyramidal Cone)
        bCtx.fillStyle = 'rgba(0, 240, 255, 0.06)';
        bCtx.strokeStyle = 'rgba(0, 240, 255, 0.35)';
        bCtx.lineWidth = 1;
        bCtx.beginPath();
        bCtx.moveTo(basePt.x, basePt.y);
        bCtx.lineTo(tAir.x - 35, tAir.y - 25);
        bCtx.lineTo(tAir.x + 35, tAir.y - 25);
        bCtx.closePath();
        bCtx.fill();
        bCtx.stroke();

        bCtx.beginPath();
        bCtx.moveTo(basePt.x, basePt.y);
        bCtx.lineTo(tAir.x + 35, tAir.y + 25);
        bCtx.lineTo(tAir.x - 35, tAir.y + 25);
        bCtx.closePath();
        bCtx.fill();
        bCtx.stroke();

        // Directional RF Jammer Saturation Cone (When active)
        if (activeEffector === 'RF_JAMMER' && Date.now() < effectorEndTime) {
          bCtx.fillStyle = 'rgba(255, 176, 0, 0.15)';
          bCtx.strokeStyle = 'rgba(255, 176, 0, 0.7)';
          bCtx.beginPath();
          bCtx.moveTo(basePt.x, basePt.y);
          const jamAng = Math.atan2(lockedTarget.enu[1], lockedTarget.enu[0]);
          const coneL = 2200;
          const pCone1 = project3D(Math.cos(jamAng - 0.52) * coneL, Math.sin(jamAng - 0.52) * coneL, 0, w, h);
          const pCone2 = project3D(Math.cos(jamAng + 0.52) * coneL, Math.sin(jamAng + 0.52) * coneL, 0, w, h);
          bCtx.lineTo(pCone1.x, pCone1.y);
          bCtx.lineTo(pCone2.x, pCone2.y);
          bCtx.closePath();
          bCtx.fill();
          bCtx.stroke();
        }

        // Optical Dazzler Laser Line
        if (activeEffector === 'OPTICAL_DAZZLER' && Date.now() < effectorEndTime) {
          bCtx.strokeStyle = '#10B981';
          bCtx.lineWidth = 3;
          bCtx.shadowColor = '#10B981';
          bCtx.shadowBlur = 12;
          bCtx.beginPath();
          bCtx.moveTo(basePt.x, basePt.y);
          bCtx.lineTo(tAir.x, tAir.y);
          bCtx.stroke();
          bCtx.shadowBlur = 0;
        }
      }

      // 6. Render Swarm Aerial Tracks with 3D Elevation Stalks & IMM-UKF Trajectories
      let lowestTTI = 999;
      for (const trk of swarmTracks) {
        // Physics update
        trk.enu[0] += trk.vel[0] * 0.04;
        trk.enu[1] += trk.vel[1] * 0.04;
        trk.enu[2] += trk.vel[2] * 0.04;
        if (trk.enu[2] < 30) trk.enu[2] = 30; // Min AGL

        // Record history trail
        if (!trk.history) trk.history = [];
        if (Math.random() < 0.25) {
          trk.history.push([...trk.enu]);
          if (trk.history.length > 25) trk.history.shift();
        }

        const dist = Math.hypot(trk.enu[0], trk.enu[1], trk.enu[2]);
        trk.tti = Math.max(0.5, (dist / Math.max(12, Math.hypot(...trk.vel)))).toFixed(1);
        if (trk.tti < lowestTTI) lowestTTI = trk.tti;

        const isLocked = (trk.id === selectedTrackId);
        const col = (trk.level === 'CRITICAL') ? '#FF2A54' : (trk.level === 'HIGH' ? '#FF6B00' : (trk.level === 'ELEVATED' ? '#FFB000' : '#10B981'));

        const pAir = project3D(trk.enu[0], trk.enu[1], trk.enu[2], w, h);
        const pGnd = project3D(trk.enu[0], trk.enu[1], 0, w, h);

        // A. 3D Vertical Elevation Stalk (Drop-Line)
        bCtx.strokeStyle = 'rgba(148, 163, 184, 0.45)';
        bCtx.setLineDash([3, 3]);
        bCtx.lineWidth = 1;
        bCtx.beginPath();
        bCtx.moveTo(pAir.x, pAir.y);
        bCtx.lineTo(pGnd.x, pGnd.y);
        bCtx.stroke();
        bCtx.setLineDash([]);

        // Ground shadow footprint ellipse
        bCtx.strokeStyle = col;
        bCtx.fillStyle = col.replace(/#/, 'rgba(') + ', 0.15)';
        bCtx.beginPath();
        bCtx.ellipse(pGnd.x, pGnd.y, 8, 4, 0, 0, Math.PI * 2);
        bCtx.fill();
        bCtx.stroke();

        // B. Translucent Historical Flight Curtain
        if (trk.history.length > 1) {
          bCtx.fillStyle = 'rgba(255, 176, 0, 0.08)';
          bCtx.strokeStyle = 'rgba(255, 176, 0, 0.35)';
          bCtx.beginPath();
          for (let k = 0; k < trk.history.length; k++) {
            const hPt = project3D(trk.history[k][0], trk.history[k][1], trk.history[k][2], w, h);
            if (k === 0) bCtx.moveTo(hPt.x, hPt.y); else bCtx.lineTo(hPt.x, hPt.y);
          }
          bCtx.stroke();
        }

        // C. Forward 3D IMM-UKF Predicted Trajectory Tube & Uncertainty Ellipse
        if (isLocked) {
          bCtx.strokeStyle = '#00F0FF';
          bCtx.lineWidth = 2;
          bCtx.beginPath();
          let prevPred = pAir;
          for (let s = 1; s <= 15; s++) {
            const predE = trk.enu[0] + trk.vel[0] * (s * 0.4);
            const predN = trk.enu[1] + trk.vel[1] * (s * 0.4);
            const predU = Math.max(0, trk.enu[2] + trk.vel[2] * (s * 0.4));
            const predPt = project3D(predE, predN, predU, w, h);
            bCtx.moveTo(prevPred.x, prevPred.y);
            bCtx.lineTo(predPt.x, predPt.y);
            prevPred = predPt;

            // 95% Covariance Uncertainty Ellipse at forward intervals
            if (s % 5 === 0) {
              bCtx.ellipse(predPt.x, predPt.y, s * 1.5, s * 0.9, 0, 0, Math.PI * 2);
            }
          }
          bCtx.stroke();

          // Update SVG Leader Tether Line to Zone D Dossier
          updateTetherLeader(pAir.x, pAir.y);
        }

        // D. 3D Airframe NATO MIL-STD-2525D Symbology (Diamond / Circle)
        bCtx.strokeStyle = col;
        bCtx.lineWidth = isLocked ? 2.5 : 1.5;
        bCtx.beginPath();
        // Hostile Diamond
        bCtx.moveTo(pAir.x, pAir.y - 8);
        bCtx.lineTo(pAir.x + 8, pAir.y);
        bCtx.lineTo(pAir.x, pAir.y + 8);
        bCtx.lineTo(pAir.x - 8, pAir.y);
        bCtx.closePath();
        bCtx.stroke();

        if (isLocked) {
          bCtx.strokeStyle = '#00F0FF';
          bCtx.strokeRect(pAir.x - 12, pAir.y - 12, 24, 24);
        }

        // Callout Tag
        bCtx.fillStyle = '#F8FAFC';
        bCtx.font = '10px JetBrains Mono';
        bCtx.fillText(`TRK-${trk.id} [${trk.class.split(' ')[0]}]`, pAir.x + 12, pAir.y - 4);
        bCtx.fillStyle = col;
        bCtx.fillText(`ALT: ${Math.round(trk.enu[2])}m | TTI ${trk.tti}s`, pAir.x + 12, pAir.y + 8);
      }

      // 7. Render Friendly Blue Kinetic Interceptors
      for (let bIdx = blueInterceptors.length - 1; bIdx >= 0; bIdx--) {
        const b = blueInterceptors[bIdx];
        b.progress += 0.05;
        const bAir = project3D(b.x, b.y, b.z, w, h);
        bCtx.fillStyle = '#00F0FF';
        bCtx.fillRect(bAir.x - 4, bAir.y - 4, 8, 8);
        bCtx.font = '9px JetBrains Mono';
        bCtx.fillText("BLUE-INT-ALPHA", bAir.x + 8, bAir.y + 3);

        // Move towards target
        b.x += (b.targetEnu[0] - b.x) * 0.12;
        b.y += (b.targetEnu[1] - b.y) * 0.12;
        b.z += (b.targetEnu[2] - b.z) * 0.12;

        if (b.progress >= 1.0 || Math.hypot(b.targetEnu[0] - b.x, b.targetEnu[1] - b.y) < 15) {
          // SPLASH CONFIRMED BDA
          bCtx.strokeStyle = '#FF2A54';
          bCtx.lineWidth = 3;
          bCtx.beginPath();
          bCtx.arc(bAir.x, bAir.y, 25, 0, Math.PI * 2);
          bCtx.stroke();
          appendAuditLedger(`BDA: SPLASH CONFIRMED on TRK #${b.targetId}`);
          blueInterceptors.splice(bIdx, 1);
        }
      }

      requestAnimationFrame(renderBattlespaceOS);
    }

    // --- 5. DYNAMIC LEADER TETHER TO ZONE D ---
    function updateTetherLeader(tx, ty) {
      const zoneDPod = document.getElementById('zone-d-pod');
      if (!zoneDPod) return;
      const rect = zoneDPod.getBoundingClientRect();
      const cardX = rect.left;
      const cardY = rect.top + 36;

      const midX = tx + (cardX - tx) * 0.55;
      const pathD = `M ${tx} ${ty} L ${midX} ${ty} L ${midX} ${cardY} L ${cardX} ${cardY}`;
      leaderPath.setAttribute('d', pathD);
      leaderDotTgt.setAttribute('cx', tx);
      leaderDotTgt.setAttribute('cy', ty);
      leaderDotCard.setAttribute('cx', cardX);
      leaderDotCard.setAttribute('cy', cardY);
    }

    // --- 6. OPTRONIC EO/IR GIMBAL VIEWPORT (ZONE B) ---
    const optCanvas = document.getElementById('optronic-canvas');
    const optCtx = optCanvas.getContext('2d');
    const pipCanvas = document.getElementById('pip-canvas');
    const pipCtx = pipCanvas.getContext('2d');
    let currentShaderMode = 'EO_DAYLIGHT';

    function renderOptronicViewport() {
      const w = optCanvas.width, h = optCanvas.height;
      const locked = swarmTracks.find(t => t.id === selectedTrackId) || swarmTracks[0];

      // Shader Background
      if (currentShaderMode === 'EO_DAYLIGHT') {
        const grad = optCtx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, '#0a101d');
        grad.addColorStop(0.68, '#182436');
        grad.addColorStop(1, '#0e1726');
        optCtx.fillStyle = grad;
        optCtx.fillRect(0, 0, w, h);
      } else if (currentShaderMode === 'FLIR_WHITE_HOT') {
        optCtx.fillStyle = '#0d1117';
        optCtx.fillRect(0, 0, w, h);
      } else if (currentShaderMode === 'FLIR_BLACK_HOT') {
        optCtx.fillStyle = '#b8c0cc';
        optCtx.fillRect(0, 0, w, h);
      } else { // SWIR Night Vision
        optCtx.fillStyle = '#04180d';
        optCtx.fillRect(0, 0, w, h);
      }

      // Artificial Horizon & Roll/Pitch Ladder
      const cx = w / 2, cy = h / 2;
      optCtx.strokeStyle = (currentShaderMode === 'FLIR_BLACK_HOT') ? '#1e293b' : 'rgba(0, 240, 255, 0.4)';
      optCtx.lineWidth = 1;
      optCtx.beginPath();
      optCtx.moveTo(cx - 50, cy); optCtx.lineTo(cx - 15, cy);
      optCtx.moveTo(cx + 15, cy); optCtx.lineTo(cx + 50, cy);
      optCtx.stroke();

      // Pitch rungs
      optCtx.beginPath();
      optCtx.moveTo(cx - 30, cy - 25); optCtx.lineTo(cx + 30, cy - 25);
      optCtx.moveTo(cx - 30, cy + 25); optCtx.lineTo(cx + 30, cy + 25);
      optCtx.stroke();

      // Heading tape
      optCtx.strokeRect(cx - 60, 10, 120, 16);
      optCtx.fillStyle = (currentShaderMode === 'FLIR_BLACK_HOT') ? '#000' : '#00F0FF';
      optCtx.font = '10px JetBrains Mono';
      optCtx.fillText("048° NNE // EL +14°", cx - 48, 22);

      // Render Targeted UAV in Gimbal Viewport
      const uavColor = (currentShaderMode === 'FLIR_WHITE_HOT') ? '#FFFFFF' : (currentShaderMode === 'FLIR_BLACK_HOT' ? '#000000' : (currentShaderMode === 'SWIR_NIGHT_VISION' ? '#10B981' : '#F8FAFC'));
      optCtx.fillStyle = uavColor;
      optCtx.beginPath();
      optCtx.arc(cx, cy, 6, 0, Math.PI * 2);
      optCtx.fill();

      // Quad arms & blurred rotors
      optCtx.strokeStyle = uavColor;
      optCtx.lineWidth = 2;
      optCtx.beginPath();
      optCtx.moveTo(cx - 18, cy - 10); optCtx.lineTo(cx + 18, cy + 10);
      optCtx.moveTo(cx - 18, cy + 10); optCtx.lineTo(cx + 18, cy - 10);
      optCtx.stroke();

      // Precision Corner Brackets
      const bw = 38, bh = 32;
      optCtx.strokeStyle = '#FF2A54';
      optCtx.lineWidth = 1.5;
      optCtx.beginPath();
      optCtx.moveTo(cx - bw, cy - bh + 8); optCtx.lineTo(cx - bw, cy - bh); optCtx.lineTo(cx - bw + 8, cy - bh);
      optCtx.moveTo(cx + bw - 8, cy - bh); optCtx.lineTo(cx + bw, cy - bh); optCtx.lineTo(cx + bw, cy - bh + 8);
      optCtx.moveTo(cx - bw, cy + bh - 8); optCtx.lineTo(cx - bw, cy + bh); optCtx.lineTo(cx - bw + 8, cy + bh);
      optCtx.moveTo(cx + bw - 8, cy + bh); optCtx.lineTo(cx + bw, cy + bh); optCtx.lineTo(cx + bw, cy + bh - 8);
      optCtx.stroke();

      // Lead-computing pipper
      optCtx.strokeStyle = '#00F0FF';
      optCtx.beginPath();
      optCtx.arc(cx + 16, cy - 12, 10, 0, Math.PI * 2);
      optCtx.moveTo(cx + 16 - 5, cy - 12); optCtx.lineTo(cx + 16 + 5, cy - 12);
      optCtx.moveTo(cx + 16, cy - 12 - 5); optCtx.lineTo(cx + 16, cy - 12 + 5);
      optCtx.stroke();

      // Telemetry tags
      optCtx.fillStyle = '#00F0FF';
      optCtx.font = '10px JetBrains Mono';
      optCtx.fillText(`TRK-${locked.id} [${locked.class.split(' ')[0]}]`, cx - bw, cy - bh - 6);
      optCtx.fillStyle = '#FF2A54';
      optCtx.fillText(`TTI: ${locked.tti}s | RNG: ${Math.round(Math.hypot(...locked.enu))}m`, cx - bw, cy + bh + 14);

      // Render PiP Loupe (Zoom on payload)
      pipCtx.fillStyle = (currentShaderMode === 'FLIR_BLACK_HOT') ? '#b8c0cc' : '#0B101B';
      pipCtx.fillRect(0, 0, pipCanvas.width, pipCanvas.height);
      const pcx = pipCanvas.width / 2, pcy = pipCanvas.height / 2;
      pipCtx.fillStyle = (currentShaderMode === 'FLIR_WHITE_HOT') ? '#FFFFFF' : '#CBD5E1';
      pipCtx.beginPath();
      pipCtx.arc(pcx, pcy - 8, 14, 0, Math.PI * 2);
      pipCtx.fill();
      // Payload munition cylinder
      pipCtx.fillStyle = '#FF2A54';
      pipCtx.fillRect(pcx - 8, pcy + 6, 16, 20);
      pipCtx.fillStyle = '#00F0FF';
      pipCtx.font = '8px JetBrains Mono';
      pipCtx.fillText("SHAPED CHG", 4, pipCanvas.height - 4);

      requestAnimationFrame(renderOptronicViewport);
    }

    // --- 7. DUAL SPECTROGRAMS (ZONE D) ---
    const rfSpecCanvas = document.getElementById('rf-spec-canvas');
    const rfCtx = rfSpecCanvas.getContext('2d');
    const dopSpecCanvas = document.getElementById('dop-spec-canvas');
    const dopCtx = dopSpecCanvas.getContext('2d');

    function renderSpectrograms() {
      // 128-bin RF PSD slice
      const rw = rfSpecCanvas.width, rh = rfSpecCanvas.height;
      rfCtx.fillStyle = '#020408';
      rfCtx.fillRect(0, 0, rw, rh);
      rfCtx.strokeStyle = '#FFB000';
      rfCtx.lineWidth = 1;
      rfCtx.beginPath();
      for (let i = 0; i < 128; i++) {
        const x = (i / 128) * rw;
        const db = Math.sin(i * 0.1) * 12 + Math.random() * 8 + (i > 50 && i < 75 ? 40 : 8);
        const y = rh - (db / 65) * rh;
        if (i === 0) rfCtx.moveTo(x, y); else rfCtx.lineTo(x, y);
      }
      rfCtx.stroke();

      // Micro-Doppler Rotor Blade Harmonics Spectrogram
      const dw = dopSpecCanvas.width, dh = dopSpecCanvas.height;
      dopCtx.fillStyle = '#020408';
      dopCtx.fillRect(0, 0, dw, dh);
      dopCtx.strokeStyle = '#10B981';
      dopCtx.lineWidth = 1.2;
      dopCtx.beginPath();
      for (let j = 0; j < 64; j++) {
        const x = (j / 64) * dw;
        const d_amp = (Math.abs(j - 32) < 4 ? 38 : (Math.abs(j - 32) === 12 ? 24 : Math.random() * 6));
        const y = dh - (d_amp / 45) * dh;
        if (j === 0) dopCtx.moveTo(x, y); else dopCtx.lineTo(x, y);
      }
      dopCtx.stroke();

      setTimeout(renderSpectrograms, 100);
    }

    // --- 8. UI INTERACTIONS & TABLE POPULATION ---
    function populateTrackMatrix() {
      const tbody = document.getElementById('track-matrix-tbody');
      tbody.innerHTML = '';
      for (const t of swarmTracks) {
        const tr = document.createElement('tr');
        if (t.id === selectedTrackId) tr.className = 'locked';
        tr.onclick = () => selectTrack(t.id);

        const bCol = (t.level === 'CRITICAL') ? 'badge-crimson' : (t.level === 'HIGH' ? 'badge-amber' : 'badge-emerald');
        const dist = Math.round(Math.hypot(...t.enu));
        const speed = Math.round(Math.hypot(...t.vel));
        const ttiNum = parseFloat(t.tti);

        tr.innerHTML = `
          <td class="mono">#${t.id}</td>
          <td><span class="badge ${bCol}">${t.class.split(' ')[0]}</span></td>
          <td class="mono">${dist}m</td>
          <td class="mono">${speed}m/s</td>
          <td class="mono" style="color:${ttiNum < 6 ? 'var(--hostile-crimson)' : 'inherit'}; font-weight:700;">
            ${t.tti}s
            <div class="tti-bar-wrap"><div class="tti-bar-fill" style="width:${Math.max(8, Math.min(100, (1 - ttiNum/30)*100))}%;"></div></div>
          </td>
          <td><span class="badge badge-cyan">RAD+RF</span></td>
          <td><button class="pill-btn" style="padding:2px 6px; font-size:9px;" onclick="selectTrack(${t.id})">LOCK</button></td>
        `;
        tbody.appendChild(tr);
      }
    }

    function selectTrack(id) {
      selectedTrackId = id;
      const t = swarmTracks.find(item => item.id === id);
      if (t) {
        document.getElementById('dos-track-id').innerText = `TRK #${t.id}-ALPHA`;
        document.getElementById('dos-class-label').innerText = t.class;
        document.getElementById('dos-severity-badge').innerText = `${t.level} (${t.threat})`;
        document.getElementById('dial-score-num').innerText = Math.round(t.threat);
        document.getElementById('telem-dist').innerText = `${Math.round(Math.hypot(...t.enu))} m`;
        document.getElementById('telem-tti').innerText = `${t.tti} s`;
        document.getElementById('telem-vel').innerText = `${Math.round(Math.hypot(...t.vel))} m/s`;
        document.getElementById('telem-alt').innerText = `${Math.round(t.enu[2])} m`;
        document.getElementById('telem-cep').innerText = `IMPACT: E ${Math.round(t.enu[0] + t.vel[0]*t.tti)}m, N ${Math.round(t.enu[1] + t.vel[1]*t.tti)}m | CEP: 3.8m`;
        playLockChime();
      }
      populateTrackMatrix();
    }

    function setViewMode(mode) {
      camera.mode = mode;
      document.getElementById('btn-view-3d').classList.toggle('active', mode === '3D_ISOMETRIC');
      document.getElementById('btn-view-2d').classList.toggle('active', mode === '2D_PLANAR');
      if (mode === '2D_PLANAR') {
        camera.targetPitch = 0.0;
        camera.targetYaw = 0.0;
      } else {
        camera.targetPitch = 0.78;
        camera.targetYaw = 0.58;
      }
    }

    function setShaderMode(mode) {
      currentShaderMode = mode;
      document.getElementById('btn-sh-eo').classList.toggle('active', mode === 'EO_DAYLIGHT');
      document.getElementById('btn-sh-flir-w').classList.toggle('active', mode === 'FLIR_WHITE_HOT');
      document.getElementById('btn-sh-flir-b').classList.toggle('active', mode === 'FLIR_BLACK_HOT');
      document.getElementById('btn-sh-swir').classList.toggle('active', mode === 'SWIR_NIGHT_VISION');
    }

    function toggleAutonomy() {
      autoEngage = !autoEngage;
      const el = document.getElementById('autonomy-txt');
      el.innerText = autoEngage ? "AUTO-ENGAGE" : "MANUAL HITL";
      el.style.color = autoEngage ? "var(--nominal-emerald)" : "var(--suspect-amber)";
      appendAuditLedger(`ROE updated to: ${el.innerText}`);
    }

    function toggleAudioMaster() {
      audioEnabled = !audioEnabled;
      const el = document.getElementById('audio-txt');
      el.innerText = audioEnabled ? "SYNTH ON" : "MUTED";
      el.style.color = audioEnabled ? "var(--friendly-cyan)" : "var(--text-muted)";
    }

    async function switchScenario(scen) {
      try {
        await fetch('/api/v1/scenario', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ scenario: scen })
        });
        appendAuditLedger(`Scenario switched to ${scen}`);
      } catch(e) {}
    }

    async function fireEffector(type) {
      activeEffector = type;
      effectorEndTime = Date.now() + 4000;
      appendAuditLedger(`ENGAGING ${type} against TRK #${selectedTrackId}`);
      playBeep(420, 0.25, 'sawtooth', 0.15);

      if (type === 'KINETIC_INTERCEPT') {
        const t = swarmTracks.find(item => item.id === selectedTrackId);
        if (t) {
          blueInterceptors.push({
            id: Date.now(),
            targetId: t.id,
            x: 0, y: 0, z: 0,
            targetEnu: [...t.enu],
            progress: 0.0
          });
        }
      }

      try {
        await fetch('/api/v1/countermeasures/engage', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ target_id: selectedTrackId, measure_type: type, operator: "COMMANDER_C2" })
        });
      } catch(e) {}
    }

    async function fireCeasefire() {
      activeEffector = null;
      effectorEndTime = 0;
      appendAuditLedger("EMERGENCY CEASEFIRE // ALL EFFECTORS DISENGAGED");
      playBeep(240, 0.4, 'square', 0.2);
      try {
        await fetch('/api/v1/countermeasures/disengage', { method: 'POST' });
      } catch(e) {}
    }

    function appendAuditLedger(text) {
      const ticker = document.getElementById('audit-ticker-txt');
      const hash = '#' + Math.random().toString(16).substring(2, 6) + '...' + Math.random().toString(16).substring(2, 6);
      ticker.innerText = `${hash} [TACTICAL] ${text} | ${ticker.innerText.substring(0, 180)}`;
    }

    // Keyboard Shortcuts
    window.addEventListener('keydown', (e) => {
      if (e.key === '1') fireEffector('RF_JAMMER');
      else if (e.key === '2') fireEffector('GPS_SPOOF');
      else if (e.key === '3') fireEffector('OPTICAL_DAZZLER');
      else if (e.key === '4') fireEffector('KINETIC_INTERCEPT');
      else if (e.code === 'Space') { e.preventDefault(); fireCeasefire(); }
      else if (e.key === 'v' || e.key === 'V') setViewMode(camera.mode === '3D_ISOMETRIC' ? '2D_PLANAR' : '3D_ISOMETRIC');
      else if (e.key === 'm' || e.key === 'M') {
        const modes = ['EO_DAYLIGHT', 'FLIR_WHITE_HOT', 'FLIR_BLACK_HOT', 'SWIR_NIGHT_VISION'];
        const next = modes[(modes.indexOf(currentShaderMode) + 1) % modes.length];
        setShaderMode(next);
      }
      else if (e.key === 'a' || e.key === 'A') toggleAudioMaster();
    });

    // UTC Military Clock
    setInterval(() => {
      const now = new Date();
      document.getElementById('utc-clock').innerText = now.toTimeString().split(' ')[0] + '.' + String(Math.floor(now.getMilliseconds()/100)) + ' UTC';
    }, 100);

    // Initial Boots
    renderBattlespaceOS();
    renderOptronicViewport();
    renderSpectrograms();
    populateTrackMatrix();
    setInterval(populateTrackMatrix, 1000);
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def get_command_center_ui():
    return HTMLResponse(content=LATTICE_SPATIAL_OS_HTML)

@app.get("/command-center", response_class=HTMLResponse)
def get_command_center_alias():
    return HTMLResponse(content=LATTICE_SPATIAL_OS_HTML)

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
