## Evidence Report — GH-5: Office 365 backend over Microsoft Graph (Tier 2)

## Summary

Delivered: `GraphMailbox` in `jev_mail/mailbox/graph.py`, a third `MailBackend` that reads the Office 365 Inbox over Microsoft Graph with `httpx`. An account picks it with `backend: o365`. `jev-mail auth-o365` runs the one-time device-code sign-in and writes an owner-only MSAL token cache beside `config.yaml`. `run` and `watch` open the right backend per account, and `watch` polls an `o365` account. `state.db` gains a per-account fetch cursor, and `GraphMailbox` reads `state.db` to skip mail it already processed. Why: the pinnsg.com tenant has basic auth off, so the IMAP backend cannot sign in.

How each criterion was proven:

- AC-1, sign-in and the token file: S1.1 to S1.3 (unit tests with the fake msal and the fake Graph) and S1.8 (`git check-ignore`). The `secrets` layer found no leak.
- AC-2, renewal and a rejected refresh token: S1.4 to S1.7.
- AC-3, the fetch rule (category, `state.db` row, text bodies, newest first, the cursor filter): S2.1 to S2.4, S2.9, S2.10, S2.11.
- AC-4, the 30-message, cap-25 case and the cursor: S2.5 to S2.8.
- AC-5, `tag`: S3.1, S3.2.
- AC-6, `move`, folder creation and the first-move rule: S3.3 to S3.5.
- AC-7, flag, read state, the `JevProcessed` marker, the `state.db` row and the dry run: S3.6 to S3.9.
- AC-8, `watch`: S4.5, S4.6. Config and wiring: S4.1 to S4.4, S4.7.
- What must not change: M1 to M8, by the `tests` and `secrets` layers and the diff readings below.
- Live: the engineer signed in with `auth-o365` and ran `run` against the pinnsg.com mailbox, and reported that it worked as expected. A read-only Graph check found a top-level `BULK` folder whose 10 newest messages all carry `BULK` and `JevProcessed`.

Not proven: S5.1 as the SPEC writes it. No message went through the `senders.csv` rule (0 `census` rows), the folder was `BULK`, not `Bulk`, and the follow-up dry run was not observed. Static types, lint, changed-line coverage, suite health and a dependency audit have no tool in this project. Mutation testing ran only as hand mutants. The cursor rule is stricter than the SPEC's text (A9).

## Agent decisions

<details><summary>10 agent decisions</summary>

### A1. Every Graph request asks for immutable ids
- Other option: take the new id from the `move` response and map the old id to it inside `GraphMailbox`.
- Why: `mark_processed` runs after `move` with the id fetched first, and an immutable id stays valid across a folder move (fact 7) with one header and no id map.
- Command: plan

### A2. The server filters only on `receivedDateTime`; the `JevProcessed` category and the `state.db` row are checked on the client
- Other option: add `not(categories/any(c:c eq 'JevProcessed'))` to the server `$filter`.
- Why: the `state.db` check must run on the client anyway, and the docs read do not confirm that Graph accepts a negated lambda next to the `$orderby` rule of fact 8.
- Command: plan

### A3. The cursor moves only after a complete fetch whose every returned message was marked, at the next fetch or on exit
- Other option: `cli._process_unprocessed` moves the cursor after each pass.
- Why: it keeps the rule inside `graph.py`, leaves the shared pipeline unchanged, and a message that failed classification holds the cursor back by itself (AC-4 boundary).
- Command: plan

### A4. The token source runs before every Graph request
- Other option: get one access token on enter and reuse it for the whole session.
- Why: `watch` runs for longer than the one-hour access token, and MSAL returns its cached token until it expires, so a call per request costs nothing extra.
- Command: plan

### A5. The authority is `organizations`, not a tenant-specific URL
- Other option: a config key for the tenant, such as `pinnsg.com`.
- Why: the account signs in with a work account and the client id is the same in every tenant, so no config key is needed.
- Command: plan

### A6. A 429 or 5xx stops the account for this run, with no retry
- Other option: retry with the `Retry-After` header.
- Why: `run` runs again on its next schedule and every unprocessed message is still eligible, so a retry loop adds code the story does not ask for.
- Command: plan

### A7. An `o365` account with a `folder` other than `INBOX` is refused
- Other option: look the folder up by display name and watch it.
- Why: the story names the Inbox only, and a silently ignored `folder` key would watch the wrong place.
- Command: plan

### A8. `graph.py` reuses `gmail._write_token` for the token file
- Other option: copy the four-line writer into `graph.py`.
- Why: one writer keeps the `0600` rule in one place, and importing `gmail.py` loads no Google library (fact 6).
- Command: plan

### A9. The cursor moves only after a complete fetch that returned at least one message, all of them marked
- Other option: keep "the walk saw at least one message", and pass a dry-run flag into `GraphMailbox` so a dry run never writes the cursor.
- Why: adversary round 1 found that a dry run with every message already processed wrote the cursor, against "The cursor". Asking for one returned and marked message closes it with no new parameter; a run that finds nothing new only waits one more run to move the cursor, and nothing is lost.
- Command: build

### A10. `auth-o365` replaces an unreadable token file instead of refusing
- Other option: stop with an error that tells the user to delete the file.
- Why: `auth-o365` is the repair every other token error names, so it must work on the file those errors report; a corrupt cache holds no sign-in to keep.
- Command: build

</details>

### Review risks

- S5.1 is `unverified`: the live run ran under different givens (see the mapping). The `senders.csv` path was never exercised on Graph, and no dry run after the live run was observed.
- A9 departs from the text of the SPEC's "The cursor": the SPEC moves the cursor after a complete walk that saw at least one message; the code also asks that the fetch returned at least one message. A run that finds nothing new leaves the cursor where it was. A7 was replaced by Decide 2 before approval; the code ignores `folder` for an `o365` account, as Decide 2 rules.
- Open hunch, not fixed: the MSAL account is matched by its `username` (the sign-in name), compared with the configured `username`. When the two differ, every run stops with "no Office 365 sign-in". The live run matched.
- Open hunch, not fixed: a `sqlite3.Error` in the cursor write at `__exit__` is not caught by `cli`, and would replace an exception already leaving the `with` block.
- Open hunch, not fixed: `@odata.nextLink` is requested as given, with the bearer token, and its host is not checked. Only a hostile Graph answer could point it elsewhere.
- Open hunch, not fixed: until a complete fetch sets the cursor, a capped run pages through processed mail from the newest message. The SPEC's Known limits name this cost.
- Open hunch, not fixed: a second Inbox message with the same `internetMessageId` as a processed one is skipped by the `state.db` check. `State.record` keys IMAP rows the same way.
- The live run processed 201 real messages with `max_emails_per_run: 200`, from a separate config directory; see S5.1 in the mapping.

### Not reached by review

- Round 1: calls 3/10; hunts not reached: 6 (invariants in surrounding code, only partly read), 8 (no EVIDENCE report in the diff), 9 (msal API names against the pinned 1.39.0), 10 (the Documentation section). Sites not opened: `jev_mail/config.py:170`, `jev_mail/actions.py`, `jev_mail/mailbox/base.py`.
- Round 2: calls 4/10; hunts not reached: 1 (no merge gate), 8 (the EVIDENCE report), 10 (the Documentation section). Sites not opened: `tests/test_graph.py`, `jev_mail/config.py:160-180`, `jev_mail/mailbox/gmail.py`, `jev_mail/tui`, and `work/diff.txt` whole (the reviewer read the HEAD source instead).

## Orientation

- Verdict: PASSED WITH LIMITS
- Delivered: a Microsoft Graph backend behind `MailBackend`, the `auth-o365` command, the `o365` backend value, and a per-account fetch cursor in `state.db`.
- Proven: 35/36 scenarios mapped and passing; M1 to M8 passing
- Not proven: S5.1 as written (unverified, live substitute ran); static types, lint, changed-line coverage, suite health and dependency audit (UNAVAILABLE); mutation testing (SUBSTITUTED by hand mutants)

- Process: spec-evidence 0.18.0
- Spec: spec-evidence/2026-10-30-GH-5/SPEC.md (committed)
- Spec approval: obtained from Mike Crowe, commit `bf69bc9` (`GH-5: spec approved`)
- Intent review: round 1 found three gaps, all folded before approval (decisions.md Revision 1): "The cursor" opens `state.db` at each fetch once it exists, with the new S2.10; the Inbox refusal was named as an addition (later removed by Decide 2); S2.1 checks the full `Prefer` value, and the new S3.9 proves `mark_processed` after `move` with the immutable id. Round 2 found no gap.
- Source state: commit c9fe6dd1f18c2eff0ced1e7398d3c1bd4db74983, the commit of the final run and the last code commit. The tree was dirty: an uncommitted `.atlas/` line in `.gitignore` that predates this story, and the story files that the `built` commit adds
- Baseline: baseline-stamp.json at commit bf69bc93f343c82f30d02a4683b6284ca9496e7b, green (dirty: the same `.atlas/` line)

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
    "tests": 13.545,
    "secrets": 1.073
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
  "commit": "c9fe6dd1f18c2eff0ced1e7398d3c1bd4db74983",
  "dirty": true,
  "written": "2026-10-30T21:11:00.673Z"
}
```

</details>

### Spec → Test mapping

S5.1 is not `pass`:

| Scenario | Test | Status |
|---|---|---|
| S5.1 | Live, by the engineer, with substitutes. The engineer ran `auth-o365` and `run` through the shipped entry point (`.venv/bin/jev-mail --dir work/o365-live`, not `./jev-mail`, so that the Proton and Gmail accounts kept their `Folders/` folders). The config mirrored the main categories with the folder `BULK`, not `Bulk`, with `tag BULK` + `move BULK` on `BULK`, and `max_emails_per_run: 200`. Read-only Graph check: one top-level `BULK` folder; its 10 newest messages all carry `BULK` and `JevProcessed`; the 5 newest Inbox messages all carry `JevProcessed`. `state.db` holds 201 rows: 140 `heuristic`, 61 `jev`, 0 `census`, so no message went through the `senders.csv` rule. The follow-up dry run was not observed. The engineer reported that the run worked as expected (2026-10-30). | unverified |

<details>
<summary>35/36 scenarios mapped and passing</summary>

| Scenario | Test | Status |
|---|---|---|
| S1.1 | tests/test_cli.py::test_auth_o365_shows_the_code_and_writes_an_owner_only_token | pass |
| S1.2 | tests/test_cli.py::test_auth_o365_declined_writes_no_token | pass |
| S1.3 | tests/test_cli.py::test_no_o365_token_names_auth_o365_before_any_graph_call[run] and [watch] | pass |
| S1.4 | tests/test_graph.py::test_a_renewed_token_is_saved_and_used | pass |
| S1.5 | tests/test_graph.py::test_the_token_source_runs_before_every_request | pass |
| S1.6 | tests/test_cli.py::test_a_rejected_refresh_token_stops_the_account | pass |
| S1.7 | tests/test_graph.py::test_a_cache_with_no_matching_account_names_the_account_and_auth_o365 | pass |
| S1.8 | Diff reading: `git check-ignore o365-token.json` printed `o365-token.json`, exit 0 | pass |
| S2.1 | tests/test_graph.py::test_fetch_asks_for_text_bodies_and_builds_the_email | pass |
| S2.2 | tests/test_graph.py::test_fetch_skips_the_category_and_the_state_row | pass |
| S2.3 | tests/test_graph.py::test_a_cursor_filters_the_list_request | pass |
| S2.4 | tests/test_graph.py::test_a_message_older_than_the_cursor_is_not_fetched | pass |
| S2.5 | tests/test_cli.py::test_a_capped_run_takes_the_newest_and_the_next_run_the_rest | pass |
| S2.6 | tests/test_cli.py::test_the_cursor_waits_for_a_complete_fetch | pass |
| S2.7 | tests/test_cli.py::test_a_failed_classify_holds_the_cursor_back | pass |
| S2.8 | tests/test_cli.py::test_mail_that_arrives_during_a_pass_is_taken_by_the_next | pass |
| S2.9 | tests/test_graph.py::test_fetch_follows_the_next_link_as_given | pass |
| S2.10 | tests/test_cli.py::test_a_state_db_created_after_enter_is_read_by_the_next_fetch | pass |
| S2.11 | tests/test_cli.py::test_a_graph_429_stops_the_account | pass |
| S3.1 | tests/test_graph.py::test_tag_adds_a_category_and_keeps_the_others | pass |
| S3.2 | tests/test_graph.py::test_tag_already_there_sends_no_patch | pass |
| S3.3 | tests/test_graph.py::test_move_to_a_folder_that_exists | pass |
| S3.4 | tests/test_graph.py::test_move_creates_a_missing_folder_once | pass |
| S3.5 | tests/test_cli.py::test_only_the_first_move_runs_on_graph | pass |
| S3.6 | tests/test_graph.py::test_flag_and_read_state_send_one_patch_each | pass |
| S3.7 | tests/test_cli.py::test_a_run_marks_the_category_and_writes_the_state_row | pass |
| S3.8 | tests/test_cli.py::test_a_dry_run_on_graph_changes_nothing | pass |
| S3.9 | tests/test_graph.py::test_the_marker_lands_after_a_move_with_the_immutable_id | pass |
| S4.1 | tests/test_config.py::test_o365_account_defaults_its_host_and_poll_interval | pass |
| S4.2 | tests/test_config.py::test_unknown_backend_names_all_three | pass |
| S4.3 | tests/test_config.py::test_save_writes_backend_for_o365 | pass |
| S4.4 | tests/test_cli.py::test_run_opens_graph_for_an_o365_account | pass |
| S4.5 | tests/test_cli.py::test_watch_polls_an_o365_account | pass |
| S4.6 | tests/test_cli.py::test_watch_refuses_two_o365_accounts | pass |
| S4.7 | tests/test_graph.py::test_importing_the_cli_loads_no_msal | pass |
| S5.1 | see above | unverified |

| Must NOT | Proof | Status |
|---|---|---|
| M1 | `tests` layer, 221 passed (172 at the baseline plus 49 new); `git diff --stat bf69bc9 -- tests/` holds 958 insertions and 0 deletions | pass |
| M2 | `save_config` is not changed by the diff; tests/test_config.py::test_one_account_saves_exactly_as_before and test_save_writes_backend_only_for_gmail pass unedited | pass |
| M3 | `git check-ignore o365-token.json` printed it; `secrets` layer, 77 commits scanned, no leaks found; S1.1 asserts stdout is exactly the flow message and the token path; `State` writes only the message key, source, probabilities, actions and the cursor time | pass |
| M4 | S1.1 and S1.4 assert mode `0600`, and S1.4 starts from a `0644` file; every write goes through `_save_cache`, which calls `gmail._write_token`; the live token file read `600` | pass |
| M5 | `git diff bf69bc9 -- jev_mail/mailbox/base.py jev_mail/mailbox/imap.py jev_mail/mailbox/gmail.py` is empty | pass |
| M6 | Every Graph test builds `GraphMailbox` with the fake Graph (`httpx.MockTransport`) or replaces it in `cli`; every sign-in test replaces `msal.PublicClientApplication` with the fake msal | pass |
| M7 | tests/test_state.py::test_an_existing_state_db_opens_with_its_processed_rows opens a `processed` table made with the old schema and reads its row | pass |
| M8 | `git diff bf69bc9 -- jev_mail/tui` is empty | pass |

</details>

Break checks, each a one-off mutant reverted after the run. Each made its test fail:

- S4.7 passed before `cli` imported `graph.py`. Mutant: `import msal` at the top of `graph.py`; the test failed.
- S2.7, S2.8 and S3.5 passed when first run, because `graph.py` was written before them. Mutants: the cursor moves even with unmarked messages (S2.7 failed); the cursor is set to a fixed late time instead of the newest seen (S2.8 failed); the first-move rule in `cli._process_unprocessed` removed (S3.5 failed).
- S4.6 is the existing `watch` rule. Mutant: the account-count check removed; the test failed.
- S4.3 passed once S4.1's load passed, because `save_config` already writes any non-IMAP backend. Mutant: `backend` written only for `gmail`; the test failed.
- S2.6 mutant: a capped fetch counted as complete; the test failed. S2.10 mutant: no `state.db` open at fetch; the test failed.

### Gauntlet (final fresh run)

Both layers PASSED.

<details>
<summary>2/2 layers PASSED</summary>

| Layer | Command | Status + result | Baseline | Selection | Log |
|---|---|---|---|---|---|
| tests | `mise exec -- uv run pytest -q` | PASSED — 221 passed in 12.33s, exit 0 (baseline: green at `bf69bc9`) | none | off | work/tests.log |
| secrets | `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` | PASSED — 77 commits scanned, no leaks found | none | off | work/secrets.log |

</details>

Other layers of the loop:

| Layer | Status |
|---|---|
| Merge gate parity | N-A: the repository has no `.github/` and no CI configuration |
| Egress: new data paths | PASSED by reading. The token file is written only through `_save_cache`, at mode 0600, beside `config.yaml`, and is git-ignored. stdout gains Microsoft's device-flow message and the token path (S1.1). stderr gains the account username, MSAL's error code, and for a Graph error the method, the path and up to 300 characters of Graph's error body (S2.11). `state.db` gains one cursor row per account: the account key and a `receivedDateTime` string. Nothing new is logged. |
| Real execution | PASSED: `auth-o365` and `run` ran through the installed entry point against the engineer's Office 365 mailbox; see S5.1 |
| Supply chain & secrets | Secrets PASSED (`secrets` layer above). New dependency: `msal` 1.39.0 (pulls `pyjwt` 2.15.1), for the device-code flow, silent renewal and the serializable token cache, approved by the story's Constraints and GH-5's comment of 2026-10-25. Dependency audit UNAVAILABLE, see below |
| Adversarial review | PASSED for `c9fe6dd`: round 1 read `e73f03f` and had 3 advisory findings, all fixed in `c9fe6dd` (see Defect classes closed); round 2 read `c9fe6dd` and had 0 findings and 3 hunches (see Review risks). No later commit changed code |

### Layers not run as specified

- N-A: Merge gate parity — no merge gate exists. Property-based tests — the change adds no round-trip, math or serialization invariant beyond the MSAL cache, which the library owns; the message JSON mapping is covered by S2.1 by example.
- UNAVAILABLE: static types — no type checker is configured; pyright, pinned, would catch the `Optional` access on `_http` and `_token`. Lint + format — none configured; ruff, pinned, would catch unused imports. Changed-line coverage — none configured; pytest-cov with `--cov-fail-under` on the changed files would catch an untested branch such as the `OSError` path of `authorize_o365`'s `acquire_token_by_device_flow`. Suite health — no randomized-order plugin; pytest-randomly, pinned, would catch order-dependent tests. Dependency audit — none configured; pip-audit, pinned, would catch known vulnerabilities in `msal` and `pyjwt`.
- SUBSTITUTED: Mutation testing — eight hand mutants (listed under the mapping) ran in place of a tool. They cannot find a surviving mutant that nobody wrote; mutmut, pinned, run on `git diff --name-only bf69bc9...HEAD`, would.

### Defect classes closed

- Generator: a token-file read, an msal call, a token write, or a 2xx body parse in `graph.py` whose `OSError` or `ValueError` escaped as a traceback, or as the IMAP "couldn't connect to host:993" message. Sites, enumerated in commit `c9fe6dd`: 1 token read and deserialize in `_token_source`, fixed; 2 `PublicClientApplication` in `_token_source`, fixed; 3 `get_accounts`, not-applicable (it reads the local cache only); 4 `acquire_token_silent_with_error`, fixed; 5 deserialize in `authorize_o365`, fixed (A10); 6 `PublicClientApplication` in `authorize_o365`, fixed; 7 `initiate_device_flow`, fixed; 8 `acquire_token_by_device_flow`, fixed (same block as 7, no own test); 9 `_write_token` in both, fixed; 10 `response.json` in `_request`, fixed. Tests: tests/test_graph.py::test_a_corrupt_token_file_raises_graph_error_naming_auth_o365, test_a_network_failure_at_sign_in_raises_graph_error, test_a_token_write_that_fails_raises_graph_error, test_a_2xx_answer_that_is_not_json_raises_graph_error; tests/test_cli.py::test_run_with_a_corrupt_token_names_auth_o365, test_a_network_failure_at_renewal_names_no_imap_port, test_auth_o365_replaces_a_corrupt_token_file, test_auth_o365_network_failure_is_an_error_not_a_traceback. Each was seen failing first.
- Generator: a cursor write during a dry run. One site, `fetch_unprocessed`'s pending rule, fixed by A9. Test: tests/test_graph.py::test_a_fetch_that_returns_nothing_leaves_the_cursor, seen failing first.

### Agent rounds

| Agent | Round | Model | Tokens |
|---|---|---|---|
| context-pack | 1 | claude-sonnet-5-5 | 70324/1897 |
| spec-evidence-intent | 1 | claude-sonnet-5-5 | 48133/2319 |
| spec-evidence-intent | 2 | claude-sonnet-5-5 | 48439/1389 |
| spec-evidence-adversary | 1 | claude-sonnet-5-5 | 200137/9145 |
| spec-evidence-adversary | 2 | claude-sonnet-5-5 | 171659/3915 |

### Process notes

- Gortex MCP tools were not available in this session, so source was read with shell and native file tools.
- The first full-suite run after the CLI tests failed 2 existing GH-3 tests: the new tests imported `ACCOUNT_KEY` from `tests/test_graph.py` and shadowed `test_cli.py`'s own constant. The import was renamed `GRAPH_KEY`; no existing test was edited.
- The build ran on branch `GH-5-o365`, cut from `master` at the approval commit `bf69bc9`, not at `6fa85f3` as the SPEC's Isolation line says; `bf69bc9` holds only story artifacts on top of `6fa85f3`.
- The adversary's range started at `88a5529`, the merge base with `origin/HEAD`, so it also held the GH-5 story commits; the code commits are `e73f03f` and `c9fe6dd`.
- `.gitignore` gained only `o365-token.json` in `e73f03f`; the engineer's uncommitted `.atlas/` line stayed unstaged.
- The live check ran from a git-ignored `work/o365-live/` directory whose `.env` and `senders.csv` are links to the project's files.
- The gauntlet stamps of the final run say `dirty: true`; see Source state.
