from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Jev rejects input over its token limit (measured between 28k and 38k tokens,
# GH-2 decisions.md fact 11) with max_tokens_exceeded, failing the whole run.
MAX_STATE_BODY_CHARS = 20_000


@dataclass
class Email:
    uid: int
    subject: str
    body: str
    message_id: str = ""
    sender: str = ""
    list_unsubscribe: str = ""

    @property
    def state(self) -> str:
        return f"Subject: {self.subject}\n\n{self.body[:MAX_STATE_BODY_CHARS]}"


class MailBackend(Protocol):
    """What the run pipeline needs from a mail backend. IDLE stays on the
    IMAP `Mailbox` only, because `watch` is IMAP-specific."""

    def fetch_unprocessed(self, limit: int | None = None) -> list[Email]: ...

    def mark_processed(self, uid: int) -> None: ...

    def add_tag(self, uid: int, value: str) -> None: ...

    def move(self, uid: int, folder: str) -> None: ...

    def set_flag(self, uid: int, flagged: bool) -> None: ...

    def set_seen(self, uid: int, seen: bool) -> None: ...
