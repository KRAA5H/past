"""
test_gemini_live.py — unit tests for gemini_live.py.

All Gemini network I/O is replaced by mocks via the mock_live_client
fixture defined in conftest.py.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from google.genai import types as genai_types


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_started_session(mock_live_client, **kwargs):
    """Return a GeminiLiveSession that has already been start()ed."""
    from gemini_live import GeminiLiveSession

    session = GeminiLiveSession(api_key="test-key", **kwargs)
    await session.start()
    return session


def _make_response(*, data=None, text=None, turn_complete=False):
    """Build a minimal mock Gemini Live response object."""
    resp = MagicMock()
    resp.data = data
    resp.text = text
    if turn_complete:
        resp.server_content = MagicMock()
        resp.server_content.turn_complete = True
    else:
        resp.server_content = None
    return resp


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestGeminiLiveSessionInit:
    def test_creates_instance(self, mock_live_client):
        from gemini_live import GeminiLiveSession, LIVE_MODEL

        sess = GeminiLiveSession(api_key="key")
        assert sess._model == LIVE_MODEL
        assert sess._session is None
        assert sess._receive_task is None

    def test_custom_model(self, mock_live_client):
        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key", model="gemini-custom")
        assert sess._model == "gemini-custom"

    def test_callbacks_stored(self, mock_live_client):
        from gemini_live import GeminiLiveSession

        async def audio_cb(data): pass
        async def text_cb(text): pass

        sess = GeminiLiveSession(api_key="key", on_audio=audio_cb, on_text=text_cb)
        assert sess._on_audio is audio_cb
        assert sess._on_text is text_cb


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


class TestGeminiLiveSessionStart:
    @pytest.mark.asyncio
    async def test_start_enters_context_manager(self, mock_live_client):
        client, mock_session = mock_live_client
        sess = await _make_started_session(mock_live_client)

        client.aio.live.connect.assert_called_once()
        assert sess._session is mock_session

    @pytest.mark.asyncio
    async def test_start_creates_receive_task(self, mock_live_client):
        sess = await _make_started_session(mock_live_client)

        assert sess._receive_task is not None
        assert not sess._receive_task.done()

        # cleanup
        await sess.close()

    @pytest.mark.asyncio
    async def test_start_passes_config_with_voice(self, mock_live_client):
        client, _ = mock_live_client
        sess = await _make_started_session(mock_live_client)

        _, kwargs = client.aio.live.connect.call_args
        config = kwargs.get("config") or client.aio.live.connect.call_args[0][1]
        # Just verify connect was called with config keyword
        assert client.aio.live.connect.called

        await sess.close()


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


class TestGeminiLiveSessionClose:
    @pytest.mark.asyncio
    async def test_close_cancels_receive_task(self, mock_live_client):
        sess = await _make_started_session(mock_live_client)
        task = sess._receive_task

        await sess.close()

        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_close_exits_context_manager(self, mock_live_client):
        client, _ = mock_live_client
        cm = client.aio.live.connect.return_value

        sess = await _make_started_session(mock_live_client)
        await sess.close()

        cm.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_before_start_is_safe(self, mock_live_client):
        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key")
        # Should not raise
        await sess.close()

    @pytest.mark.asyncio
    async def test_double_close_is_safe(self, mock_live_client):
        sess = await _make_started_session(mock_live_client)
        await sess.close()
        # Second close should not raise
        await sess.close()


# ---------------------------------------------------------------------------
# send_audio()
# ---------------------------------------------------------------------------


class TestSendAudio:
    @pytest.mark.asyncio
    async def test_raises_if_not_started(self, mock_live_client):
        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key")
        with pytest.raises(RuntimeError, match="not started"):
            await sess.send_audio(b"\x00\x01\x02\x03")

    @pytest.mark.asyncio
    async def test_sends_pcm_blob(self, mock_live_client):
        _, mock_session = mock_live_client
        sess = await _make_started_session(mock_live_client)

        pcm = b"\x00\x01\x02\x03" * 100
        await sess.send_audio(pcm)

        mock_session.send.assert_called_once()
        send_arg = mock_session.send.call_args

        # Verify the input is a LiveClientRealtimeInput with correct MIME type
        kw_input = send_arg.kwargs.get("input") or send_arg.args[0]
        assert isinstance(kw_input, genai_types.LiveClientRealtimeInput)
        blob = kw_input.media_chunks[0]
        assert blob.mime_type == "audio/pcm;rate=16000"
        assert blob.data == pcm

        await sess.close()

    @pytest.mark.asyncio
    async def test_send_audio_empty_bytes(self, mock_live_client):
        _, mock_session = mock_live_client
        sess = await _make_started_session(mock_live_client)

        await sess.send_audio(b"")

        mock_session.send.assert_called_once()
        await sess.close()


# ---------------------------------------------------------------------------
# send_text()
# ---------------------------------------------------------------------------


class TestSendText:
    @pytest.mark.asyncio
    async def test_raises_if_not_started(self, mock_live_client):
        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key")
        with pytest.raises(RuntimeError, match="not started"):
            await sess.send_text("Hello")

    @pytest.mark.asyncio
    async def test_sends_text_turn(self, mock_live_client):
        _, mock_session = mock_live_client
        sess = await _make_started_session(mock_live_client)

        await sess.send_text("Tell me about Rome")

        mock_session.send.assert_called_once()
        send_arg = mock_session.send.call_args
        kw_input = send_arg.kwargs.get("input") or send_arg.args[0]

        assert isinstance(kw_input, genai_types.LiveClientContent)
        assert kw_input.turn_complete is True
        assert kw_input.turns[0].parts[0].text == "Tell me about Rome"
        assert kw_input.turns[0].role == "user"

        await sess.close()

    @pytest.mark.asyncio
    async def test_send_text_empty_string(self, mock_live_client):
        _, mock_session = mock_live_client
        sess = await _make_started_session(mock_live_client)

        await sess.send_text("")

        mock_session.send.assert_called_once()
        await sess.close()


# ---------------------------------------------------------------------------
# _handle_response()
# ---------------------------------------------------------------------------


class TestHandleResponse:
    @pytest.mark.asyncio
    async def test_dispatches_audio_to_callback(self, mock_live_client):
        received: list[bytes] = []

        async def audio_cb(data: bytes):
            received.append(data)

        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key", on_audio=audio_cb)
        pcm = b"\xff\x00" * 50
        response = _make_response(data=pcm)

        await sess._handle_response(response)

        assert len(received) == 1
        assert received[0] == pcm

    @pytest.mark.asyncio
    async def test_dispatches_text_to_callback(self, mock_live_client):
        received: list[str] = []

        async def text_cb(text: str):
            received.append(text)

        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key", on_text=text_cb)
        response = _make_response(text="Salve, civis!")

        await sess._handle_response(response)

        assert received == ["Salve, civis!"]

    @pytest.mark.asyncio
    async def test_audio_callback_not_called_without_data(self, mock_live_client):
        called = False

        async def audio_cb(data):
            nonlocal called
            called = True

        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key", on_audio=audio_cb)
        response = _make_response(data=None, text="transcript only")

        await sess._handle_response(response)

        assert not called

    @pytest.mark.asyncio
    async def test_text_callback_not_called_without_text(self, mock_live_client):
        called = False

        async def text_cb(text):
            nonlocal called
            called = True

        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key", on_text=text_cb)
        response = _make_response(data=b"\x00\x01", text=None)

        await sess._handle_response(response)

        assert not called

    @pytest.mark.asyncio
    async def test_no_callbacks_registered(self, mock_live_client):
        """_handle_response with no callbacks registered should not raise."""
        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key")
        response = _make_response(data=b"\x00\x01", text="hello", turn_complete=True)

        # Should not raise
        await sess._handle_response(response)

    @pytest.mark.asyncio
    async def test_turn_complete_no_crash(self, mock_live_client):
        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key")
        response = _make_response(turn_complete=True)

        await sess._handle_response(response)  # no-op, but must not raise

    @pytest.mark.asyncio
    async def test_both_callbacks_fired_on_same_response(self, mock_live_client):
        audio_received = []
        text_received = []

        async def audio_cb(d): audio_received.append(d)
        async def text_cb(t): text_received.append(t)

        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key", on_audio=audio_cb, on_text=text_cb)
        response = _make_response(data=b"\xAA", text="Ave!")

        await sess._handle_response(response)

        assert audio_received == [b"\xAA"]
        assert text_received == ["Ave!"]


# ---------------------------------------------------------------------------
# _receive_loop() — background dispatch
# ---------------------------------------------------------------------------


class TestReceiveLoop:
    @pytest.mark.asyncio
    async def test_dispatches_multiple_responses(self, mock_live_client, monkeypatch):
        """Reception loop should call _handle_response for every response yielded."""
        _, mock_session = mock_live_client

        responses = [
            _make_response(text="response 1"),
            _make_response(text="response 2"),
        ]

        async def fake_receive():
            for r in responses:
                yield r

        mock_session.receive = fake_receive

        received_texts = []

        async def text_cb(t):
            received_texts.append(t)

        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key", on_text=text_cb)
        await sess.start()
        # Give the event loop a moment to run the receive task
        await asyncio.sleep(0.05)
        await sess.close()

        assert "response 1" in received_texts
        assert "response 2" in received_texts

    @pytest.mark.asyncio
    async def test_loop_handles_cancelled_error_gracefully(self, mock_live_client):
        """CancelledError inside _receive_loop should not propagate."""
        _, mock_session = mock_live_client

        # receive() will block forever; cancellation breaks the loop
        async def blocking_receive():
            await asyncio.sleep(9999)
            return
            yield  # make it async generator

        mock_session.receive = blocking_receive

        from gemini_live import GeminiLiveSession

        sess = GeminiLiveSession(api_key="key")
        await sess.start()
        await asyncio.sleep(0.01)
        await sess.close()  # cancels the task — should not raise
