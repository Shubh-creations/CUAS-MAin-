"""
LATTICE-CUAS Tactical Desktop Command Center (v4.0-Lattice).
Adheres to modern defense C2 design standards (Anduril Lattice / Palantir Gotham / MIL-STD-2525D).
Integrates IMM-UKF 3D Trajectory Prediction, Multi-Target Swarm Tracking, Multi-Spectral EO/IR FLIR,
3D AESA Radar Scope, and Weapon-Target Assignment (WTA) Countermeasures.
"""

import sys
import os
import cv2
import datetime
import math
import random
import time
from collections import deque
from typing import Optional, List, Tuple, Dict, Any

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel,
    QFileDialog, QHBoxLayout, QMenuBar, QAction, QFrame,
    QGridLayout, QSplitter, QProgressBar,
    QLineEdit, QDialog, QFormLayout, QComboBox, QCheckBox, QTabWidget,
    QTextEdit, QStackedWidget, QMessageBox, QGroupBox
)
from PyQt5.QtCore import QTimer, Qt, QSize
from PyQt5.QtGui import QPixmap, QImage, QColor, QFont, QPainter, QPen, QBrush

import torch
import numpy as np
import psutil

try:
    import pynvml as nvml
except Exception:
    nvml = None

from utils.logger import get_logger
from utils.geo_utils import haversine_distance, calculate_bearing, check_geofence_status
from utils.visualization import draw_corner_brackets, draw_lead_reticle, draw_trajectory_path
from ai_core.detection import DroneDetector, TrackedDrone, SyntheticDroneGenerator
from ai_core.classifier import DroneClassifierEngine, DroneClassificationResult
from ai_core.trajectory_predictor import TrajectoryPredictor, TrajectoryPrediction
from ai_core.response_engine import ThreatResponseEngine, ThreatEvaluation
from sensors.rf_sensor import RFSensorSimulator, RFEmission
from sensors.radar_sensor import RadarSensorSimulator, RadarContact
from sensors.sensor_fusion import SensorFusionHub, FusedTacticalTrack
from control_unit.neutralization import CountermeasureController, CountermeasureType, ActuatorStatus
from control_unit.threat_manager import ThreatManager
from control_unit.audit_logger import ForensicAuditLogger

logger = get_logger("CUAS.GUI")

# Modern Defense C2 Panel
class DashboardPanel(QFrame):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("dashboardPanel")
        self.setStyleSheet("""
            #dashboardPanel {
                background-color: #0B101B;
                border: 1px solid #1E293B;
                border-radius: 3px;
            }
        """)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 8, 10, 8)
        self.layout.setSpacing(6)

        if title:
            title_label = QLabel(title)
            title_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
            title_label.setStyleSheet("""
                color: #94A3B8;
                padding-bottom: 4px;
                border-bottom: 1px solid #1E293B;
                letter-spacing: 1px;
            """)
            self.layout.addWidget(title_label)


# High-Density 3D Tactical Radar Scope
class RadarScopeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)
        self.setStyleSheet("background-color: #04070D; border: 1px solid #1E293B; border-radius: 3px;")
        self.sweep_angle = 0.0
        self.contacts: List[Tuple[float, float, str, int]] = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate_sweep)
        self.timer.start(40)

    def rotate_sweep(self):
        self.sweep_angle = (self.sweep_angle + 4.5) % 360.0
        self.update()

    def set_contacts(self, contacts: List[Tuple[float, float, str, int]]):
        self.contacts = contacts
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        radius = min(cx, cy) - 12

        painter.fillRect(self.rect(), QColor(4, 7, 13))

        # Range rings
        rings = [
            (0.33, QColor(244, 63, 94, 90), "500m"),
            (0.66, QColor(245, 158, 11, 80), "1500m"),
            (1.00, QColor(16, 185, 129, 70), "3500m")
        ]
        for f, col, lbl in rings:
            r_curr = int(radius * f)
            painter.setPen(QPen(col, 1))
            painter.drawEllipse(cx - r_curr, cy - r_curr, r_curr * 2, r_curr * 2)
            painter.setFont(QFont("Consolas", 7))
            painter.setPen(col)
            painter.drawText(cx + 4, cy - r_curr + 10, lbl)

        # Crosshairs
        painter.setPen(QPen(QColor(30, 41, 59), 1))
        painter.drawLine(cx - radius, cy, cx + radius, cy)
        painter.drawLine(cx, cy - radius, cx, cy + radius)

        # Rotating AESA sweep line
        rad = math.radians(self.sweep_angle - 90)
        bx = int(cx + radius * math.cos(rad))
        by = int(cy + radius * math.sin(rad))
        painter.setPen(QPen(QColor(16, 185, 129, 180), 1.5))
        painter.drawLine(cx, cy, bx, by)

        # Contacts with MIL-STD symbology
        for az_deg, dist_ratio, level, tid in self.contacts:
            c_rad = math.radians(az_deg - 90)
            c_r = max(10, min(radius, int(radius * dist_ratio)))
            px = int(cx + c_r * math.cos(c_rad))
            py = int(cy + c_r * math.sin(c_rad))

            if level in ["CRITICAL", "HIGH"]:
                p_col = QColor(244, 63, 94)
            elif level == "ELEVATED":
                p_col = QColor(245, 158, 11)
            else:
                p_col = QColor(16, 185, 129)

            painter.setPen(QPen(p_col, 1.5))
            painter.setBrush(QBrush(p_col))
            # Hostile diamond
            painter.drawPolygon([
                painter.device().rect().topLeft() # dummy
            ])
            painter.drawRect(px - 3, py - 3, 6, 6)
            painter.setFont(QFont("Consolas", 7))
            painter.drawText(px + 6, py + 3, f"#{tid}")


# Modern Authentication Dialog
class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LATTICE-CUAS // DEFENSE AUTHENTICATION")
        self.setFixedSize(440, 260)
        self.setStyleSheet("""
            QDialog {
                background-color: #06090F;
                border: 1px solid #1E293B;
            }
            QLabel {
                color: #94A3B8;
                font-family: 'Segoe UI';
                font-weight: 600;
                font-size: 11px;
            }
            QLineEdit {
                background-color: #111827;
                color: #F8FAFC;
                border: 1px solid #1E293B;
                padding: 6px 10px;
                font-family: 'Consolas';
                font-size: 12px;
                border-radius: 3px;
            }
            QLineEdit:focus {
                border: 1px solid #0EA5E9;
            }
            QPushButton {
                background-color: #0EA5E9;
                color: #06090F;
                border: none;
                padding: 8px 16px;
                font-family: 'Segoe UI';
                font-weight: 700;
                font-size: 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #38BDF8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("LATTICE-CUAS OPERATOR ACCESS")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet("color: #F8FAFC; letter-spacing: 1px;")
        layout.addWidget(title)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setText("CDR. S. PAWAR")
        form.addRow(QLabel("OPERATOR ID:"), self.name_input)

        self.profile_input = QLineEdit()
        self.profile_input.setText("DEFCON-1 CONTROLLER")
        form.addRow(QLabel("CLEARANCE:"), self.profile_input)
        layout.addLayout(form)

        login_btn = QPushButton("AUTHENTICATE & ENTER C2")
        login_btn.clicked.connect(self.accept)
        layout.addWidget(login_btn)


# Main Modern Desktop C2 Window
class DesktopApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LATTICE-CUAS // Autonomous Air Defense & Counter-Swarm Command (v4.0)")
        self.setMinimumSize(1340, 860)

        # AI Core, Sensors & Control
        self.detector = DroneDetector(confidence_threshold=0.50, device="auto")
        self.classifier = DroneClassifierEngine(device="auto")
        self.trajectory_predictor = TrajectoryPredictor(history_len=30, forecast_steps=40, fps=30.0)
        self.threat_engine = ThreatResponseEngine()
        self.threat_mgr = ThreatManager()
        self.rf_sensor = RFSensorSimulator()
        self.radar_sensor = RadarSensorSimulator()
        self.fusion_hub = SensorFusionHub()
        self.countermeasure_ctrl = CountermeasureController()
        self.audit_logger = ForensicAuditLogger()

        self.synthetic_gen = SyntheticDroneGenerator(width=640, height=480, scenario="SWARM_SATURATION")
        self.is_simulation_mode = True
        self.cap: Optional[cv2.VideoCapture] = None

        self.user_name = "CDR. S. PAWAR"
        self.user_profile = "DEFCON-1 CONTROLLER"
        self._frame_times = deque(maxlen=60)
        self._last_fps = 30.0
        self._last_latency = 28
        self._current_threat: Optional[ThreatEvaluation] = None

        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #06090F;
                color: #F8FAFC;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #94A3B8;
            }
            QPushButton {
                background-color: #111827;
                color: #F8FAFC;
                border: 1px solid #1E293B;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 11px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1E293B;
                border-color: #334155;
            }
            QMenuBar {
                background-color: #0B101B;
                color: #94A3B8;
                border-bottom: 1px solid #1E293B;
                font-size: 11px;
            }
            QMenuBar::item:selected {
                background-color: #1E293B;
                color: #F8FAFC;
            }
        """)

        self.main_container = QVBoxLayout(self)
        self.main_container.setContentsMargins(0, 0, 0, 0)
        self.stacked_widget = QStackedWidget()

        # Login Screen
        self.login_page = QWidget()
        login_vbox = QVBoxLayout(self.login_page)
        login_vbox.setAlignment(Qt.AlignCenter)
        t_lbl = QLabel("LATTICE-CUAS // AUTONOMOUS AIR DEFENSE")
        t_lbl.setFont(QFont("Segoe UI", 18, QFont.Bold))
        t_lbl.setStyleSheet("color: #F8FAFC; margin-bottom: 15px; letter-spacing: 1px;")
        login_vbox.addWidget(t_lbl)

        auth_btn = QPushButton("INITIATE DEFENSE AUTHENTICATION")
        auth_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        auth_btn.setFixedSize(380, 44)
        auth_btn.clicked.connect(self.show_login_dialog)
        login_vbox.addWidget(auth_btn)

        # Main C2 Screen
        self.main_page = QWidget()
        main_vbox = QVBoxLayout(self.main_page)
        main_vbox.setContentsMargins(8, 8, 8, 8)
        main_vbox.setSpacing(6)

        # Menu Bar
        self.menu_bar = QMenuBar(self)
        file_menu = self.menu_bar.addMenu("FILE")
        act_video = QAction("Open Video File", self)
        act_cam = QAction("Open Live Camera", self)
        act_sim = QAction("Swarm Simulation Mode", self)
        file_menu.addAction(act_video)
        file_menu.addAction(act_cam)
        file_menu.addAction(act_sim)
        act_video.triggered.connect(self.load_video)
        act_cam.triggered.connect(self.open_camera)
        act_sim.triggered.connect(self.start_simulation)

        sensor_menu = self.menu_bar.addMenu("SENSOR MODE")
        act_eo = QAction("EO Daylight", self)
        act_flir_w = QAction("FLIR White-Hot", self)
        act_flir_b = QAction("FLIR Black-Hot", self)
        sensor_menu.addAction(act_eo)
        sensor_menu.addAction(act_flir_w)
        sensor_menu.addAction(act_flir_b)
        act_eo.triggered.connect(lambda: self.set_sensor_mode("EO_DAYLIGHT"))
        act_flir_w.triggered.connect(lambda: self.set_sensor_mode("FLIR_WHITE_HOT"))
        act_flir_b.triggered.connect(lambda: self.set_sensor_mode("FLIR_BLACK_HOT"))

        main_vbox.setMenuBar(self.menu_bar)

        # Top Ribbon
        header = QHBoxLayout()
        self.operator_label = QLabel(f"OPERATOR: {self.user_name} | {self.user_profile}")
        self.operator_label.setFont(QFont("Consolas", 10, QFont.Bold))
        self.operator_label.setStyleSheet("color: #F8FAFC;")

        self.defcon_label = QLabel("DEFCON 1 // CRITICAL")
        self.defcon_label.setFont(QFont("Consolas", 10, QFont.Bold))
        self.defcon_label.setStyleSheet("color: #F43F5E; padding: 2px 8px; border: 1px solid #F43F5E; background: rgba(244,63,94,0.1); border-radius: 3px;")

        self.time_label = QLabel()
        self.time_label.setFont(QFont("Consolas", 10))
        self.time_label.setStyleSheet("color: #94A3B8;")

        header.addWidget(self.operator_label)
        header.addStretch()
        header.addWidget(self.defcon_label)
        header.addSpacing(16)
        header.addWidget(self.time_label)
        main_vbox.addLayout(header)

        # 3-Column Content Grid
        grid = QGridLayout()
        grid.setSpacing(8)

        # Left Column: Optronic Camera Viewport
        video_panel = DashboardPanel("TACTICAL OPTRONIC SENSOR (LIVE EO/IR)")
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(600, 440)
        self.video_label.setStyleSheet("border: 1px solid #1E293B; background-color: #04070D; border-radius: 2px;")
        video_panel.layout.addWidget(self.video_label)
        grid.addWidget(video_panel, 0, 0, 2, 1)

        # Middle Column: AI Threat & Effector Center
        mid_layout = QVBoxLayout()

        det_panel = DashboardPanel("AI THREAT CLASSIFICATION (IMM-UKF)")
        self.det_status_label = QLabel("STATUS: MULTI-TARGET SWARM TRACKING")
        self.det_status_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.det_status_label.setStyleSheet("color: #F8FAFC;")

        self.first_det_label = QLabel("TARGET: #101-ALPHA [SUICIDE DRONE]")
        self.first_det_label.setFont(QFont("Consolas", 9))
        self.first_det_label.setStyleSheet("color: #F43F5E;")

        self.det_preview = QLabel("LOCKING OPTICAL TARGET")
        self.det_preview.setAlignment(Qt.AlignCenter)
        self.det_preview.setFixedSize(140, 140)
        self.det_preview.setStyleSheet("border: 1px solid #1E293B; background-color: #0B101B; border-radius: 3px;")

        self.cls_result_label = QLabel("TYPE: SUICIDE DRONE (LOITERING)")
        self.cls_result_label.setFont(QFont("Consolas", 10, QFont.Bold))
        self.cls_result_label.setStyleSheet("color: #F8FAFC;")

        self.threat_score_bar = QProgressBar()
        self.threat_score_bar.setRange(0, 100)
        self.threat_score_bar.setValue(92)
        self.threat_score_bar.setTextVisible(True)
        self.threat_score_bar.setFormat("SEVERITY: %v/100")
        self.threat_score_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #1E293B;
                text-align: center;
                background-color: #111827;
                color: #F8FAFC;
                font-family: 'Consolas';
                font-weight: bold;
                border-radius: 2px;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #F43F5E;
            }
        """)

        det_panel.layout.addWidget(self.det_status_label)
        det_panel.layout.addWidget(self.first_det_label)
        det_panel.layout.addWidget(self.det_preview)
        det_panel.layout.addWidget(self.cls_result_label)
        det_panel.layout.addWidget(self.threat_score_bar)
        mid_layout.addWidget(det_panel)

        # Effector Matrix
        ecm_panel = DashboardPanel("EFFECTOR CONTROL MATRIX (WTA)")
        ecm_grid = QGridLayout()

        self.btn_rf_jam = QPushButton("ENGAGE RF JAMMER [2.4/5.8G]")
        self.btn_rf_jam.clicked.connect(self.trigger_rf_jam)
        self.btn_rf_jam.setStyleSheet("border-color: #F59E0B; color: #F59E0B; background: rgba(245,158,11,0.1);")

        self.btn_gps_spoof = QPushButton("ACTIVATE GNSS SPOOFING")
        self.btn_gps_spoof.clicked.connect(self.trigger_gps_spoof)
        self.btn_gps_spoof.setStyleSheet("border-color: #0EA5E9; color: #0EA5E9; background: rgba(14,165,233,0.1);")

        self.btn_kinetic = QPushButton("LAUNCH KINETIC INTERCEPTOR")
        self.btn_kinetic.clicked.connect(self.trigger_kinetic)
        self.btn_kinetic.setStyleSheet("border-color: #F43F5E; color: #F43F5E; background: rgba(244,63,94,0.15);")

        self.btn_standby = QPushButton("CEASEFIRE // ALL STANDBY")
        self.btn_standby.clicked.connect(self.disengage_countermeasures)

        ecm_grid.addWidget(self.btn_rf_jam, 0, 0)
        ecm_grid.addWidget(self.btn_gps_spoof, 0, 1)
        ecm_grid.addWidget(self.btn_kinetic, 1, 0)
        ecm_grid.addWidget(self.btn_standby, 1, 1)
        ecm_panel.layout.addLayout(ecm_grid)

        self.ecm_status_label = QLabel("EFFECTORS: ALL SYSTEMS IN READY POSTURE")
        self.ecm_status_label.setFont(QFont("Consolas", 8))
        self.ecm_status_label.setStyleSheet("color: #94A3B8;")
        ecm_panel.layout.addWidget(self.ecm_status_label)
        mid_layout.addWidget(ecm_panel)

        grid.addLayout(mid_layout, 0, 1)

        # Right Column: Radar & Perimeter
        right_layout = QVBoxLayout()
        radar_panel = DashboardPanel("3D PULSE-DOPPLER AESA RADAR")
        self.radar_widget = RadarScopeWidget()
        radar_panel.layout.addWidget(self.radar_widget)
        right_layout.addWidget(radar_panel)

        ledger_panel = DashboardPanel("FORENSIC LEDGER (SHA-256)")
        self.ledger_txt = QLabel("CHAIN INTEGRITY: 100% VERIFIED\nLAST BLOCK: #8f3a...9c12\nIMM-UKF 3D KINEMATICS ACTIVE")
        self.ledger_txt.setFont(QFont("Consolas", 8))
        self.ledger_txt.setStyleSheet("color: #0EA5E9; line-height: 1.4;")
        ledger_panel.layout.addWidget(self.ledger_txt)
        right_layout.addWidget(ledger_panel)

        grid.addLayout(right_layout, 0, 2)
        main_vbox.addLayout(grid)

        # Bottom System Bar
        metrics_panel = DashboardPanel()
        metrics_h = QHBoxLayout()
        metrics_h.setContentsMargins(4, 2, 4, 2)

        self.lbl_cpu = QLabel("CPU: 0%")
        self.lbl_mem = QLabel("MEM: 0%")
        self.lbl_gpu = QLabel("GPU: RTX 3050")
        self.lbl_fps = QLabel("FPS: 30.0")
        self.lbl_lat = QLabel("LATENCY: 28 ms")
        self.lbl_rf = QLabel("RF SENSOR: 2.4/5.8 GHz FHSS")
        self.lbl_threats = QLabel("ACTIVE TRACKS: 4")

        for lab in [self.lbl_cpu, self.lbl_mem, self.lbl_gpu, self.lbl_fps, self.lbl_lat, self.lbl_rf, self.lbl_threats]:
            lab.setFont(QFont("Consolas", 9, QFont.Bold))
            lab.setStyleSheet("color: #94A3B8;")
            metrics_h.addWidget(lab)

        metrics_panel.layout.addLayout(metrics_h)
        main_vbox.addWidget(metrics_panel)

        self.stacked_widget.addWidget(self.login_page)
        self.stacked_widget.addWidget(self.main_page)
        self.main_container.addWidget(self.stacked_widget)

        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.process_frame)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_telemetry)
        self.clock_timer.start(1000)

        self.stacked_widget.setCurrentIndex(0)

    def show_login_dialog(self):
        dlg = LoginDialog(self)
        if dlg.exec_():
            if dlg.name_input.text(): self.user_name = dlg.name_input.text()
            if dlg.profile_input.text(): self.user_profile = dlg.profile_input.text()
            self.operator_label.setText(f"OPERATOR: {self.user_name} | {self.user_profile}")
            self.countermeasure_ctrl.set_operator(self.user_name)
            self.stacked_widget.setCurrentIndex(1)
            self.start_simulation()

    def set_sensor_mode(self, mode: str):
        if self.synthetic_gen:
            self.synthetic_gen.set_display_mode(mode)
            logger.info(f"Sensor mode changed to {mode}")

    def load_video(self):
        vpath, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Video Files (*.mp4 *.avi)")
        if vpath:
            self.is_simulation_mode = False
            if self.cap: self.cap.release()
            self.cap = cv2.VideoCapture(vpath)
            self.frame_timer.start(33)

    def open_camera(self):
        self.is_simulation_mode = False
        if self.cap: self.cap.release()
        self.cap = cv2.VideoCapture(0)
        self.frame_timer.start(33)

    def start_simulation(self):
        self.is_simulation_mode = True
        if self.cap:
            self.cap.release()
            self.cap = None
        self.frame_timer.start(33)

    def process_frame(self):
        t0 = time.time()
        frame = None

        if self.is_simulation_mode and self.synthetic_gen:
            frame = self.synthetic_gen.generate_frame()
        elif self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                return

        if frame is None:
            return

        h, w = frame.shape[:2]
        tracks = self.detector.detect(frame)
        radar_ui_contacts = []

        for trk in tracks:
            cx, cy = trk.center
            dist_m = max(150.0, 3200.0 - (cy * 4.5))
            bearing_deg = (45.0 + (cx / w) * 90.0) % 360.0

            traj = self.trajectory_predictor.update_track(trk.target_id, cx, cy, est_dist_m=dist_m)
            cls_res = self.classifier.classify_crop(trk.crop, closing_speed_mps=traj.speed)

            drone_lat = 37.7749 + (cy - h // 2) * 0.00004
            drone_lon = -122.4194 + (cx - w // 2) * 0.00004
            threat_eval = self.threat_engine.evaluate_target(
                target_id=trk.target_id,
                target_lat=drone_lat,
                target_lon=drone_lon,
                classification=cls_res,
                trajectory=traj
            )

            radar_ui_contacts.append((bearing_deg, dist_m / 3500.0, threat_eval.threat_level, trk.target_id))

            # Render corner brackets and lead reticle
            col = (94, 63, 244) if threat_eval.geofence_zone == "RED" else (11, 158, 245)
            draw_corner_brackets(frame, trk.bbox, col, thickness=1)
            draw_lead_reticle(frame, (cx, cy), lead_vector=(traj.velocity_vector[0]*0.5, traj.velocity_vector[1]*0.5))

            if trk.target_id == 101 or trk == tracks[0]:
                self._current_threat = threat_eval
                self.det_status_label.setText(f"TRK #{trk.target_id}: LOCKED [{threat_eval.geofence_zone} ZONE]")
                self.first_det_label.setText(f"RANGE: {dist_m:.0f}m | SPEED: {traj.speed:.1f} m/s | TTI: {traj.time_to_impact_sec}s")
                self.cls_result_label.setText(f"TYPE: {cls_res.predicted_class}\nMODE: {traj.dominant_mode}")
                self.threat_score_bar.setValue(int(threat_eval.numerical_threat_score))

                if trk.crop is not None and trk.crop.size > 0:
                    cr = cv2.cvtColor(cv2.resize(trk.crop, (140, 140)), cv2.COLOR_BGR2RGB)
                    qcr = QImage(cr.data, 140, 140, cr.strides[0], QImage.Format_RGB888)
                    self.det_preview.setPixmap(QPixmap.fromImage(qcr))

        self.radar_widget.set_contacts(radar_ui_contacts)

        dt = time.time() - t0
        self._frame_times.append(time.time())
        if len(self._frame_times) >= 2:
            self._last_fps = (len(self._frame_times) - 1) / (self._frame_times[-1] - self._frame_times[0])
        self._last_latency = int(dt * 1000)

        # Scale and render frame
        rgb_frame = cv2.cvtColor(cv2.resize(frame, (600, 440)), cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb_frame.data, 600, 440, rgb_frame.strides[0], QImage.Format_RGB888)
        self.video_label.setPixmap(QPixmap.fromImage(qimg))

    def trigger_rf_jam(self):
        tid = self._current_threat.target_id if self._current_threat else 101
        self.countermeasure_ctrl.activate_rf_jammer(tid)
        self.ecm_status_label.setText(f"EFFECTORS: RF JAMMER ACTIVE (TRK #{tid})")
        self.audit_logger.log_event("RF_JAMMER_ENGAGED", {"target_id": tid}, operator=self.user_name)
        QMessageBox.information(self, "COUNTERMEASURE ENGAGED", f"Directional RF Jammer Activated on TRK #{tid}!")

    def trigger_gps_spoof(self):
        tid = self._current_threat.target_id if self._current_threat else 101
        self.countermeasure_ctrl.activate_gps_spoofing(tid)
        self.ecm_status_label.setText(f"EFFECTORS: GNSS SPOOFER ACTIVE (TRK #{tid})")
        self.audit_logger.log_event("GPS_SPOOF_ENGAGED", {"target_id": tid}, operator=self.user_name)
        QMessageBox.information(self, "COUNTERMEASURE ENGAGED", f"GNSS Constellation Spoofing Active on TRK #{tid}!")

    def trigger_kinetic(self):
        tid = self._current_threat.target_id if self._current_threat else 101
        self.countermeasure_ctrl.launch_kinetic_interceptor(tid)
        self.ecm_status_label.setText(f"EFFECTORS: INTERCEPTOR DISPATCHED (TRK #{tid})")
        self.audit_logger.log_event("KINETIC_LAUNCH", {"target_id": tid}, operator=self.user_name)
        QMessageBox.warning(self, "KINETIC LAUNCH AUTHORIZED", f"Interceptor Drone Dispatched against TRK #{tid}!")

    def disengage_countermeasures(self):
        self.countermeasure_ctrl.disengage_all()
        self.ecm_status_label.setText("EFFECTORS: ALL SYSTEMS IN READY POSTURE")
        self.audit_logger.log_event("CEASEFIRE_DISENGAGED", {}, operator=self.user_name)

    def update_telemetry(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        self.time_label.setText(now)
        try:
            self.lbl_cpu.setText(f"CPU: {int(psutil.cpu_percent())}%")
            self.lbl_mem.setText(f"MEM: {int(psutil.virtual_memory().percent)}%")
            self.lbl_fps.setText(f"FPS: {self._last_fps:.1f}")
            self.lbl_lat.setText(f"LATENCY: {self._last_latency} ms")
        except Exception:
            pass

    def closeEvent(self, event):
        if self.cap: self.cap.release()
        self.frame_timer.stop()
        self.clock_timer.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DesktopApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
