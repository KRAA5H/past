"""
test_models.py — unit tests for models.py.

Covers enums, Pydantic models, NPC ORM roundtrip, DB setup, and
function-calling argument schemas.
"""
from __future__ import annotations

import json
import pytest
from sqlmodel import Session, select


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestNPCMood:
    def test_all_values(self):
        from models import NPCMood

        assert set(NPCMood) == {
            NPCMood.neutral,
            NPCMood.happy,
            NPCMood.sad,
            NPCMood.angry,
            NPCMood.fearful,
            NPCMood.surprised,
        }

    def test_is_string_enum(self):
        from models import NPCMood

        assert NPCMood.neutral == "neutral"
        assert NPCMood.angry == "angry"


class TestNPCAction:
    def test_all_values(self):
        from models import NPCAction

        assert set(NPCAction) == {
            NPCAction.idle,
            NPCAction.walk,
            NPCAction.run,
            NPCAction.gesture,
            NPCAction.sit,
        }

    def test_is_string_enum(self):
        from models import NPCAction

        assert NPCAction.walk == "walk"


class TestWSMessageType:
    def test_client_message_types(self):
        from models import WSMessageType

        assert WSMessageType.audio_chunk == "audio_chunk"
        assert WSMessageType.text_input == "text_input"
        assert WSMessageType.scene_request == "scene_request"

    def test_interaction_flow_client_types(self):
        """Client-to-server types introduced for the full interaction flow."""
        from models import WSMessageType

        assert WSMessageType.npc_interact == "npc_interact"
        assert WSMessageType.npc_leave == "npc_leave"
        assert WSMessageType.scene_exit == "scene_exit"

    def test_server_message_types(self):
        from models import WSMessageType

        assert WSMessageType.scene_update == "scene_update"
        assert WSMessageType.audio_output == "audio_output"
        assert WSMessageType.transcript == "transcript"
        assert WSMessageType.error == "error"
        assert WSMessageType.status == "status"

    def test_interaction_flow_server_types(self):
        """Server-to-client types introduced for the full interaction flow."""
        from models import WSMessageType

        assert WSMessageType.scene_plan_update == "scene_plan_update"
        assert WSMessageType.cutscene_start == "cutscene_start"

    def test_npc_interact_message_roundtrip(self):
        """npc_interact message can be created and validated."""
        from models import WSMessage, WSMessageType

        msg = WSMessage(type=WSMessageType.npc_interact, payload={"npc_id": "gene_kranz"})
        data = msg.model_dump()
        restored = WSMessage.model_validate(data)
        assert restored.type == WSMessageType.npc_interact
        assert restored.payload["npc_id"] == "gene_kranz"

    def test_cutscene_start_message_roundtrip(self):
        """cutscene_start message carries intro_narration and character_name."""
        from models import WSMessage, WSMessageType

        msg = WSMessage(
            type=WSMessageType.cutscene_start,
            payload={
                "intro_narration": "Humanity stands at the edge of history.",
                "character_name": "Gene Kranz",
            },
        )
        data = msg.model_dump()
        restored = WSMessage.model_validate(data)
        assert restored.type == WSMessageType.cutscene_start
        assert "intro_narration" in restored.payload

    def test_scene_plan_update_message(self):
        """scene_plan_update carries the serialised ScenePlan."""
        from models import WSMessage, WSMessageType

        msg = WSMessage(
            type=WSMessageType.scene_plan_update,
            payload={"event_name": "Apollo 11"},
        )
        assert msg.type == WSMessageType.scene_plan_update

    def test_scene_exit_message(self):
        """scene_exit message has no required payload."""
        from models import WSMessage, WSMessageType

        msg = WSMessage(type=WSMessageType.scene_exit)
        assert msg.type == WSMessageType.scene_exit
        assert msg.payload is None


# ---------------------------------------------------------------------------
# NPCBase
# ---------------------------------------------------------------------------


class TestNPCBase:
    def test_required_fields(self):
        from models import NPCBase

        npc = NPCBase(npc_id="n1", name="Marcus")
        assert npc.npc_id == "n1"
        assert npc.name == "Marcus"

    def test_defaults(self):
        from models import NPCBase, NPCMood, NPCAction

        npc = NPCBase(npc_id="n1", name="Marcus")
        assert npc.role == ""
        assert npc.position == [0.0, 0.0, 0.0]
        assert npc.rotation == [0.0, 0.0, 0.0]
        assert npc.mood == NPCMood.neutral
        assert npc.action == NPCAction.idle
        assert npc.dialogue == ""

    def test_custom_fields(self):
        from models import NPCBase, NPCMood, NPCAction

        npc = NPCBase(
            npc_id="caesar",
            name="Julius Caesar",
            role="General",
            position=[1.0, 0.0, -2.5],
            rotation=[0.0, 1.57, 0.0],
            mood=NPCMood.happy,
            action=NPCAction.gesture,
            dialogue="Veni, vidi, vici.",
        )
        assert npc.role == "General"
        assert npc.position == [1.0, 0.0, -2.5]
        assert npc.mood == NPCMood.happy
        assert npc.action == NPCAction.gesture
        assert npc.dialogue == "Veni, vidi, vici."

    def test_position_list_is_independent(self):
        """Each NPCBase instance gets its own position list (not shared)."""
        from models import NPCBase

        a = NPCBase(npc_id="a", name="A")
        b = NPCBase(npc_id="b", name="B")
        a.position[0] = 99.0
        assert b.position[0] == 0.0

    def test_serialization(self):
        from models import NPCBase

        npc = NPCBase(npc_id="n1", name="Marcus")
        data = npc.model_dump()
        assert data["npc_id"] == "n1"
        assert data["name"] == "Marcus"
        assert "mood" in data and "action" in data

    def test_invalid_mood_raises(self):
        from models import NPCBase
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            NPCBase(npc_id="n1", name="X", mood="floating")

    def test_invalid_action_raises(self):
        from models import NPCBase
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            NPCBase(npc_id="n1", name="X", action="flying")


# ---------------------------------------------------------------------------
# SceneObjectBase
# ---------------------------------------------------------------------------


class TestSceneObjectBase:
    def test_required_fields(self):
        from models import SceneObjectBase

        obj = SceneObjectBase(object_id="table1", asset="table.glb")
        assert obj.object_id == "table1"
        assert obj.asset == "table.glb"

    def test_defaults(self):
        from models import SceneObjectBase

        obj = SceneObjectBase(object_id="o1", asset="pillar.glb")
        assert obj.position == [0.0, 0.0, 0.0]
        assert obj.rotation == [0.0, 0.0, 0.0]
        assert obj.scale == [1.0, 1.0, 1.0]

    def test_custom_fields(self):
        from models import SceneObjectBase

        obj = SceneObjectBase(
            object_id="cart1",
            asset="cart.glb",
            position=[3.0, 0.0, 1.0],
            rotation=[0.0, 0.78, 0.0],
            scale=[2.0, 2.0, 2.0],
        )
        assert obj.position == [3.0, 0.0, 1.0]
        assert obj.scale == [2.0, 2.0, 2.0]


# ---------------------------------------------------------------------------
# SceneState
# ---------------------------------------------------------------------------


class TestSceneState:
    def test_required_field(self):
        from models import SceneState

        state = SceneState(session_id="sess-abc")
        assert state.session_id == "sess-abc"

    def test_defaults(self):
        from models import SceneState

        state = SceneState(session_id="s1")
        assert state.description == ""
        assert state.npcs == []
        assert state.objects == []
        assert state.ambient_sound == ""
        assert state.lighting == "day"

    def test_npc_list_is_independent(self):
        from models import SceneState, NPCBase

        a = SceneState(session_id="a")
        b = SceneState(session_id="b")
        a.npcs.append(NPCBase(npc_id="x", name="X"))
        assert b.npcs == []

    def test_full_serialization(self):
        from models import SceneState, NPCBase, SceneObjectBase

        state = SceneState(
            session_id="sess-1",
            description="Roman forum",
            lighting="day",
            ambient_sound="market.mp3",
            npcs=[NPCBase(npc_id="n1", name="Cicero")],
            objects=[SceneObjectBase(object_id="o1", asset="column.glb")],
        )
        data = state.model_dump()
        assert data["session_id"] == "sess-1"
        assert len(data["npcs"]) == 1
        assert data["npcs"][0]["name"] == "Cicero"
        assert len(data["objects"]) == 1


# ---------------------------------------------------------------------------
# WSMessage
# ---------------------------------------------------------------------------


class TestWSMessage:
    def test_text_input_message(self):
        from models import WSMessage, WSMessageType

        msg = WSMessage(type=WSMessageType.text_input, payload={"text": "hello"})
        assert msg.type == WSMessageType.text_input
        assert msg.payload["text"] == "hello"

    def test_scene_update_message(self):
        from models import WSMessage, WSMessageType

        msg = WSMessage(type=WSMessageType.scene_update, payload=None)
        assert msg.payload is None

    def test_parse_from_dict(self):
        from models import WSMessage, WSMessageType

        raw = {"type": "transcript", "payload": {"text": "Salve!"}}
        msg = WSMessage.model_validate(raw)
        assert msg.type == WSMessageType.transcript

    def test_invalid_type_raises(self):
        from models import WSMessage
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            WSMessage(type="not_a_type")


# ---------------------------------------------------------------------------
# NPC ORM — from_base / to_base roundtrip
# ---------------------------------------------------------------------------


class TestNPCORM:
    def test_from_base_fields(self):
        from models import NPC, NPCBase, NPCMood, NPCAction

        base = NPCBase(
            npc_id="socrates",
            name="Socrates",
            role="Philosopher",
            position=[0.5, 0.0, 1.0],
            rotation=[0.0, 0.3, 0.0],
            mood=NPCMood.surprised,
            action=NPCAction.gesture,
            dialogue="Know thyself.",
        )
        orm = NPC.from_base(base, session_id="sess-42")

        assert orm.session_id == "sess-42"
        assert orm.npc_id == "socrates"
        assert orm.name == "Socrates"
        assert orm.role == "Philosopher"
        assert json.loads(orm.position_json) == [0.5, 0.0, 1.0]
        assert json.loads(orm.rotation_json) == [0.0, 0.3, 0.0]
        assert orm.mood == "surprised"
        assert orm.action == "gesture"
        assert orm.dialogue == "Know thyself."

    def test_to_base_roundtrip(self):
        from models import NPC, NPCBase, NPCMood, NPCAction

        base = NPCBase(
            npc_id="plato",
            name="Plato",
            role="Student",
            position=[1.0, 0.0, -1.0],
            mood=NPCMood.sad,
            action=NPCAction.sit,
            dialogue="The unexamined life.",
        )
        orm = NPC.from_base(base, session_id="s99")
        recovered = orm.to_base()

        assert recovered.npc_id == base.npc_id
        assert recovered.name == base.name
        assert recovered.role == base.role
        assert recovered.position == base.position
        assert recovered.rotation == base.rotation
        assert recovered.mood == base.mood
        assert recovered.action == base.action
        assert recovered.dialogue == base.dialogue

    def test_default_position_json(self):
        from models import NPCBase, NPC

        orm = NPC.from_base(NPCBase(npc_id="x", name="X"), session_id="s")
        assert json.loads(orm.position_json) == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


class TestDatabase:
    def test_create_and_query(self, mem_engine, db_session):
        from models import NPC, NPCBase

        npc = NPC.from_base(
            NPCBase(npc_id="augustus", name="Augustus"), session_id="db-test"
        )
        db_session.add(npc)
        db_session.commit()

        result = db_session.exec(select(NPC).where(NPC.session_id == "db-test")).all()
        assert len(result) == 1
        assert result[0].name == "Augustus"

    def test_multiple_sessions_isolated(self, mem_engine, db_session):
        from models import NPC, NPCBase

        for sess_id, name in [("s1", "Caesar"), ("s2", "Pompey")]:
            db_session.add(
                NPC.from_base(NPCBase(npc_id=f"npc_{sess_id}", name=name), session_id=sess_id)
            )
        db_session.commit()

        s1_npcs = db_session.exec(select(NPC).where(NPC.session_id == "s1")).all()
        s2_npcs = db_session.exec(select(NPC).where(NPC.session_id == "s2")).all()
        assert len(s1_npcs) == 1 and s1_npcs[0].name == "Caesar"
        assert len(s2_npcs) == 1 and s2_npcs[0].name == "Pompey"

    def test_get_session_yields(self, mem_engine):
        from models import get_session

        gen = get_session()
        sess = next(gen)
        assert sess is not None
        try:
            next(gen)
        except StopIteration:
            pass


# ---------------------------------------------------------------------------
# Function-calling argument schemas
# ---------------------------------------------------------------------------


class TestFunctionCallSchemas:
    def test_place_npc_args_required(self):
        from models import PlaceNPCArgs

        args = PlaceNPCArgs(npc_id="n1", name="Nero")
        assert args.npc_id == "n1"
        assert args.name == "Nero"
        assert args.role == ""

    def test_place_npc_args_full(self):
        from models import PlaceNPCArgs, NPCMood, NPCAction

        args = PlaceNPCArgs(
            npc_id="nero",
            name="Nero",
            role="Emperor",
            position=[0.0, 0.0, 0.0],
            mood=NPCMood.angry,
            action=NPCAction.walk,
            dialogue="I am emperor!",
        )
        assert args.mood == NPCMood.angry
        assert args.action == NPCAction.walk

    def test_place_object_args_required(self):
        from models import PlaceObjectArgs

        args = PlaceObjectArgs(object_id="o1", asset="arch.glb")
        assert args.asset == "arch.glb"
        assert args.scale == [1.0, 1.0, 1.0]

    def test_set_scene_description_required(self):
        from models import SetSceneDescriptionArgs
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            SetSceneDescriptionArgs()  # description is required

    def test_set_scene_description_defaults(self):
        from models import SetSceneDescriptionArgs

        args = SetSceneDescriptionArgs(description="Ancient Rome")
        assert args.lighting == "day"
        assert args.ambient_sound == ""

    def test_clear_scene_args_no_fields(self):
        from models import ClearSceneArgs

        args = ClearSceneArgs()
        assert args.model_dump() == {}
