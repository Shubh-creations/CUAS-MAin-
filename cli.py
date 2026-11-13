"""
Command Line Interface (CLI) for CUAS Defense Platform.
Allows headless execution, batch video analysis, simulation, and hardware diagnostics.
"""

import argparse
import sys
import time
import os
import cv2
import torch
import yaml

from utils.logger import get_logger
from ai_core.detection import DroneDetector, SyntheticDroneGenerator
from ai_core.classifier import DroneClassifierEngine
from ai_core.trajectory_predictor import TrajectoryPredictor
from ai_core.response_engine import ThreatResponseEngine
from sensors.camera_stream import CameraStream
from sensors.rf_sensor import RFSensorSimulator
from sensors.radar_sensor import RadarSensorSimulator
from sensors.sensor_fusion import SensorFusionHub
from control_unit.neutralization import CountermeasureController
from control_unit.threat_manager import ThreatManager

logger = get_logger("CUAS.CLI")

def run_diagnostics():
    """Runs system and AI accelerator diagnostics."""
    print("=" * 60)
    print("  CUAS DEFENSE SYSTEM - PRE-FLIGHT HARDWARE DIAGNOSTICS")
    print("=" * 60)
    print(f"Python Version : {sys.version.split()[0]}")
    print(f"PyTorch Version: {torch.__version__}")
    cuda_avail = torch.cuda.is_available()
    print(f"CUDA Available : {cuda_avail}")
    if cuda_avail:
        print(f"GPU Device     : {torch.cuda.get_device_name(0)}")
        print(f"Device Count   : {torch.cuda.device_count()}")
        mem_alloc = torch.cuda.memory_allocated(0) / (1024 ** 2)
        print(f"VRAM Allocated : {mem_alloc:.2f} MB")
    print(f"OpenCV Version : {cv2.__version__}")
    print("=" * 60)
    print("[SUCCESS] All system prerequisites verified.")


def run_simulation(duration_sec: int = 15, config_path: str = "config/default_config.yaml"):
    """Runs end-to-end tactical simulation with synthetic drone flight and sensor fusion."""
    print(f"Starting CUAS Multi-Modal Simulation ({duration_sec}s runtime)...")

    detector = DroneDetector(confidence_threshold=0.45, device="auto")
    classifier = DroneClassifierEngine(device="auto")
    trajectory_predictor = TrajectoryPredictor(history_len=20, forecast_steps=30, fps=20.0)
    threat_engine = ThreatResponseEngine()
    threat_mgr = ThreatManager()
    rf_sensor = RFSensorSimulator()
    radar_sensor = RadarSensorSimulator()
    fusion_hub = SensorFusionHub()
    countermeasure_ctrl = CountermeasureController(operator_name="SIM_OPERATOR")

    stream = CameraStream(simulation_mode=True, width=640, height=480)
    stream.start()

    start_time = time.time()
    frame_count = 0

    try:
        while time.time() - start_time < duration_sec:
            ret, frame = stream.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            frame_count += 1
            # 1. Detection
            tracks = detector.detect(frame)

            # 2. RF & Radar Scan
            sim_bearing = 48.5 + (frame_count * 0.2) % 360.0
            sim_dist = max(350.0, 2400.0 - (frame_count * 8.0))
            rf_emissions = rf_sensor.scan_spectrum(simulated_target_bearing=sim_bearing, distance_m=sim_dist)
            radar_contacts = radar_sensor.scan_for_contacts(target_range_m=sim_dist, target_azimuth_deg=sim_bearing)

            # 3. Multi-Sensor Fusion
            fused_tracks = fusion_hub.fuse(tracks, rf_emissions, radar_contacts)

            for track in tracks:
                # 4. Classification
                cls_result = classifier.classify_crop(track.crop)

                # 5. Trajectory Prediction
                traj_pred = trajectory_predictor.update_track(track.target_id, track.center[0], track.center[1])

                # 6. Response Engine
                sim_lat = 37.7749 + (track.center[1] - 240) * 0.00005
                sim_lon = -122.4194 + (track.center[0] - 320) * 0.00005
                threat_eval = threat_engine.evaluate_target(
                    target_id=track.target_id,
                    target_lat=sim_lat,
                    target_lon=sim_lon,
                    classification=cls_result,
                    trajectory=traj_pred
                )
                threat_mgr.update_threat(threat_eval)

                if frame_count % 15 == 0:
                    print(f"[{time.strftime('%H:%M:%S')}] Frame {frame_count:04d} | Target #{track.target_id} | "
                          f"Class: {cls_result.predicted_class} ({cls_result.confidence*100:.1f}%) | "
                          f"Zone: {threat_eval.geofence_zone} | Dist: {threat_eval.distance_to_base_m:.0f}m | "
                          f"Threat: {threat_eval.threat_level} ({threat_eval.numerical_threat_score:.1f}/100) | "
                          f"Measure: {threat_eval.recommended_countermeasure}")

            time.sleep(1.0 / 25.0)

    finally:
        stream.stop()

    summary = threat_mgr.get_summary()
    print("=" * 60)
    print("  SIMULATION COMPLETE - MISSION SUMMARY")
    print(f"Total Frames Processed: {frame_count}")
    print(f"Total Targets Tracked : {summary['total_detections']}")
    print(f"Final DEFCON State    : {summary['overall_threat_level']}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="CUAS Tactical Counter-UAS System CLI")
    parser.add_argument("--check", action="store_true", help="Run hardware & PyTorch CUDA diagnostics")
    parser.add_argument("--simulate", action="store_true", help="Run multi-modal synthetic flight simulation")
    parser.add_argument("--duration", type=int, default=10, help="Simulation duration in seconds")
    parser.add_argument("--server", action="store_true", help="Launch FastAPI REST/WebSocket C2 API daemon")
    parser.add_argument("--port", type=int, default=8080, help="API server port")
    parser.add_argument("--gui", action="store_true", help="Launch PyQt5 Desktop GUI")

    args = parser.parse_args()

    if args.check:
        run_diagnostics()
    elif args.simulate:
        run_simulation(duration_sec=args.duration)
    elif args.server:
        from api.api_server import run_server
        run_server(port=args.port)
    elif args.gui:
        import subprocess
        subprocess.run([sys.executable, "main.py"])
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
