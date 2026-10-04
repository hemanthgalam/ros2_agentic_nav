import { PathLayer } from "@deck.gl/layers";

import type { DatumMsg } from "@/hooks/useRosBridge";
import { mapToLngLat } from "@/lib/coordinates";

export function createTrajectoryLayer(
  trajectory: [number, number][],
  datum: DatumMsg | null,
) {
  if (!datum || trajectory.length < 2) return null;

  const path = trajectory.map(([x, y]) => mapToLngLat(x, y, datum));

  return new PathLayer({
    id: "robot-trajectory",
    data: [{ path }],
    getPath: (d: { path: [number, number][] }) => d.path,
    getColor: [251, 191, 36, 200],
    getWidth: 0.15,
    widthMinPixels: 2,
    capRounded: true,
    jointRounded: true,
  });
}
