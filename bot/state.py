"""JSON notification state persisted by a GitHub Actions commit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast


class StateError(RuntimeError):
    pass


class StateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, object] = {}

    def load(self) -> None:
        if not self.path.exists():
            self.data = {"schedule_last_sent": None, "events": {}}
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(f"Could not read state file {self.path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise StateError(f"State file {self.path} must contain a JSON object.")
        events = loaded.get("events", {})
        self.data = {
            "schedule_last_sent": loaded.get("schedule_last_sent"),
            "events": events if isinstance(events, dict) else {},
        }

    def schedule_sent_for(self, slot: str) -> bool:
        return self.data.get("schedule_last_sent") == slot

    def mark_schedule_sent(self, slot: str) -> None:
        self.data["schedule_last_sent"] = slot

    def deadline_today_sent(self, event_id: str, date: str) -> bool:
        event = self._events().get(event_id, {})
        return isinstance(event, dict) and event.get("deadline_today_sent") == date

    def mark_deadline_today_sent(self, event_id: str, date: str) -> None:
        self._events().setdefault(event_id, {})["deadline_today_sent"] = date

    def _events(self) -> dict[str, dict[str, str]]:
        events = self.data.get("events")
        if not isinstance(events, dict):
            events = {}
            self.data["events"] = events
        return cast(dict[str, dict[str, str]], events)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
