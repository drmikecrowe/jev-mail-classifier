# GH-1: Run the fork against Proton Bridge

## Summary

This change proves that jev-mail runs against Proton Bridge before any refactor starts. Bridge serves IMAP on 127.0.0.1:1143 as a plain connection that is upgraded with STARTTLS. Today `Mailbox` always opens an implicit-TLS connection (`IMAPClient` default `ssl=True`), so it cannot talk to Bridge. The one code change adds two mailbox settings: `tls` (`ssl` or `starttls`) and `tls_ca_file` (the certificate file exported from Bridge, used to verify the STARTTLS connection).

The acceptance criteria, in plain words:

- With `tls: starttls`, jev-mail connects without TLS, upgrades with STARTTLS, and only then logs in.
- With no `tls` setting, jev-mail connects exactly as it does today.
- A `tls` value other than `ssl` or `starttls` stops config loading with a clear error.
- The two settings survive a save and a reload, and the configure wizard keeps them.
- Against the live Bridge, a dry run prints classification lines and leaves the mailbox unchanged.
- Bridge either accepts or rejects the `$JevProcessed` keyword, and the result is recorded.
- A dry run with the TypeSafe-direct provider and a live key either works or fails, and the result is recorded.

What must not change: the existing tests, the default implicit-TLS connection on port 993, the rule that `config.yaml` never holds literal secrets, and the provider code. Unit tests prove the first four criteria. The live criteria are proven by recorded runs, with counts and outcome words only, never real subjects or addresses. Open decisions: none.

## Orientation

- Lane: engineering, because this is a pre-refactor verification spike on the fork owner's own mail setup, with no product author and no user-facing behavior asked for.
- Decided: Decide 1 ruled that `tls: starttls` verifies Bridge's certificate against a file named by a new `tls_ca_file` setting, not by default verification and not by skipping verification; it governs S1.1, S1.2, S1.4 and the Touches entry for `jev_mail/config.py` (Mike Crowe, 2026-10-25). Decide 2 ruled that the TypeSafe run in S2.3 is a dry run, not a real run that marks mail and runs actions (Mike Crowe, 2026-10-25).
- Brief: issue GH-1. Its goal is to prove the fork runs against Bridge with no new code. Its one exception: if Bridge needs plain connect plus STARTTLS, a `tls: starttls` config field is the one code change allowed in this phase. Decide 1's `tls_ca_file` is part of that same TLS setting. Any other code change is out of scope.
- Base: `469c7a2` on `master`.

## Definitions

- **Bridge**: Proton Mail Bridge running on the engineer's machine, serving IMAP at `127.0.0.1:1143`.
- **Bridge certificate file**: the TLS certificate that Bridge exports (Bridge settings, export TLS certificates), saved at an absolute path on the engineer's machine.
- **Unprocessed count**: the number of UIDs that `SEARCH UNKEYWORD $JevProcessed` returns in the configured folder.
- **Folder count**: the number of UIDs that `SEARCH ALL` returns in the configured folder.
- **Phase 1**: the refactor that follows this phase, named in brief GH-1. It is not built here.
- **SQLite-only processed set**: a design where jev-mail stores processed message ids in a local SQLite file instead of an IMAP keyword. S2.2 only records whether Phase 1 needs it.
- **Live run record**: the lines the engineer writes into EVIDENCE.md for an S2 scenario: the command, its exit code, the counts, and outcome words. It holds no subject, address, or body from the live mailbox.

## Scenarios

### S1. The `tls` and `tls_ca_file` mailbox settings

- S1.1 Given a `MailboxConfig(host="127.0.0.1", port=1143, tls="starttls", tls_ca_file="/tmp/bridge.pem")` and `jev_mail.mailbox.IMAPClient` replaced with a `MagicMock`, and `ssl.create_default_context` replaced with a mock that returns a sentinel context, when `Mailbox(config).__enter__()` runs, then `IMAPClient` is called once with `("127.0.0.1", port=1143, use_uid=True, ssl=False)`, `ssl.create_default_context` is called with `cafile="/tmp/bridge.pem"`, `starttls` is called with `ssl_context=<sentinel>`, and `starttls` is called before `login`.
- S1.2 Given a `MailboxConfig(host="127.0.0.1", port=1143, tls="starttls")` with no `tls_ca_file` and a mocked `IMAPClient`, when `Mailbox(config).__enter__()` runs, then `starttls` is called with `ssl_context=None` before `login`.
- S1.3 (boundary) Given a `config.yaml` whose `mailbox` block has no `tls` and no `tls_ca_file` key and a mocked `IMAPClient`, when `load_config` runs and then `Mailbox(config).__enter__()` runs, then `config.mailbox.tls == "ssl"`, `config.mailbox.tls_ca_file == ""`, `IMAPClient` is called with `ssl=True`, and `starttls` is never called.
- S1.4 Given an `AppConfig` whose mailbox has `tls="starttls"` and `tls_ca_file="/tmp/bridge.pem"`, when `save_config` writes it and `load_config` reads it back, then the loaded mailbox has `tls == "starttls"` and `tls_ca_file == "/tmp/bridge.pem"`.
- S1.5 (negative) Given a `config.yaml` with `mailbox.tls: plain`, when `load_config` runs, then it raises `ConfigError` whose message contains `mailbox.tls`, `ssl` and `starttls`.
- S1.6 Given a `config.yaml` whose mailbox has `tls: starttls` and `tls_ca_file: /tmp/bridge.pem` and one category, and `JevMailConfigApp` started with `config=load_config(<that file>)`, when the pilot clicks `#continue` on the credentials screen with its fields unchanged, clicks `#continue` on the mailbox screen with no field changed, and presses `s` (Save & exit) on the categories screen, then the written `config.yaml` still holds `tls: starttls` and `tls_ca_file: /tmp/bridge.pem`.

### S2. Live runs against Bridge

These run by hand on the engineer's machine. Each records a live run record in EVIDENCE.md.

- S2.1 Given `config.yaml` with `mailbox.host: 127.0.0.1`, `port: 1143`, `tls: starttls`, `tls_ca_file: <Bridge certificate file>`, and the Bridge username and password in `.env` as `IMAP_USERNAME` and `IMAP_PASSWORD`, when the engineer records the unprocessed count and the folder count, runs `./jev-mail run --dry-run`, and records both counts again, then the command exits 0, every line it prints matches `[dry-run] '<subject>': <category> (<p>) -> <action>` or `[dry-run] '<subject>': no category matched`, at least one such line is printed, and both counts are equal before and after.
- S2.2 Given the S2.1 settings and one UID `u` that the engineer picks from the folder, when the engineer adds the flag `$JevProcessed` to `u`, reads the flags of `u`, removes `$JevProcessed` from `u`, and reads the flags of `u` again, then the live run record says `accepted` when the first read holds `$JevProcessed` and the second does not, or says `rejected` with the server's error text when the add fails or the first read lacks the keyword. A `rejected` record also holds the line `Phase 1 needs a SQLite-only processed set.`
- S2.3 Given the S2.1 settings, `jev.provider: typesafe`, and a live `TYPESAFE_API_KEY` in `.env`, when the engineer records the unprocessed count, runs `./jev-mail run --dry-run`, and records the count again, then the live run record holds the exit code and says `works` when the exit code is 0 and at least one S2.1-shaped line is printed, or says `fails` with the error line the command printed. In both cases the unprocessed count is equal before and after.

## Must NOT

- M1. Every test in `tests/` that passes at `469c7a2` still passes. Proven by the `tests` layer.
- M2. A `config.yaml` with no `tls` key connects with `IMAPClient(host, port=..., use_uid=True, ssl=True)` and no STARTTLS, as at `469c7a2`. Proven by S1.3.
- M3. `MailboxConfig`'s existing fields keep their names, order and defaults; the new fields come after `max_emails_per_run`. Proven by M1 (existing constructors in `tests/` use keywords and positional `host`).
- M4. `save_config` never writes the literal username or password (`save_config` docstring, `tests/test_config.py::test_save_config_never_writes_literal_secrets`). Proven by M1.
- M5. No file under `jev_mail/providers/` changes. Proven by `git diff --stat 469c7a2 -- jev_mail/providers/` showing nothing.
- M6. No commit holds `config.yaml`, `.env`, the Bridge certificate file, or a real subject, address or body. Proven by the `secrets` layer and by the live run record holding counts and outcome words only.

## Touches

- `jev_mail/config.py`: `MailboxConfig` gains `tls: str = "ssl"` and `tls_ca_file: str = ""`; `load_config` reads both and raises `ConfigError` for a `tls` value outside `ssl`, `starttls`; `save_config` writes both.
- `jev_mail/mailbox.py`: `Mailbox.__enter__` passes `ssl=(tls == "ssl")` to `IMAPClient`, and for `starttls` calls `starttls(ssl_context=...)` before `login`, with a context built from `tls_ca_file` when it is set.
- `jev_mail/tui/screens/mailbox_screen.py`: `on_button_pressed` copies `tls` and `tls_ca_file` from the loaded mailbox into the `MailboxConfig` it returns. No new widget.
- `tests/test_mailbox.py`: S1.1, S1.2, S1.3.
- `tests/test_config.py`: S1.4, S1.5.
- `tests/test_tui.py`: S1.6.
- `spec-evidence/2026-10-25-GH-1/EVIDENCE.md` (in build): S2.1, S2.2, S2.3 live run records.

## Known limits

- The configure wizard has no widget for `tls` or `tls_ca_file`; the engineer sets them by hand in `config.yaml`.
- `tls_ca_file` is read only in `starttls` mode. In `ssl` mode it is ignored.
- `tls_ca_file` is used as given, so it must be an absolute path.
- If Bridge's certificate does not name `127.0.0.1`, hostname checking fails in S2.1. Then this SPEC is revised visibly before the build goes on.
- The README is not updated in this phase.

## Verification contract

- `tests`: `mise exec -- uv run pytest -q` covers S1.1 to S1.6 and M1 to M4.
- `secrets`: `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` covers M6 for committed content.
- M5: `git diff --stat 469c7a2 -- jev_mail/providers/` is empty.
- S2.1 to S2.3: manual live runs, recorded in EVIDENCE.md as live run records.
