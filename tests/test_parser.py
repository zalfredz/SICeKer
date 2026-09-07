from datetime import datetime
from pathlib import Path

from bot.main import deadlines_today, send_tester_notifications, tester_enabled as is_tester_enabled, upcoming_events
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
    assert first.description.startswith("Deadline : Senin, 7 September 2026, Pukul 23.55")
    assert "Format pengumpulan: File text (.txt)" in first.description
    assert first.activity_url == "https://scele.cs.ui.ac.id/mod/assign/view.php?id=221440"

    second = events[1]
    assert second.course_name.startswith("Pemrograman Berbasis Platform")
    assert second.assignment_title == "Tugas 1"


def test_upcoming_sorting_and_today_filter() -> None:
    events = parsed_events()
    upcoming = upcoming_events(events, NOW)
    assert [event.event_id for event in upcoming] == ["112207", "112208", "112209"]
    assert [event.event_id for event in deadlines_today(upcoming, NOW)] == ["112207", "112208"]
    assert "112210" not in [event.event_id for event in upcoming]


def test_relative_deadlines_use_wib_reference_date() -> None:
    assert _parse_deadline("Today, 23:55", NOW) == datetime(2026, 9, 7, 23, 55, tzinfo=WIB)
    assert _parse_deadline("Besok, Pukul 00.30", NOW) == datetime(2026, 9, 8, 0, 30, tzinfo=WIB)


def test_discord_embed_payloads_without_sending_webhook(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_AVATAR_URL", "https://example.test/avatar.png")
    events = parsed_events()
    upcoming = upcoming_events(events, NOW)
    schedule = schedule_payload(upcoming)
    assert schedule["username"] == "ALz SceleReminder"
    assert schedule["avatar_url"] == "https://example.test/avatar.png"
    embed = schedule["embeds"][0]
    assert embed["title"] == "📚 JADWAL TUGAS"
    assert embed["color"] == 3447003
    assert embed["footer"]["text"] == "SCELE Reminder • Auto Update 12.00 & 00.00 WIB"
    first_field, second_field = embed["fields"][:2]
    assert first_field["name"] == "🎓 Pengantar Sistem Operasi (A,B) Gasal 2026/2027"
    assert "**Tugas 0**" in first_field["value"]
    assert "⏰ Deadline: **Senin, 7 September 2026, Pukul 23.55**" in first_field["value"]
    assert "[🔗 Buka Tugas](https://scele.cs.ui.ac.id/mod/assign/view.php?id=221440)" in first_field["value"]
    assert first_field["inline"] is False
    assert "Tugas 1" in second_field["value"]

    deadline = deadline_today_payload(upcoming[0])["embeds"][0]
    assert deadline["title"] == "🚨 DEADLINE HARI INI"
    assert deadline["color"] == 15158332
    assert deadline["footer"]["text"] == "⚠️ Jangan lupa dikumpulkan sebelum deadline!"
    assert "📝 **Informasi Tugas**" in deadline["fields"][0]["value"]
    assert "Deadline :" not in deadline["fields"][0]["value"]


def test_state_prevents_duplicate_deadline_today(tmp_path: Path) -> None:
    state = StateStore(tmp_path / "state.json")
    state.load()
    assert not state.deadline_today_sent("112207", "2026-09-07")
    state.mark_deadline_today_sent("112207", "2026-09-07")
    state.mark_schedule_sent("2026-09-07T12:00:00+07:00")
    state.save()

    reread = StateStore(tmp_path / "state.json")
    reread.load()
    assert reread.deadline_today_sent("112207", "2026-09-07")
    assert not reread.deadline_today_sent("112207", "2026-09-08")
    assert reread.schedule_sent_for("2026-09-07T12:00:00+07:00")


def test_tester_mode_sends_production_payloads_without_state(monkeypatch) -> None:
    events = upcoming_events(parsed_events(), NOW)
    sent: list[dict[str, object]] = []
    monkeypatch.setattr("bot.main.send_payload", lambda _url, payload: sent.append(payload))

    assert is_tester_enabled("ON") is True
    assert is_tester_enabled("off") is False
    send_tester_notifications("https://example.test/webhook", events, NOW)

    assert len(sent) == 3  # One schedule plus two assignments due today.
    assert sent[0]["embeds"][0]["title"] == "📚 JADWAL TUGAS"
    assert sent[1]["embeds"][0]["title"] == "🚨 DEADLINE HARI INI"
