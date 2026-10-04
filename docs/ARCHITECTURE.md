# SpatialPilot Architecture

## 1. High-Level Design (HLD)

SpatialPilot has three deployable units — a ROS 2 stack, a FastAPI backend, and a
Next.js frontend — plus one external dependency, the Gemini API. The browser talks
to two different servers directly: the backend for chat/HITL/calibration (HTTP),
and rosbridge for live telemetry (WebSocket). This split keeps high-frequency
sensor data (map/odom) off the backend's request path entirely.

```mermaid
flowchart LR
    subgraph Operator["Operator's browser"]
        UI["Mission Control UI\n(Next.js / MapLibre / deck.gl)"]
    end

    subgraph ROS["ROS 2 stack (WSL2 / container)"]
        GZ["Gazebo\nTurtleBot3 Waffle"]
        SLAM["slam_toolbox"]
        NAV2["Nav2\n(planner, controller, bt_navigator)"]
        DATUM["datum_broadcaster\n(spatialpilot_bridge)"]
        RB["rosbridge_server\n(ws://:9090)"]
        GZ <-- "/odom /scan /tf" --> SLAM
        SLAM -- "/map" --> RB
        GZ -- "/odom /tf" --> RB
        NAV2 -- "NavigateToPose action" --> RB
        DATUM -- "/spatialpilot/datum" --> RB
    end

    subgraph BE["Backend (FastAPI, :8000)"]
        API["REST API\n/api/chat /api/actions/confirm\n/api/datum /api/status"]
        AGENT["gemini_agent.py\ntool-calling loop"]
        SAFETY["safety.py\ngeofence check"]
        NAVC["nav_client.py\nroslibpy action relay"]
        API --> AGENT
        API --> SAFETY
        API --> NAVC
    end

    GEMINI[("Google Gemini API")]

    UI -- "HTTP: chat, approve/reject,\ncalibrate datum" --> API
    UI -- "WebSocket: /map /odom\n/spatialpilot/datum" --> RB
    AGENT -- "tool-calling" --> GEMINI
    NAVC -- "WebSocket (rosbridge protocol)" --> RB
```

Key architectural decisions:

- **Human-In-The-Loop is structural, not a UI convention.** Gemini's navigation
  tool calls never reach `nav_client.py` directly — `gemini_agent.py` can only
  return a `PendingAction`. Only `/api/actions/confirm`, triggered by an explicit
  operator click, calls `nav_client.send_goal()`, and only after `safety.py`
  re-validates the goal against the geofence.
- **Telemetry bypasses the backend.** The frontend subscribes to `/map`, `/odom`,
  and `/spatialpilot/datum` straight from rosbridge over WebSocket. Routing
  10Hz+ occupancy-grid/odometry data through the FastAPI process would add
  latency and load for no benefit — the backend only needs pose data for
  `get_robot_status` tool calls and geofence checks, which it polls on demand.
- **One geodetic datum, two consumers.** `datum_broadcaster.py` is the source of
  truth on the ROS side (latched topic); `coordinates.py` (Python, ellipsoidal
  via pymap3d) and `lib/coordinates.ts` (TypeScript, flat-earth approximation)
  both implement the same ENU→WGS84 rotation from it — see `coordinates.ts`'s
  docstring for why the frontend's approximation is intentional.

## 2. Low-Level Design (LLD)

### 2.1 Backend module dependencies

```mermaid
flowchart TD
    main["main.py\nFastAPI routes"]
    config["config.py\nSettings (env/.env)"]
    models["models.py\nPydantic schemas"]
    coordinates["coordinates.py\nENU <-> WGS84 (pymap3d)"]
    safety["safety.py\nGeofence"]
    nav_client["nav_client.py\nDatumStore, NavClient (roslibpy)"]
    gemini_agent["gemini_agent.py\nGeminiAgent (google-genai)"]

    main --> config
    main --> models
    main --> coordinates
    main --> safety
    main --> nav_client
    main --> gemini_agent
    safety --> coordinates
    nav_client --> coordinates
    nav_client --> models
    gemini_agent --> models
```

### 2.2 Sequence: natural-language navigation with HITL approval

This is the critical path — every safety property the system has lives in the
gap between the first and second `POST`.

```mermaid
sequenceDiagram
    actor Op as Operator
    participant UI as ChatControl (Next.js)
    participant API as FastAPI /api/chat
    participant Agent as gemini_agent.py
    participant Gemini as Gemini API
    participant Confirm as FastAPI /api/actions/confirm
    participant Safety as safety.py
    participant Nav as nav_client.py
    participant RB as rosbridge
    participant Nav2 as Nav2

    Op->>UI: "go to the loading dock"
    UI->>API: POST /api/chat {message, history}
    API->>Agent: handle_message(...)
    Agent->>Gemini: generate_content(tools=[navigate_to_gps, ...])
    Gemini-->>Agent: function_call: navigate_to_named_place
    Agent-->>API: PendingAction(lat, lon, rationale)
    API-->>UI: ChatResponse{reply, pending_action}
    UI-->>Op: Approval card (lat/lon, rationale)

    Op->>UI: click "Approve"
    UI->>Confirm: POST /api/actions/confirm {action_id, approve:true}
    Confirm->>Safety: validate_goal(lat, lon, datum)
    alt outside geofence
        Safety-->>Confirm: not ok, reason
        Confirm-->>UI: executed:false, detail=reason
    else within geofence
        Safety-->>Confirm: ok
        Confirm->>Nav: send_goal(map_x, map_y)
        Nav->>RB: send_action_goal NavigateToPose
        RB->>Nav2: NavigateToPose.action
        Nav2-->>RB: feedback / result
        Confirm-->>UI: executed:true, detail="Goal sent"
    end
```

### 2.3 Frontend component tree

```mermaid
flowchart TD
    page["app/page.tsx"]
    useRos["useRosBridge()\nWS -> /map /odom /datum"]
    useMission["useGeminiMission()\nchat state + HITL"]
    MapViewer["MapViewer.tsx\nMapLibre + deck.gl MapboxOverlay"]
    OccLayer["layers/OccupancyLayer.ts"]
    RobotLayer["layers/RobotMarkerLayer.ts"]
    TrajLayer["layers/TrajectoryLayer.ts"]
    ChatControl["ChatControl.tsx"]
    DatumModal["DatumConfigModal.tsx"]

    page --> useRos
    page --> useMission
    page --> MapViewer
    page --> ChatControl
    page --> DatumModal
    MapViewer --> OccLayer
    MapViewer --> RobotLayer
    MapViewer --> TrajLayer
    useRos -.->|map, odom, datum, trajectory| MapViewer
    useMission -.->|messages, pendingAction| ChatControl
```

### 2.4 Data model: `PendingAction` lifecycle

A `PendingAction` is created by `gemini_agent.py`, held server-side in
`main.py`'s in-memory `_pending_actions` dict (keyed by `action_id`), and
consumed exactly once by `/api/actions/confirm` — approving or rejecting always
pops it, so a given action can only ever be executed once.

```mermaid
stateDiagram-v2
    [*] --> Proposed: Gemini tool call
    Proposed --> Approved: POST /api/actions/confirm {approve:true}
    Proposed --> Rejected: POST /api/actions/confirm {approve:false}
    Approved --> Dispatched: geofence check passes
    Approved --> Blocked: geofence check fails
    Dispatched --> [*]
    Blocked --> [*]
    Rejected --> [*]
```
