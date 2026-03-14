"""
Pydantic / SQLModel data models for Chronos.
"""
from __future__ import annotations

import json
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import String
from sqlmodel import Column, Field as SQLField, Session, SQLModel, create_engine, select


# ---------------------------------------------------------------------------
# Enums
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

    # Server → Client
    scene_update = "scene_update"
    audio_output = "audio_output"
    transcript = "transcript"
    error = "error"
    status = "status"


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
# SQLite helpers
# ---------------------------------------------------------------------------

DATABASE_URL = "sqlite:///./chronos.db"
engine = create_engine(DATABASE_URL, echo=False)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
