from __future__ import annotations

import email
import ssl
from email.header import decode_header
from email.message import Message

from imapclient import IMAPClient
from imapclient.imapclient import TRASH

from jev_mail.config import MailboxConfig
from jev_mail.mailbox.base import Email

PROCESSED_KEYWORD = "$JevProcessed"


class Mailbox:
    """Thin wrapper around imapclient.IMAPClient: fetch unprocessed mail and
    apply the primitive actions (tag/move/flag/seen). Use as a context
    manager so the connection always gets closed."""

    def __init__(self, config: MailboxConfig, server: IMAPClient | None = None):
        self._config = config
        # `server` is an injection point for tests; production code always
        # leaves it unset and lets __enter__ create the real connection.
        self._server = server

    def __enter__(self) -> "Mailbox":
        if self._server is None:
            starttls = self._config.tls == "starttls"
            self._server = IMAPClient(self._config.host, port=self._config.port, use_uid=True, ssl=not starttls)
            if starttls:
                # Proton Bridge serves plain IMAP on 1143 and needs an upgrade before login.
                context = ssl.create_default_context(cafile=self._config.tls_ca_file) if self._config.tls_ca_file else None
                self._server.starttls(ssl_context=context)
            self._server.login(self._config.username, self._config.password)
            self._server.select_folder(self._config.folder)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            try:
                self._server.logout()
            except Exception:
                pass

    def fetch_unprocessed(self, limit: int | None = None) -> list[Email]:
        """`limit` caps how many messages get fetched+classified in one call
        -- keeps a single run/poll bounded (cost, rate limits, one huge
        backlog) instead of processing an entire inbox at once.

        IMAP UIDs increase monotonically with arrival, and SEARCH returns
        them in ascending order -- sort descending so a capped run picks up
        the newest unprocessed mail first, not whatever's oldest in a big
        backlog."""
        uids = self._server.search(["UNKEYWORD", PROCESSED_KEYWORD])
        if not uids:
            return []
        uids = sorted(uids, reverse=True)
        if limit is not None:
            uids = uids[:limit]
        # PEEK: fetching RFC822 or BODY[] sets \Seen (RFC 3501), and processed mail must stay unread.
        response = self._server.fetch(uids, ["BODY.PEEK[]"])
        emails = []
        for uid, data in response.items():
            msg = email.message_from_bytes(data[b"BODY[]"])
            emails.append(
                Email(
                    uid=uid,
                    subject=_decode_subject(msg),
                    body=_extract_body(msg),
                    message_id=_decode_header(msg, "Message-ID"),
                    sender=_decode_header(msg, "From"),
                    list_unsubscribe=_decode_header(msg, "List-Unsubscribe"),
                )
            )
        return emails

    def fetch_senders(self, limit: int | None = None) -> list[tuple[str, str]]:
        """(From, List-Unsubscribe) of the newest `limit` messages in the folder, processed or not, for `census`."""
        uids = sorted(self._server.search(["ALL"]), reverse=True)[:limit]
        rows = []
        for start in range(0, len(uids), 500):
            response = self._server.fetch(uids[start : start + 500], ["BODY.PEEK[HEADER.FIELDS (FROM LIST-UNSUBSCRIBE)]"])
            for data in response.values():
                # The server answers under BODY[...], not the BODY.PEEK[...] key that was asked for.
                header = next(value for key, value in data.items() if key.startswith(b"BODY["))
                msg = email.message_from_bytes(header)
                rows.append((_decode_header(msg, "From"), _decode_header(msg, "List-Unsubscribe")))
        return rows

    def folder_mail(self, folder: str, marker: str) -> list[tuple[int | str, str, bool]]:
        """(uid, From, carries `marker`) for every message in `folder`, for `clean`. Leaves `folder` selected.
        A Proton label is the IMAP folder Labels/<marker>, so a message is marked when its Message-ID is there too."""
        # shortcut: Proton labels only, not an IMAP keyword; read a keyword too when a non-Proton server needs it.
        names = {name for _, _, name in self._server.list_folders()}
        if folder not in names:
            return []
        marked_ids: set[str] = set()
        if f"Labels/{marker}" in names:
            self._server.select_folder(f"Labels/{marker}", readonly=True)
            marked_ids = {_decode_header(msg, "Message-ID") for _, msg in self._headers("MESSAGE-ID")} - {""}
        self._server.select_folder(folder)
        return [
            (uid, _decode_header(msg, "From"), _decode_header(msg, "Message-ID") in marked_ids)
            for uid, msg in self._headers("FROM MESSAGE-ID")
        ]

    def trash(self, folder: str, uids: list[int | str]) -> None:
        self._server.select_folder(folder)
        self._server.move(uids, self._server.find_special_folder(TRASH) or "Trash")

    def labeled_mail(self, marker: str) -> list[Email]:
        """Headers of every message in the Proton label folder Labels/<marker>, for `unsubscribe`. Body is empty."""
        folder = f"Labels/{marker}"
        if folder not in (name for _, _, name in self._server.list_folders()):
            return []
        self._server.select_folder(folder)
        return [
            Email(
                uid=uid,
                subject=_decode_subject(msg),
                body="",
                message_id=_decode_header(msg, "Message-ID"),
                sender=_decode_header(msg, "From"),
                list_unsubscribe=_decode_header(msg, "List-Unsubscribe"),
                list_unsubscribe_post=_decode_header(msg, "List-Unsubscribe-Post"),
            )
            for uid, msg in self._headers("FROM SUBJECT MESSAGE-ID LIST-UNSUBSCRIBE LIST-UNSUBSCRIBE-POST")
        ]

    def relabel(self, uid: int | str, old: str, new: str) -> None:
        """Moves `uid` from Labels/<old> to Labels/<new>, which swaps the Proton label and leaves its folder alone."""
        # shortcut: relies on Proton Bridge turning a move between label folders into a label swap; not checked live.
        target = f"Labels/{new}"
        if target not in (name for _, _, name in self._server.list_folders()):
            self._server.create_folder(target)
        self._server.select_folder(f"Labels/{old}")
        self._server.move([uid], target)

    def _headers(self, fields: str) -> list[tuple[int, Message]]:
        uids = self._server.search(["ALL"])
        out = []
        for start in range(0, len(uids), 500):
            response = self._server.fetch(uids[start : start + 500], [f"BODY.PEEK[HEADER.FIELDS ({fields})]"])
            for uid, data in response.items():
                header = next(value for key, value in data.items() if key.startswith(b"BODY["))
                out.append((uid, email.message_from_bytes(header)))
        return out

    def mark_processed(self, uid: int) -> None:
        self._server.add_flags([uid], [PROCESSED_KEYWORD])

    def add_tag(self, uid: int, value: str) -> None:
        self._server.add_flags([uid], [value])

    def move(self, uid: int, folder: str) -> None:
        if folder not in (name for _, _, name in self._server.list_folders()):
            self._server.create_folder(folder)
        self._server.move([uid], folder)

    def set_flag(self, uid: int, flagged: bool) -> None:
        (self._server.add_flags if flagged else self._server.remove_flags)([uid], [b"\\Flagged"])

    def set_seen(self, uid: int, seen: bool) -> None:
        (self._server.add_flags if seen else self._server.remove_flags)([uid], [b"\\Seen"])

    def supports_idle(self) -> bool:
        return bool(self._server.has_capability("IDLE"))

    def idle(self) -> None:
        self._server.idle()

    def idle_check(self, timeout: int = 30) -> list:
        return self._server.idle_check(timeout=timeout)

    def idle_done(self) -> None:
        self._server.idle_done()


def _decode_subject(msg: Message) -> str:
    return _decode_header(msg, "Subject")


def _decode_header(msg: Message, name: str) -> str:
    raw = msg.get(name, "")
    parts = decode_header(raw)
    return "".join(
        part.decode(encoding or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, encoding in parts
    )


def _extract_body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                return _decode_payload(part)
        return ""
    return _decode_payload(msg)


def _decode_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")
