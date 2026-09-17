"""Config loading for rnk-agent.

Reads config.yaml (falls back to config.example.yaml if it doesn't exist
yet, so a fresh checkout still runs) and exposes it as plain dataclasses.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"
EXAMPLE_CONFIG_PATH = REPO_ROOT / "config.example.yaml"


@dataclass
class PlatformConfig:
    base_url: str = "http://192.168.1.20:5000"
    request_timeout_s: float = 10.0
    snapshot_scaled: bool = True
    poll_interval_s: float = 0.5
    poll_timeout_s: float = 60.0


@dataclass
class TTSConfig:
    """Local speech synthesis (macOS `say`), used by PlatformClient.say()."""

    # empty = macOS's default system voice
    voice: str = ""
    # words per minute; None = macOS's default rate
    rate: int | None = None
    timeout_s: float = 30.0


@dataclass
class LLMConfig:
    base_url: str = "http://localhost:1234/v1"
    model: str = "auto"
    api_key: str = "lm-studio"
    temperature: float = 0.2
    max_tokens: int = 600
    request_timeout_s: float = 120.0


@dataclass
class AudioStreamConfig:
    """Continuous raw-PCM audio feed from the rnk-rpi (see rnk-rpi's
    app/audio/capture_constants.py - sample_rate/channels/sample_width must
    match what's configured there)."""

    host: str = "192.168.1.20"
    port: int = 5001
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2
    connect_timeout_s: float = 5.0
    reconnect_interval_s: float = 2.0
    recv_bytes: int = 4096


@dataclass
class VADConfig:
    """Speech start/end detection over the continuous audio feed, see
    rnk_agent.speech_segmenter."""

    # webrtcvad aggressiveness: 0 (least aggressive, more false positives)
    # .. 3 (most aggressive) - 3 filters out background noise (footsteps,
    # appliance humming, ...) much better than lower settings
    aggressiveness: int = 3
    frame_ms: int = 20
    # rolling buffer kept before speech is detected, so an utterance keeps
    # the audio right before it was flagged as speech
    pre_roll_ms: int = 300
    # consecutive speech-classified audio needed to trigger an utterance start
    # - kept generous so brief noise bursts (a footstep, a door) don't start one
    speech_start_ms: int = 300
    # minimum loudness (dBFS, 0 = full scale) for a frame to ever count as
    # speech, regardless of what webrtcvad says - filters out quiet but
    # broadband background noise (appliance humming, etc.) a sensitive mic
    # picks up. Raise (toward 0) if quiet noise still triggers false starts;
    # lower (more negative) if quiet speech is being ignored.
    min_speech_dbfs: float = -40.0
    # consecutive silence needed to finalize an utterance - keep this
    # generous enough that a short mid-sentence pause doesn't cut it short
    silence_hangover_ms: int = 800
    # safety cap so a single utterance can't grow unbounded
    max_utterance_s: float = 30.0


@dataclass
class STTConfig:
    """Local speech-to-text, see rnk_agent.stt."""

    engine: str = "faster-whisper"
    model_size: str = "base"
    # "ru", "en", ... or "" to auto-detect
    language: str = "ru"
    device: str = "cpu"
    compute_type: str = "int8"


@dataclass
class LoopConfig:
    interval_s: float = 1.0
    # extra pause after a ptz_absolute/ptz_relative/ptz_home action, on top of
    # interval_s - the platform reports "not moving" a bit before the camera
    # has actually visually settled, so the next snapshot can still be stale
    camera_settle_extra_s: float = 1.0
    max_iterations: int = 0
    log_dir: str = "logs"
    # where todo.json / observations.json (agent scratch state) are persisted
    state_dir: str = "state"
    system_prompt_path: str = "prompts/system_prompt.txt"
    # sub-prompts for the %%TODO%%/%%OBSERVATIONS%%/%%CAMERA%%/%%TIME%%
    # placeholders in system_prompt_path - each is substituted with its
    # rendered section, or "" if that section has nothing to show
    todo_section_path: str = "prompts/sections/todo.txt"
    observations_section_path: str = "prompts/sections/observations.txt"
    camera_section_path: str = "prompts/sections/camera.txt"
    time_section_path: str = "prompts/sections/time.txt"


@dataclass
class AppConfig:
    platform: PlatformConfig = field(default_factory=PlatformConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    loop: LoopConfig = field(default_factory=LoopConfig)
    audio_stream: AudioStreamConfig = field(default_factory=AudioStreamConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    stt: STTConfig = field(default_factory=STTConfig)


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or DEFAULT_CONFIG_PATH

    if not config_path.exists():
        if EXAMPLE_CONFIG_PATH.exists():
            shutil.copy(EXAMPLE_CONFIG_PATH, config_path)
            print(f"No config.yaml found - created one from config.example.yaml at {config_path}")
        else:
            raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f) or {}

    return AppConfig(
        tts=TTSConfig(**raw.get("tts", {})),
        platform=PlatformConfig(**raw.get("platform", {})),
        llm=LLMConfig(**raw.get("llm", {})),
        loop=LoopConfig(**raw.get("loop", {})),
        audio_stream=AudioStreamConfig(**raw.get("audio_stream", {})),
        vad=VADConfig(**raw.get("vad", {})),
        stt=STTConfig(**raw.get("stt", {})),
    )
