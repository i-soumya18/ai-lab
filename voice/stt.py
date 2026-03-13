from __future__ import annotations

import structlog

logger = structlog.get_logger()


class WhisperSTT:
    """Placeholder for speech-to-text.

    Currently skipped to reduce Docker image size.
    To implement: use Coqui STT, Vosk, or PocketSphinx.

    TODO: Implement lightweight STT alternative
    """

    def __init__(self, model_name: str = "base") -> None:
        """Initialize STT (placeholder)."""
        logger.info("stt.placeholder", model=model_name)

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio data (not yet supported).
            language:    ISO 639-1 language code (e.g. "en").

        Returns:
            Empty string — STT not yet implemented.
        """
        logger.warning("stt.not_implemented", requested=True)
        raise NotImplementedError(
            "STT is currently disabled to reduce Docker image size. "
            "To enable: install Coqui STT, Vosk, or PocketSphinx and implement the endpoint."
        )

