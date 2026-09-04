"""The actual perceive -> decide -> act loop."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rnk_agent.config import AppConfig
from rnk_agent.llm_client import LLMClient, LLMError
from rnk_agent.notes import NoteError, ObservationsNotebook, TodoList
from rnk_agent.platform_client import PlatformClient, PlatformError

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

VALID_ACTIONS = {
    "move",
    "rotate",
    "ptz_absolute",
    "ptz_relative",
    "ptz_home",
    "todo_add",
    "todo_check",
    "todo_uncheck",
    "todo_remove",
    "observation_add",
    "observation_overwrite",
    "observation_remove",
    "noop",
}


class ActionParseError(RuntimeError):
    pass


def parse_action(raw_text: str) -> dict[str, Any]:
    """Best-effort extraction of the {"reasoning", "action", "params"} object
    from the model's raw reply (tolerates ```json fences or stray prose)."""
    text = raw_text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            raise ActionParseError(f"No JSON object found in model output: {raw_text!r}")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ActionParseError(f"Could not parse JSON from model output: {exc}") from exc

    if "action" not in data:
        raise ActionParseError(f"Model output is missing 'action': {data!r}")
    if data["action"] not in VALID_ACTIONS:
        raise ActionParseError(f"Unknown action {data['action']!r}, expected one of {VALID_ACTIONS}")
    data.setdefault("params", {})
    data.setdefault("reasoning", "")
    return data


def execute_action(
    platform: PlatformClient,
    todo: TodoList,
    notebook: ObservationsNotebook,
    action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    if action == "move":
        result = platform.move(float(params["cm"]))
        platform.wait_until_idle()
        return result
    if action == "rotate":
        result = platform.rotate(float(params["deg"]))
        platform.wait_until_idle()
        return result
    if action == "ptz_absolute":
        result = platform.camera_ptz_absolute(
            pan=float(params["pan"]), tilt=float(params["tilt"]), zoom=params.get("zoom")
        )
        platform.wait_until_camera_idle()
        return result
    if action == "ptz_relative":
        result = platform.camera_ptz_relative(
            pan=float(params["pan"]), tilt=float(params["tilt"]), zoom=params.get("zoom")
        )
        platform.wait_until_camera_idle()
        return result
    if action == "ptz_home":
        result = platform.camera_home()
        platform.wait_until_camera_idle()
        return result
    if action == "todo_add":
        item = todo.add(str(params["text"]))
        return {"status": "ok", "id": item.id}
    if action == "todo_check":
        item = todo.check(int(params["id"]))
        return {"status": "ok", "id": item.id, "checked": item.checked}
    if action == "todo_uncheck":
        item = todo.uncheck(int(params["id"]))
        return {"status": "ok", "id": item.id, "checked": item.checked}
    if action == "todo_remove":
        todo.remove(int(params["id"]))
        return {"status": "ok"}
    if action == "observation_add":
        entry = notebook.add(str(params["name"]), str(params["text"]))
        return {"status": "ok", "name": entry.name}
    if action == "observation_overwrite":
        entry = notebook.overwrite(str(params["name"]), str(params["text"]))
        return {"status": "ok", "name": entry.name}
    if action == "observation_remove":
        notebook.remove(str(params["name"]))
        return {"status": "ok"}
    if action == "noop":
        return {"status": "noop"}
    raise ActionParseError(f"Unknown action {action!r}")


def _build_user_text(iteration: int, last_action: dict[str, Any] | None, last_result: str) -> str:
    lines = [f"Step {iteration}."]
    if last_action is None:
        lines.append("This is the first step - there is no previous action yet.")
    else:
        lines.append(f"Previous action: {json.dumps(last_action)}")
        lines.append(f"Previous action result: {last_result}")
    lines.append("Decide the next single action and respond with only the JSON object.")
    return "\n".join(lines)


def _build_system_prompt(
    base_prompt: str,
    todo: TodoList,
    notebook: ObservationsNotebook,
    current_time: str,
    previous_step_time: str | None,
) -> str:
    lines = [
        base_prompt.rstrip(),
        "",
        "--- Live state (auto-generated, refreshed every step) ---",
        f"Current time (UTC): {current_time}",
        f"Previous step time (UTC): {previous_step_time or 'N/A - this is the first step'}",
        "",
        todo.render(),
        "",
        notebook.render(),
    ]
    return "\n".join(lines)


def run_loop(config: AppConfig) -> None:
    platform = PlatformClient(config.platform)
    llm = LLMClient(config.llm)

    system_prompt_path = Path(config.loop.system_prompt_path)
    if not system_prompt_path.is_absolute():
        system_prompt_path = Path(__file__).resolve().parent.parent / system_prompt_path
    base_system_prompt = system_prompt_path.read_text()

    log_dir = Path(config.loop.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    state_dir = Path(config.loop.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    todo = TodoList(state_dir / "todo.json")
    notebook = ObservationsNotebook(state_dir / "observations.json")

    model = llm.resolve_model()
    print(f"Using LLM model: {model}")
    print(f"Platform: {config.platform.base_url}")

    previous_frame = platform.camera_snapshot()
    last_action: dict[str, Any] | None = None
    last_result = ""
    previous_step_time: str | None = None

    iteration = 0
    while True:
        iteration += 1
        if config.loop.max_iterations and iteration > config.loop.max_iterations:
            print("Reached max_iterations, stopping.")
            break

        current_frame = platform.camera_snapshot()
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%dT%H%M%S%fZ")
        current_time = now.isoformat(timespec="seconds")
        (log_dir / f"{ts}_step{iteration:04d}.jpg").write_bytes(current_frame)

        user_text = _build_user_text(iteration, last_action, last_result)
        system_prompt = _build_system_prompt(base_system_prompt, todo, notebook, current_time, previous_step_time)

        print(f"\n=== Step {iteration} ===")
        try:
            raw_reply = llm.chat(system_prompt, user_text, previous_frame, current_frame)
        except LLMError as exc:
            print(f"[llm error] {exc}")
            time.sleep(config.loop.interval_s)
            continue

        try:
            action_obj = parse_action(raw_reply)
        except ActionParseError as exc:
            print(f"[parse error] {exc}")
            last_action = None
            last_result = f"error: could not parse previous reply ({exc})"
            previous_frame = current_frame
            time.sleep(config.loop.interval_s)
            continue

        print(f"reasoning: {action_obj['reasoning']}")
        print(f"action: {action_obj['action']} params: {action_obj['params']}")

        try:
            result = execute_action(platform, todo, notebook, action_obj["action"], action_obj["params"])
            last_result = f"ok: {json.dumps(result)[:500]}"
        except (PlatformError, NoteError, KeyError, TypeError, ValueError) as exc:
            print(f"[action error] {exc}")
            last_result = f"error: {exc}"

        last_action = action_obj
        previous_frame = current_frame
        previous_step_time = current_time

        time.sleep(config.loop.interval_s)
