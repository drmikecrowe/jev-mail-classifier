import json
import stat
import subprocess
import sys

import httpx
import pytest

from jev_mail.config import MailboxConfig
from jev_mail.mailbox import Email
from jev_mail.mailbox.graph import GRAPH_BASE, GraphError, GraphMailbox
from jev_mail.state import State

ACCOUNT_KEY = "graph.microsoft.com/me@example.com"
LIST_PATH = "/me/mailFolders/inbox/messages"
PREFER = 'outlook.body-content-type="text", IdType="ImmutableId"'


def _account() -> MailboxConfig:
    return MailboxConfig(
        backend="o365", host="graph.microsoft.com", username="me@example.com", folder="INBOX", max_emails_per_run=25
    )


def message(id: str, received: str, categories=(), **extra) -> dict:
    """One message JSON item of a list page."""
    return {
        "id": id,
        "subject": f"Subject {id}",
        "body": {"contentType": "text", "content": f"Body {id}"},
        "from": {"emailAddress": {"name": "Sender", "address": "sender@example.com"}},
        "internetMessageId": f"<{id}@example.com>",
        "categories": list(categories),
        "receivedDateTime": received,
        "internetMessageHeaders": [],
        **extra,
    }


class FakeGraph:
    """The fake Graph: records each request and answers from canned responses.
    The list request is answered from `messages` (newest first), with the
    `ge` filter applied, unless `routes` holds pages for it."""

    def __init__(self, messages=None, routes=None):
        self.messages = list(messages or [])
        self.routes = dict(routes or {})
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/v1.0")
        route = self.routes.get((request.method, path))
        if route is not None:
            answer = route(request) if callable(route) else route
            return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)
        if (request.method, path) == ("GET", LIST_PATH):
            flt = request.url.params.get("$filter")
            floor = flt.split(" ge ", 1)[1] if flt else ""
            return httpx.Response(200, json={"value": [m for m in self.messages if m["receivedDateTime"] >= floor]})
        if request.method == "GET" and path.startswith("/me/messages/"):
            found = next((m for m in self.messages if m["id"] == path.rsplit("/", 1)[1]), None)
            return httpx.Response(200, json={"categories": found["categories"] if found else []})
        return httpx.Response(200, json={})

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=GRAPH_BASE, transport=httpx.MockTransport(self.handler))

    def sent(self, method: str | None = None) -> list[tuple[str, str, object]]:
        """(method, path, JSON body or None) for each request, optionally of one method."""
        out = []
        for r in self.requests:
            if method is None or r.method == method:
                out.append((r.method, r.url.path.removeprefix("/v1.0"), json.loads(r.content) if r.content else None))
        return out

    def list_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "GET" and r.url.path.endswith(LIST_PATH)]


def graph_mailbox(fake: FakeGraph, config_dir, token=lambda: "t", account: MailboxConfig | None = None) -> GraphMailbox:
    return GraphMailbox(account or _account(), config_dir, http=fake.client(), token=token)


# --- the fake msal --------------------------------------------------------


def add_token(cache, access_token: str) -> None:
    """Writes one access and refresh token into a real SerializableTokenCache."""
    cache.add(
        {
            "client_id": "x",
            "scope": ["Mail.ReadWrite"],
            "token_endpoint": "https://login.microsoftonline.com/organizations/oauth2/v2.0/token",
            "response": {"access_token": access_token, "refresh_token": "r", "expires_in": 3600, "token_type": "Bearer"},
        }
    )


def fake_msal(monkeypatch, *, accounts=None, silent=None, renew=False, flow=None, device_result=None, raises=None):
    """Replaces msal.PublicClientApplication with a class that answers from canned values.
    `raises` maps a method name ("__init__" included) to the exception it raises."""
    raises = raises or {}
    import msal

    class FakeApp:
        built: list[tuple] = []
        calls: list[str] = []

        def __init__(self, client_id, authority=None, token_cache=None, **kwargs):
            if "__init__" in raises:
                raise raises["__init__"]
            self.cache = token_cache
            FakeApp.built.append((client_id, authority, token_cache))

        def get_accounts(self, username=None):
            return list(accounts if accounts is not None else [{"username": "me@example.com"}])

        def acquire_token_silent_with_error(self, scopes, account, **kwargs):
            FakeApp.calls.append(f"silent {scopes} {account['username']}")
            if "acquire_token_silent_with_error" in raises:
                raise raises["acquire_token_silent_with_error"]
            if renew:
                add_token(self.cache, "t2")
            return silent if silent is not None else {"access_token": "t2"}

        def initiate_device_flow(self, scopes=None, **kwargs):
            FakeApp.calls.append(f"initiate {scopes}")
            if "initiate_device_flow" in raises:
                raise raises["initiate_device_flow"]
            return flow

        def acquire_token_by_device_flow(self, flow, **kwargs):
            FakeApp.calls.append("device")
            if "access_token" in device_result:
                add_token(self.cache, device_result["access_token"])
            return device_result

    monkeypatch.setattr(msal, "PublicClientApplication", FakeApp)
    return FakeApp


def write_token_file(config_dir, mode=0o600) -> str:
    import msal

    cache = msal.SerializableTokenCache()
    add_token(cache, "t-old")
    text = cache.serialize()
    path = config_dir / "o365-token.json"
    path.write_text(text)
    path.chmod(mode)
    return text


# --- S1. Sign-in and token -------------------------------------------------


def test_a_renewed_token_is_saved_and_used(tmp_path, monkeypatch):
    """S1.4"""
    old = write_token_file(tmp_path, mode=0o644)
    app = fake_msal(monkeypatch, renew=True)
    fake = FakeGraph()

    with GraphMailbox(_account(), tmp_path, http=fake.client()) as mailbox:
        mailbox.set_seen("m1", True)

    token = tmp_path / "o365-token.json"
    assert not any(c.startswith("initiate") for c in app.calls)
    assert app.calls[0] == "silent ['Mail.ReadWrite'] me@example.com"
    assert token.read_text() != old
    assert token.read_text() == app.built[0][2].serialize()
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
    assert fake.requests[0].headers["Authorization"] == "Bearer t2"


def test_the_token_source_runs_before_every_request(tmp_path):
    """S1.5"""
    tokens = iter(["t1", "t2"])
    fake = FakeGraph()

    with graph_mailbox(fake, tmp_path, token=lambda: next(tokens)) as mailbox:
        mailbox.set_flag("m1", True)
        mailbox.set_flag("m1", False)

    assert [r.headers["Authorization"] for r in fake.requests] == ["Bearer t1", "Bearer t2"]


def test_a_cache_with_no_matching_account_names_the_account_and_auth_o365(tmp_path, monkeypatch):
    """S1.7"""
    write_token_file(tmp_path)
    fake_msal(monkeypatch, accounts=[{"username": "other@example.com"}])

    with pytest.raises(GraphError) as raised:
        GraphMailbox(_account(), tmp_path, http=FakeGraph().client()).__enter__()

    assert "me@example.com" in str(raised.value)
    assert "jev-mail auth-o365" in str(raised.value)


# --- S2. Fetch -------------------------------------------------------------


def test_fetch_asks_for_text_bodies_and_builds_the_email(tmp_path):
    """S2.1"""
    m1 = message(
        "m1",
        "2026-10-30T10:00:00Z",
        subject="Invoice 12",
        body={"contentType": "text", "content": "Amount due"},
        **{
            "from": {"emailAddress": {"name": "Billing", "address": "billing@example.com"}},
            "internetMessageHeaders": [{"name": "List-Unsubscribe", "value": "<mailto:u@example.com>"}],
        },
    )
    fake = FakeGraph([m1])

    with graph_mailbox(fake, tmp_path) as mailbox:
        emails = mailbox.fetch_unprocessed(limit=25)

    (request,) = fake.list_requests()
    assert request.headers["Prefer"] == PREFER
    params = request.url.params
    assert params["$orderby"] == "receivedDateTime desc"
    assert params["$top"] == "50"
    assert set(params["$select"].split(",")) == set(m1)
    assert "$filter" not in params
    (mail,) = emails
    assert (mail.uid, mail.subject, mail.body) == ("m1", "Invoice 12", "Amount due")
    assert mail.sender == "Billing <billing@example.com>"
    assert mail.message_id == "<m1@example.com>"
    assert mail.list_unsubscribe == "<mailto:u@example.com>"


def test_fetch_skips_the_category_and_the_state_row(tmp_path):
    """S2.2"""
    State(tmp_path / "state.db").record(
        ACCOUNT_KEY, Email(uid="m2", subject="s", body="b", message_id="<m2@example.com>"), "jev", {}, []
    )
    fake = FakeGraph(
        [
            message("m3", "2026-10-30T10:00:00Z", categories=["JevProcessed"]),
            message("m2", "2026-10-30T09:00:00Z"),
            message("m1", "2026-10-30T08:00:00Z"),
        ]
    )

    with graph_mailbox(fake, tmp_path) as mailbox:
        emails = mailbox.fetch_unprocessed(limit=25)

    assert [m.uid for m in emails] == ["m1"]


def test_a_cursor_filters_the_list_request(tmp_path):
    """S2.3"""
    State(tmp_path / "state.db").set_cursor(ACCOUNT_KEY, "2026-10-30T09:00:00Z")
    fake = FakeGraph()

    with graph_mailbox(fake, tmp_path) as mailbox:
        mailbox.fetch_unprocessed(limit=25)

    params = fake.list_requests()[0].url.params
    assert params["$filter"] == "receivedDateTime ge 2026-10-30T09:00:00Z"
    assert params["$orderby"] == "receivedDateTime desc"


def test_a_message_older_than_the_cursor_is_not_fetched(tmp_path):
    """S2.4"""
    State(tmp_path / "state.db").set_cursor(ACCOUNT_KEY, "2026-10-30T09:00:00Z")
    fake = FakeGraph([message("back", "2026-10-29T08:00:00Z")])

    with graph_mailbox(fake, tmp_path) as mailbox:
        emails = mailbox.fetch_unprocessed(limit=25)

    assert emails == []


def test_fetch_follows_the_next_link_as_given(tmp_path):
    """S2.9"""
    next_link = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?$skiptoken=abc"
    pages = iter(
        [
            {
                "value": [
                    message("p2", "2026-10-30T10:00:00Z", categories=["JevProcessed"]),
                    message("p1", "2026-10-30T09:30:00Z", categories=["JevProcessed"]),
                ],
                "@odata.nextLink": next_link,
            },
            {"value": [message("m1", "2026-10-30T09:00:00Z")]},
        ]
    )
    fake = FakeGraph(routes={("GET", LIST_PATH): lambda request: next(pages)})

    with graph_mailbox(fake, tmp_path) as mailbox:
        emails = mailbox.fetch_unprocessed(limit=25)

    assert [m.uid for m in emails] == ["m1"]
    assert str(fake.list_requests()[1].url) == next_link


# --- S3. Actions -----------------------------------------------------------


def test_tag_adds_a_category_and_keeps_the_others(tmp_path):
    """S3.1"""
    fake = FakeGraph(routes={("GET", "/me/messages/m1"): {"categories": ["Red"]}})

    with graph_mailbox(fake, tmp_path) as mailbox:
        mailbox.add_tag("m1", "BULK")

    assert fake.requests[0].url.params["$select"] == "categories"
    assert fake.sent("PATCH") == [("PATCH", "/me/messages/m1", {"categories": ["Red", "BULK"]})]


def test_tag_already_there_sends_no_patch(tmp_path):
    """S3.2"""
    fake = FakeGraph(routes={("GET", "/me/messages/m1"): {"categories": ["BULK"]}})

    with graph_mailbox(fake, tmp_path) as mailbox:
        mailbox.add_tag("m1", "BULK")

    assert fake.sent("PATCH") == []


def test_move_to_a_folder_that_exists(tmp_path):
    """S3.3"""
    lookups = []

    def folders(request):
        lookups.append(request.url.params["$filter"])
        return {"value": [{"id": "f1", "displayName": "Bulk"}]}

    fake = FakeGraph(routes={("GET", "/me/mailFolders"): folders})

    with graph_mailbox(fake, tmp_path) as mailbox:
        mailbox.move("m1", "Bulk")

    assert lookups == ["displayName eq 'Bulk'"]
    assert fake.sent("POST") == [("POST", "/me/messages/m1/move", {"destinationId": "f1"})]


def test_move_creates_a_missing_folder_once(tmp_path):
    """S3.4"""
    fake = FakeGraph(
        routes={
            ("GET", "/me/mailFolders"): {"value": []},
            ("POST", "/me/mailFolders"): lambda request: httpx.Response(201, json={"id": "f2"}),
        }
    )

    with graph_mailbox(fake, tmp_path) as mailbox:
        mailbox.move("m1", "Bulk")
        mailbox.move("m1", "Bulk")

    assert fake.sent("POST") == [
        ("POST", "/me/mailFolders", {"displayName": "Bulk"}),
        ("POST", "/me/messages/m1/move", {"destinationId": "f2"}),
        ("POST", "/me/messages/m1/move", {"destinationId": "f2"}),
    ]


def test_flag_and_read_state_send_one_patch_each(tmp_path):
    """S3.6"""
    fake = FakeGraph()

    with graph_mailbox(fake, tmp_path) as mailbox:
        mailbox.set_flag("m1", True)
        mailbox.set_flag("m1", False)
        mailbox.set_seen("m1", True)
        mailbox.set_seen("m1", False)

    assert fake.sent() == [
        ("PATCH", "/me/messages/m1", {"flag": {"flagStatus": "flagged"}}),
        ("PATCH", "/me/messages/m1", {"flag": {"flagStatus": "notFlagged"}}),
        ("PATCH", "/me/messages/m1", {"isRead": True}),
        ("PATCH", "/me/messages/m1", {"isRead": False}),
    ]


def test_the_marker_lands_after_a_move_with_the_immutable_id(tmp_path):
    """S3.9"""

    def immutable_only(answer):
        def route(request):
            if 'IdType="ImmutableId"' not in request.headers.get("Prefer", ""):
                return httpx.Response(404, json={"error": {"code": "ErrorItemNotFound"}})
            return answer

        return route

    fake = FakeGraph(
        routes={
            ("GET", "/me/mailFolders"): {"value": [{"id": "f1", "displayName": "Bulk"}]},
            ("POST", "/me/messages/m1/move"): immutable_only({"id": "m1"}),
            ("GET", "/me/messages/m1"): immutable_only({"categories": []}),
            ("PATCH", "/me/messages/m1"): immutable_only({}),
        }
    )

    with graph_mailbox(fake, tmp_path) as mailbox:
        mailbox.move("m1", "Bulk")
        mailbox.mark_processed("m1")

    assert fake.sent("PATCH") == [("PATCH", "/me/messages/m1", {"categories": ["JevProcessed"]})]


# --- S4. Wiring ------------------------------------------------------------


def test_importing_the_cli_loads_no_msal():
    """S4.7"""
    out = subprocess.run(
        [sys.executable, "-c", "import sys, jev_mail.cli; print('msal' in sys.modules)"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert out.strip() == "False"


# --- Round 1 findings: errors on the token path and in a 2xx body -------


def test_a_corrupt_token_file_raises_graph_error_naming_auth_o365(tmp_path, monkeypatch):
    """Finding 2, sites 1"""
    (tmp_path / "o365-token.json").write_text('{"AccessToken": {')
    fake_msal(monkeypatch)

    with pytest.raises(GraphError, match=r"unreadable Office 365 token .* -- run `jev-mail auth-o365`"):
        GraphMailbox(_account(), tmp_path, http=FakeGraph().client()).__enter__()


@pytest.mark.parametrize("where", ["__init__", "acquire_token_silent_with_error"])
def test_a_network_failure_at_sign_in_raises_graph_error(tmp_path, monkeypatch, where):
    """Finding 3, sites 2 and 4"""
    import requests

    write_token_file(tmp_path)
    fake_msal(monkeypatch, raises={where: requests.ConnectionError("down")})

    with pytest.raises(GraphError, match="could not reach Microsoft"):
        GraphMailbox(_account(), tmp_path, http=FakeGraph().client()).__enter__()


def test_a_token_write_that_fails_raises_graph_error(tmp_path, monkeypatch):
    """Finding 2, site 9"""
    write_token_file(tmp_path, mode=0o400)
    fake_msal(monkeypatch, renew=True)

    with pytest.raises(GraphError, match="o365-token.json"):
        GraphMailbox(_account(), tmp_path, http=FakeGraph().client()).__enter__()


def test_a_2xx_answer_that_is_not_json_raises_graph_error(tmp_path):
    """Finding 2, the 2xx body site"""
    fake = FakeGraph(routes={("GET", LIST_PATH): lambda request: httpx.Response(200, text="<html>proxy</html>")})

    with graph_mailbox(fake, tmp_path) as mailbox, pytest.raises(GraphError, match="not JSON"):
        mailbox.fetch_unprocessed(limit=25)


def test_a_fetch_that_returns_nothing_leaves_the_cursor(tmp_path):
    """Finding 1: a dry run with every message processed writes no cursor"""
    State(tmp_path / "state.db")
    fake = FakeGraph([message("m1", "2026-10-30T09:00:00Z", categories=["JevProcessed"])])

    with graph_mailbox(fake, tmp_path) as mailbox:
        assert mailbox.fetch_unprocessed(limit=25) == []
        mailbox.fetch_unprocessed(limit=25)

    assert State(tmp_path / "state.db").cursor(ACCOUNT_KEY) is None
