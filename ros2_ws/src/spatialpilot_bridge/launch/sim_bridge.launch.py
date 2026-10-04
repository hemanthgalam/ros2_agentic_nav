"""Brings up the full SpatialPilot simulation + bridge stack:

  TurtleBot3 Gazebo world -> slam_toolbox (async) -> Nav2 -> rosbridge_server
  -> datum_broadcaster

so the FastAPI backend and Next.js frontend have a single launch file to
depend on. Requires TB3_MODEL=waffle in the environment (set below) and the
turtlebot3_gazebo / nav2_bringup / slam_toolbox / rosbridge_server packages.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
)
from launch.launch_description_sources import (
    FrontendLaunchDescriptionSource,
    PythonLaunchDescriptionSource,
)
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    use_sim_time = LaunchConfiguration("use_sim_time")

    tb3_gazebo_dir = get_package_share_directory("turtlebot3_gazebo")
    slam_toolbox_dir = get_package_share_directory("slam_toolbox")
    nav2_bringup_dir = get_package_share_directory("nav2_bringup")
    rosbridge_dir = get_package_share_directory("rosbridge_server")

    declare_use_sim_time = DeclareLaunchArgument(
        "use_sim_time", default_value="true", description="Use Gazebo simulation clock"
    )
    declare_map_yaml = DeclareLaunchArgument(
        "map",
        default_value="",
        description="Full path to a saved map yaml; empty means SLAM builds the map live",
    )

    set_tb3_model = SetEnvironmentVariable("TURTLEBOT3_MODEL", "waffle")

    gazebo_world = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tb3_gazebo_dir, "launch", "turtlebot3_world.launch.py")
        )
    )

    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(slam_toolbox_dir, "launch", "online_async_launch.py")
        ),
        launch_arguments={"use_sim_time": use_sim_time}.items(),
    )

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, "launch", "navigation_launch.py")
        ),
        launch_arguments={"use_sim_time": use_sim_time}.items(),
    )

    rosbridge = IncludeLaunchDescription(
        FrontendLaunchDescriptionSource(
            os.path.join(rosbridge_dir, "launch", "rosbridge_websocket_launch.xml")
        )
    )

    datum_broadcaster = Node(
        package="spatialpilot_bridge",
        executable="datum_broadcaster",
        name="datum_broadcaster",
        output="screen",
    )

    return LaunchDescription(
        [
            declare_use_sim_time,
            declare_map_yaml,
            set_tb3_model,
            gazebo_world,
            slam,
            nav2,
            rosbridge,
            datum_broadcaster,
        ]
    )
