"""
Real-time Aerial Object Detection and Tracking Engine for CUAS.
Supports Faster R-CNN ResNet50-FPN and YOLOv8 backends with automated GPU/CPU device handling,
simple multi-object tracking, and synthetic target simulation for live testing.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
import math
import random
import time

import cv2
import numpy as np
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


class DroneDetector:
    """Robust Aerial Detection Engine supporting Faster R-CNN and YOLOv8 backends."""
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

        self.transform = transforms.Compose([
            transforms.ToTensor()
        ])

        # Tracking state
        self.next_track_id = 1
        self.active_tracks: Dict[int, TrackedDrone] = {}
        self.max_lost_seconds = 1.5

    def _init_backend(self):
        """Loads the selected deep learning detection architecture."""
        if self.model_type == "yolov8":
            try:
                from ultralytics import YOLO
                self.yolo_model = YOLO("yolov8n.pt")
                logger.info("YOLOv8 nano model loaded successfully.")
                return
            except Exception as e:
                logger.warning(f"Could not load YOLOv8: {e}. Falling back to Faster R-CNN.")
                self.model_type = "fasterrcnn"

        # Default to Faster R-CNN
        try:
            weights = FasterRCNN_ResNet50_FPN_Weights.DEFAULT
            self.model = fasterrcnn_resnet50_fpn(weights=weights)
            self.model.to(self.device)
            self.model.eval()
            if self.device.type == "cuda":
                torch.backends.cudnn.benchmark = True
            logger.info("Faster R-CNN ResNet-50 FPN initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing Faster R-CNN: {e}")
            raise

    def detect(self, frame_bgr: np.ndarray) -> List[TrackedDrone]:
        """Runs object detection and assigns persistent track IDs."""
        if frame_bgr is None or frame_bgr.size == 0:
            return []

        h, w = frame_bgr.shape[:2]
        raw_detections = []

        if self.model_type == "yolov8" and self.yolo_model is not None:
            raw_detections = self._detect_yolo(frame_bgr)
        else:
            raw_detections = self._detect_fasterrcnn(frame_bgr)

        # Associate raw detections with existing tracks
        tracked = self._update_tracks(raw_detections, frame_bgr)
        return tracked

    def _detect_fasterrcnn(self, frame_bgr: np.ndarray) -> List[Tuple[Tuple[int, int, int, int], float, str]]:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        tensor = self.transform(rgb).to(self.device)

        with torch.no_grad():
            predictions = self.model([tensor])[0]

        detections = []
        # CRITICAL FIX: Ensure tensors are transferred to CPU before calling numpy()
        boxes = predictions["boxes"].detach().cpu().numpy()
        scores = predictions["scores"].detach().cpu().numpy()
        labels = predictions["labels"].detach().cpu().numpy()

        for idx, score in enumerate(scores):
            if score >= self.confidence_threshold:
                box = boxes[idx].astype(int)
                x1, y1, x2, y2 = box
                # Clamp to frame boundary
                x1 = max(0, min(frame_bgr.shape[1] - 1, x1))
                y1 = max(0, min(frame_bgr.shape[0] - 1, y1))
                x2 = max(x1 + 1, min(frame_bgr.shape[1], x2))
                y2 = max(y1 + 1, min(frame_bgr.shape[0], y2))

                detections.append(((x1, y1, x2, y2), float(score), "uav"))

        return detections

    def _detect_yolo(self, frame_bgr: np.ndarray) -> List[Tuple[Tuple[int, int, int, int], float, str]]:
        detections = []
        try:
            results = self.yolo_model(frame_bgr, conf=self.confidence_threshold, verbose=False)[0]
            boxes = results.boxes.xyxy.detach().cpu().numpy()
            scores = results.boxes.conf.detach().cpu().numpy()
            classes = results.boxes.cls.detach().cpu().numpy()

            for idx in range(len(boxes)):
                box = boxes[idx].astype(int)
                x1, y1, x2, y2 = box
                score = float(scores[idx])
                cls_id = int(classes[idx])
                cls_name = self.yolo_model.names.get(cls_id, "uav")
                detections.append(((x1, y1, x2, y2), score, cls_name))
        except Exception as e:
            logger.error(f"YOLO detection exception: {e}")
        return detections

    def _update_tracks(
        self,
        raw_detections: List[Tuple[Tuple[int, int, int, int], float, str]],
        frame_bgr: np.ndarray
    ) -> List[TrackedDrone]:
        """Simple greedy distance/IoU multi-object tracking association."""
        now = time.time()
        updated_tracks = []
        assigned_track_ids = set()

        for (bbox, score, label) in raw_detections:
            x1, y1, x2, y2 = bbox
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

            best_match_id = None
            min_dist = float("inf")

            for tid, track in self.active_tracks.items():
                if tid in assigned_track_ids:
                    continue
                dist = math.hypot(cx - track.center[0], cy - track.center[1])
                if dist < 120.0 and dist < min_dist:
                    min_dist = dist
                    best_match_id = tid

            crop = frame_bgr[y1:y2, x1:x2].copy() if (y2 > y1 and x2 > x1) else None

            if best_match_id is not None:
                # Update existing track
                t = self.active_tracks[best_match_id]
                t.bbox = bbox
                t.center = (cx, cy)
                t.confidence = score
                t.class_label = label
                if crop is not None:
                    t.crop = crop
                t.last_updated_time = now
                assigned_track_ids.add(best_match_id)
                updated_tracks.append(t)
            else:
                # Spawn new track
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
                    last_updated_time=now
                )
                self.active_tracks[new_id] = new_track
                assigned_track_ids.add(new_id)
                updated_tracks.append(new_track)

        # Evict stale tracks
        stale_ids = [
            tid for tid, track in self.active_tracks.items()
            if (now - track.last_updated_time) > self.max_lost_seconds
        ]
        for sid in stale_ids:
            del self.active_tracks[sid]

        return updated_tracks


class SyntheticDroneGenerator:
    """Generates synthetic drone video frames and simulated flight paths for live test/demo."""
    def __init__(self, width: int = 640, height: int = 480):
        self.w = width
        self.h = height
        self.x = random.randint(100, width - 100)
        self.y = random.randint(80, height // 2)
        self.vx = random.uniform(-2.5, 2.5)
        self.vy = random.uniform(-1.0, 1.5)
        self.size = 48

    def generate_frame(self) -> np.ndarray:
        # Create dark sky / terrain background
        frame = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        # Horizon gradient
        for i in range(self.h):
            intensity = int(15 + (i / self.h) * 35)
            frame[i, :] = (intensity // 2, intensity, intensity // 3)

        # Update synthetic drone position
        self.x += self.vx
        self.y += self.vy

        # Bounce off boundaries
        if self.x < 50 or self.x > self.w - 50:
            self.vx *= -1
        if self.y < 50 or self.y > self.h - 100:
            self.vy *= -1

        # Draw realistic synthetic multirotor drone
        cx, cy = int(self.x), int(self.y)
        r = self.size // 2

        # Central fuselage
        cv2.circle(frame, (cx, cy), r // 2, (200, 200, 200), -1)
        # Carbon arms
        cv2.line(frame, (cx - r, cy - r // 2), (cx + r, cy + r // 2), (120, 120, 120), 3)
        cv2.line(frame, (cx - r, cy + r // 2), (cx + r, cy - r // 2), (120, 120, 120), 3)
        # Rotors (spinning circle blur)
        for rx, ry in [
            (cx - r, cy - r // 2),
            (cx + r, cy + r // 2),
            (cx - r, cy + r // 2),
            (cx + r, cy - r // 2)
        ]:
            cv2.ellipse(frame, (rx, ry), (12, 4), 0, 0, 360, (230, 230, 230), 1)
            cv2.circle(frame, (rx, ry), 2, (0, 0, 255), -1)

        # Red blinking beacon light
        if int(time.time() * 3) % 2 == 0:
            cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)

        return frame
