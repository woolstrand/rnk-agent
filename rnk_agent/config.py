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
class LLMConfig:
    base_url: str = "http://localhost:1234/v1"
    model: str = "auto"
    api_key: str = "lm-studio"
    temperature: float = 0.2
    max_tokens: int = 600
    request_timeout_s: float = 120.0


@dataclass
class LoopConfig:
    interval_s: float = 1.0
    max_iterations: int = 0
    log_dir: str = "logs"
    # where todo.json / observations.json (agent scratch state) are persisted
    state_dir: str = "state"
    system_prompt_path: str = "prompts/system_prompt.txt"


@dataclass
class AppConfig:
    platform: PlatformConfig = field(default_factory=PlatformConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    loop: LoopConfig = field(default_factory=LoopConfig)


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
        platform=PlatformConfig(**raw.get("platform", {})),
        llm=LLMConfig(**raw.get("llm", {})),
        loop=LoopConfig(**raw.get("loop", {})),
    )
