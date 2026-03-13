from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger()


class PiperTTS:
    """Local text-to-speech using Piper TTS (runs entirely offline).

    Piper is invoked as a subprocess, which means it must be installed in the
    container (via the Dockerfile or as a system package).
    The binary is expected to be on PATH as `piper`.
    """

    def __init__(self, model_path: str = "/app/voice/models/en_US-lessac-medium.onnx") -> None:
        """Configure TTS.

        Args:
            model_path: Path to the Piper ONNX voice model file.
        """
        self._model_path = model_path
        logger.info("tts.initialized", model=model_path)

    async def synthesize(self, text: str) -> bytes:
        """Convert text to speech audio bytes (WAV format).

        Returns empty bytes if synthesis fails or Piper is not installed.
        """
        if not text.strip():
            return b""

        return await asyncio.to_thread(self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> bytes:
        """Synchronous synthesis — runs in thread pool via piper subprocess."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                [
                    "piper",
                    "--model", self._model_path,
                    "--output_file", tmp_path,
                ],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace")
                logger.error("tts.piper_failed", stderr=stderr[:500])
                return b""

            audio_bytes = Path(tmp_path).read_bytes()
            logger.info("tts.synthesized", text_len=len(text), audio_bytes=len(audio_bytes))
            return audio_bytes

        except FileNotFoundError:
            logger.error("tts.piper_not_found",
                         help="Install Piper TTS: https://github.com/rhasspy/piper")
            return b""
        except subprocess.TimeoutExpired:
            logger.error("tts.timeout")
            return b""
        except Exception as exc:
            logger.error("tts.error", error=str(exc))
            return b""
        finally:
            Path(tmp_path).unlink(missing_ok=True)
