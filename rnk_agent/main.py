"""Entry point: `python -m rnk_agent.main` (or `python main.py` from the repo root)."""

from __future__ import annotations

import argparse
from pathlib import Path

from rnk_agent.agent_loop import run_loop
from rnk_agent.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="rnk-agent: agentic control loop for the robot platform")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to ./config.yaml, created from config.example.yaml if missing)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    try:
        run_loop(config)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
