# Decisions — GH-3: Tier 0, decide known senders and obvious bulk mail before Jev

## Setup plan

- Isolation: branch `GH-3-tier0` from `master` at `ba47cef`, in the main checkout. This project uses no worktrees.
- Git: one commit per loop step, files staged by name, never `git add -A` (public repository, CLAUDE.md).
- New dependencies: none. `csv`, `re` and `email.utils` are standard library.
- New files: `jev_mail/tier0.py`, `senders.example.csv`, `tests/test_tier0.py`; `spec-evidence/2026-10-26-GH-3/` holds the story artifacts.
- New local data files: `senders.csv` (read, never written, by the code) and `sender-census.csv` get `.gitignore` entries in the commit that adds `tier0.py`. The review CSV is refused inside the project directory (S4.3), so it needs no entry.
- Tooling audit: `tools/gauntlet-layers.json` declares `tests` (`mise exec -- uv run pytest -q`) and `secrets` (`mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .`); both run. Lint, format, type check, coverage, mutation and randomized order: no tool declared; these stay `UNAVAILABLE`.
- Merge gate: the repository has no `.github/` directory and no `.pre-commit-config.yaml`, as recorded for GH-8; 0 checks transcribed.
- Context pack: `context-pack.md` holds the agent's record verbatim. Its guess that `fetch_unprocessed` may not fetch `List-Unsubscribe` yet is wrong; see fact 2.

## Facts this SPEC rests on

1. `jev_mail/cli.py::_process_unprocessed` at `ba47cef` calls `classify(client, config, mail.state)` for every email, then runs every action of every matched category, then calls `mark_processed`, then `state.record(..., "jev", probabilities, applied)`. Read at `ba47cef`.
2. `Email` (`jev_mail/mailbox/base.py`) already has `sender` and `list_unsubscribe`, and `Mailbox.fetch_unprocessed` (`jev_mail/mailbox/imap.py:71` to `:72`) fills them from the `From` and `List-Unsubscribe` headers. GH-2 built them. So Tier 0 needs no mailbox change.
3. `state.db`'s `processed` table (`jev_mail/state.py`) already has a `source` column, and `cli.py` always writes `"jev"` to it. Step 3 of the brief needs new values only, no schema change.
4. `fetch_unprocessed` searches `UNKEYWORD $JevProcessed` with no `UNSEEN`, so it already takes read and unread mail. The scope line of the third decision comment needs no change.
5. `save_config` (`jev_mail/config.py:170` to `:203`) builds the file from known keys only, so a new `senders_file` key is lost on a TUI save unless `save_config` writes it (S2.7).
6. `run_action` (`jev_mail/actions.py`) takes a `probability` and puts it in the webhook payload, so a Tier 0 hit needs a probability value (A6).
7. GH-2's `tests/test_cli.py::test_dry_run_output_is_unchanged` fixes the exact dry-run text of Jev lines (`[dry-run] 'Invoice #1': Invoice (0.90) -> tag`). It holds one category with a `tag` and a `move`, so the move-order rule does not change it.
8. `config.example.yaml` at `ba47cef` holds the categories `invoice`, `urgent` (with `threshold: 0.7` and a `webhook`) and `spam`. No test reads it (`rg config.example tests/` finds nothing).
9. `.gitignore` holds `state.db` but neither `senders.csv` nor `sender-census.csv`. Read at `ba47cef`.
10. `git config user.name` is `Mike Crowe`.

## Restatements

- The brief's "`decide(email) -> Category | None`" is restated as `decide(mail, senders, config) -> tuple[Category, str] | None` (A1). The table and the config are passed in, so the function reads no file.
- The brief's taxonomy (`BULK`, `BILLING`, `attention`, `transactional`, `newsletter`) is superseded by the taxonomy revision on epic #7 (2026-10-25): `BULK`, `BILLING`, `ACTION`, `PERSONAL`, `MONITOR`. The heuristic outputs follow GH-3's third decision comment: OTP subject and noreply give `MONITOR`, `List-Unsubscribe` gives `BULK`.
- The table mapping follows GH-3's third decision comment: `unsubscribe` gives `BULK`, `auto-archive` gives `MONITOR`, `keep` falls through to Jev. The second comment's "`keep` gives no Tier 0 decision" is read as: rules 2 to 4 are not tried either, because the comment names `keep` as the per-sender fix for a wrong heuristic.
- The storage open question is ruled by GH-3's first decision comment: a git-ignored CSV, its path in config, read with stdlib `csv`, with a committed `senders.example.csv`.
- The brief's "log shows the per-message decision source" is restated as the review CSV's `source` column (S4.1), plus the source on a Tier 0 dry-run line (S3.3).
- The brief's "the Jev call count drops versus Phase 0 on the same sample" is restated as S6.1: Phase 0 sends every email to Jev, so its count on a 200-message sample is 200, and the GH-3 count is the number of `jev` rows.
- "Record both numbers here" is a GitHub comment, so it waits for the engineer's yes (S6.1).
- The third comment's "Move priority" and "Review CSV" items land in this issue, as that comment says.

## Decide calls

### Decide 1. What does the dry-run line for a Tier 0 hit print?

Evidence: fact 7; `jev_mail/cli.py::_process_unprocessed`, the line `[dry-run] {subject!r}: {name} ({probability:.2f}) -> {action}`.

- A. Print the source in place of the probability on a Tier 0 line, `[dry-run] 'Weekly deals': BULK (census) -> move`. Jev lines stay as they are. Cost: a Jev line shows its source only by having a number in the brackets.
- B. Add the source to every dry-run line, for example `[dry-run] [jev] 'Invoice #1': Invoice (0.90) -> tag`. Cost: GH-2's `test_dry_run_output_is_unchanged` must change, against M1.

Default: A. Ruling: A (Mike Crowe, 2026-10-26).
Changes: S3.3 cites Decide 1's ruling; the Orientation's Decided line names it. M1 is unchanged.

### Decide 2. Do the five categories replace the example categories, or join them?

Evidence: fact 8; brief step 4 says "Add categories"; epic #7 calls the five "the final category set".

- A. Replace `invoice`, `urgent` and `spam` with the five. `ACTION` keeps `threshold: 0.7` and the `webhook` line, so the example still shows both features. Cost: the old example names are gone for a new user who reads the file.
- B. Keep the three and add the five. Cost: `invoice` overlaps `BILLING` and `urgent` overlaps `ACTION`, so a user who copies the file gets two questions for one meaning and pays for both.

Default: A. Ruling: A (Mike Crowe, 2026-10-26).
Changes: S5.1 and the `config.example.yaml` Touches entry cite Decide 2's ruling; the Orientation's Decided line names it.

## Revisions

### Revision 1. Decide 1 and 2 ruled
The engineer ruled A and A in the Decide round; SPEC.md was updated with those rulings.
