# CUAS (Counter-Unmanned Aerial System) — Comprehensive Project Context & Technical Specification

> **Version:** 2.5.0-Tactical  
> **Classification:** Unclassified / Defense Engineering Reference  
> **Author & Maintainer:** Shubham Pawar ([shubhampawar0610@gmail.com](mailto:shubhampawar0610@gmail.com))  
> **Repository:** [https://github.com/Shubh-creations/Counter-UAS.git](https://github.com/Shubh-creations/Counter-UAS.git)  
> **Workspace Directory:** `C:\CUAS`  

---

## 1. Executive Summary & Mission Profile

The **CUAS (Counter-Unmanned Aerial System)** is an autonomous, AI-native defense and airspace security framework designed to detect, classify, track, extrapolate trajectories for, and neutralize unauthorized or rogue unmanned aerial vehicles (UAVs / drones). 

The platform operates across three integrated operational layers:
1. **Multi-Modal Detection & Sensory Intelligence**: Ingests electro-optical/infrared (EO/IR) video, radio-frequency (RF) spectrum telemetry, and 3D pulse-Doppler radar returns.
2. **Predictive AI Core**: Uses deep CNNs for aerial object localization, drone class recognition, payload threat assessment, and a 6-state Kalman filter for trajectory and Time-to-Impact (TTI) projection.
3. **Automated Response & Actuator Control**: Dynamically enforces multi-tier defense geofencing and issues Rules of Engagement (ROE) countermeasures: directional multi-band RF Jamming, GNSS/GPS spoofing, directed optical dazzlers, and kinetic interceptor drone launch.

---

## 2. Complete Repository Directory Architecture

```text
C:\CUAS\
│
├── ai_core/                            # Deep Learning & Predictive Trajectory Modeling
│   ├── __init__.py                     # Package export declarations
│   ├── detection.py                    # Faster R-CNN & YOLOv8 detector + Synthetic flight generator
│   ├── classifier.py                   # 5-class deep drone classifier & payload variance analyzer
│   ├── trajectory_predictor.py         # 6-state Kalman filter motion estimator & path projector
│   └── response_engine.py              # Geofence breach evaluator & countermeasure recommendation matrix
│
├── sensors/                            # Sensory Data Acquisition & Track Correlation
│   ├── __init__.py                     # Package export declarations
│   ├── camera_stream.py                # Threaded, non-blocking zero-latency camera/RTSP/video streamer
│   ├── rf_sensor.py                    # RF spectrum scanner, RSSI path-loss model, protocol fingerprinter
│   ├── radar_sensor.py                 # 3D pulse-Doppler radar simulation (azimuth, range, micro-Doppler)
│   └── sensor_fusion.py                # Multi-modal track fusion hub (Vision + RF + Radar correlation)
│
├── control_unit/                       # Actuator Controls, Threat Lifecycles & Defense Auditing
│   ├── __init__.py                     # Package export declarations
│   ├── neutralization.py               # ECM actuators (RF Jammer, GNSS Spoofer, Kinetic Interceptor)
│   ├── threat_manager.py               # DEFCON state machine, alert queues & track deconfliction
│   └── audit_logger.py                 # SHA-256 cryptographically chained forensic mission logger
│
├── config/                             # Deployment & Tuning Profiles
│   ├── default_config.yaml             # Workstation/Server config (geofence coordinates, model thresholds)
│   └── jetson_config.yaml              # NVIDIA Jetson edge config (FP16, MobileNet/YOLOv8 nano)
│
├── api/                                # Remote Command & Control (C2) Subsystem
│   ├── __init__.py                     # Package export declarations
│   └── api_server.py                   # FastAPI REST endpoints, WebSocket telemetry & Web Command Center UI
│
├── utils/                              # Shared Computational & Visualization Utilities
│   ├── __init__.py                     # Package export declarations
│   ├── logger.py                       # High-performance structured logging with ANSI color coding
│   ├── geo_utils.py                    # Haversine distance, initial bearing, forward geodetic projection
│   └── visualization.py                # HUD military overlays, targeting brackets, radar scope renderer
│
├── tests/                              # Automated Unit & Integration Test Suite
│   ├── __init__.py                     # Test package initialization
│   └── test_cuas_core.py               # 11 unit tests covering geometry, AI, Kalman, sensors, & audit
│
├── data/                               # Recorded datasets & telemetry logs
│   └── README.md                       # Instructions for placing MP4, AVI, and RF log callsets
│
├── models/                             # Deep Learning Weights & Checkpoints
│   └── README.md                       # Documentation for YOLOv8n, Faster R-CNN, and custom weights
│
├── logs/                               # System execution logs & audit trails
│   └── audit/                          # Tamper-evident mission audit blockchain-style JSONL logs
│
├── cli.py                              # Unified Command-Line Interface for headless operations
├── main.py                             # PyQt5 Tactical Military Desktop Command Dashboard
├── cuda_check.py                       # Hardware acceleration & GPU benchmark utility
├── requirements.txt                    # Project Python package dependencies
├── setup.py                            # Standard setuptools packaging script
├── .gitignore                          # Exclusions for weights, logs, cache, and virtual environments
└── README.md                           # GitHub landing page documentation
```

---

## 3. Deep Dive: Module-by-Module Technical Breakdown

### 3.1 AI Core (`ai_core/`)

#### `ai_core/detection.py`
- **Class `TrackedDrone`**: Dataclass representing a tracked target: `target_id`, `bbox` `(x1, y1, x2, y2)`, `center` `(cx, cy)`, `confidence`, `class_label`, `crop` image, `first_detected_time`, `last_updated_time`.
- **Class `DroneDetector`**:
  - Supports dual backends: **PyTorch Faster R-CNN (ResNet-50 FPN)** and **Ultralytics YOLOv8**.
  - **Memory Safety & GPU Fix**: Explicitly calls `.detach().cpu().numpy()` on CUDA prediction tensors prior to casting to NumPy arrays, preventing device conversion exceptions.
  - Multi-target tracking: Employs Euclidean greedy distance association with automatic stale track eviction after `max_lost_seconds` (default: 1.5s).
- **Class `SyntheticDroneGenerator`**:
  - Generates realistic 640x480 test frames with atmospheric gradient sky, multirotor carbon arms, spinning rotor blade blur discs, and blinking infrared/red beacons. Allows fully automated regression testing without live camera or video inputs.

#### `ai_core/classifier.py`
- **Model `DeepDroneClassifier`**:
  - PyTorch neural network built upon ResNet-18 or MobileNet-V2 with custom linear classifier head producing logits across 5 classes:
    1. `SURVEILLANCE_DRONE` (Base threat weight: 0.60)
    2. `SUICIDE_DRONE` / Loitering Munition (Base threat weight: 1.00)
    3. `CIVILIAN_MULTIROTOR` (Base threat weight: 0.20)
    4. `CUSTOMIZED_DRONE` (Base threat weight: 0.85)
    5. `UNKNOWN_AIR_VEHICLE` (Base threat weight: 0.50)
- **Heuristic Feature Inspection**:
  - Calculates physical aspect ratio ($w/h$) and categorizes size (`SMALL` < 60px, `MEDIUM` 60–180px, `LARGE` > 180px).
  - Examines bottom 30% of target crop using Laplacian gradient variance to detect slung loads, bomb canisters, or drop mechanisms.
- **Threat Score Calculation**:
  $$\text{ThreatScore} = \min\left(100.0, (\text{ClassWeight} \times \text{Confidence} \times 70.0) + \text{PayloadBonus} + \text{SizeBonus}\right)$$

#### `ai_core/trajectory_predictor.py`
- **Class `KalmanFilter2D`**:
  - 6-state continuous-discrete Kalman Filter:
    $$\mathbf{x} = \begin{bmatrix} p_x & p_y & v_x & v_y & a_x & a_y \end{bmatrix}^T$$
  - State Transition Matrix $\mathbf{F}(\Delta t)$:
    $$\mathbf{F} = \begin{bmatrix}
    1 & 0 & \Delta t & 0 & \frac{1}{2}\Delta t^2 & 0 \\
    0 & 1 & 0 & \Delta t & 0 & \frac{1}{2}\Delta t^2 \\
    0 & 0 & 1 & 0 & \Delta t & 0 \\
    0 & 0 & 0 & 1 & 0 & \Delta t \\
    0 & 0 & 0 & 0 & 1 & 0 \\
    0 & 0 & 0 & 0 & 0 & 1
    \end{bmatrix}$$
  - Predicts future trajectory $N$ steps ahead (default: 35–45 frames, equivalent to ~1.5s horizon).
  - Identifies target dive attacks ($v_y > 35\text{ px/s}$) and evasive zig-zag maneuvers ($\|\mathbf{a}\| > 50\text{ px/s}^2$).

#### `ai_core/response_engine.py`
- **Class `ThreatResponseEngine`**:
  - Implements Rules of Engagement (ROE) state machine evaluating:
    1. Proximity score relative to defended asset.
    2. Classification lethality multiplier.
    3. Kinematic descent rate.
  - Determines threat priority (`SAFE`, `ADVISORY`, `ELEVATED`, `HIGH`, `CRITICAL`) and assigns countermeasure with estimated probability of success $P_{\text{success}}$.

---

### 3.2 Sensory Intelligence & Data Fusion (`sensors/`)

#### `sensors/camera_stream.py`
- **Class `CameraStream`**:
  - Background daemon thread continuously grabbing frames from hardware webcam (`cv2.VideoCapture(0)`), RTSP IP stream, prerecorded video file, or synthetic flight generator.
  - Decouples sensor acquisition from AI inference, eliminating frame lag and display latency.

#### `sensors/rf_sensor.py`
- **Class `RFSensorSimulator`**:
  - Models software-defined radio (SDR) spectrum scanning across 2400–2483.5 MHz and 5725–5850 MHz ISM bands.
  - Implements Free-Space Path Loss (FSPL) model to compute Received Signal Strength Indicator (RSSI in dBm):
    $$\text{FSPL(dB)} = 20\log_{10}(d) + 20\log_{10}(f) + 32.44$$
  - Identifies protocol telemetry signatures: DJI OcuSync-3, Lightbridge, ExpressLRS, TBS Crossfire, and MAVLink.

#### `sensors/radar_sensor.py`
- **Class `RadarSensorSimulator`**:
  - Models a continuous $360^\circ$ pulse-Doppler radar scanning at 2.0 Hz.
  - Detects radial range, azimuth bearing ($0^\circ - 360^\circ$), elevation ($5^\circ - 15^\circ$), Doppler velocity ($\text{m/s}$), Radar Cross Section ($\text{RCS}$ in $\text{dBsm}$, typically $-18$ to $-12\text{ dBsm}$ for consumer/tactical drones), and micro-Doppler rotor blade flutter.

#### `sensors/sensor_fusion.py`
- **Class `SensorFusionHub`**:
  - Integrates vision tracks, RF signatures, and radar blips into unified `FusedTacticalTrack` objects.
  - Fused Confidence Formula:
    $$\text{Confidence}_{\text{fused}} = \min(1.0, 0.45 \cdot C_{\text{visual}} + 0.30 \cdot \mathbb{I}_{\text{RF}} + 0.25 \cdot \mathbb{I}_{\text{Radar}})$$
  - Eliminates false alarms caused by birds, debris, or specular radar clutter.

---

### 3.3 Defense Command & Control (`control_unit/`)

#### `control_unit/neutralization.py`
- **Class `CountermeasureController`**:
  - Manages 4 electronic countermeasure (ECM) effectors:
    1. **Directional RF Jammer**: Saturates 2.4 GHz, 5.8 GHz, and GNSS L1 frequencies to sever drone C2 and real-time video transmission.
    2. **GNSS/GPS Spoofing Engine**: Synthesizes falsified GPS constellation ephemeris data to force target drone into automatic Return-to-Home (RTH) away from the base or trigger a controlled soft landing.
    3. **Directed Optical Dazzler**: High-intensity optical/infrared dazzler saturating target CMOS/CCD image sensors.
    4. **Kinetic Interceptor**: Autonomous defensive drone launched from base silo to intercept high-speed suicide drones.

#### `control_unit/threat_manager.py`
- **Class `ThreatManager`**:
  - Maintains DEFCON state (`DEFCON 5 [ALL CLEAR]`, `DEFCON 4 [ADVISORY]`, `DEFCON 3 [ELEVATED]`, `DEFCON 2 [WARNING]`, `DEFCON 1 [CRITICAL]`).
  - Records active threat queues, total detections, and successful neutralizations.

#### `control_unit/audit_logger.py`
- **Class `ForensicAuditLogger`**:
  - Blockchain-style immutable incident ledger storing records in `logs/audit/mission_audit_chain.jsonl`.
  - Every event block includes timestamp, event type, operator identifier, payload, and a SHA-256 hash incorporating the previous block's hash:
    $$\text{BlockHash}_i = \text{SHA256}(\text{Timestamp} + \text{EventType} + \text{Operator} + \text{Payload} + \text{BlockHash}_{i-1})$$

---

### 3.4 User Interfaces & APIs

1. **Tactical Desktop C2 GUI (`main.py`)**:
   - Built with PyQt5 adhering to military high-contrast dark theme styling (`#030703` base, `#00ff66` telemetry text, `#ff3333` alert indicators).
   - Features: Live optronic feed, 3D radar scope canvas, satellite map geofence display, AI classification breakdown, and interactive ECM buttons.
2. **Web Command Center (`http://127.0.0.1:8080/`)**:
   - Built into `api/api_server.py`.
   - Browser-accessible HTML5 Canvas interface featuring live simulated optronic feeds with projected Kalman trajectories, rotating radar scope, and interactive weapon buttons triggering live REST calls to `/api/v1/countermeasures/engage`.
3. **Headless CLI (`cli.py`)**:
   - Allows running hardware audits (`--check`), headless simulations (`--simulate --duration 15`), or launching the server (`--server --port 8080`).

---

## 4. Hardware Verification & Performance Metrics

Benchmarked on **NVIDIA GeForce RTX 3050 Laptop GPU (4GB VRAM)** running **CUDA 11.8 / PyTorch 2.7.1**:

| Benchmark Parameter | Result | Operational Requirement | Status |
| :--- | :--- | :--- | :--- |
| **Average Inference Latency** | **31.40 ms** | < 50.0 ms | **PASS (Real-Time)** |
| **Peak Throughput** | **31.8 FPS** | > 20.0 FPS | **PASS** |
| **cuDNN Acceleration** | **Enabled** | Required | **PASS** |
| **Test Suite Execution** | **11 tests in 0.021s** | 100% Pass | **PASS** |

---

## 5. Quick Reference: Operational Commands

```powershell
# 1. Open Tactical Military Desktop GUI
python main.py

# 2. Open Web Command Center
python -m uvicorn api.api_server:app --host 127.0.0.1 --port 8080
# Browse to: http://127.0.0.1:8080/

# 3. Run Headless CLI Simulation
python cli.py --simulate --duration 10

# 4. Run GPU Diagnostic Benchmark
python cuda_check.py

# 5. Run Automated Unit Tests
python -m unittest discover -s tests
```
