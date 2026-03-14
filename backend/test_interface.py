#!/usr/bin/env python
"""
test_interface.py — interactive CLI for testing Chronos backend modules
without the frontend.

Run from the backend/ directory:

    python test_interface.py

Requires the backend virtual-environment to be active so that
google-genai, fastapi, sqlmodel etc. are importable.

Features
--------
1. Inspect / validate models             (no API key needed)
2. ScenePlanner — mock mode              (no API key needed)
3. ScenePlanner — live Gemini API        (GEMINI_API_KEY required)
4. GeminiLiveSession — text, mock mode  (no API key needed)
5. GeminiLiveSession — text, live API   (GEMINI_API_KEY required)
6. Run pytest unit-tests
0. Exit
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import textwrap
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Path setup — allow running from project root as well
# ---------------------------------------------------------------------------

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ---------------------------------------------------------------------------
# Optional: load .env from project root
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(BACKEND_DIR), ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
    else:
        load_dotenv()  # try cwd
except ImportError:
    pass  # python-dotenv not installed — rely on shell env


# ---------------------------------------------------------------------------
# Colour / formatting helpers (no external deps)
# ---------------------------------------------------------------------------

_BOLD  = "\033[1m"
_GREEN = "\033[32m"
_CYAN  = "\033[36m"
_YELLOW = "\033[33m"
_RED   = "\033[31m"
_RESET = "\033[0m"

# Disable ANSI on Windows cmd.exe unless ANSICON / WT_SESSION set
if sys.platform == "win32" and not (
    os.environ.get("ANSICON") or os.environ.get("WT_SESSION") or
    os.environ.get("TERM_PROGRAM")
):
    _BOLD = _GREEN = _CYAN = _YELLOW = _RED = _RESET = ""


def _hdr(text: str) -> None:
    print(f"\n{_BOLD}{_CYAN}{'─' * 60}{_RESET}")
    print(f"{_BOLD}{_CYAN}  {text}{_RESET}")
    print(f"{_BOLD}{_CYAN}{'─' * 60}{_RESET}\n")


def _ok(text: str) -> None:
    print(f"{_GREEN}✔  {text}{_RESET}")


def _warn(text: str) -> None:
    print(f"{_YELLOW}⚠  {text}{_RESET}")


def _err(text: str) -> None:
    print(f"{_RED}✘  {text}{_RESET}")


def _pretty_scene(state) -> None:
    """Pretty-print a SceneState object."""
    data = state.model_dump()
    print(f"\n{_BOLD}Session ID  :{_RESET} {data['session_id']}")
    print(f"{_BOLD}Description :{_RESET} {data['description']}")
    print(f"{_BOLD}Lighting    :{_RESET} {data['lighting']}")
    print(f"{_BOLD}Ambient     :{_RESET} {data['ambient_sound'] or '(none)'}")

    if data["npcs"]:
        print(f"\n{_BOLD}NPCs ({len(data['npcs'])}){_RESET}")
        for npc in data["npcs"]:
            print(f"  [{npc['npc_id']}] {npc['name']} — {npc['role'] or 'no role'}")
            print(f"       pos={npc['position']}  mood={npc['mood']}  action={npc['action']}")
            if npc["dialogue"]:
                print(f"       dialogue: \"{npc['dialogue']}\"")
    else:
        print(f"\n{_BOLD}NPCs{_RESET}: (none)")

    if data["objects"]:
        print(f"\n{_BOLD}Objects ({len(data['objects'])}){_RESET}")
        for obj in data["objects"]:
            print(f"  [{obj['object_id']}] {obj['asset']}")
            print(f"       pos={obj['position']}  rot={obj['rotation']}  scale={obj['scale']}")
    else:
        print(f"\n{_BOLD}Objects{_RESET}: (none)")

    print(f"\n{_BOLD}Raw JSON:{_RESET}")
    print(textwrap.indent(json.dumps(data, indent=2), "  "))


def _get_api_key() -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key if key else None


# ---------------------------------------------------------------------------
# Option 1 — Model inspection
# ---------------------------------------------------------------------------


def option_inspect_models() -> None:
    _hdr("Model Inspection & Validation")

    from models import (
        NPCBase, NPCMood, NPCAction,
        SceneObjectBase, SceneState,
        WSMessage, WSMessageType,
    )

    # --- Enums ---
    print(f"{_BOLD}NPCMood values:{_RESET}", [m.value for m in NPCMood])
    print(f"{_BOLD}NPCAction values:{_RESET}", [a.value for a in NPCAction])
    print(f"{_BOLD}WSMessageType values:{_RESET}", [t.value for t in WSMessageType])

    # --- NPCBase ---
    npc = NPCBase(
        npc_id="demo_npc",
        name="Cleopatra VII",
        role="Pharaoh",
        position=[1.0, 0.0, -2.0],
        mood=NPCMood.happy,
        action=NPCAction.gesture,
        dialogue="Welcome to Alexandria.",
    )
    print(f"\n{_BOLD}Example NPCBase:{_RESET}")
    print(textwrap.indent(json.dumps(npc.model_dump(), indent=2), "  "))

    # --- SceneObjectBase ---
    obj = SceneObjectBase(
        object_id="obelisk_1",
        asset="obelisk.glb",
        position=[0.0, 0.0, -5.0],
        scale=[1.5, 1.5, 1.5],
    )
    print(f"\n{_BOLD}Example SceneObjectBase:{_RESET}")
    print(textwrap.indent(json.dumps(obj.model_dump(), indent=2), "  "))

    # --- SceneState ---
    state = SceneState(
        session_id="demo-session",
        description="Alexandria harbour, 47 BC",
        lighting="dusk",
        ambient_sound="waves.mp3",
        npcs=[npc],
        objects=[obj],
    )
    print(f"\n{_BOLD}Example SceneState:{_RESET}")
    _pretty_scene(state)

    # --- Validation error example ---
    print(f"\n{_BOLD}Validation (invalid mood):{_RESET}")
    try:
        NPCBase(npc_id="x", name="X", mood="flying")
        _err("No error raised — unexpected!")
    except Exception as exc:
        _ok(f"ValidationError raised as expected: {exc.errors()[0]['msg']}")

    # --- WSMessage round-trip ---
    raw = {"type": "scene_update", "payload": {"session_id": "abc"}}
    msg = WSMessage.model_validate(raw)
    _ok(f"WSMessage parsed: type={msg.type.value}")


# ---------------------------------------------------------------------------
# Option 2 — ScenePlanner mock mode
# ---------------------------------------------------------------------------


def option_scene_planner_mock() -> None:
    _hdr("ScenePlanner — Mock Gemini Mode")

    from scene_planner import ScenePlanner
    from google import genai as _genai

    prompt = input("Enter a scene description prompt\n> ").strip()
    if not prompt:
        _warn("Empty prompt — using default.")
        prompt = "The Roman Forum during Caesar's time"

    session_id = "mock-session-001"

    # Build a realistic mock response
    def _make_mock_response():
        def _fc(name, args):
            fc = MagicMock(); fc.name = name; fc.args = args
            part = MagicMock(); part.function_call = fc
            return part

        candidate = MagicMock()
        candidate.content.parts = [
            _fc("set_scene_description", {
                "description": f"[MOCK] Scene for: {prompt}",
                "lighting": "day",
                "ambient_sound": "ambient.mp3",
            }),
            _fc("place_npc", {
                "npc_id": "mock_npc_1",
                "name": "Mock Person A",
                "role": "Citizen",
                "position": [0.0, 0.0, 0.0],
                "mood": "neutral",
                "action": "idle",
                "dialogue": "This is a mock response.",
            }),
            _fc("place_npc", {
                "npc_id": "mock_npc_2",
                "name": "Mock Person B",
                "role": "Merchant",
                "position": [2.0, 0.0, 1.5],
                "mood": "happy",
                "action": "gesture",
                "dialogue": "Buy my wares!",
            }),
            _fc("place_object", {
                "object_id": "mock_obj_1",
                "asset": "column.glb",
                "position": [-3.0, 0.0, -2.0],
                "scale": [1.0, 1.0, 1.0],
            }),
        ]
        resp = MagicMock()
        resp.candidates = [candidate]
        return resp

    # Patch genai.Client
    original_client = _genai.Client
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response()
    _genai.Client = lambda **kw: mock_client

    try:
        planner = ScenePlanner(api_key="mock-key")
        print(f"\nPlanning scene for: {_BOLD}{prompt}{_RESET}")
        state = planner.plan_scene(prompt, session_id)
        _ok("Scene generated (mock)")
        _pretty_scene(state)
    finally:
        _genai.Client = original_client


# ---------------------------------------------------------------------------
# Option 3 — ScenePlanner live API
# ---------------------------------------------------------------------------


def option_scene_planner_live() -> None:
    _hdr("ScenePlanner — Live Gemini API")

    api_key = _get_api_key()
    if not api_key:
        _err("No GEMINI_API_KEY found. Set it in .env or as an environment variable.")
        return

    from scene_planner import ScenePlanner

    prompt = input("Enter a historical scene prompt\n> ").strip()
    if not prompt:
        _warn("Empty prompt — using default.")
        prompt = "The Roman Forum during Caesar's time, 44 BC"

    session_id = "live-session-001"
    print(f"\nSending to Gemini: {_BOLD}{prompt}{_RESET}")
    print("(this may take a few seconds...)\n")

    try:
        planner = ScenePlanner(api_key=api_key)
        state = planner.plan_scene(prompt, session_id)
        _ok("Scene generated (live API)")
        _pretty_scene(state)
    except Exception as exc:
        _err(f"Error: {exc}")


# ---------------------------------------------------------------------------
# Option 4 — GeminiLiveSession mock (text)
# ---------------------------------------------------------------------------


def option_live_session_mock() -> None:
    _hdr("GeminiLiveSession — Mock Mode (text input)")

    from gemini_live import GeminiLiveSession
    from google import genai as _genai

    print("Type messages and see simulated responses. Enter 'done' to exit.\n")

    audio_chunks: list[bytes] = []
    transcripts: list[str] = []

    async def _run():
        async def on_audio(data: bytes):
            audio_chunks.append(data)
            print(f"  {_CYAN}[audio] received {len(data)} bytes of PCM{_RESET}")

        async def on_text(text: str):
            transcripts.append(text)
            print(f"  {_GREEN}[transcript]{_RESET} {text}")

        # Patch genai.Client
        original_client = _genai.Client

        # Build async mock session
        mock_session = AsyncMock()
        counter = {"n": 0}

        async def fake_receive():
            """Yield a text response after each send_text call."""
            while True:
                await asyncio.sleep(0.3)
                counter["n"] += 1
                r = MagicMock()
                r.data = None
                r.text = f"[MOCK response #{counter['n']}] Interesting historical question!"
                r.server_content = MagicMock()
                r.server_content.turn_complete = True
                yield r

        mock_session.receive = fake_receive

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_client = MagicMock()
        mock_client.aio.live.connect.return_value = mock_cm
        _genai.Client = lambda **kw: mock_client

        try:
            sess = GeminiLiveSession(api_key="mock-key", on_audio=on_audio, on_text=on_text)
            await sess.start()
            _ok("Session started (mock)")

            while True:
                try:
                    text = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("\nYou > ")
                    )
                except (EOFError, KeyboardInterrupt):
                    break

                if text.strip().lower() in ("done", "exit", "quit", ""):
                    break

                await sess.send_text(text)
                await asyncio.sleep(0.5)  # let receive loop deliver response

            await sess.close()
            _ok("Session closed")

        finally:
            _genai.Client = original_client

        print(f"\n{_BOLD}Summary:{_RESET} {len(transcripts)} transcript(s) received, "
              f"{len(audio_chunks)} audio chunk(s) received")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Option 5 — GeminiLiveSession live API (text)
# ---------------------------------------------------------------------------


def option_live_session_live() -> None:
    _hdr("GeminiLiveSession — Live Gemini API (text input)")

    api_key = _get_api_key()
    if not api_key:
        _err("No GEMINI_API_KEY found. Set it in .env or as an environment variable.")
        return

    from gemini_live import GeminiLiveSession

    print("Type messages and press Enter. Type 'done' to exit.\n")

    transcripts: list[str] = []
    audio_chunks: list[bytes] = []

    async def _run():
        async def on_audio(data: bytes):
            audio_chunks.append(data)
            print(f"  {_CYAN}[audio chunk received: {len(data)} bytes]{_RESET}")

        async def on_text(text: str):
            transcripts.append(text)
            print(f"  {_GREEN}Chronos:{_RESET} {text}")

        print("Connecting to Gemini Live API...\n")
        try:
            sess = GeminiLiveSession(api_key=api_key, on_audio=on_audio, on_text=on_text)
            await sess.start()
            _ok("Live session started")

            while True:
                try:
                    text = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("\nYou > ")
                    )
                except (EOFError, KeyboardInterrupt):
                    break

                if text.strip().lower() in ("done", "exit", "quit", ""):
                    break

                await sess.send_text(text)
                await asyncio.sleep(1.0)  # allow Gemini time to respond

            await sess.close()
            _ok("Session closed")

        except Exception as exc:
            _err(f"Error: {exc}")

        print(f"\n{_BOLD}Summary:{_RESET} {len(transcripts)} transcripts, "
              f"{len(audio_chunks)} audio chunks")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Option 6 — Run pytest
# ---------------------------------------------------------------------------


def option_run_tests() -> None:
    _hdr("Running Pytest Unit Tests")

    tests_dir = os.path.join(BACKEND_DIR, "tests")
    args = [sys.executable, "-m", "pytest", tests_dir, "-v", "--tb=short", "--no-header"]

    extra = input(
        "Extra pytest flags (e.g. -k test_models, or press Enter for all): "
    ).strip()
    if extra:
        args.extend(extra.split())

    print()
    result = subprocess.run(args, cwd=BACKEND_DIR)
    if result.returncode == 0:
        _ok("All tests passed.")
    else:
        _err(f"Tests finished with exit code {result.returncode}.")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------


_MENU = f"""
{_BOLD}Chronos Backend — Test Interface{_RESET}

  {_CYAN}1{_RESET} — Inspect & validate models          (no API key needed)
  {_CYAN}2{_RESET} — ScenePlanner: mock Gemini           (no API key needed)
  {_CYAN}3{_RESET} — ScenePlanner: live Gemini API       (GEMINI_API_KEY required)
  {_CYAN}4{_RESET} — GeminiLiveSession: text, mock       (no API key needed)
  {_CYAN}5{_RESET} — GeminiLiveSession: text, live API   (GEMINI_API_KEY required)
  {_CYAN}6{_RESET} — Run pytest unit tests
  {_CYAN}0{_RESET} — Exit
"""

_OPTIONS = {
    "1": option_inspect_models,
    "2": option_scene_planner_mock,
    "3": option_scene_planner_live,
    "4": option_live_session_mock,
    "5": option_live_session_live,
    "6": option_run_tests,
}


def main() -> None:
    api_key = _get_api_key()
    key_status = (
        f"{_GREEN}GEMINI_API_KEY found{_RESET}"
        if api_key
        else f"{_YELLOW}GEMINI_API_KEY not set (mock options still work){_RESET}"
    )
    print(_MENU)
    print(f"  Status: {key_status}\n")

    while True:
        try:
            choice = input("Select option > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if choice == "0":
            print("Bye.")
            break

        fn = _OPTIONS.get(choice)
        if fn:
            try:
                fn()
            except KeyboardInterrupt:
                print("\n(interrupted)")
            except Exception as exc:
                _err(f"Unexpected error: {exc}")
                import traceback
                traceback.print_exc()
        else:
            _warn(f"Unknown option '{choice}'. Enter 0-6.")

        print()  # blank line between interactions


if __name__ == "__main__":
    main()
