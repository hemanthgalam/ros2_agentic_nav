FROM osrf/ros:humble-desktop

RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-humble-turtlebot3 \
    ros-humble-turtlebot3-gazebo \
    ros-humble-nav2-bringup \
    ros-humble-slam-toolbox \
    ros-humble-rosbridge-suite \
    python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

ENV TURTLEBOT3_MODEL=waffle
WORKDIR /ros2_ws
COPY src ./src
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

SHELL ["/bin/bash", "-c"]
RUN source /opt/ros/humble/setup.bash && colcon build --symlink-install --cmake-args -DBUILD_TESTING=OFF

# rosbridge_server (websocket bridge to the backend + frontend)
EXPOSE 9090
# Gazebo's own web/master ports, exposed for host tooling (e.g. gzweb, gz topic
# introspection) — not required for SpatialPilot itself.
EXPOSE 11345

# Runs headless: turtlebot3_world.launch.py also starts gzclient (the GUI), but
# with no DISPLAY it fails to open and exits harmlessly — gzserver keeps running.
CMD ["/ros2_ws/entrypoint.sh"]
