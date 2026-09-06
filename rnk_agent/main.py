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
    parser.add_argument(
        "--reset-todo",
        action="store_true",
        help="Clear the persisted todo list (state/todo.json) before starting",
    )
    parser.add_argument(
        "--reset-observations",
        action="store_true",
        help="Clear the persisted observations notebook (state/observations.json) before starting",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    state_dir = Path(config.loop.state_dir)
    if args.reset_todo:
        todo_path = state_dir / "todo.json"
        todo_path.unlink(missing_ok=True)
        print(f"Cleared todo list ({todo_path})")
    if args.reset_observations:
        observations_path = state_dir / "observations.json"
        observations_path.unlink(missing_ok=True)
        print(f"Cleared observations notebook ({observations_path})")

    try:
        run_loop(config)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
