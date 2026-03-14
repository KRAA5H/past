"""
main.py — FastAPI application entry point.

Routes:
  GET  /health             — health check
  POST /api/scene          — generate a scene (legacy SceneState, function-calling)
  POST /api/scene/plan     — generate a validated ScenePlan (JSON mode, with retry)
  GET  /api/scene/{id}     — retrieve a stored scene
  GET  /api/scene/plan/{id}— retrieve a stored ScenePlan
  WS   /ws/{session_id}    — bidirectional audio/text WebSocket

WebSocket message flow (idea → Scene → NPC → Voice → Leave → Exit):
  Client sends scene_request    → server generates ScenePlan → sends scene_plan_update
  Client sends npc_interact     → server starts NPC Live session → sends cutscene_start
  Client sends audio_chunk/text → forwarded to active Live session
  Client sends npc_leave        → server resets to general Live session
  Client sends scene_exit       → server clears scene state
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session, select

load_dotenv()

from gemini_live import GeminiLiveSession
from models import (
    NPC,
    ScenePlan,
    SceneState,
    WSMessage,
    WSMessageType,
    create_db_and_tables,
    get_session,
)
from scene_planner import ScenePlanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

# In-memory store for active WebSocket ↔ Live sessions
_live_sessions: dict[str, GeminiLiveSession] = {}
_scene_states: dict[str, SceneState] = {}
_scene_plans: dict[str, ScenePlan] = {}


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    logger.info("DB tables created / verified")
    yield
    # Cleanup open Live sessions
    for session in list(_live_sessions.values()):
        await session.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Chronos API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets from the backend/assets folder
assets_path = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(assets_path, exist_ok=True)
app.mount("/assets", StaticFiles(directory=assets_path), name="assets")


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


class SceneRequest(BaseModel):
    prompt: str
    session_id: str | None = None


@app.post("/api/scene", response_model=SceneState)
async def create_scene(req: SceneRequest):
    """Generate a new scene from a text prompt using Gemini function calling."""
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    session_id = req.session_id or str(uuid.uuid4())
    planner = ScenePlanner(api_key=GEMINI_API_KEY)
    try:
        state = planner.plan_scene(req.prompt, session_id=session_id)
    except Exception as exc:
        logger.error("Scene planning error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Gemini error: {exc}") from exc

    _scene_states[session_id] = state
    return state


@app.get("/api/scene/{session_id}", response_model=SceneState)
async def get_scene(session_id: str):
    """Return a previously generated scene by session ID."""
    state = _scene_states.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Scene not found")
    return state


@app.post("/api/scene/plan", response_model=ScenePlan)
async def create_scene_plan(req: SceneRequest):
    """
    Generate a validated ScenePlan using JSON mode with automatic retry and
    an Apollo 11 fallback if Gemini fails twice.
    """
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    planner = ScenePlanner(api_key=GEMINI_API_KEY)
    try:
        plan = planner.generate_scene_plan(req.prompt)
    except Exception as exc:
        logger.error("Scene plan generation error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Gemini error: {exc}") from exc

    # Use the plan's own scene_id as the storage key so GET and POST agree on the ID.
    _scene_plans[plan.scene_id] = plan
    return plan


@app.get("/api/scene/plan/{plan_id}", response_model=ScenePlan)
async def get_scene_plan(plan_id: str):
    """Return a previously generated ScenePlan by its scene_id."""
    plan = _scene_plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="ScenePlan not found")
    return plan


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info("WebSocket connected: %s", session_id)

    # Queues bridge WS ↔ Live session and persist across Live session restarts.
    audio_out_queue: asyncio.Queue[bytes] = asyncio.Queue()
    text_out_queue: asyncio.Queue[str] = asyncio.Queue()

    async def on_audio(pcm: bytes) -> None:
        await audio_out_queue.put(pcm)

    async def on_text(text: str) -> None:
        await text_out_queue.put(text)

    async def _start_live(system_prompt: str | None = None) -> GeminiLiveSession:
        """Create, start and register a GeminiLiveSession."""
        sess = GeminiLiveSession(
            api_key=GEMINI_API_KEY,
            on_audio=on_audio,
            on_text=on_text,
            system_prompt=system_prompt,
        )
        await sess.start()
        _live_sessions[session_id] = sess
        return sess

    live: GeminiLiveSession | None = None

    if GEMINI_API_KEY:
        live = await _start_live()

    # Send a status message to the client
    await websocket.send_json(
        WSMessage(type=WSMessageType.status, payload={"connected": True}).model_dump()
    )

    async def forward_audio_out():
        """Forward Gemini audio responses back to the WebSocket client."""
        while True:
            pcm = await audio_out_queue.get()
            try:
                msg = WSMessage(
                    type=WSMessageType.audio_output,
                    payload={"data": list(pcm)},
                )
                await websocket.send_json(msg.model_dump())
            except Exception:
                break

    async def forward_text_out():
        """Forward Gemini transcript responses back to the WebSocket client."""
        while True:
            text = await text_out_queue.get()
            try:
                msg = WSMessage(
                    type=WSMessageType.transcript,
                    payload={"text": text},
                )
                await websocket.send_json(msg.model_dump())
            except Exception:
                break

    # Start forwarding tasks once; they survive Live session restarts because
    # they read from the shared queues rather than from a specific session.
    tasks = []
    if live:
        tasks.append(asyncio.create_task(forward_audio_out()))
        tasks.append(asyncio.create_task(forward_text_out()))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = WSMessage.model_validate_json(raw)
            except Exception as exc:
                logger.warning("Invalid WS message: %s", exc)
                await websocket.send_json(
                    WSMessage(
                        type=WSMessageType.error,
                        payload={"detail": "Invalid message format"},
                    ).model_dump()
                )
                continue

            # ----------------------------------------------------------------
            # audio_chunk — forward raw PCM to the active Live session
            # ----------------------------------------------------------------
            if msg.type == WSMessageType.audio_chunk:
                if live and msg.payload and "data" in msg.payload:
                    pcm = bytes(msg.payload["data"])
                    await live.send_audio(pcm)

            # ----------------------------------------------------------------
            # text_input — forward text to the active Live session (or echo)
            # ----------------------------------------------------------------
            elif msg.type == WSMessageType.text_input:
                text = (msg.payload or {}).get("text", "")
                if text:
                    if live:
                        await live.send_text(text)
                    else:
                        # No API key — echo back
                        await websocket.send_json(
                            WSMessage(
                                type=WSMessageType.transcript,
                                payload={"text": f"[echo] {text}"},
                            ).model_dump()
                        )

            # ----------------------------------------------------------------
            # scene_request — Idea → ScenePlan (generate_scene_plan)
            # ----------------------------------------------------------------
            elif msg.type == WSMessageType.scene_request:
                prompt = (msg.payload or {}).get("prompt", "")
                if prompt:
                    if GEMINI_API_KEY:
                        planner = ScenePlanner(api_key=GEMINI_API_KEY)
                        try:
                            plan = planner.generate_scene_plan(prompt)
                            _scene_plans[session_id] = plan
                            await websocket.send_json(
                                WSMessage(
                                    type=WSMessageType.scene_plan_update,
                                    payload=plan.model_dump(mode="json"),
                                ).model_dump()
                            )
                        except Exception as exc:
                            logger.error("Scene plan error: %s", exc)
                            await websocket.send_json(
                                WSMessage(
                                    type=WSMessageType.error,
                                    payload={"detail": str(exc)},
                                ).model_dump()
                            )
                    else:
                        # No API key — use fallback Apollo 11 scene
                        from scene_planner import _build_fallback_scene
                        plan = _build_fallback_scene()
                        _scene_plans[session_id] = plan
                        await websocket.send_json(
                            WSMessage(
                                type=WSMessageType.scene_plan_update,
                                payload=plan.model_dump(mode="json"),
                            ).model_dump()
                        )

            # ----------------------------------------------------------------
            # npc_interact — press key → intro cutscene + NPC Live session
            # ----------------------------------------------------------------
            elif msg.type == WSMessageType.npc_interact:
                npc_id = (msg.payload or {}).get("npc_id", "")
                plan = _scene_plans.get(session_id)
                if plan:
                    character = next(
                        (c for c in plan.characters if c.id == npc_id), None
                    )
                    if character:
                        if GEMINI_API_KEY:
                            # Restart Live session using the NPC's persona
                            if live:
                                await live.close()
                            live = await _start_live(character.persona_summary)
                        # Send cutscene_start with intro narration
                        await websocket.send_json(
                            WSMessage(
                                type=WSMessageType.cutscene_start,
                                payload={
                                    "intro_narration": plan.intro_narration,
                                    "character_name": character.name,
                                },
                            ).model_dump()
                        )

            # ----------------------------------------------------------------
            # npc_leave — leave NPC interaction, restore general Live session
            # ----------------------------------------------------------------
            elif msg.type == WSMessageType.npc_leave:
                if live:
                    await live.close()
                    _live_sessions.pop(session_id, None)
                    live = None
                if GEMINI_API_KEY:
                    live = await _start_live()
                    if not tasks:
                        tasks.append(asyncio.create_task(forward_audio_out()))
                        tasks.append(asyncio.create_task(forward_text_out()))

            # ----------------------------------------------------------------
            # scene_exit — clear scene state, back to idle
            # ----------------------------------------------------------------
            elif msg.type == WSMessageType.scene_exit:
                _scene_plans.pop(session_id, None)
                _scene_states.pop(session_id, None)
                await websocket.send_json(
                    WSMessage(
                        type=WSMessageType.status,
                        payload={"scene_exited": True},
                    ).model_dump()
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", session_id)
    finally:
        for task in tasks:
            task.cancel()
        if live:
            await live.close()
            _live_sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.environ.get("BACKEND_HOST", "0.0.0.0"),
        port=int(os.environ.get("BACKEND_PORT", "8000")),
        reload=True,
    )
