# SpatialPilot

Natural-language mission control for a ROS 2 AMR: drive a TurtleBot3 (Nav2 +
slam_toolbox) with Gemini tool-calling, visualized on a satellite map via
MapLibre GL JS + deck.gl.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the high-level system
design and low-level module/sequence diagrams.

This repo was built and verified natively inside WSL2 (ROS 2 Humble, Gazebo,
TurtleBot3 and Nav2 already installed there), end to end: Gemini proposing a
goal, HITL approval, and the robot actually driving in Gazebo. A Docker path
is also provided (§4) for machines that don't already have ROS 2 installed.

## 1. ROS 2 simulation + bridge

```bash
sudo apt install ros-humble-rosbridge-suite   # not installed by default

cd ros2_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash

./entrypoint.sh
```

This brings up: Gazebo with a TurtleBot3 Waffle, slam_toolbox (online async),
Nav2, `rosbridge_server` on `ws://localhost:9090`, and the datum broadcaster
on `/spatialpilot/datum` — as separate `ros2 launch`/`ros2 run` processes,
waiting for each dependency (the `/spawn_entity` service, `/odom`) before
starting the next.

> **Why `entrypoint.sh` and not `ros2 launch spatialpilot_bridge
> sim_bridge.launch.py`?** That combined launch file (which includes all four
> stacks via `IncludeLaunchDescription`) is still in the repo and works, but
> was found to intermittently fail with a launch-internal `[Errno 2] No such
> file or directory: ''` when everything starts concurrently under CPU load —
> each component launches cleanly on its own, just not reliably all at once.
> `entrypoint.sh` is the sequential bring-up that was verified end-to-end
> (Gemini → HITL approval → Nav2 goal → the robot actually driving in
> Gazebo). See `docs/ARCHITECTURE.md` and the launch file's own comments.

Sanity checks:

```bash
ros2 topic echo /spatialpilot/datum --once
ros2 topic hz /map
ros2 topic hz /odom
```

## 2. Backend (FastAPI + Gemini)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # requires python3-venv
pip install -r requirements.txt

cp .env.example .env
# edit .env: set GEMINI_API_KEY (https://aistudio.google.com/apikey)

uvicorn app.main:app --reload --port 8000
```

> If your system Python has neither `pip` nor `ensurepip` (some minimal ROS
> images don't), `sudo apt install python3-pip python3.10-venv`, or bootstrap
> pip without sudo via `curl -fsSL https://bootstrap.pypa.io/get-pip.py |
> python3 - --user`.

Sanity checks:

```bash
curl localhost:8000/api/status
curl localhost:8000/api/datum
```

**Interactive API docs** (Swagger UI / OpenAPI): open
http://localhost:8000/docs (or `/redoc` for ReDoc, `/openapi.json` for the
raw schema). Every route is documented and typed from the Pydantic models in
`backend/app/models.py` — try `/api/chat` and `/api/actions/confirm` directly
from the Swagger UI to exercise the HITL flow without the frontend.

## 3. Frontend (Next.js)

> This WSL2 distro had no native Linux Node.js — `node`/`npm` on PATH were
> actually the Windows-side binaries via WSL interop (`/mnt/c/Program Files/nodejs`),
> which breaks tools like `tsc` on path translation. A native Linux Node 24 LTS
> was installed via `nvm` (`~/.nvm`) and used to install, typecheck, and build
> this frontend. Open a fresh shell (or `source ~/.bashrc`) so `nvm` is on PATH,
> then `nvm use default`, before running the commands below.

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open http://localhost:3000. Use the "Calibrate datum" button to click the
robot's real-world position on the satellite map (one-time, or whenever the
sim world changes) so the occupancy grid / robot marker project correctly.

## 4. Docker (all-in-one)

```bash
cp .env.example .env
# edit .env: set GEMINI_API_KEY

docker compose up --build
```

This builds and runs three containers on one compose network:

| service    | image base               | exposes | notes |
|------------|---------------------------|---------|-------|
| `ros2`     | `osrf/ros:humble-desktop` | `9090`  | Gazebo + slam_toolbox + Nav2 + rosbridge, via `ros2_ws/entrypoint.sh` |
| `backend`  | `python:3.11-slim`        | `8000`  | talks to `ros2` over the internal network (`ROSBRIDGE_HOST=ros2`) |
| `frontend` | `node:20-slim` (multi-stage, Next.js standalone output) | `3000` | server-side calls `backend` internally; the *browser* connects to `ws://localhost:9090` directly for telemetry, so rosbridge's port is published to the host too |

Then open http://localhost:3000, and http://localhost:8000/docs for the API.

> **This could not be built/run here.** This environment has Docker Desktop
> installed on the Windows host but its WSL2 integration wasn't enabled for
> this distro, so `docker`/`docker compose` aren't reachable from inside it —
> everything above (§1-3) was what got verified end-to-end instead, and this
> compose setup mirrors that exact working configuration (same entrypoint
> script, same env vars, same port layout) as closely as possible. If it
> doesn't come up cleanly for you:
> - `docker compose logs ros2` first — Gazebo taking a long time to expose
>   `/spawn_entity` was the main source of flakiness natively too;
>   `entrypoint.sh` waits up to 90s for it.
> - Gazebo needs no GPU/display for this headless setup (`gzclient` fails to
>   open without a `DISPLAY` and exits harmlessly; `gzserver` keeps running).
> - If `backend` logs connection errors to rosbridge, confirm the `ros2`
>   container is healthy and reachable at `ros2:9090` on the compose network
>   (`docker compose exec backend python3 -c "import socket;
>   socket.create_connection(('ros2', 9090), timeout=3)"`).

## Notes on Human-In-The-Loop safety

Every navigation request from Gemini (`navigate_to_gps`,
`navigate_to_named_place`, `stop_robot`) returns a `PendingAction` that the
operator must explicitly approve in the chat panel before anything is sent
to Nav2. Approved goals are still re-validated against a geofence
(`backend/app/safety.py`, configurable via `GEOFENCE_MAX_RADIUS_M` in
`.env`) immediately before dispatch.
