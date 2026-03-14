"""
scene_planner.py — builds / updates a SceneState using the Gemini text model
with function calling.
"""
from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types as genai_types

from models import (
    NPCAction,
    NPCBase,
    NPCMood,
    PlaceNPCArgs,
    PlaceObjectArgs,
    SceneObjectBase,
    SceneState,
    SetSceneDescriptionArgs,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions — sent to Gemini as function declarations
# ---------------------------------------------------------------------------

TOOLS = genai_types.Tool(
    function_declarations=[
        genai_types.FunctionDeclaration(
            name="set_scene_description",
            description="Set the overall scene description, lighting and ambient sound.",
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "description": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="A short description of the historical scene.",
                    ),
                    "lighting": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Lighting preset: day | night | dawn | dusk | overcast.",
                    ),
                    "ambient_sound": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Filename of the ambient sound loop, e.g. market.mp3",
                    ),
                },
                required=["description"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="place_npc",
            description="Add or update an NPC in the scene.",
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "npc_id": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Unique id for this NPC (snake_case).",
                    ),
                    "name": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Display name of the NPC.",
                    ),
                    "role": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Historical role or occupation of the NPC.",
                    ),
                    "position": genai_types.Schema(
                        type=genai_types.Type.ARRAY,
                        items=genai_types.Schema(type=genai_types.Type.NUMBER),
                        description="[x, y, z] world position.",
                    ),
                    "mood": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Mood: neutral | happy | sad | angry | fearful | surprised",
                    ),
                    "action": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Current action: idle | walk | run | gesture | sit",
                    ),
                    "dialogue": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Short dialogue line the NPC will say aloud.",
                    ),
                },
                required=["npc_id", "name"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="place_object",
            description="Add or update a 3-D object (GLTF asset) in the scene.",
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={
                    "object_id": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Unique id for this object.",
                    ),
                    "asset": genai_types.Schema(
                        type=genai_types.Type.STRING,
                        description="Filename of the GLTF asset, e.g. market_stall.glb",
                    ),
                    "position": genai_types.Schema(
                        type=genai_types.Type.ARRAY,
                        items=genai_types.Schema(type=genai_types.Type.NUMBER),
                        description="[x, y, z] world position.",
                    ),
                    "rotation": genai_types.Schema(
                        type=genai_types.Type.ARRAY,
                        items=genai_types.Schema(type=genai_types.Type.NUMBER),
                        description="[x, y, z] Euler rotation in radians.",
                    ),
                    "scale": genai_types.Schema(
                        type=genai_types.Type.ARRAY,
                        items=genai_types.Schema(type=genai_types.Type.NUMBER),
                        description="[x, y, z] scale factors.",
                    ),
                },
                required=["object_id", "asset"],
            ),
        ),
        genai_types.FunctionDeclaration(
            name="clear_scene",
            description="Remove all NPCs and objects from the scene.",
            parameters=genai_types.Schema(
                type=genai_types.Type.OBJECT,
                properties={},
            ),
        ),
    ]
)

SYSTEM_PROMPT = (
    "You are Chronos, an AI that recreates historical scenes in 3-D. "
    "When given a user description of a past event or place, you MUST call the "
    "provided functions to populate the scene. Use place_npc for each person "
    "and place_object for significant items. Always call set_scene_description "
    "first. Be historically accurate and vivid. "
    "Return no plain-text content — only function calls."
)


# ---------------------------------------------------------------------------
# ScenePlanner class
# ---------------------------------------------------------------------------


class ScenePlanner:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def plan_scene(self, user_prompt: str, session_id: str) -> SceneState:
        """
        Send *user_prompt* to Gemini with function-calling tools and return a
        fully populated SceneState.
        """
        state = SceneState(session_id=session_id)
        messages: list[genai_types.Content] = [
            genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=user_prompt)],
            )
        ]

        response = self._client.models.generate_content(
            model=self._model,
            contents=messages,
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[TOOLS],
                tool_config=genai_types.ToolConfig(
                    function_calling_config=genai_types.FunctionCallingConfig(
                        mode=genai_types.FunctionCallingConfigMode.ANY
                    )
                ),
            ),
        )

        # Process function calls from the response
        for candidate in response.candidates or []:
            for part in candidate.content.parts or []:
                if part.function_call:
                    self._apply_function_call(
                        state, part.function_call.name, part.function_call.args or {}
                    )

        return state

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_function_call(
        self, state: SceneState, name: str, args: dict[str, Any]
    ) -> None:
        if name == "set_scene_description":
            parsed = SetSceneDescriptionArgs(**args)
            state.description = parsed.description
            state.lighting = parsed.lighting
            state.ambient_sound = parsed.ambient_sound

        elif name == "place_npc":
            parsed = PlaceNPCArgs(**args)
            # Update existing NPC or append new one
            for npc in state.npcs:
                if npc.npc_id == parsed.npc_id:
                    for field, value in parsed.model_dump().items():
                        setattr(npc, field, value)
                    return
            state.npcs.append(
                NPCBase(
                    npc_id=parsed.npc_id,
                    name=parsed.name,
                    role=parsed.role,
                    position=parsed.position,
                    mood=parsed.mood,
                    action=parsed.action,
                    dialogue=parsed.dialogue,
                )
            )

        elif name == "place_object":
            parsed = PlaceObjectArgs(**args)
            for obj in state.objects:
                if obj.object_id == parsed.object_id:
                    for field, value in parsed.model_dump().items():
                        setattr(obj, field, value)
                    return
            state.objects.append(
                SceneObjectBase(
                    object_id=parsed.object_id,
                    asset=parsed.asset,
                    position=parsed.position,
                    rotation=parsed.rotation,
                    scale=parsed.scale,
                )
            )

        elif name == "clear_scene":
            state.npcs.clear()
            state.objects.clear()

        else:
            logger.warning("Unknown function call: %s", name)
