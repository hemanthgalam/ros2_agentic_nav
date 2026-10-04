import { PolygonLayer } from "@deck.gl/layers";

import type { DatumMsg, OdometryMsg } from "@/hooks/useRosBridge";
import { mapToLngLat } from "@/lib/coordinates";

const ARROW_LENGTH_M = 0.5;
const ARROW_WIDTH_M = 0.3;
const FOV_RADIUS_M = 3.0;
const FOV_HALF_ANGLE_DEG = 35;

function yawFromQuaternion(z: number, w: number): number {
  return 2 * Math.atan2(z, w);
}

function rotateCCW(x: number, y: number, yawRad: number): [number, number] {
  const c = Math.cos(yawRad);
  const s = Math.sin(yawRad);
  return [x * c - y * s, x * s + y * c];
}

function localPolygonToLngLat(
  center: [number, number],
  yawRad: number,
  localPoints: [number, number][],
  datum: DatumMsg,
): [number, number][] {
  return localPoints.map(([lx, ly]) => {
    const [rx, ry] = rotateCCW(lx, ly, yawRad);
    return mapToLngLat(center[0] + rx, center[1] + ry, datum);
  });
}

export function createRobotMarkerLayers(odom: OdometryMsg | null, datum: DatumMsg | null) {
  if (!odom || !datum) return [];

  const { x, y } = odom.pose.pose.position;
  const q = odom.pose.pose.orientation;
  const yaw = yawFromQuaternion(q.z, q.w);
  const center: [number, number] = [x, y];

  const arrowLocal: [number, number][] = [
    [ARROW_LENGTH_M, 0],
    [-ARROW_LENGTH_M * 0.5, ARROW_WIDTH_M * 0.5],
    [-ARROW_LENGTH_M * 0.5, -ARROW_WIDTH_M * 0.5],
  ];

  const fovSteps = 12;
  const halfAngle = (FOV_HALF_ANGLE_DEG * Math.PI) / 180;
  const coneLocal: [number, number][] = [[0, 0]];
  for (let i = 0; i <= fovSteps; i++) {
    const angle = -halfAngle + (2 * halfAngle * i) / fovSteps;
    coneLocal.push([FOV_RADIUS_M * Math.cos(angle), FOV_RADIUS_M * Math.sin(angle)]);
  }

  const arrowPolygon = localPolygonToLngLat(center, yaw, arrowLocal, datum);
  const conePolygon = localPolygonToLngLat(center, yaw, coneLocal, datum);

  return [
    new PolygonLayer({
      id: "robot-fov-cone",
      data: [{ polygon: conePolygon }],
      getPolygon: (d: { polygon: [number, number][] }) => d.polygon,
      getFillColor: [56, 189, 248, 60],
      getLineColor: [56, 189, 248, 120],
      lineWidthMinPixels: 1,
      stroked: true,
      filled: true,
    }),
    new PolygonLayer({
      id: "robot-heading-arrow",
      data: [{ polygon: arrowPolygon }],
      getPolygon: (d: { polygon: [number, number][] }) => d.polygon,
      getFillColor: [34, 197, 94, 230],
      getLineColor: [15, 23, 42, 255],
      lineWidthMinPixels: 1,
      stroked: true,
      filled: true,
    }),
  ];
}
