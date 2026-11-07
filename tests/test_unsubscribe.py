from unittest.mock import MagicMock

import httpx

from jev_mail import cli, unsubscribe
from jev_mail.config import MailboxConfig
from jev_mail.mailbox import Mailbox
from jev_mail.mailbox.base import Email
from jev_mail.mailbox.gmail import GmailMailbox
from jev_mail.mailbox.graph import GRAPH_BASE, GraphMailbox

ONE_CLICK = "List-Unsubscribe=One-Click"
CONFIG = "accounts:\n  - host: imap.example.com\ncategories:\n  BULK:\n    description: bulk\n"


# --- one_click_url ----------------------------------------------------------


def test_one_click_url_picks_the_https_link():
    header = "<mailto:u@example.com?subject=unsub>, <https://example.com/u?id=1>"
    assert unsubscribe.one_click_url(header, ONE_CLICK) == "https://example.com/u?id=1"


def test_one_click_url_needs_the_post_header():
    assert unsubscribe.one_click_url("<https://example.com/u>", "") is None


def test_one_click_url_refuses_plain_http_and_mailto():
    assert unsubscribe.one_click_url("<http://example.com/u>, <mailto:u@example.com>", ONE_CLICK) is None


def test_one_click_url_joins_a_folded_link():
    assert unsubscribe.one_click_url("<https://example.com/\r\n u?id=1>", f"  {ONE_CLICK.lower()} ") == "https://example.com/u?id=1"


# --- unsubscribe ------------------------------------------------------------


def _post(monkeypatch, answer):
    sent = []

    def fake_post(url, **kwargs):
        sent.append((url, kwargs))
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer, request=httpx.Request("POST", url))

    monkeypatch.setattr(unsubscribe.httpx, "post", fake_post)
    return sent


def test_unsubscribe_posts_the_one_click_body(monkeypatch):
    sent = _post(monkeypatch, 200)

    assert unsubscribe.unsubscribe("https://example.com/u") is None
    url, kwargs = sent[0]
    assert url == "https://example.com/u"
    assert kwargs["content"] == ONE_CLICK
    assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_unsubscribe_reports_a_non_2xx(monkeypatch):
    _post(monkeypatch, 302)
    assert unsubscribe.unsubscribe("https://example.com/u") == "HTTP 302"


def test_unsubscribe_reports_a_network_error(monkeypatch):
    _post(monkeypatch, httpx.ConnectError("refused"))
    assert unsubscribe.unsubscribe("https://example.com/u") == "ConnectError: refused"


# --- cmd_unsubscribe --------------------------------------------------------

REQUESTS = [
    Email(uid=1, subject="a", body="", sender="News <news@example.com>", list_unsubscribe="<https://example.com/ok>", list_unsubscribe_post=ONE_CLICK),
    Email(uid=2, subject="b", body="", sender="deals@example.com", list_unsubscribe="<mailto:u@example.com>"),
    Email(uid=3, subject="c", body="", sender="shop@example.com", list_unsubscribe="<https://example.com/bad>", list_unsubscribe_post=ONE_CLICK),
    Email(uid=4, subject="d", body="", sender="news@example.com", list_unsubscribe="<https://example.com/ok>", list_unsubscribe_post=ONE_CLICK),
]


def _run(tmp_path, monkeypatch, *argv):
    (tmp_path / "config.yaml").write_text(CONFIG)
    calls: list = []

    class FakeMailbox:
        def __init__(self, account):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def labeled_mail(self, marker):
            calls.append(("labeled_mail", marker))
            return REQUESTS

        def relabel(self, uid, old, new):
            calls.append(("relabel", uid, old, new))

    posted = []
    monkeypatch.setattr(cli, "Mailbox", FakeMailbox)
    monkeypatch.setattr(cli.unsubscribe, "unsubscribe", lambda url: posted.append(url) or (None if url.endswith("/ok") else "HTTP 500"))
    args = cli.build_parser().parse_args(["--dir", str(tmp_path), "unsubscribe", *argv])
    return cli.cmd_unsubscribe(args), calls, posted


def test_unsubscribe_relabels_by_outcome(tmp_path, monkeypatch, capsys):
    code, calls, posted = _run(tmp_path, monkeypatch)

    assert code == 0
    assert posted == ["https://example.com/ok", "https://example.com/bad"]
    assert calls == [
        ("labeled_mail", "Unsubscribe"),
        ("relabel", 1, "Unsubscribe", "Unsubscribed"),
        ("relabel", 2, "Unsubscribe", "Manual-Unsubscribe"),
        ("relabel", 3, "Unsubscribe", "Manual-Unsubscribe"),
        ("relabel", 4, "Unsubscribe", "Unsubscribed"),
    ]
    out = capsys.readouterr().out
    assert out.count("news@example.com") == 1
    assert "[unsubscribe] news@example.com: unsubscribed -> Unsubscribed\n" in out
    assert "[unsubscribe] deals@example.com: no one-click link -> Manual-Unsubscribe\n" in out
    assert "[unsubscribe] shop@example.com: HTTP 500 -> Manual-Unsubscribe\n" in out
    assert "1 unsubscribed, 2 for you" in out


def test_unsubscribe_dry_run_sends_and_relabels_nothing(tmp_path, monkeypatch, capsys):
    code, calls, posted = _run(tmp_path, monkeypatch, "--dry-run")

    assert code == 0
    assert posted == []
    assert calls == [("labeled_mail", "Unsubscribe")]
    assert "[dry-run] news@example.com: one-click https://example.com/ok\n" in capsys.readouterr().out


# --- backends ---------------------------------------------------------------


def test_imap_reads_the_proton_label_folder_and_moves_between_labels():
    server = MagicMock()
    server.list_folders.return_value = [((), b"/", "Folders/BULK"), ((), b"/", "Labels/Unsubscribe")]
    server.search.return_value = [7]
    header = f"From: a@example.com\r\nList-Unsubscribe: <https://example.com/u>\r\nList-Unsubscribe-Post: {ONE_CLICK}\r\n\r\n"
    server.fetch.return_value = {7: {b"BODY[HEADER.FIELDS (X)]": header.encode()}}
    mailbox = Mailbox(MailboxConfig(host="imap.example.com"), server=server)

    [mail] = mailbox.labeled_mail("Unsubscribe")
    assert (mail.uid, mail.sender, mail.list_unsubscribe_post) == (7, "a@example.com", ONE_CLICK)
    server.select_folder.assert_called_with("Labels/Unsubscribe")

    mailbox.relabel(7, "Unsubscribe", "Unsubscribed")
    server.create_folder.assert_called_once_with("Labels/Unsubscribed")
    server.move.assert_called_once_with([7], "Labels/Unsubscribed")


def test_imap_without_the_label_folder_gives_no_mail():
    server = MagicMock()
    server.list_folders.return_value = [((), b"/", "INBOX")]
    assert Mailbox(MailboxConfig(host="imap.example.com"), server=server).labeled_mail("Unsubscribe") == []


def test_gmail_reads_the_label_and_swaps_it():
    service = MagicMock()
    labels = [{"id": "INBOX", "name": "INBOX"}, {"id": "L2", "name": "Unsubscribe"}, {"id": "L3", "name": "Unsubscribed"}]
    service.users.return_value.labels.return_value.list.return_value.execute.return_value = {"labels": labels}
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.return_value = {"messages": [{"id": "m1"}]}
    headers = [{"name": "From", "value": "a@example.com"}, {"name": "List-Unsubscribe-Post", "value": ONE_CLICK}]
    messages.get.return_value.execute.return_value = {"payload": {"headers": headers}}
    mailbox = GmailMailbox(MailboxConfig(backend="gmail", host="gmail.googleapis.com"), "/nonexistent", service=service).__enter__()

    [mail] = mailbox.labeled_mail("Unsubscribe")
    assert (mail.uid, mail.sender, mail.list_unsubscribe_post) == ("m1", "a@example.com", ONE_CLICK)
    assert messages.list.call_args.kwargs["labelIds"] == ["L2"]

    mailbox.relabel("m1", "Unsubscribe", "Unsubscribed")
    messages.modify.assert_called_once_with(userId="me", id="m1", body={"addLabelIds": ["L3"], "removeLabelIds": ["L2"]})


def test_graph_filters_by_category_and_swaps_it(tmp_path):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        path = request.url.path.removeprefix("/v1.0")
        if request.method == "GET" and path == "/me/messages":
            item = {
                "id": "m1",
                "from": {"emailAddress": {"address": "a@example.com"}},
                "internetMessageHeaders": [{"name": "List-Unsubscribe-Post", "value": ONE_CLICK}],
            }
            return httpx.Response(200, json={"value": [item]})
        if request.method == "GET":
            return httpx.Response(200, json={"categories": ["Red", "Unsubscribe"]})
        return httpx.Response(200, json={})

    http = httpx.Client(base_url=GRAPH_BASE, transport=httpx.MockTransport(handler))
    with GraphMailbox(MailboxConfig(backend="o365", host="graph.microsoft.com"), tmp_path, http=http, token=lambda: "t") as mailbox:
        [mail] = mailbox.labeled_mail("Unsubscribe")
        mailbox.relabel("m1", "Unsubscribe", "Unsubscribed")

    assert (mail.uid, mail.list_unsubscribe_post) == ("m1", ONE_CLICK)
    assert sent[0].url.params["$filter"] == "categories/any(c:c eq 'Unsubscribe')"
    assert sent[-1].method == "PATCH"
    assert sent[-1].content == b'{"categories":["Red","Unsubscribed"]}'
