"""Activation and fixed-time updates for persistent SCELE Discord messages."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from dotenv import load_dotenv

from .notifier import create_message, deadline_today_payload, edit_message, schedule_payload
from .parser import CalendarEvent, WIB, parse_calendar_html
from .scraper import SceleClient
from .state import StateStore

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)

# Manual notification exclusions. Add normalized course names here as needed.
# The parser removes prefixes such as [Reg] and [SI.Reg] before this comparison.
UN_NOTIF = {
    "Kalkulus 1 (A,B,C,D,E,F,G,H) Gasal 2026/2027",
}


def upcoming_events(events: list[CalendarEvent], now: datetime) -> list[CalendarEvent]:
    return sorted(
        (
            event
            for event in events
            if event.deadline
            and event.deadline > now
            and event.course_name not in UN_NOTIF
        ),
        key=lambda event: event.deadline,
    )


def deadlines_today(events: list[CalendarEvent], now: datetime) -> list[CalendarEvent]:
    today = now.astimezone(WIB).date()
    return sorted(
        (event for event in events if event.deadline and event.deadline.astimezone(WIB).date() == today),
        key=lambda event: event.deadline,
    )


def enabled(name: str, value: str | None) -> bool:
    normalized = (value or "OFF").strip().upper()
    if normalized not in {"ON", "OFF"}:
        raise RuntimeError(f"{name} must be ON or OFF.")
    return normalized == "ON"


SCHEDULE_UPDATE_KINDS = {
    # 00.07, 00.22, 00.37, and 00.52 WIB: schedule retries.
    "7 17 * * *": "schedule",
    "22 17 * * *": "schedule",
    "37 17 * * *": "schedule",
    "52 17 * * *": "schedule",
    # 10.07, 10.22, 10.37, and 10.52 WIB: deadline-today retries.
    "7 3 * * *": "deadline",
    "22 3 * * *": "deadline",
    "37 3 * * *": "deadline",
    "52 3 * * *": "deadline",
    # 12.07, 12.22, 12.37, and 12.52 WIB: schedule retries.
    "7 5 * * *": "schedule",
    "22 5 * * *": "schedule",
    "37 5 * * *": "schedule",
    "52 5 * * *": "schedule",
}


def scheduled_update_kind(schedule_trigger: str | None) -> str | None:
    """Return the update type from GitHub's triggering cron expression.

    GitHub-hosted runners can start late, so the runner's current clock must
    not decide which scheduled update is due.
    """
    return SCHEDULE_UPDATE_KINDS.get((schedule_trigger or "").strip())


def fetch_upcoming(now: datetime) -> list[CalendarEvent]:
    LOGGER.info("Fetching SCELE calendar")
    html = SceleClient(os.environ.get("SCELE_USERNAME"), os.environ.get("SCELE_PASSWORD")).fetch_calendar()
    events = parse_calendar_html(html, now=now)
    upcoming = upcoming_events(events, now)
    LOGGER.info("Upcoming %d events", len(upcoming))
    LOGGER.info("Deadline today: %d", len(deadlines_today(upcoming, now)))
    return upcoming


def ensure_message(
    webhook_url: str,
    message_id: str | None,
    payload: dict[str, object],
    label: str,
) -> str:
    """Edit the message if it exists; create a replacement after a 404."""
    if message_id:
        LOGGER.info("Updating %s message", label)
        if edit_message(webhook_url, message_id, payload):
            LOGGER.info("%s message updated", label.capitalize())
            return message_id
        LOGGER.warning("%s message was not found; creating replacement", label.capitalize())
    else:
        LOGGER.info("Creating %s message", label)
    new_id = create_message(webhook_url, payload)
    LOGGER.info("%s message created", label.capitalize())
    return new_id


def activate(webhook_url: str, state: StateStore, upcoming: list[CalendarEvent], now: datetime) -> None:
    """Create the two persistent messages, then mark the bot active."""
    if state.active:
        LOGGER.info("Bot already active. No activation message sent.")
        return

    schedule_id = ensure_message(webhook_url, state.schedule_message_id, schedule_payload(upcoming), "schedule")
    if schedule_id != state.schedule_message_id:
        state.set_schedule_message_id(schedule_id)
        state.save()

    due_today = deadlines_today(upcoming, now)
    deadline_id = ensure_message(
        webhook_url, state.deadline_message_id, deadline_today_payload(due_today), "deadline"
    )
    if deadline_id != state.deadline_message_id:
        state.set_deadline_message_id(deadline_id)
        state.save()

    state.activate(now.astimezone(WIB).isoformat())
    state.save()
    LOGGER.info("Bot activated")


def update_schedule(webhook_url: str, state: StateStore, upcoming: list[CalendarEvent]) -> None:
    message_id = ensure_message(webhook_url, state.schedule_message_id, schedule_payload(upcoming), "schedule")
    if message_id != state.schedule_message_id:
        state.set_schedule_message_id(message_id)
        state.save()


def update_deadline(webhook_url: str, state: StateStore, upcoming: list[CalendarEvent], now: datetime) -> None:
    due_today = deadlines_today(upcoming, now)
    message_id = ensure_message(
        webhook_url, state.deadline_message_id, deadline_today_payload(due_today), "deadline"
    )
    if message_id != state.deadline_message_id:
        state.set_deadline_message_id(message_id)
        state.save()


def _webhook_url() -> str:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is required.")
    return webhook_url


def main() -> None:
    load_dotenv()
    now = datetime.now(WIB)
    is_activate = enabled("ACTIVATE", os.environ.get("ACTIVATE"))
    is_manual_update = enabled("MANUAL_UPDATE", os.environ.get("MANUAL_UPDATE"))
    if is_activate and is_manual_update:
        raise RuntimeError("ACTIVATE and MANUAL_UPDATE cannot be ON together.")

    state = StateStore(os.environ.get("STATE_FILE", "state.json"))
    state.load()

    if is_activate:
        if state.active:
            LOGGER.info("Bot already active. No activation message sent.")
            return
        activate(_webhook_url(), state, fetch_upcoming(now), now)
        return

    if not state.active:
        LOGGER.info("Bot inactive. Skipping update.")
        return

    if is_manual_update:
        LOGGER.info("MANUAL UPDATE: ON")
        upcoming = fetch_upcoming(now)
        webhook_url = _webhook_url()
        update_schedule(webhook_url, state, upcoming)
        update_deadline(webhook_url, state, upcoming, now)
        LOGGER.info("Manual update complete")
        return

    kind = scheduled_update_kind(os.environ.get("SCHEDULE_TRIGGER"))
    if kind is None:
        LOGGER.info("No scheduled update trigger. Skipping manual production update.")
        return

    upcoming = fetch_upcoming(now)
    if kind == "schedule":
        update_schedule(_webhook_url(), state, upcoming)
    else:
        update_deadline(_webhook_url(), state, upcoming, now)
    LOGGER.info("Done")


if __name__ == "__main__":
    main()
