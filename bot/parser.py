"""Resilient parser for the SCELE/Moodle upcoming-calendar markup."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser

WIB = ZoneInfo("Asia/Jakarta")
LOGGER = logging.getLogger(__name__)

_INDONESIAN_MONTHS = {
    "januari": "January", "februari": "February", "maret": "March",
    "april": "April", "mei": "May", "juni": "June", "juli": "July",
    "agustus": "August", "september": "September", "oktober": "October",
    "november": "November", "desember": "December",
}


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    course_id: str | None
    course_name: str | None
    course_url: str | None
    assignment_title: str
    deadline: datetime | None
    description: str | None
    activity_url: str | None
    event_type: str | None = None
    event_component: str | None = None

def _clean(value: str | None) -> str | None:
    if not value:
        return None
    result = " ".join(value.split())
    return result or None


def _plain_text(node: Tag) -> str | None:
    """Keep paragraph breaks while discarding all HTML markup."""
    blocks = node.select("p, li")
    if blocks:
        lines = [_clean(block.get_text(" ", strip=True)) for block in blocks]
    else:
        lines = [_clean(line) for line in node.get_text("\n", strip=True).splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines) or None


def _first_text(node: Tag, selectors: Iterable[str]) -> str | None:
    for selector in selectors:
        found = node.select_one(selector)
        if found:
            value = _clean(found.get_text(" ", strip=True))
            if value:
                return value
    return None


def _first_attr(node: Tag, names: Iterable[str]) -> str | None:
    for name in names:
        value = _clean(node.get(name))
        if value:
            return value
    return None


def _clean_course_name(value: str | None) -> str | None:
    value = _clean(value)
    if not value:
        return None
    return _clean(re.sub(r"^\s*\[(?:si\.)?reg\]\s*", "", value, flags=re.I))


def _clean_assignment_title(value: str) -> str:
    return re.sub(r"\s+(?:is\s+due|closes|due)\s*$", "", value, flags=re.I).strip()


def _normalise_date_text(raw: str) -> str:
    value = re.sub(r"\bPukul\b", "", raw, flags=re.I)
    value = re.sub(r"\s*,\s*", ", ", value)
    for indonesian, english in _INDONESIAN_MONTHS.items():
        value = re.sub(rf"\b{indonesian}\b", english, value, flags=re.I)
    return re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", value)


def _parse_deadline(raw: str | None, now: datetime | None = None) -> datetime | None:
    """Return a WIB datetime, including Moodle's relative Today/Tomorrow labels."""
    raw = _clean(raw)
    if not raw:
        return None
    if raw.isdigit() and len(raw) >= 9:
        return datetime.fromtimestamp(int(raw), tz=WIB)

    reference = (now or datetime.now(WIB)).astimezone(WIB)
    value = _normalise_date_text(raw)
    relative = re.match(r"^(today|hari ini|tomorrow|besok)\s*,?\s*(.*)$", value, flags=re.I)
    if relative:
        day_offset = 0 if relative.group(1).lower() in {"today", "hari ini"} else 1
        try:
            clock = date_parser.parse(relative.group(2), fuzzy=True).time()
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"unrecognised deadline {raw!r}") from exc
        return datetime.combine(reference.date(), clock, tzinfo=WIB) + timedelta(days=day_offset)

    value = re.sub(r"^(due|deadline|jatuh tempo)\s*:\s*", "", value, flags=re.I)
    try:
        parsed = date_parser.parse(
            value,
            fuzzy=True,
            default=reference.replace(tzinfo=None, second=0, microsecond=0),
        )
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"unrecognised deadline {raw!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=WIB)
    return parsed.astimezone(WIB)


def _event_nodes(soup: BeautifulSoup) -> list[Tag]:
    """Return every event container, preferring SCELE's calendar selector."""
    nodes = soup.select("div[data-type='event'][data-event-id]")
    if not nodes:
        nodes = soup.select("[data-event-id]")
    return [node for node in nodes if isinstance(node, Tag)]


def _description(node: Tag) -> str | None:
    found = node.select_one(
        ".description-content, .event-description, .description, [data-region='event-description']"
    )
    return _plain_text(found) if found else _first_attr(node, ["data-event-description"])


def _description_deadline(description: str | None) -> str | None:
    if not description:
        return None
    match = re.search(r"(?:^|\n)\s*deadline\s*:\s*([^\n]+)", description, flags=re.I)
    return _clean(match.group(1)) if match else None


def _visible_deadline(node: Tag) -> str | None:
    """Read Moodle's visible calendar date, including its unclassed first row."""
    direct = _first_text(node, [".event-date", ".date", ".deadline", ".due-date", "time"])
    if direct:
        return direct
    for row in node.select(".description.card-body > .row, .description > .row"):
        text = _clean(row.get_text(" ", strip=True))
        if text and re.search(
            r"\b(today|tomorrow|hari ini|besok)\b|\d{1,2}[:.]\d{2}|\d{1,2}\s+[A-Za-z]+|\d{4}-\d{2}-\d{2}",
            text,
            flags=re.I,
        ):
            return text
    return None


def _calendar_link_timestamp(node: Tag) -> str | None:
    """Read Moodle's canonical event time from its calendar day link."""
    for link in node.select("a[href*='/calendar/view.php'][href*='time=']"):
        time_values = parse_qs(urlparse(link.get("href", "")).query).get("time", [])
        if time_values and time_values[0].isdigit():
            return time_values[0]
    return None


def _is_opening_event(node: Tag) -> bool:
    """Opening events are calendar markers, not submission deadlines."""
    title = _first_attr(node, ["data-event-title"])
    title = title or _first_text(
        node, [".event-name", ".event-title", ".calendar-event-name", ".card-title", "h3", "h4"]
    )
    event_type = _first_attr(node, ["data-event-eventtype", "data-event-type"])
    return bool(
        (title and re.search(r"\bopens?\s*$", title, flags=re.I))
        or (event_type and event_type.casefold() == "open")
    )


def _parse_event(node: Tag, base_url: str, now: datetime | None) -> CalendarEvent:
    event_id = _first_attr(node, ["data-event-id"])
    if not event_id:
        raise ValueError("event container has no data-event-id")

    title = _first_attr(node, ["data-event-title"])
    title = title or _first_text(
        node, [".event-name", ".event-title", ".calendar-event-name", ".card-title", "h3", "h4"]
    )
    if not title:
        raise ValueError("event has no assignment title")

    course_link = node.select_one("a[href*='/course/view.php']")
    course_url = urljoin(base_url, course_link["href"]) if course_link and course_link.get("href") else None
    course_name = _clean_course_name(course_link.get_text(" ", strip=True) if course_link else None)
    course_name = course_name or _clean_course_name(_first_attr(node, ["data-course-name"]))
    course_name = course_name or _clean_course_name(
        _first_text(node, [".course-name", ".event-course", "[data-region='course-name']"])
    )

    description = _description(node)
    raw_deadline = _description_deadline(description)
    raw_deadline = raw_deadline or _first_attr(
        node, ["data-event-timestart", "data-event-time", "data-deadline", "data-due-date"]
    )
    raw_deadline = raw_deadline or _calendar_link_timestamp(node)
    if not raw_deadline:
        time_node = node.select_one("time[datetime]")
        raw_deadline = time_node.get("datetime") if time_node else None
    raw_deadline = raw_deadline or _visible_deadline(node)

    activity_url = _first_attr(node, ["data-event-url", "data-activity-url"])
    if not activity_url:
        links = node.find_all("a", href=True)
        activity = next((link for link in links if "/mod/" in link["href"]), None)
        activity = activity or next((link for link in links if link is not course_link), None)
        activity_url = activity.get("href") if activity else None

    return CalendarEvent(
        event_id=event_id,
        course_id=_first_attr(node, ["data-course-id", "data-event-course-id"]),
        course_name=course_name,
        course_url=course_url,
        assignment_title=_clean_assignment_title(title),
        deadline=_parse_deadline(raw_deadline, now),
        description=description,
        activity_url=urljoin(base_url, activity_url) if activity_url else None,
        event_type=_first_attr(node, ["data-event-eventtype", "data-event-type"]),
        event_component=_first_attr(node, ["data-event-component"]),
    )


def parse_calendar_html(
    html: str, base_url: str = "https://scele.cs.ui.ac.id/", now: datetime | None = None
) -> list[CalendarEvent]:
    """Parse valid events and log/skip malformed individual entries."""
    soup = BeautifulSoup(html, "html.parser")
    events: list[CalendarEvent] = []
    seen: set[str] = set()
    malformed = 0
    opening = 0
    nodes = _event_nodes(soup)
    LOGGER.info("Found %d raw event nodes", len(nodes))
    for node in nodes:
        if _is_opening_event(node):
            opening += 1
            continue
        try:
            event = _parse_event(node, base_url, now)
            if event.event_id in seen:
                LOGGER.warning("Skipping duplicate event id %s", event.event_id)
                continue
            seen.add(event.event_id)
            events.append(event)
        except ValueError as exc:
            malformed += 1
            LOGGER.warning("Skipping malformed event %s: %s", node.get("data-event-id", "unknown"), exc)
    LOGGER.info("Parsed %d events", len(events))
    LOGGER.info("Skipped %d malformed events", malformed)
    if opening:
        LOGGER.info("Skipped %d opening event(s)", opening)
    return events
