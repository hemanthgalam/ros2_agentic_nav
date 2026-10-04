"""Geofence and sanity checks a candidate goal must pass before Nav2 ever
sees it. This is the last line of defense before HITL-approved actions are
executed — keep it dependency-light and fail closed (any exception => reject).
"""
from dataclasses import dataclass

from shapely.geometry import Point, Polygon

from app.coordinates import Datum, haversine_m


@dataclass
class GeofenceResult:
    ok: bool
    reason: str = ""


class Geofence:
    """Circular geofence around the datum, optionally tightened by a polygon."""

    def __init__(self, max_radius_m: float, polygon_latlon: list[tuple[float, float]] | None = None):
        self.max_radius_m = max_radius_m
        self.polygon = Polygon(polygon_latlon) if polygon_latlon else None

    def check(self, lat: float, lon: float, datum: Datum) -> GeofenceResult:
        try:
            distance = haversine_m(datum.lat0, datum.lon0, lat, lon)
        except Exception as exc:  # noqa: BLE001 - fail closed on any math error
            return GeofenceResult(False, f"Could not evaluate geofence: {exc}")

        if distance > self.max_radius_m:
            return GeofenceResult(
                False,
                f"Target is {distance:.1f}m from the datum, exceeding the "
                f"{self.max_radius_m:.0f}m geofence radius.",
            )

        if self.polygon is not None and not self.polygon.contains(Point(lon, lat)):
            return GeofenceResult(False, "Target falls outside the configured geofence polygon.")

        return GeofenceResult(True)


def validate_goal(
    lat: float, lon: float, datum: Datum, geofence: Geofence
) -> GeofenceResult:
    if lat is None or lon is None:
        return GeofenceResult(False, "Missing lat/lon for goal.")
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return GeofenceResult(False, "lat/lon out of valid range.")
    return geofence.check(lat, lon, datum)
