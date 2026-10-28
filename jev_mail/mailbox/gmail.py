from __future__ import annotations

import base64
import email
import os
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
