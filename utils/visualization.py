"""
HUD and Tactical Military Symbology Rendering for CUAS.
Draws targeting reticles, trajectory paths, velocity vectors, MIL-STD threat icons, and radar scopes.
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict, Any

# Tactical HUD Color Palette (BGR format)
COLOR_GREEN = (0, 255, 0)
COLOR_AMBER = (0, 190, 255)
COLOR_RED = (0, 0, 255)
COLOR_CYAN = (255, 255, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_GREY = (100, 100, 100)

def draw_corner_brackets(
    img: np.ndarray,
    bbox: Tuple[int, int, int, int],
    color: Tuple[int, int, int] = COLOR_GREEN,
    thickness: int = 2,
    bracket_len: int = 16
) -> None:
    """Draws military targeting brackets on the corners of a bounding box."""
    x1, y1, x2, y2 = bbox
    # Clamp bracket length to half of dimensions
    bl_x = min(bracket_len, max(4, (x2 - x1) // 3))
    bl_y = min(bracket_len, max(4, (y2 - y1) // 3))

    # Top-Left
    cv2.line(img, (x1, y1), (x1 + bl_x, y1), color, thickness)
    cv2.line(img, (x1, y1), (x1, y1 + bl_y), color, thickness)
    # Top-Right
    cv2.line(img, (x2, y1), (x2 - bl_x, y1), color, thickness)
    cv2.line(img, (x2, y1), (x2, y1 + bl_y), color, thickness)
    # Bottom-Left
    cv2.line(img, (x1, y2), (x1 + bl_x, y2), color, thickness)
    cv2.line(img, (x1, y2), (x1, y2 - bl_y), color, thickness)
    # Bottom-Right
    cv2.line(img, (x2, y2), (x2 - bl_x, y2), color, thickness)
    cv2.line(img, (x2, y2), (x2, y2 - bl_y), color, thickness)


def draw_targeting_reticle(
    img: np.ndarray,
    center: Tuple[int, int],
    radius: int = 24,
    color: Tuple[int, int, int] = COLOR_GREEN,
    threat_level: str = "LOW"
) -> None:
    """Draws a circular crosshair reticle with threat color coding."""
    cx, cy = center
    if threat_level in ["CRITICAL", "RED"]:
        color = COLOR_RED
    elif threat_level in ["HIGH", "AMBER"]:
        color = COLOR_AMBER

    # Center circle
    cv2.circle(img, (cx, cy), radius, color, 1)
    cv2.circle(img, (cx, cy), 3, color, -1)

    # Cross lines
    cv2.line(img, (cx - radius - 10, cy), (cx - 6, cy), color, 1)
    cv2.line(img, (cx + 6, cy), (cx + radius + 10, cy), color, 1)
    cv2.line(img, (cx, cy - radius - 10), (cx, cy - 6), color, 1)
    cv2.line(img, (cx, cy + 6), (cx, cy + radius + 10), color, 1)


def draw_trajectory_path(
    img: np.ndarray,
    history_points: List[Tuple[int, int]],
    predicted_points: List[Tuple[int, int]] = None,
    color_history: Tuple[int, int, int] = COLOR_CYAN,
    color_predicted: Tuple[int, int, int] = COLOR_AMBER
) -> None:
    """Renders historical breadcrumb points and future projected trajectory."""
    # Past trail
    if len(history_points) > 1:
        for i in range(1, len(history_points)):
            alpha = i / len(history_points)
            c = tuple(int(ch * alpha) for ch in color_history)
            pt1 = (int(history_points[i - 1][0]), int(history_points[i - 1][1]))
            pt2 = (int(history_points[i][0]), int(history_points[i][1]))
            cv2.line(img, pt1, pt2, c, 1, cv2.LINE_AA)
            cv2.circle(img, pt2, 2, c, -1)

    # Future prediction
    if predicted_points and len(predicted_points) > 1:
        for i in range(1, len(predicted_points)):
            pt1 = (int(predicted_points[i - 1][0]), int(predicted_points[i - 1][1]))
            pt2 = (int(predicted_points[i][0]), int(predicted_points[i][1]))
            # Dashed line effect
            if i % 2 == 0:
                cv2.line(img, pt1, pt2, color_predicted, 2, cv2.LINE_AA)
        if len(predicted_points) > 0:
            last_pt = (int(predicted_points[-1][0]), int(predicted_points[-1][1]))
            cv2.drawMarker(img, last_pt, color_predicted, cv2.MARKER_TILTED_CROSS, 10, 2)


def render_military_hud(
    frame: np.ndarray,
    system_metrics: Dict[str, Any],
    threat_summary: Dict[str, Any]
) -> np.ndarray:
    """Overlays high-contrast military HUD telemetry onto the frame."""
    hud = frame.copy()
    h, w = hud.shape[:2]

    # Corner framing
    bracket_size = 28
    cv2.line(hud, (4, 4), (4 + bracket_size, 4), COLOR_GREEN, 2)
    cv2.line(hud, (4, 4), (4, 4 + bracket_size), COLOR_GREEN, 2)
    cv2.line(hud, (w - 4, 4), (w - 4 - bracket_size, 4), COLOR_GREEN, 2)
    cv2.line(hud, (w - 4, 4), (w - 4, 4 + bracket_size), COLOR_GREEN, 2)
    cv2.line(hud, (4, h - 4), (4 + bracket_size, h - 4), COLOR_GREEN, 2)
    cv2.line(hud, (4, h - 4), (4, h - 4 - bracket_size), COLOR_GREEN, 2)
    cv2.line(hud, (w - 4, h - 4), (w - 4 - bracket_size, h - 4), COLOR_GREEN, 2)
    cv2.line(hud, (w - 4, h - 4), (w - 4, h - 4 - bracket_size), COLOR_GREEN, 2)

    # Top HUD Bar
    fps = system_metrics.get("fps", 0.0)
    latency = system_metrics.get("latency_ms", 0)
    device = system_metrics.get("device", "GPU")
    top_bar = f"SYS: ONLINE | {device} | FPS: {fps:.1f} | LAT: {latency}ms"
    cv2.putText(hud, top_bar, (16, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_GREEN, 1, cv2.LINE_AA)

    # Threat Status
    level = threat_summary.get("threat_level", "SAFE")
    threat_count = threat_summary.get("active_threats", 0)
    threat_col = COLOR_RED if level in ["CRITICAL", "HIGH"] else (COLOR_AMBER if level == "ADVISORY" else COLOR_GREEN)
    threat_text = f"THREAT: {level} [{threat_count} TRACKS]"
    cv2.putText(hud, threat_text, (w - 260, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, threat_col, 2, cv2.LINE_AA)

    return hud
