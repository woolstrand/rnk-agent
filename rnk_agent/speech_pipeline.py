"""Wires the continuous audio feed, VAD-based utterance segmentation, and
local STT into a background pipeline that is fully independent of the
model/action loop's iteration cadence (see agent_loop.run_loop).

Audio flows: AudioStreamClient (socket) -> SpeechSegmenter.feed() (per
chunk received) -> finalized utterances are queued -> a dedicated worker
thread runs STT on each and hands the resulting transcript to
``on_transcript`` (typically MicrophoneInputChannel.push), so a slow
transcription never blocks the live audio feed or the model loop.
"""

from __future__ import annotations

import queue
import threading
from typing import Callable, Optional

from rnk_agent.audio_stream_client import AudioStreamClient
from rnk_agent.config import AudioStreamConfig, STTConfig, VADConfig
from rnk_agent.speech_segmenter import SpeechSegmenter
from rnk_agent.stt import STTError, SpeechToText, WhisperSTT


class SpeechPipeline:
    def __init__(
        self,
        stream_config: AudioStreamConfig,
        vad_config: VADConfig,
        stt_config: STTConfig,
        on_transcript: Callable[[str], None],
        stt: Optional[SpeechToText] = None,
    ):
        self._stream_config = stream_config
        self._on_transcript = on_transcript
        self._stt = stt or WhisperSTT(stt_config)

        self._utterances: "queue.Queue[bytes]" = queue.Queue()
        self._segmenter = SpeechSegmenter(vad_config, stream_config, on_utterance=self._utterances.put)
        self._client = AudioStreamClient(stream_config, on_chunk=self._segmenter.feed)

        self._stop_event = threading.Event()
        self._stt_thread = threading.Thread(target=self._stt_loop, name="rnk-stt", daemon=True)

    def start(self) -> None:
        self._stt_thread.start()
        self._client.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._client.stop()

    def _stt_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                audio = self._utterances.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                text = self._stt.transcribe(audio, self._stream_config.sample_rate)
            except STTError as exc:
                print(f"[stt error] {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - must not kill this thread permanently
                print(f"[stt error] unexpected error: {exc}")
                continue
            if text:
                print(f'[speech] heard: "{text}"')
                self._on_transcript(text)
            else:
                print("[speech] utterance had no recognizable speech, discarding")
