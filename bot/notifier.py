"""Discord webhook embeds and create/edit helpers for persistent messages."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

import requests

from .parser import CalendarEvent, WIB

BOT_USERNAME = "Rachel"
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


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _plain_embed_text(value: str) -> str:
    """Defensively remove markup or Discord asset links from source text."""
    value = re.sub(r"!\[[^]]*]\([^)]*\)", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"https?://(?:cdn\.)?discord(?:app)?\.com/assets/\S+", "", value, flags=re.I)
    return " ".join(value.split())


def _activity_link(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "scele.cs.ui.ac.id" or not parsed.path.startswith("/mod/"):
        return None
    return url


def task_field(event: CalendarEvent) -> dict[str, object]:
    if not event.deadline:
        raise ValueError(f"Event {event.event_id} has no deadline")
    lines = [
        _plain_embed_text(event.course_name or "Mata kuliah tidak diketahui"),
        f"Deadline: **{format_wib(event.deadline)}**",
    ]
    activity_url = _activity_link(event.activity_url)
    if activity_url:
        lines.append(f"[Buka Tugas]({activity_url})")
    return {
        "name": f"**{_truncate(_plain_embed_text(event.assignment_title), 252)}**",
        "value": _truncate("\n".join(lines), 1024),
        "inline": False,
    }


def _embed(title: str, color: int, footer: str, fields: list[dict[str, object]], empty_text: str) -> dict[str, object]:
    embed: dict[str, object] = {"title": title, "color": color, "footer": {"text": footer}}
    if fields:
        embed["fields"] = fields
    else:
        embed["description"] = empty_text
    return embed


def _payload(embed: dict[str, object]) -> dict[str, object]:
    return {"username": BOT_USERNAME, "embeds": [embed]}


def schedule_payload(events: list[CalendarEvent]) -> dict[str, object]:
    if len(events) > 25:
        raise RuntimeError("Schedule contains more than Discord's 25 fields per embed limit.")
    return _payload(_embed(
        "📚 JADWAL TUGAS",
        SCHEDULE_COLOR,
        "SCELE Reminder • Auto Update 00.00 & 12.00 WIB",
        [task_field(event) for event in events],
        "✨ Tidak ada tugas yang ditemukan.",
    ))


def deadline_today_payload(events: list[CalendarEvent]) -> dict[str, object]:
    if len(events) > 25:
        raise RuntimeError("Deadline list contains more than Discord's 25 fields per embed limit.")
    return _payload(_embed(
        "🚨 DEADLINE HARI INI",
        DEADLINE_TODAY_COLOR,
        "⚠️ Jangan lupa dikumpulkan sebelum deadline!",
        [task_field(event) for event in events],
        "✨ Tidak ada tugas yang deadline hari ini.",
    ))


def _raise_delivery_error(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        status = getattr(exc.response, "status_code", None)
        detail = f" (HTTP {status})" if status else ""
        raise RuntimeError(f"Discord webhook delivery failed{detail}: {exc.__class__.__name__}") from exc


def create_message(webhook_url: str, payload: dict[str, object]) -> str:
    """Create a webhook message and return its Discord message ID."""
    separator = "&" if "?" in webhook_url else "?"
    try:
        response = requests.post(f"{webhook_url}{separator}wait=true", json=payload, timeout=20)
    except requests.RequestException as exc:
        raise RuntimeError(f"Discord webhook delivery failed: {exc.__class__.__name__}") from exc
    _raise_delivery_error(response)
    try:
        message_id = response.json()["id"]
    except (TypeError, ValueError, KeyError) as exc:
        raise RuntimeError("Discord webhook did not return a message ID.") from exc
    return str(message_id)


def edit_message(webhook_url: str, message_id: str, payload: dict[str, object]) -> bool:
    """Edit an existing message. Return False only when it no longer exists."""
    try:
        response = requests.patch(f"{webhook_url}/messages/{message_id}", json=payload, timeout=20)
    except requests.RequestException as exc:
        raise RuntimeError(f"Discord webhook delivery failed: {exc.__class__.__name__}") from exc
    if response.status_code == 404:
        return False
    _raise_delivery_error(response)
    return True
