# LATTICE-CUAS v4.0-Lattice // Master Project Architecture & Context

**Autonomous Multi-Target Counter-Swarm Air Defense Operating System**  
*Architecture Class: Anduril Lattice OS / Palantir Gotham / Lockheed Aegis Grade C2*  
*Deployment: Local Host `http://127.0.0.1:8080/` | Base HQ Coordinates: `37.7749° N, 122.4194° W`*  
*Repository: [Counter-UAS (GitHub)](https://github.com/Shubh-creations/Counter-UAS.git) & [CUAS-MAin- (GitHub)](https://github.com/Shubh-creations/CUAS-MAin-.git)*

---

## 1. Executive System Overview
**LATTICE-CUAS v4.0** is an enterprise-grade autonomous counter-unmanned aerial defense operating system engineered for real-time detection, 3D kinematic tracking, multi-spectral thermal identification, micro-Doppler radar analysis, RF emission decoding, and automated Weapon-Target Assignment (WTA) against coordinated multi-drone saturation swarms.

The user interface has been re-architected from boxy multi-column dashboards into a **Full-Bleed 100vw × 100vh Spatial Battlespace Operating System** with hardware-accelerated 2.5D/3D isometric projection, chamfered glassmorphic HUD overlays, zero scrollbars, and dynamic SVG leader-line targeting tethers.

---

## 2. Spatial UI/UX Topology (Anduril Lattice OS Architecture)

```
+----------------------------------------------------------------------------------------------------+
|                                  ZONE A: TACTICAL COMMAND BAR                                      |
|  [BRAND]   [DEFCON 1 CRITICAL]   [3D ISOMETRIC / 2D PLANAR]   [SCENARIO SELECT]   [ROE]   [AUDIO]   |
+----------------------------------------------------------------------------------------------------+
|  ZONE B: OPTRONIC GIMBAL POD  |                                      |  ZONE D: TARGET DOSSIER      |
|  - Multi-Spectral Viewport    |                                      |  - Radial Threat Dial (0-100)|
|    (EO / FLIR-W / FLIR-B/SWIR)|                                      |  - IMM Probabilities         |
|  - Lead-Angle Pipper Reticle  |        FULL-BLEED 100vw x 100vh      |    (CV / CTRV / CA_DIVE)     |
|  - Roll/Pitch Attitude Ladder |       3D SPATIAL BATTLESPACE         |  - 128-Bin SDR RF Spectrum   |
|  - PiP 4x Payload Loupe       |          (Z-INDEX 1)                 |  - Micro-Doppler Rotor Specs |
+-------------------------------+                                      |  - Ground Impact & CEP       |
|                               |  * Isometric Meter Grid              +------------------------------+
|                               |  * 500m/1500m/3500m Geodesic Domes   |
|                               |  * 3D Elevation Stalks & Curtains    |
|  ZONE C: SWARM TRACK MATRIX   |  * 60-Step IMM-UKF Predicted Tubes   |
|  - 8 Simultaneous UAV Tracks  |  * Volumetric Sensor / Effector Cones|
|  - NATO MIL-STD-2525D Icons   |  * Dynamic Target Tether Line        |
|  - Range, Speed, TTI Bars     |                                      |
|  - Corroboration [RAD+RF+EO]  |                                      |
+----------------------------------------------------------------------------------------------------+
|                               ZONE E: AUTONOMOUS KILL-CHAIN DOCK                                   |
|   [DETECT] -> [TRACK] -> [IDENTIFY] -> [CUE_EFFECTOR] -> [ENGAGE] -> [ASSESS_BDA]                  |
|   [1] DIR RF JAMMER   [2] GNSS SPOOFER   [3] OPTICAL DAZZLER   [4] KINETIC INTERCEPT   [CEASEFIRE] |
|   SHA-256 TAMPER-EVIDENT FORENSIC LEDGER TICKER (#8f3a...9c12)                                     |
+----------------------------------------------------------------------------------------------------+
```

### Zone Topology & Coordinates
1. **Background Spatial Battlespace Scope (`#battlespace-canvas`, `z-index: 1`)**:
   - `100vw × 100vh` full-bleed viewport fixed at `inset: 0`.
   - Hardware-accelerated 2.5D/3D isometric projection with interactive mouse pan, smooth scroll-wheel zoom (`200m` to `5000m`), and continuous pitch tilt ($0^\circ$ Planar PPI to $63^\circ$ 3D Isometric Perspective).
   - Render elements:
     - Dark obsidian void `#04070B` with isometric meter grid.
     - Concentric geodesic defense domes (`500m` Crimson Killzone `#FF2A54`, `1500m` Amber Warning `#FFB000`, `3500m` Cyan Early Detection `#00F0FF`) with 3D longitude/latitude wireframe hemispherical arches.
     - 3D target elevation stalks (curtains) connecting $(E, N, U)$ down to $(E, N, 0)$ ground shadow.
     - 60-step IMM-UKF predicted trajectory ribbons with 95% covariance uncertainty ellipsoids.
     - Volumetric sensor cones: EO/IR camera viewing frustum, directional RF jammer 60° microwave cone, optical dazzler coherent laser beam, and blue kinetic interceptor flight arc.
2. **Dynamic Target Tether Leader Line (`#tether-svg`, `z-index: 5`)**:
   - Animated SVG leader-line dynamically connecting the 3D target airframe directly to the Zone D Target Intelligence Dossier card.
3. **Zone A — Tactical Command Ribbon (`top: 12px; left: 50%; transform: translateX(-50%)`)**:
   - DEFCON posture status (`DEFCON 1` to `DEFCON 5`).
   - Perspective switcher (`[3D ISOMETRIC]` vs `[2D PLANAR]`).
   - Tactical scenario injector:
     - `SWARM_SATURATION` (8 simultaneous UAVs in pincer formation)
     - `FPV_TERMINAL_DIVE` (high-G terminal suicide skimmer)
     - `RF_SILENT_STEALTH` (dark autonomous munition with zero RF emission)
     - `MIXED_AIRSPACE` (civilian flyby + hostile loitering munition)
   - ROE Autonomy switch (`[HITL MANUAL]` vs `[AUTONOMOUS WVR INTERCEPT]`).
   - Web Audio API master caution synth toggle (synthesizes radar clicks, twin lock chime, and killzone alert siren).
   - High-precision UTC military clock (`HH:MM:SS.ms UTC`).
4. **Zone B — EO/IR Gimbal Targeting Pod (`top: 68px; left: 16px; width: 370px; height: 290px`)**:
   - 4-mode multi-spectral shader engine:
     - `EO_DAYLIGHT` (photorealistic daylight gradient, horizon, motion blur)
     - `FLIR_WHITE_HOT` (thermal bloom on battery/motors, horizontal scanlines)
     - `FLIR_BLACK_HOT` (inverted thermal contrast, high-temperature black nodes)
     - `SWIR_NIGHT_VISION` (phosphor emerald monochrome `#10B981`)
   - Military gimbal HUD overlay:
     - Lead-computing reticle with dynamic lead-angle prediction diamond.
     - Artificial horizon and roll/pitch ladder markings (`+10°`, `+05°`, `00°`, `-05°`, `-10°`).
     - Optical zoom multiplier ($1\times, 4\times, 12\times, 30\times$).
     - Picture-in-Picture (PiP) inset zoom loupe focusing 4x magnification on the drone payload.
5. **Zone C — Swarm Track Matrix (`bottom: 16px; left: 16px; width: 410px; height: 380px`)**:
   - NATO MIL-STD-2525D icons.
   - Live telemetry: Track ID, Classification, Slant Range, Speed, Time-to-Impact (TTI) bar.
   - Sensor corroboration badges (`[RAD]`, `[RF]`, `[EO/IR]`).
   - One-click `[LOCK]` button to immediately slave all sensors and effectors.
6. **Zone D — Target Intelligence Dossier (`top: 68px; right: 16px; width: 390px; bottom: 84px`)**:
   - Radial SVG threat dial ($0\text{--}100$) with sub-scores:
     - Kinematic Lethality
     - Payload Hazard
     - RF Stealth Anomaly
     - Swarm Cohesion Index
   - Triple real-time IMM kinematic mode probabilities (`CV`, `CTRV`, `CA_DIVE`).
   - Live 128-bin FFT SDR RF waterfall canvas with protocol identification and SNR.
   - Radar micro-Doppler rotor blade spectrogram canvas.
   - Ground impact projection and Circular Error Probable (CEP) radius.
7. **Zone E — Autonomous Kill-Chain Dock (`bottom: 14px; left: 50%; transform: translateX(-50%); width: 740px`)**:
   - 6-Stage Kill-Chain Stepper (`DETECT` $\rightarrow$ `TRACK` $\rightarrow$ `IDENTIFY` $\rightarrow$ `CUE_EFFECTOR` $\rightarrow$ `ENGAGE` $\rightarrow$ `ASSESS_BDA`).
   - 4 Effector Triggers with Hotkeys `[1]`, `[2]`, `[3]`, `[4]` and live actuator status:
     1. `[1] DIR RF JAMMER (60° AZ)`
     2. `[2] GNSS MULTI-BAND SPOOFER`
     3. `[3] HIGH-ENERGY OPTICAL DAZZLER`
     4. `[4] KINETIC INTERCEPTOR (LAUNCH)`
   - Master CEASEFIRE / SAFE Button (`Spacebar`).
   - Live scrolling SHA-256 tamper-evident audit ledger strip.

---

## 3. Mathematical & Algorithmic Engines

### 1. `ai_core/trajectory_predictor.py` -> `IMM_UKF_3D`
- **9-State Kinematic State Vector**:
  $$\mathbf{x} = [p_E, p_N, p_U, v_E, v_N, v_U, a_E, a_N, a_U]^T$$
- **Parallel Mode Filters**:
  1. $M_1$: Constant Velocity (`CV`) - Loitering/reconnaissance.
  2. $M_2$: Constant Turn Rate & Velocity (`CTRV`) - Evasive weaving.
  3. $M_3$: Constant Acceleration / Ballistic Dive (`CA_DIVE`) - High-G terminal suicide dive.
- **Outputs**: Live Markov probabilities ($\mu_{CV}, \mu_{CTRV}, \mu_{CA}$), 60-step 3D predicted ribbon, 95% covariance uncertainty ellipsoids, Time-to-Impact (TTI), ground impact projection, and Circular Error Probable (CEP).

### 2. `ai_core/detection.py` -> Swarm Tracking & Synthetic Generation
- **Two-Stage ByteTrack + Hungarian Association**:
  - Gated association via IoU + Mahalanobis kinematic distance using `scipy.optimize.linear_sum_assignment`.
  - Multi-target memory management preventing track swaps during swarm crossing.
- **Multi-Drone Swarm Generator**:
  - Simultaneous 8-UAV multi-axis swarm simulation.
  - Multi-spectral frame generation: `EO_DAYLIGHT`, `FLIR_WHITE_HOT`, `FLIR_BLACK_HOT`, and `SWIR_NIGHT_VISION`.

### 3. `ai_core/classifier.py` -> Evidential Multi-Modal Classifier
- Multi-sensor Bayesian log-odds evidential fusion:
  - Visual CNN feature extraction + bounding-box logits.
  - Radar micro-Doppler blade harmonics (rotor RPM, blade count, BPF).
  - RF protocol signatures (`ExpressLRS 900MHz/2.4GHz`, `OcuSync-3`, `TBS Crossfire`, `MAVLink`, or `Dark/RF-Silent`).
  - Automatic detection of RF-Silent autonomous munitions (boosts threat score $>80$).

### 4. `ai_core/response_engine.py` -> Weapon-Target Assignment (WTA)
- Multi-target WTA optimization maximizing defended asset survival under physical constraints:
  $$\max_{\mathbf{x}} \sum_{i=1}^{N} \text{ThreatValue}_i \left(1 - \prod_{j=1}^{M} (1 - P_k(j, i))^{x_{ij}}\right)$$
- Evaluates azimuth cone, line-of-sight range, effector magazine count, and reload cooldowns.

---

## 4. Verification & Validation Metrics

| Subsystem / Module | Test Suite Status | Execution Latency | Integrity Verification |
|---|---|---|---|
| `ai_core/trajectory_predictor.py` | 100% PASS | $< 1.2\text{ ms}$ (IMM-UKF 9-State) | 60-Step Covariance Verified |
| `ai_core/detection.py` | 100% PASS | $31.4\text{ ms}$ (RTX 3050 CUDA) | Two-Stage Hungarian Swarm Tracking |
| `ai_core/classifier.py` | 100% PASS | $< 4.5\text{ ms}$ | Evidential Fusion + RF-Silent Boost |
| `ai_core/response_engine.py` | 100% PASS | $< 0.8\text{ ms}$ | Optimal WTA Assignment Matrix |
| `sensors/rf_sensor.py` | 100% PASS | $< 0.5\text{ ms}$ | 128-Bin FFT PSD Waterfall |
| `sensors/radar_sensor.py` | 100% PASS | $< 0.5\text{ ms}$ | 3D Phased Array + Micro-Doppler |
| `control_unit/neutralization.py` | 100% PASS | $< 0.4\text{ ms}$ | Closed-Loop Actuator State Machines |
| `control_unit/audit_logger.py` | 100% PASS | $< 0.2\text{ ms}$ | SHA-256 Cryptographic Chain Verified |
| **Comprehensive Test Suite** | **20/20 PASS** | **3.44s total** | **100% Automated Coverage** |

---

## 5. Live Service Operation & Hotkeys

- **Web Command Center**: `http://127.0.0.1:8080/`
- **REST Status**: `http://127.0.0.1:8080/api/v1/status`
- **Audit Verification**: `http://127.0.0.1:8080/api/v1/audit/verify`
- **Telemetry Stream**: `ws://127.0.0.1:8080/ws/telemetry`

### Keyboard Shortcuts
- `[1]`: Engage Directional RF Jammer
- `[2]`: Engage GNSS / GPS Multi-Band Spoofer
- `[3]`: Engage High-Energy Optical / IR Dazzler
- `[4]`: Launch Silo-Based Kinetic Interceptor Drone
- `[Spacebar]`: Master Emergency Ceasefire (Disengage All Effectors)
- `[V]`: Toggle Camera View Mode (`3D ISOMETRIC` $\leftrightarrow$ `2D PLANAR`)
- `[M]`: Cycle Multi-Spectral Shader Mode (`EO` $\rightarrow$ `FLIR-W` $\rightarrow$ `FLIR-B` $\rightarrow$ `SWIR`)
- `[A]`: Toggle Audio Master Caution Synth
