#!/bin/bash
# Single-command bring-up for the whole stack: ROS 2 sim/bridge, backend, frontend.
#
# Why not `docker compose up`? That's the containerized path (see
# docker-compose.yml) but wasn't runnable in the sandbox this repo was built
# in (no Docker). This script drives the exact same native bring-up that was
# verified end to end: ros2_ws/entrypoint.sh, then the FastAPI backend, then
# the Next.js frontend, each gated on the previous one's readiness.
#
# Not `set -u`: ROS 2's setup.bash intentionally references unset variables.
set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGDIR="$ROOT/.run/logs"
mkdir -p "$LOGDIR"

# Local pip installs (e.g. via get-pip.py --user) and nvm both land outside
# the default PATH in some shells; make sure this script sees them.
export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" >/dev/null 2>&1
command -v nvm >/dev/null 2>&1 && nvm use default >/dev/null 2>&1 || true

PIDS=()
CLEANED_UP=0

cleanup() {
    [ "$CLEANED_UP" -eq 1 ] && return
    CLEANED_UP=1
    echo
    echo "[start.sh] shutting down..."
    for pid in "${PIDS[@]:-}"; do
        kill -9 "$pid" >/dev/null 2>&1 || true
    done
    # `ros2 launch` fans out into many child processes (nav2's controller_server,
    # planner_server, bt_navigator, etc.; slam_toolbox's node; rosbridge's
    # rosbridge_websocket + rosapi_node). SIGKILL-ing the launch wrapper does
    # NOT cascade to them (only SIGINT/SIGTERM, which launch catches to shut
    # down children, would) — each has to be matched and killed explicitly,
    # or they're left running as orphans after this script exits.
    local patterns=(
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
    for pattern in "${patterns[@]}"; do
        pkill -9 -f "$pattern" >/dev/null 2>&1 || true
    done
    echo "[start.sh] done."
}
trap cleanup EXIT INT TERM

wait_for_tcp() {
    local host="$1" port="$2" timeout="$3"
    for ((i = 0; i < timeout; i++)); do
        (exec 3<>"/dev/tcp/$host/$port") >/dev/null 2>&1 && exec 3>&- 3<&- && return 0
        if ((i > 0 && i % 30 == 0)); then
            echo "[start.sh]     ...still waiting on $host:$port (${i}s elapsed)"
        fi
        sleep 1
    done
    return 1
}

wait_for_http() {
    local url="$1" timeout="$2"
    for ((i = 0; i < timeout; i++)); do
        curl -fs -o /dev/null "$url" >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

# --- 1. ROS 2 stack -----------------------------------------------------
echo "[start.sh] 1/3 ROS 2 stack"
source /opt/ros/humble/setup.bash

if [ ! -d "$ROOT/ros2_ws/install" ]; then
    echo "[start.sh]     workspace not built yet, running colcon build..."
    (cd "$ROOT/ros2_ws" && colcon build --symlink-install --cmake-args -DBUILD_TESTING=OFF)
fi

"$ROOT/ros2_ws/entrypoint.sh" >"$LOGDIR/ros2.log" 2>&1 &
PIDS+=("$!")

echo "[start.sh]     waiting for rosbridge on :9090 (Gazebo startup time varies a lot — this can take anywhere from ~15s to several minutes under load)..."
ROSBRIDGE_TIMEOUT=480
SECONDS=0
if ! wait_for_tcp localhost 9090 "$ROSBRIDGE_TIMEOUT"; then
    echo "[start.sh] ERROR: rosbridge did not come up within ${ROSBRIDGE_TIMEOUT}s — see $LOGDIR/ros2.log"
    exit 1
fi
echo "[start.sh]     rosbridge is up (took ${SECONDS}s)."

# --- 2. Backend -----------------------------------------------------------
echo "[start.sh] 2/3 backend"

if [ ! -f "$ROOT/backend/.env" ]; then
    echo "[start.sh]     backend/.env missing, copying from .env.example (set GEMINI_API_KEY in it)"
    cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
fi

if ! python3 -c "import fastapi, uvicorn, roslibpy, pymap3d, shapely, google.genai" >/dev/null 2>&1; then
    echo "[start.sh]     backend dependencies missing, installing (pip install --user)..."
    python3 -m pip install --user -q -r "$ROOT/backend/requirements.txt"
fi

(cd "$ROOT/backend" && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000) >"$LOGDIR/backend.log" 2>&1 &
PIDS+=("$!")

echo "[start.sh]     waiting for backend on :8000..."
if ! wait_for_http http://localhost:8000/api/status 60; then
    echo "[start.sh] ERROR: backend never came up — see $LOGDIR/backend.log"
    exit 1
fi
echo "[start.sh]     backend is up."

if ! grep -q "GEMINI_API_KEY=.\+" "$ROOT/backend/.env" 2>/dev/null; then
    echo "[start.sh]     WARNING: GEMINI_API_KEY looks unset in backend/.env — /api/chat will report Gemini as unconfigured."
fi

# --- 3. Frontend ------------------------------------------------------------
echo "[start.sh] 3/3 frontend"

if [ ! -f "$ROOT/frontend/.env.local" ]; then
    cp "$ROOT/frontend/.env.local.example" "$ROOT/frontend/.env.local"
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
    echo "[start.sh]     frontend dependencies missing, running npm install..."
    (cd "$ROOT/frontend" && npm install)
fi

(cd "$ROOT/frontend" && npm run dev) >"$LOGDIR/frontend.log" 2>&1 &
PIDS+=("$!")

echo "[start.sh]     waiting for frontend on :3000..."
if ! wait_for_http http://localhost:3000 60; then
    echo "[start.sh] ERROR: frontend never came up — see $LOGDIR/frontend.log"
    exit 1
fi

cat <<EOF

[start.sh] Everything is up:
  Frontend (Mission Control):  http://localhost:3000
  Backend API + Swagger docs:  http://localhost:8000/docs
  rosbridge websocket:         ws://localhost:9090

  Logs: $LOGDIR/{ros2,backend,frontend}.log
  Ctrl+C to stop everything.

EOF

tail -f "$LOGDIR/ros2.log" "$LOGDIR/backend.log" "$LOGDIR/frontend.log"
