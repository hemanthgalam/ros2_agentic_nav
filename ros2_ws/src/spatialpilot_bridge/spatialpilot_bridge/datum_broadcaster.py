"""Publishes and updates the ENU<->WGS84 geodetic datum used to project SLAM
data (map frame, metric ENU) onto a real-world satellite map.

The datum is the single source of truth shared between the FastAPI backend
(coordinates.py) and any other ROS-side consumer. It is published on a
transient-local ("latched") topic so late-joining subscribers immediately
get the current calibration, and can be updated at runtime by publishing to
/spatialpilot/set_datum (e.g. from the backend's /api/datum endpoint via
roslibpy) after the operator calibrates it from the map UI.
"""
import json

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import String

LATCHED_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
)


class DatumBroadcaster(Node):
    def __init__(self) -> None:
        super().__init__("datum_broadcaster")

        self.declare_parameter("lat0", 37.4275)
        self.declare_parameter("lon0", -122.1697)
        self.declare_parameter("alt0", 0.0)
        self.declare_parameter("heading_offset_deg", 0.0)

        self._datum = {
            "lat0": self.get_parameter("lat0").value,
            "lon0": self.get_parameter("lon0").value,
            "alt0": self.get_parameter("alt0").value,
            "heading_offset_deg": self.get_parameter("heading_offset_deg").value,
        }

        self._pub = self.create_publisher(String, "/spatialpilot/datum", LATCHED_QOS)
        self._sub = self.create_subscription(
            String, "/spatialpilot/set_datum", self._on_set_datum, 10
        )

        self._publish_datum()
        self.get_logger().info(f"Datum broadcaster started with datum: {self._datum}")

    def _on_set_datum(self, msg: String) -> None:
        try:
            update = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error(f"Ignoring malformed datum update: {msg.data!r}")
            return

        for key in ("lat0", "lon0", "alt0", "heading_offset_deg"):
            if key in update:
                self._datum[key] = float(update[key])

        self._publish_datum()
        self.get_logger().info(f"Datum updated: {self._datum}")

    def _publish_datum(self) -> None:
        msg = String()
        msg.data = json.dumps(self._datum)
        self._pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DatumBroadcaster()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
