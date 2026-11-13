"""
Unit and Integration Test Suite for CUAS.
Verifies AI detection, classification, Kalman trajectory prediction, sensor fusion,
and threat response mechanics.
"""

import unittest
import numpy as np
import time

from utils.geo_utils import haversine_distance, calculate_bearing, check_geofence_status
from ai_core.trajectory_predictor import KalmanFilter2D, TrajectoryPredictor
from ai_core.classifier import DroneClassifierEngine, DroneClassificationResult
from ai_core.response_engine import ThreatResponseEngine, ThreatEvaluation
from ai_core.detection import SyntheticDroneGenerator, TrackedDrone
from sensors.rf_sensor import RFSensorSimulator
from sensors.radar_sensor import RadarSensorSimulator
from sensors.sensor_fusion import SensorFusionHub
from control_unit.neutralization import CountermeasureController, CountermeasureType
from control_unit.audit_logger import ForensicAuditLogger
from control_unit.threat_manager import ThreatManager

class TestCUASGeospatial(unittest.TestCase):
    def test_haversine_distance(self):
        # Distance between SF (37.7749, -122.4194) and Oakland (37.8044, -122.2711) is ~13-14km
        dist = haversine_distance(37.7749, -122.4194, 37.8044, -122.2711)
        self.assertTrue(12000 < dist < 15000, f"Distance {dist} out of expected range")

    def test_calculate_bearing(self):
        # Due north
        bearing = calculate_bearing(0.0, 0.0, 10.0, 0.0)
        self.assertAlmostEqual(bearing, 0.0, places=1)
        # Due east
        bearing_east = calculate_bearing(0.0, 0.0, 0.0, 10.0)
        self.assertAlmostEqual(bearing_east, 90.0, places=1)

    def test_geofence_zones(self):
        base_lat, base_lon = 37.7749, -122.4194
        # Inside inner killzone (50m away)
        target_lat = base_lat + 0.0004
        status = check_geofence_status(target_lat, base_lon, base_lat, base_lon, inner_killzone_m=500.0)
        self.assertEqual(status["zone"], "RED")
        self.assertEqual(status["threat_level"], "CRITICAL")


class TestCUASTrajectory(unittest.TestCase):
    def test_kalman_filter_convergence(self):
        kf = KalmanFilter2D(init_x=100.0, init_y=100.0, dt=1.0/30.0)
        # Move target at constant velocity 10 px/frame
        for i in range(10):
            kf.predict()
            kf.update(100.0 + i * 10.0, 100.0 + i * 5.0)

        # Forecast future points
        forecast = kf.forecast_steps(10)
        self.assertEqual(len(forecast), 10)
        self.assertGreater(forecast[-1][0], forecast[0][0])

    def test_trajectory_predictor(self):
        predictor = TrajectoryPredictor(history_len=15, forecast_steps=20)
        pred = predictor.update_track(target_id=1, pos_x=200.0, pos_y=150.0)
        self.assertEqual(pred.target_id, 1)
        self.assertIsNotNone(pred.velocity_vector)
        self.assertEqual(len(pred.predicted_path), 20)


class TestCUASThreatResponse(unittest.TestCase):
    def test_threat_evaluation_levels(self):
        engine = ThreatResponseEngine(base_latitude=37.7749, base_longitude=-122.4194)
        mock_cls = DroneClassificationResult(
            predicted_class="SUICIDE_DRONE",
            confidence=0.92,
            threat_score=85.0,
            probabilities={"SUICIDE_DRONE": 0.92},
            has_payload_risk=True,
            size_category="MEDIUM",
            wingspan_estimate_px=120,
            aspect_ratio=1.4
        )
        # Target close to base (200m away -> RED zone)
        eval_result = engine.evaluate_target(
            target_id=42,
            target_lat=37.7749 + 0.001,
            target_lon=-122.4194,
            classification=mock_cls
        )
        self.assertEqual(eval_result.geofence_zone, "RED")
        self.assertEqual(eval_result.threat_level, "CRITICAL")
        self.assertIn(eval_result.recommended_countermeasure, ["KINETIC_INTERCEPT", "RF_JAMMER"])


class TestCUASSensorsAndFusion(unittest.TestCase):
    def test_synthetic_drone_generation(self):
        gen = SyntheticDroneGenerator(width=640, height=480)
        frame = gen.generate_frame()
        self.assertEqual(frame.shape, (480, 640, 3))

    def test_rf_and_radar_sensors(self):
        rf = RFSensorSimulator()
        radar = RadarSensorSimulator()
        emissions = rf.scan_spectrum(simulated_target_bearing=45.0, distance_m=1200.0)
        contacts = radar.scan_for_contacts(target_range_m=1200.0, target_azimuth_deg=radar.current_azimuth)

        self.assertIsInstance(emissions, list)
        self.assertIsInstance(contacts, list)

    def test_sensor_fusion(self):
        hub = SensorFusionHub()
        v_track = TrackedDrone(
            target_id=1,
            bbox=(100, 100, 200, 200),
            center=(150, 150),
            confidence=0.88,
            class_label="uav",
            crop=np.zeros((100, 100, 3), dtype=np.uint8),
            first_detected_time=time.time(),
            last_updated_time=time.time()
        )
        fused = hub.fuse([v_track], [], [])
        self.assertEqual(len(fused), 1)
        self.assertTrue(fused[0].has_visual)


class TestCUASControlAndAudit(unittest.TestCase):
    def test_countermeasure_controller(self):
        ctrl = CountermeasureController(operator_name="TEST_AGENT")
        res = ctrl.activate_rf_jammer(target_id=99)
        self.assertEqual(res["status"], "ACTIVE")
        self.assertEqual(len(ctrl.history), 1)
        ctrl.disengage_all()

    def test_audit_logger(self):
        logger = ForensicAuditLogger(log_dir="logs/test_audit")
        h1 = logger.log_event("TEST_EVENT_1", {"key": "val1"}, operator="AGENT")
        h2 = logger.log_event("TEST_EVENT_2", {"key": "val2"}, operator="AGENT")
        self.assertNotEqual(h1, h2)
        self.assertEqual(len(h1), 64)


if __name__ == "__main__":
    unittest.main()
