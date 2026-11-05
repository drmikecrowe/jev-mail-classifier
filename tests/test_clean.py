from unittest.mock import MagicMock

import httpx

from jev_mail import cli
from jev_mail.config import MailboxConfig
from jev_mail.mailbox import Mailbox
from jev_mail.mailbox.gmail import GmailMailbox
from jev_mail.mailbox.graph import GRAPH_BASE, GraphMailbox

CONFIG = """accounts:
  - host: imap.example.com
    folder_prefix: Folders/
categories:
  BULK:
    description: bulk
    actions:
      - type: move
        folder: BULK
"""

BULK_MAIL = [
    (1, "News <news@example.com>", False),
    (2, "news@example.com", True),
    (3, "deals@example.com", False),
    (4, "", True),
]


def _fake(calls: list):
    class FakeMailbox:
        def __init__(self, account):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def folder_mail(self, folder, marker):
            calls.append(("folder_mail", folder, marker))
            return BULK_MAIL

        def trash(self, folder, uids):
            calls.append(("trash", folder, uids))

    return FakeMailbox


def _run(tmp_path, monkeypatch, *argv):
    (tmp_path / "config.yaml").write_text(CONFIG)
    calls: list = []
    monkeypatch.setattr(cli, "Mailbox", _fake(calls))
    args = cli.build_parser().parse_args(["--dir", str(tmp_path), "clean", *argv])
    return cli.cmd_clean(args), calls


def test_clean_trashes_every_bulk_email_from_a_marked_sender(tmp_path, monkeypatch, capsys):
    code, calls = _run(tmp_path, monkeypatch)

    assert code == 0
    assert calls == [("folder_mail", "Folders/BULK", "Unsubscribe"), ("trash", "Folders/BULK", [1, 2])]
    assert "[clean] news@example.com: 2 emails in Folders/BULK -> Trash\n" in capsys.readouterr().out


def test_clean_dry_run_moves_nothing(tmp_path, monkeypatch, capsys):
    code, calls = _run(tmp_path, monkeypatch, "--dry-run")

    assert code == 0
    assert [c[0] for c in calls] == ["folder_mail"]
    assert "[dry-run] news@example.com: 2 emails in Folders/BULK -> Trash\n" in capsys.readouterr().out


def _imap_headers(*pairs):
    return {uid: {b"BODY[HEADER.FIELDS (X)]": text.encode()} for uid, text in pairs}


def test_imap_marks_by_message_id_in_the_proton_label_folder():
    server = MagicMock()
    server.list_folders.return_value = [((), b"/", "Folders/BULK"), ((), b"/", "Labels/Unsubscribe"), ((), b"/", "Trash")]
    server.search.side_effect = [[7], [1, 2]]
    server.fetch.side_effect = [
        _imap_headers((7, "Message-ID: <b@example.com>\r\n\r\n")),
        _imap_headers(
            (1, "From: a@example.com\r\nMessage-ID: <a@example.com>\r\n\r\n"),
            (2, "From: b@example.com\r\nMessage-ID: <b@example.com>\r\n\r\n"),
        ),
    ]
    server.find_special_folder.return_value = "Trash"
    mailbox = Mailbox(MailboxConfig(host="imap.example.com"), server=server)

    assert mailbox.folder_mail("Folders/BULK", "Unsubscribe") == [(1, "a@example.com", False), (2, "b@example.com", True)]
    mailbox.trash("Folders/BULK", [2])
    server.move.assert_called_once_with([2], "Trash")


def test_imap_missing_bulk_folder_gives_no_mail():
    server = MagicMock()
    server.list_folders.return_value = [((), b"/", "INBOX")]

    assert Mailbox(MailboxConfig(host="imap.example.com"), server=server).folder_mail("Folders/BULK", "Unsubscribe") == []


def test_gmail_marks_by_label_and_trashes_by_id():
    service = MagicMock()
    labels = [{"id": "INBOX", "name": "INBOX"}, {"id": "L1", "name": "Folders/BULK"}, {"id": "L2", "name": "Unsubscribe"}]
    service.users.return_value.labels.return_value.list.return_value.execute.return_value = {"labels": labels}
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.return_value = {"messages": [{"id": "m1"}]}
    messages.get.return_value.execute.return_value = {
        "labelIds": ["L1", "L2"],
        "payload": {"headers": [{"name": "From", "value": "a@example.com"}]},
    }
    mailbox = GmailMailbox(MailboxConfig(backend="gmail", host="gmail.googleapis.com"), "/nonexistent", service=service).__enter__()

    assert mailbox.folder_mail("Folders/BULK", "Unsubscribe") == [("m1", "a@example.com", True)]
    assert messages.list.call_args.kwargs["labelIds"] == ["L1"]
    mailbox.trash("Folders/BULK", ["m1"])
    messages.trash.assert_called_once_with(userId="me", id="m1")


def test_graph_marks_by_category_and_moves_to_deleted_items(tmp_path):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append((request.method, request.url.path.removeprefix("/v1.0")))
        if request.url.path.endswith("/me/mailFolders"):
            return httpx.Response(200, json={"value": [{"id": "F1"}]})
        if request.url.path.endswith("/me/mailFolders/F1/messages"):
            item = {"id": "m1", "from": {"emailAddress": {"address": "a@example.com"}}, "categories": ["Unsubscribe"]}
            return httpx.Response(200, json={"value": [item]})
        return httpx.Response(200, json={})

    http = httpx.Client(base_url=GRAPH_BASE, transport=httpx.MockTransport(handler))
    with GraphMailbox(MailboxConfig(backend="o365", host="graph.microsoft.com"), tmp_path, http=http, token=lambda: "t") as mailbox:
        assert mailbox.folder_mail("BULK", "Unsubscribe") == [("m1", "a@example.com", True)]
        mailbox.trash("BULK", ["m1"])

    assert sent[-1] == ("POST", "/me/messages/m1/move")
