"""Local speech-to-text, pluggable behind the SpeechToText interface.

WhisperSTT (faster-whisper, running entirely locally/offline) is the only
implementation for now, but any other engine can be dropped in later as
long as it implements transcribe(pcm, sample_rate) -> str - nothing else in
the speech pipeline depends on faster-whisper directly.
"""

from __future__ import annotations

import abc

from rnk_agent.config import STTConfig


class STTError(RuntimeError):
    """Raised when transcription fails or the engine isn't available."""


class SpeechToText(abc.ABC):
    @abc.abstractmethod
    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        """Transcribe raw mono 16-bit signed-LE PCM audio to text.

        Returns "" if no speech could be made out.
        """


class WhisperSTT(SpeechToText):
    """faster-whisper (CTranslate2): runs entirely locally, no network calls.

    The model is loaded lazily, on first use, so importing this module (and
    starting the rest of the agent) doesn't pay the load cost or require
    faster-whisper to be installed unless speech input is actually used.
    """

    def __init__(self, config: STTConfig):
        self._config = config
        self._model = None

    def _model_instance(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise STTError(
                    "faster-whisper is not installed (pip install -r requirements.txt)"
                ) from exc
            print(
                f"[stt] loading whisper model '{self._config.model_size}' "
                f"(first use downloads it from Hugging Face and can take a while)..."
            )
            self._model = WhisperModel(
                self._config.model_size,
                device=self._config.device,
                compute_type=self._config.compute_type,
            )
            print("[stt] model loaded")
        return self._model

    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        if not pcm:
            return ""

        try:
            import numpy as np

            audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _ = self._model_instance().transcribe(
                audio, language=self._config.language or None
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
        except STTError:
            raise
        except Exception as exc:  # faster-whisper doesn't expose a narrower error type
            raise STTError(f"transcription failed: {exc}") from exc
