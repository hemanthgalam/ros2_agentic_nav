"use client";

import { useEffect, useRef, useState } from "react";

export interface OccupancyGridMsg {
  info: {
    resolution: number;
    width: number;
    height: number;
    origin: {
      position: { x: number; y: number; z: number };
      orientation: { x: number; y: number; z: number; w: number };
    };
  };
  data: number[];
}

export interface OdometryMsg {
  pose: {
    pose: {
      position: { x: number; y: number; z: number };
      orientation: { x: number; y: number; z: number; w: number };
    };
  };
}

export interface DatumMsg {
  lat0: number;
  lon0: number;
  alt0: number;
  heading_offset_deg: number;
}

interface RosBridgeState {
  connected: boolean;
  map: OccupancyGridMsg | null;
  odom: OdometryMsg | null;
  datum: DatumMsg | null;
  /** Accumulated (x, y) trail of the robot in map frame. */
  trajectory: [number, number][];
}

const ROSBRIDGE_URL =
  process.env.NEXT_PUBLIC_ROSBRIDGE_URL ?? "ws://localhost:9090";

const MAX_TRAJECTORY_POINTS = 5000;

/**
 * Minimal rosbridge v2 protocol client (subscribe-only) speaking JSON
 * directly over WebSocket — avoids the roslibjs dependency for the small
 * set of topics this dashboard needs.
 */
export function useRosBridge(): RosBridgeState {
  const [connected, setConnected] = useState(false);
  const [map, setMap] = useState<OccupancyGridMsg | null>(null);
  const [odom, setOdom] = useState<OdometryMsg | null>(null);
  const [datum, setDatum] = useState<DatumMsg | null>(null);
  const trajectoryRef = useRef<[number, number][]>([]);
  const [trajectory, setTrajectory] = useState<[number, number][]>([]);

  useEffect(() => {
    let ws: WebSocket;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    const subscribe = (socket: WebSocket, topic: string, type: string) => {
      socket.send(JSON.stringify({ op: "subscribe", topic, type }));
    };

    const connect = () => {
      if (cancelled) return;
      ws = new WebSocket(ROSBRIDGE_URL);

      ws.onopen = () => {
        setConnected(true);
        subscribe(ws, "/map", "nav_msgs/OccupancyGrid");
        subscribe(ws, "/odom", "nav_msgs/Odometry");
        subscribe(ws, "/spatialpilot/datum", "std_msgs/String");
      };

      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) reconnectTimer = setTimeout(connect, 2000);
      };

      ws.onerror = () => ws.close();

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (parsed.op !== "publish") return;

          switch (parsed.topic) {
            case "/map":
              setMap(parsed.msg as OccupancyGridMsg);
              break;
            case "/odom": {
              const msg = parsed.msg as OdometryMsg;
              setOdom(msg);
              const { x, y } = msg.pose.pose.position;
              const trail = trajectoryRef.current;
              const last = trail[trail.length - 1];
              if (!last || Math.hypot(last[0] - x, last[1] - y) > 0.05) {
                trail.push([x, y]);
                if (trail.length > MAX_TRAJECTORY_POINTS) trail.shift();
                setTrajectory([...trail]);
              }
              break;
            }
            case "/spatialpilot/datum":
              setDatum(JSON.parse(parsed.msg.data) as DatumMsg);
              break;
            default:
              break;
          }
        } catch {
          // Ignore malformed frames rather than tearing down the socket.
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  return { connected, map, odom, datum, trajectory };
}
