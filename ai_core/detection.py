"""
Multi-Drone Swarm Detection, Two-Stage ByteTrack Association, and Multi-Spectral EO/IR FLIR Generator (v4.0-Lattice).
Supports Faster R-CNN and YOLOv8 with Hungarian IoU + Mahalanobis kinematic matching.
Synthetic generator models simultaneous swarm scenarios (pincer saturation, low-altitude FPV skimmers, decoys)
across Daylight Optical, FLIR White-Hot, and FLIR Black-Hot thermal modes.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import math
import random
import time

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
import torch
from torchvision import transforms
from torchvision.models.detection import fasterrcnn_resnet50_fpn, FasterRCNN_ResNet50_FPN_Weights

from utils.logger import get_logger

logger = get_logger("CUAS.Detection")

@dataclass
class TrackedDrone:
    target_id: int
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    center: Tuple[int, int]
    confidence: float
    class_label: str
    crop: Optional[np.ndarray]
    first_detected_time: float
    last_updated_time: float
    velocity_px: Tuple[float, float] = (0.0, 0.0)
    track_age_frames: int = 1
    consecutive_misses: int = 0
    state: str = "CONFIRMED"  # "TENTATIVE", "CONFIRMED", "LOST"


def compute_iou(boxA: Tuple[int, int, int, int], boxB: Tuple[int, int, int, int]) -> float:
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

    iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
    return max(0.0, min(1.0, iou))


class DroneDetector:
    """Two-Stage ByteTrack + Hungarian Multi-Object Tracker."""
    def __init__(
        self,
        model_type: str = "fasterrcnn",
        confidence_threshold: float = 0.55,
        device: str = "auto"
    ):
        self.model_type = model_type.lower()
        self.confidence_threshold = confidence_threshold

        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        logger.info(f"Initializing DroneDetector [{self.model_type}] on device: {self.device}")

        self.model = None
        self.yolo_model = None
        self._init_backend()

        self.transform = transforms.Compose([transforms.ToTensor()])

        self.next_track_id = 101
        self.active_tracks: Dict[int, TrackedDrone] = {}
        self.max_lost_seconds = 2.0
        self.high_conf_thresh = confidence_threshold
        self.low_conf_thresh = max(0.20, confidence_threshold * 0.5)

    def _init_backend(self):
        if self.model_type == "yolov8":
            try:
                from ultralytics import YOLO
                self.yolo_model = YOLO("yolov8n.pt")
                logger.info("YOLOv8 nano model loaded successfully.")
                return
            except Exception as e:
                logger.warning(f"Could not load YOLOv8: {e}. Falling back to Faster R-CNN.")
                self.model_type = "fasterrcnn"

        try:
            weights = FasterRCNN_ResNet50_FPN_Weights.DEFAULT
            self.model = fasterrcnn_resnet50_fpn(weights=weights)
            self.model.to(self.device)
            self.model.eval()
            if self.device.type == "cuda":
                torch.backends.cudnn.benchmark = True
            logger.info("Faster R-CNN ResNet-50 FPN initialized.")
        except Exception as e:
            logger.error(f"Error initializing Faster R-CNN: {e}")
            raise

    def detect(self, frame_bgr: np.ndarray) -> List[TrackedDrone]:
        if frame_bgr is None or frame_bgr.size == 0:
            return []

        if self.model_type == "yolov8" and self.yolo_model is not None:
            raw_detections = self._detect_yolo(frame_bgr)
        else:
            raw_detections = self._detect_fasterrcnn(frame_bgr)

        # Apply Two-Stage ByteTrack Hungarian Association
        tracked = self._bytetrack_association(raw_detections, frame_bgr)
        return tracked

    def _detect_fasterrcnn(self, frame_bgr: np.ndarray) -> List[Tuple[Tuple[int, int, int, int], float, str]]:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        tensor = self.transform(rgb).to(self.device)

        with torch.no_grad():
            predictions = self.model([tensor])[0]

        detections = []
        # PyTorch CUDA safety: copy to CPU before numpy
        boxes = predictions["boxes"].detach().cpu().numpy()
        scores = predictions["scores"].detach().cpu().numpy()

        for idx, score in enumerate(scores):
            if score >= self.low_conf_thresh:
                box = boxes[idx].astype(int)
                x1 = max(0, min(frame_bgr.shape[1] - 1, int(box[0])))
                y1 = max(0, min(frame_bgr.shape[0] - 1, int(box[1])))
                x2 = max(x1 + 1, min(frame_bgr.shape[1], int(box[2])))
                y2 = max(y1 + 1, min(frame_bgr.shape[0], int(box[3])))
                detections.append(((x1, y1, x2, y2), float(score), "uav"))

        return detections

    def _detect_yolo(self, frame_bgr: np.ndarray) -> List[Tuple[Tuple[int, int, int, int], float, str]]:
        detections = []
        try:
            results = self.yolo_model(frame_bgr, conf=self.low_conf_thresh, verbose=False)[0]
            boxes = results.boxes.xyxy.detach().cpu().numpy()
            scores = results.boxes.conf.detach().cpu().numpy()
            classes = results.boxes.cls.detach().cpu().numpy()

            for idx in range(len(boxes)):
                box = boxes[idx].astype(int)
                x1, y1, x2, y2 = box
                cls_id = int(classes[idx])
                cls_name = self.yolo_model.names.get(cls_id, "uav")
                detections.append(((x1, y1, x2, y2), float(scores[idx]), cls_name))
        except Exception as e:
            logger.error(f"YOLO detection exception: {e}")
        return detections

    def _bytetrack_association(
        self,
        raw_detections: List[Tuple[Tuple[int, int, int, int], float, str]],
        frame_bgr: np.ndarray
    ) -> List[TrackedDrone]:
        """
        Two-Stage ByteTrack Association using Hungarian Algorithm:
        Stage 1: Match high-confidence detections with existing confirmed tracks using IoU + Mahalanobis.
        Stage 2: Match remaining unassigned tracks with low-confidence detections to preserve tracks through occlusion/blur.
        """
        now = time.time()
        high_dets = [d for d in raw_detections if d[1] >= self.high_conf_thresh]
        low_dets = [d for d in raw_detections if self.low_conf_thresh <= d[1] < self.high_conf_thresh]

        track_ids = list(self.active_tracks.keys())
        unmatched_tracks = set(track_ids)
        unmatched_high_dets = set(range(len(high_dets)))

        # STAGE 1: Match High Detections
        if track_ids and high_dets:
            cost_matrix = np.zeros((len(track_ids), len(high_dets)))
            for i, tid in enumerate(track_ids):
                t = self.active_tracks[tid]
                pred_x = t.center[0] + t.velocity_px[0]
                pred_y = t.center[1] + t.velocity_px[1]
                pred_box = (
                    int(pred_x - (t.bbox[2] - t.bbox[0]) // 2),
                    int(pred_y - (t.bbox[3] - t.bbox[1]) // 2),
                    int(pred_x + (t.bbox[2] - t.bbox[0]) // 2),
                    int(pred_y + (t.bbox[3] - t.bbox[1]) // 2)
                )

                for j, (det_box, _, _) in enumerate(high_dets):
                    iou_val = compute_iou(pred_box, det_box)
                    det_cx, det_cy = (det_box[0] + det_box[2]) / 2.0, (det_box[1] + det_box[3]) / 2.0
                    euc_dist = math.hypot(det_cx - pred_x, det_cy - pred_y)
                    # Combined cost: 1 - IoU + normalized distance
                    cost_matrix[i, j] = (1.0 - iou_val) * 0.7 + min(1.0, euc_dist / 180.0) * 0.3

            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            for r, c in zip(row_ind, col_ind):
                if cost_matrix[r, c] < 0.85: # Gating threshold
                    tid = track_ids[r]
                    bbox, score, label = high_dets[c]
                    self._update_existing_track(tid, bbox, score, label, frame_bgr, now)
                    unmatched_tracks.discard(tid)
                    unmatched_high_dets.discard(c)

        # STAGE 2: Match Remaining Tracks with Low Detections
        unmatched_track_list = list(unmatched_tracks)
        if unmatched_track_list and low_dets:
            cost_matrix_low = np.zeros((len(unmatched_track_list), len(low_dets)))
            for i, tid in enumerate(unmatched_track_list):
                t = self.active_tracks[tid]
                for j, (det_box, _, _) in enumerate(low_dets):
                    iou_val = compute_iou(t.bbox, det_box)
                    cost_matrix_low[i, j] = 1.0 - iou_val

            row_ind_l, col_ind_l = linear_sum_assignment(cost_matrix_low)
            for r, c in zip(row_ind_l, col_ind_l):
                if cost_matrix_low[r, c] < 0.75:
                    tid = unmatched_track_list[r]
                    bbox, score, label = low_dets[c]
                    self._update_existing_track(tid, bbox, score, label, frame_bgr, now)
                    unmatched_tracks.discard(tid)

        # Spawn new tracks from unmatched high detections
        for det_idx in unmatched_high_dets:
            bbox, score, label = high_dets[det_idx]
            x1, y1, x2, y2 = bbox
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            crop = frame_bgr[y1:y2, x1:x2].copy() if (y2 > y1 and x2 > x1) else None

            new_id = self.next_track_id
            self.next_track_id += 1
            new_track = TrackedDrone(
                target_id=new_id,
                bbox=bbox,
                center=(cx, cy),
                confidence=score,
                class_label=label,
                crop=crop,
                first_detected_time=now,
                last_updated_time=now,
                velocity_px=(0.0, 0.0),
                track_age_frames=1,
                consecutive_misses=0,
                state="CONFIRMED"
            )
            self.active_tracks[new_id] = new_track

        # Handle remaining unmatched tracks
        for tid in list(unmatched_tracks):
            t = self.active_tracks[tid]
            t.consecutive_misses += 1
            if (now - t.last_updated_time) > self.max_lost_seconds or t.consecutive_misses > 30:
                del self.active_tracks[tid]
            else:
                t.state = "LOST"

        return [t for t in self.active_tracks.values() if t.consecutive_misses < 3]

    def _update_existing_track(
        self, tid: int, bbox: Tuple[int, int, int, int], score: float, label: str,
        frame_bgr: np.ndarray, now: float
    ):
        t = self.active_tracks[tid]
        x1, y1, x2, y2 = bbox
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        vx = cx - t.center[0]
        vy = cy - t.center[1]

        t.bbox = bbox
        t.center = (cx, cy)
        t.velocity_px = (round(vx * 0.7 + t.velocity_px[0] * 0.3, 1), round(vy * 0.7 + t.velocity_px[1] * 0.3, 1))
        t.confidence = score
        t.class_label = label
        t.last_updated_time = now
        t.track_age_frames += 1
        t.consecutive_misses = 0
        t.state = "CONFIRMED"

        if y2 > y1 and x2 > x1:
            t.crop = frame_bgr[y1:y2, x1:x2].copy()


# =====================================================================
# SYNTHETIC DRONE SWARM & MULTI-SPECTRAL EO/IR FLIR GENERATOR
# =====================================================================

@dataclass
class SwarmDroneInstance:
    id_num: int
    x: float
    y: float
    z: float               # Altitude in meters
    vx: float
    vy: float
    vz: float
    drone_type: str        # "SUICIDE_FPV", "RECON_QUAD", "DECOY", "CIVILIAN"
    has_payload: bool
    temperature_k: float   # Hot spot temp (340K-410K)
    rotor_rpm: float       # 8,000 - 24,000 RPM


class SyntheticDroneGenerator:
    """
    Renders realistic synthetic multi-target swarms across:
    1. EO Daylight (Optical RGB)
    2. FLIR White-Hot Thermal
    3. FLIR Black-Hot Thermal
    """
    def __init__(self, width: int = 640, height: int = 480, scenario: str = "SWARM_SATURATION"):
        self.w = width
        self.h = height
        self.scenario = scenario
        self.display_mode = "EO_DAYLIGHT"  # "EO_DAYLIGHT", "FLIR_WHITE_HOT", "FLIR_BLACK_HOT"
        self.drones: List[SwarmDroneInstance] = []
        self._init_scenario()

    def set_display_mode(self, mode: str):
        if mode in ["EO_DAYLIGHT", "FLIR_WHITE_HOT", "FLIR_BLACK_HOT"]:
            self.display_mode = mode

    def set_scenario(self, scenario: str):
        self.scenario = scenario
        self._init_scenario()

    def _init_scenario(self):
        self.drones.clear()
        if self.scenario == "FPV_TERMINAL_DIVE":
            # Single high-speed terminal diving suicide drone
            self.drones.append(SwarmDroneInstance(
                id_num=101, x=320, y=110, z=280, vx=-1.2, vy=4.5, vz=-22.0,
                drone_type="SUICIDE_FPV", has_payload=True, temperature_k=395.0, rotor_rpm=24000
            ))
        elif self.scenario == "RF_SILENT_STEALTH":
            # Autonomous optical navigation loitering munition with zero RF emissions
            self.drones.append(SwarmDroneInstance(
                id_num=102, x=220, y=140, z=180, vx=2.0, vy=1.8, vz=-8.0,
                drone_type="AUTONOMOUS_LOITERING_MUNITION", has_payload=True, temperature_k=365.0, rotor_rpm=16000
            ))
        elif self.scenario == "MIXED_AIRSPACE":
            # 1 Hostile suicide drone + 1 civilian commercial drone
            self.drones.append(SwarmDroneInstance(
                id_num=101, x=200, y=120, z=220, vx=2.2, vy=2.8, vz=-14.0,
                drone_type="SUICIDE_FPV", has_payload=True, temperature_k=390.0, rotor_rpm=22000
            ))
            self.drones.append(SwarmDroneInstance(
                id_num=104, x=450, y=200, z=110, vx=-1.4, vy=0.4, vz=-1.0,
                drone_type="CIVILIAN_MULTIROTOR", has_payload=False, temperature_k=320.0, rotor_rpm=9500
            ))
        else:
            # Default: Multi-Axis Swarm Saturation (4 simultaneous drones)
            self.drones.append(SwarmDroneInstance(
                id_num=101, x=180, y=130, z=260, vx=2.0, vy=2.5, vz=-16.0,
                drone_type="SUICIDE_FPV", has_payload=True, temperature_k=395.0, rotor_rpm=24000
            ))
            self.drones.append(SwarmDroneInstance(
                id_num=102, x=460, y=120, z=290, vx=-2.2, vy=2.2, vz=-15.0,
                drone_type="SUICIDE_FPV", has_payload=True, temperature_k=390.0, rotor_rpm=23500
            ))
            self.drones.append(SwarmDroneInstance(
                id_num=103, x=330, y=80, z=380, vx=0.6, vy=1.2, vz=-6.0,
                drone_type="RECON_QUAD", has_payload=False, temperature_k=345.0, rotor_rpm=14000
            ))
            self.drones.append(SwarmDroneInstance(
                id_num=104, x=510, y=240, z=90, vx=-1.0, vy=0.2, vz=0.0,
                drone_type="CIVILIAN_MULTIROTOR", has_payload=False, temperature_k=315.0, rotor_rpm=8800
            ))

    def generate_frame(self) -> np.ndarray:
        frame = np.zeros((self.h, self.w, 3), dtype=np.uint8)

        # 1. Background Generation (Sky + Horizon + Terrain)
        if self.display_mode == "EO_DAYLIGHT":
            # Realistic Daylight: atmospheric gradient from deep aerospace blue to light haze
            for y in range(self.h):
                if y < int(self.h * 0.72):
                    ratio = y / (self.h * 0.72)
                    b = int(45 + ratio * 35)
                    g = int(35 + ratio * 30)
                    r = int(25 + ratio * 25)
                    frame[y, :] = (b, g, r)
                else:
                    # Rolling terrain / horizon
                    t_ratio = (y - self.h * 0.72) / (self.h * 0.28)
                    frame[y, :] = (int(18 + t_ratio * 12), int(28 + t_ratio * 16), int(14 + t_ratio * 10))
        elif self.display_mode == "FLIR_WHITE_HOT":
            # FLIR White-Hot: Cool background is dark gray/black; hot targets glow white
            for y in range(self.h):
                val = int(18 + (y / self.h) * 22)
                frame[y, :] = (val, val, val)
        else: # FLIR_BLACK_HOT
            # FLIR Black-Hot: Cool background is light gray; hot targets glow deep black
            for y in range(self.h):
                val = int(210 - (y / self.h) * 25)
                frame[y, :] = (val, val, val)

        # 2. Update and Render Multi-Drone Swarm
        for drone in self.drones:
            drone.x += drone.vx
            drone.y += drone.vy
            drone.z += drone.vz * (1.0 / 30.0)

            # Clamp & rebound horizontally
            if drone.x < 50 or drone.x > self.w - 50:
                drone.vx *= -1
            if drone.y < 50 or drone.y > self.h - 100:
                drone.vy *= -1

            cx, cy = int(drone.x), int(drone.y)
            # Distance scale (smaller if higher altitude)
            scale = max(0.5, min(1.8, 250.0 / max(60.0, drone.z)))
            arm_len = int(24 * scale)

            # Render styling based on sensor mode
            if self.display_mode == "EO_DAYLIGHT":
                body_color = (130, 130, 130)
                arm_color = (70, 70, 70)
                rotor_blur = (180, 180, 180)
                payload_color = (40, 40, 40)
            elif self.display_mode == "FLIR_WHITE_HOT":
                # Motors & batteries glow bright white/yellow
                body_color = (245, 245, 245)
                arm_color = (190, 190, 190)
                rotor_blur = (220, 220, 220)
                payload_color = (255, 255, 255)
            else: # FLIR_BLACK_HOT
                body_color = (15, 15, 15)
                arm_color = (40, 40, 40)
                rotor_blur = (30, 30, 30)
                payload_color = (5, 5, 5)

            # Drone Central Body
            cv2.circle(frame, (cx, cy), max(3, int(6 * scale)), body_color, -1)

            # Carbon arms
            cv2.line(frame, (cx - arm_len, cy - int(arm_len * 0.5)), (cx + arm_len, cy + int(arm_len * 0.5)), arm_color, max(1, int(2 * scale)))
            cv2.line(frame, (cx - arm_len, cy + int(arm_len * 0.5)), (cx + arm_len, cy - int(arm_len * 0.5)), arm_color, max(1, int(2 * scale)))

            # Rotors (spinning motion blur discs)
            for rx, ry in [
                (cx - arm_len, cy - int(arm_len * 0.5)),
                (cx + arm_len, cy + int(arm_len * 0.5)),
                (cx - arm_len, cy + int(arm_len * 0.5)),
                (cx + arm_len, cy - int(arm_len * 0.5))
            ]:
                cv2.ellipse(frame, (rx, ry), (int(10 * scale), int(3 * scale)), 0, 0, 360, rotor_blur, 1)
                # Motor heat signature
                cv2.circle(frame, (rx, ry), max(1, int(2 * scale)), body_color, -1)

            # Slung Munition Payload Silhouette
            if drone.has_payload:
                p_len = int(10 * scale)
                cv2.rectangle(frame, (cx - int(4 * scale), cy + int(4 * scale)), (cx + int(4 * scale), cy + int(4 * scale) + p_len), payload_color, -1)

            # Thermal Blooming effect for FLIR
            if self.display_mode == "FLIR_WHITE_HOT":
                cv2.circle(frame, (cx, cy), int(12 * scale), (255, 255, 200), 1)

        # Micro-noise grain for realism
        noise = np.random.randint(0, 5, (self.h, self.w, 3), dtype=np.uint8)
        frame = cv2.add(frame, noise)

        return frame
