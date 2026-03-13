from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from api.config import get_settings
from models.ollama_client import OllamaClient
from voice.stt import WhisperSTT
from voice.tts import PiperTTS
from voice.voice_handler import VoiceHandler

logger = structlog.get_logger()
router = APIRouter()

# Lazy-initialize (heavy models) — created once per process
_stt: WhisperSTT | None = None
_tts: PiperTTS | None = None
_stt_lock: asyncio.Lock | None = None
_tts_lock: asyncio.Lock | None = None

# Per-session VoiceHandler cache to preserve conversation history
_voice_handlers: dict[str, VoiceHandler] = {}


def _get_stt_lock() -> asyncio.Lock:
    global _stt_lock
    if _stt_lock is None:
        _stt_lock = asyncio.Lock()
    return _stt_lock


def _get_tts_lock() -> asyncio.Lock:
    global _tts_lock
    if _tts_lock is None:
        _tts_lock = asyncio.Lock()
    return _tts_lock


async def _get_stt() -> WhisperSTT:
    global _stt
    async with _get_stt_lock():
        if _stt is None:
            _stt = WhisperSTT(model_name="base")
    return _stt


async def _get_tts() -> PiperTTS:
    global _tts
    async with _get_tts_lock():
        if _tts is None:
            _tts = PiperTTS()
    return _tts


# ── Request / Response Models ────────────────────────────────────────────────

class SpeakRequest(BaseModel):
    """Request body for text-to-speech synthesis."""

    text: str
    language: str | None = None


class TranscribeResponse(BaseModel):
    """Response for audio transcription."""

    data: dict | None = None
    error: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile,
    language: str | None = None,
) -> TranscribeResponse:
    """Transcribe an uploaded audio file to text using Whisper STT.

    Accepts WAV, MP3, or any ffmpeg-supported audio format.
    Max file size: 25 MB.
    """
    MAX_BYTES = 25 * 1024 * 1024
    audio_bytes = await file.read()

    if len(audio_bytes) > MAX_BYTES:
        return TranscribeResponse(
            data=None, error=f"Audio file too large. Max 25 MB."
        )

    if not audio_bytes:
        return TranscribeResponse(data=None, error="Empty audio file")

    try:
        stt = await _get_stt()
        transcript = await stt.transcribe(audio_bytes, language=language)
        return TranscribeResponse(
            data={"transcript": transcript, "language": language or "auto"},
            error=None,
        )
    except Exception as exc:
        logger.error("voice.transcribe_error", error=str(exc))
        return TranscribeResponse(data=None, error=str(exc))


@router.post("/speak")
async def text_to_speech(body: SpeakRequest) -> Response:
    """Synthesize text to speech using Piper TTS.

    Returns raw WAV audio bytes with content-type audio/wav.
    """
    if not body.text.strip():
        return Response(content=b"", media_type="audio/wav", status_code=400)

    try:
        tts = await _get_tts()
        audio_bytes = await tts.synthesize(body.text)

        if not audio_bytes:
            return Response(
                content=b"",
                status_code=503,
                headers={"X-Error": "TTS synthesis failed - is Piper installed?"},
            )

        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=speech.wav"},
        )
    except Exception as exc:
        logger.error("voice.speak_error", error=str(exc))
        return Response(content=b"", status_code=500)


@router.post("/conversation")
async def voice_conversation(
    request: Request,
    file: UploadFile,
    language: str | None = None,
) -> Response:
    """Full voice pipeline: audio → transcribe → LLM → speech.

    Returns a multipart response with text transcript (header) and WAV audio (body).
    """
    audio_bytes = await file.read()

    if not audio_bytes:
        return Response(content=b"", status_code=400,
                        headers={"X-Error": "Empty audio file"})

    settings = get_settings()
    session_id = request.headers.get("X-Session-Id", "default")
    if session_id not in _voice_handlers:
        ollama = OllamaClient(base_url=settings.ollama_base_url)
        _voice_handlers[session_id] = VoiceHandler(
            ollama_client=ollama,
            stt=await _get_stt(),
            tts=await _get_tts(),
            model=settings.default_model,
        )
    handler = _voice_handlers[session_id]

    try:
        result = await handler.process_audio(audio_bytes, language=language)

        if result.get("error"):
            return Response(
                content=b"",
                status_code=422,
                headers={"X-Error": result["error"]},
            )

        return Response(
            content=result["audio_bytes"],
            media_type="audio/wav",
            headers={
                "X-Transcript": result["transcript"][:500],
                "X-Response-Text": result["response_text"][:500],
            },
        )
    except Exception as exc:
        logger.error("voice.conversation_error", error=str(exc))
        return Response(content=b"", status_code=500)
