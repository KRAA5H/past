"""
test_scene_plan.py — unit tests for the new ScenePlan Pydantic models
and the generate_scene_plan() pipeline in ScenePlanner.
"""
from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_scene_dict(**overrides) -> dict:
    """Return a minimal valid ScenePlan dict, with optional field overrides."""
    base = {
        "event_name": "Apollo 11 Moon Landing",
        "dramatic_moment": "T-5 minutes before lunar touchdown",
        "room": {
            "width": 15.0,
            "depth": 10.0,
            "height": 4.0,
            "fog": {"color": "#0a0a14", "near": 5.0, "far": 20.0},
            "ambient_color": "#1a1a3e",
        },
        "lights": [
            {
                "type": "ambient",
                "position": {"x": 0.0, "y": 3.0, "z": 0.0},
                "color": "#ffffff",
                "intensity": 0.5,
            }
        ],
        "props": [],
        "characters": [
            {
                "id": "kranz",
                "name": "Gene Kranz",
                "role": "NASA Flight Director overseeing the Apollo 11 landing.",
                "position": {"x": 0.0, "y": 0.0, "z": -1.0},
                "head_portrait_prompt": "Portrait of Gene Kranz, white vest, determined, white background.",
                "persona_summary": "You are Gene Kranz. Speak with authority and precision.",
                "interact_text": "Speak with Gene Kranz",
                "primary": True,
            }
        ],
        "ambient_sounds": ["console_beeps"],
        "intro_narration": "Humanity stands at the edge of history. Three men approach the Moon.",
        "camera_start": {"x": 0.0, "y": 1.6, "z": 2.0},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ShapeType / InteractType / LightType / SoundID enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_shape_type_values(self):
        from models import ShapeType

        assert set(ShapeType) == {ShapeType.box, ShapeType.sphere, ShapeType.cylinder}

    def test_shape_type_is_string(self):
        from models import ShapeType

        assert ShapeType.box == "box"

    def test_interact_type_values(self):
        from models import InteractType

        assert set(InteractType) == {InteractType.read, InteractType.inspect}

    def test_light_type_values(self):
        from models import LightType

        assert set(LightType) == {LightType.point, LightType.spot, LightType.ambient}

    def test_sound_id_values(self):
        from models import SoundID

        expected = {
            "radio_chatter", "console_beeps", "crowd_murmur", "wind",
            "fire_crackling", "church_bells", "horse_hooves",
            "typewriter_clatter", "machinery_hum", "silence",
        }
        assert {s.value for s in SoundID} == expected


# ---------------------------------------------------------------------------
# Position3D
# ---------------------------------------------------------------------------


class TestPosition3D:
    def test_valid(self):
        from models import Position3D

        p = Position3D(x=0.0, y=0.0, z=0.0)
        assert p.x == 0.0

    def test_x_out_of_bounds(self):
        from models import Position3D

        with pytest.raises(ValidationError):
            Position3D(x=11.0, y=0.0, z=0.0)

    def test_x_negative_out_of_bounds(self):
        from models import Position3D

        with pytest.raises(ValidationError):
            Position3D(x=-11.0, y=0.0, z=0.0)

    def test_y_below_floor(self):
        from models import Position3D

        with pytest.raises(ValidationError):
            Position3D(x=0.0, y=-0.1, z=0.0)

    def test_y_above_ceiling(self):
        from models import Position3D

        with pytest.raises(ValidationError):
            Position3D(x=0.0, y=5.1, z=0.0)

    def test_z_out_of_bounds(self):
        from models import Position3D

        with pytest.raises(ValidationError):
            Position3D(x=0.0, y=0.0, z=10.1)

    def test_boundary_values_accepted(self):
        from models import Position3D

        p = Position3D(x=-10.0, y=0.0, z=10.0)
        assert p.x == -10.0
        assert p.z == 10.0


# ---------------------------------------------------------------------------
# Fog
# ---------------------------------------------------------------------------


class TestFog:
    def test_valid(self):
        from models import Fog

        f = Fog(color="#ffffff", near=5.0, far=20.0)
        assert f.near == 5.0

    def test_far_must_exceed_near(self):
        from models import Fog

        with pytest.raises(ValidationError):
            Fog(color="#ffffff", near=20.0, far=10.0)

    def test_far_equal_to_near_rejected(self):
        from models import Fog

        with pytest.raises(ValidationError):
            Fog(color="#ffffff", near=10.0, far=10.0)


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------


class TestRoom:
    def test_valid(self):
        from models import Fog, Room

        r = Room(
            width=15.0, depth=10.0, height=4.0,
            fog=Fog(color="#000000", near=5.0, far=20.0),
            ambient_color="#1a1a3e",
        )
        assert r.width == 15.0

    def test_width_exceeds_max(self):
        from models import Fog, Room

        with pytest.raises(ValidationError):
            Room(
                width=21.0, depth=10.0, height=4.0,
                fog=Fog(color="#000000", near=5.0, far=20.0),
                ambient_color="#000000",
            )

    def test_height_exceeds_max(self):
        from models import Fog, Room

        with pytest.raises(ValidationError):
            Room(
                width=10.0, depth=10.0, height=6.0,
                fog=Fog(color="#000000", near=5.0, far=20.0),
                ambient_color="#000000",
            )

    def test_room_new_field_defaults(self):
        from models import ArchitectureStyle, Atmosphere, Fog, Room, TimeOfDay

        r = Room(
            width=15.0, depth=10.0, height=4.0,
            fog=Fog(color="#000000", near=5.0, far=20.0),
            ambient_color="#1a1a3e",
        )
        assert r.architecture_style == ArchitectureStyle.contemporary
        assert r.time_of_day == TimeOfDay.unknown
        assert r.atmosphere == Atmosphere.mundane
        assert r.ceiling_material == "plaster"
        assert r.has_windows is False
        assert r.ambient_light_color == "#ffffff"

    def test_room_new_fields_custom(self):
        from models import ArchitectureStyle, Atmosphere, Fog, Room, TimeOfDay

        r = Room(
            width=15.0, depth=10.0, height=4.0,
            fog=Fog(color="#0a0a14", near=8.0, far=20.0),
            ambient_color="#1a1a3e",
            architecture_style=ArchitectureStyle.space_age,
            time_of_day=TimeOfDay.afternoon,
            atmosphere=Atmosphere.tense,
            ceiling_material="acoustic_tile",
            has_windows=False,
            ambient_light_color="#cce0ff",
        )
        assert r.architecture_style == ArchitectureStyle.space_age
        assert r.time_of_day == TimeOfDay.afternoon
        assert r.atmosphere == Atmosphere.tense
        assert r.ceiling_material == "acoustic_tile"
        assert r.ambient_light_color == "#cce0ff"


# ---------------------------------------------------------------------------
# Prop
# ---------------------------------------------------------------------------


class TestProp:
    def test_valid_non_interactable(self):
        from models import Position3D, Prop, ShapeType

        p = Prop(
            id="box1",
            shape=ShapeType.box,
            dimensions=[1.0, 1.0, 1.0],
            position=Position3D(x=0.0, y=0.0, z=0.0),
        )
        assert p.shape == ShapeType.box

    def test_invalid_shape(self):
        from models import Position3D, Prop

        with pytest.raises(ValidationError):
            Prop(
                id="bad",
                shape="pyramid",
                dimensions=[1.0, 1.0, 1.0],
                position=Position3D(x=0.0, y=0.0, z=0.0),
            )

    def test_interactable_requires_all_fields(self):
        from models import Position3D, Prop, ShapeType

        with pytest.raises(ValidationError):
            Prop(
                id="p1",
                shape=ShapeType.box,
                dimensions=[1.0, 1.0, 1.0],
                position=Position3D(x=0.0, y=0.0, z=0.0),
                interactable=True,
                # missing interact_type, interact_text, interact_content
            )

    def test_interactable_valid(self):
        from models import InteractType, Position3D, Prop, ShapeType

        p = Prop(
            id="p1",
            shape=ShapeType.box,
            dimensions=[1.0, 1.0, 1.0],
            position=Position3D(x=0.0, y=0.0, z=0.0),
            interactable=True,
            interact_type=InteractType.read,
            interact_text="Read the letter",
            interact_content="A letter sealed with wax. It reads: the plan is set for midnight.",
        )
        assert p.interact_type == InteractType.read

    def test_interact_text_too_many_words(self):
        from models import InteractType, Position3D, Prop, ShapeType

        # "This text has way too many words for the limit" = 10 words (limit is 6)
        with pytest.raises(ValidationError):
            Prop(
                id="p1",
                shape=ShapeType.box,
                dimensions=[1.0, 1.0, 1.0],
                position=Position3D(x=0.0, y=0.0, z=0.0),
                interactable=True,
                interact_type=InteractType.read,
                interact_text="This text has way too many words for the limit",
                interact_content="Content here.",
            )

    def test_interact_content_too_many_words(self):
        from models import InteractType, Position3D, Prop, ShapeType

        long_content = " ".join(["word"] * 51)
        with pytest.raises(ValidationError):
            Prop(
                id="p1",
                shape=ShapeType.box,
                dimensions=[1.0, 1.0, 1.0],
                position=Position3D(x=0.0, y=0.0, z=0.0),
                interactable=True,
                interact_type=InteractType.inspect,
                interact_text="Inspect the box",
                interact_content=long_content,
            )

    def test_prop_new_field_defaults(self):
        from models import MaterialType, Position3D, Prop, ShapeType

        p = Prop(
            id="box1",
            shape=ShapeType.box,
            dimensions=[1.0, 1.0, 1.0],
            position=Position3D(x=0.0, y=0.0, z=0.0),
        )
        assert p.material_type == MaterialType.wood
        assert p.scale == (1.0, 1.0, 1.0)
        assert p.rotation_y == 0.0
        assert p.emissive is False
        assert p.emissive_color == "#ffffff"
        assert p.emissive_intensity == 1.0

    def test_prop_new_fields_custom(self):
        from models import MaterialType, Position3D, Prop, ShapeType

        p = Prop(
            id="lamp1",
            shape=ShapeType.cylinder,
            dimensions=[0.1, 0.3, 0.1],
            position=Position3D(x=1.0, y=1.0, z=0.0),
            material_type=MaterialType.metal,
            scale=(1.0, 2.0, 1.0),
            rotation_y=90.0,
            emissive=True,
            emissive_color="#ff8c00",
            emissive_intensity=0.8,
        )
        assert p.material_type == MaterialType.metal
        assert p.scale == (1.0, 2.0, 1.0)
        assert p.rotation_y == 90.0
        assert p.emissive is True
        assert p.emissive_color == "#ff8c00"
        assert p.emissive_intensity == 0.8


# ---------------------------------------------------------------------------
# Character
# ---------------------------------------------------------------------------


class TestCharacter:
    def test_valid(self):
        from models import Character, Position3D

        c = Character(
            id="c1",
            name="Julius Caesar",
            role="Roman dictator at the height of his power.",
            position=Position3D(x=0.0, y=0.0, z=0.0),
            head_portrait_prompt="Portrait of Julius Caesar, Roman bust style, white background.",
            persona_summary="You are Julius Caesar. Speak with imperial authority.",
            interact_text="Speak with Caesar",
            primary=True,
        )
        assert c.primary is True

    def test_head_portrait_max_30_words(self):
        from models import Character, Position3D

        with pytest.raises(ValidationError):
            Character(
                id="c1",
                name="Caesar",
                role="Leader.",
                position=Position3D(x=0.0, y=0.0, z=0.0),
                head_portrait_prompt=" ".join(["word"] * 31),
                persona_summary="Short summary.",
                interact_text="Talk",
                primary=True,
            )

    def test_persona_summary_max_60_words(self):
        from models import Character, Position3D

        with pytest.raises(ValidationError):
            Character(
                id="c1",
                name="Caesar",
                role="Leader.",
                position=Position3D(x=0.0, y=0.0, z=0.0),
                head_portrait_prompt="Portrait white background.",
                persona_summary=" ".join(["word"] * 61),
                interact_text="Talk",
                primary=True,
            )

    def test_character_new_field_defaults(self):
        from models import AnimationHint, Character, CharacterArchetype, Position3D

        c = Character(
            id="c1",
            name="Caesar",
            role="Leader.",
            position=Position3D(x=0.0, y=0.0, z=0.0),
            head_portrait_prompt="Portrait white background.",
            persona_summary="You are Caesar.",
            interact_text="Talk",
            primary=True,
        )
        assert c.rotation_y == 0.0
        assert c.animation_hint == AnimationHint.idle_standing
        assert c.archetype == CharacterArchetype.formal_male

    def test_character_new_fields_custom(self):
        from models import AnimationHint, Character, CharacterArchetype, Position3D

        c = Character(
            id="c1",
            name="Charlie Duke",
            role="CAPCOM.",
            position=Position3D(x=3.0, y=0.0, z=-1.5),
            head_portrait_prompt="Portrait white background.",
            persona_summary="You are Charlie Duke.",
            interact_text="Talk",
            primary=True,
            rotation_y=225.0,
            animation_hint=AnimationHint.working_console,
            archetype=CharacterArchetype.scientist,
        )
        assert c.rotation_y == 225.0
        assert c.animation_hint == AnimationHint.working_console
        assert c.archetype == CharacterArchetype.scientist


# ---------------------------------------------------------------------------
# Light
# ---------------------------------------------------------------------------


class TestLight:
    def test_valid(self):
        from models import Light, LightType, Position3D

        l = Light(
            type=LightType.point,
            position=Position3D(x=0.0, y=3.0, z=0.0),
            color="#ffffff",
            intensity=1.0,
        )
        assert l.intensity == 1.0

    def test_intensity_too_high(self):
        from models import Light, LightType, Position3D

        with pytest.raises(ValidationError):
            Light(
                type=LightType.point,
                position=Position3D(x=0.0, y=3.0, z=0.0),
                color="#ffffff",
                intensity=2.1,
            )

    def test_intensity_negative(self):
        from models import Light, LightType, Position3D

        with pytest.raises(ValidationError):
            Light(
                type=LightType.ambient,
                position=Position3D(x=0.0, y=1.0, z=0.0),
                color="#ffffff",
                intensity=-0.1,
            )

    def test_invalid_light_type(self):
        from models import Light, Position3D

        with pytest.raises(ValidationError):
            Light(
                type="fluorescent",
                position=Position3D(x=0.0, y=1.0, z=0.0),
                color="#ffffff",
                intensity=1.0,
            )

    def test_light_new_field_defaults(self):
        from models import Light, LightType, Position3D

        l = Light(
            type=LightType.point,
            position=Position3D(x=0.0, y=3.0, z=0.0),
            color="#ffffff",
            intensity=1.0,
        )
        assert l.decay == 2.0
        assert l.cast_shadow is True
        assert l.source_label == ""

    def test_light_new_fields_custom(self):
        from models import Light, LightType, Position3D

        l = Light(
            type=LightType.point,
            position=Position3D(x=0.0, y=3.0, z=0.0),
            color="#4080ff",
            intensity=1.2,
            decay=1.5,
            cast_shadow=False,
            source_label="monitor glow",
        )
        assert l.decay == 1.5
        assert l.cast_shadow is False
        assert l.source_label == "monitor glow"


# ---------------------------------------------------------------------------
# CameraStart
# ---------------------------------------------------------------------------


class TestCameraStart:
    def test_valid(self):
        from models import CameraStart

        c = CameraStart(x=0.0, y=1.6, z=2.0)
        assert c.y == 1.6

    def test_y_must_be_1_6(self):
        from models import CameraStart

        with pytest.raises(ValidationError):
            CameraStart(x=0.0, y=1.8, z=2.0)

    def test_x_out_of_bounds(self):
        from models import CameraStart

        with pytest.raises(ValidationError):
            CameraStart(x=11.0, y=1.6, z=0.0)


# ---------------------------------------------------------------------------
# ScenePlan
# ---------------------------------------------------------------------------


class TestScenePlan:
    def test_valid_scene(self):
        from models import ScenePlan

        plan = ScenePlan.model_validate(_valid_scene_dict())
        assert plan.event_name == "Apollo 11 Moon Landing"
        assert plan.scene_id  # auto-generated UUID

    def test_scene_id_is_auto_generated(self):
        from models import ScenePlan

        p1 = ScenePlan.model_validate(_valid_scene_dict())
        p2 = ScenePlan.model_validate(_valid_scene_dict())
        assert p1.scene_id != p2.scene_id

    def test_dramatic_moment_max_20_words(self):
        from models import ScenePlan

        d = _valid_scene_dict(dramatic_moment=" ".join(["word"] * 21))
        with pytest.raises(ValidationError):
            ScenePlan.model_validate(d)

    def test_intro_narration_max_2_sentences(self):
        from models import ScenePlan

        d = _valid_scene_dict(
            intro_narration="First sentence. Second sentence. Third sentence."
        )
        with pytest.raises(ValidationError):
            ScenePlan.model_validate(d)

    def test_too_many_props(self):
        from models import ScenePlan

        prop = {
            "id": "p", "shape": "box", "dimensions": [1.0, 1.0, 1.0],
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        }
        d = _valid_scene_dict(props=[{**prop, "id": f"p{i}"} for i in range(7)])
        with pytest.raises(ValidationError):
            ScenePlan.model_validate(d)

    def test_too_many_characters(self):
        from models import ScenePlan

        char_base = {
            "name": "Caesar", "role": "Leader.",
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "head_portrait_prompt": "Portrait white background.",
            "persona_summary": "You are Caesar.",
            "interact_text": "Talk",
            "primary": False,
        }
        chars = [{**char_base, "id": f"c{i}"} for i in range(4)]
        chars[0]["primary"] = True
        d = _valid_scene_dict(characters=chars)
        with pytest.raises(ValidationError):
            ScenePlan.model_validate(d)

    def test_too_many_lights(self):
        from models import ScenePlan

        light = {
            "type": "point", "position": {"x": 0.0, "y": 1.0, "z": 0.0},
            "color": "#ffffff", "intensity": 1.0,
        }
        d = _valid_scene_dict(lights=[light] * 4)
        with pytest.raises(ValidationError):
            ScenePlan.model_validate(d)

    def test_too_many_ambient_sounds(self):
        from models import ScenePlan

        d = _valid_scene_dict(ambient_sounds=["wind", "fire_crackling", "silence"])
        with pytest.raises(ValidationError):
            ScenePlan.model_validate(d)

    def test_invalid_sound_id(self):
        from models import ScenePlan

        d = _valid_scene_dict(ambient_sounds=["laser_blasts"])
        with pytest.raises(ValidationError):
            ScenePlan.model_validate(d)

    def test_no_primary_character(self):
        from models import ScenePlan

        d = _valid_scene_dict()
        d["characters"][0]["primary"] = False
        with pytest.raises(ValidationError):
            ScenePlan.model_validate(d)

    def test_two_primary_characters_rejected(self):
        from models import ScenePlan

        char_base = {
            "name": "Caesar", "role": "Leader.",
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "head_portrait_prompt": "Portrait white background.",
            "persona_summary": "You are Caesar.",
            "interact_text": "Talk",
            "primary": True,
        }
        d = _valid_scene_dict(
            characters=[{**char_base, "id": "c1"}, {**char_base, "id": "c2"}]
        )
        with pytest.raises(ValidationError):
            ScenePlan.model_validate(d)

    def test_json_serializable(self):
        from models import ScenePlan

        plan = ScenePlan.model_validate(_valid_scene_dict())
        dumped = plan.model_dump(mode="json")
        assert isinstance(json.dumps(dumped), str)

    def test_is_valid_returns_empty_for_valid_plan(self):
        from models import ScenePlan

        plan = ScenePlan.model_validate(_valid_scene_dict())
        assert plan.is_valid() == []

    def test_validate_data_returns_errors_for_bad_dict(self):
        from models import ScenePlan

        errors = ScenePlan.validate_data({"event_name": "Missing fields"})
        assert len(errors) > 0

    def test_validate_data_returns_empty_for_valid_dict(self):
        from models import ScenePlan

        errors = ScenePlan.validate_data(_valid_scene_dict())
        assert errors == []

    def test_skybox_hint_default(self):
        from models import ScenePlan, SkyboxHint

        plan = ScenePlan.model_validate(_valid_scene_dict())
        assert plan.skybox_hint == SkyboxHint.none

    def test_skybox_hint_custom(self):
        from models import ScenePlan, SkyboxHint

        d = _valid_scene_dict(skybox_hint="night_stars")
        plan = ScenePlan.model_validate(d)
        assert plan.skybox_hint == SkyboxHint.night_stars


# ---------------------------------------------------------------------------
# ScenePlanner.generate_scene_plan — success path
# ---------------------------------------------------------------------------


def _make_json_response(data: dict):
    """Build a mock generate_content response with a .text JSON payload."""
    resp = MagicMock()
    resp.text = json.dumps(data)
    return resp


class TestGenerateScenePlanSuccess:
    def test_returns_scene_plan(self, mock_genai_client):
        from scene_planner import ScenePlanner

        mock_genai_client.models.generate_content.return_value = _make_json_response(
            _valid_scene_dict()
        )
        planner = ScenePlanner(api_key="key")
        plan = planner.generate_scene_plan("Apollo 11")

        from models import ScenePlan
        assert isinstance(plan, ScenePlan)
        assert plan.event_name == "Apollo 11 Moon Landing"

    def test_called_once_on_valid_response(self, mock_genai_client):
        from scene_planner import ScenePlanner

        mock_genai_client.models.generate_content.return_value = _make_json_response(
            _valid_scene_dict()
        )
        planner = ScenePlanner(api_key="key")
        planner.generate_scene_plan("Apollo 11")

        assert mock_genai_client.models.generate_content.call_count == 1


# ---------------------------------------------------------------------------
# ScenePlanner.generate_scene_plan — retry path
# ---------------------------------------------------------------------------


class TestGenerateScenePlanRetry:
    def test_retries_on_invalid_response(self, mock_genai_client):
        from scene_planner import ScenePlanner

        bad_resp = _make_json_response({"event_name": "Incomplete"})
        good_resp = _make_json_response(_valid_scene_dict())
        mock_genai_client.models.generate_content.side_effect = [bad_resp, good_resp]

        planner = ScenePlanner(api_key="key")
        plan = planner.generate_scene_plan("Something historical")

        assert mock_genai_client.models.generate_content.call_count == 2

        from models import ScenePlan
        assert isinstance(plan, ScenePlan)

    def test_retry_prompt_contains_errors(self, mock_genai_client):
        from scene_planner import ScenePlanner

        bad_resp = _make_json_response({})
        good_resp = _make_json_response(_valid_scene_dict())
        mock_genai_client.models.generate_content.side_effect = [bad_resp, good_resp]

        planner = ScenePlanner(api_key="key")
        planner.generate_scene_plan("Any event")

        second_call_args = mock_genai_client.models.generate_content.call_args_list[1]
        prompt_text = second_call_args[1]["contents"][0].parts[0].text
        assert "errors" in prompt_text.lower()


# ---------------------------------------------------------------------------
# ScenePlanner.generate_scene_plan — fallback path
# ---------------------------------------------------------------------------


class TestGenerateScenePlanFallback:
    def test_fallback_on_double_failure(self, mock_genai_client):
        from scene_planner import ScenePlanner

        bad_resp = _make_json_response({})
        mock_genai_client.models.generate_content.side_effect = [bad_resp, bad_resp]

        planner = ScenePlanner(api_key="key")
        plan = planner.generate_scene_plan("Broken input")

        assert mock_genai_client.models.generate_content.call_count == 2
        assert plan.event_name == "Apollo 11 Moon Landing"

    def test_fallback_plan_is_valid(self, mock_genai_client):
        from scene_planner import ScenePlanner

        bad_resp = _make_json_response({})
        mock_genai_client.models.generate_content.side_effect = [bad_resp, bad_resp]

        planner = ScenePlanner(api_key="key")
        plan = planner.generate_scene_plan("Broken input")

        assert plan.is_valid() == []

    def test_fallback_has_primary_character(self, mock_genai_client):
        from scene_planner import ScenePlanner

        bad_resp = _make_json_response({})
        mock_genai_client.models.generate_content.side_effect = [bad_resp, bad_resp]

        planner = ScenePlanner(api_key="key")
        plan = planner.generate_scene_plan("Broken input")

        primary_chars = [c for c in plan.characters if c.primary]
        assert len(primary_chars) == 1

    def test_fallback_invalid_json_triggers_fallback(self, mock_genai_client):
        """A non-JSON Gemini response should also end in the fallback scene."""
        from scene_planner import ScenePlanner

        bad_resp = MagicMock()
        bad_resp.text = "not valid json {{{"
        mock_genai_client.models.generate_content.return_value = bad_resp

        planner = ScenePlanner(api_key="key")
        plan = planner.generate_scene_plan("Bad response")

        assert plan.event_name == "Apollo 11 Moon Landing"


# ---------------------------------------------------------------------------
# build_scene_prompt
# ---------------------------------------------------------------------------


class TestBuildScenePrompt:
    def test_contains_user_input(self):
        from scene_planner import build_scene_prompt

        prompt = build_scene_prompt("French Revolution, Paris 1789")
        assert "French Revolution, Paris 1789" in prompt

    def test_contains_required_instructions(self):
        from scene_planner import build_scene_prompt

        prompt = build_scene_prompt("Something")
        assert "primary" in prompt.lower()
        assert "primitives" in prompt.lower() or "box" in prompt.lower()
        assert "dramatic moment" in prompt.lower() or "dramatic_moment" in prompt.lower()

    def test_returns_string(self):
        from scene_planner import build_scene_prompt

        assert isinstance(build_scene_prompt("test"), str)


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT content
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_mentions_shape_constraints(self):
        from scene_planner import SYSTEM_PROMPT

        assert "box" in SYSTEM_PROMPT
        assert "sphere" in SYSTEM_PROMPT
        assert "cylinder" in SYSTEM_PROMPT

    def test_mentions_max_props(self):
        from scene_planner import SYSTEM_PROMPT

        assert "6" in SYSTEM_PROMPT

    def test_mentions_max_characters(self):
        from scene_planner import SYSTEM_PROMPT

        assert "3" in SYSTEM_PROMPT

    def test_mentions_primary(self):
        from scene_planner import SYSTEM_PROMPT

        assert "primary" in SYSTEM_PROMPT

    def test_mentions_sound_ids(self):
        from scene_planner import SYSTEM_PROMPT

        assert "radio_chatter" in SYSTEM_PROMPT
        assert "console_beeps" in SYSTEM_PROMPT
