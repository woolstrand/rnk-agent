"""TCP client for the continuous raw-PCM audio feed streamed by rnk-rpi.

Runs on a background thread, fully independent of the model/action loop
(agent_loop.run_loop) - it just keeps pushing received bytes into a
callback for as long as the process runs. Reconnects automatically if the
Pi is unreachable or drops the connection, logging connection status
changes to stdout so it's visible in the agent's console output.

Both the reconnect loop and the per-chunk callback are guarded against
arbitrary exceptions (not just socket/OSError failures) so a single bad
chunk or a downstream processing bug can never permanently kill this
thread - it always keeps retrying.
"""

from __future__ import annotations

import socket
import threading
from typing import Callable

from rnk_agent.config import AudioStreamConfig


class AudioStreamClient:
    def __init__(self, config: AudioStreamConfig, on_chunk: Callable[[bytes], None]):
        self._config = config
        self._on_chunk = on_chunk
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="rnk-audio-stream", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._connect_and_stream()
            except OSError as exc:
                print(
                    f"[audio] could not connect to {self._config.host}:{self._config.port} "
                    f"({exc}); retrying in {self._config.reconnect_interval_s:.0f}s"
                )
            except Exception as exc:  # noqa: BLE001 - must never permanently kill this thread
                print(
                    f"[audio] unexpected error in audio stream ({exc!r}); "
                    f"retrying in {self._config.reconnect_interval_s:.0f}s"
                )
            if not self._stop_event.is_set():
                self._stop_event.wait(self._config.reconnect_interval_s)

    def _connect_and_stream(self) -> None:
        with socket.create_connection(
            (self._config.host, self._config.port), timeout=self._config.connect_timeout_s
        ) as sock:
            print(f"[audio] connected to {self._config.host}:{self._config.port}")
            sock.settimeout(1.0)
            bytes_received = 0
            first_chunk = True
            try:
                while not self._stop_event.is_set():
                    try:
                        chunk = sock.recv(self._config.recv_bytes)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    if first_chunk:
                        print("[audio] receiving audio data from the platform")
                        first_chunk = False
                    bytes_received += len(chunk)
                    try:
                        self._on_chunk(chunk)
                    except Exception as exc:  # noqa: BLE001 - a bad chunk must not drop the connection
                        print(f"[audio] error processing audio chunk: {exc!r}")
            finally:
                print(
                    f"[audio] disconnected from {self._config.host}:{self._config.port} "
                    f"({bytes_received} bytes received)"
                )
