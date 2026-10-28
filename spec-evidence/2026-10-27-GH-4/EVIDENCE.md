## Evidence Report — GH-4: Gmail backend over the Gmail API (Tier 2)

## Summary

Delivered: `GmailMailbox` in `jev_mail/mailbox/gmail.py`, a second `MailBackend` that works through the Gmail API, so a tag or a move is a real Gmail label. An account picks it with `backend: gmail`; an account with no `backend` key stays IMAP. `jev-mail auth-gmail` runs the one-time Google sign-in and writes an owner-only token beside `config.yaml`. `run` and `watch` open the right backend per account, and `watch` polls a Gmail account. Why: Gmail never shows an IMAP keyword as a label, so tags applied over IMAP were invisible in the Gmail web UI.

How each criterion was proven:

- Fetch of unprocessed Gmail mail (watched label, `-label:JevProcessed`, newest first, capped, parsed like IMAP): S1.1 to S1.3, unit tests with a fake service.
- `tag` adds a label and creates a missing one once: S2.1, S2.2.
- `move` adds the folder's label and removes `INBOX`; `[Gmail]/All Mail` only archives: S2.3 to S2.5.
- `flag`, `mark_read` and the `JevProcessed` marker: S2.6, S2.7. A Google error becomes `GmailError`: S2.8.
- Config: mixed accounts, backend validation, save and the wizard keep `backend: gmail`: S3.1 to S3.5.
- Sign-in and token: `auth-gmail` writes a mode-0600 token and never prints it, a missing token or client secret file is a readable error, a refresh rewrites the token at 0600: S4.1 to S4.5.
- CLI wiring and `watch` polling: S5.1, S5.2. String uids and lazy Google imports: S6.1, S6.2.
- What must not change: M1 to M6, by the `tests` and `secrets` layers and the diff readings below.
- Live: the engineer ran `auth-gmail` and a real `./jev-mail run` over Proton and Gmail. A read-only API check then found 20 Gmail messages with `Folders/BULK` and `JevProcessed`, 0 of them in the inbox, and 0 of them in what the next run would fetch.

Not proven: S7.1 as the SPEC writes it (a test message from a second address, `tag BULK` + `move [Gmail]/All Mail`) did not run; the live run above is a substitute, so the tag and archive paths are proven only by unit tests. Static types, lint, changed-line coverage, suite health and a dependency audit have no tool in this project. Mutation testing ran only as hand mutants.

## Agent decisions

<details><summary>10 agent decisions</summary>

### A1. An account picks its backend with a `backend` key, `imap` by default
- Other option: pick Gmail from the host name, as the IMAP plan could.
- Why: the Gmail API has no IMAP host to test, and a missing key keeps every existing config on IMAP.
- Command: hotfix

### A2. The OAuth scope is `https://www.googleapis.com/auth/gmail.modify`
- Other option: `https://mail.google.com/`, the scope of the email-triage adapter.
- Why: `gmail.modify` covers list, get, modify and label create, and it cannot delete mail permanently, so a leaked token can do less.
- Command: hotfix

### A3. The token and client secret files have fixed names beside `config.yaml`
- Other option: a per-account `token_file` key.
- Why: the issue names one location, beside `config.yaml`, and one Gmail account is the only case asked for; a second Gmail account is a known limit.
- Command: hotfix

### A4. Gmail mail is parsed from `format="raw"` with the existing IMAP parsers
- Other option: walk the `format="full"` payload, as the email-triage adapter does.
- Why: one parser for both backends keeps subject, sender, `List-Unsubscribe` and body decoding the same, so Tier 0 behaves the same on both.
- Command: hotfix

### A5. The Gmail API dependencies are required, and imported only inside `gmail.py` functions
- Other option: an optional `gmail` extra in `pyproject.toml`.
- Why: an extra adds an install step for Gmail users and an import-error path to test; a lazy import keeps IMAP startup unchanged.
- Command: hotfix

### A6. A missing token raises `ConfigError`, caught beside the mailbox errors in `run` and `watch`
- Other option: a new exception class.
- Why: `ConfigError` already means "fix your setup", and `run` and `watch` already print it as `error: <message>`.
- Command: hotfix

### A7. Google errors are wrapped in one `GmailError` raised by `gmail.py`
- Other option: catch `HttpError` and `GoogleAuthError` directly in `cli.py`.
- Why: `cli.py` can then catch Gmail failures without importing the Google libraries, which keeps S6.2 true.
- Command: hotfix

### A8. The wizard's mailbox screen keeps the account's `backend` on save
- Other option: leave the screen as it is and list the lost key as a known limit.
- Why: the screen already carries `tls` the same way, and without it one wizard save silently turns a Gmail account into an IMAP account with no usable host.
- Command: hotfix

### A9. An uncapped fetch asks Gmail for one page of 500 messages
- Other option: page through `nextPageToken` until every unprocessed message is listed.
- Why: `max_emails_per_run` always caps a run in practice, and the SPEC lists 500 per run as a known limit; paging adds a loop no scenario asks for.
- Command: build

### A10. A token file that does not parse is reported as a `GmailError`, not a traceback
- Other option: catch only `GoogleAuthError`, and let the `ValueError` of a malformed token file propagate.
- Why: the issue asks that a Google error stop the run with a readable message, and a hand-damaged token file is the likeliest such error after `invalid_grant`.
- Command: build

</details>

### Review risks

- S7.1 is `unverified`: the live proof ran under different givens (see the mapping). `tag` and `move [Gmail]/All Mail` were never applied to real Gmail; S2.1 and S2.5 cover them against the fake service only.
- The adversary read `c6ec005`, the only code commit. Its range started at `1b01072`, the merge base with `origin/HEAD`, because local `master` holds GH-3 and GH-8 commits not yet pushed; the range so also held those stories' changes.
- Open hunch, not fixed: `save_config` writes a Gmail first account's credentials as `${IMAP_USERNAME}` / `${IMAP_PASSWORD}`, and a Gmail account has no password, so a configure-wizard save over a Gmail first account can leave a file that `load_config` rejects. S3.5 checks only that `backend: gmail` survives. The SPEC's Known limits say the wizard cannot set up a Gmail account.
- Open hunch, not fixed: `base64.urlsafe_b64decode` raises `binascii.Error` on an unpadded `raw` payload, which no handler catches. All 25 live Gmail payloads decoded without error.
- Open hunch, not fixed: a tag whose name differs only in case from an existing label makes `labels().create` fail with a `GmailError`, which stops the run at that email.

### Not reached by review

- Round 1: calls 5/10; hunts not reached: 1 (no merge gate; the layer manifest was not compared), 8 (EVIDENCE against its tables), 9 (version constraints in `pyproject.toml` and `uv.lock`), 10 (the Documentation section against `README.md` and `CLAUDE.md`). Sites not opened: `tests/test_gmail.py`, `tests/test_cli.py`, `tests/test_tui.py`, `jev_mail/tui/screens/credentials_screen.py`, `jev_mail/tier0.py`, `README.md`, `CLAUDE.md`, `uv.lock`.

## Orientation

- Verdict: PASSED WITH LIMITS
- Delivered: a Gmail API backend behind `MailBackend`, the `auth-gmail` command, and a per-account `backend` key.
- Proven: 25/26 scenarios mapped and passing; M1 to M6 passing
- Not proven: S7.1 as written (unverified, live substitute ran); static types, lint, changed-line coverage, suite health and dependency audit (UNAVAILABLE); mutation testing (SUBSTITUTED by hand mutants)

- Process: spec-evidence 0.18.0 (gate files: story-gate.md none, spec-gate.md spec-evidence 0.18.0)
- Lane: engineering, because this is Phase 3 of the engineer-owned epic #7, specified by the engineer in the issue and its decision comments; there is no product author.
- Spec: spec-evidence/2026-10-27-GH-4/SPEC.md (committed)
- Spec approval: obtained from Mike Crowe, commit `2d809e8` (`GH-4: spec approved`)
- Intent review: not run, engineering lane
- Source state: commit c6ec0050e32a40101ccb2cc40922d9b23ee9f2d3, the commit of the final run and the last code commit. The tree was dirty: an uncommitted `.atlas/` line in `.gitignore` that predates this story, and the untracked story files that the `built` commit adds
- Baseline: baseline-stamp.json at commit 2d809e83140d8efd43f943c163a95fdc9d4bf290, green

<details>
<summary>Stamp: green, 2/2 layers</summary>

```json
{
  "result": "green",
  "mode": "full",
  "expected_layers": [
    "tests",
    "secrets"
  ],
  "completed_layers": [
    "tests",
    "secrets"
  ],
  "layer_seconds": {
    "tests": 13.847,
    "secrets": 0.842
  },
  "layers": {
    "tests": {
      "baseline": "none",
      "selection": "off"
    },
    "secrets": {
      "baseline": "none",
      "selection": "off"
    }
  },
  "failed": null,
  "exit_code": 0,
  "commit": "c6ec0050e32a40101ccb2cc40922d9b23ee9f2d3",
  "dirty": true,
  "written": "2026-10-28T10:00:45.157Z"
}
```

</details>

### Spec → Test mapping

S7.1 is not `pass`:

| Scenario | Test | Status |
|---|---|---|
| S7.1 | Live, by the engineer, with substitutes: `auth-gmail` run once; a real `varlock run -- ./jev-mail run` over Proton and Gmail printed no error line, and wrote 25 Gmail state rows (census 3, heuristic 17, jev 5). The `BULK` category was `move Folders/BULK`, not `tag BULK` + `move [Gmail]/All Mail`, and no test message from a second address was sent. Read-only check (`/tmp/jev-s71-check.py`): 20 messages hold `Folders/BULK` and `JevProcessed`, 0 of them hold `INBOX`, and 0 of them are in `INBOX -label:JevProcessed`, the list the next run fetches. The engineer's mail client showed the run's messages under `Folders/BULK`. | unverified |

<details>
<summary>25/26 scenarios mapped and passing</summary>

| Scenario | Test | Status |
|---|---|---|
| S1.1 | tests/test_gmail.py::test_fetch_lists_unprocessed_mail_in_the_watched_label_and_parses_it | pass |
| S1.2 | tests/test_gmail.py::test_fetch_with_no_messages_returns_empty_and_gets_nothing | pass |
| S1.3 | tests/test_gmail.py::test_unknown_watched_label_is_a_config_error | pass |
| S2.1 | tests/test_gmail.py::test_tag_adds_an_existing_label_by_id | pass |
| S2.2 | tests/test_gmail.py::test_tag_creates_a_missing_label_once | pass |
| S2.3 | tests/test_gmail.py::test_move_adds_the_folder_label_and_removes_inbox | pass |
| S2.4 | tests/test_gmail.py::test_move_to_a_missing_label_creates_it | pass |
| S2.5 | tests/test_gmail.py::test_move_to_all_mail_only_archives | pass |
| S2.6 | tests/test_gmail.py::test_flag_and_seen_map_to_starred_and_unread | pass |
| S2.7 | tests/test_gmail.py::test_mark_processed_creates_and_adds_the_processed_label | pass |
| S2.8 | tests/test_gmail.py::test_http_error_becomes_gmail_error | pass |
| S3.1 | tests/test_config.py::test_accounts_mix_imap_and_gmail | pass |
| S3.2 | tests/test_config.py::test_unknown_backend_is_rejected | pass |
| S3.3 | tests/test_config.py::test_no_backend_and_no_host_is_still_the_empty_host_error | pass |
| S3.4 | tests/test_config.py::test_save_writes_backend_only_for_gmail | pass |
| S3.5 | tests/test_tui.py::test_wizard_keeps_the_gmail_backend | pass |
| S4.1 | tests/test_cli.py::test_auth_gmail_writes_an_owner_only_token | pass |
| S4.2 | tests/test_cli.py::test_auth_gmail_without_client_secrets_names_the_file | pass |
| S4.3 | tests/test_cli.py::test_run_without_a_gmail_token_names_auth_gmail | pass |
| S4.4 | tests/test_gmail.py::test_expired_token_is_refreshed_and_rewritten_owner_only | pass |
| S4.5 | tests/test_cli.py::test_run_reports_a_gmail_error_not_a_traceback | pass |
| S5.1 | tests/test_cli.py::test_run_opens_the_backend_each_account_names | pass |
| S5.2 | tests/test_cli.py::test_watch_polls_a_gmail_account | pass |
| S6.1 | tests/test_state.py::test_gmail_string_uid_falls_back_as_uid_prefix | pass |
| S6.2 | tests/test_gmail.py::test_importing_the_cli_loads_no_google_client | pass |
| S7.1 | see above | unverified |

| Must NOT | Proof | Status |
|---|---|---|
| M1 | `tests` layer, 172 passed; `git diff --stat 2d809e8 -- tests/` holds 470 insertions and 0 deletions | pass |
| M2 | tests/test_config.py::test_one_account_saves_exactly_as_before (unedited, M1); S3.4's IMAP half writes no `backend` key | pass |
| M3 | `git check-ignore client_secrets.json gmail-token.json` printed both; `secrets` layer, no leaks found; S4.1 asserts stdout holds the token path and not the token; `State.record` writes only uid, Message-ID, source, probabilities and actions | pass |
| M4 | S4.1 and S4.4 assert mode `0600`; S4.4 starts from a `0644` file; `_write_token` is the only writer of the token file | pass |
| M5 | `git diff 2d809e8 -- jev_mail/mailbox/base.py` changes only the six `uid` annotations, `int` to `int \| str` | pass |
| M6 | Every Gmail test injects the fake service or replaces `googleapiclient.discovery.build`, `Credentials.refresh` or `InstalledAppFlow`; S4.3 asserts the replaced `build` is never called | pass |

</details>

Break checks, each a one-off mutant reverted after the run. Each made its test fail:

- S6.1 passed before any code change. Mutant: `State.record` falls back to `uid:{int(mail.uid)}`; the test failed. Kept as regression armor for pre-existing behavior.
- S3.3 passed before any code change. Mutant: the Gmail host default applied to every backend (`if not mailbox.host:`); the test failed.

### Gauntlet (final fresh run)

Both layers PASSED.

<details>
<summary>2/2 layers PASSED</summary>

| Layer | Command | Status + result | Baseline | Selection | Log |
|---|---|---|---|---|---|
| tests | `mise exec -- uv run pytest -q` | PASSED — 172 passed in 12.74s, exit 0 (baseline: green at `2d809e8`) | none | off | work/tests.log |
| secrets | `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` | PASSED — 69 commits scanned, no leaks found | none | off | work/secrets.log |

</details>

Other layers of the loop:

| Layer | Status |
|---|---|
| Merge gate parity | N-A: the repository has no `.github/` and no CI configuration |
| Egress: new data paths | PASSED by reading: the token file is written only by `_write_token`, at mode 0600, beside `config.yaml`, and is git-ignored; stderr gains the account username and Google's error text (S4.5), and the token path (S4.3); stdout gains the token path only (S4.1); Gmail label names come from the engineer's own `config.yaml`; nothing new is logged |
| Real execution | PASSED: `auth-gmail` and `./jev-mail run` ran through the shipped entry point against the engineer's Gmail and Proton accounts; see S7.1 |
| Supply chain & secrets | Secrets PASSED (`secrets` layer above). New dependencies: `google-api-python-client` (the Gmail API client) and `google-auth-oauthlib` (the desktop OAuth flow), both named by GH-4's comment of 2026-10-25; dependency audit UNAVAILABLE, see below |
| Adversarial review | PASSED for `c6ec005`: round 1 had 0 findings and 3 hunches (see Review risks). No round 2: no fix changed code |

### Layers not run as specified

- N-A: Merge gate parity — no merge gate exists. Property-based tests — the change adds no round-trip, math or serialization invariant; base64 decoding of `raw` is the one parser input, and S1.1 covers it by example.
- UNAVAILABLE: static types — no type checker is configured; pyright, pinned, would catch the `Optional` access on `_service`. Lint + format — none configured; ruff, pinned, would catch unused imports. Changed-line coverage — none configured; pytest-cov with `--cov-fail-under` on the changed files would catch an untested branch such as the `ValueError` path of A10. Suite health — no randomized-order plugin; pytest-randomly, pinned, would catch order-dependent tests. Dependency audit — none configured; pip-audit, pinned, would catch known vulnerabilities in the two new dependencies and the packages they pull in.
- SUBSTITUTED: Mutation testing — two hand mutants (listed under the mapping) ran in place of a tool. They cannot find a surviving mutant that nobody wrote; mutmut, pinned, run on `git diff --name-only 2d809e8...HEAD`, would.

### Defect classes closed

none. The adversary reported no finding, and every hunch is listed under Review risks.

### Agent rounds

| Agent | Round | Model | Tokens |
|---|---|---|---|
| context-pack | 1 | claude-sonnet-5-5 | 64206/1889 |
| spec-evidence-adversary | 1 | claude-sonnet-5-5 | 238940/4338 |

### Process notes

- Gortex MCP tools were not available in this session, so source was read with shell and native file tools.
- The first live run stopped on Proton: `move BULK` tried to create a top-level folder, which Proton Bridge refuses. The engineer's git-ignored `config.yaml` was changed to `Folders/<NAME>` folders; no code changed. A read/write test then showed that both Bridge (under `Folders/`) and Gmail create a missing folder or label.
- The second live run stopped with a traceback: the engineer's `config.yaml` held a `move` with `value:` and no `folder:`. `load_config` accepts a `move` with no folder. This predates GH-4 and is left for its own issue; the config line was fixed.
- One account's IMAP error stops `run` before later accounts. This predates GH-4.
- Header folding: subjects from both backends can hold `\r\n` because `_decode_header` does not unfold. This predates GH-4 and showed in the live dry run.
- A new feature found during the live run, proposed sender-table rows, is filed as GH-9.
- The gauntlet stamps of the final run say `dirty: true`; see Source state.
