"""
scene_planner.py — builds / updates a SceneState or ScenePlan using Gemini.

Legacy interface  : ScenePlanner.plan_scene()          → SceneState  (function calling)
New interface     : ScenePlanner.generate_scene_plan() → ScenePlan   (JSON mode + validation)
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from google import genai
from google.genai import types as genai_types
from pydantic import ValidationError

from models import (
    # Legacy models
    NPCAction,
    NPCBase,
    NPCMood,
    PlaceNPCArgs,
    PlaceObjectArgs,
    SceneObjectBase,
    SceneState,
    SetSceneDescriptionArgs,
    # ScenePlan models
    AnimationHint,
    ArchitectureStyle,
    Atmosphere,
    CameraStart,
    Character,
    CharacterArchetype,
    Fog,
    Light,
    LightType,
    Material,
    MaterialType,
    Position3D,
    Prop,
    Room,
    ScenePlan,
    ShapeType,
    SkyboxHint,
    SoundID,
    TimeOfDay,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — enforces constraints on Gemini's ScenePlan output
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are Chronos, a scene generation AI for a 3D historical immersion application "
    "built on React Three Fiber. "
    "OUTPUT: Respond ONLY with a single valid JSON object matching the ScenePlan schema. "
    "No markdown fences, no prose, no commentary outside the JSON.\n\n"
    "HARD CONSTRAINTS:\n"
    "- scene: single room or bounded outdoor area only. No open worlds.\n"
    "- props: maximum 6. shape must be one of: box, sphere, cylinder. No other values.\n"
    "- characters: maximum 3.\n"
    "- Every prop and character must have an exact x/y/z position — no relative positions.\n"
    "- room must be a JSON object with exactly these keys: "
    "width (float, 0–20), depth (float, 0–20), height (float, 0–5), "
    "fog (object with keys color, near, far), ambient_color (hex string). "
    "Do NOT use keys named 'size', 'dimensions', 'colour', or any other variant.\n"
    "- Characters always stand at y=0. Character body: ~0.4 m wide, ~1.8 m tall.\n"
    "- Interactable props must include interact_type (read or inspect), "
    "interact_text (max 6 words), and interact_content (max 50 words).\n"
    "- Every character must have: id (snake_case string — NOT 'character_id'), "
    "name, a one-sentence role description, "
    "head_portrait_prompt (max 30 words, portrait style, white background), "
    "persona_summary (max 60 words, written as direct second-person instructions "
    "for a voice agent system prompt), and interact_text (required on every "
    "character, max 6 words, regardless of interactable).\n"
    "- lights: maximum 3. Each must specify type ('point', 'spot', or 'ambient'), "
    "position, color (hex string — use 'color', NOT 'colour'), "
    "and intensity (0.0–2.0).\n"
    "- ambient_sounds: maximum 2. Only use values from: "
    "radio_chatter, console_beeps, crowd_murmur, wind, fire_crackling, "
    "church_bells, horse_hooves, typewriter_clatter, machinery_hum, silence.\n"
    "- intro_narration: maximum 2 sentences, spoken by a neutral narrator, "
    "sets the scene without revealing outcomes.\n"
    "- All x and z positions: within [-10, 10]. All y positions: within [0, 5].\n"
    "- camera_start.y must be exactly 1.6.\n\n"
    "ENHANCED FIELD RULES:\n"
    "- material_type on each prop must reflect the actual physical substance "
    "(wood, metal, fabric, glass, stone, plastic, paper, leather, ceramic), "
    "not just the label word.\n"
    "- scale on each prop uses a base unit of roughly 0.4 metres. Produce "
    "believable relative sizing — a wide desk is much wider than a candle.\n"
    "- rotation_y on props and characters should orient them logically toward "
    "the scene focus rather than all facing the same direction.\n"
    "- emissive must only be true for props that actually emit visible light "
    "(candles, lamps, monitors, fire). emissive_color should be physically "
    "appropriate — warm orange (#ff8c00) for flame, cool blue (#4488ff) for screens.\n"
    "- animation_hint on each character must reflect what the character is "
    "literally doing at the dramatic moment. Values: idle_standing, idle_sitting, "
    "working_console, walking, pointing, talking_gesture, saluting, writing, watching_sky.\n"
    "- archetype on each character selects a base character mesh — choose the "
    "closest era and gender match. Values: formal_male, formal_female, "
    "military_male, military_female, laborer, scientist, civilian.\n"
    "- room.time_of_day must match the real historical event. Values: "
    "dawn, morning, midday, afternoon, dusk, evening, night, unknown.\n"
    "- room.atmosphere must reflect the emotional register of the dramatic moment. "
    "Values: tense, solemn, triumphant, mundane, chaotic, quiet, celebratory, ominous.\n"
    "- room.ambient_light_color must match the combined effect of all light sources.\n"
    "- room.architecture_style: victorian, colonial_american, ancient_roman, "
    "ancient_greek, medieval_european, ww1_trench, ww2_bunker, mid_century_modern, "
    "space_age, contemporary.\n"
    "- skybox_hint must be none for any fully enclosed indoor scene. Values: "
    "none, night_stars, overcast, clear_day, sunrise, sunset, stormy.\n"
    "- lights: decay defaults to 2 for inverse-square falloff. "
    "cast_shadow defaults to true. source_label is a hint like candle, gas lamp, "
    "monitor glow, or fire.\n\n"
    "GLTF ASSET HINTS:\n"
    "- Each prop may optionally include a gltf_asset field (string or null). "
    "When set, the frontend loads a 3D glTF model for visual realism instead of "
    "rendering a primitive shape. The primitive shape is kept as a fallback.\n"
    "- Available asset slugs: abandoned_mansion_bedroom, armor_set, british_pub, "
    "furniture_a_models_from_fps_creator_classic, gameready_colt_python_revolver, "
    "garden_table, human_models_set_malefemale_rigged, "
    "knight_includes_file_for_3d_printing, medieval_tavern, old_bar, old_town, "
    "restaurant_in_the_evening, ruins_of_hore_abbey, "
    "stylized_medieval_castle_room, table_and_chairs_low_poly.\n"
    "- Only use a gltf_asset slug when the asset is a close match for the prop. "
    "If no asset matches, leave gltf_asset as null and the primitive renders.\n"
    "- gltf_asset is optional; omit it or set to null when no suitable asset exists.\n\n"
    "QUALITY RULES:\n"
    "- Props must be historically plausible. No anachronistic objects.\n"
    "- Characters must be real historical figures if the event is documented, "
    "or clearly fictional archetypes otherwise. Never invent names for real undocumented figures.\n"
    "- Character positions must be spatially logical.\n"
    "- props[].dimensions must be a JSON array of exactly 3 floats [width, height, depth] "
    "(e.g. [1.5, 0.8, 0.75]) — NOT an object or named keys. "
    "Dimensions must be realistic in metres "
    "(desk ~[1.5, 0.75, 0.8], chair ~[0.5, 0.9, 0.5]).\n"
    "- Exactly one character must have primary=true "
    "(the one the user approaches first for voice interaction).\n"
    "- dramatic_moment must be at most 20 words.\n"
    "- The scene must have clear dramatic tension — something is about to happen, "
    "has just happened, or is happening now."
)

# ---------------------------------------------------------------------------
# Legacy tool definitions — kept for plan_scene() backward compatibility
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


# ---------------------------------------------------------------------------
# Apollo 11 fallback scene
# ---------------------------------------------------------------------------

def _build_fallback_scene() -> ScenePlan:
    """Return a hardcoded Apollo 11 Mission Control scene used when Gemini fails twice."""
    return ScenePlan(
        scene_id=str(uuid.uuid4()),
        event_name="Apollo 11 Moon Landing",
        dramatic_moment="T-5 minutes before lunar module touchdown at Tranquility Base",
        room=Room(
            width=15.0,
            depth=10.0,
            height=4.0,
            fog=Fog(color="#0a0a14", near=8.0, far=20.0),
            ambient_color="#1a1a3e",
            architecture_style=ArchitectureStyle.space_age,
            time_of_day=TimeOfDay.afternoon,
            atmosphere=Atmosphere.tense,
            ceiling_material="acoustic_tile",
            has_windows=False,
            ambient_light_color="#cce0ff",
        ),
        lights=[
            Light(
                type=LightType.ambient,
                position=Position3D(x=0.0, y=3.0, z=0.0),
                color="#ffffff",
                intensity=0.3,
                decay=2.0,
                cast_shadow=False,
                source_label="fluorescent",
            ),
            Light(
                type=LightType.point,
                position=Position3D(x=0.0, y=3.5, z=-3.0),
                color="#4080ff",
                intensity=1.2,
                decay=2.0,
                cast_shadow=True,
                source_label="monitor glow",
            ),
            Light(
                type=LightType.point,
                position=Position3D(x=5.0, y=2.0, z=0.0),
                color="#ffcc44",
                intensity=0.8,
                decay=2.0,
                cast_shadow=True,
                source_label="overhead lamp",
            ),
        ],
        props=[
            Prop(
                id="console_main",
                shape=ShapeType.box,
                dimensions=[2.0, 0.9, 0.8],
                position=Position3D(x=0.0, y=0.45, z=-3.0),
                material=Material(color="#1a1a2e", roughness=0.8),
                interactable=True,
                interact_type="inspect",
                interact_text="Examine mission console",
                interact_content=(
                    "Banks of switches and dials glow green. "
                    "A voice crackles: 'Eagle, you are GO for powered descent.' "
                    "Every engineer in the room holds their breath."
                ),
                material_type=MaterialType.metal,
                scale=(5.0, 2.25, 2.0),
                rotation_y=0.0,
                emissive=True,
                emissive_color="#44ff88",
                emissive_intensity=0.6,
            ),
            Prop(
                id="headset_rack",
                shape=ShapeType.box,
                dimensions=[0.4, 0.3, 0.2],
                position=Position3D(x=3.0, y=0.9, z=-2.5),
                material=Material(color="#222222", roughness=0.6),
                material_type=MaterialType.metal,
                scale=(1.0, 0.75, 0.5),
                rotation_y=15.0,
            ),
            Prop(
                id="coffee_cup",
                shape=ShapeType.cylinder,
                dimensions=[0.05, 0.05, 0.1],
                position=Position3D(x=0.8, y=0.95, z=-2.8),
                material=Material(color="#8b4513", roughness=0.9),
                material_type=MaterialType.ceramic,
                scale=(0.125, 0.25, 0.125),
                rotation_y=0.0,
            ),
        ],
        characters=[
            Character(
                id="gene_kranz",
                name="Gene Kranz",
                role="NASA Flight Director leading the Apollo 11 lunar landing.",
                position=Position3D(x=0.0, y=0.0, z=-1.0),
                head_portrait_prompt=(
                    "Portrait of Gene Kranz, middle-aged American man, short brown hair, "
                    "iconic white vest, determined expression, white background, photorealistic."
                ),
                persona_summary=(
                    "You are Gene Kranz, NASA Flight Director for Apollo 11. "
                    "Speak with calm authority. "
                    "Reference mission data precisely. "
                    "Address crew by callsign. "
                    "You are focused and resolute."
                ),
                interact_text="Speak with Flight Director",
                primary=True,
                rotation_y=180.0,
                animation_hint=AnimationHint.talking_gesture,
                archetype=CharacterArchetype.formal_male,
            ),
            Character(
                id="capcom_duke",
                name="Charlie Duke",
                role="CAPCOM relaying communications between Mission Control and the crew.",
                position=Position3D(x=3.0, y=0.0, z=-1.5),
                head_portrait_prompt=(
                    "Portrait of Charlie Duke, young American man, short dark hair, "
                    "NASA headset, focused expression, white background, photorealistic."
                ),
                persona_summary=(
                    "You are Charlie Duke, CAPCOM for Apollo 11. "
                    "Relay messages to Armstrong and Aldrin with precision. "
                    "Keep responses brief and technical. "
                    "Remain calm under pressure."
                ),
                interact_text="Ask CAPCOM for status",
                primary=False,
                rotation_y=225.0,
                animation_hint=AnimationHint.working_console,
                archetype=CharacterArchetype.scientist,
            ),
        ],
        ambient_sounds=[SoundID.console_beeps, SoundID.radio_chatter],
        intro_narration=(
            "The year is 1969 and humanity is four minutes from touching the Moon. "
            "In this room, quiet engineers hold the fate of three astronauts in their hands."
        ),
        camera_start=CameraStart(x=0.0, y=1.6, z=2.0),
        skybox_hint=SkyboxHint.none,
    )


# ---------------------------------------------------------------------------
# Prompt builder — Part 2
# ---------------------------------------------------------------------------

def build_scene_prompt(user_input: str) -> str:
    """
    Construct a rich, constrained prompt from the user's raw input.

    Infers missing context (event name, date, location, role, dramatic moment)
    and explicitly instructs Gemini to include the most significant historical
    figure and to use only primitive shapes.
    """
    return (
        f"Generate a fully detailed 3D historical scene as a ScenePlan JSON object.\n\n"
        f"USER INPUT: {user_input}\n\n"
        "You MUST include ALL of the following in the scene plan:\n"
        "1. EVENT NAME AND DATE: The specific historical event and its date "
        "(or approximate era if the date is unknown). "
        "Infer from context if not stated "
        "(e.g. 'Apollo 11' -> Apollo 11 Moon Landing, 20 July 1969; "
        "'WW1 trench' -> Somme Offensive, October 1916).\n"
        "2. EXACT LOCATION: The precise physical location within the event "
        "(not just the broad event — e.g. not 'WW1' but "
        "'a dugout trench on the Somme, October 1916, the night before the offensive').\n"
        "3. USER ROLE: The user's role in the scene "
        "(observer, participant, or a specific job title).\n"
        "4. DRAMATIC MOMENT: A precise temporal description of what is happening "
        "(e.g. 'T-5 minutes before lunar touchdown', "
        "'the moment the armistice is signed', 'mid-battle at dawn'). "
        "Maximum 20 words.\n"
        "5. PRIMARY CHARACTER: Include the most historically significant person present "
        "who the user can interact with, marked as primary=true.\n"
        "6. PRIMITIVES ONLY: The scene must be fully self-contained and renderable "
        "using only box, sphere, and cylinder primitives.\n\n"
        "Return ONLY a valid JSON object conforming to the ScenePlan schema. "
        "No markdown fences, no prose outside the JSON."
    )


# ---------------------------------------------------------------------------
# ScenePlanner class
# ---------------------------------------------------------------------------


def _normalize_scene_plan(raw: dict) -> dict:
    """
    Silently fix the structural variants Gemini commonly produces before
    Pydantic validation runs.  Handles:

    - room with flat/misnamed size keys  → {width, depth, height}
    - fog.colour                         → fog.color
    - lights[].colour                    → lights[].color
    - props[].dimensions as a dict       → [width, height, depth] list
    - characters[].character_id          → characters[].id
    """
    data = dict(raw)

    # --- room ---
    room = data.get("room")
    if isinstance(room, dict):
        for size_key in ("size", "dimensions"):
            val = room.get(size_key)
            if isinstance(val, list) and len(val) == 3:
                room.setdefault("width", val[0])
                room.setdefault("depth", val[1])
                room.setdefault("height", val[2])
                del room[size_key]
        fog = room.get("fog")
        if isinstance(fog, dict) and "colour" in fog:
            fog["color"] = fog.pop("colour")

    # --- lights: colour → color ---
    for light in data.get("lights") or []:
        if isinstance(light, dict) and "colour" in light:
            light["color"] = light.pop("colour")

    # --- props: dimensions dict → [w, h, d] list ---
    for prop in data.get("props") or []:
        if not isinstance(prop, dict):
            continue
        dims = prop.get("dimensions")
        if isinstance(dims, dict):
            prop["dimensions"] = [
                float(dims.get("width", dims.get("x", dims.get("w", 1.0)))),
                float(dims.get("height", dims.get("y", dims.get("h", 1.0)))),
                float(dims.get("depth", dims.get("z", dims.get("d", 1.0)))),
            ]

    # --- characters: character_id → id ---
    for char in data.get("characters") or []:
        if isinstance(char, dict) and "id" not in char and "character_id" in char:
            char["id"] = char.pop("character_id")

    return data


def _humanize_errors(errors: list[str]) -> str:
    """
    Convert Pydantic error strings (e.g. "props.0.dimensions: Input should be a valid list")
    into model-legible, actionable instructions.  Each logical issue is emitted at most once.
    """
    # Map location fragment  →  actionable instruction
    _FIXES: list[tuple[str, str]] = [
        (
            "dimensions",
            "props[].dimensions must be a JSON array of 3 floats [width, height, depth], "
            "e.g. [1.5, 0.8, 0.75] — NOT an object",
        ),
        (
            "room.width",
            "room must have keys: width (float), depth (float), height (float), "
            "fog (object with color/near/far), ambient_color (hex) — "
            "do NOT use 'size', 'dimensions', or 'colour'",
        ),
        (
            "room",
            "room must be a JSON object with keys width, depth, height, fog, ambient_color",
        ),
        (
            "lights",
            "lights[].color must be a hex string (use 'color', NOT 'colour')",
        ),
        (
            "characters",
            "every character needs: id (snake_case, NOT 'character_id'), "
            "name, role, position, head_portrait_prompt, persona_summary, "
            "interact_text (required on every character), primary (bool)",
        ),
        (
            "camera_start.y",
            "camera_start.y must be exactly 1.6",
        ),
    ]

    seen: set[str] = set()
    messages: list[str] = []
    for err in errors:
        loc = err.split(":")[0]
        matched = False
        for fragment, fix in _FIXES:
            if fragment in loc and fix not in seen:
                messages.append(fix)
                seen.add(fix)
                matched = True
                break
        if not matched and err not in seen:
            messages.append(err)
            seen.add(err)
    return "; ".join(messages)


class ScenePlanner:
    def __init__(self, api_key: str, model: str = "gemini-3-flash-preview") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    # ------------------------------------------------------------------
    # Legacy interface — backward compatible, used by main.py /api/scene
    # ------------------------------------------------------------------

    def plan_scene(self, user_prompt: str, session_id: str) -> SceneState:
        """
        Send *user_prompt* to Gemini with function-calling tools and return a
        fully populated SceneState.
        """
        enriched_prompt = build_scene_prompt(user_prompt)
        state = SceneState(session_id=session_id)
        messages: list[genai_types.Content] = [
            genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=enriched_prompt)],
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
    # New interface — returns validated ScenePlan with retry & fallback
    # ------------------------------------------------------------------

    def generate_scene_plan(self, user_input: str) -> ScenePlan:
        """
        Generate a fully validated ScenePlan from *user_input*.

        1. Calls Gemini in JSON mode with the enriched prompt.
        2. Validates the response against ScenePlan.
        3. On failure, retries once with the validation errors appended.
        4. On second failure, returns the hardcoded Apollo 11 fallback scene.
        """
        prompt = build_scene_prompt(user_input)

        # First attempt
        raw = self._call_gemini_json(prompt)
        raw = _normalize_scene_plan(raw)
        errors = ScenePlan.validate_data(raw)

        if errors:
            error_summary = _humanize_errors(errors)
            logger.warning("ScenePlan validation failed on first attempt: %s", error_summary)
            retry_prompt = (
                prompt
                + f"\n\nYour previous response had these errors:\n{error_summary}\n"
                "Fix every error listed above and return a corrected ScenePlan JSON."
            )
            raw = self._call_gemini_json(retry_prompt)
            raw = _normalize_scene_plan(raw)
            errors = ScenePlan.validate_data(raw)

        if errors:
            logger.error(
                "ScenePlan validation failed after retry. Using Apollo 11 fallback. Errors: %s",
                errors,
            )
            return _build_fallback_scene()

        return ScenePlan.model_validate(raw)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_gemini_json(self, prompt: str) -> dict:
        """Send prompt to Gemini in JSON mode and return the parsed response dict."""
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=prompt)],
                )
            ],
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        try:
            return json.loads(response.text)
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.warning("Failed to parse Gemini JSON response: %s", exc)
            return {}

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
