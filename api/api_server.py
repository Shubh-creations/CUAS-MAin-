"""
FastAPI REST & WebSocket Command and Control (C2) Server for CUAS.
Enables headless remote operations, tactical multi-client monitoring, and API-driven countermeasure activation.
"""

from typing import Dict, List, Optional, Any
import time
import asyncio

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from utils.logger import get_logger
from control_unit.threat_manager import ThreatManager
from control_unit.neutralization import CountermeasureController, CountermeasureType

logger = get_logger("CUAS.API")

if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="CUAS Tactical C2 API",
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

    # In-memory shared state
    threat_mgr = ThreatManager()
    countermeasure_ctrl = CountermeasureController()

    class CountermeasureRequest(BaseModel):
        target_id: int
        measure_type: str  # "RF_JAMMER", "GPS_SPOOF", "OPTICAL_DAZZLER", "KINETIC_INTERCEPT"
        operator: Optional[str] = "REMOTE_C2"
        duration_sec: Optional[float] = 10.0

    @app.get("/")
    def root():
        return {
            "system": "CUAS Tactical Command and Control",
            "status": "ONLINE",
            "version": "2.5.0",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

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
    """Starts the FastAPI application via uvicorn."""
    if not FASTAPI_AVAILABLE:
        logger.error("FastAPI or Uvicorn not installed. Cannot start API server.")
        return
    import uvicorn
    logger.info(f"Starting CUAS C2 API Server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")

if __name__ == "__main__":
    run_server()
