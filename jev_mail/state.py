from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jev_mail.mailbox import Email

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed (
    account TEXT NOT NULL,
    message_id TEXT NOT NULL,
    source TEXT NOT NULL,
    probabilities TEXT NOT NULL,
    actions TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    PRIMARY KEY (account, message_id)
)
"""

_CURSOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS cursor (
    account TEXT PRIMARY KEY,
    received_at TEXT NOT NULL
)
"""


class State:
    """A local record of each processed email, beside the server keyword, and
    one fetch cursor per account. The keyword stays the source of truth;
    `GraphMailbox` reads the rows and the cursor to skip mail (GH-5)."""

    def __init__(self, path: str | Path):
        self._conn = sqlite3.connect(path)
        with self._conn:
            self._conn.execute(_SCHEMA)
            self._conn.execute(_CURSOR_SCHEMA)

    def record(self, account_key: str, mail: Email, source: str, probabilities: dict, actions: list[dict]) -> None:
        # A message without a Message-ID falls back to its UID, unique only within one folder.
        message_id = mail.message_id or f"uid:{mail.uid}"
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO processed VALUES (?, ?, ?, ?, ?, ?)",
                (
                    account_key,
                    message_id,
                    source,
                    json.dumps(probabilities),
                    json.dumps(actions),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def has(self, account_key: str, message_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM processed WHERE account = ? AND message_id = ?", (account_key, message_key)
        ).fetchone()
        return row is not None

    def cursor(self, account_key: str) -> str | None:
        row = self._conn.execute("SELECT received_at FROM cursor WHERE account = ?", (account_key,)).fetchone()
        return row[0] if row else None

    def set_cursor(self, account_key: str, received_at: str) -> None:
        with self._conn:
            self._conn.execute("INSERT OR REPLACE INTO cursor VALUES (?, ?)", (account_key, received_at))
