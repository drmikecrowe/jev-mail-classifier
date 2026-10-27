# GH-4: Gmail backend over the Gmail API

## Summary

This change lets `jev-mail` classify a Gmail account through the Gmail API, so a tag shows up as a real Gmail label. Today every account is IMAP, and an IMAP keyword never shows as a label in the Gmail web UI. The issue's final comment (2026-10-25) drops the IMAP + app password plan in its body and asks for a port of the email-triage Gmail API adapter; the engineer confirmed that on 2026-10-27.

What changes: a new backend, `GmailMailbox` in `jev_mail/mailbox/gmail.py`, implements the existing `MailBackend` interface with the Gmail API. An account picks it with `backend: gmail` in `config.yaml`; an account with no `backend` key stays IMAP. A new `jev-mail auth-gmail` command runs the one-time Google sign-in in a browser and saves the token beside `config.yaml`. `run` and `watch` open the right backend for each account. Two Google libraries become dependencies. The token file and the Google client secret file are git-ignored.

The acceptance criteria, in plain words:

- Unprocessed Gmail mail is the mail in the watched label without the `JevProcessed` label, newest first, capped at `max_emails_per_run`, parsed the same way as IMAP mail.
- A `tag` action adds a Gmail label of that name, and creates the label when it does not exist yet.
- A `move` action adds the folder's label and takes the mail out of the inbox. A `move` to `[Gmail]/All Mail` only takes it out of the inbox (archive).
- `flag` and `mark_read` map to Gmail's star and unread labels. Processed mail gets the `JevProcessed` label, so a second run skips it.
- `auth-gmail` writes the token, readable by its owner only. `run` without a token stops with a message that names `auth-gmail`. A Google error stops the run with a readable message, not a traceback.
- A config can mix IMAP and Gmail accounts in an `accounts:` list. `watch` polls a Gmail account, because Gmail has no IDLE.

What must not change: IMAP behavior and every existing test; the `config.yaml` that the wizard writes for an IMAP account; no secret or token is committed or printed; tests make no network call.

How each criterion is proven: unit tests with a fake Gmail service object for the backend, tests for the config and CLI wiring, a gitleaks scan and a diff reading for the secrets, and one live run against the engineer's Gmail account for the issue's own check.

Open decisions: none.

## Orientation

- Lane: engineering, because this is Phase 3 of the engineer-owned epic #7, specified by the engineer in the issue and its decision comments; there is no product author.
- Change: add a Gmail API backend behind `MailBackend`, an `auth-gmail` command, and a per-account `backend` key.
- Why: Gmail shows IMAP keywords as nothing, so tags applied over IMAP are invisible in Gmail, and the engineer chose the Gmail API over app passwords.
- Touches: `jev_mail/mailbox/gmail.py` (new), `jev_mail/mailbox/base.py`, `jev_mail/mailbox/__init__.py`, `jev_mail/config.py`, `jev_mail/cli.py`, `jev_mail/tui/screens/mailbox_screen.py`, `pyproject.toml`, `uv.lock`, `.gitignore`, `README.md`, `CLAUDE.md`, and tests.
- Decide: Decide 1, how a Gmail id fits `uid: int`; Decide 2, how the first sign-in happens; Decide 3, what `move` means on Gmail.
- Decided: Decide 1 ruled that `uid` is annotated `int | str` and Gmail ids pass through as strings; it governs S1.1 and S6.1 (Mike Crowe, 2026-10-27). Decide 2 ruled a separate `auth-gmail` subcommand, with `run` and `watch` refusing when no token exists; it governs S4 (Mike Crowe, 2026-10-27). Decide 3 ruled that `move` adds the folder's label and removes `INBOX`, and `move` to `[Gmail]/All Mail` only removes `INBOX`; it governs S2.3 and S2.4 (Mike Crowe, 2026-10-27).

- Tier: 2
- Issue: GH-4
- Isolation: branch `GH-4-gmail` from `master` at `dca1f05`, in the main checkout, because this project uses no worktrees.

## Definitions

- **Config directory**: the directory that holds `config.yaml`, which is `--dir`.
- **Token file**: `<config directory>/gmail-token.json`, the authorized-user JSON of `google.oauth2.credentials.Credentials.to_json()`.
- **Client secret file**: `<config directory>/client_secrets.json`, the Desktop OAuth client file that the engineer downloads from Google Cloud Console.
- **Scope**: `https://www.googleapis.com/auth/gmail.modify`.
- **Fake service**: a `MagicMock` passed as `GmailMailbox(account, config_dir, service=fake)`, in place of `googleapiclient.discovery.build(...)`. Its `labels().list(userId="me").execute()` returns `{"labels": [...]}`, each label a `{"id", "name"}` dict. System labels have `id == name`: `INBOX`, `STARRED`, `UNREAD`.
- **Raw message**: `messages().get(userId="me", id=<id>, format="raw").execute()` returns `{"id": <id>, "raw": <URL-safe base64 of the RFC 822 bytes>}`.
- **GmailError**: an exception class in `gmail.py`. Every Gmail API call and every token refresh raises it in place of `googleapiclient.errors.HttpError` or `google.auth.exceptions.GoogleAuthError`, with the original message.

## Scenarios

All Gmail scenarios use the fake service and an account `MailboxConfig(backend="gmail", host="gmail.googleapis.com", username="me@example.com", folder="INBOX")`, unless they say otherwise. "Labels L" means `labels().list` returns L.

### S1. Fetch unprocessed Gmail mail
- S1.1 Given labels `INBOX` and `{"id": "Label_9", "name": "JevProcessed"}`, `messages().list` returning `{"messages": [{"id": "b2"}, {"id": "a1"}]}`, and each raw message holding `Subject: Invoice 12`, `From: Billing <billing@example.com>`, `Message-ID: <m1@example.com>`, `List-Unsubscribe: <mailto:u@example.com>` and a `text/plain` body `Amount due`, when `fetch_unprocessed(limit=25)` runs, then `messages().list` is called once with `userId="me"`, `labelIds=["INBOX"]`, `q="-label:JevProcessed"`, `maxResults=25`, and it returns two `Email`s in the list order, with `uid` `"b2"` and `"a1"` (strings), and subject, sender, message_id, list_unsubscribe and body equal to those header values and `Amount due`.
- S1.2 (boundary) Given `messages().list` returns `{"resultSizeEstimate": 0}` with no `messages` key, when `fetch_unprocessed(limit=25)` runs, then it returns `[]` and `messages().get` is never called.
- S1.3 (negative) Given labels `INBOX` only and an account with `folder="Work"`, when the mailbox is entered, then it raises `ConfigError` whose message names `Work`.

### S2. Actions on Gmail
- S2.1 Given labels `INBOX` and `{"id": "Label_1", "name": "BULK"}`, when `add_tag("b2", "BULK")` runs, then `messages().modify` is called with `userId="me"`, `id="b2"`, `body={"addLabelIds": ["Label_1"]}`, and `labels().create` is never called.
- S2.2 (boundary) Given labels `INBOX` only and `labels().create(...).execute()` returning `{"id": "Label_7", "name": "BULK"}`, when `add_tag("b2", "BULK")` runs twice, then `labels().create` is called once, with `userId="me"`, `body={"name": "BULK"}`, and both `modify` calls carry `{"addLabelIds": ["Label_7"]}`.
- S2.3 Given labels `INBOX` and `{"id": "Label_3", "name": "Receipts"}`, when `move("b2", "Receipts")` runs, then `modify` is called with `body={"addLabelIds": ["Label_3"], "removeLabelIds": ["INBOX"]}` (Decide 3, Mike Crowe, 2026-10-27).
- S2.4 (boundary) Given labels `INBOX` only, when `move("b2", "[Gmail]/All Mail")` runs, then `modify` is called with `body={"removeLabelIds": ["INBOX"]}` and `labels().create` is never called (Decide 3, Mike Crowe, 2026-10-27).
- S2.5 When `set_flag("b2", True)`, `set_flag("b2", False)`, `set_seen("b2", True)` and `set_seen("b2", False)` run, then the `modify` bodies are, in order, `{"addLabelIds": ["STARRED"]}`, `{"removeLabelIds": ["STARRED"]}`, `{"removeLabelIds": ["UNREAD"]}`, `{"addLabelIds": ["UNREAD"]}`.
- S2.6 Given labels `INBOX` only and `labels().create` returning `{"id": "Label_9", "name": "JevProcessed"}`, when `mark_processed("b2")` runs, then `labels().create` is called with `body={"name": "JevProcessed"}` and `modify` with `body={"addLabelIds": ["Label_9"]}`. `supports_idle()` returns `False`.
- S2.7 (negative) Given `modify(...).execute()` raises `googleapiclient.errors.HttpError` with status 403, when `add_tag("b2", "BULK")` runs, then it raises `GmailError` whose message holds `403`.

### S3. Config
- S3.1 Given an `accounts:` list holding `{host: imap.example.com, username: u, password: p}` and `{backend: gmail, username: me@example.com}`, when `load_config` runs, then the first account has `backend == "imap"` and the second has `backend == "gmail"` and `host == "gmail.googleapis.com"`, with no `ConfigError`.
- S3.2 (negative) Given `mailbox: {backend: pop3, host: imap.example.com}`, when `load_config` runs, then it raises `ConfigError` whose message names `imap, gmail`.
- S3.3 (negative) Given `mailbox: {username: u}` with no `backend` and no `host`, when `load_config` runs, then it raises the existing empty-host `ConfigError`.
- S3.4 Given a loaded config whose first account has `backend: gmail`, when `save_config` writes it, then the written `mailbox:` block holds `backend: gmail`. Given an IMAP first account, the written block holds no `backend` key.
- S3.5 Given a `config.yaml` whose `mailbox:` block has `backend: gmail`, when the configure wizard runs through all three screens with no field changed and saves, then the written `mailbox:` block still holds `backend: gmail`.

### S4. Sign-in and token (Decide 2, Mike Crowe, 2026-10-27)
- S4.1 Given a client secret file in `--dir D` and `InstalledAppFlow` replaced by a fake whose `run_local_server(port=0)` returns credentials with `to_json()` = `{"token": "t"}`, when `jev-mail --dir D auth-gmail` runs, then the flow is built with `from_client_secrets_file(D/client_secrets.json, [scope])`, `D/gmail-token.json` holds `{"token": "t"}` with file mode `0600`, stdout holds `D/gmail-token.json` and not `{"token": "t"}`, and the exit code is 0.
- S4.2 (negative) Given no client secret file in `D`, when `jev-mail --dir D auth-gmail` runs, then the exit code is 1, stderr names `D/client_secrets.json` and says to create a Desktop OAuth client with the Gmail API enabled, and no token file is written.
- S4.3 (negative) Given a config with one Gmail account and no token file, when `jev-mail --dir D run` runs, then stderr holds `error: no Gmail token at D/gmail-token.json -- run \`jev-mail auth-gmail\``, the exit code is 1, and no Gmail API call is made.
- S4.4 (boundary) Given a token file whose credentials are expired and hold a refresh token, and a fake refresh that sets the token to `t2`, when the mailbox is entered with no injected service, then the credentials are refreshed before the service is built, and the token file is rewritten with the refreshed JSON at mode `0600`.
- S4.5 (negative) Given `GmailMailbox` raises `GmailError("invalid_grant")` on enter, when `run` processes that account, then stderr holds `error: Gmail API error for me@example.com -- invalid_grant` and the exit code is 1.

### S5. CLI wiring
- S5.1 Given an `accounts:` list of one IMAP account and one Gmail account, both `Mailbox` and `GmailMailbox` in `jev_mail.cli` replaced by recording fakes, when `run --dry-run` runs, then `Mailbox` is built with the IMAP account, `GmailMailbox` is built with the Gmail account and the config directory, each is entered once, and the exit code is 0.
- S5.2 Given a single Gmail account with `poll_interval_seconds: 7`, a fake `GmailMailbox` whose `supports_idle()` is `False`, and `time.sleep` replaced by a fake that records its argument and raises `KeyboardInterrupt`, when `watch` runs, then `idle` is never called and the fake sleep is called with `7`.

### S6. Shared interface
- S6.1 Given an `Email` with `uid="b2"` and an empty `message_id`, when `State.record` writes it, then the row's `message_id` is `uid:b2` (Decide 1, Mike Crowe, 2026-10-27).
- S6.2 Given a fresh Python process, when it runs `import jev_mail.cli`, then neither `googleapiclient` nor `google_auth_oauthlib` is in `sys.modules`.

### S7. Live check
- S7.1 Given the engineer's Gmail account with the README's Google Cloud setup done, `auth-gmail` run once, a `senders.csv` row marking a second address of the engineer's as `unsubscribe`, and a `BULK` category whose actions are `tag BULK` and `move [Gmail]/All Mail`, when a message from that address arrives and `./jev-mail run` runs, then in the Gmail web UI the message carries the `BULK` and `JevProcessed` labels and is not in the inbox; and a second `./jev-mail run --dry-run` prints no line for its subject.

## Must NOT
- M1. Every test that passes on `master` at `dca1f05` still passes, unedited.
- M2. For an IMAP-only config, `save_config` writes the same YAML as on `master`.
- M3. `client_secrets.json` and `gmail-token.json` are listed in `.gitignore` and never committed; no token or secret value is printed, logged or written to `state.db`.
- M4. The token file is written with mode `0600` on every write.
- M5. `MailBackend` keeps its six method names and their parameter names; only the `uid` annotation changes.
- M6. No test makes a network call: every Gmail test injects the fake service or fakes the flow.

## Touches
- `jev_mail/mailbox/gmail.py` (new): `GmailMailbox`, `GmailError`, `SCOPES`, the token load, refresh and write, label lookup and creation, and the six `MailBackend` methods plus `supports_idle`.
- `jev_mail/mailbox/base.py`: `uid` annotated `int | str` in `Email` and `MailBackend`.
- `jev_mail/mailbox/__init__.py`: export `GmailMailbox` and `GmailError`.
- `jev_mail/config.py`: `BACKENDS = ("imap", "gmail")`, `MailboxConfig.backend`, `_load_account` validation and the Gmail host default, `save_config` writes `backend` when it is not `imap`.
- `jev_mail/cli.py`: `_open_mailbox(account, config_dir)` used by `run` and `watch`, `ConfigError` and `GmailError` in their except tuples, the Gmail line of `_mailbox_error_message`, and the `auth-gmail` subcommand.
- `jev_mail/tui/screens/mailbox_screen.py`: the dismissed `MailboxConfig` keeps the account's `backend`.
- `pyproject.toml`, `uv.lock`: `google-api-python-client` and `google-auth-oauthlib`.
- `.gitignore`: `client_secrets.json` and `gmail-token.json`.
- `tests/test_gmail.py` (new): S1, S2, S4.4, S6.2.
- `tests/test_config.py`: S3.1 to S3.4. `tests/test_tui.py`: S3.5. `tests/test_cli.py`: S4.1 to S4.3, S4.5, S5. `tests/test_state.py`: S6.1.

## Documentation
- `README.md`, section "Getting your IMAP username & password": a new "Gmail API" subsection with the Google Cloud setup (create a Desktop OAuth client, enable the Gmail API, add the account as a test user, save `client_secrets.json` beside `config.yaml`), `auth-gmail`, the `backend: gmail` key, and what `tag` and `move` do on Gmail, including `[Gmail]/All Mail` as archive.
- `CLAUDE.md`, sections "Commands" and "Architecture": the `auth-gmail` command, the Gmail backend in step 1 and step 5, and the `backend` key and the two git-ignored files in the Config paragraph.

## Known limits
- One Gmail account per config directory, because the token file has a fixed name.
- The configure wizard cannot set up a Gmail account: `backend: gmail` is written by hand, and the wizard's mailbox screen still asks for a host.
- `watch` polls a Gmail account every `poll_interval_seconds`; it does not use Gmail push notifications.
- Gmail returns at most 500 messages per `messages().list` page, so a `max_emails_per_run` above 500 processes 500 per run.
- `move` always removes `INBOX`, even when the account watches another label, so a `move` from a watched label `Work` leaves the `Work` label on the mail (Decide 3).
- S7.1 needs the engineer's Google Cloud setup and sign-in; the build cannot run it without them.

## Verification contract

| Layer | What it gates | Threshold |
|---|---|---|
| tests | S1.1 to S6.2, M1, M2, M4, M5, M6 | `mise exec -- uv run pytest -q` exits 0 |
| secrets | committed content, M3 | `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` reports no leak |
| diff reading | M3, M5, the Documentation entries | `git check-ignore client_secrets.json gmail-token.json` prints both; `git diff master -- jev_mail/mailbox/base.py` changes only annotations |
| live run | S7.1 | the labels and the inbox state seen in the Gmail web UI; the second dry run prints no line for the subject |
