# GH-5: Office 365 backend over Microsoft Graph

## Summary

This change lets `jev-mail` classify an Office 365 Inbox through Microsoft Graph. The pinnsg.com tenant has basic auth off, so IMAP cannot reach it.

What changes: a new backend, `GraphMailbox` in `jev_mail/mailbox/graph.py`, implements the existing `MailBackend` interface with Graph REST calls over `httpx`. An account picks it with `backend: o365` in `config.yaml`. A new `jev-mail auth-o365` command runs the one-time device-code sign-in and saves the token cache beside `config.yaml`. `run` and `watch` open the right backend for each account. `msal` becomes a dependency. The token file is git-ignored. `state.db` gets a small table that holds one fetch cursor per account, and `GraphMailbox` reads `state.db` to skip mail it already processed.

The acceptance criteria, in plain words:

- `auth-o365` shows a sign-in URL and code, then saves the token file, readable by its owner only. With no token file, `run` and `watch` stop before any Graph call and name `auth-o365`.
- An expired access token is renewed from the refresh token with no prompt, and the renewed cache is saved. A rejected refresh token stops the account with a message that names `auth-o365`.
- `run` fetches Inbox mail that has no `JevProcessed` category and no `state.db` row, newest first, capped at `max_emails_per_run`, with text bodies. Mail older than the account's cursor is not fetched.
- With 30 new messages and a cap of 25, one run takes the newest 25 and the next run takes the other 5. The cursor never passes a message that was not processed.
- `tag` adds an Outlook category and keeps the others, with no duplicate.
- `move` moves the message to a top-level folder, and creates the folder when it is missing. Only the first `move` among the matched categories runs.
- `flag`, `unflag`, `mark_read` and `mark_unread` set the flag and read state only. Processed mail gets the `JevProcessed` category and a `state.db` row; a dry run adds neither.
- `watch` on one `o365` account polls every `poll_interval_seconds`.

What must not change: IMAP and Gmail behavior and every existing test; the YAML `save_config` writes for an IMAP or Gmail account; no token is committed or printed; tests make no network call.

How each criterion is proven: unit tests with a fake Graph server (`httpx.MockTransport`) and a fake `msal` app, tests for the config, state and CLI wiring, a gitleaks scan and a `git check-ignore` reading for the token file, and one live run against the engineer's pinnsg.com mailbox for the story's example.

Open decisions: none. Decide 1 is ruled: the cursor is a table in `state.db`.

## Orientation

- Change: add a Microsoft Graph backend behind `MailBackend`, an `auth-o365` command, the `o365` backend value, and a per-account fetch cursor.
- Why: the pinnsg.com Office 365 tenant has basic auth off, so the IMAP backend cannot sign in.
- Touches: `jev_mail/mailbox/graph.py` (new), `jev_mail/mailbox/__init__.py`, `jev_mail/config.py`, `jev_mail/state.py`, `jev_mail/cli.py`, `pyproject.toml`, `uv.lock`, `.gitignore`, `README.md`, `CLAUDE.md`, and tests.
- Decide: Decide 1, where the per-account cursor is stored.
- Decided: Decide 1 ruled a `cursor` table in `state.db`, keyed by the account key; it governs "The cursor" and S2.3 to S2.7 (Mike Crowe, 2026-10-30). Decide 2 ruled that an `o365` account always reads the Inbox and ignores its `folder` key, with no refusal; it governs the Known limits line on the Inbox (Mike Crowe, 2026-10-30).

- Tier: 2
- Issue: GH-5
- Isolation: branch `GH-5-o365` from `master` at `6fa85f3`, in the main checkout, because this project uses no worktrees.

## Definitions

- **Config directory**: the directory that holds `config.yaml`, which is `--dir`.
- **Token file**: `<config directory>/o365-token.json`, the serialized `msal.SerializableTokenCache`.
- **Client id**: `14d82eec-204b-4c2f-b7e8-296a70dab67e`, Microsoft Graph Command Line Tools.
- **Authority**: `https://login.microsoftonline.com/organizations`.
- **Scopes**: `["Mail.ReadWrite"]`. MSAL adds `offline_access` itself and raises `ValueError` when it is passed, so the requested scopes are `Mail.ReadWrite offline_access`.
- **Account key**: `<host>/<username>`, the key `cli._process_unprocessed` already writes to `state.db`. An `o365` account with no `host` gets host `graph.microsoft.com`.
- **Message key**: the message's `internetMessageId`, or `uid:<id>` when it is empty, the key `State.record` already writes.
- **Graph base**: `https://graph.microsoft.com/v1.0`.
- **Prefer header**: every Graph request sends `Prefer: outlook.body-content-type="text", IdType="ImmutableId"`. An immutable id does not change when the message moves to another folder of the same mailbox, so `mark_processed` after `move` still finds the message.
- **Fake Graph**: an `httpx.Client(base_url=<Graph base>, transport=httpx.MockTransport(handler))` passed as `GraphMailbox(account, config_dir, http=fake, token=lambda: "t")`. The handler records each request and answers from a dict of canned responses.
- **Fake msal**: `msal.PublicClientApplication` replaced through `monkeypatch` by a class whose `get_accounts`, `acquire_token_silent_with_error`, `initiate_device_flow` and `acquire_token_by_device_flow` return canned values, and that uses the real `SerializableTokenCache` passed to it.
- **GraphError**: an exception class in `graph.py`. A non-2xx Graph response, an `httpx` transport error, or a failed token renewal raises it, with the status code or the error text.
- **Cursor**: the newest `receivedDateTime` string seen in a complete fetch, stored per account key. See "The cursor".
- **Message JSON**: one item of a list page, with keys `id`, `subject`, `body` (`{"contentType": "text", "content": ...}`), `from` (`{"emailAddress": {"name", "address"}}`), `internetMessageId`, `categories`, `receivedDateTime` and `internetMessageHeaders` (a list of `{"name", "value"}`).

## The cursor

This section answers where the per-account cursor is stored (the story's SR-DEFER note, for AC-3 and AC-4).

- Storage: a table `cursor (account TEXT PRIMARY KEY, received_at TEXT NOT NULL)` in `state.db`, beside `config.yaml`, keyed by the account key (Decide 1, Mike Crowe, 2026-10-30). `State` gets three methods: `has(account_key, message_key) -> bool`, `cursor(account_key) -> str | None` and `set_cursor(account_key, received_at)`.
- Read: at the start of every `fetch_unprocessed`, `GraphMailbox` checks for `<config directory>/state.db`. When the file exists, it opens it through `State` (once per session) and reads the cursor and the processed rows. With no file there is no cursor and no row, so the whole Inbox is eligible. A `state.db` that `cli` creates after the mailbox opened, as on a first `watch`, is read from the next fetch on.
- Fetch: with a cursor, the list request carries `$filter=receivedDateTime ge <cursor>`. With none, it carries no `$filter`. Both carry `$orderby=receivedDateTime desc` and `$top=50`.
- Advance: a fetch is complete when it returned fewer messages than its `limit` and the page walk ended because the last page had no `@odata.nextLink`. A fetch that returned exactly `limit` messages is capped, even when its last page had no `@odata.nextLink`. The cursor moves to the newest `receivedDateTime` seen in that page walk, returned or skipped, only when the fetch was complete, the walk saw at least one message, and `mark_processed` ran for every message the fetch returned. A skipped message is already processed, so moving past it loses nothing. The move happens at the start of the next `fetch_unprocessed` and on exit from the mailbox. Otherwise the cursor stays.
- A dry run never calls `mark_processed`, so it never moves the cursor and never creates `state.db`.

## Scenarios

All Graph scenarios use the fake Graph and an account `MailboxConfig(backend="o365", host="graph.microsoft.com", username="me@example.com", folder="INBOX", max_emails_per_run=25)`, unless they say otherwise. "The list request" is `GET /me/mailFolders/inbox/messages`.

### S1. Sign-in and token (AC-1, AC-2)
- S1.1 Given an empty config directory `D` and the fake msal, whose `initiate_device_flow(scopes=["Mail.ReadWrite"])` returns `{"user_code": "ABC123", "message": "To sign in, open https://microsoft.com/devicelogin and enter ABC123"}` and whose `acquire_token_by_device_flow` adds an account to the cache and returns `{"access_token": "t"}`, when `jev-mail --dir D auth-o365` runs, then the app is built with the client id, the authority and that cache, stdout holds the flow's `message` and `D/o365-token.json`, `D/o365-token.json` holds the serialized cache with file mode `0600`, stdout does not hold `t`, and the exit code is 0.
- S1.2 (negative) Given the fake msal whose `acquire_token_by_device_flow` returns `{"error": "authorization_declined", "error_description": "denied"}`, when `jev-mail --dir D auth-o365` runs, then stderr holds `authorization_declined`, the exit code is 1, and no token file is written.
- S1.3 (boundary) Given a config with one `o365` account and no token file, when `jev-mail --dir D run` runs, then stderr holds `error: no Office 365 token at D/o365-token.json -- run \`jev-mail auth-o365\``, the exit code is 1, and the fake Graph handler gets no request. The same holds for `watch`.
- S1.4 (boundary) Given a token file and the fake msal whose `acquire_token_silent_with_error(["Mail.ReadWrite"], account)` changes the cache (a renewal from the refresh token) and returns `{"access_token": "t2"}`, when the mailbox is entered with no injected `token`, then `initiate_device_flow` is never called, the token file is rewritten with the new cache at mode `0600`, and the next Graph request carries `Authorization: Bearer t2`.
- S1.5 (boundary) Given an entered mailbox whose token source returns `t1` and then `t2`, when two Graph requests run, then the first carries `Bearer t1` and the second `Bearer t2`, because the token source runs before every request.
- S1.6 (negative) Given a token file and the fake msal whose `acquire_token_silent_with_error` returns `{"error": "invalid_grant", "error_description": "AADSTS70043"}`, when `run` processes that account, then stderr holds `error: Microsoft Graph error for me@example.com -- Office 365 sign-in for me@example.com failed (invalid_grant) -- run \`jev-mail auth-o365\``, the exit code is 1, `initiate_device_flow` is never called, and the fake Graph handler gets no request.
- S1.7 (negative) Given a token file whose cache holds no account with username `me@example.com`, when the mailbox is entered, then it raises `GraphError` whose message names `me@example.com` and `jev-mail auth-o365`.
- S1.8 (negative) Given the repository after this change, when `git check-ignore o365-token.json` runs, then it prints `o365-token.json` and exits 0.

### S2. Fetch (AC-3, AC-4)
- S2.1 Given no `state.db` and one list page with message JSON `id "m1"`, `subject "Invoice 12"`, `body.content "Amount due"`, `from {"name": "Billing", "address": "billing@example.com"}`, `internetMessageId "<m1@example.com>"`, `categories []`, `receivedDateTime "2026-10-30T10:00:00Z"` and header `List-Unsubscribe: <mailto:u@example.com>`, and no `@odata.nextLink`, when `fetch_unprocessed(limit=25)` runs, then the list request carries the header `Prefer: outlook.body-content-type="text", IdType="ImmutableId"`, `$orderby=receivedDateTime desc`, `$top=50`, a `$select` that names every message JSON key, and no `$filter`; and it returns one `Email` with `uid "m1"`, subject `Invoice 12`, body `Amount due`, sender `Billing <billing@example.com>`, message_id `<m1@example.com>` and list_unsubscribe `<mailto:u@example.com>`.
- S2.2 Given a list page of three messages, `m3` with categories `["JevProcessed"]`, `m2` whose message key has a `state.db` row for account key `graph.microsoft.com/me@example.com` and no categories, and `m1` with neither, when `fetch_unprocessed(limit=25)` runs, then it returns only `m1`.
- S2.3 (boundary) Given a `state.db` whose cursor for the account key is `2026-10-30T09:00:00Z`, when `fetch_unprocessed(limit=25)` runs, then the list request carries `$filter=receivedDateTime ge 2026-10-30T09:00:00Z` and `$orderby=receivedDateTime desc`.
- S2.4 (negative) Given that cursor, and a message moved back into the Inbox with `receivedDateTime "2026-10-29T08:00:00Z"`, when `fetch_unprocessed` runs, then the message is not returned, because the server filter excludes it (the fake Graph applies the `ge` filter to its canned messages).
- S2.5 Given 30 eligible messages `n30` (newest) to `n1` on one page and `max_emails_per_run: 25`, when `run` processes the account twice with no category matched, then the first run marks `n30` to `n6`, in that order, and the second run marks `n5` to `n1`.
- S2.6 (boundary) Given the run of S2.5, when the first run ends, then the cursor is unset, because that fetch reached the cap. When the second run ends, the cursor is `n30`'s `receivedDateTime`, the newest seen in that complete walk, and a third run's list request carries `$filter=receivedDateTime ge <n30's receivedDateTime>`.
- S2.7 (boundary) Given a complete fetch of `m2` and `m1`, and a classify call that raises `ProviderError` for `m1`, when the pass ends and the next `fetch_unprocessed` starts, then the cursor is not moved, and `m1` is returned again.
- S2.8 (negative) Given a cursor `C`, a pass that processes every fetched message, and a message `m9` that arrives during that pass with a `receivedDateTime` after `C`, when the next pass runs, then `m9` is returned and processed.
- S2.9 (boundary) Given a first page with two processed messages and an `@odata.nextLink`, and a second page with `m1` eligible, when `fetch_unprocessed(limit=25)` runs, then it requests the `@odata.nextLink` URL as given and returns `m1`.
- S2.10 (boundary) Given a config directory with no `state.db`, a mailbox entered with it, a first pass that processes `m1` (so `cli` creates `state.db` and writes `m1`'s row), and an Outlook rule that then removes `JevProcessed` from `m1`, when the second `fetch_unprocessed` of the same session runs, then `m1` is not returned, because that fetch opened the new `state.db` and found the row.
- S2.11 (negative) Given a list request answered with status 429, when `run` processes the account, then stderr holds `error: Microsoft Graph error for me@example.com --` and `429`, and the exit code is 1.

### S3. Actions (AC-5, AC-6, AC-7)
- S3.1 Given `GET /me/messages/m1?$select=categories` returns `{"categories": ["Red"]}`, when `add_tag("m1", "BULK")` runs, then one `PATCH /me/messages/m1` is sent with the JSON body exactly `{"categories": ["Red", "BULK"]}`.
- S3.2 (boundary) Given the GET returns `{"categories": ["BULK"]}`, when `add_tag("m1", "BULK")` runs, then no PATCH is sent.
- S3.3 Given `GET /me/mailFolders?$filter=displayName eq 'Bulk'` returns `{"value": [{"id": "f1", "displayName": "Bulk"}]}`, when `move("m1", "Bulk")` runs, then `POST /me/messages/m1/move` is sent with the body `{"destinationId": "f1"}` and no `POST /me/mailFolders` is sent.
- S3.4 (boundary) Given that GET returns `{"value": []}` and `POST /me/mailFolders` with the body `{"displayName": "Bulk"}` returns `{"id": "f2"}`, when `move("m1", "Bulk")` runs twice, then the folder POST is sent once, before the first move, and both moves carry `{"destinationId": "f2"}`.
- S3.5 (negative) Given categories `A` (action `move FolderA`) and `B` (action `move FolderB`), in that config order, that both match message `m1`, when `_process_unprocessed` runs with a `GraphMailbox` on the fake Graph, then exactly one `POST /me/messages/m1/move` is sent, with `FolderA`'s folder id. The rule already lives in `cli._process_unprocessed`; this scenario proves it holds on Graph.
- S3.6 When `set_flag("m1", True)`, `set_flag("m1", False)`, `set_seen("m1", True)` and `set_seen("m1", False)` run, then four `PATCH /me/messages/m1` requests are sent with the bodies, in order, exactly `{"flag": {"flagStatus": "flagged"}}`, `{"flag": {"flagStatus": "notFlagged"}}`, `{"isRead": true}` and `{"isRead": false}`, and no other request is sent.
- S3.7 Given a run on one message `m1` with categories `[]` and no category matched, when `run` ends, then `PATCH /me/messages/m1` was sent with `{"categories": ["JevProcessed"]}` and `state.db` holds a row for account key `graph.microsoft.com/me@example.com` and message key `<m1@example.com>`.
- S3.8 (negative) Given the same message, when `run --dry-run` runs, then no PATCH, POST or move is sent, and `state.db` does not exist after it.
- S3.9 (boundary) Given message `m1`, folder `Bulk` with id `f1`, and a fake Graph that answers a request for `m1` only when it carries `IdType="ImmutableId"` in its `Prefer` header, when `move("m1", "Bulk")` and then `mark_processed("m1")` run, then the move and the `PATCH /me/messages/m1` that adds `JevProcessed` both succeed with the same id `m1`. The story does not name immutable ids; they are what lets AC-7's marker land after AC-6's move.

### S4. Config and wiring (AC-1, AC-8)
- S4.1 Given `mailbox: {backend: o365, username: me@example.com}`, when `load_config` runs, then the account has `backend == "o365"`, `host == "graph.microsoft.com"` and `poll_interval_seconds == 60`, with no `ConfigError`.
- S4.2 (negative) Given `mailbox: {backend: pop3, host: imap.example.com}`, when `load_config` runs, then the `ConfigError` message names `imap, gmail, o365`.
- S4.3 Given a loaded config whose first account has `backend: o365`, when `save_config` writes it, then the written `mailbox:` block holds `backend: o365`.
- S4.4 Given an `accounts:` list of one IMAP account and one `o365` account, with `Mailbox` and `GraphMailbox` in `jev_mail.cli` replaced by recording fakes, when `run --dry-run` runs, then `Mailbox` is built with the IMAP account, `GraphMailbox` with the `o365` account and the config directory, each is entered once, and the exit code is 0.
- S4.5 Given a single `o365` account with no `poll_interval_seconds` key, a fake `GraphMailbox` whose `supports_idle()` is `False` and whose second `fetch_unprocessed` returns a message `m9` that the first did not, and `time.sleep` replaced by a fake that records its argument and raises `KeyboardInterrupt` on its second call, when `watch` runs, then the fake sleep is first called with `60`, and `m9` is marked processed in the second pass.
- S4.6 (negative) Given an `accounts:` list of two `o365` accounts, when `watch` runs, then stderr holds `error: watch handles one account only` and the exit code is 1.
- S4.7 Given a fresh Python process, when it runs `import jev_mail.cli`, then `msal` is not in `sys.modules`.

### S5. Live check (Example)
- S5.1 Given the engineer's pinnsg.com mailbox with Step 0's tenant consent granted, `auth-o365` run once, and a `BULK` category whose actions are `tag BULK` and `move Bulk`, when a message from a second address of the engineer's that the `senders.csv` table marks `unsubscribe` arrives and `./jev-mail run` runs, then in Outlook on the web the message carries the categories `BULK` and `JevProcessed` and is in the folder `Bulk`; and a second `./jev-mail run --dry-run` prints no line for its subject.

## Must NOT
- M1. Every test that passes on `master` at `6fa85f3` still passes, unedited.
- M2. For an IMAP or Gmail config, `save_config` writes the same YAML as on `master`.
- M3. `o365-token.json` is listed in `.gitignore` and never committed; no access token, refresh token or cache text is printed, logged or written to `state.db`.
- M4. The token file is written with mode `0600` on every write.
- M5. `MailBackend` keeps its six methods and their signatures; `Mailbox` and `GmailMailbox` do not change.
- M6. No test makes a network call: every Graph test uses the fake Graph, and every sign-in test uses the fake msal.
- M7. The `processed` table of `state.db` keeps its columns and key, so an existing `state.db` opens with no migration.
- M8. The `configure` wizard does not change.

## Touches
- `jev_mail/mailbox/graph.py` (new): `GraphMailbox`, `GraphError`, `CLIENT_ID`, `AUTHORITY`, `SCOPES`, `TOKEN_FILE`, `authorize_o365`, the token source, the Graph request helper with the Prefer header, the cursor rule of "The cursor", and the six `MailBackend` methods plus `supports_idle`.
- `jev_mail/mailbox/__init__.py`: export `GraphMailbox` and `GraphError`.
- `jev_mail/config.py`: `BACKENDS = ("imap", "gmail", "o365")`, `GRAPH_HOST`, and the `o365` host default in `_load_account`.
- `jev_mail/state.py`: the `cursor` table, `State.has`, `State.cursor`, `State.set_cursor`, and the class docstring, which today says nothing reads the record.
- `jev_mail/cli.py`: `_open_mailbox` picks `GraphMailbox` for `o365`, `GraphError` in the `run` and `watch` except tuples, the Graph line of `_mailbox_error_message`, and the `auth-o365` subcommand.
- `pyproject.toml`, `uv.lock`: `msal`.
- `.gitignore`: `o365-token.json`.
- `tests/test_graph.py` (new): S1.4, S1.5, S1.7, S2.1 to S2.4, S2.9, S3.1 to S3.4, S3.6, S3.9, S4.7.
- `tests/test_cli.py`: S1.1 to S1.3, S1.6, S2.5 to S2.8, S2.10, S2.11, S3.5, S3.7, S3.8, S4.4 to S4.6. `tests/test_config.py`: S4.1, S4.2, S4.3. `tests/test_state.py`: the three new `State` methods.

## Documentation
- `README.md`, after the Gmail API subsection: a new "Office 365 (Microsoft Graph)" subsection with Step 0 (the tenant admin consent for the client id), `auth-o365`, the `backend: o365` key, the Inbox-only rule, and what `tag`, `move`, `flag` and `mark_read` do on Office 365.
- `CLAUDE.md`, sections "Commands" and "Architecture": the `auth-o365` command, the Graph backend in steps 1 and 5, the cursor table, the fact that `GraphMailbox` reads `state.db`, and the git-ignored token file.

## Known limits
- One token file per config directory. It can hold several accounts, but `auth-o365` signs in one at a time.
- Only the Inbox is watched. An `o365` account ignores its `folder` key (Decide 2, Mike Crowe, 2026-10-30).
- `move` finds and creates top-level folders only.
- A message moved back into the Inbox with a `receivedDateTime` older than the cursor is never fetched (the story accepts this).
- Until the first complete fetch sets the cursor, each run walks the Inbox from the newest message and skips processed ones on the client, so a large Inbox costs more list requests on early runs.
- No retry: a 429 or 5xx stops the account for this run, and the next run tries again.
- `watch` polls; it does not use Graph change notifications.
- S5.1 needs Step 0's tenant consent and the engineer's sign-in; the build cannot run it without them.

## Verification contract

| Layer | What it gates | Threshold |
|---|---|---|
| tests | S1.1 to S4.7, M1, M2, M4 to M8 | `mise exec -- uv run pytest -q` exits 0 |
| secrets | committed content, M3 | `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` reports no leak |
| diff reading | S1.8, M3, M5, M8, the Documentation entries | `git check-ignore o365-token.json` prints it; `git diff master -- jev_mail/mailbox/base.py jev_mail/mailbox/imap.py jev_mail/mailbox/gmail.py jev_mail/tui` is empty |
| live run | S5.1 | the categories and the folder seen in Outlook on the web; the second dry run prints no line for the subject |
