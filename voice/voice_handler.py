from __future__ import annotations

from typing import Any

import structlog

from models.ollama_client import OllamaClient
from voice.stt import WhisperSTT
from voice.tts import PiperTTS

logger = structlog.get_logger()


class VoiceHandler:
    """Full voice loop: audio → text → LLM → speech.

    Orchestrates the STT → LLM → TTS pipeline for voice assistant interactions.
    All components run entirely locally with no cloud dependencies.
    """

    def __init__(
        self,
        ollama_client: OllamaClient,
        stt: WhisperSTT,
        tts: PiperTTS,
        model: str = "nemotron-3-super:cloud",
    ) -> None:
        self._ollama = ollama_client
        self._stt = stt
        self._tts = tts
        self._model = model
        self._conversation: list[dict[str, str]] = []

    async def process_audio(
        self,
        audio_bytes: bytes,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Full pipeline: transcribe audio → generate response → synthesize speech.

        Returns a dict with:
        - transcript: what was spoken
        - response_text: LLM response
        - audio_bytes: synthesized speech (WAV)
        """
        # Step 1: Speech → Text
        transcript = await self._stt.transcribe(audio_bytes, language=language)
        if not transcript:
            return {"transcript": "", "response_text": "", "audio_bytes": b"",
                    "error": "Could not transcribe audio"}

        logger.info("voice.transcribed", transcript=transcript[:100])

        # Step 2: LLM response
        self._conversation.append({"role": "user", "content": transcript})
        response_text = await self._ollama.chat(
            model=self._model,
            messages=self._conversation,
            stream=False,
        )
        self._conversation.append({"role": "assistant", "content": response_text})

        # Keep conversation history bounded
        if len(self._conversation) > 20:
            self._conversation = self._conversation[-20:]

        logger.info("voice.response_generated", chars=len(response_text))

        # Step 3: Text → Speech
        speech_bytes = await self._tts.synthesize(response_text)

        return {
            "transcript": transcript,
            "response_text": response_text,
            "audio_bytes": speech_bytes,
            "error": None,
        }

    async def transcribe_only(self, audio_bytes: bytes, language: str | None = None) -> str:
        """Just transcribe audio to text — no LLM call."""
        return await self._stt.transcribe(audio_bytes, language=language)

    async def speak_only(self, text: str) -> bytes:
        """Just synthesize text to speech — no LLM call."""
        return await self._tts.synthesize(text)

    def reset_conversation(self) -> None:
        """Clear the voice conversation history."""
        self._conversation = []
        logger.info("voice.conversation_reset")
