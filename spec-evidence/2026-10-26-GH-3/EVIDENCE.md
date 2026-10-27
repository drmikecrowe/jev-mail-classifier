## Evidence Report — GH-3: Tier 0, decide known senders and obvious bulk mail before Jev (Tier 2)

## Summary

Delivered: a local Tier 0 step, `jev_mail/tier0.py`, that decides an email before the paid Jev call. It uses the sender table (`senders_file`), then a one-time-code subject, then `List-Unsubscribe`, then a noreply sender. A hit gives one category and skips Jev. The state row records the source. Only the first matched `move` in config order runs. `run --dry-run --review <path>` writes a CSV. The example config ships the five-category taxonomy. Why: every email cost one Jev call, even when a hand-made table or an obvious header already gave the answer.

How each criterion was proven:

- Table verdicts (`unsubscribe` gives BULK, `auto-archive` gives MONITOR, `keep` goes to Jev even when a header rule fires): unit tests S1.1 to S1.3, S1.9.
- Header rules in order (OTP subject, then `List-Unsubscribe`, then noreply), and the near misses: S1.4 to S1.7, S1.10.
- A rule for a category that is not configured does not fire: S1.8.
- A bad table stops the run before any mailbox connects: S2.2 to S2.4 and S2.6. A row that is no email address also stops it (A14, from adversary round 1).
- The state row source and probability 1.0: S3.1, S3.2, S3.4.
- Dry-run lines: S3.3, S3.6.
- Move order: S3.5, S3.6, S3.9.
- `--review`: S4.1 to S4.5.
- Ignore rules and the example table: S5.2, S5.3.
- Live sample: S6.1. The review CSV has 200 rows: `heuristic` 102, `census` 14, `jev` 84. So Jev ran 84 times, not 200.
- What must not change: M1 to M8, by the `tests` and `secrets` layers and the diff readings.

Not proven: static types, lint, changed-line coverage and suite health have no tool in this project. Mutation testing ran only as hand mutants. The last commit, `9ccdad7`, changes docs only, and no adversary round read it.

## Agent decisions

<details><summary>14 agent decisions</summary>

### A1. `tier0.decide` returns the category and the decision source together
- Other option: return only a `Category`, as the brief's `decide(email) -> Category | None` says, and work out the source in `cli.py`.
- Why: the state row and the review CSV need the source, and only `decide` knows which rule fired.
- Command: hotfix

### A2. A sender matches the table by its bare address, lowercased
- Other option: match the whole `From` header text, display name included.
- Why: the display name changes between emails from one sender, and a folded `From` header keeps its `\r\n ` (GH-2 EVIDENCE), so only the parsed address is stable.
- Command: hotfix

### A3. A rule whose category is not configured does not fire, and the next rule is tried
- Other option: skip Jev and mark the email processed with no action when Tier 0 names a category the config lacks.
- Why: a config without the new categories then behaves exactly as today, and no email is marked without any decision.
- Command: hotfix

### A4. The table path is a top-level `senders_file` key, relative to the config directory
- Other option: a `tier0:` block holding `senders_file`, or a fixed file name with no key.
- Why: one key is the smallest change that the issue's "its path set in config" asks for, and the relative path matches where `state.db` and `.env` live.
- Command: hotfix

### A5. A missing table file, an unknown verdict or a sender listed twice stops the run with a config error
- Other option: skip the bad row, or let the last row for a sender win.
- Why: the table is hand-edited, and a silent skip would send a sender's mail to the wrong place with no sign of the typo.
- Command: hotfix

### A6. A Tier 0 hit records probability 1.0 for its one category
- Other option: record an empty probability map, or a sentinel such as -1.
- Why: `run_action`'s webhook payload and `state.record` both take a probability, and 1.0 states a certain decision in the same shape as a Jev answer.
- Command: hotfix

### A7. `--review` is refused without `--dry-run`, and refused for a path inside `--dir`
- Other option: allow `--review` on a real run, or only warn about a path inside the repository.
- Why: the issue names `run --dry-run --review`, and its rows hold real subjects, so a file inside the public repository must not be possible.
- Command: hotfix

### A8. The review CSV has one column per configured category, in config order, after `account,uid,subject,source`
- Other option: one JSON column holding the probability map.
- Why: one column per category opens directly in a spreadsheet for threshold tuning, which is what the issue says the file is for.
- Command: hotfix

### A9. The example categories run in the order BILLING, ACTION, PERSONAL, MONITOR, BULK
- Other option: the taxonomy's own order, BULK first.
- Why: the first match owns the `move`, so a bill that Jev also calls bulk goes to BILLING, not BULK.
- Command: hotfix

### A10. A noreply sender is one whose local part is exactly `noreply`, `no-reply` or `donotreply`
- Other option: any local part that starts with or holds `noreply`.
- Why: the brief names those three literals, and a looser match sends more human-adjacent mail, such as `noreply-support@`, around Jev.
- Command: hotfix

### A11. The OTP subject rule uses a fixed list of English phrases
- Other option: a regex for any 4 to 8 digit number in the subject.
- Why: a bare number also matches order numbers and invoice numbers, which must reach Jev for `BILLING`.
- Command: hotfix

### A12. The `move` that runs belongs to the first matched category with a `move`, taken in `config.categories` order, while every other action keeps the order it runs in today
- Other option: sort the matched categories into config order and run every action in that order.
- Why: `matched_categories` returns Jev's answer order, so sorting would reorder today's actions and dry-run lines for emails with no Tier 0 hit (M2), while picking only the move owner by config order changes nothing else.
- Command: build

### A13. The example categories take their descriptions from the epic #7 taxonomy revision, and only BILLING, MONITOR and BULK move
- Other option: give every one of the five a `move` to its own folder, as the SPEC's test configs do.
- Why: the revision says ACTION needs a reply or task and PERSONAL is a human with no action, so both stay in the inbox (ACTION keeps its flag and webhook, PERSONAL gets a tag), while bills, receipts and mass mail leave it.
- Command: build

### A14. A table row whose sender parses to no address stops the run, and an email whose sender parses to no address never matches the table
- Other option: skip such a row silently, as a row with an empty sender is skipped.
- Why: adversary round 1 showed a row such as `deals@` is stored under the key `''`, which every email with an empty or malformed `From` then matches; a hand-edited typo must stop the run (A5), and the lookup guard keeps a From-less email out of the table whatever the file holds.
- Command: build

</details>

### Review risks

- Adversary round 2 read `b90fe14`. The later commit `9ccdad7` changes two doc lines only (`README.md`, `CLAUDE.md`), and no review read it, so the adversary layer is not-run for that commit.
- Both adversary rounds had low coverage: a Gortex hook blocked some of their reads (see "Not reached by review"). I checked the sites they could not open myself: `Email.sender` and `Email.list_unsubscribe` default to `""`, and `imap.py:71-72` fills them from `_decode_header`, which always returns `str`. No reviewer confirmed that.
- Open hunch, not fixed: the review CSV writes subjects raw. A subject that starts with `=`, `+`, `-` or `@` becomes a formula when the file is opened in a spreadsheet. The file is the engineer's own, and no scenario covers it.
- Open hunch, not fixed: `cmd_run` opens the review file before any mailbox connects. A later IMAP error leaves a file with only the header row, and it overwrites an earlier file at that path.
- Open hunch, already a SPEC Known limit: the `--review` guard checks paths inside `--dir` only.
- S6.1 compares the 84 Jev calls against the SPEC's Phase 0 count of 200, one call per email by design. No Phase 0 run on the same 200 emails was measured.

### Not reached by review

- Round 1: calls 3/10; hunts not reached: 2 (callers of changed functions: only the diff was read, and the two Grep calls on jev_mail/mailbox were blocked by the Gortex hook, so Email.sender and Email.list_unsubscribe defaults, None versus empty string, were not verified), 5 (error paths: whether a None mail.sender or None mail.list_unsubscribe would raise in tier0.decide), 8 (no EVIDENCE.md in the diff), 9; sites not opened: jev_mail/mailbox/base.py (Email dataclass defaults), jev_mail/mailbox/imap.py:71 (the line that fills sender and list_unsubscribe), jev_mail/state.py (record signature and the source column), jev_mail/classify.py (matched_categories), jev_mail/actions.py (run_action)
- Round 2: calls 3/10; hunts not reached: 1 (there is no merge gate, so nothing to compare), 2 (caller hunt: all changed-function call sites were not opened), 3 (generator hunt), 4, 5, 6, 7, 8, 9 (not verified: Email.sender and Email.list_unsubscribe exist and are populated by imap.py; State.record accepts the new sources census and heuristic), 10; sites not opened: /home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/imap.py (blocked by Gortex hook, and Gortex was unavailable here), /home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/state.py:32 (blocked), /home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/base.py, /home/mcrowe/Programming/AI/jev-mail-classifier/spec-evidence/2026-10-26-GH-3/work/diff.txt lines 553-1411 (tests, EVIDENCE, remainder of SPEC)

## Orientation

- Verdict: PASSED WITH LIMITS
- Delivered: a Tier 0 step that decides known senders and obvious bulk or automated mail before Jev, with its source recorded, first-move-only ordering, a review CSV, and the five-category example config.
- Proven: 36/36 scenarios mapped and passing; M1 to M8 passing
- Not proven: static types, lint, changed-line coverage and suite health (UNAVAILABLE); mutation testing (SUBSTITUTED by hand mutants); adversarial review of `9ccdad7`, a docs-only commit (not run)

- Process: spec-evidence 0.16.2 (gate files: story-gate.md none, spec-gate.md spec-evidence 0.16.2)
- Spec: spec-evidence/2026-10-26-GH-3/SPEC.md (committed)
- Spec approval: obtained from Mike Crowe, commit `bea20f3` (`GH-3: spec approved`)
- Intent review: not run, engineering lane
- Source state: commit 9ccdad7d6b355a1aa185e071d95424c4396eb530, the commit of the final run. Adversary round 2 read `b90fe14`, the last code commit. The tree was dirty: an uncommitted `.atlas/` line in `.gitignore` that predates this story, and the untracked story files that the `built` commit adds.
- Baseline: baseline-stamp.json at commit bea20f30de13583f2b9cb915bd02b449006577b4, green

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
    "tests": 11.226,
    "secrets": 0.751
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
  "commit": "9ccdad7d6b355a1aa185e071d95424c4396eb530",
  "dirty": true,
  "written": "2026-10-27T12:55:02.928Z"
}
```

</details>

### Spec → Test mapping

Every row passes.

<details>
<summary>36/36 scenarios mapped and passing</summary>

| Scenario | Test | Status |
|---|---|---|
| S1.1 | tests/test_tier0.py::test_unsubscribe_sender_goes_to_bulk | pass |
| S1.2 | tests/test_tier0.py::test_auto_archive_sender_goes_to_monitor | pass |
| S1.3 | tests/test_tier0.py::test_keep_sender_goes_to_jev_even_when_a_header_rule_fires | pass |
| S1.4 | tests/test_tier0.py::test_otp_subject_comes_before_list_unsubscribe | pass |
| S1.5 | tests/test_tier0.py::test_list_unsubscribe_comes_before_noreply | pass |
| S1.6 | tests/test_tier0.py::test_noreply_sender_goes_to_monitor (3 parameters) | pass |
| S1.7 | tests/test_tier0.py::test_near_misses_go_to_jev | pass |
| S1.8 | tests/test_tier0.py::test_rule_for_an_unconfigured_category_does_not_fire | pass |
| S1.9 | tests/test_tier0.py::test_folded_from_header_still_matches_the_table | pass |
| S1.10 | tests/test_tier0.py::test_blank_list_unsubscribe_does_not_fire | pass |
| S2.1 | tests/test_tier0.py::test_load_senders_normalizes_and_skips_blank_senders | pass |
| S2.2 | tests/test_tier0.py::test_load_senders_refuses_an_unknown_verdict | pass |
| S2.3 | tests/test_tier0.py::test_load_senders_refuses_a_sender_listed_twice | pass |
| S2.4 | tests/test_tier0.py::test_load_senders_refuses_a_header_without_sender | pass |
| S2.5 | tests/test_config.py::test_senders_file_key_loads_and_defaults_to_empty | pass |
| S2.6 | tests/test_cli.py::test_missing_senders_file_stops_the_run_before_any_mailbox | pass |
| S2.7 | tests/test_config.py::test_senders_file_round_trips_and_is_omitted_when_empty | pass |
| S3.1 | tests/test_cli.py::test_census_hit_skips_jev_and_the_state_row_records_its_source | pass |
| S3.2 | tests/test_cli.py::test_heuristic_hit_skips_jev_and_records_heuristic | pass |
| S3.3 | tests/test_cli.py::test_dry_run_line_shows_the_tier0_source | pass |
| S3.4 | tests/test_cli.py::test_tier0_webhook_carries_probability_one | pass |
| S3.5 | tests/test_cli.py::test_only_the_first_matched_move_runs | pass |
| S3.6 | tests/test_cli.py::test_dry_run_prints_no_line_for_a_skipped_move | pass |
| S3.7 | tests/test_cli.py::test_tier0_hit_is_marked_when_jev_fails_for_the_others | pass |
| S3.8 | tests/test_cli.py::test_watch_uses_the_sender_table_and_has_no_review_option | pass |
| S3.9 | tests/test_cli.py::test_a_matched_category_without_move_lets_a_later_move_run | pass |
| S4.1 | tests/test_cli.py::test_review_csv_has_one_row_per_email_with_source_and_probabilities | pass |
| S4.2 | tests/test_cli.py::test_review_is_refused_without_dry_run | pass |
| S4.3 | tests/test_cli.py::test_review_is_refused_inside_the_project_directory | pass |
| S4.4 | tests/test_cli.py::test_review_csv_has_no_row_for_a_failed_email | pass |
| S4.5 | tests/test_cli.py::test_review_defaults_to_none | pass |
| S5.1 | tests/test_config.py::test_example_config_ships_the_five_categories | pass |
| S5.2 | tests/test_tier0.py::test_example_senders_file_holds_only_fake_addresses | pass |
| S5.3 | `git check-ignore senders.csv sender-census.csv` printed both names and exited 0; `git check-ignore senders.example.csv` printed nothing and exited 1 | pass |
| S5.4 | README.md:166 (the four Tier 0 rules in order, a hit skips Jev), README.md:208 (`senders_file`), README.md:214 (the move order), README.md:218 (`run --dry-run --review <path>`), CLAUDE.md:31 (Tier 0 step 2, before the `classify` step 3) | pass |
| S6.1 | `varlock run -- ./jev-mail run --dry-run --review /tmp/gh3-review.csv` against the engineer's mailbox with `max_emails_per_run: 200`, the five categories and the engineer's `senders.csv` (152 senders): exit 0, 200 rows after the header, `heuristic` 102, `census` 14, `jev` 84; 84 is below 200. Counts only. Posting them on GH-3 waits for the engineer's yes | pass |

| Must NOT | Proof | Status |
|---|---|---|
| M1 | `tests` layer, 147 passed; `git diff ba47cef -- tests/` holds 551 added lines and 0 removed lines | pass |
| M2 | M1 and S3.1; A12 keeps every non-move action in today's order | pass |
| M3 | tests/test_cli.py::test_dry_run_marks_nothing_and_creates_no_state_db (M1), S4.1 to S4.3; the S6.1 dry run left no `state.db` | pass |
| M4 | S1.8, S2.5, M1 | pass |
| M5 | `git diff --stat ba47cef -- pyproject.toml uv.lock` printed nothing | pass |
| M6 | `git diff --stat ba47cef -- jev_mail/providers/ jev_mail/mailbox/` printed nothing | pass |
| M7 | S5.2; `secrets` layer, no leaks found; every address on an added line of the code commit is at `example.com` | pass |
| M8 | tests/test_cli.py::test_real_run_marks_processed_then_writes_one_state_row (M1) | pass |

</details>

Break checks, each a one-off mutant reverted after the run. Each made its test fail:

- S1.3: `keep` short-circuit removed. S1.7: the noreply rule widened to `startswith("noreply")`. S1.10: `.strip()` removed from the `List-Unsubscribe` check. These three tests passed against the empty stub, so the mutants prove they can fail.
- S3.9: Decide 3's rejected option A, where the first matched category owns the move even with no `move` action. S3.5 and S3.6: the move skip removed. S3.1, S3.2 and S3.4: Tier 0 not called.

### Gauntlet (final fresh run)

Both layers PASSED.

<details>
<summary>2/2 layers PASSED</summary>

| Layer | Command | Status + result | Baseline | Selection | Log |
|---|---|---|---|---|---|
| tests | `mise exec -- uv run pytest -q` | PASSED — 147 passed in 10.04s, exit 0 (baseline: green at `bea20f3`) | none | off | work/tests.log |
| secrets | `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` | PASSED — 61 commits scanned, no leaks found | none | off | work/secrets.log |

</details>

Other layers of the loop:

| Layer | Status |
|---|---|
| Merge gate parity | N-A: the repository has no `.github/` and no CI configuration |
| Egress: new data paths | PASSED by reading: the review CSV holds account, uid, subject, source and probabilities, and is written only to a path outside `--dir` (S4.3); the state row source is one of three literals; nothing new is logged |
| Real execution | PASSED: S6.1 ran through `./jev-mail` against the live mailbox |
| Supply chain & secrets | PASSED: no new dependency (M5); `secrets` layer above |
| Adversarial review | PASSED for `b90fe14`: round 1 had 1 blocking finding, fixed in `b90fe14`; round 2 had no findings. Not run for `9ccdad7` (docs only) |

### Layers not run as specified

- N-A: Merge gate parity — no merge gate exists. Property-based tests — the change adds no round-trip, math or serialization invariant beyond the config round trip, which S2.7 covers by example.
- UNAVAILABLE: static types — no type checker is configured; pyright, pinned, would catch wrong `Optional` use. Lint + format — none configured; ruff, pinned, would catch unused imports. Changed-line coverage — none configured; pytest-cov with `--cov-fail-under` on the diff would catch unexecuted lines. Suite health — no random-order plugin; pytest-randomly would catch order dependence.
- SUBSTITUTED: Mutation testing — hand mutants on `tier0.py` and `cli.py` (listed under the mapping) ran in place of a tool. They cannot find a surviving mutant that nobody wrote; mutmut, pinned, run on `git diff --name-only bea20f3...HEAD`, would.

### Defect classes closed

- Generator: a parsed sender address that can be empty is used as a sender-table key or a lookup key.
- Enumerated by: `rg -n '\bsender_address\(' jev_mail/`
- Sites: 2 — jev_mail/tier0.py:46 (`load_senders`, the stored key) — fixed, a row that parses to no address now stops the run; jev_mail/tier0.py:57 (`decide`, the table lookup) — fixed, an empty address never matches; the noreply rule at the same site was already correct, because it needs an `@`.

### Agent rounds

| Agent | Round | Model | Tokens |
|---|---|---|---|
| context-pack | 1 | claude-sonnet-5-5 | 97892/1941 |
| spec-evidence-adversary | 1 | claude-sonnet-5-5 | 254324/2818 |
| spec-evidence-adversary | 2 | claude-sonnet-5-5 | 145326/1989 |

### Process notes

- The Gortex daemon went down and restarted several times during the build. Some edits used native tools, and two Gortex edits timed out, but `git diff` showed that both had landed. The code is not affected.
- The engineer's `senders.csv` was not in `email-triage`, the repository first named. The engineer then put it at the project root. It loads as 152 senders and is git-ignored (S5.3).
- For S6.1, at the engineer's request, `config.yaml` (git-ignored) was changed: `max_emails_per_run` 5 to 200, `senders_file: senders.csv` added, and the categories replaced by the five from `config.example.yaml`. The earlier file is at `/tmp/config.yaml.before-gh3`. Its `ACTION` webhook URL is the literal `${SLACK_WEBHOOK_URL}`, because action fields are not interpolated. A dry run sends no webhook. A real run would pass that literal string to `httpx.post` for every ACTION match. What it does then was not tested. Set a real URL or remove the action before a real run.
- Secrets for the live run came from 1Password through `varlock run`. There is no `.env` file.
- The gauntlet stamps of the final run say `dirty: true`; see Source state.
