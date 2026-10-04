"""ENU (ROS map frame) <-> WGS84 (lat/lon) conversions.

The robot's SLAM map frame is a local ENU-like plane (x=east-ish, y=north-ish)
but its y-axis is rarely aligned with true north — the TurtleBot3 spawns at
an arbitrary heading in Gazebo/the real world. `heading_offset_deg` is the
clockwise angle from the map frame's +y axis to true north, captured during
datum calibration (DatumConfigModal: the operator clicks the robot's real
position on the satellite map). We rotate map-frame (x, y) into a
true-north-aligned ENU frame before handing off to pymap3d, and the inverse
rotation on the way back.
"""
import math
from dataclasses import dataclass

import pymap3d as pm

from app.models import DatumConfig


@dataclass
class Datum:
    lat0: float
    lon0: float
    alt0: float
    heading_offset_deg: float

    @classmethod
    def from_config(cls, cfg: DatumConfig) -> "Datum":
        return cls(cfg.lat0, cfg.lon0, cfg.alt0, cfg.heading_offset_deg)


def _rotate(x: float, y: float, angle_deg: float) -> tuple[float, float]:
    """Rotate (x, y) clockwise by angle_deg."""
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return (x * cos_t + y * sin_t, -x * sin_t + y * cos_t)


def map_to_wgs84(x: float, y: float, datum: Datum, z: float = 0.0) -> tuple[float, float, float]:
    """Convert a map-frame (ROS ENU-ish) point to (lat, lon, alt)."""
    true_e, true_n = _rotate(x, y, datum.heading_offset_deg)
    lat, lon, alt = pm.enu2geodetic(true_e, true_n, z, datum.lat0, datum.lon0, datum.alt0)
    return float(lat), float(lon), float(alt)


def wgs84_to_map(lat: float, lon: float, datum: Datum, alt: float = 0.0) -> tuple[float, float]:
    """Convert a (lat, lon) point to map-frame (x, y) meters."""
    east, north, _up = pm.geodetic2enu(lat, lon, alt, datum.lat0, datum.lon0, datum.alt0)
    # Inverse rotation: undo the clockwise rotation we applied in map_to_wgs84.
    x, y = _rotate(east, north, -datum.heading_offset_deg)
    return float(x), float(y)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters, used for geofence radius checks."""
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
