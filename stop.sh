#!/bin/bash
# Force-stops every process start.sh can leave running (ROS 2 stack, backend,
# frontend) and frees ports 3000/8000/9090, even if start.sh's own Ctrl+C
# cleanup was skipped (e.g. the terminal was closed instead).
set -eo pipefail

patterns=(
    "ros2_ws/entrypoint.sh"
    "gzserver" "gzclient"
    "ros2 launch" "ros2 run"
    "async_slam_toolbox_node"
    "controller_server" "planner_server" "smoother_server" "behavior_server"
    "bt_navigator" "waypoint_follower" "velocity_smoother" "lifecycle_manager"
    "rosbridge_websocket" "rosapi_node"
    "uvicorn app.main"
    "next-server" "next dev"
)

echo "[stop.sh] killing SpatialPilot processes..."
for pattern in "${patterns[@]}"; do
    pkill -9 -f "$pattern" >/dev/null 2>&1 || true
done

sleep 1

echo "[stop.sh] port check:"
for p in 3000 8000 9090; do
    if ss -tln 2>/dev/null | grep -q ":$p "; then
        echo "  :$p  STILL IN USE"
    else
        echo "  :$p  free"
    fi
done
