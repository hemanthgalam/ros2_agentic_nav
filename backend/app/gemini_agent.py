"""Gemini tool-calling loop that turns natural-language prompts into
structured navigation goals.

Design: robot-moving tools (navigate_to_gps / navigate_to_named_place /
stop_robot) never execute directly from here — calling one produces a
PendingAction that main.py surfaces to the frontend for Human-In-The-Loop
approval. Only the read-only get_robot_status tool executes immediately, so
Gemini can ground its replies ("you are currently near X") without a human
in the loop.
"""
from __future__ import annotations

import logging
import uuid
from typing import Callable

from google import genai
from google.genai import types

from app.models import ActionType, ChatMessage, ChatResponse, PendingAction, RobotStatus

logger = logging.getLogger("spatialpilot.gemini_agent")

SYSTEM_INSTRUCTION = """You are SpatialPilot, the mission-control copilot for an autonomous \
mobile robot navigating with ROS 2 Nav2. You translate operator requests into precise \
navigation goals.

Rules:
- Any request that moves the robot MUST go through the navigate_to_gps, \
navigate_to_named_place, or stop_robot tools. Never claim you moved the robot without \
calling a tool — the tool call itself only *proposes* the action; a human approves it \
before the robot moves, so tell the user you are proposing/requesting the move, not that \
it is done.
- Use get_robot_status to ground your answers in the robot's real current position when \
relevant (e.g. "how far to X", "where are we").
- If a request is geographically ambiguous or a named place is not one you were given \
coordinates for, ask a clarifying question instead of guessing coordinates.
- Be concise."""

NAVIGATE_TO_GPS = types.FunctionDeclaration(
    name="navigate_to_gps",
    description="Propose sending the robot to an absolute GPS coordinate.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "lat": types.Schema(type=types.Type.NUMBER, description="Target latitude, degrees"),
            "lon": types.Schema(type=types.Type.NUMBER, description="Target longitude, degrees"),
            "rationale": types.Schema(
                type=types.Type.STRING, description="Why this destination was chosen"
            ),
        },
        required=["lat", "lon"],
    ),
)

NAVIGATE_TO_NAMED_PLACE = types.FunctionDeclaration(
    name="navigate_to_named_place",
    description=(
        "Propose sending the robot to a place identified by name from the operator-provided "
        "list of known semantic places (not a geocoded address)."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "place_name": types.Schema(type=types.Type.STRING),
            "rationale": types.Schema(type=types.Type.STRING),
        },
        required=["place_name"],
    ),
)

STOP_ROBOT = types.FunctionDeclaration(
    name="stop_robot",
    description="Propose immediately canceling any active navigation goal.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={"rationale": types.Schema(type=types.Type.STRING)},
    ),
)

GET_ROBOT_STATUS = types.FunctionDeclaration(
    name="get_robot_status",
    description="Read the robot's current position, heading, and navigation state.",
    parameters=types.Schema(type=types.Type.OBJECT, properties={}),
)

TOOLS = [
    types.Tool(
        function_declarations=[
            NAVIGATE_TO_GPS,
            NAVIGATE_TO_NAMED_PLACE,
            STOP_ROBOT,
            GET_ROBOT_STATUS,
        ]
    )
]

RobotStatusProvider = Callable[[], RobotStatus]
KnownPlaces = dict[str, tuple[float, float]]


class GeminiAgent:
    def __init__(self, api_key: str, model: str, known_places: KnownPlaces | None = None):
        self._client = genai.Client(api_key=api_key) if api_key else None
        self._model = model
        self._known_places = known_places or {}

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def _to_contents(
        self, history: list[ChatMessage], message: str
    ) -> list[types.Content]:
        contents = [
            types.Content(role=m.role, parts=[types.Part.from_text(text=m.text)])
            for m in history
        ]
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
        return contents

    def handle_message(
        self, message: str, history: list[ChatMessage], status_provider: RobotStatusProvider
    ) -> ChatResponse:
        if not self.enabled:
            return ChatResponse(
                reply=(
                    "Gemini is not configured (GEMINI_API_KEY is unset on the backend). "
                    "Set it in backend/.env and restart the server."
                )
            )

        contents = self._to_contents(history, message)
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=TOOLS,
        )

        # get_robot_status is the only tool executed inline (it's read-only), so
        # the model may chain it before deciding on a movement tool call; bound
        # the round-trips so a confused model can't loop forever.
        for _ in range(3):
            response = self._client.models.generate_content(
                model=self._model, contents=contents, config=config
            )

            call = self._first_function_call(response)
            if call is None:
                return ChatResponse(reply=self._text_of(response))

            if call.name != "get_robot_status":
                pending = self._to_pending_action(call)
                reply = pending.rationale or "Proposing this navigation action for your approval."
                return ChatResponse(reply=reply, pending_action=pending)

            status = status_provider()
            contents.append(response.candidates[0].content)
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name="get_robot_status", response=status.model_dump()
                        )
                    ],
                )
            )

        return ChatResponse(
            reply="I wasn't able to settle on an answer after checking robot status. Please rephrase."
        )

    def _to_pending_action(self, call: types.FunctionCall) -> PendingAction:
        args = dict(call.args or {})
        action_id = str(uuid.uuid4())

        if call.name == "navigate_to_gps":
            return PendingAction(
                action_id=action_id,
                action_type=ActionType.NAVIGATE_TO_GPS,
                lat=args.get("lat"),
                lon=args.get("lon"),
                rationale=args.get("rationale", ""),
            )
        if call.name == "navigate_to_named_place":
            place = args.get("place_name", "")
            coords = self._known_places.get(place)
            return PendingAction(
                action_id=action_id,
                action_type=ActionType.NAVIGATE_TO_NAMED_PLACE,
                place_name=place,
                lat=coords[0] if coords else None,
                lon=coords[1] if coords else None,
                rationale=args.get("rationale", ""),
            )
        # stop_robot
        return PendingAction(
            action_id=action_id,
            action_type=ActionType.STOP_ROBOT,
            rationale=args.get("rationale", ""),
        )

    @staticmethod
    def _first_function_call(response) -> types.FunctionCall | None:
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None:
            return None
        for part in candidate.content.parts:
            if part.function_call is not None:
                return part.function_call
        return None

    @staticmethod
    def _text_of(response) -> str:
        return response.text or ""
