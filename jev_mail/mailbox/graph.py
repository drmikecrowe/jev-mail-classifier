from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from email.utils import formataddr
from pathlib import Path
from urllib.parse import quote

import httpx

from jev_mail.config import ConfigError, MailboxConfig
from jev_mail.mailbox.base import Email
from jev_mail.mailbox.gmail import _write_token
from jev_mail.state import State

# msal is imported inside functions only, so IMAP and Gmail runs never load it (S4.7).

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# Microsoft Graph Command Line Tools: a public client that exists in every tenant (A5).
CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
AUTHORITY = "https://login.microsoftonline.com/organizations"
# MSAL adds offline_access itself, and raises ValueError when it is passed.
SCOPES = ["Mail.ReadWrite"]
TOKEN_FILE = "o365-token.json"
PROCESSED_CATEGORY = "JevProcessed"
# Immutable ids survive a move, so mark_processed after move finds the message (A1).
PREFER = 'outlook.body-content-type="text", IdType="ImmutableId"'
LIST_PATH = "/me/mailFolders/inbox/messages"
ALL_MAIL_PATH = "/me/messages"
SELECT = "id,subject,body,from,internetMessageId,categories,receivedDateTime,internetMessageHeaders"
PAGE_SIZE = 50


class GraphError(Exception):
    """A Microsoft Graph or Office 365 sign-in failure, with the status code or the error text."""


class GraphMailbox:
    """The Office 365 Inbox over Microsoft Graph, behind the same primitives as
    the IMAP `Mailbox`. Tags and the processed marker are Outlook categories."""

    def __init__(
        self,
        config: MailboxConfig,
        config_dir: str | Path,
        http: httpx.Client | None = None,
        token: Callable[[], str] | None = None,
    ):
        self._config = config
        self._config_dir = Path(config_dir)
        self._account_key = f"{config.host}/{config.username}"
        # `http` and `token` are injection points for tests, like `Mailbox(server=...)`.
        self._http = http
        self._owns_http = http is None
        self._token = token
        self._state: State | None = None
        self._folders: dict[str, str] = {}
        # (newest receivedDateTime, uids returned and not yet marked) of the last complete fetch.
        self._pending: tuple[str, set[int | str]] | None = None

    def __enter__(self) -> "GraphMailbox":
        if self._token is None:
            self._token = _token_source(self._config_dir / TOKEN_FILE, self._config.username)
        if self._http is None:
            self._http = httpx.Client(base_url=GRAPH_BASE, timeout=30)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._advance_cursor()
        if self._owns_http and self._http is not None:
            self._http.close()

    def fetch_unprocessed(self, limit: int | None = None) -> list[Email]:
        self._open_state()
        self._advance_cursor()
        cursor = self._state.cursor(self._account_key) if self._state else None
        params: dict | None = {"$select": SELECT, "$orderby": "receivedDateTime desc", "$top": str(PAGE_SIZE)}
        if cursor:
            # $orderby's property must lead the $filter, or Graph answers InefficientFilter.
            params["$filter"] = f"receivedDateTime ge {cursor}"
        url: str | None = LIST_PATH
        emails: list[Email] = []
        newest = ""
        while url and (limit is None or len(emails) < limit):
            page = self._request("GET", url, params=params)
            url, params = page.get("@odata.nextLink"), None
            for item in page.get("value", []):
                newest = max(newest, item.get("receivedDateTime") or "")
                if limit is not None and len(emails) >= limit:
                    # A capped fetch never moves the cursor, so stop reading.
                    break
                if not self._is_processed(item):
                    emails.append(self._email(item))
        complete = url is None and (limit is None or len(emails) < limit)
        # A fetch that returned nothing moves no cursor, so a dry run never writes one (A9).
        self._pending = (newest, {m.uid for m in emails}) if complete and emails and newest else None
        return emails

    def fetch_senders(self, limit: int | None = None) -> list[tuple[str, str]]:
        """(From, List-Unsubscribe) of the newest `limit` messages in every folder, for `census`."""
        params: dict | None = {"$select": "from,internetMessageHeaders", "$orderby": "receivedDateTime desc", "$top": str(PAGE_SIZE)}
        url: str | None = ALL_MAIL_PATH
        rows: list[tuple[str, str]] = []
        while url and (limit is None or len(rows) < limit):
            page = self._request("GET", url, params=params)
            url, params = page.get("@odata.nextLink"), None
            for item in page.get("value", []):
                mail = self._email({"id": "", **item})
                rows.append((mail.sender, mail.list_unsubscribe))
        return rows[:limit]

    def folder_mail(self, folder: str, marker: str) -> list[tuple[int | str, str, bool]]:
        """(id, From, carries the `marker` category) for every message in the top-level `folder`, for `clean`."""
        escaped = folder.replace("'", "''")
        found = self._request("GET", "/me/mailFolders", params={"$filter": f"displayName eq '{escaped}'"}).get("value")
        if not found:
            return []
        params: dict | None = {"$select": "id,from,categories", "$top": str(PAGE_SIZE)}
        url: str | None = f"/me/mailFolders/{found[0]['id']}/messages"
        rows: list[tuple[int | str, str, bool]] = []
        while url:
            page = self._request("GET", url, params=params)
            url, params = page.get("@odata.nextLink"), None
            for item in page.get("value", []):
                rows.append((item["id"], self._email(item).sender, marker in (item.get("categories") or [])))
        return rows

    def trash(self, folder: str, uids: list[int | str]) -> None:
        for uid in uids:
            # A well-known folder name is a valid destinationId.
            self._request("POST", f"{_message_path(uid)}/move", json={"destinationId": "deleteditems"})

    def mark_processed(self, uid: int | str) -> None:
        self.add_tag(uid, PROCESSED_CATEGORY)
        if self._pending is not None:
            self._pending[1].discard(uid)

    def add_tag(self, uid: int | str, value: str) -> None:
        categories = self._request("GET", _message_path(uid), params={"$select": "categories"}).get("categories", [])
        if value not in categories:
            self._request("PATCH", _message_path(uid), json={"categories": [*categories, value]})

    def move(self, uid: int | str, folder: str) -> None:
        self._request("POST", f"{_message_path(uid)}/move", json={"destinationId": self._folder_id(folder)})

    def set_flag(self, uid: int | str, flagged: bool) -> None:
        self._request("PATCH", _message_path(uid), json={"flag": {"flagStatus": "flagged" if flagged else "notFlagged"}})

    def set_seen(self, uid: int | str, seen: bool) -> None:
        self._request("PATCH", _message_path(uid), json={"isRead": seen})

    def supports_idle(self) -> bool:
        return False

    def _open_state(self) -> None:
        # Read only when cli has created it; a dry run never does.
        db = self._config_dir / "state.db"
        if self._state is None and db.exists():
            self._state = State(db)

    def _advance_cursor(self) -> None:
        # Moves only after a complete fetch whose every returned message was marked (A3).
        pending, self._pending = self._pending, None
        if pending is not None and not pending[1] and self._state is not None:
            self._state.set_cursor(self._account_key, pending[0])

    def _is_processed(self, item: dict) -> bool:
        if PROCESSED_CATEGORY in (item.get("categories") or []):
            return True
        key = item.get("internetMessageId") or f"uid:{item['id']}"
        return self._state is not None and self._state.has(self._account_key, key)

    @staticmethod
    def _email(item: dict) -> Email:
        sender = (item.get("from") or {}).get("emailAddress") or {}
        headers = {h["name"].lower(): h["value"] for h in item.get("internetMessageHeaders") or []}
        return Email(
            uid=item["id"],
            subject=item.get("subject") or "",
            body=(item.get("body") or {}).get("content") or "",
            message_id=item.get("internetMessageId") or "",
            sender=formataddr((sender.get("name") or "", sender.get("address") or "")),
            list_unsubscribe=headers.get("list-unsubscribe", ""),
        )

    def _folder_id(self, name: str) -> str:
        # Top-level folders only (Known limits).
        if name not in self._folders:
            escaped = name.replace("'", "''")
            found = self._request("GET", "/me/mailFolders", params={"$filter": f"displayName eq '{escaped}'"})
            if found.get("value"):
                self._folders[name] = found["value"][0]["id"]
            else:
                self._folders[name] = self._request("POST", "/me/mailFolders", json={"displayName": name})["id"]
        return self._folders[name]

    def _request(self, method: str, url: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self._token()}", "Prefer": PREFER}
        try:
            response = self._http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise GraphError(f"{method} {url} failed: {exc}") from exc
        if response.is_error:
            # No retry: a 429 or 5xx stops the account for this run (A6).
            raise GraphError(f"{method} {response.url.path} returned {response.status_code}: {response.text[:300]}")
        try:
            return response.json() if response.content else {}
        except ValueError as exc:
            raise GraphError(f"{method} {response.url.path} returned {response.status_code} with a body that is not JSON") from exc


def _message_path(uid: int | str) -> str:
    # An id may hold "/", "+" or "=", so it is quoted as one path segment.
    return f"/me/messages/{quote(str(uid), safe='')}"


def _token_source(token: Path, username: str) -> Callable[[], str]:
    """Returns a callable that gives a valid access token, renewing it from the
    refresh token and saving the cache when MSAL changed it."""
    if not token.exists():
        raise ConfigError(f"no Office 365 token at {token} -- run `jev-mail auth-o365`")
    import msal

    cache = msal.SerializableTokenCache()
    try:
        cache.deserialize(token.read_text())
    except (OSError, ValueError) as exc:
        raise GraphError(f"unreadable Office 365 token at {token} -- run `jev-mail auth-o365`") from exc
    with _reaching_microsoft():
        app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    account = next((a for a in app.get_accounts() if a.get("username", "").lower() == username.lower()), None)
    if account is None:
        raise GraphError(f"no Office 365 sign-in for {username} in {token} -- run `jev-mail auth-o365`")

    def access_token() -> str:
        with _reaching_microsoft():
            result = app.acquire_token_silent_with_error(SCOPES, account)
        if not result or "access_token" not in result:
            error = result.get("error") if result else "no cached token"
            raise GraphError(f"Office 365 sign-in for {username} failed ({error}) -- run `jev-mail auth-o365`")
        if cache.has_state_changed:
            _save_cache(token, cache)
            cache.has_state_changed = False
        return result["access_token"]

    # Run once on enter, so a rejected refresh token stops the account before any Graph call.
    access_token()
    return access_token


def authorize_o365(config_dir: str | Path) -> Path:
    """Runs the one-time device-code sign-in and writes the token file; returns its path."""
    import msal

    token = Path(config_dir) / TOKEN_FILE
    cache = msal.SerializableTokenCache()
    if token.exists():
        # Keeps the accounts already signed in; the file can hold several.
        try:
            cache.deserialize(token.read_text())
        except (OSError, ValueError):
            # This command is the repair for an unreadable file, so it starts a new cache (A10).
            cache = msal.SerializableTokenCache()
    with _reaching_microsoft():
        app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise GraphError(f"Office 365 sign-in did not start ({flow.get('error')}): {flow.get('error_description')}")
        print(flow["message"], flush=True)
        result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise GraphError(f"Office 365 sign-in failed ({result.get('error')}): {result.get('error_description')}")
    _save_cache(token, cache)
    return token


@contextmanager
def _reaching_microsoft() -> Iterator[None]:
    # msal reaches Microsoft through `requests`, whose errors are OSError.
    try:
        yield
    except OSError as exc:
        raise GraphError(f"Office 365 sign-in could not reach Microsoft ({exc})") from exc


def _save_cache(token: Path, cache) -> None:
    try:
        _write_token(token, cache.serialize())
    except OSError as exc:
        raise GraphError(f"could not write the Office 365 token to {token} ({exc})") from exc
