"""FastAPI app: chat/Gemini, HITL action confirmation, datum calibration,
and robot status — the single backend the Next.js frontend talks to.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.coordinates import Datum, wgs84_to_map
from app.gemini_agent import GeminiAgent
from app.models import (
    ActionConfirmRequest,
    ActionConfirmResponse,
    ActionType,
    ChatRequest,
    ChatResponse,
    DatumConfig,
    PendingAction,
    RobotStatus,
)
from app.nav_client import DatumStore, NavClient
from app.safety import Geofence, validate_goal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spatialpilot.main")

settings = get_settings()

datum_store = DatumStore(
    Datum(
        settings.datum_lat0,
        settings.datum_lon0,
        settings.datum_alt0,
        settings.datum_heading_offset_deg,
    )
)
nav_client = NavClient(settings.rosbridge_host, settings.rosbridge_port, datum_store)
geofence = Geofence(max_radius_m=settings.geofence_max_radius_m)
gemini_agent = GeminiAgent(api_key=settings.gemini_api_key, model=settings.gemini_model)

# Pending HITL actions awaiting operator approval, keyed by action_id.
_pending_actions: dict[str, PendingAction] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        nav_client.connect()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Could not connect to rosbridge at %s:%s — is sim_bridge.launch.py running? "
            "Endpoints will report connected=false until it is reachable.",
            settings.rosbridge_host,
            settings.rosbridge_port,
        )
    yield
    nav_client.disconnect()


app = FastAPI(
    title="SpatialPilot Backend",
    description=(
        "Spatial orchestrator for a ROS 2 AMR: turns natural-language prompts into "
        "Gemini tool calls, resolves them to geofenced Nav2 goals, and requires "
        "explicit Human-In-The-Loop approval before anything moves the robot.\n\n"
        "Interactive docs: this page (Swagger UI) and [/redoc](/redoc) (ReDoc)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status", response_model=RobotStatus, tags=["telemetry"], summary="Get live robot status")
def get_status() -> RobotStatus:
    """Current rosbridge connection state, pose, and nav state, as last reported by /odom."""
    return nav_client.get_status()


@app.get("/api/datum", response_model=DatumConfig, tags=["datum"], summary="Get the current geodetic datum")
def get_datum() -> DatumConfig:
    """The WGS84 anchor + heading offset currently used to project map-frame poses to lat/lon."""
    d = datum_store.get()
    return DatumConfig(lat0=d.lat0, lon0=d.lon0, alt0=d.alt0, heading_offset_deg=d.heading_offset_deg)


@app.post("/api/datum", response_model=DatumConfig, tags=["datum"], summary="Calibrate the geodetic datum")
def set_datum(cfg: DatumConfig) -> DatumConfig:
    """Set a new datum (e.g. from DatumConfigModal) and re-publish it onto the ROS bus."""
    nav_client.publish_datum(cfg)
    return cfg


@app.post("/api/chat", response_model=ChatResponse, tags=["mission"], summary="Send a natural-language mission prompt")
def chat(req: ChatRequest) -> ChatResponse:
    """Runs one turn of the Gemini tool-calling loop. A navigation/stop tool call comes
    back as `pending_action` for HITL approval via /api/actions/confirm — it is never
    executed here."""
    response = gemini_agent.handle_message(req.message, req.history, nav_client.get_status)
    if response.pending_action is not None:
        _pending_actions[response.pending_action.action_id] = response.pending_action
    return response


@app.post(
    "/api/actions/confirm",
    response_model=ActionConfirmResponse,
    tags=["mission"],
    summary="Approve or reject a pending action",
)
def confirm_action(req: ActionConfirmRequest) -> ActionConfirmResponse:
    """Human-In-The-Loop gate: only on approval is the action re-validated against the
    geofence (safety.py) and, if it passes, dispatched to Nav2."""
    action = _pending_actions.pop(req.action_id, None)
    if action is None:
        raise HTTPException(status_code=404, detail="No such pending action (already resolved?)")

    if not req.approve:
        return ActionConfirmResponse(action_id=req.action_id, executed=False, detail="Rejected by operator.")

    if action.action_type == ActionType.STOP_ROBOT:
        nav_client.cancel_goal()
        return ActionConfirmResponse(action_id=req.action_id, executed=True, detail="Stop command sent.")

    if action.lat is None or action.lon is None:
        return ActionConfirmResponse(
            action_id=req.action_id,
            executed=False,
            detail="Action has no resolved coordinates (unknown place name?).",
        )

    datum = datum_store.get()
    result = validate_goal(action.lat, action.lon, datum, geofence)
    if not result.ok:
        return ActionConfirmResponse(action_id=req.action_id, executed=False, detail=f"Rejected by safety check: {result.reason}")

    map_x, map_y = wgs84_to_map(action.lat, action.lon, datum)
    nav_client.send_goal(map_x, map_y)
    return ActionConfirmResponse(
        action_id=req.action_id,
        executed=True,
        detail=f"Goal sent: map=({map_x:.2f}, {map_y:.2f}) from lat/lon ({action.lat:.6f}, {action.lon:.6f}).",
    )
