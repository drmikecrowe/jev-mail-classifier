## Evidence Report — GH-8 one ProviderError on one email aborts the whole run (Tier 2)

## Summary

Delivered: `_process_unprocessed` in `jev_mail/cli.py` now catches `ProviderError` for each email, prints one `error:` line with the email's UID to stderr, leaves that email unmarked, and goes on to the next email. It returns the number of failing emails. `cmd_run` exits 1 when any email failed, after every account. `cmd_watch` keeps looping. This stops one provider error from aborting the run, and from aborting every later run on the same newest unprocessed email. `CLAUDE.md` and `README.md` now name the TypeSafe-direct adapter as verified against a live key.

Each criterion and its proof:

- A failing email gets one `error:` line and no keyword, action or state row, and the emails after it are still processed: S1.1, S1.2 and M4, by unit tests that pass.
- A dry run does the same: S1.3, by a unit test that asserts the exact stdout and stderr.
- `run` exits 1 when any email failed, only after every account, and exits 0 with no failure: S1.4, S2.1, S2.2 and S2.3, by unit tests. S2.3 passed before the fix, and a throwaway mutant showed that it can fail.
- `watch` keeps going after a failing email: S3.1, by a unit test.
- The docs: S4.1, by the cited lines `CLAUDE.md:36` and `README.md:218` to `:219`.
- What must not change: M1, M5 and M6 by `git diff` readings against `b29cc70`; M2 by S1.3 and the existing dry-run test; M3 and M7 by new tests, each break-checked with a throwaway mutant.

Not proven: no project tool for static types, lint, changed-line coverage or mutation testing (UNAVAILABLE). Mutation testing was substituted by three hand mutants. The real CLI was not run against a live mailbox (UNAVAILABLE). See "Layers not run as specified".

## Agent decisions

<details><summary>4 agent decisions</summary>

### A1. `_process_unprocessed` returns the count of failing emails

- Other option: return the list of failing UIDs, or raise one aggregate exception after the loop.
- Why: `cmd_run` needs only "did any fail"; a count is the smallest return, and the existing callers that ignore the return keep working.
- Command: hotfix

### A2. The error line goes to stderr

- Other option: print it to stdout, beside the dry-run lines.
- Why: every other `error:` in `cli.py` goes to stderr, and stdout keeps only dry-run lines, so GH-2's byte-identical dry-run check still holds.
- Command: hotfix

### A3. Only `ProviderError` is caught per email

- Other option: catch every `Exception` per email.
- Why: the brief names `ProviderError`; a broader catch would hide real bugs, such as a failing action or a state write, behind one stderr line.
- Command: hotfix

### A4. `run` exits 1 for a partial failure, the same code as every other error

- Other option: a distinct exit code, for example 2, for "some emails failed".
- Why: one nonzero code is what a cron wrapper checks, and the error lines already say which emails failed.
- Command: hotfix

</details>

### Review risks

- The adversary's range (`e393a22...HEAD`) also holds the unmerged GH-2 commits, because `origin/HEAD` is `master` and GH-2 is not merged. The review read GH-8's hunks in that larger diff, with 3 of 10 calls used.
- The adversary could not open indexed source (the Gortex hook blocked Grep and it holds no Gortex tools). Its hunch that the error line could leak a secret was triaged by the doer: API keys go only in `Authorization` headers (`jev_mail/providers/openrouter.py:23`, `typesafe_direct.py:24`, `vercel_gateway.py:28`), and an HTTP status error becomes only `<code> <reason>` (`jev_mail/providers/base.py::describe_http_error`). The only other per-email `ProviderError` text is the model's answer, from `extract_probabilities`. The error line can carry that answer text to stderr.
- Hunch, out of scope: `cmd_run` still returns 1 at once on an `OSError` or `imaplib.IMAP4.error` from one account, so later accounts are skipped in that run. This is not changed by GH-8 and no scenario covers it.
- The doer, not the adversary, enumerated the callers of `_process_unprocessed` (hunt 2): `jev_mail/cli.py:110` (`cmd_run`, sums the count), `:133` and `:141` (`cmd_watch`, ignores it). No caller lies outside `cli.py`.

### Not reached by review

- Round 1: calls 3/10; hunts not reached: 1 (there is no merge gate; the layer manifest tools/gauntlet-layers.json was not compared), 2 (callers of _process_unprocessed outside cli.py, and the tui; Grep and Read of indexed source were blocked by the Gortex hook, one Grep attempt, and I hold no Gortex tools), 5 (what ProviderError messages contain, and whether classify can raise a ProviderError subclass or wrap other exceptions), 6, 7, 8 (the GH-8 EVIDENCE.md is not in the diff, so the Orientation block was not checked against its tables), 9, 10; sites not opened: jev_mail/providers/*.py (ProviderError message construction), jev_mail/classify.py (what classify raises), tools/gauntlet-layers.json, spec-evidence/2026-10-26-GH-8/EVIDENCE.md (does not exist at HEAD in the diff), The M1, M5 and M6 diff readings against b29cc70 could not be re-run: the diff is against e393a22 and I hold no shell. They are unproven by me.

## Orientation

- Verdict: PASSED WITH LIMITS
- Delivered: a `ProviderError` on one email is reported and skipped, not fatal, and `run` exits 1 after every account when any email failed.
- Proven: 16/16 scenarios mapped and passing
- Not proven: static types, lint, changed-line coverage and real execution (UNAVAILABLE); mutation testing (SUBSTITUTED by three hand mutants)

- Process: spec-evidence 0.16.2 (gate files: spec-gate.md spec-evidence 0.16.2, story-gate.md none)
- Spec: spec-evidence/2026-10-26-GH-8/SPEC.md (committed)
- Spec approval: obtained from Mike Crowe, commit a95f537 `GH-8: spec approved`
- Intent review: not run, engineering lane
- Source state: commit 571720d3ae97f909f7c0b2e7b87cab13d47d5300 — the commit the final run and the review read. The stamp says `dirty: true`, because the story artifact `baseline-stamp.json` was untracked at the run; no tracked file differed from the commit.
- Baseline: baseline-stamp.json at commit a95f5375c6950114c4fa8809a777f8b8710def26, green

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
    "tests": 11.192,
    "secrets": 0.787
  },
  "layers": {
    "tests": {
      "baseline": "reused",
      "selection": "off"
    },
    "secrets": {
      "baseline": "reused",
      "selection": "off"
    }
  },
  "failed": null,
  "exit_code": 0,
  "commit": "571720d3ae97f909f7c0b2e7b87cab13d47d5300",
  "dirty": true,
  "written": "2026-10-26T10:37:51.351Z"
}
```

</details>

### Spec → Test mapping

Every row is `pass`.

<details>
<summary>16/16 scenarios mapped and passing</summary>

| Scenario | Test | Status |
|---|---|---|
| S1.1 | `tests/test_cli.py::test_failing_email_is_reported_and_the_next_is_processed` | pass |
| S1.2 | `tests/test_cli.py::test_failing_email_gets_no_state_row` | pass |
| S1.3 | `tests/test_cli.py::test_dry_run_reports_failing_email_and_prints_the_others` | pass |
| S1.4 | `tests/test_cli.py::test_no_failure_returns_zero` | pass |
| S2.1 | `tests/test_cli.py::test_run_exits_1_when_an_email_failed` | pass |
| S2.2 | `tests/test_cli.py::test_run_finishes_every_account_before_exiting_1` | pass |
| S2.3 | `tests/test_cli.py::test_run_exits_0_when_nothing_failed` (passed before the fix; break check: mutant `return 1 if failed else 0` -> `return 1` failed it) | pass |
| S3.1 | `tests/test_cli.py::test_watch_keeps_going_after_a_failing_email` | pass |
| S4.1 | `CLAUDE.md:36` (Providers paragraph: "The OpenRouter and TypeSafe-direct adapters are verified against a live key. The Vercel adapter is built from docs only."); `README.md:218` to `:219` ("The OpenRouter and TypeSafe-direct paths are live-verified. The Vercel-gateway adapter is built from its published docs but not yet tested against a live key") | pass |
| M1 | `tests` layer, 107 passed; `git diff b29cc70 -- tests/` holds 0 removed lines | pass |
| M2 | S1.3, and `tests/test_cli.py::test_dry_run_output_is_unchanged` (unchanged, passes) | pass |
| M3 | `tests/test_cli.py::test_startup_provider_error_still_exits_1_before_any_mailbox` (passed before the fix; break check: mutant `except (ConfigError, ProviderError)` -> `except ConfigError` in `cmd_run` failed it) | pass |
| M4 | S1.1 and S1.2 | pass |
| M5 | `git diff --stat b29cc70 -- jev_mail/providers/` prints nothing | pass |
| M6 | `git diff --stat b29cc70 -- pyproject.toml uv.lock` prints nothing | pass |
| M7 | `tests/test_cli.py::test_only_provider_error_is_caught_per_email` (passed before the fix; break check: mutant `except ProviderError` -> `except Exception` failed it) | pass |

</details>

### Gauntlet (final fresh run)

Every layer of the manifest is `PASSED`.

<details>
<summary>2/2 layers PASSED</summary>

| Layer | Command | Status + result | Baseline | Selection | Log |
|---|---|---|---|---|---|
| tests | `mise exec -- uv run pytest -q` | PASSED — 107 passed, 0 failed (baseline completed green) | reused | off | `work/tests.log` |
| secrets | `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` | PASSED — 49 commits scanned, no leaks found | reused | off | `work/secrets.log` |

</details>

### Layers not run as specified

- N-A: none
- UNAVAILABLE: static types — no type checker is configured (for example `mypy`, pinned, would catch a caller that uses the new `int` return as a `None`). Lint and format — no linter is configured. Changed-line coverage — no coverage tool is configured (for example `pytest-cov` with a fail-under on changed lines). Real execution — `./jev-mail run` against a live mailbox and key was not run, because it would classify, tag and bill real mail.
- SUBSTITUTED: mutation testing — three hand mutants on `jev_mail/cli.py` (the `cmd_run` return, the per-email `except`, and the startup `except`), each killed. They cannot detect survivors elsewhere in the changed lines; no mutation tool (for example `mutmut`) is configured.

### Defect classes closed

- Generator: an exception raised for one email inside the per-email loop of `_process_unprocessed` leaves the loop and ends the run.
- Enumerated by: reading the loop body in `jev_mail/cli.py::_process_unprocessed` for each call that can raise.
- Sites: 4 — `classify(...)` (`jev_mail/cli.py:43`) — fixed for `ProviderError`; `matched_categories(...)` — not applicable (pure threshold comparison, raises no `ProviderError`); `run_action(...)` — not applicable, kept fatal by M7 and the Known limits; `mailbox.mark_processed` / `state.record` — not applicable, an IMAP or state error stays fatal so that no email is half-recorded.

### Agent rounds

| Agent | Round | Model | Tokens |
|---|---|---|---|
| context-pack | 1 | claude-sonnet-5-5 | 66330/1096 |
| spec-evidence-intent | — | not run, engineering lane | unrecorded |
| spec-evidence-adversary | 1 | claude-sonnet-5-5 | 218579/2345 |

### Process notes

- RED: the 7 tests for S1.1 to S1.4, S2.1, S2.2 and S3.1 failed before the `cli.py` change (7 failed, 19 passed in `tests/test_cli.py`). GREEN: the full suite passed after it (107 passed).
- The context-pack round for GH-8 reported a Gortex MCP integration failure and emitted no record (`context-pack.md`); the plan was drafted from the doer's own reading.
- Adversary round 2 did not run: round 1 had no confirmed finding, and no fix changed code.
- Each round's model is read from the `model` field of its assistant turns; every assistant turn of the context-pack and adversary transcripts ran on `claude-sonnet-5-5`. A first draft of this table also listed `claude-opus-5-5`, from a non-turn line of the transcript, and was corrected before Gate 2a was recorded.
- `README.md`'s provider note is hard-wrapped; the edit kept its existing wrap style.
