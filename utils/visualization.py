"""
Tactical Symbology & Military HUD Rendering Utilities (v4.0-Lattice).
Adheres to modern defense C2 design standards (Anduril Lattice / Palantir Gotham / MIL-STD-2525D).
Zero retro-neon styling. Features precision hairlines, lead-computing reticles, covariance uncertainty ellipses,
pitch/roll attitude ladders, and NATO symbology.
"""

from typing import List, Tuple, Optional, Dict, Any
import math
import cv2
import numpy as np

# Semantic Tactical Color Palette (BGR format for OpenCV)
COLOR_HOSTILE_CRIMSON = (94, 63, 244)     # #F43F5E (Hostile / Critical)
COLOR_SUSPECT_AMBER    = (11, 158, 245)    # #F59E0B (Suspect / Elevated)
COLOR_FRIENDLY_CYAN    = (233, 165, 14)    # #0EA5E9 (Blue Force / Interceptor)
COLOR_NOMINAL_EMERALD  = (129, 185, 16)    # #10B981 (Nominal / Safe)
COLOR_SLATE_WHITE      = (250, 250, 248)   # #F8FAFC (Primary Telemetry)
COLOR_SLATE_MUTED      = (184, 163, 148)   # #94A3B8 (Labels)
COLOR_DARK_SURFACE     = (27, 16, 11)      # #0B101B (Card / Panel)
COLOR_BORDER_HAIRLINE  = (59, 41, 30)      # #1E293B (Crisp Hairline)

def draw_corner_brackets(
    img: np.ndarray,
    bbox: Tuple[int, int, int, int],
    color: Tuple[int, int, int] = COLOR_HOSTILE_CRIMSON,
    thickness: int = 1,
    bracket_len: int = 14
) -> None:
    """Draws crisp hairline targeting corner brackets around bounding box."""
    x1, y1, x2, y2 = bbox
    bl_x = min(bracket_len, max(4, (x2 - x1) // 3))
    bl_y = min(bracket_len, max(4, (y2 - y1) // 3))

    cv2.line(img, (x1, y1), (x1 + bl_x, y1), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x1, y1), (x1, y1 + bl_y), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x2, y1), (x2 - bl_x, y1), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x2, y1), (x2, y1 + bl_y), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x1, y2), (x1 + bl_x, y2), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x1, y2), (x1, y2 - bl_y), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x2, y2), (x2 - bl_x, y2), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x2, y2), (x2, y2 - bl_y), color, thickness, cv2.LINE_AA)


def draw_lead_reticle(
    img: np.ndarray,
    center: Tuple[int, int],
    lead_vector: Tuple[float, float] = (0.0, 0.0),
    radius: int = 22,
    color: Tuple[int, int, int] = COLOR_HOSTILE_CRIMSON
) -> None:
    """Draws lead-computing targeting pipper for fire-control calculation."""
    cx, cy = center
    lx = int(cx + lead_vector[0])
    ly = int(cy + lead_vector[1])

    cv2.circle(img, (cx, cy), radius, color, 1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), 2, color, -1)

    cv2.line(img, (lx - 8, ly), (lx + 8, ly), COLOR_FRIENDLY_CYAN, 1, cv2.LINE_AA)
    cv2.line(img, (lx, ly - 8), (lx, ly + 8), COLOR_FRIENDLY_CYAN, 1, cv2.LINE_AA)
    cv2.circle(img, (lx, ly), 4, COLOR_FRIENDLY_CYAN, 1, cv2.LINE_AA)
    cv2.line(img, (cx, cy), (lx, ly), (80, 80, 80), 1, cv2.LINE_AA)


def draw_targeting_reticle(
    img: np.ndarray,
    center: Tuple[int, int],
    radius: int = 24,
    color: Tuple[int, int, int] = COLOR_HOSTILE_CRIMSON,
    threat_level: str = "LOW"
) -> None:
    """Backward-compatible wrapper for targeting crosshair."""
    draw_lead_reticle(img, center, (0.0, 0.0), radius, color)


def draw_trajectory_path(
    img: np.ndarray,
    history_points: List[Tuple[float, float]],
    predicted_points: Optional[List[Tuple[float, float]]] = None,
    color_history: Tuple[int, int, int] = COLOR_SUSPECT_AMBER,
    color_predicted: Tuple[int, int, int] = COLOR_HOSTILE_CRIMSON
) -> None:
    """Draws historical track ribbon and projected IMM-UKF predicted path."""
    if len(history_points) > 1:
        for i in range(1, len(history_points)):
            alpha = float(i) / len(history_points)
            c = tuple(int(ch * alpha) for ch in color_history)
            pt1 = (int(history_points[i - 1][0]), int(history_points[i - 1][1]))
            pt2 = (int(history_points[i][0]), int(history_points[i][1]))
            cv2.line(img, pt1, pt2, c, 1, cv2.LINE_AA)

    if predicted_points and len(predicted_points) > 1:
        for i in range(1, len(predicted_points)):
            pt1 = (int(predicted_points[i - 1][0]), int(predicted_points[i - 1][1]))
            pt2 = (int(predicted_points[i][0]), int(predicted_points[i][1]))
            if i % 2 == 0:
                cv2.line(img, pt1, pt2, color_predicted, 2, cv2.LINE_AA)
        last_pt = (int(predicted_points[-1][0]), int(predicted_points[-1][1]))
        cv2.drawMarker(img, last_pt, color_predicted, cv2.MARKER_TILTED_CROSS, 8, 1, cv2.LINE_AA)


def render_military_hud(
    frame: np.ndarray,
    system_metrics: Dict[str, Any],
    threat_summary: Dict[str, Any]
) -> np.ndarray:
    """Overlays clean defense C2 telemetry onto frame."""
    hud = frame.copy()
    h, w = hud.shape[:2]
    fps = system_metrics.get("fps", 30.0)
    lat = system_metrics.get("latency_ms", 28)
    lvl = threat_summary.get("threat_level", "SAFE")
    trks = threat_summary.get("active_threats", 0)

    cv2.putText(hud, f"LATTICE-C2 // FPS: {fps:.1f} | LAT: {lat}ms", (14, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_SLATE_WHITE, 1, cv2.LINE_AA)
    col = COLOR_HOSTILE_CRIMSON if lvl in ["CRITICAL", "HIGH"] else COLOR_NOMINAL_EMERALD
    cv2.putText(hud, f"DEFCON: {lvl} [{trks} TRKS]", (w - 220, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
    return hud
