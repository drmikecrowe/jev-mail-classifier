# GH-2: Mail backend interface and persistent state

## Summary

This change puts the existing IMAP code behind a backend interface, adds a local SQLite record of each processed email, and lets `config.yaml` list more than one account. It prepares Phase 2, which adds Gmail and Graph backends. Today `cli.py` and `actions.py` call the IMAP `Mailbox` class directly, the only record of a processed email is the `$JevProcessed` keyword on the server, and `config.yaml` holds one `mailbox:` block.

What changes: `jev_mail/mailbox.py` becomes the package `jev_mail/mailbox/`, with the interface in `base.py` and the IMAP code in `imap.py`. `Email` gains `message_id`, `sender` and `list_unsubscribe`. A new `jev_mail/state.py` writes one row per processed email to `state.db`. `config.yaml` accepts an `accounts:` list, and `mailbox:` still works as the one-account form.

The acceptance criteria, in plain words:

- Every name that code imports from `jev_mail.mailbox` today still imports from it.
- The interface names the six methods the pipeline uses, and not the IDLE methods.
- A fetched email carries its Message-ID, sender and List-Unsubscribe header, or empty strings when the email has none.
- A config with `mailbox:` loads and saves exactly as it does today. A config with `accounts:` loads every account; a config with both, or with an empty list, is refused.
- The configure wizard edits the first account and writes the other accounts back as they were in the file.
- A real run writes the keyword and then one state row per email. A dry run writes nothing and creates no `state.db`.
- `run` processes each account in turn. `watch` with more than one account refuses to start.
- The dry-run output is byte-identical to today's on fixed inputs, and has the same line count and line shapes on the live mailbox.

What must not change: the existing tests (only three patch targets move), the one-account config file format, the rule that `config.yaml` never holds literal secrets, the provider code, and the dependency list. Unit tests prove every criterion except the live shape check, which the engineer runs by hand and records with counts only. Open decisions: none.

## Orientation

- Lane: engineering, because this is an internal refactor with no user-facing behavior change, preparing Phase 2 (Gmail and Graph backends); there is no product author.
- Change: put the IMAP code behind a `MailBackend` interface, add a SQLite state record beside the keyword, and accept an `accounts:` list in `config.yaml`.
- Why: Phase 2 needs a second and third backend, a per-email record that is not on the server, and more than one account; the code today has none of the three.
- Touches: `jev_mail/mailbox/` (new package), `jev_mail/state.py` (new), `jev_mail/actions.py`, `jev_mail/cli.py`, `jev_mail/config.py`, `.gitignore`, tests, `CLAUDE.md`, `README.md`.
- Decide: the three most likely to be wrong are the state row's account key (`<host>/<username>`), the `uid:<uid>` stand-in for a missing Message-ID, and writing accounts 2 to n back verbatim.
- Decided: Decide 1 ruled that the three `IMAPClient` patch targets in `tests/test_mailbox.py` change to `jev_mail.mailbox.imap.IMAPClient`; it governs S4.1, M1 and the Touches entry for `tests/test_mailbox.py` (Mike Crowe, 2026-10-25). Decide 2 ruled that `run` processes each account in order and `watch` refuses more than one account; it governs S3.3, S3.4 and the Touches entry for `jev_mail/cli.py` (Mike Crowe, 2026-10-25). Decide 3 ruled that the wizard edits the first account and `save_config` writes accounts 2 to n back from their raw YAML entries; it governs S2.5, S2.6 and the Touches entry for `jev_mail/config.py` (Mike Crowe, 2026-10-25). Decide 4 ruled that the brief's byte-identical check is proven by a golden test and a live line-shape check; it governs S5.1 and S5.2 (Mike Crowe, 2026-10-25).
- Brief: issue GH-2. Scope guard: no Gmail or Graph code, no new dependency beyond the standard library.
- Tier: 2
- Issue: GH-2
- Isolation: branch `GH-2-mailbox-backend` from `master` at `e393a22` — a refactor of four source files and two new modules.

## Definitions

- **Account key**: the string `<host>/<username>` of one account's `MailboxConfig`, after `${VAR}` interpolation.
- **State row**: one row of the `processed` table in `state.db`, keyed on (account key, message id), with the columns `source`, `probabilities` (JSON object), `actions` (JSON list), `processed_at` (ISO-8601 UTC).
- **Raw entry**: one item of the `accounts:` list exactly as `yaml.safe_load` returns it, before interpolation.
- **Dry-run line**: a line `[dry-run] <subject repr>: <category> (<p>) -> <action>` or `[dry-run] <subject repr>: no category matched` (`jev_mail/cli.py:34`, `:40` at `e393a22`).

## Scenarios

### S1. The `jev_mail.mailbox` package and the interface

- S1.1 Given the branch, when a test runs `from jev_mail.mailbox import PROCESSED_KEYWORD, Email, Mailbox, MailBackend`, then the import succeeds, `jev_mail.mailbox.Mailbox is jev_mail.mailbox.imap.Mailbox`, `jev_mail.mailbox.Email is jev_mail.mailbox.base.Email`, and the file `jev_mail/mailbox.py` does not exist.
- S1.2 Given `MailBackend` in `jev_mail/mailbox/base.py`, when a test reads its members, then `fetch_unprocessed`, `mark_processed`, `add_tag`, `move`, `set_flag` and `set_seen` are each defined on `MailBackend` and on `Mailbox`, and none of `supports_idle`, `idle`, `idle_check`, `idle_done` is defined on `MailBackend`.
- S1.3 Given a `MagicMock(spec=MailBackend)` and an `Email(uid=7, subject="s", body="b")`, when `run_action` runs once for each of `tag` (value `"Invoice"`), `move` (folder `"Invoices"`), `flag`, `unflag`, `mark_read`, `mark_unread`, then the mock receives, in order, `add_tag(7, "Invoice")`, `move(7, "Invoices")`, `set_flag(7, True)`, `set_flag(7, False)`, `set_seen(7, True)`, `set_seen(7, False)`.
- S1.4 Given a fake IMAP server whose `fetch` returns one RFC 822 message with `Message-ID: <a1@example.com>`, `From: =?utf-8?q?Ann_Lee?= <ann@example.com>` and `List-Unsubscribe: <mailto:unsub@example.com>`, when `Mailbox.fetch_unprocessed()` runs, then the one `Email` has `message_id == "<a1@example.com>"`, `sender == "Ann Lee <ann@example.com>"` and `list_unsubscribe == "<mailto:unsub@example.com>"`.
- S1.5 (boundary) Given a fake IMAP message with none of the three headers, when `Mailbox.fetch_unprocessed()` runs, then `message_id`, `sender` and `list_unsubscribe` are each `""`; and `Email(uid=1, subject="x", body="y")` constructs with the same three fields `""`.

### S2. `accounts:` in `config.yaml`

- S2.1 Given a `config.yaml` with a `mailbox:` block and no `accounts:` key, when `load_config` runs, then `config.accounts == [config.mailbox]` and every `config.mailbox` field equals what `load_config` returns at `e393a22` for the same file.
- S2.2 Given a `config.yaml` with `accounts:` holding two entries, the first with `host: imap.example.com`, `username: ${A_USER}`, `password: ${A_PASS}`, the second with `host: ${B_HOST}`, `username: ${B_USER}`, `password: ${B_PASS}`, `tls: starttls`, `port: 1143`, and all five variables set, when `load_config` runs, then `config.mailbox` is the first account, `config.accounts` has two `MailboxConfig`s, each has its own interpolated host, username and password, and the second has `tls == "starttls"` and `port == 1143`.
- S2.3 (negative) Given a `config.yaml` with both a `mailbox:` block and an `accounts:` list, when `load_config` runs, then it raises `ConfigError` whose message contains `mailbox` and `accounts`.
- S2.4 (negative) Given a `config.yaml` with `accounts: []`, or with an `accounts:` entry whose `tls` is `plain`, when `load_config` runs, then it raises `ConfigError` whose message contains `accounts`.
- S2.5 Given an `AppConfig` loaded from a one-account `mailbox:` file, when `save_config` writes it, then the written file is byte-identical to what `save_config` writes at `e393a22` for the same `AppConfig`, and it has no `accounts:` key.
- S2.6 Given the S2.2 file loaded with `load_config`, when `config.mailbox` is replaced with a new `MailboxConfig(host="imap2.example.com", username="new@example.com", password="pw")` (as `JevMailConfigApp._after_mailbox` does) and `save_config` writes it, then the written file has an `accounts:` list and no `mailbox:` key; its first entry has `host: imap2.example.com`, `username: ${IMAP_USERNAME}`, `password: ${IMAP_PASSWORD}`; its second entry equals the S2.2 second raw entry, key for key, still `${B_HOST}`, `${B_USER}`, `${B_PASS}`; and the file does not contain `new@example.com`, `pw`, or any of the five variables' values.

### S3. State rows and accounts in the CLI

- S3.1 Given an account `MailboxConfig(host="imap.example.com", username="me@example.com")`, a fake backend that returns `Email(uid=1, subject="Invoice #1", body="Please pay", message_id="<a1@example.com>")`, a fake client returning `{"Invoice": 0.9}`, a category `Invoice` with one `tag` action of value `Invoice`, and a `State` on `tmp_path / "state.db"`, when `_process_unprocessed` runs with `dry_run=False`, then `mark_processed(1)` is called, and then `state.db` holds exactly one state row with account key `imap.example.com/me@example.com`, message id `<a1@example.com>`, `source == "jev"`, `probabilities == {"Invoice": 0.9}`, `actions == [{"category": "Invoice", "type": "tag", "value": "Invoice"}]`, and a `processed_at` that parses as an ISO-8601 UTC time.
- S3.2 (negative) Given a directory with a valid one-account `config.yaml`, `jev_mail.cli.Mailbox` replaced with a fake backend that returns one email, and a fake client, when `cmd_run` runs with `--dry-run`, then it returns 0, `mark_processed` is never called, and the directory holds no `state.db`.
- S3.3 Given a two-account config where the first account has `max_emails_per_run: 3` and the second `max_emails_per_run: 4`, and `jev_mail.cli.Mailbox` replaced with a fake class that records the `MailboxConfig` it is built with, when `cmd_run` runs without `--dry-run`, then it returns 0, the fake is built with the first account and then the second, `fetch_unprocessed` is called with `limit=3` and then `limit=4`, and `state.db` in the config directory exists.
- S3.4 (negative) Given a two-account config, when `cmd_watch` runs, then it returns 1, stderr contains `watch` and `one account`, and `jev_mail.cli.Mailbox` is never built.
- S3.5 (boundary) Given an `Email` with `message_id == ""` and `uid == 42`, when `State.record` stores it, then the state row's message id is `uid:42`.
- S3.6 (boundary) Given one state row for (account key `a`, message id `<m@example.com>`), when `State.record` stores the same pair again with `probabilities == {"X": 0.1}`, then the table holds one row for that pair, with `{"X": 0.1}`.

### S4. The IMAP code moves unchanged

- S4.1 Given the branch, when the engineer runs `git diff -M e393a22 -- jev_mail/mailbox.py jev_mail/mailbox/imap.py`, then the only changed lines in `Mailbox` and its helpers are the import lines, the removal of the `Email` class, a new `_decode_header` helper shared with the subject decode, and the three new header reads in `fetch_unprocessed`; and `tests/test_mailbox.py` differs from `e393a22` in the three patch target strings and in new test functions only.

### S5. Dry-run output

- S5.1 Given a directory with a one-account `config.yaml` holding a category `Invoice` (threshold 0.6, actions `tag` value `Invoice` then `move` folder `Invoices`), `jev_mail.cli.Mailbox` replaced with a fake that returns `Email(uid=2, subject="Invoice #1", body="b")` and `Email(uid=1, subject="Newsletter", body="b")`, and `jev_mail.cli.get_jev_client` replaced with a fake whose `decide` returns `{"Invoice": 0.9}` and then `{"Invoice": 0.1}`, when `cmd_run` runs with `--dry-run`, then stdout equals exactly `"[dry-run] 'Invoice #1': Invoice (0.90) -> tag\n[dry-run] 'Invoice #1': Invoice (0.90) -> move\n[dry-run] 'Newsletter': no category matched\n"`. The same test passes at `e393a22` (with `Email` built from `jev_mail.mailbox`) and on the branch.
- S5.2 Given the engineer's live `config.yaml` with `max_emails_per_run: 5`, when the engineer runs `./jev-mail run --dry-run` once at `e393a22` and once on the branch, then both exit 0, both print the same number of lines, every line is a dry-run line or the cap notice `[jev-mail] hit max_emails_per_run (5) ...`, the unprocessed count is the same before and after each run, and no `state.db` exists after either run. EVIDENCE.md records the commands, exit codes, line counts and counts only, with no subject, address or body.

## Must NOT

- M1. Every test in `tests/` that passes at `e393a22` still passes, and no existing test function changes except the three `IMAPClient` patch targets in `tests/test_mailbox.py`. Proven by the `tests` layer and S4.1.
- M2. A one-account `mailbox:` config loads and saves exactly as at `e393a22`. Proven by S2.1 and S2.5.
- M3. `save_config` never writes a literal username or password (`save_config` docstring, `tests/test_config.py::test_save_config_never_writes_literal_secrets`). Proven by S2.6 and M1.
- M4. The keyword is still written on every non-dry-run email; a state row is never written instead of it, and is written only after it. Proven by S3.1 and M1.
- M5. A dry run changes nothing: no keyword, no action, no state row, no `state.db` file. Proven by S3.2 and S5.2.
- M6. No file under `jev_mail/providers/` changes, and no Gmail or Graph code is added. Proven by `git diff --stat e393a22 -- jev_mail/providers/` showing nothing.
- M7. No new dependency: `pyproject.toml` and `uv.lock` do not change. Proven by `git diff --stat e393a22 -- pyproject.toml uv.lock` showing nothing.
- M8. `Email(uid=..., subject=..., body=...)` still constructs with keywords; the new fields come after `body` with default `""`. Proven by S1.5 and M1.
- M9. No commit holds `state.db`, `config.yaml`, `.env`, or a real subject, address or body; `.gitignore` gains `state.db` in the commit that adds `jev_mail/state.py`. Proven by the `secrets` layer and by `git check-ignore state.db`.

## Touches

- `jev_mail/mailbox.py`: removed; its content moves to `jev_mail/mailbox/imap.py`.
- `jev_mail/mailbox/__init__.py`: new; re-exports `PROCESSED_KEYWORD`, `Email`, `Mailbox`, `MailBackend`.
- `jev_mail/mailbox/base.py`: new; `Email` (with `message_id`, `sender`, `list_unsubscribe`, default `""`) and the `MailBackend` `typing.Protocol` with the six methods of S1.2.
- `jev_mail/mailbox/imap.py`: new; `PROCESSED_KEYWORD`, `Mailbox` and its helpers from `jev_mail/mailbox.py`; `fetch_unprocessed` fills the three new `Email` fields.
- `jev_mail/state.py`: new; `State(path)` opens `state.db` with `sqlite3`, creates the `processed` table if missing, and `record(account_key, mail, source, probabilities, actions)` upserts one state row.
- `jev_mail/actions.py`: `run_action` takes a `MailBackend` instead of a `Mailbox`; dispatch is unchanged.
- `jev_mail/cli.py`: `_process_unprocessed` gains keyword arguments `account` (default `config.mailbox`) and `state` (default `None`), uses `account.max_emails_per_run`, and after `mark_processed` calls `state.record` when `state` is set; `cmd_run` opens `State(<dir>/state.db)` only when not `--dry-run` and runs each account in `config.accounts` in its own `Mailbox`; `cmd_watch` refuses more than one account; `_mailbox_error_message` names the failing account's host and port.
- `jev_mail/config.py`: `AppConfig` gains `extra_accounts: list[MailboxConfig]` and `extra_accounts_raw: list[dict]` (both default empty) and an `accounts` property (`[mailbox, *extra_accounts]`); `load_config` reads either `mailbox:` or `accounts:`, applies the same interpolation and checks to each account, and refuses both or an empty list; `save_config` writes `mailbox:` when there are no extra accounts, and otherwise `accounts:` with the first account as `mailbox:` is written today followed by `extra_accounts_raw` verbatim.
- `.gitignore`: adds `state.db`.
- `tests/test_mailbox.py`: three patch targets (Decide 1); S1.4, S1.5.
- `tests/test_actions.py`: S1.3.
- `tests/test_config.py`: S2.1 to S2.6.
- `tests/test_cli.py`: S3.1 to S3.4, S5.1.
- `tests/test_state.py`: new; S3.5, S3.6.
- `tests/test_package.py`: new; S1.1, S1.2.
- `spec-evidence/2026-10-25-GH-2/EVIDENCE.md` (in build): S4.1 diff reading and S5.2 live run record.

## Documentation

- `CLAUDE.md`: Architecture step 1 names `mailbox.py` and says "There is no database"; it changes to name `jev_mail/mailbox/` and `state.db`, and the Config section gains one line on `accounts:`.
- `README.md:163`: says there is "no separate database"; it changes to say the keyword stays the source of truth and `state.db` is a local record beside it.

## Known limits

- `watch` handles one account only (Decide 2).
- The wizard edits only the first account. It writes that account's credentials as `${IMAP_USERNAME}` and `${IMAP_PASSWORD}`, as it does today, even when the file named other variables for it.
- Accounts 2 to n are written back as loaded; an edit made to `extra_accounts` in memory is not saved.
- `state.db` is a record only in this phase. Nothing reads it, and a failed state write stops the run after that email's keyword is already set, so that email has no state row.
- A missing Message-ID falls back to `uid:<uid>`, which is unique only within one folder of one account.
- S5.2 compares line counts and shapes, not bytes, because provider answers vary between runs.

## Verification contract

| Layer | What it gates | Threshold |
|---|---|---|
| tests | S1.1 to S3.6, S5.1, M1 to M5, M8 | `mise exec -- uv run pytest -q` exits 0 |
| secrets | M9 for committed content | `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` reports no leak |
| diff reading | S4.1, M6, M7 | the `git diff` commands in S4.1, M6, M7 show only the allowed lines |
| live run | S5.2 | recorded in EVIDENCE.md with counts only |
