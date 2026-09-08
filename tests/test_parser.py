import logging
from datetime import datetime, timedelta
from pathlib import Path

from bot.main import (
    activate,
    deadlines_today,
    enabled,
    main as run_main,
    scheduled_update_kind,
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


def generated_calendar_html(
    count: int,
    malformed_indexes: set[int] | None = None,
    past_count: int = 0,
    today_count: int = 0,
) -> str:
    """Create arbitrary-sized calendar markup without production count assumptions."""
    malformed_indexes = malformed_indexes or set()
    events: list[str] = []
    for index in range(count):
        if index < past_count:
            deadline = "2026-09-06 23:55"
        elif index < past_count + today_count:
            deadline = f"2026-09-07 {10 + index:02d}:55"
        else:
            deadline = (NOW + timedelta(days=index + 1)).strftime("%Y-%m-%d 23:55")
        title = "" if index in malformed_indexes else f' data-event-title="Task {index} is due"'
        component = "mod_quiz" if index % 2 else "mod_assign"
        events.append(
            f'<div data-type="event" data-event-id="dynamic-{index}" data-course-id="{index}"{title} '
            f'data-event-component="{component}"><a href="/course/view.php?id={index}">[Reg] Course {index}</a>'
            f'<div class="description"><p>Deadline : {deadline}</p></div>'
            f'<a href="/mod/assign/view.php?id={index}">Buka tugas</a></div>'
        )
    return "<html><body>" + "".join(events) + "</body></html>"


def test_parses_event_course_links_titles_deadlines_and_multiple_events() -> None:
    events = parsed_events()
    assert len(events) == 6
    assert len({event.event_id for event in events}) == len(events)
    assert [event.assignment_title for event in events] == [
        "Tugas 0",
        "Tugas 1",
        "Checkpoint 01: Analisis Algoritma",
        "Kuis Partisipasi Pekan Ketiga PBP C",
        "Tugas Individu 1 - Sistem Bilangan, Fungsi, dan Limit",
        "Pengumpulan Tugas Individu 1",
    ]

    first = events[0]
    assert first.event_id == "112207"
    assert first.course_id == "4286"
    assert first.course_name == "Pengantar Sistem Operasi (A,B) Gasal 2026/2027"
    assert first.course_url == "https://scele.cs.ui.ac.id/course/view.php?id=4286"
    assert first.assignment_title == "Tugas 0"
    assert first.deadline == datetime(2026, 9, 7, 23, 55, tzinfo=WIB)
    assert "Format pengumpulan: File text (.txt)" in first.description
    assert first.activity_url == "https://scele.cs.ui.ac.id/mod/assign/view.php?id=221440"
    quiz = next(event for event in events if event.event_component == "mod_quiz")
    assert quiz.assignment_title == "Kuis Partisipasi Pekan Ketiga PBP C"
    assert quiz.deadline == datetime(2026, 9, 13, 23, 59, tzinfo=WIB)


def test_upcoming_sorting_and_today_filter() -> None:
    upcoming = upcoming_events(parsed_events(), NOW)
    assert len(upcoming) == 5
    assert "112209" not in [event.event_id for event in upcoming]
    assert [event.event_id for event in deadlines_today(upcoming, NOW)] == ["112207", "112208", "112211"]


def test_sorting_uses_deadline_not_html_input_order() -> None:
    events = parsed_events()
    shuffled = [events[4], events[1], events[5], events[0], events[3], events[2]]
    upcoming = upcoming_events(shuffled, NOW)
    assert [event.event_id for event in upcoming] == ["112207", "112208", "112211", "112212", "112213"]
    today = deadlines_today(list(reversed(upcoming)), NOW)
    assert today[0].event_id == "112207"
    assert {event.event_id for event in today[1:]} == {"112208", "112211"}

    varied_hours = parse_calendar_html(generated_calendar_html(4, today_count=4), now=NOW)
    sorted_today = deadlines_today(list(reversed(varied_hours)), NOW)
    assert [event.deadline.hour for event in sorted_today] == [10, 11, 12, 13]


def test_relative_deadlines_use_wib_reference_date() -> None:
    assert _parse_deadline("Today, 23:55", NOW) == datetime(2026, 9, 7, 23, 55, tzinfo=WIB)
    assert _parse_deadline("Besok, Pukul 00.30", NOW) == datetime(2026, 9, 8, 0, 30, tzinfo=WIB)


def test_parses_moodle_card_date_rows_without_deadline_description() -> None:
    html = """
    <div data-type="event" data-event-id="row-today" data-event-title="Tugas 1 is due" data-event-component="mod_assign">
      <div class="description card-body"><div class="row"><div class="col-11">Today , 23:59</div></div></div>
      <a href="/course/view.php?id=1">[Reg] Course 1</a><a href="/mod/assign/view.php?id=1">Buka</a>
    </div>
    <div data-type="event" data-event-id="row-date" data-event-title="Quiz closes" data-event-component="mod_quiz">
      <div class="description card-body"><div class="row"><div class="col-11">Sunday, 13 September , 23:59</div></div></div>
      <a href="/course/view.php?id=2">[SI.Reg] Course 2</a><a href="/mod/quiz/view.php?id=2">Buka</a>
    </div>
    """
    events = parse_calendar_html(html, now=NOW)
    assert [(event.assignment_title, event.deadline) for event in events] == [
        ("Tugas 1", datetime(2026, 9, 7, 23, 59, tzinfo=WIB)),
        ("Quiz", datetime(2026, 9, 13, 23, 59, tzinfo=WIB)),
    ]


def test_calendar_day_link_timestamp_is_used_before_relative_date_text() -> None:
    timestamp = int(datetime(2026, 9, 8, 17, 0, tzinfo=WIB).timestamp())
    html = f"""
    <div data-type="event" data-event-id="timestamp-event" data-event-title="Checkpoint closes">
      <div class="description card-body"><div class="row"><div class="col-11">
        <a href="/calendar/view.php?view=day&amp;time={timestamp}">Tomorrow</a>, 09:00
      </div></div></div>
      <a href="/course/view.php?id=1">Course</a><a href="/mod/quiz/view.php?id=1">Buka</a>
    </div>
    """
    event = parse_calendar_html(html, now=NOW)[0]
    assert event.deadline == datetime(2026, 9, 8, 17, 0, tzinfo=WIB)


def test_opening_events_are_not_parsed_as_deadlines(caplog) -> None:
    caplog.set_level(logging.INFO, logger="bot.parser")
    html = """
    <div data-type="event" data-event-id="opening" data-event-title="Checkpoint 02 opens"
         data-event-eventtype="open">
      <a href="/course/view.php?id=1">Course</a><a href="/mod/quiz/view.php?id=1">Buka</a>
      <div class="description"><p>Deadline : 2026-09-08 17:00</p></div>
    </div>
    <div data-type="event" data-event-id="closing" data-event-title="Checkpoint 02 closes"
         data-event-eventtype="close">
      <a href="/course/view.php?id=1">Course</a><a href="/mod/quiz/view.php?id=1">Buka</a>
      <div class="description"><p>Deadline : 2026-09-16 23:59</p></div>
    </div>
    """
    events = parse_calendar_html(html, now=NOW)
    assert [event.event_id for event in events] == ["closing"]
    assert "Skipped 1 opening event(s)" in caplog.text


def test_parser_logs_raw_and_parsed_event_counts(caplog) -> None:
    caplog.set_level(logging.INFO, logger="bot.parser")
    parsed_events()
    assert "Found 6 raw event nodes" in caplog.text
    assert "Parsed 6 events" in caplog.text
    assert "Skipped 0 malformed events" in caplog.text


def test_parser_is_dynamic_for_one_six_ten_and_zero_events() -> None:
    for raw_count in (1, 6, 10, 0):
        events = parse_calendar_html(generated_calendar_html(raw_count), now=NOW)
        assert len(events) == raw_count


def test_malformed_events_are_skipped_without_stopping_collection(caplog) -> None:
    caplog.set_level(logging.INFO, logger="bot.parser")
    events = parse_calendar_html(generated_calendar_html(10, {3, 8}), now=NOW)
    assert len(events) == 8
    assert "Found 10 raw event nodes" in caplog.text
    assert "Skipped 2 malformed events" in caplog.text


def test_upcoming_and_today_filters_keep_all_matching_events() -> None:
    events = parse_calendar_html(generated_calendar_html(10, past_count=3, today_count=4), now=NOW)
    upcoming = upcoming_events(events, NOW)
    assert len(upcoming) == 7
    assert len(deadlines_today(upcoming, NOW)) == 4


def test_thirty_upcoming_events_are_split_across_embeds_without_loss() -> None:
    events = parse_calendar_html(generated_calendar_html(30), now=NOW)
    payload = schedule_payload(upcoming_events(events, NOW))
    embeds = payload["embeds"]
    assert len(embeds) == 2
    assert [len(embed["fields"]) for embed in embeds] == [25, 5]
    assert sum(len(embed["fields"]) for embed in embeds) == 30


def test_embed_payloads_are_plain_task_first_text() -> None:
    upcoming = upcoming_events(parsed_events(), NOW)
    schedule = schedule_payload(upcoming, now=NOW)
    assert schedule["username"] == "Chloe - ALz Reminder"
    assert "avatar_url" not in schedule
    schedule_embed = schedule["embeds"][0]
    assert schedule_embed["title"] == "📚 JADWAL TUGAS - Last update: 7 September 2026, 12.00 WIB"
    assert schedule_embed["color"] == 3447003
    first_field = schedule_embed["fields"][0]
    assert first_field["name"] == "**Tugas 0**"
    assert first_field["value"] == (
        "Pengantar Sistem Operasi (A,B) Gasal 2026/2027\n"
        "Deadline: **Senin, 7 September 2026, Pukul 23.55**\n"
        "[Buka Tugas](https://scele.cs.ui.ac.id/mod/assign/view.php?id=221440)\n\u200b"
    )
    assert "Informasi Tugas" not in first_field["value"]
    assert "Format pengumpulan" not in first_field["value"]
    assert "discord.com/assets" not in str(schedule)
    assert "![" not in str(schedule)

    deadline = deadline_today_payload([])["embeds"][0]
    assert deadline["title"] == "🚨 DEADLINE HARI INI"
    assert deadline["description"] == "Be Happy today. No deadline"
    assert "footer" not in deadline

    deadline_with_tasks = deadline_today_payload([upcoming[0]])["embeds"][0]
    assert deadline_with_tasks["footer"]["text"] == "⚠️ Jangan lupa dikumpulkan sebelum deadline!"


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
    assert sent[0]["embeds"][0]["title"].startswith("📚 JADWAL TUGAS - Last update: ")
    assert sent[1]["embeds"][0]["title"] == "🚨 DEADLINE HARI INI"


def test_scheduled_update_kind_comes_from_triggering_cron() -> None:
    for trigger in ("7 17 * * *", "22 17 * * *", "37 17 * * *", "52 17 * * *"):
        assert scheduled_update_kind(trigger) == "schedule"
    for trigger in ("7 3 * * *", "22 3 * * *", "37 3 * * *", "52 3 * * *"):
        assert scheduled_update_kind(trigger) == "deadline"
    for trigger in ("7 5 * * *", "22 5 * * *", "37 5 * * *", "52 5 * * *"):
        assert scheduled_update_kind(trigger) == "schedule"
    assert scheduled_update_kind(None) is None
    assert scheduled_update_kind("0 17 * * *") is None


def test_scheduled_run_uses_cron_trigger_not_delayed_runner_time(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"active": true, "schedule_message_id": "schedule-id"}', encoding="utf-8")
    monkeypatch.setenv("STATE_FILE", str(state_path))
    monkeypatch.setenv("TESTER", "OFF")
    monkeypatch.setenv("ACTIVATE", "OFF")
    monkeypatch.setenv("SCHEDULE_TRIGGER", "7 17 * * *")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.test/webhook")
    monkeypatch.setattr("bot.main.fetch_upcoming", lambda _now: [])

    updated: list[str] = []
    monkeypatch.setattr("bot.main.update_schedule", lambda *_args: updated.append("schedule"))
    monkeypatch.setattr(
        "bot.main.update_deadline",
        lambda *_args: (_ for _ in ()).throw(AssertionError("wrong update")),
    )

    run_main()
    assert updated == ["schedule"]


def test_manual_update_refreshes_both_persistent_messages(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"active": true, "schedule_message_id": "schedule-id", "deadline_message_id": "deadline-id"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("STATE_FILE", str(state_path))
    monkeypatch.setenv("TESTER", "OFF")
    monkeypatch.setenv("ACTIVATE", "OFF")
    monkeypatch.setenv("MANUAL_UPDATE", "ON")
    monkeypatch.setenv("SCHEDULE_TRIGGER", "")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.test/webhook")
    monkeypatch.setattr("bot.main.fetch_upcoming", lambda _now: [])

    updated: list[str] = []
    monkeypatch.setattr("bot.main.update_schedule", lambda *_args: updated.append("schedule"))
    monkeypatch.setattr("bot.main.update_deadline", lambda *_args: updated.append("deadline"))

    run_main()
    assert updated == ["schedule", "deadline"]


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
