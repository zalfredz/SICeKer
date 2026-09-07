"""Entrypoint for fixed-time SCELE schedule notifications."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from dotenv import load_dotenv

from .notifier import deadline_today_payload, schedule_payload, send_payload
from .parser import CalendarEvent, WIB, parse_calendar_html
from .scraper import SceleClient
from .state import StateStore

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)


def upcoming_events(events: list[CalendarEvent], now: datetime) -> list[CalendarEvent]:
    """Keep only future deadlines and order them from nearest to furthest."""
    return sorted(
        (event for event in events if event.deadline and event.deadline > now),
        key=lambda event: event.deadline,
    )


def deadlines_today(events: list[CalendarEvent], now: datetime) -> list[CalendarEvent]:
    today = now.astimezone(WIB).date()
    return [event for event in events if event.deadline and event.deadline.astimezone(WIB).date() == today]


def schedule_slot(now: datetime) -> str:
    """Identifier for the fixed 00.00/12.00 WIB schedule, not elapsed time."""
    local = now.astimezone(WIB)
    hour = 0 if local.hour < 6 else 12
    return local.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def tester_enabled(value: str | None) -> bool:
    normalized = (value or "OFF").strip().upper()
    if normalized not in {"ON", "OFF"}:
        raise RuntimeError("TESTER must be ON or OFF.")
    return normalized == "ON"


def send_tester_notifications(webhook_url: str, upcoming: list[CalendarEvent], now: datetime) -> None:
    """Send production-format payloads without touching production state."""
    LOGGER.info("Sending TEST notification")
    send_payload(webhook_url, schedule_payload(upcoming))
    LOGGER.info("Test schedule notification sent successfully")
    for event in deadlines_today(upcoming, now):
        LOGGER.info("Sending TEST deadline notification for event %s", event.event_id)
        send_payload(webhook_url, deadline_today_payload(event))
        LOGGER.info("Test deadline notification sent successfully")


def main() -> None:
    # GitHub Actions secrets override an optional local .env file.
    load_dotenv()
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is required.")

    now = datetime.now(WIB)
    is_tester = tester_enabled(os.environ.get("TESTER"))
    LOGGER.info("TESTER MODE: %s", "ON" if is_tester else "OFF")

    LOGGER.info("Fetching SCELE calendar")
    html = SceleClient(os.environ.get("SCELE_USERNAME"), os.environ.get("SCELE_PASSWORD")).fetch_calendar()
    events = parse_calendar_html(html, now=now)
    LOGGER.info("Found %d events", len(events))
    upcoming = upcoming_events(events, now)
    LOGGER.info("%d upcoming assignments", len(upcoming))
    due_today = deadlines_today(upcoming, now)
    LOGGER.info("%d deadline today", len(due_today))

    if is_tester:
        send_tester_notifications(webhook_url, upcoming, now)
        LOGGER.info("Done")
        return

    state = StateStore(os.environ.get("STATE_FILE", "state.json"))
    state.load()
    slot = schedule_slot(now)
    if state.schedule_sent_for(slot):
        LOGGER.info("Schedule for this fixed WIB slot was already sent")
    else:
        LOGGER.info("Sending schedule notification")
        send_payload(webhook_url, schedule_payload(upcoming))
        state.mark_schedule_sent(slot)
        state.save()

    today = now.date().isoformat()
    for event in due_today:
        if state.deadline_today_sent(event.event_id, today):
            continue
        LOGGER.info("Sending deadline notification for event %s", event.event_id)
        send_payload(webhook_url, deadline_today_payload(event))
        state.mark_deadline_today_sent(event.event_id, today)
        # Persist each success so a later failed delivery does not duplicate it.
        state.save()
    LOGGER.info("Done")


if __name__ == "__main__":
    main()
