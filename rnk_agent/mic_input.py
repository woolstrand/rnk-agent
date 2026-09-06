"""Inbound messages "heard" by the platform.

For now this reads free-text lines typed into this process's stdin on the
laptop. Later the same interface should be backed by STT transcripts pushed
from the rnk-rpi's onboard microphone instead - the agent is already told
these messages come from the platform's microphone, so no prompt wording
needs to change when the real source is swapped in.
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

    def poll(self) -> list[str]:
        """Return, and clear, any messages received since the last poll."""
        messages: list[str] = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return messages
