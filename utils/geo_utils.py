"""
Geospatial and Tactical Coordinate Utilities for CUAS.
Calculates Haversine distance, initial bearings, forward projection, and geofence containment.
"""

import math
from typing import Tuple, List, Dict, Any

EARTH_RADIUS_M = 6371000.0  # Mean radius in meters

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in meters."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the initial compass bearing from point 1 to point 2 in degrees (0-360)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)

    bearing_rad = math.atan2(y, x)
    bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0
    return bearing_deg


def forward_project(lat: float, lon: float, distance_m: float, bearing_deg: float) -> Tuple[float, float]:
    """Calculate destination coordinates given origin, distance, and bearing."""
    delta = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)

    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta) +
        math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2)
    )

    return math.degrees(phi2), (math.degrees(lambda2) + 540.0) % 360.0 - 180.0


def check_geofence_status(
    target_lat: float,
    target_lon: float,
    base_lat: float,
    base_lon: float,
    inner_killzone_m: float = 500.0,
    warning_perimeter_m: float = 1500.0,
    detection_boundary_m: float = 3500.0
) -> Dict[str, Any]:
    """
    Evaluates target distance to base and returns perimeter breach status.
    Zones:
      - RED: Target inside inner killzone (imminent breach, auto-defense engagement)
      - AMBER: Target inside warning perimeter (active tracking, countermeasure pre-arm)
      - GREEN: Target inside outer detection boundary (early warning)
      - CLEAR: Outside all perimeters
    """
    distance_to_base = haversine_distance(target_lat, target_lon, base_lat, base_lon)
    bearing_from_base = calculate_bearing(base_lat, base_lon, target_lat, target_lon)

    if distance_to_base <= inner_killzone_m:
        zone = "RED"
        threat_level = "CRITICAL"
        description = "INNER PERIMETER BREACH - IMMEDIATE ENGAGEMENT AUTHORIZED"
    elif distance_to_base <= warning_perimeter_m:
        zone = "AMBER"
        threat_level = "HIGH"
        description = "WARNING PERIMETER BREACH - TARGET LOCKED, ECM STANDBY"
    elif distance_to_base <= detection_boundary_m:
        zone = "GREEN"
        threat_level = "ADVISORY"
        description = "APPROACHING PERIMETER - TRACKING INITIATED"
    else:
        zone = "CLEAR"
        threat_level = "LOW"
        description = "EXTERNAL AIRSPACE - NO PERIMETER INFRINGEMENT"

    return {
        "distance_m": round(distance_to_base, 1),
        "bearing_deg": round(bearing_from_base, 1),
        "zone": zone,
        "threat_level": threat_level,
        "description": description
    }
