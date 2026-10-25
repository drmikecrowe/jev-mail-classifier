# Decisions — GH-2: mail backend interface and persistent state

## Setup plan

- Isolation: branch `GH-2-mailbox-backend` cut from `master` at `e393a22`. This is a refactor of four source files plus two new modules; a worktree buys nothing.
- Git: one commit per loop step, files staged by name, each staged diff shown to the engineer before commit (public repository, CLAUDE.md).
- New dependencies: none. `sqlite3` and `json` are the standard library.
- New files: `jev_mail/mailbox/__init__.py`, `jev_mail/mailbox/base.py`, `jev_mail/mailbox/imap.py` (from `jev_mail/mailbox.py`, which is removed), `jev_mail/state.py`, `tests/test_state.py`. `state.db` is a new local data file and gets a `.gitignore` entry in the commit that adds `state.py`.
- Tooling audit: layers come from `tools/gauntlet-layers.json`. `tests` is declared as `mise exec -- uv run pytest -q` and runs. `secrets` is declared as `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` and runs. Lint, format and type check: no tool is declared in `pyproject.toml` or `mise.toml`; these stay `UNAVAILABLE`.
- Merge gate: the repository has no `.github/` directory and no `.pre-commit-config.yaml`; 0 checks transcribed.

## Facts this SPEC rests on

1. `jev_mail/mailbox.py` holds `PROCESSED_KEYWORD`, `Email(uid, subject, body)`, `Mailbox` and the helpers `_decode_subject`, `_extract_body`, `_decode_payload`. Read at `e393a22`.
2. `Mailbox.fetch_unprocessed` parses each message with `email.message_from_bytes` and reads only `Subject` and the text body; `Message-ID`, `From` and `List-Unsubscribe` are on the parsed `Message` but are not surfaced. Read at `e393a22`.
3. `jev_mail/actions.py::run_action` calls `add_tag`, `move`, `set_flag`, `set_seen` on the mailbox, and posts webhooks with `httpx.post`. Read at `e393a22`.
4. `jev_mail/cli.py::_process_unprocessed(mailbox, client, config, dry_run)` reads `config.mailbox.max_emails_per_run`, prints the dry-run lines, and calls `mark_processed` only when not `dry_run`. `cmd_run` and `cmd_watch` each open one `Mailbox(config.mailbox)`. Read at `e393a22`.
5. `tests/test_mailbox.py:135`, `:154`, `:180` patch `"jev_mail.mailbox.IMAPClient"` with `monkeypatch.setattr`. After the move, `Mailbox.__enter__` looks `IMAPClient` up in `jev_mail.mailbox.imap`, so these three patches no longer reach it. Found with `search_text`.
6. `tests/test_actions.py:8`, `tests/test_cli.py:5` import `Email` from `jev_mail.mailbox`; `tests/test_mailbox.py:5` imports `PROCESSED_KEYWORD, Mailbox` from it. `tests/test_cli.py` builds `Email(uid=1, subject=..., body=...)` with keywords only.
7. `jev_mail/config.py::save_config` always writes `username: ${IMAP_USERNAME}` and `password: ${IMAP_PASSWORD}`, and `load_config` interpolates only the `mailbox` block's `host`, `username`, `password`. A second account cannot share those two variables, so a save cannot write a second account's credential references back without new code.
8. `jev_mail/tui/app.py` and `jev_mail/tui/screens/mailbox_screen.py` read and write `config.mailbox` only.
9. `.gitignore` at `e393a22` has no `state.db` entry.
10. The provider answers are model output, so two live dry runs over the same mail can print different probabilities. The brief's live "byte-identical" check therefore cannot be proven by a live run.

## Restatements

- Brief step 2, "Interface = the methods `run_action` already calls plus `fetch_unprocessed` / `mark_processed`", is restated as a `typing.Protocol` named `MailBackend` in `base.py`, following `JevClient` in `jev_mail/providers/base.py`.
- Brief step 4, "Written alongside the keyword, never instead of it", is restated as: a state row is written right after `mark_processed`, and only when `mark_processed` runs. A dry run writes no row and opens no database.
- The brief's Check, "`./jev-mail run --dry-run` output is byte-identical to Phase 0's", is restated per Decide 4 as S5.1 (byte-identical on fixed inputs) and S5.2 (live line count and shape).
- The brief's Check, "`pytest` passes unchanged", is restated per Decide 1 as M1: every test passing at `e393a22` passes, with only the three patch targets changed.

## Decide calls

### Decide 1. How do the three `IMAPClient` patches in `tests/test_mailbox.py` keep working after the move?

Evidence: fact 5.

- A. Change the three patch targets to `"jev_mail.mailbox.imap.IMAPClient"`. Cost: three test lines change, so "pytest passes unchanged" holds for every assertion but not for every byte of `tests/`.
- B. Keep the tests byte-unchanged: `imap.py` looks `IMAPClient` up through the `jev_mail.mailbox` package at call time. Cost: production code carries an indirection whose only purpose is a test patch path.

Default: A. Ruling: A (Mike Crowe, 2026-10-25).
Changes: S4.1 and the Touches entry for `tests/test_mailbox.py`: the three patch targets become `"jev_mail.mailbox.imap.IMAPClient"`; M1 reads "no assertion changes".

### Decide 2. What do `run` and `watch` do with more than one account?

Evidence: fact 4; `cmd_watch` blocks in IMAP IDLE on one connection.

- A. `run` processes each account in order, one connection each. `watch` with more than one account prints an error and exits 1. Cost: no multi-account watch until a later phase.
- B. `run` and `watch` both use only the first account; the others are parsed and ignored. Cost: a configured account silently does nothing.

Default: A. Ruling: A (Mike Crowe, 2026-10-25).
Changes: S3.3, S3.4 and the Touches entry for `jev_mail/cli.py`.

### Decide 3. What does `configure` do with a config that has more than one account?

Evidence: facts 7 and 8.

- A. `configure` prints an error that tells the engineer to edit `config.yaml` by hand, and exits 1. Cost: no wizard for multi-account configs in this phase.
- B. The wizard edits the first account, and `save_config` writes the other accounts back as loaded. Cost: their credentials are already interpolated in memory, so this writes literal secrets or needs new code to keep the raw `${VAR}` references.

Default: A. Ruling: B (Mike Crowe, 2026-10-25).
Changes: S2.5, S2.6 and the Touches entry for `jev_mail/config.py`: `load_config` keeps the raw YAML entries of accounts 2 to n, and `save_config` writes them back verbatim.

### Decide 4. How is "dry-run output is byte-identical" proven?

Evidence: fact 10; `jev_mail/cli.py` prints the dry-run lines.

- A. A golden test: a fixed fake mailbox and a fixed fake client drive `cmd_run --dry-run`, and the captured stdout equals a literal expected string taken from the `e393a22` output format. Cost: it proves the code path, not the engineer's live mailbox.
- B. A plus a live check: the engineer runs `./jev-mail run --dry-run` on `e393a22` and on the branch with `max_emails_per_run: 5`, and compares line count and line shapes. Cost: provider calls for ten mails, and still no byte proof.

Default: A. Ruling: B (Mike Crowe, 2026-10-25).
Changes: S5.1 (golden test) and S5.2 (live shape check).

## Revisions

### Revision 1. Decide 1 to 4 ruled
The engineer ruled A, A, B, B in the Decide round; SPEC.md was written with those rulings.
