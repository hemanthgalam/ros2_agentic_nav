#!/bin/bash
# Brings up Gazebo + SLAM + Nav2 + rosbridge + datum_broadcaster as separate
# `ros2 launch`/`ros2 run` processes rather than one combined launch file.
#
# Why: sim_bridge.launch.py (which IncludeLaunchDescription's all four at
# once) was found to intermittently fail with a launch-internal
# "[Errno 2] No such file or directory: ''" when everything starts
# concurrently under CPU load, even though each component launches cleanly
# on its own. This script mirrors the sequential bring-up that was verified
# to work end-to-end (Gemini -> HITL -> Nav2 goal -> robot motion) during
# development. See docs/ARCHITECTURE.md and the spatialpilot_bridge launch
# file's header comment for more context.
# Not `set -u`: ROS 2's setup.bash scripts reference unset variables
# (e.g. AMENT_TRACE_SETUP_FILES) by design and rely on nounset being off.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source /opt/ros/humble/setup.bash
source "$SCRIPT_DIR/install/setup.bash"

export TURTLEBOT3_MODEL=waffle

echo "[entrypoint] starting Gazebo (turtlebot3_world)..."
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py &
GAZEBO_PID=$!

echo "[entrypoint] waiting for /spawn_entity service..."
for i in $(seq 1 90); do
    if ros2 service list 2>/dev/null | grep -q "^/spawn_entity$"; then
        break
    fi
    sleep 1
done

echo "[entrypoint] waiting for /odom (robot spawned)..."
SPAWNED=0
for i in $(seq 1 30); do
    if ros2 topic list 2>/dev/null | grep -q "^/odom$"; then
        SPAWNED=1
        break
    fi
    sleep 1
done

if [ "$SPAWNED" -eq 0 ]; then
    echo "[entrypoint] /odom not up yet, spawning the robot explicitly..."
    ros2 run gazebo_ros spawn_entity.py -entity waffle \
        -file /opt/ros/humble/share/turtlebot3_gazebo/models/turtlebot3_waffle/model.sdf \
        -x -2.0 -y -0.5 -z 0.01 || true
fi

echo "[entrypoint] unpausing physics (world can start paused)..."
ros2 service call /unpause_physics std_srvs/srv/Empty "{}" >/dev/null 2>&1 || true

echo "[entrypoint] starting slam_toolbox..."
ros2 launch slam_toolbox online_async_launch.py use_sim_time:=true &

echo "[entrypoint] starting Nav2..."
ros2 launch nav2_bringup navigation_launch.py use_sim_time:=true &

echo "[entrypoint] starting rosbridge_server..."
ros2 launch rosbridge_server rosbridge_websocket_launch.xml &

echo "[entrypoint] starting datum_broadcaster..."
ros2 run spatialpilot_bridge datum_broadcaster &

echo "[entrypoint] stack is up. Following Gazebo; container exits if it dies."
wait "$GAZEBO_PID"
