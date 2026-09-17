"""Inbound messages "heard" by the platform.

Two sources feed the same queue:
  - lines typed into this process's stdin (handy for manual testing)
  - transcripts pushed by rnk_agent.speech_pipeline.SpeechPipeline, backed by
    real audio streamed from the rnk-rpi (extracted from the platform's
    camera for now) and run through VAD + local STT

Either way, the agent is told these messages come from the platform's
microphone, so no prompt wording needs to change based on the source.
"""

from __future__ import annotations

import queue
import sys
import threading


class MicrophoneInputChannel:
    """Collects incoming messages on a background thread, non-blocking to poll()."""

    def __init__(self):
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        for line in sys.stdin:
            text = line.strip()
            if text:
                self._queue.put(text)

    def push(self, text: str) -> None:
        """Enqueue a message as if it had been typed/heard, e.g. an STT transcript."""
        text = text.strip()
        if text:
            self._queue.put(text)

    def poll(self) -> list[str]:
        """Return, and clear, any messages received since the last poll."""
        messages: list[str] = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return messages

