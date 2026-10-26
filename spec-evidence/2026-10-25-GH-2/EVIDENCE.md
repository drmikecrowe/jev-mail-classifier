## Evidence Report — GH-2: Mail backend interface and persistent state (Tier 2)

## Summary

Delivered: the IMAP code now sits behind a `MailBackend` interface in the `jev_mail/mailbox/` package, a real run writes a local `state.db` record after each `$JevProcessed` keyword, and `config.yaml` accepts an `accounts:` list beside the one-account `mailbox:` form. This prepares Phase 2 (Gmail and Graph backends). During the build the live check found that an email over Jev's token limit failed the whole run; the engineer revised the SPEC (Revision 2, Decide 5), and the text sent to Jev now holds at most the first 20,000 body characters.

How each acceptance criterion was proven:

- Every name imported from `jev_mail.mailbox` still imports from it, and `jev_mail/mailbox.py` is gone: S1.1, a unit test.
- The interface names the six pipeline methods and none of the IDLE methods, and `run_action` drives any backend: S1.2 and S1.3, unit tests.
- A fetched email carries its Message-ID, sender and List-Unsubscribe header, or empty strings: S1.4 and S1.5, unit tests.
- A `mailbox:` config loads and saves exactly as at `e393a22`; an `accounts:` config loads every account; both keys, an empty list or a malformed list are refused: S2.1 to S2.5, unit tests, with S2.5 checked against output captured at `e393a22`.
- The wizard edits the first account and writes the other accounts back as written, with no literal secret: S2.6, a unit test.
- A real run writes the keyword and then one state row; a dry run writes nothing and creates no `state.db`: S3.1, S3.2, S3.5 and S3.6, unit tests.
- `run` processes each account in turn, and `watch` with more than one account refuses to start: S3.3 and S3.4, unit tests.
- The IMAP code moved unchanged apart from the allowed lines: S4.1, a diff reading.
- The dry-run output is byte-identical on fixed inputs at `e393a22` and on the branch: S5.1, a unit test run on both commits. On the live mailbox, the branch run exits 0 and prints only dry-run lines and the cap notice: S5.2, a live run recorded with counts only.
- The text sent to Jev holds at most the first 20,000 body characters: S6.1 and S6.2, unit tests.

Every check ran, and all 22 scenarios pass. Not proven: the adversary did not review the last code commit (the S6 body cap). Lint, type checks, changed-line coverage, property-based tests and randomized order are `UNAVAILABLE`. Mutation testing is `SUBSTITUTED` by hand-written mutants.

## Agent decisions

<details><summary>8 agent decisions</summary>

### A1. The state row's account key is `<host>/<username>`

- Other option: a new `name` field on each account, defaulting to some fixed value for the `mailbox:` form.
- Why: it needs no new config field and stays the same when a `mailbox:` file is rewritten as an `accounts:` list.
- Command: hotfix

### A2. A missing Message-ID is stored as `uid:<uid>`

- Other option: skip the state row for an email with no Message-ID.
- Why: the brief says the row is written alongside every keyword; a stand-in keeps that true, at the cost of a key that is unique only within one folder.
- Command: hotfix

### A3. `state.db` lives in the `--dir` directory, beside `config.yaml`

- Other option: a `state_path` setting in `config.yaml`.
- Why: `./jev-mail` already resolves `config.yaml` and `.env` from `--dir`, and a new setting is a config option nobody asked for.
- Command: hotfix

### A4. `AppConfig` keeps `mailbox` as the first account and adds `extra_accounts`, with an `accounts` property

- Other option: replace `AppConfig.mailbox` with an `accounts` list.
- Why: every existing constructor, the TUI and the tests use `config.mailbox`; keeping it means none of them change.
- Command: hotfix

### A5. A failed state write stops the run

- Other option: catch `sqlite3.Error`, print a warning, and go on.
- Why: a silent gap in the record is worse than a visible stop, and the keyword is already set, so no email is billed twice.
- Command: hotfix

### A6. The decision source written in this phase is `jev`

- Other option: leave `source` empty until Phase 2 adds other sources.
- Why: every decision in this phase comes from the Jev call, and an explicit value lets Phase 2 add others without a migration.
- Command: hotfix

### A7. `cmd_run` opens `state.db` after the first account connects, not before the loop

- Other option: open `State` once before the account loop, whenever the run is not a dry run.
- Why: a run that cannot reach any server then leaves no empty `state.db` behind, including in the cwd of the existing connection-error test that runs with `--dir .`.
- Command: build

### A8. `watch` also writes a state row after each keyword

- Other option: `watch` writes no state rows in this phase, and only `run` does.
- Why: decisions.md restates the brief as "a state row is written right after `mark_processed`, and only when `mark_processed` runs"; `watch` calls `mark_processed` too, and the record would otherwise have gaps.
- Command: build

</details>

### Review risks

- The adversary's two rounds read `ca7e032` at the latest. Commit `3086823` (the S6 body cap: 5 lines in `jev_mail/mailbox/base.py` and two tests) came after Revision 2 and has had no adversarial review; the loop allows no third round, so the adversarial layer is not-run for that commit.
- Round 2 finding, triaged as no change: a `sqlite3.Error` from opening `state.db` or from `State.record` ends the run with a raw traceback, not an `error:` line, and in `run` the remaining accounts are skipped. The stop is A5 and a SPEC known limit; the traceback form is not tested.
- Round 1 finding 3, triaged as no change: a webhook action's URL is copied into each state row's `actions` JSON. `config.yaml` already holds the same URL in plaintext in the same directory, and both files are git-ignored.
- The adversary could not open files outside the diff in either round: the Gortex hook blocked its Grep and Read, so `jev_mail/tui/app.py` and the other callers of `config.mailbox` were not reviewed (hunt 2 not reached, both rounds).
- A folded `From` header keeps its `\r\n ` in `Email.sender` (checked with a synthetic message; a folded Message-ID decodes clean). `sender` is not read anywhere in this phase.
- The S5.2 live run used a scratch copy of the live `config.yaml` (its cap was already 5) with secrets from `varlock run`, because the repository has no `.env`. It ran `jev_mail.cli.main` with `--dir <scratch>`, the code `./jev-mail` execs, not the `./jev-mail` wrapper itself.
- Each adversary transcript records two model names, `claude-opus-5-5` and `claude-sonnet-5-5`; `adversary_model` is unset, so the spawn named no model.

### Not reached by review

- Round 1: calls 3/10; hunts not reached: 2 (callers of changed functions outside the diff: the Grep was blocked by the Gortex hook and I have no Gortex tools; tui/ and classify.py were not opened), 8, 9; sites not opened: jev_mail/tui/app.py, jev_mail/tui/screens/mailbox_screen.py, jev_mail/classify.py, jev_mail/cli.py (cmd_run header, where config_path is defined), tools/gauntlet-layers.json, spec-evidence/2026-10-25-GH-2/EVIDENCE.md (not in the diff, so hunt 8 was not possible)
- Round 2: calls 4/10; hunts not reached: 1 (there is no merge gate, so only the manifest could have been compared), 2 for callers outside the diff: the tui, tests, and any other user of config.mailbox or _mailbox_error_message, 4 for input fuzzing of the YAML accounts shapes, 9, 10; sites not opened: /home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/tui/app.py (the Gortex hook blocked Grep and Read on indexed source, and I have no Gortex tools, so I could not check how _after_mailbox and other config.mailbox users behave with accounts), /home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/config.py:_interpolate (behaviour with an unset ${VAR} in accounts 2 to n), /home/mcrowe/Programming/AI/jev-mail-classifier/spec-evidence/2026-10-25-GH-2/work/diff.txt lines 621-1408 (the test diffs and the remaining evidence files were not read), /home/mcrowe/Programming/AI/jev-mail-classifier/tools/gauntlet-layers.json

## Orientation

- Verdict: PASSED WITH LIMITS
- Delivered: the `MailBackend` interface and `jev_mail/mailbox/` package, a `state.db` record after each keyword, an `accounts:` list in `config.yaml`, and a 20,000-character cap on the body sent to Jev.
- Proven: 22/22 scenarios mapped and passing
- Not proven: adversarial review of commit `3086823` (not-run, see Review risks); lint + format, static types, changed-line coverage, property-based tests and suite health `UNAVAILABLE`; mutation testing `SUBSTITUTED`

- Process: spec-evidence 0.16.2 (gate files: story-gate.md none, spec-gate.md spec-evidence 0.16.2)
- Spec: spec-evidence/2026-10-25-GH-2/SPEC.md (committed)
- Spec approval: obtained from Mike Crowe, at `09995a6` and again for Revision 2 at `22d3c49`
- Intent review: not run, engineering lane
- Source state: commit `3086823` for the final run; the adversary's last review read `ca7e032`
- Baseline: baseline-stamp.json at commit `09995a6`, green

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
    "tests": 11.753,
    "secrets": 0.923
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
  "commit": "3086823fe9ec7807a0f974b8db35a9625fba0576",
  "dirty": true,
  "written": "2026-10-26T01:14:44.542Z"
}
```

`dirty: true` means only the untracked `spec-evidence/2026-10-25-GH-2/baseline-stamp.json` (`git status --short` showed no other entry). It is committed with this report.

</details>

### Spec → Test mapping

Every row passes. Break checks: hand-written mutants, each run against the test named and each restored. 9 were killed and none survived: `watch` state forced to `None` (A8 test), dry run opens `State` (S3.2), probability format `.3f` (S5.1), always write `accounts:` (S2.5), `mark_processed` removed (S3.1), `INSERT OR IGNORE` (S3.6), `uid:` prefix dropped (S3.5), cap 19,999 and cap 20,001 (S6.1, S6.2). S1.1 to S1.5, S2.1 to S2.4, S2.6, S3.1, S3.3 to S3.6 and S6.1 were first seen failing (RED) before the code that satisfies them. S2.5, S3.2, S5.1 and S6.2 passed when first run (pre-existing behavior kept as regression armor); their mutants above prove each can fail.

<details>
<summary>22/22 scenarios mapped and passing</summary>

| Scenario | Test | Status |
|---|---|---|
| S1.1 | tests/test_package.py::test_mailbox_package_keeps_every_import | pass |
| S1.2 | tests/test_package.py::test_mail_backend_names_the_pipeline_methods_and_not_idle | pass |
| S1.3 | tests/test_actions.py::test_run_action_drives_any_mail_backend | pass |
| S1.4 | tests/test_mailbox.py::test_fetch_unprocessed_reads_message_id_sender_and_list_unsubscribe | pass |
| S1.5 | tests/test_mailbox.py::test_missing_headers_are_empty_strings | pass |
| S2.1 | tests/test_config.py::test_mailbox_form_loads_as_one_account (the expected `MailboxConfig` is the one `load_config` printed at `e393a22` for the same file) | pass |
| S2.2 | tests/test_config.py::test_accounts_list_loads_every_account | pass |
| S2.3 | tests/test_config.py::test_mailbox_and_accounts_together_is_refused | pass |
| S2.4 | tests/test_config.py::test_empty_or_invalid_accounts_is_refused (2 cases); tests/test_config.py::test_malformed_accounts_is_refused (3 cases, adversary round 1) | pass |
| S2.5 | tests/test_config.py::test_one_account_saves_exactly_as_before (the expected text is `save_config` output captured at `e393a22`) | pass |
| S2.6 | tests/test_config.py::test_wizard_edit_keeps_other_accounts_as_written | pass |
| S3.1 | tests/test_cli.py::test_real_run_marks_processed_then_writes_one_state_row (zero rows exist when `mark_processed` runs) | pass |
| S3.2 | tests/test_cli.py::test_dry_run_marks_nothing_and_creates_no_state_db | pass |
| S3.3 | tests/test_cli.py::test_run_processes_each_account_in_turn | pass |
| S3.4 | tests/test_cli.py::test_watch_refuses_more_than_one_account | pass |
| S3.5 | tests/test_state.py::test_missing_message_id_is_stored_as_uid | pass |
| S3.6 | tests/test_state.py::test_recording_the_same_email_again_replaces_its_row | pass |
| S4.1 | `git diff -M e393a22 -- jev_mail/mailbox.py jev_mail/mailbox/imap.py`: rename at 88% similarity, 16 insertions and 14 deletions. The changes are the `dataclass` import removed, the `Email` import added, the `Email` class removed, the `Email(...)` call expanded with the three header reads, and `_decode_subject` delegating to the new `_decode_header`. `git diff e393a22 -- tests/test_mailbox.py`: 3 removed lines, the three `IMAPClient` patch targets; the rest is new test functions | pass |
| S5.1 | tests/test_cli.py::test_dry_run_output_is_unchanged on the branch; the same test file also passed against the `e393a22` code (a detached worktree, `PYTHONPATH` pointed at it, with `jev_mail.cli` confirmed loaded from the worktree): 1 passed | pass |
| S5.2 | Live run, `jev_mail.cli.main --dir <scratch> run --dry-run` under `varlock run`, cap 5. `e393a22`: exit 1, 1 line (the cap notice), 0 lines of another shape, unprocessed 5238 before and 5238 after, no `state.db`; the cause is `ProviderError` HTTP 400 `max_tokens_exceeded` (decisions.md fact 11). Branch at `3086823`: exit 0, 6 lines (5 dry-run lines, 1 cap notice), 0 lines of another shape, 0 stderr lines, unprocessed 5238 before and 5238 after, no `state.db` | pass |
| S6.1 | tests/test_mailbox.py::test_state_sends_at_most_20000_body_characters | pass |
| S6.2 | tests/test_mailbox.py::test_state_keeps_a_body_of_exactly_20000_characters | pass |

</details>

Must NOT:

| Clause | Proof | Status |
|---|---|---|
| M1 | `tests` layer: 97 passed. The only removed lines in existing test files are the three patch targets (S4.1) | pass |
| M2 | S2.1, S2.5 | pass |
| M3 | S2.6; tests/test_config.py::test_save_config_never_writes_literal_secrets (M1) | pass |
| M4 | S3.1, plus the `mark_processed` mutant | pass |
| M5 | S3.2, S5.2 | pass |
| M6 | `git diff --stat e393a22 -- jev_mail/providers/` prints nothing | pass |
| M7 | `git diff --stat e393a22 -- pyproject.toml uv.lock` prints nothing | pass |
| M8 | S1.5; the existing keyword-built `Email(...)` tests pass (M1) | pass |
| M9 | `secrets` layer: no leaks found; `git check-ignore state.db` prints `state.db`; `.gitignore` gains `state.db` in `6e57a47`, the commit that adds `jev_mail/state.py` | pass |
| M10 | S6.1 (`body` keeps its tail); S5.1 (dry-run lines); tests/test_actions.py::test_run_action_webhook_posts_json (webhook payload, M1) | pass |

### Gauntlet (final fresh run)

The adversarial review is not-run for `3086823`, as stated above.

<details>
<summary>2/2 layers PASSED</summary>

| Layer | Command | Status + result | Baseline | Selection | Log |
|---|---|---|---|---|---|
| tests | `mise exec -- uv run pytest -q` | PASSED — 97 passed in 10.64s | none | off | work/tests.log |
| secrets | `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` | PASSED — 41 commits scanned, no leaks found | none | off | work/secrets.log |

</details>

Other layers of the loop:

| Layer | Status + result |
|---|---|
| Merge gate parity | N-A — no `.github/` and no `.pre-commit-config.yaml`; 0 checks |
| Egress: new data paths | SUBSTITUTED — read by hand. `state.db` is written beside `config.yaml`, is git-ignored, and holds the account key (`host/username`), Message-ID or `uid:<n>`, probabilities, the applied actions (including any webhook URL) and a UTC time; no subject or body. The 20,000-character cap shrinks what is sent to Jev. A reading cannot detect a path it missed |
| Full test suite | PASSED — 97 passed; baseline green at `09995a6`, so 0 new failures |
| Static types | UNAVAILABLE — no type checker declared |
| Lint + format | UNAVAILABLE — no linter or formatter declared |
| Changed-line coverage | UNAVAILABLE — no coverage tool declared |
| Mutation testing | SUBSTITUTED — 9 hand-written mutants, all killed (see the mapping); the file set was picked by hand, not derived from `git diff --name-only`, so a mutant nobody wrote cannot be detected |
| Property-based tests | UNAVAILABLE — no property-testing tool declared |
| Real execution | PASSED — S5.2 live run on the branch, exit 0 |
| Supply chain & secrets | PASSED — no new dependency (M7); `secrets` layer clean |
| Suite health | UNAVAILABLE — no randomized-order plugin declared |
| Adversarial review | 2 rounds, on `6e57a47` and `ca7e032`; not-run for `3086823` |

### Layers not run as specified

- N-A: merge gate parity — the repository has no merge gate.
- UNAVAILABLE: static types (for example mypy), lint + format (for example ruff), changed-line coverage (for example pytest-cov with diff-cover), property-based tests (for example hypothesis), suite health (for example pytest-randomly). None is declared in `pyproject.toml`, `mise.toml` or `tools/gauntlet-layers.json`.
- SUBSTITUTED: mutation testing — hand-written mutants instead of a tool such as mutmut; this cannot detect a surviving mutant nobody wrote. Egress — read by hand; this cannot detect a missed path. Adversarial review of `3086823` — none; the round limit was reached before Revision 2.

### Defect classes closed

- Generator: a `config.yaml` value that `load_config` uses as a mapping or a list without checking its type.
- Enumerated by: `rg -n '\.get\(|\.items\(\)|raw\[' jev_mail/config.py`
- Sites: 6. `jev_mail/config.py:113`, the `accounts:` list and its entries — fixed in `ca7e032` (type check, `ConfigError`). `jev_mail/config.py:121` (`mailbox:` block), `:124` (`jev:` block), `:137` (`categories:` mapping), `:133` (each category), `:30` (`Action.from_dict`, each action) — not applicable: unchanged code from before `e393a22`, outside this change's Touches, and left as found.

### Agent rounds

| Agent | Round | Model | Tokens |
|---|---|---|---|
| context-pack | 1 | claude-opus-5-5, claude-sonnet-5-5 | 120761/2437 |
| spec-evidence-intent | not run, engineering lane | unrecorded | unrecorded |
| spec-evidence-adversary | 1 | claude-opus-5-5, claude-sonnet-5-5 | 160811/3515 |
| spec-evidence-adversary | 2 | claude-opus-5-5, claude-sonnet-5-5 | 180446/3467 |

### Process notes

- The first S5.2 live run exited 1 on both commits. The cause was triaged with requests that printed only status codes, lengths and `error_type`: Jev answered HTTP 400 `max_tokens_exceeded` for bodies of 104,964 and 122,085 characters (decisions.md fact 11). The engineer chose to revise the SPEC (Revision 2, Decide 5), approved it at `22d3c49`, and S6 was built RED first.
- The repository has no `.env`; its secrets come from `varlock` (`.env.schema`). The live runs used `varlock run`, and no secret value was printed.
- The Gortex hook blocks `grep`, `cat` and Read on indexed source; source was read and edited through the Gortex file tools.
- One shell heredoc that appended tests was refused by the command-safety hook (an unbalanced quote parse); the same text went in through the Gortex edit tool.
