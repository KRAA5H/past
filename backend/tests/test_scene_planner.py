"""
test_scene_planner.py — unit tests for scene_planner.py.

All Gemini API calls are intercepted via the mock_genai_client fixture.
The make_fc_response helper from conftest builds synthetic function-call
responses so we can drive _apply_function_call from any angle.
"""
from __future__ import annotations

import logging
import pytest

from tests.conftest import make_fc_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_planner(mock_genai_client, api_key="test-key"):
    from scene_planner import ScenePlanner

    return ScenePlanner(api_key=api_key)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestScenePlannerInit:
    def test_creates_instance(self, mock_genai_client):
        from scene_planner import ScenePlanner

        planner = ScenePlanner(api_key="key")
        assert planner._model == "gemini-3-flash-preview"

    def test_custom_model(self, mock_genai_client):
        from scene_planner import ScenePlanner

        planner = ScenePlanner(api_key="key", model="gemini-1.5-pro")
        assert planner._model == "gemini-1.5-pro"


# ---------------------------------------------------------------------------
# plan_scene — set_scene_description
# ---------------------------------------------------------------------------


class TestPlanSceneDescription:
    def test_basic_description(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("set_scene_description", {"description": "Ancient Roman forum"}),
        )

        state = planner.plan_scene("Show me the Roman forum", "sess-1")

        assert state.session_id == "sess-1"
        assert state.description == "Ancient Roman forum"

    def test_description_with_lighting_and_sound(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            (
                "set_scene_description",
                {
                    "description": "Egyptian market at dusk",
                    "lighting": "dusk",
                    "ambient_sound": "market.mp3",
                },
            ),
        )

        state = planner.plan_scene("Egyptian market", "sess-2")

        assert state.description == "Egyptian market at dusk"
        assert state.lighting == "dusk"
        assert state.ambient_sound == "market.mp3"

    def test_description_default_lighting(self, mock_genai_client):
        """lighting should default to 'day' when not provided."""
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("set_scene_description", {"description": "A quiet temple"}),
        )

        state = planner.plan_scene("Temple scene", "sess-3")

        assert state.lighting == "day"
        assert state.ambient_sound == ""


# ---------------------------------------------------------------------------
# plan_scene — place_npc
# ---------------------------------------------------------------------------


class TestPlanSceneNPC:
    def test_single_npc(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("set_scene_description", {"description": "Senate house"}),
            ("place_npc", {"npc_id": "caesar", "name": "Julius Caesar"}),
        )

        state = planner.plan_scene("Caesar in the senate", "s1")

        assert len(state.npcs) == 1
        assert state.npcs[0].npc_id == "caesar"
        assert state.npcs[0].name == "Julius Caesar"

    def test_npc_defaults_applied(self, mock_genai_client):
        """NPCs placed with only required fields should have correct defaults."""
        from models import NPCMood, NPCAction

        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("place_npc", {"npc_id": "guard", "name": "Praetorian Guard"}),
        )

        state = planner.plan_scene("A guard", "s2")
        npc = state.npcs[0]

        assert npc.mood == NPCMood.neutral
        assert npc.action == NPCAction.idle
        assert npc.dialogue == ""
        assert npc.position == [0.0, 0.0, 0.0]

    def test_npc_full_args(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            (
                "place_npc",
                {
                    "npc_id": "cleopatra",
                    "name": "Cleopatra VII",
                    "role": "Pharaoh",
                    "position": [2.0, 0.0, -1.0],
                    "mood": "happy",
                    "action": "gesture",
                    "dialogue": "Welcome to Egypt.",
                },
            ),
        )

        state = planner.plan_scene("Cleopatra's throne room", "s3")
        npc = state.npcs[0]

        assert npc.role == "Pharaoh"
        assert npc.position == [2.0, 0.0, -1.0]
        assert npc.mood == "happy"
        assert npc.dialogue == "Welcome to Egypt."

    def test_multiple_npcs(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("place_npc", {"npc_id": "n1", "name": "Soldier"}),
            ("place_npc", {"npc_id": "n2", "name": "Merchant"}),
            ("place_npc", {"npc_id": "n3", "name": "Senator"}),
        )

        state = planner.plan_scene("Busy square", "s4")

        assert len(state.npcs) == 3
        ids = {n.npc_id for n in state.npcs}
        assert ids == {"n1", "n2", "n3"}

    def test_npc_upsert_same_id(self, mock_genai_client):
        """A second place_npc with the same npc_id should update, not append."""
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("place_npc", {"npc_id": "hercules", "name": "Hercules", "mood": "neutral"}),
            ("place_npc", {"npc_id": "hercules", "name": "Hercules", "mood": "angry"}),
        )

        state = planner.plan_scene("Hercules enraged", "s5")

        assert len(state.npcs) == 1
        assert state.npcs[0].mood == "angry"


# ---------------------------------------------------------------------------
# plan_scene — place_object
# ---------------------------------------------------------------------------


class TestPlanSceneObject:
    def test_single_object(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("place_object", {"object_id": "column1", "asset": "column.glb"}),
        )

        state = planner.plan_scene("A column", "s1")

        assert len(state.objects) == 1
        assert state.objects[0].asset == "column.glb"

    def test_object_defaults(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("place_object", {"object_id": "altar1", "asset": "altar.glb"}),
        )

        state = planner.plan_scene("An altar", "s2")
        obj = state.objects[0]

        assert obj.position == [0.0, 0.0, 0.0]
        assert obj.rotation == [0.0, 0.0, 0.0]
        assert obj.scale == [1.0, 1.0, 1.0]

    def test_object_full_args(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            (
                "place_object",
                {
                    "object_id": "cart1",
                    "asset": "cart.glb",
                    "position": [3.0, 0.0, 2.0],
                    "rotation": [0.0, 1.57, 0.0],
                    "scale": [1.5, 1.5, 1.5],
                },
            ),
        )

        state = planner.plan_scene("A cart", "s3")
        obj = state.objects[0]

        assert obj.position == [3.0, 0.0, 2.0]
        assert obj.scale == [1.5, 1.5, 1.5]

    def test_object_upsert_same_id(self, mock_genai_client):
        """A second place_object with the same object_id updates, not appends."""
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("place_object", {"object_id": "o1", "asset": "table.glb", "scale": [1, 1, 1]}),
            ("place_object", {"object_id": "o1", "asset": "table.glb", "scale": [2, 2, 2]}),
        )

        state = planner.plan_scene("Big table", "s4")

        assert len(state.objects) == 1
        assert state.objects[0].scale == [2, 2, 2]

    def test_multiple_objects(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("place_object", {"object_id": "o1", "asset": "bench.glb"}),
            ("place_object", {"object_id": "o2", "asset": "fountain.glb"}),
        )

        state = planner.plan_scene("A square", "s5")

        assert len(state.objects) == 2


# ---------------------------------------------------------------------------
# plan_scene — clear_scene
# ---------------------------------------------------------------------------


class TestPlanSceneClear:
    def test_clear_removes_npcs_and_objects(self, mock_genai_client):
        """clear_scene should wipe both npcs and objects lists."""
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("place_npc", {"npc_id": "n1", "name": "Guard"}),
            ("place_object", {"object_id": "o1", "asset": "wall.glb"}),
            ("clear_scene", {}),
        )

        state = planner.plan_scene("Empty the scene", "s1")

        assert state.npcs == []
        assert state.objects == []

    def test_clear_then_place(self, mock_genai_client):
        """Objects placed after clear_scene should still appear."""
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("place_npc", {"npc_id": "old", "name": "Old NPC"}),
            ("clear_scene", {}),
            ("place_npc", {"npc_id": "new", "name": "New NPC"}),
        )

        state = planner.plan_scene("Reset and rebuild", "s2")

        assert len(state.npcs) == 1
        assert state.npcs[0].npc_id == "new"


# ---------------------------------------------------------------------------
# plan_scene — unknown function name
# ---------------------------------------------------------------------------


class TestPlanSceneUnknownFunction:
    def test_unknown_name_logs_warning(self, mock_genai_client, caplog):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("unknown_function", {"foo": "bar"}),
        )

        with caplog.at_level(logging.WARNING, logger="scene_planner"):
            state = planner.plan_scene("Anything", "s1")

        assert any("unknown_function" in msg.lower() or "unknown" in msg.lower()
                   for msg in caplog.messages)

    def test_unknown_name_does_not_crash(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            ("set_scene_description", {"description": "Ok"}),
            ("teleport_npc", {"npc_id": "n1"}),  # unknown
        )

        state = planner.plan_scene("Mixed calls", "s1")

        assert state.description == "Ok"  # valid call still applied


# ---------------------------------------------------------------------------
# plan_scene — empty response (no candidates / no parts)
# ---------------------------------------------------------------------------


class TestPlanSceneEmptyResponse:
    def test_no_candidates(self, mock_genai_client):
        from unittest.mock import MagicMock

        planner = make_planner(mock_genai_client)
        resp = MagicMock()
        resp.candidates = []
        mock_genai_client.models.generate_content.return_value = resp

        state = planner.plan_scene("Anything", "s1")

        assert state.npcs == []
        assert state.objects == []
        assert state.description == ""

    def test_none_candidates(self, mock_genai_client):
        from unittest.mock import MagicMock

        planner = make_planner(mock_genai_client)
        resp = MagicMock()
        resp.candidates = None
        mock_genai_client.models.generate_content.return_value = resp

        state = planner.plan_scene("Anything", "s1")

        assert state.session_id == "s1"

    def test_no_function_calls_in_parts(self, mock_genai_client):
        from unittest.mock import MagicMock

        planner = make_planner(mock_genai_client)
        part = MagicMock()
        part.function_call = None
        candidate = MagicMock()
        candidate.content.parts = [part]
        resp = MagicMock()
        resp.candidates = [candidate]
        mock_genai_client.models.generate_content.return_value = resp

        state = planner.plan_scene("No calls", "s1")

        assert state.npcs == []


# ---------------------------------------------------------------------------
# plan_scene — integration: full scene with all call types
# ---------------------------------------------------------------------------


class TestPlanSceneFullIntegration:
    def test_rome_scene(self, mock_genai_client):
        planner = make_planner(mock_genai_client)
        mock_genai_client.models.generate_content.return_value = make_fc_response(
            (
                "set_scene_description",
                {
                    "description": "The Roman Forum, 44 BC",
                    "lighting": "day",
                    "ambient_sound": "crowd.mp3",
                },
            ),
            (
                "place_npc",
                {
                    "npc_id": "caesar",
                    "name": "Julius Caesar",
                    "role": "Dictator",
                    "position": [0.0, 0.0, 0.0],
                    "mood": "neutral",
                    "action": "idle",
                    "dialogue": "The die is cast.",
                },
            ),
            (
                "place_npc",
                {
                    "npc_id": "brutus",
                    "name": "Marcus Brutus",
                    "role": "Senator",
                    "position": [2.0, 0.0, 1.0],
                    "mood": "fearful",
                    "action": "walk",
                    "dialogue": "Et tu?",
                },
            ),
            (
                "place_object",
                {
                    "object_id": "senate_steps",
                    "asset": "stone_steps.glb",
                    "position": [0.0, 0.0, -5.0],
                    "scale": [3.0, 1.0, 3.0],
                },
            ),
        )

        state = planner.plan_scene("Show the assassination of Caesar", "rome-1")

        assert state.description == "The Roman Forum, 44 BC"
        assert state.lighting == "day"
        assert state.ambient_sound == "crowd.mp3"
        assert len(state.npcs) == 2
        assert len(state.objects) == 1

        npc_ids = [n.npc_id for n in state.npcs]
        assert "caesar" in npc_ids
        assert "brutus" in npc_ids
        assert state.objects[0].object_id == "senate_steps"
