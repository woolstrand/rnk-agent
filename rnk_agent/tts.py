"""Local text-to-speech via macOS's built-in `say` command.

Deliberately dependency-free (no pip package, no network call): `say` ships
with macOS, so this only works when rnk-agent runs on a Mac - which matches
how it's deployed (see README). Playback happens elsewhere, on the rnk-rpi
(see PlatformClient.say / rnk-rpi's POST /rnk/audio/play).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from rnk_agent.config import TTSConfig


class TTSError(RuntimeError):
    """Raised when speech synthesis fails or isn't available."""


def synthesize(text: str, config: TTSConfig) -> bytes:
    """Render `text` to AIFF audio bytes using the macOS `say` command."""
    if not text.strip():
        raise TTSError("text is empty")

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "speech.aiff"
        command = ["say", "-o", str(out_path)]
        if config.voice:
            command += ["-v", config.voice]
        if config.rate:
            command += ["-r", str(config.rate)]
        command.append(text)

        try:
            result = subprocess.run(command, capture_output=True, timeout=config.timeout_s)
        except FileNotFoundError as exc:
            raise TTSError("'say' is not available (rnk-agent's TTS only works on macOS)") from exc
        except subprocess.TimeoutExpired as exc:
            raise TTSError(f"'say' timed out after {config.timeout_s}s") from exc

        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise TTSError(f"'say' failed: {detail or f'exit code {result.returncode}'}")

        data = out_path.read_bytes()
        if not data:
            raise TTSError("'say' produced an empty audio file")
        return data
