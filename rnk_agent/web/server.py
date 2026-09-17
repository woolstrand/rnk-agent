"""Read-only Flask app that serves rnk-agent's per-step JSON/JPEG records
(written by agent_loop.run_loop under `loop.log_dir`) to the dashboard UI.

Runs two ways:
  - embedded: `run_dashboard()` is started in a daemon thread by run_loop()
    while the agent is live.
  - standalone: `python -m rnk_agent.web.server --log-dir logs` serves the
    same files after the fact, with no agent process required.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from flask import Flask, abort, jsonify, send_from_directory

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(log_dir: Path) -> Flask:
    log_dir = Path(log_dir)
    steps_dir = log_dir / "steps"

    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/api/steps")
    def list_steps():
        steps = []
        for path in sorted(steps_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            steps.append({"iteration": data.get("iteration"), "timestamp": data.get("timestamp")})
        steps.sort(key=lambda s: s["iteration"] if s["iteration"] is not None else -1)
        return jsonify(steps)

    @app.get("/api/steps/<int:iteration>")
    def get_step(iteration: int):
        matches = sorted(steps_dir.glob(f"{iteration:05d}_*.json"))
        if not matches:
            abort(404)
        return jsonify(json.loads(matches[-1].read_text()))

    @app.get("/api/frames/<path:relpath>")
    def get_frame(relpath: str):
        return send_from_directory(log_dir, relpath)

    return app


def run_dashboard(log_dir: Path, host: str, port: int) -> None:
    create_app(log_dir).run(host=host, port=port, threaded=True, use_reloader=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone viewer for rnk-agent step logs")
    parser.add_argument("--log-dir", type=Path, default=Path("logs"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    print(f"Serving dashboard for {args.log_dir} at http://{args.host}:{args.port}")
    run_dashboard(args.log_dir, args.host, args.port)


if __name__ == "__main__":
    main()
