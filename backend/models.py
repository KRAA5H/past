"""
Pydantic / SQLModel data models for Chronos.
"""
from __future__ import annotations

import json
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic import ValidationError
from sqlalchemy import String
from sqlmodel import Column, Field as SQLField, Session, SQLModel, create_engine, select


# ---------------------------------------------------------------------------
# Enums (legacy)
# ---------------------------------------------------------------------------


class NPCMood(str, Enum):
    neutral = "neutral"
    happy = "happy"
    sad = "sad"
    angry = "angry"
    fearful = "fearful"
    surprised = "surprised"


class NPCAction(str, Enum):
    idle = "idle"
    walk = "walk"
    run = "run"
    gesture = "gesture"
    sit = "sit"


# ---------------------------------------------------------------------------
# ScenePlan enums
# ---------------------------------------------------------------------------


class ShapeType(str, Enum):
    box = "box"
    sphere = "sphere"
    cylinder = "cylinder"


class InteractType(str, Enum):
    read = "read"
    inspect = "inspect"


class LightType(str, Enum):
    point = "point"
    spot = "spot"
    ambient = "ambient"


class SoundID(str, Enum):
    radio_chatter = "radio_chatter"
    console_beeps = "console_beeps"
    crowd_murmur = "crowd_murmur"
    wind = "wind"
    fire_crackling = "fire_crackling"
    church_bells = "church_bells"
    horse_hooves = "horse_hooves"
    typewriter_clatter = "typewriter_clatter"
    machinery_hum = "machinery_hum"
    silence = "silence"


# ---------------------------------------------------------------------------
# NPC
# ---------------------------------------------------------------------------


class NPCBase(BaseModel):
    npc_id: str = Field(..., description="Unique identifier for the NPC")
    name: str
    role: str = ""
    position: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    mood: NPCMood = NPCMood.neutral
    action: NPCAction = NPCAction.idle
    dialogue: str = ""


class NPC(SQLModel, table=True):
    """Persisted NPC row — list fields stored as JSON strings."""

    id: Optional[int] = SQLField(default=None, primary_key=True)
    session_id: str = SQLField(index=True)
    npc_id: str = SQLField(index=True)
    name: str = SQLField(default="")
    role: str = SQLField(default="")
    position_json: str = SQLField(default="[0.0, 0.0, 0.0]", sa_column=Column(String))
    rotation_json: str = SQLField(default="[0.0, 0.0, 0.0]", sa_column=Column(String))
    mood: str = SQLField(default=NPCMood.neutral)
    action: str = SQLField(default=NPCAction.idle)
    dialogue: str = SQLField(default="")

    @classmethod
    def from_base(cls, base: NPCBase, session_id: str) -> "NPC":
        return cls(
            session_id=session_id,
            npc_id=base.npc_id,
            name=base.name,
            role=base.role,
            position_json=json.dumps(base.position),
            rotation_json=json.dumps(base.rotation),
            mood=base.mood,
            action=base.action,
            dialogue=base.dialogue,
        )

    def to_base(self) -> NPCBase:
        return NPCBase(
            npc_id=self.npc_id,
            name=self.name,
            role=self.role,
            position=json.loads(self.position_json),
            rotation=json.loads(self.rotation_json),
            mood=NPCMood(self.mood),
            action=NPCAction(self.action),
            dialogue=self.dialogue,
        )


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------


class SceneObjectBase(BaseModel):
    object_id: str
    asset: str = Field(..., description="Asset filename, e.g. table.glb")
    position: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])


class SceneState(BaseModel):
    session_id: str
    description: str = ""
    npcs: list[NPCBase] = Field(default_factory=list)
    objects: list[SceneObjectBase] = Field(default_factory=list)
    ambient_sound: str = ""
    lighting: str = "day"


# ---------------------------------------------------------------------------
# WebSocket message schemas
# ---------------------------------------------------------------------------


class WSMessageType(str, Enum):
    # Client → Server
    audio_chunk = "audio_chunk"
    text_input = "text_input"
    scene_request = "scene_request"
    npc_interact = "npc_interact"
    npc_leave = "npc_leave"
    scene_exit = "scene_exit"

    # Server → Client
    scene_update = "scene_update"
    scene_plan_update = "scene_plan_update"
    audio_output = "audio_output"
    transcript = "transcript"
    error = "error"
    status = "status"
    cutscene_start = "cutscene_start"


class WSMessage(BaseModel):
    type: WSMessageType
    payload: Any = None


# ---------------------------------------------------------------------------
# Function-calling schemas (Gemini tool definitions)
# ---------------------------------------------------------------------------


class PlaceNPCArgs(BaseModel):
    npc_id: str
    name: str
    role: str = ""
    position: list[float] = [0.0, 0.0, 0.0]
    mood: NPCMood = NPCMood.neutral
    action: NPCAction = NPCAction.idle
    dialogue: str = ""


class PlaceObjectArgs(BaseModel):
    object_id: str
    asset: str
    position: list[float] = [0.0, 0.0, 0.0]
    rotation: list[float] = [0.0, 0.0, 0.0]
    scale: list[float] = [1.0, 1.0, 1.0]


class SetSceneDescriptionArgs(BaseModel):
    description: str
    lighting: str = "day"
    ambient_sound: str = ""


class ClearSceneArgs(BaseModel):
    pass


# ---------------------------------------------------------------------------
# ScenePlan sub-models
# ---------------------------------------------------------------------------


class Position3D(BaseModel):
    """World-space position. X/Z within the room (±10 m), Y from floor to ceiling."""

    x: float = Field(..., ge=-10.0, le=10.0)
    y: float = Field(..., ge=0.0, le=5.0)
    z: float = Field(..., ge=-10.0, le=10.0)


class Fog(BaseModel):
    color: str = Field(..., description="Hex colour, e.g. #0a0a14")
    near: float = Field(..., ge=0.0)
    far: float = Field(..., gt=0.0)

    @model_validator(mode="after")
    def far_gt_near(self) -> "Fog":
        if self.far <= self.near:
            raise ValueError("fog.far must be greater than fog.near")
        return self


class Room(BaseModel):
    width: float = Field(..., gt=0.0, le=20.0)
    depth: float = Field(..., gt=0.0, le=20.0)
    height: float = Field(..., gt=0.0, le=5.0)
    fog: Fog
    ambient_color: str = Field(..., description="Dominant ambient hex colour")


class Material(BaseModel):
    color: str = Field(default="#888888", description="Hex colour")
    roughness: float = Field(default=0.5, ge=0.0, le=1.0)
    emissive_color: Optional[str] = None


class Prop(BaseModel):
    id: str
    shape: ShapeType
    dimensions: list[float] = Field(..., min_length=3, max_length=3)
    position: Position3D
    material: Material = Field(default_factory=Material)
    interactable: bool = False
    interact_type: Optional[InteractType] = None
    interact_text: Optional[str] = None
    interact_content: Optional[str] = None

    @model_validator(mode="after")
    def check_interactable_fields(self) -> "Prop":
        if self.interactable:
            if self.interact_type is None:
                raise ValueError("interact_type is required when interactable=True")
            if not self.interact_text:
                raise ValueError("interact_text is required when interactable=True")
            if not self.interact_content:
                raise ValueError("interact_content is required when interactable=True")
        return self

    @field_validator("interact_text")
    @classmethod
    def interact_text_max_6_words(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v.split()) > 6:
            raise ValueError("interact_text must be at most 6 words")
        return v

    @field_validator("interact_content")
    @classmethod
    def interact_content_max_50_words(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v.split()) > 50:
            raise ValueError("interact_content must be at most 50 words")
        return v


class Character(BaseModel):
    id: str
    name: str
    role: str = Field(..., description="One-sentence role description")
    position: Position3D
    head_portrait_prompt: str = Field(..., description="Portrait prompt, max 30 words, white background")
    persona_summary: str = Field(..., description="Voice agent system prompt, max 60 words")
    interact_text: str = Field(..., description="UI hover label")
    primary: bool = False

    @field_validator("head_portrait_prompt")
    @classmethod
    def portrait_max_30_words(cls, v: str) -> str:
        if len(v.split()) > 30:
            raise ValueError("head_portrait_prompt must be at most 30 words")
        return v

    @field_validator("persona_summary")
    @classmethod
    def persona_max_60_words(cls, v: str) -> str:
        if len(v.split()) > 60:
            raise ValueError("persona_summary must be at most 60 words")
        return v


class Light(BaseModel):
    type: LightType
    position: Position3D
    color: str = Field(..., description="Hex colour")
    intensity: float = Field(..., ge=0.0, le=2.0)


class CameraStart(BaseModel):
    x: float = Field(..., ge=-10.0, le=10.0)
    y: float = Field(default=1.6)
    z: float = Field(..., ge=-10.0, le=10.0)

    @field_validator("y")
    @classmethod
    def y_must_be_eye_level(cls, v: float) -> float:
        if abs(v - 1.6) > 0.01:
            raise ValueError("camera_start.y must be 1.6 (eye level)")
        return v


class ScenePlan(BaseModel):
    """Top-level scene descriptor consumed directly by the R3F frontend."""

    scene_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_name: str
    dramatic_moment: str
    room: Room
    lights: list[Light] = Field(..., max_length=3)
    props: list[Prop] = Field(default_factory=list, max_length=6)
    characters: list[Character] = Field(..., max_length=3)
    ambient_sounds: list[SoundID] = Field(default_factory=list, max_length=2)
    intro_narration: str
    camera_start: CameraStart

    @field_validator("dramatic_moment")
    @classmethod
    def dramatic_moment_max_20_words(cls, v: str) -> str:
        if len(v.split()) > 20:
            raise ValueError("dramatic_moment must be at most 20 words")
        return v

    @field_validator("intro_narration")
    @classmethod
    def intro_narration_max_2_sentences(cls, v: str) -> str:
        # Count sentence-ending punctuation as a proxy for sentence count
        sentences = [s.strip() for s in v.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        if len(sentences) > 2:
            raise ValueError("intro_narration must be at most 2 sentences")
        return v

    @model_validator(mode="after")
    def check_exactly_one_primary(self) -> "ScenePlan":
        if self.characters:
            primary_count = sum(1 for c in self.characters if c.primary)
            if primary_count != 1:
                raise ValueError(
                    f"Exactly one character must have primary=True, found {primary_count}"
                )
        return self

    def is_valid(self) -> list[str]:
        """Re-validate this instance. Returns a list of human-readable error strings."""
        try:
            type(self).model_validate(self.model_dump(mode="json"))
            return []
        except ValidationError as e:
            errors: list[str] = []
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                errors.append(f"{loc}: {err['msg']}")
            return errors

    @classmethod
    def validate_data(cls, data: dict) -> list[str]:
        """Validate a raw dict and return a list of error strings (no exception raised)."""
        try:
            cls.model_validate(data)
            return []
        except ValidationError as e:
            errors: list[str] = []
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                errors.append(f"{loc}: {err['msg']}")
            return errors


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

DATABASE_URL = "sqlite:///./chronos.db"
engine = create_engine(DATABASE_URL, echo=False)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
