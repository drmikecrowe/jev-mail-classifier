from __future__ import annotations

import base64
import email
import os
from email.utils import parseaddr
from pathlib import Path

from jev_mail.config import ConfigError, MailboxConfig
from jev_mail.mailbox.base import Email
from jev_mail.mailbox.imap import _decode_header, _extract_body

# The Google client libraries are imported inside functions only, so IMAP-only
# runs never load them (GH-4 A5, S6.2).

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_FILE = "gmail-token.json"
CLIENT_SECRETS_FILE = "client_secrets.json"
PROCESSED_LABEL = "JevProcessed"
ARCHIVE_FOLDER = "[Gmail]/All Mail"
# Gmail's messages.list page limit.
MAX_RESULTS = 500


class GmailError(Exception):
    """A Gmail API or Google auth failure, with the original message."""


class GmailMailbox:
    """The Gmail API behind the same primitives as the IMAP `Mailbox`. Tags,
    folders and the processed marker are all Gmail labels, applied by id."""

    def __init__(self, config: MailboxConfig, config_dir: str | Path, service=None):
        self._config = config
        self._config_dir = Path(config_dir)
        # `service` is an injection point for tests, like `Mailbox(server=...)`.
        self._service = service
        self._labels: dict[str, str] = {}

    def __enter__(self) -> "GmailMailbox":
        if self._service is None:
            self._service = _build_service(self._config_dir / TOKEN_FILE)
        listed = _execute(self._service.users().labels().list(userId="me"))
        self._labels = {label["name"]: label["id"] for label in listed.get("labels", [])}
        if self._config.folder not in self._labels:
            raise ConfigError(f"no Gmail label named {self._config.folder!r} for {self._config.username}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def fetch_unprocessed(self, limit: int | None = None) -> list[Email]:
        # Gmail lists newest first, so a capped run takes the newest mail, as IMAP does.
        listed = _execute(
            self._messages().list(
                userId="me",
                labelIds=[self._labels[self._config.folder]],
                q=f"-label:{PROCESSED_LABEL}",
                maxResults=MAX_RESULTS if limit is None else min(limit, MAX_RESULTS),
            )
        )
        emails = []
        for ref in listed.get("messages", []):
            raw = _execute(self._messages().get(userId="me", id=ref["id"], format="raw"))["raw"]
            msg = email.message_from_bytes(base64.urlsafe_b64decode(raw))
            emails.append(
                Email(
                    uid=ref["id"],
                    subject=_decode_header(msg, "Subject"),
                    body=_extract_body(msg),
                    message_id=_decode_header(msg, "Message-ID"),
                    sender=_decode_header(msg, "From"),
                    list_unsubscribe=_decode_header(msg, "List-Unsubscribe"),
                )
            )
        return emails

    def fetch_senders(self, limit: int | None = None) -> list[tuple[str, str]]:
        """(From, List-Unsubscribe) of the newest `limit` messages under any label, for `census`."""
        rows = []
        # shortcut: one metadata get per message, slow past a few thousand; upgrade to a batch request then.
        for uid in self._list_ids(limit):
            got = _execute(
                self._messages().get(userId="me", id=uid, format="metadata", metadataHeaders=["From", "List-Unsubscribe"])
            )
            headers = {h["name"].lower(): h["value"] for h in got.get("payload", {}).get("headers", [])}
            rows.append((headers.get("from", ""), headers.get("list-unsubscribe", "")))
        return rows

    def folder_mail(self, folder: str, marker: str) -> list[tuple[int | str, str, bool]]:
        """(id, From, carries the `marker` label) for `clean`: each message under the `folder` label from a sender
        with a `marker` message there. Other senders are left out, because `clean` ignores them."""
        if folder not in self._labels or marker not in self._labels:
            return []
        folder_id, marker_id = self._labels[folder], self._labels[marker]
        # One get per message is slow, so read only the marked messages, then search the folder by sender.
        marked = {parseaddr(self._from(uid)[0])[1].lower() for uid in self._list_ids(None, labelIds=[folder_id, marker_id])}
        rows: list[tuple[int | str, str, bool]] = []
        seen: set[str] = set()
        for address in sorted(marked - {""}):
            for uid in self._list_ids(None, labelIds=[folder_id], q=f"from:{address}"):
                if uid not in seen:
                    seen.add(uid)
                    sender, label_ids = self._from(uid)
                    rows.append((uid, sender, marker_id in label_ids))
        return rows

    def _from(self, uid: str) -> tuple[str, list[str]]:
        """(From header, label ids) of one message."""
        got = _execute(self._messages().get(userId="me", id=uid, format="metadata", metadataHeaders=["From"]))
        headers = {h["name"].lower(): h["value"] for h in got.get("payload", {}).get("headers", [])}
        return headers.get("from", ""), got.get("labelIds", [])

    def trash(self, folder: str, uids: list[int | str]) -> None:
        for uid in uids:
            _execute(self._messages().trash(userId="me", id=uid))

    def labeled_mail(self, marker: str) -> list[Email]:
        """Headers of every message under the `marker` label, for `unsubscribe`. Body is empty."""
        if marker not in self._labels:
            return []
        names = ["From", "Subject", "Message-ID", "List-Unsubscribe", "List-Unsubscribe-Post"]
        out = []
        for uid in self._list_ids(None, labelIds=[self._labels[marker]]):
            got = _execute(self._messages().get(userId="me", id=uid, format="metadata", metadataHeaders=names))
            headers = {h["name"].lower(): h["value"] for h in got.get("payload", {}).get("headers", [])}
            out.append(
                Email(
                    uid=uid,
                    subject=headers.get("subject", ""),
                    body="",
                    message_id=headers.get("message-id", ""),
                    sender=headers.get("from", ""),
                    list_unsubscribe=headers.get("list-unsubscribe", ""),
                    list_unsubscribe_post=headers.get("list-unsubscribe-post", ""),
                )
            )
        return out

    def relabel(self, uid: int | str, old: str, new: str) -> None:
        self._modify(uid, add=[self._label_id(new)], remove=[self._label_id(old)])

    def _list_ids(self, limit: int | None, **query) -> list[str]:
        """Message ids, newest first, across every page of messages.list, up to `limit`."""
        ids: list[str] = []
        page_token = None
        while limit is None or len(ids) < limit:
            listed = _execute(
                self._messages().list(
                    userId="me", maxResults=MAX_RESULTS, **query, **({"pageToken": page_token} if page_token else {})
                )
            )
            ids += [ref["id"] for ref in listed.get("messages", [])]
            page_token = listed.get("nextPageToken")
            if not page_token:
                break
        return ids[:limit]

    def mark_processed(self, uid: int | str) -> None:
        self._modify(uid, add=[self._label_id(PROCESSED_LABEL)])

    def add_tag(self, uid: int | str, value: str) -> None:
        self._modify(uid, add=[self._label_id(value)])

    def move(self, uid: int | str, folder: str) -> None:
        # Decide 3: a folder is a label; leaving INBOX is the move, and All Mail is archive alone.
        if folder == ARCHIVE_FOLDER:
            self._modify(uid, remove=["INBOX"])
        else:
            self._modify(uid, add=[self._label_id(folder)], remove=["INBOX"])

    def set_flag(self, uid: int | str, flagged: bool) -> None:
        self._modify(uid, **{"add" if flagged else "remove": ["STARRED"]})

    def set_seen(self, uid: int | str, seen: bool) -> None:
        self._modify(uid, **{"remove" if seen else "add": ["UNREAD"]})

    def supports_idle(self) -> bool:
        return False

    def _messages(self):
        return self._service.users().messages()

    def _label_id(self, name: str) -> str:
        if name not in self._labels:
            created = _execute(self._service.users().labels().create(userId="me", body={"name": name}))
            self._labels[name] = created["id"]
        return self._labels[name]

    def _modify(self, uid: int | str, add: list[str] | None = None, remove: list[str] | None = None) -> None:
        body = {}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove
        _execute(self._messages().modify(userId="me", id=uid, body=body))


def authorize_gmail(config_dir: str | Path) -> Path:
    """Runs the one-time browser sign-in and writes the token file; returns its path."""
    config_dir = Path(config_dir)
    secrets = config_dir / CLIENT_SECRETS_FILE
    if not secrets.exists():
        raise ConfigError(
            f"no Google client secret file at {secrets} -- create a Desktop OAuth client "
            "with the Gmail API enabled in Google Cloud Console and save its JSON there"
        )
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
    credentials = flow.run_local_server(port=0)
    token = config_dir / TOKEN_FILE
    _write_token(token, credentials.to_json())
    return token


def _build_service(token: Path):
    if not token.exists():
        raise ConfigError(f"no Gmail token at {token} -- run `jev-mail auth-gmail`")
    from google.auth.exceptions import GoogleAuthError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient import discovery

    try:
        credentials = Credentials.from_authorized_user_file(str(token), SCOPES)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            _write_token(token, credentials.to_json())
    except (GoogleAuthError, ValueError) as exc:
        raise GmailError(str(exc)) from exc
    return discovery.build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _execute(request):
    from google.auth.exceptions import GoogleAuthError
    from googleapiclient.errors import HttpError

    try:
        return request.execute()
    except (HttpError, GoogleAuthError) as exc:
        raise GmailError(str(exc)) from exc


def _write_token(path: Path, text: str) -> None:
    # Owner-only on every write, including a rewrite of a file with looser bits (M4).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
