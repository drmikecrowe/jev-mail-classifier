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
