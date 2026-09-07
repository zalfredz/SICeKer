from datetime import datetime
from pathlib import Path

from bot.main import (
    activate,
    deadlines_today,
    enabled,
    main as run_main,
    send_tester_notifications,
    update_schedule,
    upcoming_events,
)
from bot.notifier import deadline_today_payload, schedule_payload
from bot.parser import WIB, _parse_deadline, parse_calendar_html
from bot.state import StateStore

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=WIB)


def parsed_events():
    fixture = Path(__file__).parent / "fixtures" / "upcoming_calendar.html"
    return parse_calendar_html(fixture.read_text(encoding="utf-8"), now=NOW)


def test_parses_event_course_links_titles_deadlines_and_multiple_events() -> None:
    events = parsed_events()
    assert len(events) == 4

    first = events[0]
    assert first.event_id == "112207"
    assert first.course_id == "4286"
    assert first.course_name == "Pengantar Sistem Operasi (A,B) Gasal 2026/2027"
    assert first.course_url == "https://scele.cs.ui.ac.id/course/view.php?id=4286"
    assert first.assignment_title == "Tugas 0"
    assert first.deadline == datetime(2026, 9, 7, 23, 55, tzinfo=WIB)
    assert "Format pengumpulan: File text (.txt)" in first.description
    assert first.activity_url == "https://scele.cs.ui.ac.id/mod/assign/view.php?id=221440"


def test_upcoming_sorting_and_today_filter() -> None:
    upcoming = upcoming_events(parsed_events(), NOW)
    assert [event.event_id for event in upcoming] == ["112207", "112208", "112209"]
    assert [event.event_id for event in deadlines_today(upcoming, NOW)] == ["112207", "112208"]


def test_relative_deadlines_use_wib_reference_date() -> None:
    assert _parse_deadline("Today, 23:55", NOW) == datetime(2026, 9, 7, 23, 55, tzinfo=WIB)
    assert _parse_deadline("Besok, Pukul 00.30", NOW) == datetime(2026, 9, 8, 0, 30, tzinfo=WIB)


def test_embed_payloads_have_no_avatar_and_empty_deadline_is_readable() -> None:
    upcoming = upcoming_events(parsed_events(), NOW)
    schedule = schedule_payload(upcoming)
    assert schedule["username"] == "ALz SceleReminder"
    assert "avatar_url" not in schedule
    schedule_embed = schedule["embeds"][0]
    assert schedule_embed["title"] == "📚 JADWAL TUGAS"
    assert schedule_embed["color"] == 3447003
    first_field = schedule_embed["fields"][0]
    assert first_field["name"] == "**Tugas 0**"
    assert first_field["value"].startswith("🎓 **Pengantar Sistem Operasi (A,B) Gasal 2026/2027**")
    assert "⏰ Deadline: **Senin, 7 September 2026, Pukul 23.55**" in first_field["value"]
    assert "[🔗 Buka Tugas]" in first_field["value"]
    assert "Informasi Tugas" not in first_field["value"]

    deadline = deadline_today_payload([])["embeds"][0]
    assert deadline["title"] == "🚨 DEADLINE HARI INI"
    assert deadline["description"] == "✨ Tidak ada tugas yang deadline hari ini."


def test_initial_activation_creates_two_messages_once(tmp_path: Path, monkeypatch) -> None:
    state = StateStore(tmp_path / "state.json")
    state.load()
    created: list[str] = []
    def create(_url, _payload):
        created.append("created")
        return f"message-{len(created)}"

    monkeypatch.setattr("bot.main.create_message", create)

    activate("https://example.test/webhook", state, upcoming_events(parsed_events(), NOW), NOW)

    assert state.active is True
    assert state.schedule_message_id == "message-1"
    assert state.deadline_message_id == "message-2"

    monkeypatch.setattr("bot.main.create_message", lambda *_args: (_ for _ in ()).throw(AssertionError("duplicate")))
    activate("https://example.test/webhook", state, upcoming_events(parsed_events(), NOW), NOW)


def test_schedule_update_edits_existing_message_and_recovers_missing_message(tmp_path: Path, monkeypatch) -> None:
    state = StateStore(tmp_path / "state.json")
    state.load()
    state.set_schedule_message_id("existing-schedule")
    state.activate(NOW.isoformat())

    edited: list[str] = []
    monkeypatch.setattr("bot.main.edit_message", lambda _url, message_id, _payload: edited.append(message_id) or True)
    monkeypatch.setattr("bot.main.create_message", lambda *_args: (_ for _ in ()).throw(AssertionError("should edit")))
    update_schedule("https://example.test/webhook", state, upcoming_events(parsed_events(), NOW))
    assert edited == ["existing-schedule"]

    monkeypatch.setattr("bot.main.edit_message", lambda *_args: False)
    monkeypatch.setattr("bot.main.create_message", lambda *_args: "replacement-schedule")
    update_schedule("https://example.test/webhook", state, upcoming_events(parsed_events(), NOW))
    assert state.schedule_message_id == "replacement-schedule"


def test_tester_mode_creates_preview_without_state_writes(monkeypatch) -> None:
    sent: list[dict[str, object]] = []
    monkeypatch.setattr("bot.main.create_message", lambda _url, payload: sent.append(payload) or "preview")
    upcoming = upcoming_events(parsed_events(), NOW)

    assert enabled("TESTER", "ON") is True
    assert enabled("TESTER", "off") is False
    send_tester_notifications("https://example.test/webhook", upcoming, NOW)

    assert len(sent) == 2
    assert sent[0]["embeds"][0]["title"] == "📚 JADWAL TUGAS"
    assert sent[1]["embeds"][0]["title"] == "🚨 DEADLINE HARI INI"


def test_inactive_bot_skips_fetch_and_discord(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"active": false}', encoding="utf-8")
    monkeypatch.setenv("STATE_FILE", str(state_path))
    monkeypatch.setenv("TESTER", "OFF")
    monkeypatch.setenv("ACTIVATE", "OFF")
    monkeypatch.setattr(
        "bot.main.SceleClient",
        lambda *_args: (_ for _ in ()).throw(AssertionError("inactive bot must not fetch")),
    )

    run_main()
