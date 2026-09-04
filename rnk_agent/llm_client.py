"""Minimal client for LM Studio's OpenAI-compatible local server.

We talk to it with plain `requests` (no `openai` SDK dependency) since all
we need is POST /v1/chat/completions and GET /v1/models.
"""

from __future__ import annotations

import base64
from typing import Any

import requests

from rnk_agent.config import LLMConfig


class LLMError(RuntimeError):
    pass


def _image_content_part(jpeg_bytes: bytes, label: str) -> list[dict[str, Any]]:
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    return [
        {"type": "text", "text": label},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
    ]


class LLMClient:
    def __init__(self, config: LLMConfig):
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._model = config.model

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
        previous_frame_jpeg: bytes,
        current_frame_jpeg: bytes,
    ) -> str:
        """Send one turn (system prompt + text + two images) and return the raw
        assistant text content."""
        model = self.resolve_model()

        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        content += _image_content_part(previous_frame_jpeg, "Previous frame:")
        content += _image_content_part(current_frame_jpeg, "Current frame:")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }

        url = f"{self._base_url}/chat/completions"
        try:
            resp = requests.post(url, json=payload, timeout=self._config.request_timeout_s)
        except requests.RequestException as exc:
            raise LLMError(f"POST {url} failed: {exc}") from exc

        if not resp.ok:
            raise LLMError(f"POST {url} -> {resp.status_code}: {resp.text}")

        body = resp.json()
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected LM Studio response shape: {body}") from exc
