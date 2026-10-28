import base64
import json
import stat
import subprocess
import sys
from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from jev_mail.config import ConfigError, MailboxConfig
from jev_mail.mailbox.gmail import GmailError, GmailMailbox

RAW_MESSAGE = (
    b"Subject: Invoice 12\r\n"
    b"From: Billing <billing@example.com>\r\n"
    b"Message-ID: <m1@example.com>\r\n"
    b"List-Unsubscribe: <mailto:u@example.com>\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Amount due"
)


def _account(folder: str = "INBOX") -> MailboxConfig:
    return MailboxConfig(backend="gmail", host="gmail.googleapis.com", username="me@example.com", folder=folder)


def _service(labels: list[dict], created: dict | None = None) -> MagicMock:
    service = MagicMock()
    service.users.return_value.labels.return_value.list.return_value.execute.return_value = {"labels": labels}
    if created is not None:
        service.users.return_value.labels.return_value.create.return_value.execute.return_value = created
    return service


def _messages(service: MagicMock) -> MagicMock:
    return service.users.return_value.messages.return_value


def _labels(service: MagicMock) -> MagicMock:
    return service.users.return_value.labels.return_value


def _modify_bodies(service: MagicMock) -> list[dict]:
    return [c.kwargs["body"] for c in _messages(service).modify.call_args_list]


INBOX = {"id": "INBOX", "name": "INBOX"}


def _open(service: MagicMock, folder: str = "INBOX") -> GmailMailbox:
    return GmailMailbox(_account(folder), "/nonexistent", service=service).__enter__()


def test_fetch_lists_unprocessed_mail_in_the_watched_label_and_parses_it():
    """S1.1"""
    service = _service([INBOX, {"id": "Label_9", "name": "JevProcessed"}])
    _messages(service).list.return_value.execute.return_value = {"messages": [{"id": "b2"}, {"id": "a1"}]}
    raw = base64.urlsafe_b64encode(RAW_MESSAGE).decode()
    _messages(service).get.return_value.execute.return_value = {"raw": raw}

    emails = _open(service).fetch_unprocessed(limit=25)

    _messages(service).list.assert_called_once_with(
        userId="me", labelIds=["INBOX"], q="-label:JevProcessed", maxResults=25
    )
    assert [c.kwargs for c in _messages(service).get.call_args_list] == [
        {"userId": "me", "id": "b2", "format": "raw"},
        {"userId": "me", "id": "a1", "format": "raw"},
    ]
    assert [e.uid for e in emails] == ["b2", "a1"]
    for mail in emails:
        assert mail.subject == "Invoice 12"
        assert mail.sender == "Billing <billing@example.com>"
        assert mail.message_id == "<m1@example.com>"
        assert mail.list_unsubscribe == "<mailto:u@example.com>"
        assert mail.body == "Amount due"


def test_fetch_with_no_messages_returns_empty_and_gets_nothing():
    """S1.2"""
    service = _service([INBOX])
    _messages(service).list.return_value.execute.return_value = {"resultSizeEstimate": 0}

    assert _open(service).fetch_unprocessed(limit=25) == []
    _messages(service).get.assert_not_called()


def test_unknown_watched_label_is_a_config_error():
    """S1.3"""
    with pytest.raises(ConfigError, match="Work"):
        _open(_service([INBOX]), folder="Work")


def test_tag_adds_an_existing_label_by_id():
    """S2.1"""
    service = _service([INBOX, {"id": "Label_1", "name": "BULK"}])

    _open(service).add_tag("b2", "BULK")

    _messages(service).modify.assert_called_once_with(userId="me", id="b2", body={"addLabelIds": ["Label_1"]})
    _labels(service).create.assert_not_called()


def test_tag_creates_a_missing_label_once():
    """S2.2"""
    service = _service([INBOX], created={"id": "Label_7", "name": "BULK"})
    mailbox = _open(service)

    mailbox.add_tag("b2", "BULK")
    mailbox.add_tag("b2", "BULK")

    _labels(service).create.assert_called_once_with(userId="me", body={"name": "BULK"})
    assert _modify_bodies(service) == [{"addLabelIds": ["Label_7"]}, {"addLabelIds": ["Label_7"]}]


def test_move_adds_the_folder_label_and_removes_inbox():
    """S2.3"""
    service = _service([INBOX, {"id": "Label_3", "name": "Receipts"}])

    _open(service).move("b2", "Receipts")

    assert _modify_bodies(service) == [{"addLabelIds": ["Label_3"], "removeLabelIds": ["INBOX"]}]


def test_move_to_a_missing_label_creates_it():
    """S2.4"""
    service = _service([INBOX], created={"id": "Label_4", "name": "Receipts"})

    _open(service).move("b2", "Receipts")

    _labels(service).create.assert_called_once_with(userId="me", body={"name": "Receipts"})
    assert _modify_bodies(service) == [{"addLabelIds": ["Label_4"], "removeLabelIds": ["INBOX"]}]


def test_move_to_all_mail_only_archives():
    """S2.5"""
    service = _service([INBOX])

    _open(service).move("b2", "[Gmail]/All Mail")

    assert _modify_bodies(service) == [{"removeLabelIds": ["INBOX"]}]
    _labels(service).create.assert_not_called()


def test_flag_and_seen_map_to_starred_and_unread():
    """S2.6"""
    service = _service([INBOX])
    mailbox = _open(service)

    mailbox.set_flag("b2", True)
    mailbox.set_flag("b2", False)
    mailbox.set_seen("b2", True)
    mailbox.set_seen("b2", False)

    assert _modify_bodies(service) == [
        {"addLabelIds": ["STARRED"]},
        {"removeLabelIds": ["STARRED"]},
        {"removeLabelIds": ["UNREAD"]},
        {"addLabelIds": ["UNREAD"]},
    ]


def test_mark_processed_creates_and_adds_the_processed_label():
    """S2.7"""
    service = _service([INBOX], created={"id": "Label_9", "name": "JevProcessed"})
    mailbox = _open(service)

    mailbox.mark_processed("b2")

    _labels(service).create.assert_called_once_with(userId="me", body={"name": "JevProcessed"})
    assert _modify_bodies(service) == [{"addLabelIds": ["Label_9"]}]
    assert mailbox.supports_idle() is False


def test_http_error_becomes_gmail_error():
    """S2.8"""
    service = _service([INBOX, {"id": "Label_1", "name": "BULK"}])
    _messages(service).modify.return_value.execute.side_effect = HttpError(
        httplib2.Response({"status": 403}), b'{"error": {"message": "forbidden"}}'
    )

    with pytest.raises(GmailError, match="403"):
        _open(service).add_tag("b2", "BULK")


def test_expired_token_is_refreshed_and_rewritten_owner_only(tmp_path, monkeypatch):
    """S4.4"""
    import googleapiclient.discovery
    from google.oauth2.credentials import Credentials

    token = tmp_path / "gmail-token.json"
    token.write_text(
        json.dumps(
            {
                "token": "t1",
                "refresh_token": "r",
                "client_id": "c.apps.googleusercontent.com",
                "client_secret": "s",
                "expiry": "2000-01-01T00:00:00Z",
            }
        )
    )
    token.chmod(0o644)
    order = []

    def fake_refresh(self, request):
        order.append("refresh")
        self.token = "t2"
        self.expiry = None

    def fake_build(name, version, credentials, **kwargs):
        order.append(("build", name, version, credentials.token))
        return _service([INBOX])

    monkeypatch.setattr(Credentials, "refresh", fake_refresh)
    monkeypatch.setattr(googleapiclient.discovery, "build", fake_build)

    with GmailMailbox(_account(), tmp_path):
        pass

    assert order == ["refresh", ("build", "gmail", "v1", "t2")]
    assert json.loads(token.read_text())["token"] == "t2"
    assert stat.S_IMODE(token.stat().st_mode) == 0o600


def test_importing_the_cli_loads_no_google_client():
    """S6.2"""
    code = "import sys, jev_mail.cli; print(sorted(m for m in ('googleapiclient', 'google_auth_oauthlib') if m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout

    assert out.strip() == "[]"
