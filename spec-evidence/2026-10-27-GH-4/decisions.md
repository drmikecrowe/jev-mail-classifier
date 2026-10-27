# Decisions — GH-4: Gmail backend over the Gmail API

## Setup plan

- Isolation: branch `GH-4-gmail` from `master` at `dca1f05`, in the main checkout. This project uses no worktrees.
- Git: one commit per loop step, files staged by name, never `git add -A` (public repository, CLAUDE.md).
- New dependencies: `google-api-python-client` (the Gmail API client the email-triage adapter uses) and `google-auth-oauthlib` (the desktop OAuth flow and its `google-auth` credentials), both named by GH-4's comment of 2026-10-25 12:05.
- New files: `jev_mail/mailbox/gmail.py`, `tests/test_gmail.py`; `spec-evidence/2026-10-27-GH-4/` holds the story artifacts.
- New local data files: `client_secrets.json` (read, never written, by the code) and `gmail-token.json` (written by `auth-gmail` and by a token refresh) get `.gitignore` entries in the commit that adds `gmail.py`.
- Uncommitted change found: the working tree holds an unstaged `.atlas/` line in `.gitignore` that this story did not write. It is left unstaged, and the build stages only this story's `.gitignore` lines.
- Tooling audit: `tools/gauntlet-layers.json` declares `tests` (`mise exec -- uv run pytest -q`) and `secrets` (`mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .`); both run. Lint, format, type check, coverage, mutation and randomized order: no tool declared; these stay `UNAVAILABLE`.
- Merge gate: the repository has no `.github/` directory and no `.pre-commit-config.yaml`, as recorded for GH-8 and GH-3; 0 checks transcribed.
- Context pack: `context-pack.md` holds the agent's record verbatim. It was built from the issue body, which plans IMAP; the issue's final comment replaces that plan with the Gmail API (fact 1), so its `state.py`, TUI and `X-GM-MSGID` entries do not apply.

## Facts this SPEC rests on

1. GH-4's comments supersede its body. Comment 2026-10-25 11:41 drops step 5 (`X-GM-MSGID` dedup). Comment 12:05 describes porting the email-triage Gmail API adapter: labels applied by id, names resolved through `labels.list`, a `JevProcessed` label plus the SQLite row, the two dependencies, the token beside `config.yaml` and git-ignored. Comment 12:14 makes it final: "IMAP + app password is dropped", a new Desktop OAuth client, `client_secrets.json` beside `config.yaml`, git-ignored. — `gh issue view 4 --json comments`.
2. The engineer confirmed the Gmail API plan over the body's IMAP plan in this run (Mike Crowe, 2026-10-27).
3. The adapter to port is `/home/mcrowe/Programming/AI/certification/email-triage/src/adapters/gmail.py` (path given by the engineer). It uses `messages().list`, `messages().get`, `messages().modify` with `addLabelIds`/`removeLabelIds`, `labels().list`, `Credentials.from_authorized_user_file`, refresh with a write-back of `creds.to_json()`, and `build("gmail", "v1", credentials=creds)`; its auth flow (`src/triage.py::_auth_gmail`) uses `InstalledAppFlow`. — read.
4. `MailBackend` (`jev_mail/mailbox/base.py`) has six methods, each keyed by `uid: int`; `Email.uid` is `int`. `actions.run_action` and `cli._process_unprocessed` only pass `mail.uid` through. — read.
5. `cli.cmd_run` and `cli.cmd_watch` build `Mailbox(account)` directly (lines 154 and 182) and catch only `OSError` and `imaplib.IMAP4.error` around it (lines 161 and 193). `cmd_watch` calls `supports_idle`, `idle`, `idle_check`, `idle_done`, and sleeps `poll_interval_seconds` when `supports_idle()` is false. — read.
6. `config._load_account` raises `ConfigError` when `host` is empty; `save_config` writes a fixed key list for the first account, so an unknown key such as `backend` would be dropped on save. — read, `jev_mail/config.py`.
7. `cli._process_unprocessed` keys the state row by `f"{account.host}/{account.username}"`; `State.record` uses the `Message-ID` header, falling back to `uid:<uid>`. — read.
8. `imap.py`'s `_decode_header` and `_extract_body` parse a `email.message.Message`; Gmail's `messages().get(format="raw")` returns the RFC 822 message as URL-safe base64, so the same parsers apply. — read `imap.py`; Gmail API reference, `Message.raw`.
9. `tests/test_cli.py` replaces `cli.Mailbox` with a fake through `monkeypatch.setattr(cli, "Mailbox", ...)` (line 123). — read.
10. `pyproject.toml` declares `requires-python = ">=3.10"`, so `int | str` annotations work. — read.

## Decide calls

### Decide 1. How does a Gmail message id fit `MailBackend`, whose methods take `uid: int`?

Evidence: fact 4. Gmail API ids are hex strings such as `18c2f3a4b5d6e7f8`.

- A. Widen the `uid` annotation to `int | str` in `base.py` (`Email.uid` and the six `MailBackend` methods); `GmailMailbox` passes its id string through. Cost: a type-only change to the shared Protocol.
- B. `GmailMailbox` maps per-run integers to Gmail ids. Cost: extra state, and the `uid:<n>` state fallback and the review CSV show meaningless numbers.

Default: A. Ruling: A (Mike Crowe, 2026-10-27).
Changes: S1.1, S6.1 and the `jev_mail/mailbox/base.py` Touches entry.

### Decide 2. How does the first OAuth consent happen?

Evidence: fact 3; the adapter's separate `auth gmail` command.

- A. A new `jev-mail auth-gmail` subcommand runs the browser flow and writes the token; `run` and `watch` with no usable token exit 1 and name that command. Cost: one more subcommand.
- B. `run` opens the browser when no token exists. Cost: an unattended run blocks waiting for a browser.

Default: A. Ruling: A (Mike Crowe, 2026-10-27).
Changes: S4 and the `jev_mail/cli.py` Touches entry.

### Decide 3. What does a `move` action do on Gmail, which has no folders?

Evidence: the issue body's step 3, "moving to a folder = applying that label and removing `INBOX`", and "archive = `MOVE` to `[Gmail]/All Mail`".

- A. `move` to a folder adds that label (created when missing) and removes `INBOX`; `move` to `[Gmail]/All Mail` only removes `INBOX`. No new action type. Cost: the special folder name must be documented.
- B. Add an `archive` action type. Cost: `ACTION_TYPES`, `Action.to_dict`, `run_action`, the IMAP backend and the TUI checklist all change.

Default: A. Ruling: A (Mike Crowe, 2026-10-27).
Changes: S2.3 and S2.4.

## Revisions

### Revision 1. Plan switched from IMAP to the Gmail API
The brief file holds only the issue body, which plans IMAP; the issue's final comment drops IMAP. The engineer confirmed the Gmail API plan before drafting, and Decide 1 to 3 were ruled before the first Gate 1a round.
