"""
C-UAS Military-Style Command and Control Dashboard (Enhanced Edition).
Integrates Deep Vision Detection, Real-Time Drone Classification, Kalman Trajectory Prediction,
Multi-Modal Sensor Fusion (Camera, RF, Radar), and Tactical Countermeasure Engagement.
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
    QGridLayout, QSplitter, QGraphicsDropShadowEffect, QProgressBar,
    QLineEdit, QDialog, QFormLayout, QComboBox, QCheckBox, QTabWidget,
    QTextEdit, QStackedWidget, QMessageBox, QGroupBox
)
from PyQt5.QtCore import QTimer, Qt, QSize, pyqtSignal, QThread
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
from utils.visualization import draw_corner_brackets, draw_targeting_reticle, draw_trajectory_path
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

# Custom styled military panel
class DashboardPanel(QFrame):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("dashboardPanel")
        self.setStyleSheet("""
            #dashboardPanel {
                background-color: #050805;
                border: 1px solid #1f3a1f;
                border-radius: 2px;
            }
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(8)
        shadow.setColor(QColor(0, 255, 0, 40))
        shadow.setOffset(1, 1)
        self.setGraphicsEffect(shadow)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(6)

        if title:
            title_label = QLabel(title)
            title_label.setFont(QFont("Courier New", 10, QFont.Bold))
            title_label.setStyleSheet("""
                color: #00ff66;
                padding-bottom: 4px;
                border-bottom: 1px solid #1f3a1f;
            """)
            self.layout.addWidget(title_label)


# Tactical 3D Radar Scope Widget
class RadarScopeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.setStyleSheet("background-color: #000000; border: 1px solid #1f3a1f;")
        self.sweep_angle = 0.0
        self.contacts: List[Tuple[float, float, str]] = []  # (azimuth_deg, distance_norm, threat_level)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate_sweep)
        self.timer.start(40)

    def rotate_sweep(self):
        self.sweep_angle = (self.sweep_angle + 4.5) % 360.0
        self.update()

    def set_contacts(self, contacts: List[Tuple[float, float, str]]):
        self.contacts = contacts
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w // 2, cy = h // 2
        radius = min(cx, cy) - 10

        # Background
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        # Range rings
        painter.setPen(QPen(QColor(0, 80, 0), 1))
        for r_factor in [0.33, 0.66, 1.0]:
            r_curr = int(radius * r_factor)
            painter.drawEllipse(cx - r_curr, cy - r_curr, r_curr * 2, r_curr * 2)

        # Crosshairs
        painter.drawLine(cx - radius, cy, cx + radius, cy)
        painter.drawLine(cx, cy - radius, cx, cy + radius)

        # Radar labels
        painter.setPen(QColor(0, 180, 0))
        painter.setFont(QFont("Courier New", 7))
        painter.drawText(cx + 4, cy - radius + 12, "3.5km")
        painter.drawText(cx + 4, cy - int(radius * 0.66) + 12, "2.0km")
        painter.drawText(cx + 4, cy - int(radius * 0.33) + 12, "1.0km")

        # Rotating beam
        rad = math.radians(self.sweep_angle - 90)
        bx = int(cx + radius * math.cos(rad))
        by = int(cy + radius * math.sin(rad))
        painter.setPen(QPen(QColor(0, 255, 60), 2))
        painter.drawLine(cx, cy, bx, by)

        # Contacts
        for az_deg, dist_ratio, level in self.contacts:
            c_rad = math.radians(az_deg - 90)
            c_r = max(10, min(radius, int(radius * dist_ratio)))
            px = int(cx + c_r * math.cos(c_rad))
            py = int(cy + c_r * math.sin(c_rad))

            if level in ["CRITICAL", "HIGH"]:
                p_col = QColor(255, 0, 0)
            elif level == "ELEVATED":
                p_col = QColor(255, 180, 0)
            else:
                p_col = QColor(0, 255, 0)

            painter.setBrush(QBrush(p_col))
            painter.setPen(QPen(p_col, 1))
            painter.drawEllipse(px - 4, py - 4, 8, 8)


# Military Satellite Map View
class SatelliteMapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(250, 180)
        self.setStyleSheet("background-color: #000000; border: 1px solid #1f3a1f;")
        self.latitude = 37.7749
        self.longitude = -122.4194
        self.drone_lat = None
        self.drone_lon = None
        self.threat_zone = "GREEN"

        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self.update)
        self.blink_timer.start(500)
        self.blink_state = True

    def set_coordinates(self, lat: float, lng: float, drone_lat: Optional[float] = None, drone_lon: Optional[float] = None, zone: str = "GREEN"):
        self.latitude = lat
        self.longitude = lng
        self.drone_lat = drone_lat
        self.drone_lon = drone_lon
        self.threat_zone = zone
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(2, 6, 2))

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        # Grid lines
        painter.setPen(QPen(QColor(0, 60, 0), 1, Qt.DotLine))
        for y in range(0, h, 25):
            painter.drawLine(0, y, w, y)
        for x in range(0, w, 25):
            painter.drawLine(x, 0, x, h)

        # Defense Rings around Base (Center)
        # Outer
        painter.setPen(QPen(QColor(0, 150, 0), 1))
        painter.drawEllipse(cx - 70, cy - 70, 140, 140)
        # Warning
        painter.setPen(QPen(QColor(180, 140, 0), 1, Qt.DashLine))
        painter.drawEllipse(cx - 45, cy - 45, 90, 90)
        # Killzone
        painter.setPen(QPen(QColor(200, 0, 0), 1, Qt.DashLine))
        painter.drawEllipse(cx - 20, cy - 20, 40, 40)

        # Base icon
        painter.setBrush(QBrush(QColor(0, 255, 100)))
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawRect(cx - 4, cy - 4, 8, 8)
        painter.drawText(cx + 8, cy + 4, "HQ BASE")

        # Drone Target Marker
        if self.drone_lat is not None and self.drone_lon is not None and self.blink_state:
            d_lat = self.drone_lat - self.latitude
            d_lon = self.drone_lon - self.longitude
            dx = int(cx + (d_lon * 12000.0))
            dy = int(cy - (d_lat * 12000.0))
            dx = max(10, min(w - 10, dx))
            dy = max(10, min(h - 10, dy))

            d_col = QColor(255, 0, 0) if self.threat_zone == "RED" else QColor(255, 180, 0)
            painter.setBrush(QBrush(d_col))
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.drawEllipse(dx - 5, dy - 5, 10, 10)
            painter.drawText(dx + 8, dy + 4, f"TARGET [{self.threat_zone}]")


# Login Dialog
class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CUAS MILITARY ACCESS AUTHENTICATION")
        self.setFixedSize(450, 280)
        self.setStyleSheet("""
            QDialog {
                background-color: #030803;
                border: 2px solid #00ff66;
            }
            QLabel {
                color: #00ff66;
                font-family: 'Courier New';
                font-weight: bold;
            }
            QLineEdit {
                background-color: #0a140a;
                color: #ffffff;
                border: 1px solid #00ff66;
                padding: 6px;
                font-family: 'Courier New';
                font-size: 13px;
            }
            QPushButton {
                background-color: #002200;
                color: #00ff66;
                border: 1px solid #00ff66;
                padding: 10px;
                font-family: 'Courier New';
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #004400;
                color: #ffffff;
            }
        """)

        layout = QVBoxLayout(self)
        title = QLabel("C-UAS DEFENSE COMMAND")
        title.setFont(QFont("Courier New", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. CDR. SHUBHAM PAWAR")
        name_lbl = QLabel("OPERATOR ID:")
        form.addRow(name_lbl, self.name_input)

        self.profile_input = QLineEdit()
        self.profile_input.setPlaceholderText("e.g. DEFCON-1 TACTICAL CONTROLLER")
        profile_lbl = QLabel("SECURITY CLEARANCE:")
        form.addRow(profile_lbl, self.profile_input)

        layout.addLayout(form)
        layout.addSpacing(15)

        login_btn = QPushButton("AUTHENTICATE & ENTER C2 SYSTEM")
        login_btn.clicked.connect(self.accept)
        layout.addWidget(login_btn)


# Main C2 Application Window
class DesktopApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CUAS - Counter-UAS Autonomous Defense Command (AI-Native)")
        self.setMinimumSize(1300, 850)

        # Initialize AI Core, Sensors, and Control subsystems
        self.detector = DroneDetector(confidence_threshold=0.55, device="auto")
        self.classifier = DroneClassifierEngine(device="auto")
        self.trajectory_predictor = TrajectoryPredictor(history_len=25, forecast_steps=35, fps=30.0)
        self.threat_engine = ThreatResponseEngine()
        self.threat_mgr = ThreatManager()
        self.rf_sensor = RFSensorSimulator()
        self.radar_sensor = RadarSensorSimulator()
        self.fusion_hub = SensorFusionHub()
        self.countermeasure_ctrl = CountermeasureController()
        self.audit_logger = ForensicAuditLogger()

        self.synthetic_gen: Optional[SyntheticDroneGenerator] = None
        self.is_simulation_mode = False
        self.cap: Optional[cv2.VideoCapture] = None

        self.user_name = "CDR. S. PAWAR"
        self.user_profile = "DEFCON-1 CONTROLLER"

        # Performance counters
        self._frame_times = deque(maxlen=60)
        self._last_fps = 0.0
        self._last_latency = 0
        self._current_classification: Optional[DroneClassificationResult] = None
        self._current_threat: Optional[ThreatEvaluation] = None

        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #030703;
                color: #d0ffd0;
                font-family: 'Courier New';
            }
            QLabel {
                color: #d0ffd0;
            }
            QPushButton {
                background-color: #081a08;
                color: #00ff66;
                border: 1px solid #00aa44;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #003311;
                border: 1px solid #00ff66;
            }
            QPushButton:disabled {
                background-color: #0a0e0a;
                color: #335533;
                border: 1px solid #1a2a1a;
            }
            QMenuBar {
                background-color: #000000;
                color: #00ff66;
                border-bottom: 1px solid #1f3a1f;
            }
            QMenuBar::item:selected {
                background-color: #003311;
            }
        """)

        self.main_container = QVBoxLayout(self)
        self.main_container.setContentsMargins(0, 0, 0, 0)
        self.stacked_widget = QStackedWidget()

        # Login Screen
        self.login_page = QWidget()
        login_vbox = QVBoxLayout(self.login_page)
        login_vbox.setAlignment(Qt.AlignCenter)

        title = QLabel("C-UAS AUTONOMOUS DEFENSE COMMAND CENTER")
        title.setFont(QFont("Courier New", 22, QFont.Bold))
        title.setStyleSheet("color: #00ff66; margin-bottom: 20px;")
        login_vbox.addWidget(title)

        auth_btn = QPushButton("INITIATE DEFENSE AUTHENTICATION")
        auth_btn.setFont(QFont("Courier New", 14, QFont.Bold))
        auth_btn.setFixedSize(420, 50)
        auth_btn.clicked.connect(self.show_login_dialog)
        login_vbox.addWidget(auth_btn)

        # Main C2 Screen
        self.main_page = QWidget()
        main_vbox = QVBoxLayout(self.main_page)
        main_vbox.setContentsMargins(8, 8, 8, 8)
        main_vbox.setSpacing(8)

        # Menu Bar
        self.menu_bar = QMenuBar(self)
        file_menu = self.menu_bar.addMenu("FILE")
        act_video = QAction("Open Video File", self)
        act_cam = QAction("Open Live Camera", self)
        act_sim = QAction("Launch Tactical Simulation", self)
        file_menu.addAction(act_video)
        file_menu.addAction(act_cam)
        file_menu.addAction(act_sim)

        act_video.triggered.connect(self.load_video)
        act_cam.triggered.connect(self.open_camera)
        act_sim.triggered.connect(self.start_simulation)

        tools_menu = self.menu_bar.addMenu("ECM WEAPONS")
        act_disengage = QAction("Emergency Disengage All Effectors", self)
        act_disengage.triggered.connect(self.disengage_countermeasures)
        tools_menu.addAction(act_disengage)

        main_vbox.setMenuBar(self.menu_bar)

        # Header Bar
        header = QHBoxLayout()
        self.operator_label = QLabel(f"OPERATOR: {self.user_name} | CLEARANCE: {self.user_profile}")
        self.operator_label.setFont(QFont("Courier New", 11, QFont.Bold))
        self.operator_label.setStyleSheet("color: #00ff66;")

        self.defcon_label = QLabel("DEFCON: 5 [ALL CLEAR]")
        self.defcon_label.setFont(QFont("Courier New", 12, QFont.Bold))
        self.defcon_label.setStyleSheet("color: #00ff66; padding: 2px 8px; border: 1px solid #00ff66;")

        self.time_label = QLabel()
        self.time_label.setFont(QFont("Courier New", 11, QFont.Bold))

        header.addWidget(self.operator_label)
        header.addStretch()
        header.addWidget(self.defcon_label)
        header.addSpacing(20)
        header.addWidget(self.time_label)
        main_vbox.addLayout(header)

        # Content Split Layout
        grid = QGridLayout()
        grid.setSpacing(10)

        # Left Column: Video Feed & Targeting Reticle
        video_panel = DashboardPanel("TACTICAL OPTRONIC SENSOR (LIVE FEED)")
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("border: 1px solid #1f3a1f; background-color: #000000;")
        video_panel.layout.addWidget(self.video_label)
        grid.addWidget(video_panel, 0, 0, 2, 1)

        # Middle Column: Detection & Classification
        mid_layout = QVBoxLayout()

        det_panel = DashboardPanel("AI TARGET CLASSIFICATION")
        self.det_status_label = QLabel("STATUS: SCANNING AIRSPACE")
        self.det_status_label.setFont(QFont("Courier New", 11, QFont.Bold))

        self.first_det_label = QLabel("FIRST CONTACT: NONE")
        self.first_det_label.setFont(QFont("Courier New", 9))

        self.det_preview = QLabel("NO ACTIVE TARGET LOCK")
        self.det_preview.setAlignment(Qt.AlignCenter)
        self.det_preview.setFixedSize(160, 160)
        self.det_preview.setStyleSheet("border: 1px solid #00aa44; background-color: #000000;")

        self.cls_result_label = QLabel("CLASSIFICATION: STANDBY")
        self.cls_result_label.setFont(QFont("Courier New", 11, QFont.Bold))

        self.threat_score_bar = QProgressBar()
        self.threat_score_bar.setRange(0, 100)
        self.threat_score_bar.setValue(0)
        self.threat_score_bar.setTextVisible(True)
        self.threat_score_bar.setFormat("THREAT SEVERITY: %v/100")
        self.threat_score_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #00aa44;
                text-align: center;
                background-color: #001100;
                color: #ffffff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #cc0000;
            }
        """)

        det_panel.layout.addWidget(self.det_status_label)
        det_panel.layout.addWidget(self.first_det_label)
        det_panel.layout.addWidget(self.det_preview)
        det_panel.layout.addWidget(self.cls_result_label)
        det_panel.layout.addWidget(self.threat_score_bar)
        mid_layout.addWidget(det_panel)

        # Countermeasure Action Center
        ecm_panel = DashboardPanel("ELECTRONIC COUNTERMEASURES (ECM)")
        ecm_grid = QGridLayout()

        self.btn_rf_jam = QPushButton("ENGAGE RF JAMMER (2.4/5.8G)")
        self.btn_rf_jam.clicked.connect(self.trigger_rf_jam)
        self.btn_rf_jam.setStyleSheet("background-color: #2b1100; color: #ffaa00; border: 1px solid #ffaa00;")

        self.btn_gps_spoof = QPushButton("ACTIVATE GNSS SPOOFING")
        self.btn_gps_spoof.clicked.connect(self.trigger_gps_spoof)
        self.btn_gps_spoof.setStyleSheet("background-color: #001a2b; color: #00bbff; border: 1px solid #00bbff;")

        self.btn_kinetic = QPushButton("LAUNCH INTERCEPTOR DRONE")
        self.btn_kinetic.clicked.connect(self.trigger_kinetic)
        self.btn_kinetic.setStyleSheet("background-color: #330000; color: #ff3333; border: 1px solid #ff3333;")

        self.btn_standby = QPushButton("ALL STANDBY / DISENGAGE")
        self.btn_standby.clicked.connect(self.disengage_countermeasures)

        ecm_grid.addWidget(self.btn_rf_jam, 0, 0)
        ecm_grid.addWidget(self.btn_gps_spoof, 0, 1)
        ecm_grid.addWidget(self.btn_kinetic, 1, 0)
        ecm_grid.addWidget(self.btn_standby, 1, 1)
        ecm_panel.layout.addLayout(ecm_grid)

        self.ecm_status_label = QLabel("EFFECTORS: ALL SYSTEMS IN STANDBY")
        self.ecm_status_label.setFont(QFont("Courier New", 9))
        ecm_panel.layout.addWidget(self.ecm_status_label)
        mid_layout.addWidget(ecm_panel)

        grid.addLayout(mid_layout, 0, 1)

        # Right Column: Radar Scope & Geospatial Map
        right_layout = QVBoxLayout()

        radar_panel = DashboardPanel("3D PULSE-DOPPLER RADAR")
        self.radar_widget = RadarScopeWidget()
        radar_panel.layout.addWidget(self.radar_widget)
        right_layout.addWidget(radar_panel)

        map_panel = DashboardPanel("GEOSPATIAL PERIMETER DEFENSE")
        self.coord_label = QLabel("BASE COORD: 37.7749° N, 122.4194° W")
        self.coord_label.setFont(QFont("Courier New", 9, QFont.Bold))
        map_panel.layout.addWidget(self.coord_label)

        self.map_widget = SatelliteMapWidget()
        map_panel.layout.addWidget(self.map_widget)
        right_layout.addWidget(map_panel)

        grid.addLayout(right_layout, 0, 2)
        main_vbox.addLayout(grid)

        # Bottom System Metrics Bar
        metrics_panel = DashboardPanel("SYSTEM TELEMETRY & MULTI-SENSOR STATUS")
        metrics_h = QHBoxLayout()

        self.lbl_cpu = QLabel("CPU: 0%")
        self.lbl_mem = QLabel("MEM: 0%")
        self.lbl_gpu = QLabel("GPU: RTX 3050")
        self.lbl_fps = QLabel("FPS: 0.0")
        self.lbl_lat = QLabel("LATENCY: 0 ms")
        self.lbl_rf = QLabel("RF SENSOR: SCANNING 2.4/5.8G")
        self.lbl_threats = QLabel("ACTIVE TARGETS: 0")

        for lab in [self.lbl_cpu, self.lbl_mem, self.lbl_gpu, self.lbl_fps, self.lbl_lat, self.lbl_rf, self.lbl_threats]:
            lab.setFont(QFont("Courier New", 9, QFont.Bold))
            metrics_h.addWidget(lab)

        metrics_panel.layout.addLayout(metrics_h)
        main_vbox.addWidget(metrics_panel)

        # Add pages
        self.stacked_widget.addWidget(self.login_page)
        self.stacked_widget.addWidget(self.main_page)
        self.main_container.addWidget(self.stacked_widget)

        # Frame Processing Timer
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.process_frame)

        # Time & Metrics Timer
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_telemetry)
        self.clock_timer.start(1000)

        # Start with login screen
        self.stacked_widget.setCurrentIndex(0)

    def show_login_dialog(self):
        dlg = LoginDialog(self)
        if dlg.exec_():
            if dlg.name_input.text():
                self.user_name = dlg.name_input.text()
            if dlg.profile_input.text():
                self.user_profile = dlg.profile_input.text()
            self.operator_label.setText(f"OPERATOR: {self.user_name} | CLEARANCE: {self.user_profile}")
            self.countermeasure_ctrl.set_operator(self.user_name)
            self.stacked_widget.setCurrentIndex(1)
            # Auto-start simulation by default so operator sees live defense action immediately
            self.start_simulation()

    def load_video(self):
        video_path, _ = QFileDialog.getOpenFileName(self, "Select Video File", "", "Video Files (*.mp4 *.avi *.mkv)")
        if video_path:
            self.is_simulation_mode = False
            self.synthetic_gen = None
            if self.cap:
                self.cap.release()
            self.cap = cv2.VideoCapture(video_path)
            self.frame_timer.start(33)
            logger.info(f"Opened video file: {video_path}")

    def open_camera(self):
        self.is_simulation_mode = False
        self.synthetic_gen = None
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(0)
        self.frame_timer.start(33)
        logger.info("Opened live camera index 0.")

    def start_simulation(self):
        self.is_simulation_mode = True
        self.synthetic_gen = SyntheticDroneGenerator(width=640, height=480)
        if self.cap:
            self.cap.release()
            self.cap = None
        self.frame_timer.start(33)
        logger.info("Tactical flight simulation initialized.")

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

        # 1. Optical Detection
        tracks = self.detector.detect(frame)

        # 2. Multi-Sensor Simulation (RF & Radar)
        radar_contacts = []
        rf_emissions = []
        radar_ui_contacts = []

        if tracks:
            primary_track = tracks[0]
            cx, cy = primary_track.center

            # Estimate simulated distance and bearing from pixel coordinates
            dist_m = max(200.0, 3200.0 - (cy * 4.5))
            bearing_deg = (45.0 + (cx / w) * 90.0) % 360.0

            rf_emissions = self.rf_sensor.scan_spectrum(simulated_target_bearing=bearing_deg, distance_m=dist_m)
            radar_contacts = self.radar_sensor.scan_for_contacts(target_range_m=dist_m, target_azimuth_deg=bearing_deg)

            # 3. Trajectory Prediction
            traj = self.trajectory_predictor.update_track(primary_track.target_id, cx, cy)
            history_pts = self.trajectory_predictor.get_history(primary_track.target_id)

            # 4. Deep Drone Classification
            if primary_track.crop is not None and primary_track.crop.size > 0:
                cls_result = self.classifier.classify_crop(primary_track.crop)
                self._current_classification = cls_result
            else:
                cls_result = self._current_classification

            # 5. Threat Evaluation
            drone_lat = 37.7749 + (cy - h // 2) * 0.00004
            drone_lon = -122.4194 + (cx - w // 2) * 0.00004
            threat_eval = self.threat_engine.evaluate_target(
                target_id=primary_track.target_id,
                target_lat=drone_lat,
                target_lon=drone_lon,
                classification=cls_result,
                trajectory=traj
            )
            self._current_threat = threat_eval
            self.threat_mgr.update_threat(threat_eval)

            # Update Map & Radar UI
            self.map_widget.set_coordinates(37.7749, -122.4194, drone_lat, drone_lon, threat_eval.geofence_zone)
            radar_ui_contacts.append((bearing_deg, dist_m / 3500.0, threat_eval.threat_level))

            # Render Military Target Reticle & Trajectory onto Frame
            draw_corner_brackets(frame, primary_track.bbox, (0, 0, 255) if threat_eval.geofence_zone == "RED" else (0, 255, 0))
            draw_targeting_reticle(frame, (cx, cy), radius=28, threat_level=threat_eval.threat_level)
            draw_trajectory_path(frame, history_pts, traj.predicted_path)

            # Update Right Dashboard Info
            self.det_status_label.setText(f"TARGET #{primary_track.target_id}: LOCKED [{threat_eval.geofence_zone} ZONE]")
            self.first_det_label.setText(f"RANGE: {threat_eval.distance_to_base_m:.0f}m | BEARING: {threat_eval.bearing_from_base_deg:.1f}°")

            if cls_result:
                self.cls_result_label.setText(f"TYPE: {cls_result.predicted_class}\nCONF: {cls_result.confidence*100:.1f}%")
                self.threat_score_bar.setValue(int(threat_eval.numerical_threat_score))

            # Crop Preview
            if primary_track.crop is not None and primary_track.crop.size > 0:
                cr_rgb = cv2.cvtColor(cv2.resize(primary_track.crop, (160, 160)), cv2.COLOR_BGR2RGB)
                qimg_crop = QImage(cr_rgb.data, 160, 160, cr_rgb.strides[0], QImage.Format_RGB888)
                self.det_preview.setPixmap(QPixmap.fromImage(qimg_crop))

            # Auto-DEFCON update
            if threat_eval.threat_level == "CRITICAL":
                self.defcon_label.setText("DEFCON: 1 [CRITICAL ENGAGEMENT]")
                self.defcon_label.setStyleSheet("color: #ff0000; border: 1px solid #ff0000; font-weight: bold;")
            elif threat_eval.threat_level == "HIGH":
                self.defcon_label.setText("DEFCON: 2 [WARNING BREACH]")
                self.defcon_label.setStyleSheet("color: #ffaa00; border: 1px solid #ffaa00; font-weight: bold;")
            else:
                self.defcon_label.setText("DEFCON: 4 [ACTIVE TRACK]")
                self.defcon_label.setStyleSheet("color: #00ff66; border: 1px solid #00ff66;")

            # RF Telemetry update
            if rf_emissions:
                rf = rf_emissions[0]
                self.lbl_rf.setText(f"RF: {rf.protocol} [{rf.frequency_mhz:.0f}MHz, {rf.rssi_dbm:.0f}dBm]")

        else:
            self.det_status_label.setText("STATUS: SCANNING AIRSPACE")
            self.threat_score_bar.setValue(0)
            self.defcon_label.setText("DEFCON: 5 [ALL CLEAR]")
            self.defcon_label.setStyleSheet("color: #00ff66; border: 1px solid #00ff66;")

        self.radar_widget.set_contacts(radar_ui_contacts)

        # Measure timing
        dt = time.time() - t0
        self._frame_times.append(time.time())
        if len(self._frame_times) >= 2:
            self._last_fps = (len(self._frame_times) - 1) / (self._frame_times[-1] - self._frame_times[0])
        self._last_latency = int(dt * 1000)

        # Overlay corner brackets & HUD onto video feed
        cv2.putText(frame, f"FPS: {self._last_fps:.1f} | LAT: {self._last_latency}ms", (12, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 60), 1)

        # Convert frame to QImage and display
        rgb_frame = cv2.cvtColor(cv2.resize(frame, (640, 480)), cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb_frame.data, 640, 480, rgb_frame.strides[0], QImage.Format_RGB888)
        self.video_label.setPixmap(QPixmap.fromImage(qimg))

    def trigger_rf_jam(self):
        target_id = self._current_threat.target_id if self._current_threat else 1
        res = self.countermeasure_ctrl.activate_rf_jammer(target_id)
        self.ecm_status_label.setText(f"EFFECTORS: RF JAMMER ACTIVE (TARGET #{target_id})")
        self.audit_logger.log_event("RF_JAMMER_ENGAGED", {"target_id": target_id}, operator=self.user_name)
        QMessageBox.information(self, "COUNTERMEASURE ENGAGED", f"Directional RF Jammer Activated on Target #{target_id}!\nCommand link disruption active.")

    def trigger_gps_spoof(self):
        target_id = self._current_threat.target_id if self._current_threat else 1
        res = self.countermeasure_ctrl.activate_gps_spoofing(target_id)
        self.ecm_status_label.setText(f"EFFECTORS: GNSS SPOOFER ACTIVE (TARGET #{target_id})")
        self.audit_logger.log_event("GPS_SPOOFING_ENGAGED", {"target_id": target_id}, operator=self.user_name)
        QMessageBox.information(self, "COUNTERMEASURE ENGAGED", f"GNSS Spoofing Active on Target #{target_id}!\nTransmitting simulated forced-return coordinates.")

    def trigger_kinetic(self):
        target_id = self._current_threat.target_id if self._current_threat else 1
        res = self.countermeasure_ctrl.launch_kinetic_interceptor(target_id)
        self.ecm_status_label.setText(f"EFFECTORS: INTERCEPTOR DISPATCHED (TARGET #{target_id})")
        self.audit_logger.log_event("KINETIC_LAUNCH", {"target_id": target_id}, operator=self.user_name)
        QMessageBox.warning(self, "KINETIC LAUNCH AUTHORIZED", f"Interceptor Drone Dispatched from Silo Alpha against Target #{target_id}!")

    def disengage_countermeasures(self):
        self.countermeasure_ctrl.disengage_all()
        self.ecm_status_label.setText("EFFECTORS: ALL SYSTEMS IN STANDBY")
        self.audit_logger.log_event("EFFECTORS_DISENGAGED", {}, operator=self.user_name)

    def update_telemetry(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(now)

        try:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            self.lbl_cpu.setText(f"CPU: {int(cpu)}%")
            self.lbl_mem.setText(f"MEM: {int(mem)}%")
            self.lbl_fps.setText(f"FPS: {self._last_fps:.1f}")
            self.lbl_lat.setText(f"LATENCY: {self._last_latency} ms")
            summary = self.threat_mgr.get_summary()
            self.lbl_threats.setText(f"ACTIVE TARGETS: {summary['active_threat_count']}")
        except Exception:
            pass

    def closeEvent(self, event):
        if self.cap:
            self.cap.release()
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
