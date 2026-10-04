/**
 * Map-frame (ROS ENU-ish) -> [lng, lat] projection for rendering on
 * MapLibre/deck.gl.
 *
 * This mirrors backend/app/coordinates.py's rotation-by-heading-offset step,
 * but uses a flat-earth (equirectangular) approximation instead of
 * pymap3d's ellipsoidal geodetic conversion. That's intentional: at the
 * building/campus scale this dashboard operates at (a few hundred meters,
 * per the geofence), the error versus the backend's ellipsoidal math is a
 * few centimeters — irrelevant for visualization — and it keeps the
 * frontend dependency-free. The backend's coordinates.py remains the
 * authoritative transform for anything that actually drives the robot.
 */
import type { DatumMsg } from "@/hooks/useRosBridge";

const EARTH_RADIUS_M = 6371000;

function rotateClockwise(x: number, y: number, angleDeg: number): [number, number] {
  const theta = (angleDeg * Math.PI) / 180;
  const cosT = Math.cos(theta);
  const sinT = Math.sin(theta);
  return [x * cosT + y * sinT, -x * sinT + y * cosT];
}

export function mapToLngLat(x: number, y: number, datum: DatumMsg): [number, number] {
  const [east, north] = rotateClockwise(x, y, datum.heading_offset_deg);
  const lat = datum.lat0 + (north / EARTH_RADIUS_M) * (180 / Math.PI);
  const lon =
    datum.lon0 +
    (east / (EARTH_RADIUS_M * Math.cos((datum.lat0 * Math.PI) / 180))) * (180 / Math.PI);
  return [lon, lat];
}

export function headingDegToMapYawDeg(headingOffsetDeg: number, yawRad: number): number {
  // Robot heading (yaw, CCW from map +x) rotated into a compass bearing
  // (CW from true north) for icon rotation on the map.
  const yawDeg = (yawRad * 180) / Math.PI;
  return (90 - yawDeg + headingOffsetDeg + 360) % 360;
}
