"""Cute, compact Discord embed payloads for SCELE reminders."""

from __future__ import annotations

import os
import re
from datetime import datetime

import requests

from .parser import CalendarEvent, WIB

BOT_USERNAME = "ALz SceleReminder"
SCHEDULE_COLOR = 3447003
DEADLINE_TODAY_COLOR = 15158332
_DAYS = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
_MONTHS = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)


def format_wib(deadline: datetime) -> str:
    value = deadline.astimezone(WIB)
    return f"{_DAYS[value.weekday()]}, {value.day} {_MONTHS[value.month - 1]} {value.year}, Pukul {value:%H.%M}"


def _identity() -> dict[str, object]:
    payload: dict[str, object] = {"username": BOT_USERNAME}
    avatar_url = os.environ.get("DISCORD_AVATAR_URL")
    if avatar_url:
        payload["avatar_url"] = avatar_url
    return payload


def _additional_information(description: str | None) -> str | None:
    if not description:
        return None
    useful_lines = [
        line.strip()
        for line in description.splitlines()
        if line.strip() and not re.match(r"^deadline\s*:", line.strip(), flags=re.I)
    ]
    return "\n".join(useful_lines) or None


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def task_field(event: CalendarEvent, include_information: bool = False) -> dict[str, object]:
    if not event.deadline:
        raise ValueError(f"Event {event.event_id} has no deadline")
    course_name = _truncate(event.course_name or "Mata kuliah tidak diketahui", 253)
    lines = [
        f"**{event.assignment_title}**",
        f"⏰ Deadline: **{format_wib(event.deadline)}**",
    ]
    if event.activity_url:
        lines.append(f"[🔗 Buka Tugas]({event.activity_url})")
    if include_information:
        information = _additional_information(event.description)
        if information:
            lines.extend(("", "📝 **Informasi Tugas**", information))
    return {
        "name": f"🎓 {course_name}",
        "value": _truncate("\n".join(lines), 1024),
        "inline": False,
    }


def schedule_payload(events: list[CalendarEvent]) -> dict[str, object]:
    if len(events) > 25:
        raise RuntimeError("Schedule contains more than Discord's 25 fields per embed limit.")
    embed: dict[str, object] = {
        "title": "📚 JADWAL TUGAS",
        "color": SCHEDULE_COLOR,
        "footer": {"text": "SCELE Reminder • Auto Update 12.00 & 00.00 WIB"},
    }
    if events:
        embed["fields"] = [task_field(event) for event in events]
    else:
        embed["description"] = "Tidak ada tugas yang masih memiliki deadline."
    payload = _identity()
    payload["embeds"] = [embed]
    return payload


def deadline_today_payload(event: CalendarEvent) -> dict[str, object]:
    payload = _identity()
    payload["embeds"] = [{
        "title": "🚨 DEADLINE HARI INI",
        "color": DEADLINE_TODAY_COLOR,
        "fields": [task_field(event, include_information=True)],
        "footer": {"text": "⚠️ Jangan lupa dikumpulkan sebelum deadline!"},
    }]
    return payload


def send_payload(webhook_url: str, payload: dict[str, object]) -> None:
    try:
        response = requests.post(webhook_url, json=payload, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        # The webhook URL contains its secret token; never interpolate it into logs.
        status = getattr(exc.response, "status_code", None)
        detail = f" (HTTP {status})" if status else ""
        raise RuntimeError(f"Discord webhook delivery failed{detail}: {exc.__class__.__name__}") from exc
