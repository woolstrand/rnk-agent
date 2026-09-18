"""Client for LM Studio's local server.

Model listing still uses the OpenAI-compatible GET /v1/models (see
resolve_model), but chat turns go through LM Studio's native POST
/api/v1/chat, which reports reasoning-model "thinking" output as separate
output items instead of folding it into the message text.

We talk to it with plain `requests` (no `openai`/`lmstudio` SDK dependency).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import requests

from rnk_agent.config import LLMConfig


class LLMError(RuntimeError):
    pass


@dataclass
class ChatResponse:
    text: str
    # the model's internal "thinking" output, if the model/reasoning setting
    # produced one - kept separate from `text` so it never leaks into the
    # parsed action JSON or next step's "previous actions" context, but is
    # still available to log for debugging
    reasoning: str


def _frame_input_items(jpeg_bytes: bytes | None, label: str) -> list[dict[str, Any]]:
    """``jpeg_bytes`` is None when the camera snapshot failed this step - fall
    back to a text-only notice so the model knows vision is offline rather
    than silently getting one less image than expected."""
    if jpeg_bytes is None:
        return [{"type": "text", "content": f"{label} unavailable - camera offline this step."}]
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    return [
        {"type": "text", "content": label},
        {"type": "image", "data_url": f"data:image/jpeg;base64,{b64}"},
    ]


class LLMClient:
    def __init__(self, config: LLMConfig):
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._model = config.model

    def _api_root(self) -> str:
        """Host root for LM Studio's native REST API (/api/v1/*) - independent of
        the OpenAI-compat base_url (.../v1) used for model listing."""
        root = self._base_url
        if root.endswith("/v1"):
            root = root[: -len("/v1")]
        return root

    def resolve_model(self) -> str:
        """If config says "auto", ask LM Studio for the first loaded model."""
        if self._model and self._model.lower() != "auto":
            return self._model

        url = f"{self._base_url}/models"
        try:
            resp = requests.get(url, timeout=self._config.request_timeout_s)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise LLMError(
                f"Could not reach LM Studio at {url} to auto-detect a model: {exc}. "
                "Is the LM Studio local server running (Developer tab -> Start Server) "
                "with a model loaded? Or set llm.model in config.yaml explicitly."
            ) from exc

        data = resp.json().get("data", [])
        if not data:
            raise LLMError(
                "LM Studio returned no models from /v1/models. Load a model in LM "
                "Studio first, or set llm.model in config.yaml explicitly."
            )
        self._model = data[0]["id"]
        return self._model

    def chat(
        self,
        system_prompt: str,
        user_text: str,
        previous_frame_jpeg: bytes | None,
        current_frame_jpeg: bytes | None,
    ) -> ChatResponse:
        """Send one turn (system prompt + text + up to two images) via LM
        Studio's native /api/v1/chat and return the assistant's reply text
        plus any separate reasoning/"thinking" output. Either frame may be
        None if the camera snapshot failed that step (see _frame_input_items)."""
        model = self.resolve_model()

        input_items: list[dict[str, Any]] = [{"type": "text", "content": user_text}]
        input_items += _frame_input_items(previous_frame_jpeg, "Previous frame:")
        input_items += _frame_input_items(current_frame_jpeg, "Current frame:")

        payload = {
            "model": model,
            "input": input_items,
            "system_prompt": system_prompt,
            "temperature": self._config.temperature,
            "max_output_tokens": self._config.max_tokens,
            # we replay our own history via system_prompt/user_text each step,
            # so there's no need for LM Studio to keep a server-side chat around
            "store": False,
        }

        url = f"{self._api_root()}/api/v1/chat"
        try:
            resp = requests.post(url, json=payload, timeout=self._config.request_timeout_s)
        except requests.RequestException as exc:
            raise LLMError(f"POST {url} failed: {exc}") from exc

        if not resp.ok:
            raise LLMError(f"POST {url} -> {resp.status_code}: {resp.text}")

        body = resp.json()
        output = body.get("output")
        if not isinstance(output, list):
            raise LLMError(f"Unexpected LM Studio response shape: {body}")

        text = "\n".join(item.get("content", "") for item in output if item.get("type") == "message").strip()
        reasoning = "\n".join(item.get("content", "") for item in output if item.get("type") == "reasoning").strip()
        if not text:
            raise LLMError(f"LM Studio response had no message output: {body}")
        return ChatResponse(text=text, reasoning=reasoning)
