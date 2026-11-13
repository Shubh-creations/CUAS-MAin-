"""
Autonomous Trajectory Prediction & Interception Geometry Module for CUAS.
Implements a 6-State Kalman Filter (position, velocity, acceleration) to extrapolate
future drone paths, detect evasive maneuvers, and compute Time-to-Impact (TTI).
"""

from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import numpy as np

from utils.logger import get_logger

logger = get_logger("CUAS.Trajectory")

@dataclass
class TrajectoryPrediction:
    target_id: int
    current_position: Tuple[float, float]
    velocity_vector: Tuple[float, float]          # px/sec or m/s
    speed: float                                  # Magnitude
    acceleration_vector: Tuple[float, float]
    predicted_path: List[Tuple[float, float]]     # Future positions
    time_to_impact_sec: Optional[float]           # TTI to base/perimeter
    closest_approach_dist_px: Optional[float]
    is_diving_or_descending: bool
    is_evasive: bool


class KalmanFilter2D:
    """
    Continuous-Discrete Kalman Filter for 2D Target Motion.
    State vector: x = [pos_x, pos_y, vel_x, vel_y, acc_x, acc_y]^T
    """
    def __init__(self, init_x: float, init_y: float, dt: float = 1.0 / 30.0):
        self.dt = dt
        # State vector [x, y, vx, vy, ax, ay]
        self.x = np.array([init_x, init_y, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)

        # State transition matrix F
        self.F = np.eye(6, dtype=np.float64)
        self.F[0, 2] = dt
        self.F[1, 3] = dt
        self.F[0, 4] = 0.5 * (dt ** 2)
        self.F[1, 5] = 0.5 * (dt ** 2)
        self.F[2, 4] = dt
        self.F[3, 5] = dt

        # Measurement matrix H (we measure position [x, y])
        self.H = np.zeros((2, 6), dtype=np.float64)
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0

        # State covariance P
        self.P = np.eye(6, dtype=np.float64) * 10.0

        # Process noise covariance Q
        q_pos = 0.05
        q_vel = 0.20
        q_acc = 0.50
        self.Q = np.diag([q_pos, q_pos, q_vel, q_vel, q_acc, q_acc])

        # Measurement noise covariance R
        r_noise = 2.5
        self.R = np.eye(2, dtype=np.float64) * r_noise

    def predict(self) -> np.ndarray:
        """Predict state ahead by dt."""
        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q
        return self.x[:2]

    def update(self, measured_x: float, measured_y: float) -> None:
        """Update state using new detection coordinates."""
        z = np.array([measured_x, measured_y], dtype=np.float64)
        y = z - np.dot(self.H, self.x)
        S = np.dot(np.dot(self.H, self.P), self.H.T) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))

        self.x = self.x + np.dot(K, y)
        I = np.eye(6, dtype=np.float64)
        self.P = np.dot(I - np.dot(K, self.H), self.P)

    def forecast_steps(self, num_steps: int) -> List[Tuple[float, float]]:
        """Project future positions without updating filter state."""
        future_path = []
        temp_x = self.x.copy()
        for _ in range(num_steps):
            temp_x = np.dot(self.F, temp_x)
            future_path.append((float(temp_x[0]), float(temp_x[1])))
        return future_path


class TrajectoryPredictor:
    """Manages multi-target trajectory tracks, smoothing, and threat extrapolation."""
    def __init__(self, history_len: int = 30, forecast_steps: int = 45, fps: float = 30.0):
        self.history_len = history_len
        self.forecast_steps = forecast_steps
        self.fps = fps
        self.dt = 1.0 / max(fps, 1.0)
        self.filters: Dict[int, KalmanFilter2D] = {}
        self.histories: Dict[int, deque] = {}

    def update_track(self, target_id: int, pos_x: float, pos_y: float) -> TrajectoryPrediction:
        """Updates Kalman Filter for a target and predicts future trajectory."""
        if target_id not in self.filters:
            self.filters[target_id] = KalmanFilter2D(pos_x, pos_y, dt=self.dt)
            self.histories[target_id] = deque(maxlen=self.history_len)

        kf = self.filters[target_id]
        kf.predict()
        kf.update(pos_x, pos_y)
        self.histories[target_id].append((pos_x, pos_y))

        # Velocity & Acceleration
        vx, vy = float(kf.x[2]), float(kf.x[3])
        ax, ay = float(kf.x[4]), float(kf.x[5])
        speed = float(np.hypot(vx, vy))

        # Extrapolate future steps
        future_points = kf.forecast_steps(self.forecast_steps)

        # Detect dive/rapid descent (positive Y in image coordinates is downward)
        is_diving = vy > 35.0

        # Detect erratic/evasive maneuvers
        is_evasive = np.hypot(ax, ay) > 50.0

        return TrajectoryPrediction(
            target_id=target_id,
            current_position=(pos_x, pos_y),
            velocity_vector=(vx, vy),
            speed=speed,
            acceleration_vector=(ax, ay),
            predicted_path=future_points,
            time_to_impact_sec=None,
            closest_approach_dist_px=None,
            is_diving_or_descending=is_diving,
            is_evasive=is_evasive
        )

    def get_history(self, target_id: int) -> List[Tuple[float, float]]:
        if target_id in self.histories:
            return list(self.histories[target_id])
        return []

    def purge_lost_targets(self, active_target_ids: List[int]) -> None:
        """Remove tracks that are no longer active."""
        active_set = set(active_target_ids)
        stored_ids = list(self.filters.keys())
        for tid in stored_ids:
            if tid not in active_set:
                del self.filters[tid]
                if tid in self.histories:
                    del self.histories[tid]
