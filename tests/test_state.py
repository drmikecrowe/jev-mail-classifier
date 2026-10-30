import json
import sqlite3

from jev_mail.mailbox import Email


def _rows(path) -> list[tuple]:
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT account, message_id, probabilities FROM processed").fetchall()


def test_missing_message_id_is_stored_as_uid(tmp_path):
    """S3.5"""
    from jev_mail.state import State

    state = State(tmp_path / "state.db")
    state.record("a", Email(uid=42, subject="s", body="b"), "jev", {}, [])

    assert [row[1] for row in _rows(tmp_path / "state.db")] == ["uid:42"]


def test_recording_the_same_email_again_replaces_its_row(tmp_path):
    """S3.6"""
    from jev_mail.state import State

    state = State(tmp_path / "state.db")
    mail = Email(uid=1, subject="s", body="b", message_id="<m@example.com>")
    state.record("a", mail, "jev", {"X": 0.9}, [])
    state.record("a", mail, "jev", {"X": 0.1}, [])

    rows = _rows(tmp_path / "state.db")
    assert len(rows) == 1
    assert rows[0][:2] == ("a", "<m@example.com>")
    assert json.loads(rows[0][2]) == {"X": 0.1}


def test_gmail_string_uid_falls_back_as_uid_prefix(tmp_path):
    """GH-4 S6.1"""
    from jev_mail.state import State

    state = State(tmp_path / "state.db")
    state.record("a", Email(uid="b2", subject="s", body="b"), "jev", {}, [])

    assert [row[1] for row in _rows(tmp_path / "state.db")] == ["uid:b2"]


def test_has_finds_a_recorded_message_by_its_key(tmp_path):
    """GH-5 State.has"""
    from jev_mail.state import State

    state = State(tmp_path / "state.db")
    state.record("a", Email(uid="m1", subject="s", body="b", message_id="<m1@example.com>"), "jev", {}, [])
    state.record("a", Email(uid="m2", subject="s", body="b"), "jev", {}, [])

    assert state.has("a", "<m1@example.com>")
    assert state.has("a", "uid:m2")
    assert not state.has("b", "<m1@example.com>")
    assert not state.has("a", "<m3@example.com>")


def test_cursor_is_unset_until_set_and_kept_per_account(tmp_path):
    """GH-5 State.cursor and State.set_cursor"""
    from jev_mail.state import State

    state = State(tmp_path / "state.db")
    assert state.cursor("a") is None

    state.set_cursor("a", "2026-10-30T09:00:00Z")
    state.set_cursor("a", "2026-10-30T10:00:00Z")
    state.set_cursor("b", "2026-10-29T00:00:00Z")

    reopened = State(tmp_path / "state.db")
    assert reopened.cursor("a") == "2026-10-30T10:00:00Z"
    assert reopened.cursor("b") == "2026-10-29T00:00:00Z"


def test_an_existing_state_db_opens_with_its_processed_rows(tmp_path):
    """GH-5 M7"""
    from jev_mail.state import State

    db = tmp_path / "state.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE processed (account TEXT NOT NULL, message_id TEXT NOT NULL, source TEXT NOT NULL,"
            " probabilities TEXT NOT NULL, actions TEXT NOT NULL, processed_at TEXT NOT NULL,"
            " PRIMARY KEY (account, message_id))"
        )
        conn.execute("INSERT INTO processed VALUES ('a', '<old@example.com>', 'jev', '{}', '[]', 'x')")

    state = State(db)

    assert state.has("a", "<old@example.com>")
    assert state.cursor("a") is None
