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


class State:
    """A local record of each processed email, beside the server keyword.
    The keyword stays the source of truth; nothing reads this record yet."""

    def __init__(self, path: str | Path):
        self._conn = sqlite3.connect(path)
        with self._conn:
            self._conn.execute(_SCHEMA)

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
