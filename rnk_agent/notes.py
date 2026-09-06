"""Agent-writable scratch state: a todo list and a dated observations notebook.

Both are plain JSON-backed so they survive process restarts, and both know
how to render themselves as text for inclusion in the system prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NoteError(RuntimeError):
    """Raised for invalid todo/observation operations (bad id, duplicate name, ...)."""


@dataclass
class TodoItem:
    id: int
    text: str
    checked: bool = False


class TodoList:
    def __init__(self, path: Path | None = None):
        self._path = path
        self._items: dict[int, TodoItem] = {}
        self._next_id = 1
        if self._path and self._path.exists():
            self._load()

    def add(self, text: str) -> TodoItem:
        item = TodoItem(id=self._next_id, text=text, checked=False)
        self._items[item.id] = item
        self._next_id += 1
        self._save()
        return item

    def check(self, item_id: int) -> TodoItem:
        return self._set_checked(item_id, True)

    def uncheck(self, item_id: int) -> TodoItem:
        return self._set_checked(item_id, False)

    def remove(self, item_id: int) -> None:
        if item_id not in self._items:
            raise NoteError(f"No todo item with id {item_id}")
        del self._items[item_id]
        self._save()

    def render_items(self) -> str:
        """Render just the item list ([x]/[ ] + text per id), or "" if empty."""
        if not self._items:
            return ""
        lines = []
        for item in sorted(self._items.values(), key=lambda i: i.id):
            box = "x" if item.checked else " "
            lines.append(f"  {item.id}. [{box}] {item.text}")
        return "\n".join(lines)

    def _set_checked(self, item_id: int, checked: bool) -> TodoItem:
        item = self._items.get(item_id)
        if item is None:
            raise NoteError(f"No todo item with id {item_id}")
        item.checked = checked
        self._save()
        return item

    def _save(self) -> None:
        if not self._path:
            return
        payload = {
            "next_id": self._next_id,
            "items": [
                {"id": i.id, "text": i.text, "checked": i.checked}
                for i in sorted(self._items.values(), key=lambda i: i.id)
            ],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2))

    def _load(self) -> None:
        data = json.loads(self._path.read_text())
        self._next_id = data.get("next_id", 1)
        for raw in data.get("items", []):
            item = TodoItem(id=raw["id"], text=raw["text"], checked=raw["checked"])
            self._items[item.id] = item


@dataclass
class Observation:
    name: str
    text: str
    created_at: str
    updated_at: str


class ObservationsNotebook:
    def __init__(self, path: Path | None = None):
        self._path = path
        self._entries: dict[str, Observation] = {}
        if self._path and self._path.exists():
            self._load()

    def add(self, name: str, text: str) -> Observation:
        if name in self._entries:
            raise NoteError(f"An observation named {name!r} already exists - use observation_overwrite instead")
        now = _now_iso()
        entry = Observation(name=name, text=text, created_at=now, updated_at=now)
        self._entries[name] = entry
        self._save()
        return entry

    def overwrite(self, name: str, text: str) -> Observation:
        now = _now_iso()
        existing = self._entries.get(name)
        entry = Observation(name=name, text=text, created_at=existing.created_at if existing else now, updated_at=now)
        self._entries[name] = entry
        self._save()
        return entry

    def remove(self, name: str) -> None:
        if name not in self._entries:
            raise NoteError(f"No observation named {name!r}")
        del self._entries[name]
        self._save()

    def render_items(self) -> str:
        """Render just the entry list (name/timestamps/text), or "" if empty."""
        if not self._entries:
            return ""
        lines = []
        for entry in sorted(self._entries.values(), key=lambda e: e.name):
            lines.append(f"  [{entry.name}] (created {entry.created_at}, updated {entry.updated_at}):")
            lines.append(f"    {entry.text}")
        return "\n".join(lines)

    def _save(self) -> None:
        if not self._path:
            return
        payload = {
            name: {"text": e.text, "created_at": e.created_at, "updated_at": e.updated_at}
            for name, e in self._entries.items()
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2))

    def _load(self) -> None:
        data = json.loads(self._path.read_text())
        for name, raw in data.items():
            self._entries[name] = Observation(
                name=name, text=raw["text"], created_at=raw["created_at"], updated_at=raw["updated_at"]
            )
