"""Speech start/end segmentation over a continuous raw-PCM audio feed.

Maintains a bounded pre-roll buffer and a webrtcvad-based state machine:
speech "starts" once enough consecutive frames are classified as speech
(the retained pre-roll is prepended so the utterance keeps its leading
edge), and only "ends" once enough consecutive silence has passed - a
short pause mid-sentence does not cut an utterance short. Runs entirely
off of fed-in audio chunks; independent of the model/action loop.

webrtcvad itself has no volume/loudness threshold - it's a spectral
classifier, so quiet-but-broadband noise (appliance humming, footsteps)
can still be misread as speech. A simple minimum-loudness (dBFS) gate runs
ahead of it: frames quieter than ``min_speech_dbfs`` are never treated as
speech, no matter what the VAD says.
"""

from __future__ import annotations

import collections
import math
import time
from typing import Callable

import numpy as np
import webrtcvad

from rnk_agent.config import AudioStreamConfig, VADConfig

#: minimum gap between "too quiet" diagnostic prints, so a sustained quiet
#: noise doesn't spam the console once per 20ms frame
_GATE_LOG_INTERVAL_S = 1.0
#: how often to print the current ambient loudness while idle, so the real
#: baseline level is visible even when webrtcvad never flags anything at all
_AMBIENT_LOG_INTERVAL_S = 5.0


def _dbfs(frame: bytes) -> float:
    """RMS loudness of a 16-bit PCM frame, in dBFS (0 = full scale)."""
    samples = np.frombuffer(frame, dtype=np.int16)
    rms = math.sqrt(float(np.mean(samples.astype(np.float64) ** 2)))
    if rms <= 0:
        return -math.inf
    return 20 * math.log10(rms / 32768.0)


class SpeechSegmenter:
    def __init__(
        self,
        vad_config: VADConfig,
        stream_config: AudioStreamConfig,
        on_utterance: Callable[[bytes], None],
    ):
        self._config = vad_config
        self._sample_rate = stream_config.sample_rate
        self._on_utterance = on_utterance

        self._frame_bytes = (
            stream_config.sample_rate
            * vad_config.frame_ms
            // 1000
            * stream_config.sample_width
            * stream_config.channels
        )
        self._vad = webrtcvad.Vad(vad_config.aggressiveness)

        pre_roll_frames = max(1, vad_config.pre_roll_ms // vad_config.frame_ms)
        self._pre_roll: collections.deque[bytes] = collections.deque(maxlen=pre_roll_frames)
        self._buffer = bytearray()
        self._speech_frames: list[bytes] = []
        self._in_speech = False
        self._speech_run_ms = 0
        self._silence_run_ms = 0
        self._utterance_ms = 0
        self._last_gate_log_ts = 0.0
        self._last_ambient_log_ts = 0.0

    def feed(self, chunk: bytes) -> None:
        """Accept an arbitrary-sized chunk of raw PCM, sliced into fixed VAD frames."""
        self._buffer.extend(chunk)
        while len(self._buffer) >= self._frame_bytes:
            frame = bytes(self._buffer[: self._frame_bytes])
            del self._buffer[: self._frame_bytes]
            self._process_frame(frame)

    def _process_frame(self, frame: bytes) -> None:
        vad_says_speech = self._vad.is_speech(frame, self._sample_rate)
        frame_dbfs = _dbfs(frame)
        is_speech = vad_says_speech and frame_dbfs >= self._config.min_speech_dbfs

        if vad_says_speech and not is_speech:
            now = time.monotonic()
            if now - self._last_gate_log_ts >= _GATE_LOG_INTERVAL_S:
                self._last_gate_log_ts = now
                print(
                    f"[speech] VAD flagged speech-like audio but it's too quiet "
                    f"({frame_dbfs:.1f} dBFS < min_speech_dbfs={self._config.min_speech_dbfs})"
                )

        if not self._in_speech:
            now = time.monotonic()
            if now - self._last_ambient_log_ts >= _AMBIENT_LOG_INTERVAL_S:
                self._last_ambient_log_ts = now
                print(f"[speech] ambient level: {frame_dbfs:.1f} dBFS, vad_speech={vad_says_speech}")
            self._pre_roll.append(frame)
            self._speech_run_ms = self._speech_run_ms + self._config.frame_ms if is_speech else 0
            if self._speech_run_ms >= self._config.speech_start_ms:
                print("[speech] speech started")
                self._in_speech = True
                self._speech_frames = list(self._pre_roll)
                self._pre_roll.clear()
                self._silence_run_ms = 0
                self._utterance_ms = len(self._speech_frames) * self._config.frame_ms
            return

        self._speech_frames.append(frame)
        self._utterance_ms += self._config.frame_ms
        self._silence_run_ms = 0 if is_speech else self._silence_run_ms + self._config.frame_ms

        if (
            self._silence_run_ms >= self._config.silence_hangover_ms
            or self._utterance_ms >= self._config.max_utterance_s * 1000
        ):
            self._finalize()

    def _finalize(self) -> None:
        audio = b"".join(self._speech_frames)
        print(f"[speech] speech ended ({self._utterance_ms} ms)")
        self._in_speech = False
        self._speech_frames = []
        self._speech_run_ms = 0
        self._silence_run_ms = 0
        self._utterance_ms = 0
        self._pre_roll.clear()
        if audio:
            self._on_utterance(audio)
