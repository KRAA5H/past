"""
gemini_live.py — thin async wrapper around the Gemini Live API (bidirectional
audio + text streaming).

Usage:
    session = GeminiLiveSession(api_key="...", on_audio=cb, on_text=cb)
    await session.start()
    await session.send_audio(pcm_bytes)
    await session.send_text("Hello")
    await session.close()
"""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Callable, Awaitable
from typing import Any

from google import genai
from google.genai import types as genai_types

logger = logging.getLogger(__name__)

LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

SYSTEM_PROMPT = (
    "You are Chronos, an AI guide to the past. "
    "The user can speak to you about historical events, people or places. "
    "Respond conversationally and helpfully. "
    "When the user asks you to show or recreate a scene, acknowledge the request "
    "and describe what you will show."
)


class GeminiLiveSession:
    """
    Wraps a single Gemini Live API streaming session.

    Callbacks:
        on_audio  — called with raw PCM bytes (16-bit, 24 kHz, mono)
        on_text   — called with a text transcript string
    """

    def __init__(
        self,
        api_key: str,
        on_audio: Callable[[bytes], Awaitable[None]] | None = None,
        on_text: Callable[[str], Awaitable[None]] | None = None,
        model: str = LIVE_MODEL,
    ) -> None:
        self._client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        self._model = model
        self._on_audio = on_audio
        self._on_text = on_text
        self._session: Any = None
        self._receive_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Open the Live API session and start the receive loop."""
        config = genai_types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=genai_types.Content(
                parts=[genai_types.Part(text=SYSTEM_PROMPT)]
            ),
            speech_config=genai_types.SpeechConfig(
                voice_config=genai_types.VoiceConfig(
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )
        # The Live API uses an async context manager
        self._cm = self._client.aio.live.connect(model=self._model, config=config)
        self._session = await self._cm.__aenter__()
        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.info("GeminiLiveSession started")

    async def close(self) -> None:
        """Gracefully close the session."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._session:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
        logger.info("GeminiLiveSession closed")

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Send a chunk of raw PCM audio to Gemini Live."""
        if not self._session:
            raise RuntimeError("Session not started")
        await self._session.send(
            input=genai_types.LiveClientRealtimeInput(
                media_chunks=[
                    genai_types.Blob(
                        mime_type="audio/pcm;rate=16000",
                        data=pcm_bytes,
                    )
                ]
            )
        )

    async def send_text(self, text: str) -> None:
        """Send a text turn to Gemini Live."""
        if not self._session:
            raise RuntimeError("Session not started")
        await self._session.send(
            input=genai_types.LiveClientContent(
                turns=[
                    genai_types.Content(
                        role="user",
                        parts=[genai_types.Part(text=text)],
                    )
                ],
                turn_complete=True,
            )
        )

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        """Background task: read responses and dispatch to callbacks."""
        try:
            async for response in self._session.receive():
                await self._handle_response(response)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Receive loop error: %s", exc)

    async def _handle_response(self, response: Any) -> None:
        # Audio data
        if (
            response.data
            and self._on_audio
        ):
            await self._on_audio(response.data)

        # Text / transcript
        if response.text and self._on_text:
            await self._on_text(response.text)

        # Server-turn-complete — nothing special needed here
        if response.server_content and response.server_content.turn_complete:
            logger.debug("Gemini Live turn complete")
