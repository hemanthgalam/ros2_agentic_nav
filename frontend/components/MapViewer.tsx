"use client";

import { MapboxOverlay } from "@deck.gl/mapbox";
import {
  IControl,
  Map as MapLibreMap,
  NavigationControl,
  StyleSpecification,
} from "maplibre-gl";
import { useEffect, useRef } from "react";

import { createOccupancyLayer } from "@/components/layers/OccupancyLayer";
import { createRobotMarkerLayers } from "@/components/layers/RobotMarkerLayer";
import { createTrajectoryLayer } from "@/components/layers/TrajectoryLayer";
import type { DatumMsg, OccupancyGridMsg, OdometryMsg } from "@/hooks/useRosBridge";

const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      attribution: "Esri, Maxar, Earthstar Geographics",
    },
  },
  layers: [{ id: "satellite", type: "raster", source: "satellite" }],
};

interface MapViewerProps {
  map: OccupancyGridMsg | null;
  odom: OdometryMsg | null;
  datum: DatumMsg | null;
  trajectory: [number, number][];
  calibrating: boolean;
  onCalibratePick: (lat: number, lon: number) => void;
}

export default function MapViewer({
  map,
  odom,
  datum,
  trajectory,
  calibrating,
  onCalibratePick,
}: MapViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const onCalibratePickRef = useRef(onCalibratePick);
  onCalibratePickRef.current = onCalibratePick;
  const calibratingRef = useRef(calibrating);
  calibratingRef.current = calibrating;

  useEffect(() => {
    if (!containerRef.current) return;

    const glMap = new MapLibreMap({
      container: containerRef.current,
      style: SATELLITE_STYLE,
      center: [datum?.lon0 ?? -122.1697, datum?.lat0 ?? 37.4275],
      zoom: 19,
    });

    const overlay = new MapboxOverlay({ layers: [] });
    glMap.addControl(overlay as unknown as IControl);
    glMap.addControl(new NavigationControl(), "top-right");

    glMap.on("click", (e: { lngLat: { lat: number; lng: number } }) => {
      if (calibratingRef.current) {
        onCalibratePickRef.current(e.lngLat.lat, e.lngLat.lng);
      }
    });

    mapRef.current = glMap;
    overlayRef.current = overlay;

    return () => {
      glMap.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const layers = [
      createOccupancyLayer(map, datum),
      createTrajectoryLayer(trajectory, datum),
      ...createRobotMarkerLayers(odom, datum),
    ].filter(Boolean);

    overlayRef.current?.setProps({ layers });
  }, [map, odom, datum, trajectory]);

  return (
    <div
      ref={containerRef}
      className={`h-full w-full ${calibrating ? "cursor-crosshair" : ""}`}
    />
  );
}
