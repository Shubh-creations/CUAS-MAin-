"""
Autonomous 3D Trajectory Prediction & Kinematic Interception Geometry Module (v4.0-Lattice).
Implements an Interacting Multiple Model Unscented Kalman Filter (IMM-UKF) in 3D East-North-Up (ENU)
coordinates with pixel-to-metric homography, Markov mode probabilities, covariance ellipsoids,
Time-to-Impact (TTI), and Circular Error Probable (CEP) ground impact projections.
Preserves backward compatibility for 2D KalmanFilter2D callers.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import math
import numpy as np
from scipy.linalg import cholesky

from utils.logger import get_logger

logger = get_logger("CUAS.Trajectory")

# =====================================================================
# BACKWARD-COMPATIBLE 2D KALMAN FILTER
# =====================================================================

class KalmanFilter2D:
    """
    Continuous-Discrete Kalman Filter for 2D Target Motion.
    Maintained for backwards-compatibility with legacy 2D pipelines.
    State vector: x = [pos_x, pos_y, vel_x, vel_y, acc_x, acc_y]^T
    """
    def __init__(self, init_x: float, init_y: float, dt: float = 1.0 / 30.0):
        self.dt = dt
        self.x = np.array([init_x, init_y, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)

        self.F = np.eye(6, dtype=np.float64)
        self.F[0, 2] = dt
        self.F[1, 3] = dt
        self.F[0, 4] = 0.5 * (dt ** 2)
        self.F[1, 5] = 0.5 * (dt ** 2)
        self.F[2, 4] = dt
        self.F[3, 5] = dt

        self.H = np.zeros((2, 6), dtype=np.float64)
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0

        self.P = np.eye(6, dtype=np.float64) * 10.0
        self.Q = np.diag([0.05, 0.05, 0.20, 0.20, 0.50, 0.50])
        self.R = np.eye(2, dtype=np.float64) * 2.5

    def predict(self) -> np.ndarray:
        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q
        return self.x[:2]

    def update(self, measured_x: float, measured_y: float) -> None:
        z = np.array([measured_x, measured_y], dtype=np.float64)
        y = z - np.dot(self.H, self.x)
        S = np.dot(np.dot(self.H, self.P), self.H.T) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))

        self.x = self.x + np.dot(K, y)
        I = np.eye(6, dtype=np.float64)
        self.P = np.dot(I - np.dot(K, self.H), self.P)

    def forecast_steps(self, num_steps: int) -> List[Tuple[float, float]]:
        future_path = []
        temp_x = self.x.copy()
        for _ in range(num_steps):
            temp_x = np.dot(self.F, temp_x)
            future_path.append((float(temp_x[0]), float(temp_x[1])))
        return future_path


# =====================================================================
# 3D IMM-UKF HIGH-ORDER TACTICAL ESTIMATOR (v4.0-LATTICE)
# =====================================================================

@dataclass
class TrajectoryPrediction:
    target_id: int
    current_position: Tuple[float, float]               # (x, y) pixel or 2D
    velocity_vector: Tuple[float, float]                # (vx, vy)
    speed: float                                        # Magnitude (m/s)
    acceleration_vector: Tuple[float, float]
    predicted_path: List[Tuple[float, float]]           # 2D projection
    time_to_impact_sec: Optional[float]                 # TTI to base/killzone
    closest_approach_dist_px: Optional[float]
    is_diving_or_descending: bool
    is_evasive: bool
    # 3D IMM-UKF Tactical Enhancements
    position_3d_enu: Tuple[float, float, float] = (0.0, 0.0, 0.0) # (East, North, Up) in meters
    velocity_3d_enu: Tuple[float, float, float] = (0.0, 0.0, 0.0) # (Ve, Vn, Vu) in m/s
    predicted_path_3d: List[Tuple[float, float, float]] = field(default_factory=list)
    mode_probabilities: Dict[str, float] = field(default_factory=lambda: {"CV": 0.70, "CTRV": 0.20, "CA_DIVE": 0.10})
    dominant_mode: str = "CV"
    covariance_ellipsoid_semi_axes: Tuple[float, float, float] = (10.0, 10.0, 5.0) # 95% confidence 3D
    ground_impact_point: Optional[Tuple[float, float]] = None      # (East, North) ground impact
    circular_error_probable_m: float = 12.0                        # CEP in meters


class UKFFilter3D:
    """
    Unscented Kalman Filter for 9-State 3D ENU Kinematics.
    State: x = [pE, pN, pU, vE, vN, vU, aE, aN, aU]^T (9x1)
    """
    def __init__(self, mode: str = "CV", dt: float = 1.0 / 30.0):
        self.mode = mode.upper() # "CV", "CTRV", "CA_DIVE"
        self.dt = dt
        self.n = 9
        self.m = 3 # Measure [pE, pN, pU]

        # UKF Tuning parameters
        self.alpha = 1e-3
        self.beta = 2.0
        self.kappa = 0.0
        self.lambda_ = self.alpha ** 2 * (self.n + self.kappa) - self.n

        # Weights
        self.wm = np.full(2 * self.n + 1, 1.0 / (2 * (self.n + self.lambda_)))
        self.wc = np.full(2 * self.n + 1, 1.0 / (2 * (self.n + self.lambda_)))
        self.wm[0] = self.lambda_ / (self.n + self.lambda_)
        self.wc[0] = self.wm[0] + (1 - self.alpha ** 2 + self.beta)

        # State and covariance
        self.x = np.zeros(self.n, dtype=np.float64)
        self.P = np.eye(self.n, dtype=np.float64) * 25.0

        # Process noise scaled by kinematic mode
        if self.mode == "CV":
            q_p, q_v, q_a = 0.05, 0.2, 0.1
        elif self.mode == "CTRV":
            q_p, q_v, q_a = 0.1, 0.8, 1.5
        elif self.mode == "CA_DIVE":
            q_p, q_v, q_a = 0.2, 1.2, 3.5
        else:
            q_p, q_v, q_a = 0.1, 0.4, 0.5

        self.Q = np.diag([q_p, q_p, q_p, q_v, q_v, q_v, q_a, q_a, q_a])
        self.R = np.diag([4.0, 4.0, 2.0]) # Radar / optical measurement noise

    def generate_sigma_points(self) -> np.ndarray:
        sigma = np.zeros((2 * self.n + 1, self.n))
        sigma[0] = self.x
        try:
            scale = math.sqrt(max(1e-8, self.n + self.lambda_))
            L = cholesky(self.P, lower=True)
            for i in range(self.n):
                sigma[i + 1] = self.x + scale * L[:, i]
                sigma[self.n + i + 1] = self.x - scale * L[:, i]
        except Exception:
            L = np.diag(np.sqrt(np.maximum(1e-6, np.diag(self.P))))
            scale = math.sqrt(max(1e-8, self.n + self.lambda_))
            for i in range(self.n):
                sigma[i + 1] = self.x + scale * L[:, i]
                sigma[self.n + i + 1] = self.x - scale * L[:, i]
        return sigma

    def transition_function(self, state: np.ndarray) -> np.ndarray:
        p = state[0:3]
        v = state[3:6]
        a = state[6:9]
        dt = self.dt

        if self.mode == "CV":
            # Constant Velocity (acceleration damps out)
            p_next = p + v * dt + 0.5 * a * (dt ** 2)
            v_next = v + a * dt
            a_next = a * 0.95
        elif self.mode == "CTRV":
            # Constant Turn Rate & Velocity (horizontal turn bias)
            omega = 0.12 # Turn rate rad/s
            cos_o = math.cos(omega * dt)
            sin_o = math.sin(omega * dt)
            v_rot_x = cos_o * v[0] - sin_o * v[1]
            v_rot_y = sin_o * v[0] + cos_o * v[1]
            v_next = np.array([v_rot_x, v_rot_y, v[2] * 0.98])
            p_next = p + 0.5 * (v + v_next) * dt
            a_next = np.array([-sin_o * omega * v[0], cos_o * omega * v[1], a[2]])
        elif self.mode == "CA_DIVE":
            # Terminal Ballistic Dive (downward gravity acceleration)
            g_boost = -9.81 * 0.4
            a_dive = np.array([a[0] * 1.05, a[1] * 1.05, min(-12.0, a[2] + g_boost * dt)])
            v_next = v + a_dive * dt
            p_next = p + v * dt + 0.5 * a_dive * (dt ** 2)
            a_next = a_dive
        else:
            p_next = p + v * dt
            v_next = v
            a_next = a

        return np.concatenate([p_next, v_next, a_next])

    def predict(self):
        sigma = self.generate_sigma_points()
        sigma_f = np.zeros_like(sigma)
        for i in range(len(sigma)):
            sigma_f[i] = self.transition_function(sigma[i])

        x_pred = np.zeros(self.n)
        for i in range(len(sigma_f)):
            x_pred += self.wm[i] * sigma_f[i]

        P_pred = np.zeros((self.n, self.n))
        for i in range(len(sigma_f)):
            diff = (sigma_f[i] - x_pred).reshape(-1, 1)
            P_pred += self.wc[i] * np.dot(diff, diff.T)
        P_pred += self.Q

        self.x = x_pred
        self.P = P_pred
        return self.x

    def update(self, z: np.ndarray) -> float:
        """Updates UKF state and returns innovation likelihood."""
        sigma = self.generate_sigma_points()
        # Measurement function h(x) observes [pE, pN, pU]
        Z_sigma = sigma[:, 0:3]

        z_pred = np.zeros(3)
        for i in range(len(Z_sigma)):
            z_pred += self.wm[i] * Z_sigma[i]

        S = np.zeros((3, 3))
        for i in range(len(Z_sigma)):
            diff_z = (Z_sigma[i] - z_pred).reshape(-1, 1)
            S += self.wc[i] * np.dot(diff_z, diff_z.T)
        S += self.R

        # Cross-covariance Pxz
        Pxz = np.zeros((self.n, 3))
        for i in range(len(sigma)):
            diff_x = (sigma[i] - self.x).reshape(-1, 1)
            diff_z = (Z_sigma[i] - z_pred).reshape(-1, 1)
            Pxz += self.wc[i] * np.dot(diff_x, diff_z.T)

        try:
            S_inv = np.linalg.inv(S)
            K = np.dot(Pxz, S_inv)
            y = z - z_pred
            self.x = self.x + np.dot(K, y)
            self.P = self.P - np.dot(np.dot(K, S), K.T)

            # Gaussian likelihood
            det_S = max(1e-6, float(np.linalg.det(S)))
            mahal = float(np.dot(np.dot(y.T, S_inv), y))
            likelihood = (1.0 / math.sqrt(((2 * math.pi) ** 3) * det_S)) * math.exp(-0.5 * min(50.0, mahal))
            return max(1e-12, likelihood)
        except Exception:
            return 1e-6

    def project_trajectory(self, steps: int = 60) -> List[Tuple[float, float, float]]:
        ribbon = []
        state = self.x.copy()
        for _ in range(steps):
            state = self.transition_function(state)
            ribbon.append((float(state[0]), float(state[1]), float(state[2])))
        return ribbon


class InteractingMultipleModelUKF:
    """
    IMM Estimator coordinating 3 parallel UKFs (CV, CTRV, CA_DIVE).
    Markov Transition Matrix:
      [0.85, 0.10, 0.05]
      [0.10, 0.80, 0.10]
      [0.05, 0.15, 0.80]
    """
    def __init__(self, init_pos_enu: Tuple[float, float, float], dt: float = 1.0 / 30.0):
        self.dt = dt
        self.modes = ["CV", "CTRV", "CA_DIVE"]
        self.filters = [UKFFilter3D(mode, dt=dt) for mode in self.modes]
        for f in self.filters:
            f.x[0:3] = init_pos_enu

        # Markov mode probabilities
        self.mu = np.array([0.70, 0.20, 0.10], dtype=np.float64)

        # Transition probability matrix PI
        self.PI = np.array([
            [0.88, 0.08, 0.04],
            [0.10, 0.82, 0.08],
            [0.04, 0.11, 0.85]
        ], dtype=np.float64)

        self.combined_x = np.zeros(9)
        self.combined_P = np.eye(9)

    def cycle(self, measured_enu: Tuple[float, float, float]) -> Dict[str, Any]:
        z = np.array(measured_enu, dtype=np.float64)

        # 1. Interaction / Mixing
        c_bar = np.dot(self.PI.T, self.mu)
        c_bar = np.maximum(1e-9, c_bar)
        mixing_prob = np.zeros((3, 3))
        for i in range(3):
            for j in range(3):
                mixing_prob[i, j] = (self.PI[i, j] * self.mu[i]) / c_bar[j]

        mixed_x = [np.zeros(9) for _ in range(3)]
        for j in range(3):
            for i in range(3):
                mixed_x[j] += mixing_prob[i, j] * self.filters[i].x

        mixed_P = [np.zeros((9, 9)) for _ in range(3)]
        for j in range(3):
            for i in range(3):
                diff = (self.filters[i].x - mixed_x[j]).reshape(-1, 1)
                mixed_P[j] += mixing_prob[i, j] * (self.filters[i].P + np.dot(diff, diff.T))

        # Assign mixed states
        for j in range(3):
            self.filters[j].x = mixed_x[j]
            self.filters[j].P = mixed_P[j]

        # 2. Mode-Matched Filter Predict & Update
        likelihoods = np.zeros(3)
        for j in range(3):
            self.filters[j].predict()
            likelihoods[j] = self.filters[j].update(z)

        # 3. Mode Probability Update
        raw_mu = likelihoods * c_bar
        total_mu = np.sum(raw_mu)
        if total_mu > 1e-12:
            self.mu = raw_mu / total_mu
        else:
            self.mu = np.array([0.70, 0.20, 0.10])

        # 4. State Combination
        self.combined_x = np.zeros(9)
        for j in range(3):
            self.combined_x += self.mu[j] * self.filters[j].x

        self.combined_P = np.zeros((9, 9))
        for j in range(3):
            diff = (self.filters[j].x - self.combined_x).reshape(-1, 1)
            self.combined_P += self.mu[j] * (self.filters[j].P + np.dot(diff, diff.T))

        dominant_idx = int(np.argmax(self.mu))
        dominant_mode = self.modes[dominant_idx]

        # 95% Covariance semi-axes (chi-square 3 DOF = 7.815)
        pos_cov = self.combined_P[0:3, 0:3]
        eigvals = np.maximum(0.1, np.linalg.eigvalsh(pos_cov))
        semi_axes = tuple(float(math.sqrt(ev * 7.815)) for ev in eigvals)

        return {
            "state_enu": self.combined_x,
            "mode_probabilities": {self.modes[i]: float(self.mu[i]) for i in range(3)},
            "dominant_mode": dominant_mode,
            "semi_axes": semi_axes
        }

    def project_3d_ribbon(self, steps: int = 60) -> List[Tuple[float, float, float]]:
        dominant_idx = int(np.argmax(self.mu))
        return self.filters[dominant_idx].project_trajectory(steps)


class TrajectoryPredictor:
    """
    Manages multi-target trajectory tracks, smoothing, and threat extrapolation.
    Integrates 3D IMM-UKF with homography mapping to pixel coordinates.
    """
    def __init__(self, history_len: int = 30, forecast_steps: int = 45, fps: float = 30.0):
        self.history_len = history_len
        self.forecast_steps = forecast_steps
        self.fps = fps
        self.dt = 1.0 / max(fps, 1.0)
        self.imm_filters: Dict[int, InteractingMultipleModelUKF] = {}
        self.histories: Dict[int, deque] = {}
        self.pixel_histories: Dict[int, deque] = {}

    def pixel_to_enu(self, px: float, py: float, est_dist_m: float = 800.0) -> Tuple[float, float, float]:
        """
        Homography projection from camera sensor pixels (cx, cy) to local ENU meters.
        Assumes optical optical center at (320, 240) with horizontal FOV ~60 deg.
        """
        norm_x = (px - 320.0) / 320.0
        norm_y = (240.0 - py) / 240.0
        east_m = norm_x * (est_dist_m * math.tan(math.radians(30.0)))
        up_m = max(10.0, 150.0 + norm_y * (est_dist_m * math.tan(math.radians(22.0))))
        north_m = math.sqrt(max(100.0, est_dist_m ** 2 - east_m ** 2 - up_m ** 2))
        return (east_m, north_m, up_m)

    def enu_to_pixel(self, east_m: float, north_m: float, up_m: float) -> Tuple[float, float]:
        """Projects ENU 3D coordinates back to viewport pixel plane."""
        dist_ground = math.hypot(east_m, north_m)
        if dist_ground < 1.0:
            return (320.0, 240.0)
        norm_x = east_m / (dist_ground * math.tan(math.radians(30.0)))
        norm_y = (up_m - 150.0) / (dist_ground * math.tan(math.radians(22.0)))
        px = 320.0 + norm_x * 320.0
        py = 240.0 - norm_y * 240.0
        return (max(0.0, min(640.0, px)), max(0.0, min(480.0, py)))

    def update_track(
        self,
        target_id: int,
        pos_x: float,
        pos_y: float,
        est_dist_m: float = 800.0,
        known_enu: Optional[Tuple[float, float, float]] = None
    ) -> TrajectoryPrediction:
        """Updates IMM-UKF 3D state and computes tactical flight metrics."""
        enu = known_enu or self.pixel_to_enu(pos_x, pos_y, est_dist_m)

        if target_id not in self.imm_filters:
            self.imm_filters[target_id] = InteractingMultipleModelUKF(enu, dt=self.dt)
            self.histories[target_id] = deque(maxlen=self.history_len)
            self.pixel_histories[target_id] = deque(maxlen=self.history_len)

        imm = self.imm_filters[target_id]
        imm_result = imm.cycle(enu)

        self.histories[target_id].append(enu)
        self.pixel_histories[target_id].append((pos_x, pos_y))

        state = imm_result["state_enu"]
        pos_3d = (float(state[0]), float(state[1]), float(state[2]))
        vel_3d = (float(state[3]), float(state[4]), float(state[5]))
        acc_3d = (float(state[6]), float(state[7]), float(state[8]))
        speed_3d = float(np.linalg.norm(vel_3d))

        # 3D projected ribbon and 2D pixel projection
        ribbon_3d = imm.project_3d_ribbon(self.forecast_steps)
        ribbon_2d = [self.enu_to_pixel(pt[0], pt[1], pt[2]) for pt in ribbon_3d]

        # Time-to-Impact (TTI) to Base HQ origin (0, 0, 0)
        dist_to_base = float(math.hypot(pos_3d[0], pos_3d[1]))
        closing_speed = - (pos_3d[0] * vel_3d[0] + pos_3d[1] * vel_3d[1]) / max(dist_to_base, 1e-3)
        tti_sec = max(0.5, dist_to_base / closing_speed) if closing_speed > 2.0 else None

        # Ground plane impact calculation (where altitude Z crosses 0)
        ground_impact = None
        cep_m = 12.0
        if vel_3d[2] < -2.0 and pos_3d[2] > 0.0:
            t_impact = pos_3d[2] / abs(vel_3d[2])
            impact_e = pos_3d[0] + vel_3d[0] * t_impact
            impact_n = pos_3d[1] + vel_3d[1] * t_impact
            ground_impact = (round(impact_e, 1), round(impact_n, 1))
            cep_m = max(5.0, float(imm_result["semi_axes"][0] * 0.8))

        # Kinematic flags
        is_diving = (vel_3d[2] < -8.0) or (imm_result["dominant_mode"] == "CA_DIVE")
        is_evasive = (imm_result["dominant_mode"] == "CTRV") or (math.hypot(acc_3d[0], acc_3d[1]) > 8.0)

        return TrajectoryPrediction(
            target_id=target_id,
            current_position=(pos_x, pos_y),
            velocity_vector=(vel_3d[0], vel_3d[1]),
            speed=round(speed_3d, 1),
            acceleration_vector=(acc_3d[0], acc_3d[1]),
            predicted_path=ribbon_2d,
            time_to_impact_sec=round(tti_sec, 1) if tti_sec is not None else None,
            closest_approach_dist_px=dist_to_base,
            is_diving_or_descending=is_diving,
            is_evasive=is_evasive,
            position_3d_enu=(round(pos_3d[0], 1), round(pos_3d[1], 1), round(pos_3d[2], 1)),
            velocity_3d_enu=(round(vel_3d[0], 1), round(vel_3d[1], 1), round(vel_3d[2], 1)),
            predicted_path_3d=ribbon_3d,
            mode_probabilities=imm_result["mode_probabilities"],
            dominant_mode=imm_result["dominant_mode"],
            covariance_ellipsoid_semi_axes=imm_result["semi_axes"],
            ground_impact_point=ground_impact,
            circular_error_probable_m=round(cep_m, 1)
        )

    def get_history(self, target_id: int) -> List[Tuple[float, float]]:
        if target_id in self.pixel_histories:
            return list(self.pixel_histories[target_id])
        return []

    def get_history_3d(self, target_id: int) -> List[Tuple[float, float, float]]:
        if target_id in self.histories:
            return list(self.histories[target_id])
        return []

    def purge_lost_targets(self, active_target_ids: List[int]) -> None:
        active_set = set(active_target_ids)
        stored_ids = list(self.imm_filters.keys())
        for tid in stored_ids:
            if tid not in active_set:
                del self.imm_filters[tid]
                if tid in self.histories:
                    del self.histories[tid]
                if tid in self.pixel_histories:
                    del self.pixel_histories[tid]
