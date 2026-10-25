# GH-1 decisions

## Setup plan

- Isolation: none. Work on a branch `GH-1-proton-bridge` cut from `master` at `469c7a2`; the change is small and touches three source files.
- Git usage: one commit per loop step, files staged by name, each staged diff shown to the engineer before commit (public repository, CLAUDE.md).
- New files: none in source. `EVIDENCE.md` in this directory during build.
- New dependencies: none. `ssl` is the standard library; `IMAPClient.starttls` exists in the installed `imapclient`.

## Tooling audit

Layers come from `tools/gauntlet-layers.json`.

- `tests`: declared, `mise exec -- uv run pytest -q`. Runs.
- `secrets`: declared, `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .`. Runs.
- Lint, format, type check: no tool is declared in `pyproject.toml` or `mise.toml`. These stay `UNAVAILABLE`.
- Merge gate: the repository has no `.github/` directory and no `.pre-commit-config.yaml`, so nothing else runs on merge.

## Facts verified

- `jev_mail/mailbox.py:39`: `IMAPClient(self._config.host, port=self._config.port, use_uid=True)`, with no `ssl` argument, so `IMAPClient`'s default `ssl=True` applies.
- `jev_mail/config.py:53-60`: `MailboxConfig` has `host`, `port=993`, `username`, `password`, `folder`, `poll_interval_seconds`, `max_emails_per_run`.
- `jev_mail/config.py:100-108`: `load_config` builds `MailboxConfig` field by field from `mb_raw`; `save_config` at `jev_mail/config.py:133-145` writes the same fields.
- `jev_mail/tui/screens/mailbox_screen.py:53-61`: `on_button_pressed` builds a fresh `MailboxConfig` from the form, so any field it does not copy is lost on save.
- `jev_mail/cli.py:34,40`: the dry-run lines are `[dry-run] {subject!r}: no category matched` and `[dry-run] {subject!r}: {name} ({p:.2f}) -> {action.type}`.

## Restatements

- Brief step 3, "Confirm Bridge accepts `STORE +FLAGS ($JevProcessed)` on one message", is restated as S2.2: add, read back, remove, read back, so the mailbox ends unchanged.
- Brief step 4, "Run once with `provider: typesafe`", is restated as S2.3, a dry run, per Decide 2.

## Decide calls

### Decide 1. How does `tls: starttls` verify Bridge's certificate?

- Evidence: Bridge serves its own certificate, which the engineer believes is self-signed; unverified until S2.1 runs.
- Options: `tls_ca_file` (add a field naming the exported Bridge certificate; cost: a second field and a manual export); default verification (cost: likely failure and a SPEC revision); skip verification on loopback (cost: no TLS authentication).
- Default: `tls_ca_file`.
- Ruling: tls_ca_file (Mike Crowe, 2026-10-25)

### Decide 2. Is the brief's step 4 TypeSafe run a dry run or a real run?

- Evidence: brief step 4 names no mode; the brief's Check requires the mailbox unchanged.
- Options: dry-run (cost: actions and marking are not exercised); real run (cost: marks mail and runs real actions on the inbox).
- Default: dry-run.
- Ruling: dry-run (Mike Crowe, 2026-10-25)

## Revision log

- 2026-10-25: first draft, with Decide 1 and Decide 2 ruled.
- 2026-10-25: Gate 1a round 1 fixes: Orientation states what Decide 1 and Decide 2 ruled and restates the brief's one-change limit; Definitions add Phase 1 and the SQLite-only processed set; S2.2 names the literal line; S1.6 names its button ids.
