"""Small, versioned state for the two persistent Discord messages."""

from __future__ import annotations

import json
from pathlib import Path


class StateError(RuntimeError):
    pass


class StateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, object] = self._default()

    @staticmethod
    def _default() -> dict[str, object]:
        return {
            "active": False,
            "activated_at": None,
            "schedule_message_id": None,
            "deadline_message_id": None,
        }

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(f"Could not read state file {self.path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise StateError(f"State file {self.path} must contain a JSON object.")
        self.data = self._default()
        self.data["active"] = loaded.get("active") is True
        for key in ("activated_at", "schedule_message_id", "deadline_message_id"):
            value = loaded.get(key)
            self.data[key] = str(value) if value is not None else None

    @property
    def active(self) -> bool:
        return self.data["active"] is True

    @property
    def schedule_message_id(self) -> str | None:
        value = self.data.get("schedule_message_id")
        return str(value) if value is not None else None

    @property
    def deadline_message_id(self) -> str | None:
        value = self.data.get("deadline_message_id")
        return str(value) if value is not None else None

    def set_schedule_message_id(self, message_id: str) -> None:
        self.data["schedule_message_id"] = message_id

    def set_deadline_message_id(self, message_id: str) -> None:
        self.data["deadline_message_id"] = message_id

    def activate(self, activated_at: str) -> None:
        self.data["active"] = True
        self.data["activated_at"] = activated_at

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
