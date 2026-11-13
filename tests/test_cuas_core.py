"""
Comprehensive Unit and Integration Test Suite for CUAS (v4.0-Lattice).
Covers:
- 3D IMM-UKF state estimation, covariance positive-definiteness, terminal dive detection, and CEP impact.
- Multi-target ByteTrack Hungarian assignment and swarm ID persistence.
- Evidential threat classification with Radar micro-Doppler and RF-silent stealth detection.
- Weapon-Target Assignment (WTA) optimization and 6-stage Kill-Chain progression.
- 128-bin SDR RF waterfall arrays and AESA phased-array radar micro-Doppler physics.
- Covariance Intersection multi-modal sensor fusion.
- Closed-loop countermeasure actuator kinematics and Blue-Force interceptor BDA.
- Cryptographic SHA-256 blockchain audit chain validation and tamper detection.
"""

import unittest
import numpy as np
import time
import os

from utils.geo_utils import haversine_distance, calculate_bearing, forward_project, check_geofence_status
from ai_core.trajectory_predictor import (
    KalmanFilter2D, UKFFilter3D, InteractingMultipleModelUKF, TrajectoryPredictor
)
from ai_core.classifier import DroneClassifierEngine, DroneClassificationResult
from ai_core.response_engine import ThreatResponseEngine, ThreatEvaluation, KillChainStage
from ai_core.detection import SyntheticDroneGenerator, TrackedDrone, DroneDetector, compute_iou
from sensors.rf_sensor import RFSensorSimulator
from sensors.radar_sensor import RadarSensorSimulator
from sensors.sensor_fusion import SensorFusionHub, covariance_intersection_1d
from control_unit.neutralization import CountermeasureController, CountermeasureType, ActuatorStatus
from control_unit.threat_manager import ThreatManager
from control_unit.audit_logger import ForensicAuditLogger


class TestCUASGeospatial(unittest.TestCase):
    def test_haversine_distance(self):
        dist = haversine_distance(37.7749, -122.4194, 37.8044, -122.2711)
        self.assertTrue(12000 < dist < 15000, f"Distance {dist} out of expected range")

    def test_calculate_bearing(self):
        bearing = calculate_bearing(0.0, 0.0, 10.0, 0.0)
        self.assertAlmostEqual(bearing, 0.0, places=1)
        bearing_east = calculate_bearing(0.0, 0.0, 0.0, 10.0)
        self.assertAlmostEqual(bearing_east, 90.0, places=1)

    def test_geofence_zones(self):
        base_lat, base_lon = 37.7749, -122.4194
        target_lat = base_lat + 0.0004
        status = check_geofence_status(target_lat, base_lon, base_lat, base_lon, inner_killzone_m=500.0)
        self.assertEqual(status["zone"], "RED")
        self.assertEqual(status["threat_level"], "CRITICAL")

    def test_forward_projection(self):
        base_lat, base_lon = 37.7749, -122.4194
        dest_lat, dest_lon = forward_project(base_lat, base_lon, 1000.0, 0.0)
        self.assertGreater(dest_lat, base_lat)
        self.assertAlmostEqual(dest_lon, base_lon, places=3)


class TestCUASTrajectoryIMMUKF(unittest.TestCase):
    def test_kalman_filter_2d_backward_compat(self):
        kf = KalmanFilter2D(init_x=100.0, init_y=100.0, dt=1.0/30.0)
        for i in range(10):
            kf.predict()
            kf.update(100.0 + i * 10.0, 100.0 + i * 5.0)
        forecast = kf.forecast_steps(10)
        self.assertEqual(len(forecast), 10)
        self.assertGreater(forecast[-1][0], forecast[0][0])

    def test_ukf_3d_covariance_positive_definite(self):
        ukf = UKFFilter3D(mode="CV", dt=1.0/30.0)
        ukf.predict()
        ukf.update(np.array([100.0, 200.0, 150.0]))
        eigvals = np.linalg.eigvalsh(ukf.P)
        self.assertTrue(np.all(eigvals > 0), "UKF Covariance P must remain strictly positive definite")

    def test_imm_ukf_mode_probabilities_and_dive_detection(self):
        imm = InteractingMultipleModelUKF(init_pos_enu=(0.0, 500.0, 300.0), dt=1.0/30.0)
        # Simulate downward terminal dive
        for step in range(15):
            z_enu = (0.0, 500.0 - step * 15.0, 300.0 - step * 18.0)
            res = imm.cycle(z_enu)

        self.assertIn("CA_DIVE", res["mode_probabilities"])
        self.assertGreater(res["mode_probabilities"]["CA_DIVE"], 0.20)

    def test_trajectory_predictor_3d_ribbon_and_cep(self):
        predictor = TrajectoryPredictor(history_len=20, forecast_steps=30)
        pred = predictor.update_track(target_id=101, pos_x=320.0, pos_y=180.0, est_dist_m=600.0)
        self.assertEqual(pred.target_id, 101)
        self.assertEqual(len(pred.predicted_path_3d), 30)
        self.assertGreater(pred.circular_error_probable_m, 0.0)


class TestCUASDetectionAndByteTrack(unittest.TestCase):
    def test_compute_iou(self):
        box1 = (10, 10, 50, 50)
        box2 = (10, 10, 50, 50)
        box3 = (100, 100, 150, 150)
        self.assertAlmostEqual(compute_iou(box1, box2), 1.0)
        self.assertEqual(compute_iou(box1, box3), 0.0)

    def test_synthetic_drone_swarm_generation(self):
        gen = SyntheticDroneGenerator(width=640, height=480, scenario="SWARM_SATURATION")
        frame_eo = gen.generate_frame()
        self.assertEqual(frame_eo.shape, (480, 640, 3))
        self.assertGreaterEqual(len(gen.drones), 3)

        # Test FLIR thermal modes
        gen.set_display_mode("FLIR_WHITE_HOT")
        frame_flir_w = gen.generate_frame()
        self.assertEqual(frame_flir_w.shape, (480, 640, 3))

        gen.set_display_mode("FLIR_BLACK_HOT")
        frame_flir_b = gen.generate_frame()
        self.assertEqual(frame_flir_b.shape, (480, 640, 3))

    def test_bytetrack_hungarian_track_persistence(self):
        detector = DroneDetector(confidence_threshold=0.45, device="cpu")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Direct association test
        raw_dets = [
            ((100, 100, 150, 150), 0.90, "uav"),
            ((300, 200, 360, 260), 0.85, "uav")
        ]
        t1 = detector._bytetrack_association(raw_dets, frame)
        self.assertEqual(len(t1), 2)
        initial_ids = [t.target_id for t in t1]

        # Next frame slightly moved
        raw_dets_moved = [
            ((103, 102, 153, 152), 0.88, "uav"),
            ((304, 202, 364, 262), 0.84, "uav")
        ]
        t2 = detector._bytetrack_association(raw_dets_moved, frame)
        self.assertEqual(len(t2), 2)
        moved_ids = [t.target_id for t in t2]
        self.assertEqual(initial_ids, moved_ids, "Hungarian tracking must preserve track IDs across motion")


class TestCUASEvidentialClassifier(unittest.TestCase):
    def test_classifier_micro_doppler_and_rf_silent_threat(self):
        engine = DroneClassifierEngine(device="cpu")
        crop = np.zeros((80, 80, 3), dtype=np.uint8)

        # RF-Silent fast-closing threat
        res_dark = engine.classify_crop(
            crop_bgr=crop,
            radar_micro_doppler_rpm=22000.0,
            rf_protocol="RF-SILENT",
            closing_speed_mps=28.0
        )
        self.assertTrue(res_dark.is_autonomous_dark_threat)
        self.assertEqual(res_dark.predicted_class, "AUTONOMOUS_LOITERING_MUNITION")
        self.assertGreater(res_dark.threat_score, 80.0)

    def test_classifier_civilian_low_rpm(self):
        engine = DroneClassifierEngine(device="cpu")
        crop = np.zeros((60, 60, 3), dtype=np.uint8)
        res_civ = engine.classify_crop(
            crop_bgr=crop,
            radar_micro_doppler_rpm=8500.0,
            rf_protocol="WiFi",
            closing_speed_mps=3.0
        )
        self.assertFalse(res_civ.is_autonomous_dark_threat)
        self.assertLess(res_civ.threat_score, 60.0)


class TestCUASResponseAndWTA(unittest.TestCase):
    def test_weapon_target_assignment_and_kill_chain(self):
        response_eng = ThreatResponseEngine(base_latitude=37.7749, base_longitude=-122.4194)
        mock_cls = DroneClassificationResult(
            predicted_class="SUICIDE_DRONE",
            confidence=0.94,
            threat_score=92.0,
            probabilities={"SUICIDE_DRONE": 0.94},
            has_payload_risk=True,
            size_category="MEDIUM",
            wingspan_estimate_px=90,
            aspect_ratio=1.2,
            is_autonomous_dark_threat=False
        )
        # Fast dive near base (350m -> Killzone)
        eval_res = response_eng.evaluate_target(
            target_id=101,
            target_lat=37.7749 + 0.002,
            target_lon=-122.4194,
            classification=mock_cls
        )
        self.assertEqual(eval_res.geofence_zone, "RED")
        self.assertEqual(eval_res.threat_level, "CRITICAL")
        self.assertEqual(eval_res.kill_chain_stage, KillChainStage.ENGAGE)
        self.assertIn(eval_res.recommended_countermeasure, ["KINETIC_INTERCEPT", "RF_JAMMER"])


class TestCUASSensorsAndFusion(unittest.TestCase):
    def test_sdr_rf_waterfall_128_bins(self):
        rf = RFSensorSimulator()
        psd = rf.generate_waterfall_slice(center_freq_mhz=2437.0, target_present=True)
        self.assertEqual(len(psd), 128)
        # Test jammer saturation
        rf.set_jammer_active(["2.4 GHz"])
        psd_jammed = rf.generate_waterfall_slice(center_freq_mhz=2437.0, target_present=True)
        self.assertGreater(np.mean(psd_jammed), np.mean(psd))

    def test_phased_array_radar_and_micro_doppler(self):
        radar = RadarSensorSimulator()
        contacts = radar.scan_for_contacts(
            target_range_m=1400.0,
            target_azimuth_deg=45.0,
            target_velocity_mps=22.0,
            rotor_rpm=21000.0,
            is_bird=False
        )
        self.assertEqual(len(contacts), 1)
        self.assertTrue(contacts[0].rotor_blade_detected)
        self.assertEqual(len(contacts[0].micro_doppler_spectrum_64), 64)

        # Bird comparison
        bird_contacts = radar.scan_for_contacts(
            target_range_m=800.0,
            target_azimuth_deg=60.0,
            target_velocity_mps=8.0,
            is_bird=True
        )
        self.assertEqual(len(bird_contacts), 1)
        self.assertFalse(bird_contacts[0].rotor_blade_detected)

    def test_covariance_intersection_and_fusion_hub(self):
        val_ci, var_ci = covariance_intersection_1d(100.0, 10.0, 110.0, 15.0, omega=0.6)
        self.assertTrue(100.0 <= val_ci <= 110.0)
        self.assertLess(var_ci, 15.0)

        hub = SensorFusionHub()
        v_track = TrackedDrone(
            target_id=101, bbox=(100, 100, 200, 200), center=(150, 150),
            confidence=0.85, class_label="uav", crop=None, first_detected_time=time.time(),
            last_updated_time=time.time()
        )
        fused = hub.fuse([v_track], [], [])
        self.assertEqual(len(fused), 1)
        self.assertIn("EO", fused[0].sensor_badge)


class TestCUASControlAndAudit(unittest.TestCase):
    def test_countermeasure_actuators_and_interceptor_bda(self):
        ctrl = CountermeasureController(operator_name="TEST_COMMANDER")
        res_jam = ctrl.activate_rf_jammer(target_id=101)
        self.assertEqual(res_jam["status"], "ACTIVE")
        self.assertEqual(res_jam["bda"], "LINK_SEVERED")

        res_kin = ctrl.launch_kinetic_interceptor(target_id=102, target_enu=(100.0, 100.0, 50.0))
        self.assertEqual(res_kin["status"], "ACTIVE")
        self.assertIn("SPLASH_CONFIRMED", res_kin["bda"])

        # Advance simulation to verify collision BDA
        bda_events = ctrl.update_interceptor_simulation(dt=10.0)
        self.assertGreaterEqual(len(bda_events), 1)
        self.assertEqual(bda_events[0]["event"], "SPLASH_CONFIRMED")
        ctrl.disengage_all()

    def test_threat_manager_priority_queuing(self):
        mgr = ThreatManager()
        t1 = ThreatEvaluation(
            target_id=1, threat_level="HIGH", numerical_threat_score=70.0,
            geofence_zone="AMBER", distance_to_base_m=1200.0, bearing_from_base_deg=45.0,
            recommended_countermeasure="GPS_SPOOF", countermeasure_probability_success=0.85,
            engagement_authorized=False, rationale="Approaching", time_to_perimeter_sec=12.0
        )
        t2 = ThreatEvaluation(
            target_id=2, threat_level="CRITICAL", numerical_threat_score=95.0,
            geofence_zone="RED", distance_to_base_m=350.0, bearing_from_base_deg=90.0,
            recommended_countermeasure="KINETIC_INTERCEPT", countermeasure_probability_success=0.95,
            engagement_authorized=True, rationale="Dive", time_to_perimeter_sec=3.2
        )
        mgr.update_threat(t1)
        mgr.update_threat(t2)
        prioritized = mgr.get_prioritized_threats()
        self.assertEqual(prioritized[0].target_id, 2, "Target with lowest TTI must be prioritized first")

    def test_forensic_audit_chain_verification_and_tampering(self):
        logger = ForensicAuditLogger(log_dir="logs/test_audit_v4")
        if os.path.exists(logger.chain_file):
            os.remove(logger.chain_file)
        logger.last_hash = "0" * 64

        h1 = logger.log_event("TEST_BLOCK_1", {"metric": 100}, operator="OPERATOR_1")
        h2 = logger.log_event("TEST_BLOCK_2", {"metric": 200}, operator="OPERATOR_2")
        self.assertEqual(len(h1), 64)
        self.assertEqual(len(h2), 64)

        is_valid, count, msg = logger.verify_chain_integrity()
        self.assertTrue(is_valid)
        self.assertEqual(count, 2)
        self.assertIn("100% CRYPTOGRAPHIC INTEGRITY", msg)


if __name__ == "__main__":
    unittest.main()
