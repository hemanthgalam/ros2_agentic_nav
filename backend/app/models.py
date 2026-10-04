"""Pydantic schemas shared across the FastAPI routes."""
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DatumConfig(BaseModel):
    lat0: float = Field(..., description="Latitude (deg) of the ENU/map-frame origin")
    lon0: float = Field(..., description="Longitude (deg) of the ENU/map-frame origin")
    alt0: float = Field(0.0, description="Altitude (m) of the ENU/map-frame origin")
    heading_offset_deg: float = Field(
        0.0, description="Rotation (deg, CW from true north) from ENU +Y (map north) to true north"
    )


class ActionType(str, Enum):
    NAVIGATE_TO_GPS = "navigate_to_gps"
    NAVIGATE_TO_NAMED_PLACE = "navigate_to_named_place"
    STOP_ROBOT = "stop_robot"


class PendingAction(BaseModel):
    """A robot-moving tool call proposed by Gemini, awaiting Human-In-The-Loop approval."""

    action_id: str
    action_type: ActionType
    lat: Optional[float] = None
    lon: Optional[float] = None
    place_name: Optional[str] = None
    map_x: Optional[float] = Field(None, description="Resolved map-frame (ENU) x, meters")
    map_y: Optional[float] = Field(None, description="Resolved map-frame (ENU) y, meters")
    rationale: str = Field("", description="Gemini's stated reason for this action")


class ChatMessage(BaseModel):
    role: Literal["user", "model"]
    text: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="Operator's natural-language prompt", examples=["Go to the loading dock"])
    history: list[ChatMessage] = Field(default_factory=list, description="Prior turns, oldest first")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Gemini's text reply, grounded in tool results where applicable")
    pending_action: Optional[PendingAction] = Field(
        None, description="Set when Gemini proposed a robot-moving action; requires /api/actions/confirm"
    )


class ActionConfirmRequest(BaseModel):
    action_id: str = Field(..., description="The action_id from a ChatResponse.pending_action")
    approve: bool = Field(..., description="True to dispatch the action, False to discard it")


class ActionConfirmResponse(BaseModel):
    action_id: str
    executed: bool = Field(..., description="Whether the action was actually sent to Nav2/ROS")
    detail: str = Field(..., description="Human-readable outcome, including the safety-check reason on rejection")


class RobotStatus(BaseModel):
    connected: bool = Field(..., description="Whether the backend currently has a live rosbridge connection")
    nav_state: str = Field("idle", description="'idle' or 'navigating'")
    x: Optional[float] = Field(None, description="Map-frame (ENU) x, meters")
    y: Optional[float] = Field(None, description="Map-frame (ENU) y, meters")
    yaw_deg: Optional[float] = None
    lat: Optional[float] = Field(None, description="Latitude derived from map-frame pose via the current datum")
    lon: Optional[float] = None
