"""Speech adapters.

TTS: edge-tts (free Microsoft Edge voices) for Hindi, Marathi and English.
ASR: browser Web Speech API by default. Optional faster-whisper on the server
if installed; otherwise the API returns a clear 503 instead of pretending to
transcribe. No audio is fabricated.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any

from ..config import settings

logger = logging.getLogger(__name__)


class SpeechUnavailable(RuntimeError):
    def __init__(self, message: str, provider: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider


class SpeechService:
    def __init__(self) -> None:
        self.tts_provider = settings.tts_provider
        self.asr_provider = settings.asr_provider
        self._whisper_model = None

    def voices(self) -> dict[str, str]:
        return {"hi": settings.edge_voice_hi, "mr": settings.edge_voice_mr, "en": settings.edge_voice_en}

    def info(self) -> dict[str, Any]:
        return {
            "tts": {
                "provider": self.tts_provider,
                "voices": self.voices(),
                "mode": "server-side edge-tts" if self.tts_provider.startswith("edge") else "browser fallback",
                "note": "If server TTS is unavailable the web client can use the browser SpeechSynthesis API.",
            },
            "asr": {
                "provider": self.asr_provider,
                "server_available": self.asr_provider in {"faster-whisper", "faster_whisper"},
                "note": (
                    "Browser Web Speech API is the default ASR path. Server-side faster-whisper is optional."
                    if self.asr_provider not in {"faster-whisper", "faster_whisper"}
                    else "faster-whisper is configured; the model is loaded lazily on first use."
                ),
            },
        }

    async def synthesize(self, text: str, language: str) -> dict[str, Any]:
        language = language if language in {"hi", "mr", "en"} else "en"
        if not self.tts_provider.startswith("edge"):
            raise SpeechUnavailable(
                "Server-side TTS is disabled. The web client can use the browser SpeechSynthesis API.",
                provider=self.tts_provider,
            )
        voice = self.voices()[language]
        digest = hashlib.sha256(f"{voice}:{text}".encode("utf-8")).hexdigest()[:24]
        cache_path = Path(settings.tts_cache_dir) / f"{digest}.mp3"
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return {
                "audio": cache_path.read_bytes(),
                "mime_type": "audio/mpeg",
                "provider": "edge-tts",
                "voice": voice,
                "cached": True,
                "language": language,
            }
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, voice)
            chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    chunks.append(chunk["data"])
            audio = b"".join(chunks)
            if not audio:
                raise RuntimeError("edge-tts returned no audio")
            cache_path.write_bytes(audio)
            return {
                "audio": audio,
                "mime_type": "audio/mpeg",
                "provider": "edge-tts",
                "voice": voice,
                "cached": False,
                "language": language,
            }
        except Exception as exc:
            logger.warning("TTS failed: %s", exc)
            raise SpeechUnavailable(
                "Server-side speech synthesis is unavailable. Use the browser's Play audio fallback.",
                provider="edge-tts",
            ) from exc

    def transcribe(self, audio_bytes: bytes, filename: str = "upload.webm", language: str | None = None) -> dict[str, Any]:
        if self.asr_provider not in {"faster-whisper", "faster_whisper"}:
            raise SpeechUnavailable(
                "Server-side ASR is not configured. Use the browser microphone (Web Speech API), or type the question. "
                "To enable server ASR, install faster-whisper and set ASR_PROVIDER=faster-whisper.",
                provider=self.asr_provider,
            )
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise SpeechUnavailable(
                "faster-whisper is not installed. Install it or use the browser microphone.",
                provider="faster-whisper",
            ) from exc
        if self._whisper_model is None:
            self._whisper_model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
        suffix = Path(filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(audio_bytes)
            temp_path = handle.name
        try:
            segments, info = self._whisper_model.transcribe(
                temp_path,
                language=language if language in {"hi", "mr", "en"} else None,
                vad_filter=True,
            )
            segment_list = list(segments)
            text = " ".join(segment.text.strip() for segment in segment_list).strip()
            probabilities = [getattr(segment, "avg_logprob", -1.0) for segment in segment_list]
            avg_logprob = sum(probabilities) / len(probabilities) if probabilities else -1.0
            confidence = max(0.0, min(1.0, float(__import__("math").exp(avg_logprob))))
            return {
                "text": text,
                "language": getattr(info, "language", language or "unknown"),
                "language_probability": round(float(getattr(info, "language_probability", 0.0)), 3),
                "confidence": round(confidence, 3),
                "provider": f"faster-whisper:{settings.whisper_model}",
            }
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


def run_async(coro):
    """Small helper for scripts/tests that call the async TTS method."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
