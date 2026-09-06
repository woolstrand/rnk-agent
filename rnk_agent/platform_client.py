"""Thin HTTP client for the rnk-rpi API (see the rnk-server/api_docs README).

Kept deliberately dumb: one method per endpoint, no retry/backoff magic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from rnk_agent.config import PlatformConfig


class PlatformError(RuntimeError):
    """Raised when the rnk-rpi API returns an error or is unreachable."""


@dataclass
class ScheduleResult:
    raw: dict[str, Any]


class PlatformClient:
    def __init__(self, config: PlatformConfig):
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._timeout = config.request_timeout_s

    # -- low level -----------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            resp = requests.request(method, url, timeout=self._timeout, **kwargs)
        except requests.RequestException as exc:
            raise PlatformError(f"{method} {path} failed: {exc}") from exc

        if not resp.ok:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            raise PlatformError(f"{method} {path} -> {resp.status_code}: {detail}")

        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return {}

    # -- motion ----------------------------------------------------------

    def move(self, cm: float) -> dict[str, Any]:
        return self._request("POST", "/rnk/schedule", json={"move": cm})

    def rotate(self, deg: float) -> dict[str, Any]:
        return self._request("POST", "/rnk/schedule", json={"rotate": deg})

    def schedule_status(self) -> dict[str, Any]:
        return self._request("GET", "/rnk/schedule")

    def wait_until_idle(self) -> dict[str, Any]:
        """Poll GET /rnk/schedule until the queue is empty and nothing is running."""
        deadline = time.monotonic() + self._config.poll_timeout_s
        status = self.schedule_status()
        while status.get("busy") and time.monotonic() < deadline:
            time.sleep(self._config.poll_interval_s)
            status = self.schedule_status()
        return status

    # -- camera ------------------------------------------------------------

    def camera_ptz_absolute(self, pan: float, tilt: float, zoom: float | None = None) -> dict[str, Any]:
        # this camera's hardware pans opposite to the documented convention
        # (positive pan = look right) - negate here so callers/prompt stay correct
        payload: dict[str, Any] = {"pan": -pan, "tilt": tilt}
        if zoom is not None:
            payload["zoom"] = zoom
        return self._request("POST", "/rnk/camera/ptz/absolute", json=payload)

    def camera_ptz_relative(self, pan: float, tilt: float, zoom: float | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"pan": -pan, "tilt": tilt}
        if zoom is not None:
            payload["zoom"] = zoom
        return self._request("POST", "/rnk/camera/ptz/relative", json=payload)

    def camera_ptz_stop(self) -> dict[str, Any]:
        return self._request("POST", "/rnk/camera/ptz/stop")

    def camera_home(self) -> dict[str, Any]:
        return self._request("POST", "/rnk/camera/home", json={})

    def camera_status(self) -> dict[str, Any]:
        return self._request("GET", "/rnk/camera/status")

    def wait_until_camera_idle(self) -> dict[str, Any]:
        deadline = time.monotonic() + self._config.poll_timeout_s
        status = self.camera_status()
        while status.get("moving") and time.monotonic() < deadline:
            time.sleep(self._config.poll_interval_s)
            status = self.camera_status()
        return status

    def camera_snapshot(self) -> bytes:
        url = f"{self._base_url}/rnk/camera/snapshot"
        params = {"scaled": "true"} if self._config.snapshot_scaled else {}
        try:
            resp = requests.get(url, params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            raise PlatformError(f"GET /rnk/camera/snapshot failed: {exc}") from exc
        if not resp.ok:
            raise PlatformError(f"GET /rnk/camera/snapshot -> {resp.status_code}: {resp.text}")
        return resp.content

    # -- speech ------------------------------------------------------------

    def say(self, text: str, volume: float) -> dict[str, Any]:
        """Speak through the platform's speaker.

        TODO: no rpi API endpoint for this yet - once one exists, replace the
        log line below with a POST like the other methods above.
        """
        print(f"[SAY] volume={volume} text={text!r}")
        return {"status": "ok", "text": text, "volume": volume}

