# Decisions — GH-5: Office 365 backend over Microsoft Graph

## Setup plan

- Isolation: branch `GH-5-o365` from `master` at `6fa85f3`, in the main checkout. This project uses no worktrees; the branch merges to `master` locally.
- Git: one commit per loop step, files staged by name, never `git add -A` (public repository, CLAUDE.md).
- New dependencies: `msal`, for the device-code flow, the refresh and the serializable token cache. The story's Constraints and GH-5's comment of 2026-10-25 11:41 approve it.
- New files: `jev_mail/mailbox/graph.py`, `tests/test_graph.py`; `spec-evidence/2026-10-30-GH-5/` holds the story artifacts.
- New local data files: `o365-token.json` (written by `auth-o365` and by a token renewal) gets a `.gitignore` entry in the commit that adds `graph.py`. The cursor lives in the existing, already git-ignored `state.db` (Decide 1, default A).
- Uncommitted change found: the working tree holds an unstaged `.atlas/` line in `.gitignore` that this story did not write. It stays unstaged; the build stages only this story's `.gitignore` line.
- Tooling audit: `tools/gauntlet-layers.json` declares `tests` (`mise exec -- uv run pytest -q`) and `secrets` (`mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .`); both run. Lint, format, type check, coverage, mutation and randomized order: no tool declared; these stay `UNAVAILABLE`.
- Merge gate: the repository has no `.github/` directory and no `.pre-commit-config.yaml`; 0 checks transcribed.
- Context pack: `context-pack.md` holds the agent's record verbatim. Its `actions.py`, `imap.py` and `gmail.py` entries are read-only references here; none of the three changes.

## Facts this SPEC rests on

1. `MailBackend` (`jev_mail/mailbox/base.py:25-39`) has six methods keyed by `uid: int | str`. — read.
2. `cli._open_mailbox` (`cli.py:109-110`) picks `GmailMailbox` or `Mailbox`; `cmd_run` and `cmd_watch` catch `(OSError, imaplib.IMAP4.error, ConfigError, GmailError)` (`cli.py:170`, `202`). `cmd_watch` refuses more than one account (`cli.py:185-187`) and sleeps `poll_interval_seconds` when `supports_idle()` is false (`cli.py:199-200`). — read.
3. `cli._process_unprocessed` keys the state row by `f"{account.host}/{account.username}"` (`cli.py:45`), runs only the first `move` in config order (`cli.py:73-92`), and calls `mark_processed(mail.uid)` after the actions (`cli.py:102`). `State` is opened only after a mailbox opens and never on a dry run (`cli.py:164-166`, `192`). — read.
4. `State.record` keys a row by `message_id or f"uid:{uid}"` (`state.py:34`); the table is `processed (account, message_id, ...)` with that primary key; the docstring says nothing reads it (`state.py:24-25`). — read.
5. `config.BACKENDS = ("imap", "gmail")` (`config.py:15`); `_load_account` defaults a Gmail host and raises `ConfigError` naming `', '.join(BACKENDS)` (`config.py:170-173`); `MailboxConfig.poll_interval_seconds` defaults to 60 (`config.py:62`). — read.
6. `gmail._write_token` (`gmail.py:163-168`) writes a file at mode `0600` on every write, with `os.fchmod`; `gmail.py` imports its Google libraries inside functions only, so importing it loads none of them. — read.
7. An immutable id does not change when the item moves to another folder of the same mailbox; the header is `Prefer: IdType="ImmutableId"` and applies only to the request it is on. — learn.microsoft.com, "Obtain immutable identifiers for Outlook resources".
8. With `$filter` and `$orderby` together on messages, properties in `$orderby` must appear in `$filter`, first and in the same order, or Graph answers `InefficientFilter`. `$top` takes 1 to 1000; paging follows `@odata.nextLink` as given. The list request accepts `Prefer: outlook.body-content-type`. — learn.microsoft.com, "List messages".
9. MSAL Python raises `ValueError` when the scopes hold `openid`, `profile` or `offline_access`, and adds `offline_access` itself. `acquire_token_silent` returns `None` on an error; `acquire_token_silent_with_error` returns the error dict. — `msal/application.py` on the `dev` branch, `_decorate_scope` and `acquire_token_silent`.
10. The well-known folder name `inbox` addresses the Inbox regardless of the mailbox locale. — learn.microsoft.com, "mailFolder resource type".
11. `tier0.sender_address` parses the sender with `email.utils.parseaddr` (`tier0.py:23-24`), so `Name <address>` works. — read.
12. Several preferences go in one `Prefer` header, separated by commas. — RFC 7240, section 2. Not yet seen against Graph; S5.1 is the live check.
13. Whether `internetMessageHeaders` comes back on the list request with `$select` is not confirmed in the docs read. S2.1 fixes the contract on the fake; S5.1 checks it live, and a miss shows as an empty `list_unsubscribe`, not an error.

## Decide calls

### Decide 1. Where is the per-account cursor stored?

Evidence: the story's Author note SR-DEFER; Gate 1's deferred list for AC-3 and AC-4; fact 4 (`state.db` is beside `config.yaml` and git-ignored); `GraphMailbox` already reads `state.db` for AC-3's row check.

- A. A `cursor` table in `state.db`, keyed by the account key, with `State.cursor` and `State.set_cursor`. Cost: `state.db` gains a second table, and `GraphMailbox` writes to it on the cursor move.
- B. A JSON file `o365-cursor.json` beside `config.yaml`, keyed by the account key, git-ignored. Cost: one more local data file and `.gitignore` entry, and two stores to keep in step.
- C. A field in `config.yaml`. Cost: the program rewrites a hand-edited file on every run, and `save_config` must carry it.

Default: A.
- Ruling: A (Mike Crowe, 2026-10-30)
Changes: "The cursor" storage line and S2.3 to S2.7 state the `state.db` table.

### Decide 2. What does an `o365` account do with a `folder` other than `INBOX`?

Evidence: Gate 1a round 1, PR-SCOPE on the refusal scenario (`spec-gate.md` at `0307689`); AC-3 names the Inbox and asks for no refusal; agent decision A7.

- A. Drop the refusal. `GraphMailbox` always reads the Inbox and ignores `folder`, stated as a Known limit. Cost: a `folder: Work` key is silently ignored.
- B. Keep the `ConfigError` and cite AC-3 for it. Cost: one more check, and the scope finding can return in round 2.

Default: A.
- Ruling: A (Mike Crowe, 2026-10-30)
Changes: the refusal scenario is removed, S4.4 to S4.8 are renumbered S4.3 to S4.7, and the Known limits line on the Inbox says the key is ignored. This ruling replaces agent decision A7.

## Revisions

### Revision 1. Intent review folded
All three gaps in `spec-intent.md` are accepted. "The cursor" now opens `state.db` at each fetch when it exists, and the new S2.10 covers a first `watch` that creates it mid-session. S4.3 now says the Inbox refusal is an addition. S2.1 now checks the full `Prefer` value, and the new S3.9 proves `mark_processed` after `move` with the immutable id.

### Revision 2. Decide 1 ruled
The cursor is a table in `state.db` (A, Mike Crowe, 2026-10-30).

### Revision 3. Gate 1a round 1: scope and the complete fetch
Gate 1a found PR-SCOPE on the Inbox refusal; Decide 2 removes it (A, Mike Crowe, 2026-10-30). The judge's gap on a fetch that returns exactly `limit` messages is answered in "The cursor": that fetch is capped, so the cursor waits one more run.
