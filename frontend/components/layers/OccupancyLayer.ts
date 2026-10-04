import { BitmapLayer } from "@deck.gl/layers";

import type { DatumMsg, OccupancyGridMsg } from "@/hooks/useRosBridge";
import { mapToLngLat } from "@/lib/coordinates";

function yawFromQuaternion(z: number, w: number): number {
  return 2 * Math.atan2(z, w);
}

function rotateCCW(x: number, y: number, yawRad: number): [number, number] {
  const c = Math.cos(yawRad);
  const s = Math.sin(yawRad);
  return [x * c - y * s, x * s + y * c];
}

/** nav_msgs/OccupancyGrid cost value (-1 unknown, 0..100) -> RGBA. */
function costToRgba(cost: number): [number, number, number, number] {
  if (cost < 0) return [30, 41, 59, 90]; // unknown: translucent slate
  const shade = Math.round(255 * (1 - cost / 100));
  return [shade, shade, shade, 235];
}

function gridToImageData(grid: OccupancyGridMsg): ImageData {
  const { width, height } = grid.info;
  const imageData = new ImageData(width, height);
  const px = imageData.data;

  for (let row = 0; row < height; row++) {
    // OccupancyGrid row 0 is the bottom of the map (y increases upward);
    // canvas/image row 0 is the top, so flip vertically here.
    const destRow = height - 1 - row;
    for (let col = 0; col < width; col++) {
      const cost = grid.data[row * width + col];
      const [r, g, b, a] = costToRgba(cost);
      const idx = (destRow * width + col) * 4;
      px[idx] = r;
      px[idx + 1] = g;
      px[idx + 2] = b;
      px[idx + 3] = a;
    }
  }
  return imageData;
}

/** The grid's four corners in map frame, honoring the grid origin's own yaw. */
function gridCorners(grid: OccupancyGridMsg): [number, number][] {
  const { resolution, width, height, origin } = grid.info;
  const yaw = yawFromQuaternion(origin.orientation.z, origin.orientation.w);
  const w = width * resolution;
  const h = height * resolution;

  const localCorners: [number, number][] = [
    [0, h], // top-left
    [0, 0], // bottom-left
    [w, 0], // bottom-right
    [w, h], // top-right
  ];

  return localCorners.map(([lx, ly]) => {
    const [rx, ry] = rotateCCW(lx, ly, yaw);
    return [rx + origin.position.x, ry + origin.position.y];
  });
}

export function createOccupancyLayer(grid: OccupancyGridMsg | null, datum: DatumMsg | null) {
  if (!grid || !datum) return null;

  const bounds = gridCorners(grid).map(([x, y]) => mapToLngLat(x, y, datum)) as [
    [number, number],
    [number, number],
    [number, number],
    [number, number],
  ];

  return new BitmapLayer({
    id: "occupancy-grid",
    image: gridToImageData(grid),
    bounds,
    opacity: 0.75,
  });
}
