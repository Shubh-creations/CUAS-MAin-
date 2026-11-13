"""
FastAPI REST & WebSocket Command and Control (C2) Server with Web Command Dashboard for CUAS.
Provides a browser-based tactical military Command Center at http://127.0.0.1:8080/
along with REST endpoints and WebSocket telemetry.
"""

from typing import Dict, List, Optional, Any
import time
import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from utils.logger import get_logger
from control_unit.threat_manager import ThreatManager
from control_unit.neutralization import CountermeasureController, CountermeasureType

logger = get_logger("CUAS.API")

app = FastAPI(
    title="CUAS Tactical C2 System",
    version="2.5.0",
    description="Airspace Defense, Drone Tracking, and Countermeasure Command Interface"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

threat_mgr = ThreatManager()
countermeasure_ctrl = CountermeasureController(operator_name="COMMANDER_WEB")

class CountermeasureRequest(BaseModel):
    target_id: int
    measure_type: str
    operator: Optional[str] = "COMMANDER_WEB"
    duration_sec: Optional[float] = 10.0


WEB_COMMAND_CENTER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CUAS Tactical Command Center</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: #030804;
      color: #00ff66;
      font-family: 'Courier New', Courier, monospace;
      padding: 12px;
      user-select: none;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 16px;
      background: #061208;
      border: 1px solid #1f4a25;
      margin-bottom: 12px;
    }
    h1 { font-size: 20px; letter-spacing: 2px; text-shadow: 0 0 8px #00ff66; }
    .defcon {
      font-size: 14px;
      font-weight: bold;
      padding: 4px 12px;
      border: 1px solid #00ff66;
      background: #022208;
    }
    .grid {
      display: grid;
      grid-template-columns: 2fr 1.2fr 1.2fr;
      gap: 12px;
    }
    .panel {
      background: #050d06;
      border: 1px solid #1a3a1f;
      padding: 12px;
      position: relative;
      box-shadow: 0 0 10px rgba(0,255,100,0.05);
    }
    .panel-title {
      font-size: 13px;
      font-weight: bold;
      color: #70ff99;
      border-bottom: 1px solid #1a3a1f;
      padding-bottom: 6px;
      margin-bottom: 10px;
      display: flex;
      justify-content: space-between;
    }
    canvas {
      background: #000;
      border: 1px solid #1a3a1f;
      display: block;
      width: 100%;
      height: auto;
    }
    .meter-bar {
      width: 100%;
      height: 20px;
      background: #091a0c;
      border: 1px solid #00ff66;
      margin-top: 6px;
      position: relative;
    }
    .meter-fill {
      height: 100%;
      width: 82%;
      background: #cc2200;
      transition: width 0.3s;
    }
    .ecm-btn {
      display: block;
      width: 100%;
      padding: 10px;
      margin-bottom: 8px;
      background: #081c0c;
      border: 1px solid #00ff66;
      color: #00ff66;
      font-family: 'Courier New', monospace;
      font-weight: bold;
      font-size: 12px;
      cursor: pointer;
      text-align: left;
      transition: background 0.2s;
    }
    .ecm-btn:hover { background: #003d14; color: #fff; }
    .ecm-btn.jam { border-color: #ffaa00; color: #ffaa00; background: #261700; }
    .ecm-btn.jam:hover { background: #4d2e00; }
    .ecm-btn.spoof { border-color: #00bbff; color: #00bbff; background: #001f33; }
    .ecm-btn.spoof:hover { background: #003d66; }
    .ecm-btn.kinetic { border-color: #ff3333; color: #ff3333; background: #330000; }
    .ecm-btn.kinetic:hover { background: #660000; }
    .status-toast {
      padding: 8px;
      background: #001100;
      border: 1px dashed #00aa44;
      font-size: 11px;
      min-height: 48px;
      line-height: 1.4;
    }
    footer {
      margin-top: 12px;
      background: #061208;
      border: 1px solid #1f4a25;
      padding: 8px 16px;
      display: flex;
      justify-content: space-between;
      font-size: 12px;
    }
  </style>
</head>
<body>

  <header>
    <div>
      <h1>C-UAS TACTICAL COMMAND CENTER</h1>
      <span style="font-size: 11px; color: #88cc99;">AUTONOMOUS AIR DEFENSE & COUNTER-DRONE ENGAGEMENT</span>
    </div>
    <div style="display: flex; gap: 14px; align-items: center;">
      <div id="defcon-badge" class="defcon" style="color: #ff3333; border-color: #ff3333;">DEFCON: 1 [CRITICAL INTRUSION]</div>
      <div id="clock" style="font-size: 13px; font-weight: bold;">--:--:--</div>
    </div>
  </header>

  <div class="grid">
    <!-- Camera Optronics Feed -->
    <div class="panel">
      <div class="panel-title">
        <span>TACTICAL OPTRONIC SENSOR (LIVE CAMERA)</span>
        <span style="color:#ff3333;">● TRACKING LOCKED</span>
      </div>
      <canvas id="camera-canvas" width="640" height="420"></canvas>
      <div style="margin-top: 8px; font-size: 11px; display: flex; justify-content: space-between;">
        <span>SENSOR: ELECTRO-OPTICAL / IR</span>
        <span>RESOLUTION: 1080P / FP16 GPU</span>
        <span>FPS: <strong id="fps-val">30.2</strong></span>
      </div>
    </div>

    <!-- AI Classification & Threat Assessment -->
    <div class="panel">
      <div class="panel-title">AI THREAT CLASSIFICATION</div>
      
      <div style="margin-bottom: 14px; font-size: 12px; line-height: 1.6;">
        <div>TARGET ID: <strong id="tid">#101-ALPHA</strong></div>
        <div>TYPE: <strong style="color: #ff3333;" id="target-type">SUICIDE DRONE (LOITERING)</strong></div>
        <div>CONFIDENCE: <strong id="conf">94.8%</strong></div>
        <div>EST. RANGE: <strong id="dist">420 meters</strong></div>
        <div>BEARING: <strong id="bearing">048° NNE</strong></div>
        <div>ZONE: <strong style="color: #ff2222;" id="zone">RED (INNER KILLZONE)</strong></div>
      </div>

      <div style="font-size: 11px; margin-bottom: 4px;">THREAT SEVERITY INDEX:</div>
      <div class="meter-bar">
        <div id="threat-meter" class="meter-fill"></div>
      </div>
      <div style="font-size: 11px; text-align: right; margin-top: 4px; color: #ff5555;" id="score-text">86.5 / 100 [CRITICAL]</div>

      <div class="panel-title" style="margin-top: 18px;">ELECTRONIC COUNTERMEASURES</div>
      <button class="ecm-btn jam" onclick="engageECM('RF_JAMMER')">⚡ ENGAGE RF JAMMER (2.4/5.8 GHz)</button>
      <button class="ecm-btn spoof" onclick="engageECM('GPS_SPOOF')">🛰️ ACTIVATE GNSS / GPS SPOOFING</button>
      <button class="ecm-btn kinetic" onclick="engageECM('KINETIC_INTERCEPT')">🚀 LAUNCH KINETIC INTERCEPTOR</button>
      <button class="ecm-btn" onclick="disengageAll()">🛑 EMERGENCY DISENGAGE ALL</button>

      <div class="status-toast" id="ecm-status">
        EFFECTORS STANDBY: High-power RF and GNSS spoofing standing by for engagement command.
      </div>
    </div>

    <!-- 3D Radar & Geospatial Map -->
    <div class="panel">
      <div class="panel-title">3D PULSE-DOPPLER RADAR</div>
      <canvas id="radar-canvas" width="300" height="260"></canvas>
      
      <div class="panel-title" style="margin-top: 14px;">DEFENSE GEOFENCE (BASE HQ)</div>
      <div style="font-size: 11px; line-height: 1.5; color: #88cc99;">
        <div>BASE: 37.7749° N, 122.4194° W</div>
        <div>RED ZONE: &lt; 500m (Killzone)</div>
        <div>AMBER ZONE: &lt; 1500m (Warning)</div>
        <div>GREEN ZONE: &lt; 3500m (Early Detection)</div>
      </div>
    </div>
  </div>

  <footer>
    <div>OPERATOR: <strong>COMMANDER_HQ</strong> | ACCESS LEVEL: <strong>DEFCON-1</strong></div>
    <div>ACTIVE TARGETS: <strong id="active-targets">1</strong> | TOTAL INTERCEPTIONS: <strong id="neutralized">0</strong></div>
    <div>SYSTEM: <strong>NVIDIA CUDA ONLINE</strong> | RF SCANNER: <strong>ACTIVE</strong></div>
  </footer>

  <script>
    // Clock
    setInterval(() => {
      const now = new Date();
      document.getElementById('clock').innerText = now.toTimeString().split(' ')[0];
    }, 1000);

    // Simulation Drone State
    let drone = { x: 320, y: 150, vx: 1.8, vy: 0.9, size: 44 };
    let radarSweep = 0;
    let targetHistory = [];

    // Canvas Contexts
    const camCanvas = document.getElementById('camera-canvas');
    const camCtx = camCanvas.getContext('2d');
    const radCanvas = document.getElementById('radar-canvas');
    const radCtx = radCanvas.getContext('2d');

    // Camera Render Loop
    function renderOptronics() {
      const w = camCanvas.width, h = camCanvas.height;

      // Dark Sky gradient
      const grad = camCtx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, '#020603');
      grad.addColorStop(1, '#081a0b');
      camCtx.fillStyle = grad;
      camCtx.fillRect(0, 0, w, h);

      // Grid reticle lines
      camCtx.strokeStyle = 'rgba(0, 100, 0, 0.25)';
      camCtx.lineWidth = 1;
      for (let x = 0; x < w; x += 40) { camCtx.beginPath(); camCtx.moveTo(x, 0); camCtx.lineTo(x, h); camCtx.stroke(); }
      for (let y = 0; y < h; y += 40) { camCtx.beginPath(); camCtx.moveTo(0, y); camCtx.lineTo(w, y); camCtx.stroke(); }

      // Update simulated drone
      drone.x += drone.vx;
      drone.y += drone.vy;
      if (drone.x < 80 || drone.x > w - 80) drone.vx *= -1;
      if (drone.y < 60 || drone.y > h - 100) drone.vy *= -1;

      targetHistory.push({ x: drone.x, y: drone.y });
      if (targetHistory.length > 25) targetHistory.shift();

      // Draw Trajectory Trail
      if (targetHistory.length > 1) {
        camCtx.strokeStyle = '#ffaa00';
        camCtx.lineWidth = 2;
        camCtx.beginPath();
        camCtx.moveTo(targetHistory[0].x, targetHistory[0].y);
        for (let i = 1; i < targetHistory.length; i++) {
          camCtx.lineTo(targetHistory[i].x, targetHistory[i].y);
        }
        camCtx.stroke();
      }

      // Projected Future Trajectory (Kalman extrapolation)
      camCtx.strokeStyle = '#ff3333';
      camCtx.setLineDash([4, 4]);
      camCtx.beginPath();
      camCtx.moveTo(drone.x, drone.y);
      camCtx.lineTo(drone.x + drone.vx * 30, drone.y + drone.vy * 30);
      camCtx.stroke();
      camCtx.setLineDash([]);

      // Draw Synthetic Drone
      camCtx.fillStyle = '#bbb';
      camCtx.beginPath();
      camCtx.arc(drone.x, drone.y, 10, 0, Math.PI * 2);
      camCtx.fill();

      camCtx.strokeStyle = '#666';
      camCtx.lineWidth = 3;
      camCtx.beginPath();
      camCtx.moveTo(drone.x - 22, drone.y - 12);
      camCtx.lineTo(drone.x + 22, drone.y + 12);
      camCtx.moveTo(drone.x - 22, drone.y + 12);
      camCtx.lineTo(drone.x + 22, drone.y - 12);
      camCtx.stroke();

      // Rotors
      camCtx.fillStyle = '#00ff66';
      for (const [rx, ry] of [
        [drone.x - 22, drone.y - 12], [drone.x + 22, drone.y + 12],
        [drone.x - 22, drone.y + 12], [drone.x + 22, drone.y - 12]
      ]) {
        camCtx.beginPath();
        camCtx.arc(rx, ry, 3, 0, Math.PI * 2);
        camCtx.fill();
      }

      // Corner Targeting Brackets
      const bx = drone.x - 30, by = drone.y - 30, bw = 60, bh = 60, bl = 12;
      camCtx.strokeStyle = '#ff2222';
      camCtx.lineWidth = 2;
      camCtx.strokeRect(bx, by, bw, bh);

      // Crosshair
      camCtx.beginPath();
      camCtx.moveTo(drone.x - 16, drone.y); camCtx.lineTo(drone.x + 16, drone.y);
      camCtx.moveTo(drone.x, drone.y - 16); camCtx.lineTo(drone.x, drone.y + 16);
      camCtx.stroke();

      // HUD Text
      camCtx.fillStyle = '#00ff66';
      camCtx.font = '12px Courier New';
      camCtx.fillText(`TGT LOCK: #101-ALPHA [SUICIDE DRONE]`, 14, 24);
      camCtx.fillText(`TTI: 4.2s | VEL: ${(Math.hypot(drone.vx, drone.vy)*15).toFixed(1)} m/s`, 14, 42);

      requestAnimationFrame(renderOptronics);
    }

    // Radar Render Loop
    function renderRadar() {
      const w = radCanvas.width, h = radCanvas.height;
      const cx = w / 2, cy = h / 2, radius = Math.min(cx, cy) - 10;

      radCtx.fillStyle = '#000';
      radCtx.fillRect(0, 0, w, h);

      // Rings
      radCtx.strokeStyle = '#004400';
      radCtx.lineWidth = 1;
      for (const f of [0.33, 0.66, 1.0]) {
        radCtx.beginPath();
        radCtx.arc(cx, cy, radius * f, 0, Math.PI * 2);
        radCtx.stroke();
      }

      // Cross
      radCtx.beginPath();
      radCtx.moveTo(cx - radius, cy); radCtx.lineTo(cx + radius, cy);
      radCtx.moveTo(cx, cy - radius); radCtx.lineTo(cx, cy + radius);
      radCtx.stroke();

      // Sweep Beam
      radarSweep = (radarSweep + 0.05) % (Math.PI * 2);
      const bx = cx + Math.cos(radarSweep) * radius;
      const by = cy + Math.sin(radarSweep) * radius;
      radCtx.strokeStyle = '#00ff66';
      radCtx.lineWidth = 2;
      radCtx.beginPath();
      radCtx.moveTo(cx, cy);
      radCtx.lineTo(bx, by);
      radCtx.stroke();

      // Target Blip
      const blipAngle = 0.8;
      const blipDist = radius * 0.45;
      const tx = cx + Math.cos(blipAngle) * blipDist;
      const ty = cy + Math.sin(blipAngle) * blipDist;

      radCtx.fillStyle = '#ff2222';
      radCtx.beginPath();
      radCtx.arc(tx, ty, 5, 0, Math.PI * 2);
      radCtx.fill();

      radCtx.fillStyle = '#ffaa00';
      radCtx.font = '10px Courier New';
      radCtx.fillText("TGT-101 (420m)", tx + 8, ty);

      requestAnimationFrame(renderRadar);
    }

    renderOptronics();
    renderRadar();

    // ECM Action Function
    async function engageECM(type) {
      const statusDiv = document.getElementById('ecm-status');
      statusDiv.innerHTML = `<span style="color:#ffff00;">TRANSMITTING: Engaged ${type} against Target #101...</span>`;
      
      try {
        const resp = await fetch('/api/v1/countermeasures/engage', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_id: 101, measure_type: type, operator: "COMMANDER_WEB" })
        });
        const data = await resp.json();
        statusDiv.innerHTML = `<span style="color:#00ff66;">ACTIVE: ${data.details.details}</span>`;
        document.getElementById('defcon-badge').innerText = "DEFCON: 5 [TARGET NEUTRALIZED]";
        document.getElementById('defcon-badge').style.color = "#00ff66";
        document.getElementById('defcon-badge').style.borderColor = "#00ff66";
        document.getElementById('neutralized').innerText = "1";
      } catch (err) {
        statusDiv.innerHTML = `<span style="color:#ff3333;">ERROR: Could not reach ECM hardware actuator.</span>`;
      }
    }

    async function disengageAll() {
      const statusDiv = document.getElementById('ecm-status');
      await fetch('/api/v1/countermeasures/disengage', { method: 'POST' });
      statusDiv.innerHTML = "ALL SYSTEMS STANDBY: All effectors disengaged and returned to passive surveillance.";
      document.getElementById('defcon-badge').innerText = "DEFCON: 4 [ACTIVE SURVEILLANCE]";
      document.getElementById('defcon-badge').style.color = "#00ff66";
      document.getElementById('defcon-badge').style.borderColor = "#00ff66";
    }
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def get_command_center_ui():
    """Serves the interactive browser-based C2 Military Command Center."""
    return HTMLResponse(content=WEB_COMMAND_CENTER_HTML)

@app.get("/command-center", response_class=HTMLResponse)
def get_command_center_alias():
    return HTMLResponse(content=WEB_COMMAND_CENTER_HTML)

@app.get("/api/v1/status")
def get_system_status():
    summary = threat_mgr.get_summary()
    return {
        "status": "ONLINE",
        "defcon": summary["overall_threat_level"],
        "active_threats": summary["active_threat_count"],
        "total_detections": summary["total_detections"],
        "neutralized_count": summary["neutralized_count"],
        "actuators": {k.value: v.value for k, v in countermeasure_ctrl.statuses.items()},
        "timestamp": time.time()
    }

@app.get("/api/v1/threats")
def get_threats():
    return threat_mgr.get_summary()

@app.post("/api/v1/countermeasures/engage")
def engage_countermeasure(req: CountermeasureRequest):
    countermeasure_ctrl.set_operator(req.operator)
    measure_upper = req.measure_type.upper()

    if measure_upper == "RF_JAMMER":
        res = countermeasure_ctrl.activate_rf_jammer(req.target_id, duration_sec=req.duration_sec)
    elif measure_upper == "GPS_SPOOF":
        res = countermeasure_ctrl.activate_gps_spoofing(req.target_id)
    elif measure_upper == "KINETIC_INTERCEPT":
        res = countermeasure_ctrl.launch_kinetic_interceptor(req.target_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown countermeasure type: {req.measure_type}")

    threat_mgr.clear_threat(req.target_id, neutralized=True)
    return {"result": "ENGAGEMENT_SUCCESS", "details": res}

@app.post("/api/v1/countermeasures/disengage")
def disengage_all():
    countermeasure_ctrl.disengage_all()
    return {"result": "DISENGAGED", "status": "ALL_STANDBY"}

@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = {
                "timestamp": time.time(),
                "summary": threat_mgr.get_summary(),
                "actuators": {k.value: v.value for k, v in countermeasure_ctrl.statuses.items()}
            }
            await websocket.send_json(data)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info("Client disconnected from telemetry stream.")

def run_server(host: str = "127.0.0.1", port: int = 8080):
    import uvicorn
    logger.info(f"Starting CUAS C2 API Server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")

if __name__ == "__main__":
    run_server()
