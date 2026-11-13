"""
Threaded Camera and Video Stream Source for CUAS.
Supports real-time webcams, RTSP IP video feeds, local video files, and synthetic drone simulation.
"""

import threading
import time
from typing import Optional, Union, Tuple
import cv2
import numpy as np

from utils.logger import get_logger
from ai_core.detection import SyntheticDroneGenerator

logger = get_logger("CUAS.CameraStream")

class CameraStream:
    """Zero-latency threaded video capture interface."""
    def __init__(
        self,
        source: Union[int, str] = 0,
        width: int = 1280,
        height: int = 720,
        simulation_mode: bool = False
    ):
        self.source = source
        self.width = width
        self.height = height
        self.simulation_mode = simulation_mode

        self.cap: Optional[cv2.VideoCapture] = None
        self.synthetic_gen: Optional[SyntheticDroneGenerator] = None
        self.current_frame: Optional[np.ndarray] = None
        self.is_running = False
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Starts video acquisition in background worker thread."""
        if self.is_running:
            return True

        if self.simulation_mode:
            logger.info("Initializing in SYNTHETIC SIMULATION video mode.")
            self.synthetic_gen = SyntheticDroneGenerator(self.width, self.height)
            self.is_running = True
            self.thread = threading.Thread(target=self._update_synthetic, daemon=True)
            self.thread.start()
            return True

        logger.info(f"Connecting to video source: {self.source}")
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            logger.warning(f"Could not open source {self.source}. Falling back to simulation mode.")
            self.simulation_mode = True
            self.synthetic_gen = SyntheticDroneGenerator(self.width, self.height)
            self.is_running = True
            self.thread = threading.Thread(target=self._update_synthetic, daemon=True)
            self.thread.start()
            return True

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        self.is_running = True
        self.thread = threading.Thread(target=self._update_camera, daemon=True)
        self.thread.start()
        return True

    def _update_camera(self):
        while self.is_running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                # If reading video file, loop back to start
                if isinstance(self.source, str):
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                time.sleep(0.01)
                continue

            with self.lock:
                self.current_frame = frame

            time.sleep(0.005)

    def _update_synthetic(self):
        while self.is_running and self.synthetic_gen:
            frame = self.synthetic_gen.generate_frame()
            with self.lock:
                self.current_frame = frame
            time.sleep(1.0 / 30.0)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Retrieves the latest available frame without blocking."""
        with self.lock:
            if self.current_frame is not None:
                return True, self.current_frame.copy()
        return False, None

    def stop(self):
        """Stops thread and releases hardware handles."""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()
            self.cap = None
        logger.info("CameraStream stopped.")
