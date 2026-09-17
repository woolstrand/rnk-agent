"""TCP client for the continuous raw-PCM audio feed streamed by rnk-rpi.

Runs on a background thread, fully independent of the model/action loop
(agent_loop.run_loop) - it just keeps pushing received bytes into a
callback for as long as the process runs. Reconnects automatically if the
Pi is unreachable or drops the connection, logging connection status
changes to stdout so it's visible in the agent's console output.
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
                    self._on_chunk(chunk)
            finally:
                print(
                    f"[audio] disconnected from {self._config.host}:{self._config.port} "
                    f"({bytes_received} bytes received)"
                )
