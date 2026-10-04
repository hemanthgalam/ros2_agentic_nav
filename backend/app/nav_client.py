"""Everything that talks to ROS over rosbridge: the live datum, robot pose,
and the Nav2 NavigateToPose action relay.

Uses roslibpy (a synchronous/threaded Twisted-based client) rather than a
native rclpy node so the FastAPI process stays a plain Python process with
no ROS 2 sourcing required for the backend itself — only rosbridge_server
(on the ROS side) needs to be reachable over the network.
"""
from __future__ import annotations

import json
import logging
import math
import threading

import roslibpy

from app.coordinates import Datum
from app.models import DatumConfig, RobotStatus

logger = logging.getLogger("spatialpilot.nav_client")


def _yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    """Yaw (deg) from a geometry_msgs/Quaternion, rotation about +Z."""
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    return math.degrees(math.atan2(siny_cosp, cosy_cosp))


class DatumStore:
    """Thread-safe holder for the currently-calibrated geodetic datum."""

    def __init__(self, initial: Datum):
        self._lock = threading.Lock()
        self._datum = initial

    def get(self) -> Datum:
        with self._lock:
            return self._datum

    def set(self, cfg: DatumConfig) -> None:
        with self._lock:
            self._datum = Datum.from_config(cfg)


class NavClient:
    """Owns the rosbridge connection: pose subscription + Nav2 action relay."""

    def __init__(self, host: str, port: int, datum_store: DatumStore):
        self.datum_store = datum_store
        self.host = host
        self.port = port
        self.ros = roslibpy.Ros(host=host, port=port)
        self._odom_topic: roslibpy.Topic | None = None
        self._datum_topic: roslibpy.Topic | None = None
        self._set_datum_topic: roslibpy.Topic | None = None
        self._action_client: roslibpy.ActionClient | None = None
        self._latest_odom: dict | None = None
        self._nav_state = "idle"
        self._current_goal_id: str | None = None

    def connect(self) -> None:
        self.ros.run(timeout=5)

        self._odom_topic = roslibpy.Topic(self.ros, "/odom", "nav_msgs/Odometry")
        self._odom_topic.subscribe(self._on_odom)

        self._datum_topic = roslibpy.Topic(self.ros, "/spatialpilot/datum", "std_msgs/String")
        self._datum_topic.subscribe(self._on_datum)

        self._set_datum_topic = roslibpy.Topic(
            self.ros, "/spatialpilot/set_datum", "std_msgs/String"
        )

        self._action_client = roslibpy.ActionClient(
            self.ros, "/navigate_to_pose", "nav2_msgs/action/NavigateToPose"
        )

        logger.info("Connected to rosbridge at %s:%s", self.host, self.port)

    def disconnect(self) -> None:
        if self.ros.is_connected:
            self.ros.terminate()

    @property
    def connected(self) -> bool:
        return bool(self.ros.is_connected)

    def _on_odom(self, message: dict) -> None:
        self._latest_odom = message

    def _on_datum(self, message: dict) -> None:
        try:
            data = json.loads(message["data"])
            self.datum_store.set(DatumConfig(**data))
        except Exception:  # noqa: BLE001
            logger.exception("Failed to parse datum broadcast: %s", message)

    def publish_datum(self, cfg: DatumConfig) -> None:
        """Push a new calibration onto the ROS bus (datum_broadcaster re-latches it)."""
        self.datum_store.set(cfg)
        if self._set_datum_topic is not None:
            self._set_datum_topic.publish(roslibpy.Message({"data": json.dumps(cfg.model_dump())}))

    def get_status(self) -> RobotStatus:
        if not self.connected or self._latest_odom is None:
            return RobotStatus(connected=self.connected, nav_state=self._nav_state)

        pose = self._latest_odom["pose"]["pose"]
        x, y = pose["position"]["x"], pose["position"]["y"]
        q = pose["orientation"]
        yaw = _yaw_from_quaternion(q["x"], q["y"], q["z"], q["w"])

        from app.coordinates import map_to_wgs84

        lat, lon, _alt = map_to_wgs84(x, y, self.datum_store.get())

        return RobotStatus(
            connected=True,
            nav_state=self._nav_state,
            x=x,
            y=y,
            yaw_deg=yaw,
            lat=lat,
            lon=lon,
        )

    def send_goal(self, map_x: float, map_y: float, yaw_deg: float = 0.0) -> str:
        """Send a NavigateToPose goal; returns a goal id for tracking/cancellation."""
        if self._action_client is None:
            raise RuntimeError("Action client not connected")

        yaw_rad = math.radians(yaw_deg)
        goal_msg = {
            "pose": {
                "header": {"frame_id": "map"},
                "pose": {
                    "position": {"x": map_x, "y": map_y, "z": 0.0},
                    "orientation": {
                        "x": 0.0,
                        "y": 0.0,
                        "z": math.sin(yaw_rad / 2),
                        "w": math.cos(yaw_rad / 2),
                    },
                },
            }
        }

        goal = roslibpy.Goal(goal_msg)

        def _on_result(result: dict) -> None:
            self._nav_state = "idle"
            logger.info("Nav2 goal finished: %s", result)

        def _on_feedback(feedback: dict) -> None:
            logger.debug("Nav2 goal feedback: %s", feedback)

        def _on_error(error: object) -> None:
            self._nav_state = "idle"
            logger.error("Nav2 goal failed: %s", error)

        goal_id = self._action_client.send_goal(goal, _on_result, _on_feedback, _on_error)
        self._nav_state = "navigating"
        self._current_goal_id = goal_id
        return goal_id

    def cancel_goal(self) -> None:
        if self._current_goal_id is not None and self._action_client is not None:
            self._action_client.cancel_goal(self._current_goal_id)
            self._nav_state = "idle"
