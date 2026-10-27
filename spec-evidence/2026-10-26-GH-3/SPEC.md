# GH-3: Tier 0, decide known senders and obvious bulk mail before Jev

## Summary

This change stops sending every email to Jev. Today `_process_unprocessed` calls `classify`, one paid Jev call, for every unprocessed email, even for mail whose answer is already known: senders the engineer has hand-classified, and bulk or automated mail that a header or the subject gives away.

What changes: a new module, `jev_mail/tier0.py`, decides an email locally before Jev. It checks four rules in order: the sender table (`senders.csv`, git-ignored, its path set by a new `senders_file` key in `config.yaml`), then a one-time-code subject, then a `List-Unsubscribe` header, then a noreply sender. A hit gives the email exactly one category and skips Jev. A miss, or a sender marked `keep` in the table, goes to Jev as today. The state row records which path decided (`census`, `heuristic` or `jev`). When several matched categories have a `move` action, only the first in config order moves the email. `run --dry-run --review <path>` writes one CSV row per email with its decision source and every probability, for the 200-message sample and for threshold tuning. `config.example.yaml` gets the shared taxonomy from epic #7: `BULK`, `BILLING`, `ACTION`, `PERSONAL`, `MONITOR`.

The acceptance criteria, in plain words:

- A sender marked `unsubscribe` in the table goes to `BULK`, and one marked `auto-archive` goes to `MONITOR`, with no Jev call. A sender marked `keep` always goes to Jev, even when a header rule would have matched.
- An email with a one-time-code subject goes to `MONITOR`; else one with a `List-Unsubscribe` header goes to `BULK`; else one from a `noreply@`, `no-reply@` or `donotreply@` address goes to `MONITOR`. None of these call Jev.
- A rule whose category is not in the config does not fire, so a config without the new categories works exactly as today.
- A bad table (missing file, unknown verdict, a sender listed twice) stops the run with one `error:` line before any mailbox connects.
- The state row says `census`, `heuristic` or `jev`. A Tier 0 hit records probability 1.0 for its category.
- A dry run shows the source on a Tier 0 line in place of the probability. Jev lines print as they do today.
- Only the first `move` among the matched categories, in config order, runs. A matched category with no `move` does not stop a later one from moving the email. Tags, flags and mark actions still run for every match.
- `--review <path>` writes the CSV. It is refused without `--dry-run`, and refused for a path inside the project directory, because its rows hold real subjects.
- `senders.csv` and `sender-census.csv` are git-ignored, and a `senders.example.csv` with fake rows is committed.
- On a 200-message live sample, the review CSV gives the count for each source. The Jev count is lower than Phase 0's 200 calls on the same sample.

What must not change: every existing test passes with no existing test function changed; an email with no Tier 0 hit gets the same Jev call and the same actions as today; a dry run still touches no mailbox and writes no `state.db`; no new dependency; no provider code changes; no real sender data is committed.

How each criterion is proven: unit tests in a new `tests/test_tier0.py` for the rules and the table, pipeline and `cmd_run` tests in `tests/test_cli.py`, config tests in `tests/test_config.py`, `git check-ignore` for the ignore rules, a diff reading for the docs, and one live dry run on the engineer's mailbox that reports counts only.

Open decisions: none. Decide 1 ruled that only a Tier 0 dry-run line shows its source; Decide 2 ruled that the five categories replace the example categories.

## Orientation

- Lane: engineering, because this is Phase 2 of the engineer-owned epic #7, specified by the engineer in the issue and its decision comments; there is no product author.
- Change: add a local Tier 0 decision before the Jev call, record its source, give the first matched `move` priority, add `--review`, and ship the shared taxonomy in the example config.
- Why: every email costs one Jev call today, even when a hand-made table or an obvious header already answers it.
- Touches: `jev_mail/tier0.py` (new), `jev_mail/cli.py`, `jev_mail/config.py`, `config.example.yaml`, `senders.example.csv` (new), `.gitignore`, `README.md`, `CLAUDE.md`, and tests.
- Decide: Decide 1, the dry-run line for a Tier 0 hit; Decide 2, the example categories; Decide 3, whether a later matched category may move the email.
- Decided: Decide 1 ruled that a Tier 0 dry-run line prints its source in place of the probability and Jev lines stay as they are; it governs S3.3 (Mike Crowe, 2026-10-26). Decide 2 ruled that the five categories replace `invoice`, `urgent` and `spam` in `config.example.yaml`, with `ACTION` keeping `threshold: 0.7` and the `webhook`; it governs S5.1 and the `config.example.yaml` Touches entry (Mike Crowe, 2026-10-26). Decide 3 ruled that a matched category with no `move` lets the next matched category's `move` run; it governs the Move order definition and S3.9 (Mike Crowe, 2026-10-27).
- Brief: issue GH-3, its three decision comments of 2026-10-25, and the taxonomy revision comment on epic #7 of 2026-10-25. Where a later comment supersedes an earlier one, the later one is the spec.
- Tier: 2
- Issue: GH-3
- Isolation: branch `GH-3-tier0` from `master` at `ba47cef`, in the main checkout, because this project uses no worktrees.

## Definitions

- **Sender address**: `email.utils.parseaddr(mail.sender)[1].lower()`.
- **Senders file**: a CSV file whose header row holds at least the columns `sender` and `verdict`. Other columns are ignored. Each `verdict` is `unsubscribe`, `auto-archive` or `keep`. A row whose `sender` is empty after stripping is skipped. Each `sender` is stored as `email.utils.parseaddr(value)[1].lower()`.
- **Sender table**: the `dict[str, str]` from sender address to verdict that `tier0.load_senders(path)` returns. With no `senders_file` key, the table is empty.
- **OTP subject**: a subject that matches, case-insensitively, `\b(verification code|security code|confirmation code|login code|sign[- ]in code|one[- ]time (password|passcode|code)|passcode|otp|2fa|two[- ]factor)\b`.
- **Noreply sender**: a sender address whose part before `@` is exactly `noreply`, `no-reply` or `donotreply`.
- **Tier 0 rules**, tried in this order; the first rule that fires decides:
  1. The sender address is in the sender table. `unsubscribe` gives `BULK`, `auto-archive` gives `MONITOR`, source `census`. `keep` gives no decision and stops: rules 2 to 4 are not tried, and the email goes to Jev.
  2. OTP subject: `MONITOR`, source `heuristic`.
  3. `mail.list_unsubscribe.strip()` is not empty: `BULK`, source `heuristic`.
  4. Noreply sender: `MONITOR`, source `heuristic`.
  A rule whose category name is not one of `config.categories` does not fire, and the next rule is tried. When no rule fires, there is no decision.
- **Tier 0 hit**: `tier0.decide(mail, senders, config)` returns `(category, source)`, with `category` the configured `Category` of that name. No decision returns `None`.
- **Move order**: for one email, the first `move` action found among the matched categories, taken in `config.categories` order, runs, even when an earlier matched category has no `move` (Decide 3). Every later `move` is skipped: it does not run, a dry run prints no line for it, and it is not in the state row's actions. Every other action type runs for every matched category.
- **Account key**: `f"{account.host}/{account.username}"`, as `state.record` already uses.

## Scenarios

The configs below name categories by their exact names. "All five" means `BILLING`, `ACTION`, `PERSONAL`, `MONITOR`, `BULK`, in that order, each with one `move` action to a folder of the same name.

### S1. The Tier 0 rules

- S1.1 Given a config with all five categories, the sender table `{"news@example.com": "unsubscribe"}` and `Email(uid=1, subject="Hi", body="b", sender="News <News@Example.com>")`, when `tier0.decide` runs, then it returns the `BULK` category and `"census"`.
- S1.2 Given the S1.1 config, the table `{"news@example.com": "auto-archive"}` and the S1.1 email, when `tier0.decide` runs, then it returns the `MONITOR` category and `"census"`.
- S1.3 (negative) Given the S1.1 config, the table `{"news@example.com": "keep"}` and `Email(uid=1, subject="Your verification code", body="b", sender="news@example.com", list_unsubscribe="<mailto:u@example.com>")`, when `tier0.decide` runs, then it returns `None`.
- S1.4 Given the S1.1 config, an empty table and `Email(uid=1, subject="Your verification code is 123456", body="b", sender="alerts@example.com", list_unsubscribe="<mailto:u@example.com>")`, when `tier0.decide` runs, then it returns the `MONITOR` category and `"heuristic"`.
- S1.5 Given the S1.1 config, an empty table and `Email(uid=1, subject="Receipt", body="b", sender="noreply@example.com", list_unsubscribe="<mailto:u@example.com>")`, when `tier0.decide` runs, then it returns the `BULK` category and `"heuristic"`.
- S1.6 Given the S1.1 config and an empty table, when `tier0.decide` runs on `Email(uid=1, subject="Receipt", body="b")` with each of the senders `"No Reply <no-reply@example.com>"`, `"NoReply@example.com"` and `"donotreply@example.com"`, then each returns the `MONITOR` category and `"heuristic"`.
- S1.7 (negative) Given the S1.1 config and an empty table, when `tier0.decide` runs on `Email(uid=1, subject="Code review notes", body="b", sender="noreply-billing@example.com")` and on `Email(uid=2, subject="Lunch?", body="b", sender="Ann Lee <ann@example.com>")`, then each returns `None`.
- S1.8 (boundary) Given a config whose only category is `BULK` and an empty table, when `tier0.decide` runs on `Email(uid=1, subject="Receipt", body="b", sender="noreply@example.com")`, then it returns `None`; and on `Email(uid=2, subject="Your verification code", body="b", sender="a@example.com", list_unsubscribe="<mailto:u@example.com>")`, then it returns the `BULK` category and `"heuristic"`.
- S1.9 (boundary) Given the S1.1 config, the table `{"ann@example.com": "unsubscribe"}` and `Email(uid=1, subject="Hi", body="b", sender="Ann Lee\r\n <ann@example.com>")`, when `tier0.decide` runs, then it returns the `BULK` category and `"census"`.
- S1.10 (boundary) Given the S1.1 config, an empty table and `Email(uid=1, subject="Hi", body="b", sender="ann@example.com", list_unsubscribe="   ")`, when `tier0.decide` runs, then it returns `None`.

### S2. The sender table and its config key

- S2.1 Given a file `senders.csv` with the lines `sender,verdict,count`, `News@Example.com,unsubscribe,12`, `,keep,1` and `Ann <ann@example.com>,keep,3`, when `tier0.load_senders` runs on it, then it returns `{"news@example.com": "unsubscribe", "ann@example.com": "keep"}`.
- S2.2 (negative) Given a `senders.csv` with the lines `sender,verdict`, `a@example.com,keep` and `b@example.com,archive`, when `tier0.load_senders` runs, then it raises `ConfigError` with the message `senders.csv line 3: unknown verdict 'archive' (use unsubscribe, auto-archive or keep)`.
- S2.3 (negative) Given a `senders.csv` with the lines `sender,verdict`, `a@example.com,keep`, `b@example.com,keep` and `A@example.com,unsubscribe`, when `tier0.load_senders` runs, then it raises `ConfigError` with the message `senders.csv line 4: a@example.com is listed twice`.
- S2.4 (negative) Given a `senders.csv` whose header row is `address,verdict`, when `tier0.load_senders` runs, then it raises `ConfigError` with the message `senders.csv: the header row needs the columns sender and verdict`.
- S2.5 Given a one-account `config.yaml` that holds `senders_file: senders.csv`, when `load_config` runs, then `config.senders_file` is `"senders.csv"`; and given a `config.yaml` with no `senders_file` key, then it is `""`.
- S2.6 (negative) Given a directory whose `config.yaml` holds `senders_file: senders.csv`, no `senders.csv` beside it, and `jev_mail.cli.Mailbox` replaced with a fake that records each build, when `cmd_run` runs, then it returns `1`, stderr is exactly `error: senders file not found: <dir>/senders.csv` and a newline, with `<dir>` the directory, and the fake is never built.
- S2.7 Given a config loaded with `senders_file: senders.csv`, when `save_config` writes it and `load_config` reads it back, then `senders_file` is `"senders.csv"`; and a config with `senders_file == ""` is written with no `senders_file` key.

### S3. The pipeline

- S3.1 Given a config with categories `BILLING` (one `move` to `BILLING`) and `BULK` (one `move` to `BULK`), the sender table `{"deals@example.com": "unsubscribe"}`, a fake backend that returns `Email(uid=3, subject="Weekly deals", body="b", message_id="<d@example.com>", sender="Deals <deals@example.com>")` then `Email(uid=2, subject="Invoice #1", body="b", message_id="<i@example.com>", sender="ann@example.com")`, a client that records each `decide` call and returns `{"BILLING": 0.9, "BULK": 0.1}`, and a `State` on `tmp_path / "state.db"`, when `_process_unprocessed` runs with `dry_run=False`, then `decide` is called once, with the state of uid 2; `move` is called with `(3, "BULK")` and `(2, "BILLING")`; `mark_processed` is called with `3` and `2`; and `state.db` holds two rows: `<d@example.com>` with source `census` and probabilities `{"BULK": 1.0}`, and `<i@example.com>` with source `jev` and probabilities `{"BILLING": 0.9, "BULK": 0.1}`.
- S3.2 Given the S3.1 config, an empty table, and one email `Email(uid=4, subject="Sale", body="b", message_id="<s@example.com>", sender="shop@example.com", list_unsubscribe="<mailto:u@example.com>")`, when `_process_unprocessed` runs with `dry_run=False` and a `State`, then `decide` is never called and the one state row has source `heuristic`.
- S3.3 Given the S3.1 inputs, when `_process_unprocessed` runs with `dry_run=True`, then stdout is exactly `[dry-run] 'Weekly deals': BULK (census) -> move` and a newline, then `[dry-run] 'Invoice #1': BILLING (0.90) -> move` and a newline (Decide 1, ruled A by Mike Crowe, 2026-10-26).
- S3.4 Given a config with one category `BULK` whose one action is a `webhook` to `https://hooks.example.com/x`, an empty table, one email with `list_unsubscribe="<mailto:u@example.com>"` and subject `Sale`, and `httpx.post` in `jev_mail.actions` replaced with a recorder, when `_process_unprocessed` runs with `dry_run=False`, then the recorder gets one call with the JSON `{"category": "BULK", "probability": 1.0, "subject": "Sale"}`.
- S3.5 Given a config with `BILLING` (actions: `tag` value `Billing`, then `move` to `BILLING`) and `BULK` (action: `move` to `BULK`), an empty table, one email `Email(uid=2, subject="Invoice #1", body="b", message_id="<i@example.com>", sender="ann@example.com")`, which has no Tier 0 hit, and a client that returns `{"BILLING": 0.9, "BULK": 0.9}`, when `_process_unprocessed` runs with `dry_run=False` and a `State`, then `add_tag` is called once with `Billing`, `move` is called once, with `BILLING`, and the state row's actions are `[{"category": "BILLING", "type": "tag", "value": "Billing"}, {"category": "BILLING", "type": "move", "folder": "BILLING"}]`.
- S3.6 (boundary) Given the S3.5 inputs, when `_process_unprocessed` runs with `dry_run=True`, then stdout is exactly `[dry-run] 'Invoice #1': BILLING (0.90) -> tag`, `[dry-run] 'Invoice #1': BILLING (0.90) -> move`, each with a newline, and nothing for `BULK`.
- S3.7 (boundary) Given the S3.1 inputs and a client whose `decide` always raises `ProviderError("boom")`, when `_process_unprocessed` runs with `dry_run=False`, then `mark_processed` is called with `3` only, and the call returns `1`.
- S3.8 Given a one-account `config.yaml` that holds `senders_file: senders.csv`, a `senders.csv` with the line `deals@example.com,unsubscribe` under a `sender,verdict` header, the S3.1 categories, `jev_mail.cli.Mailbox` replaced with a fake that returns the S3.1 emails and whose `supports_idle` raises `ConnectionResetError` to end the loop after the first pass, and `jev_mail.cli.get_jev_client` replaced with the S3.1 client, when `cmd_watch` runs, then `decide` is called once, with the state of uid 2, and `move` is called with `(3, "BULK")`. `watch` has no `--review` option: `build_parser().parse_args(["watch", "--review", "x.csv"])` exits with status 2.
- S3.9 (boundary) Given a config with `ACTION` (action: `flag`) then `BULK` (action: `move` to `BULK`), in that order, an empty table, one email `Email(uid=2, subject="Call me", body="b", message_id="<c@example.com>", sender="ann@example.com")`, which has no Tier 0 hit, and a client that returns `{"ACTION": 0.9, "BULK": 0.9}`, when `_process_unprocessed` runs with `dry_run=False`, then `set_flag` is called once with `(2, True)` and `move` is called once with `(2, "BULK")` (Decide 3, Mike Crowe, 2026-10-27).

### S4. The review CSV

- S4.1 Given a directory `<dir>` with a one-account `config.yaml` for host `imap.example.com` and username `user@example.com`, the S3.1 categories, a `senders.csv` with the line `deals@example.com,unsubscribe` under a `sender,verdict` header, `jev_mail.cli.Mailbox` replaced with a fake that returns the S3.1 emails, and `jev_mail.cli.get_jev_client` replaced with the S3.1 client, when `cmd_run` runs with `--dry-run --review <tmp>/review.csv` and `<tmp>` is outside `<dir>`, then it returns `0`, and `csv.reader` reads the file as three rows: `["account", "uid", "subject", "source", "BILLING", "BULK"]`, `["imap.example.com/user@example.com", "3", "Weekly deals", "census", "", "1.0"]` and `["imap.example.com/user@example.com", "2", "Invoice #1", "jev", "0.9", "0.1"]`.
- S4.2 (negative) Given the S4.1 directory, when `cmd_run` runs with `--review <tmp>/review.csv` and no `--dry-run`, then it returns `1`, stderr is exactly `error: --review needs --dry-run` and a newline, the fake mailbox is never built, and no file is written.
- S4.3 (negative) Given the S4.1 directory, when `cmd_run` runs with `--dry-run --review <dir>/review.csv`, then it returns `1`, stderr is exactly `error: --review path must be outside <dir> -- its rows hold real subjects` and a newline, with `<dir>` resolved to an absolute path, the fake mailbox is never built, and no file is written.
- S4.4 (boundary) Given the S4.1 setup with a client that raises `ProviderError("boom")` on the uid 2 call, when `cmd_run` runs with `--dry-run --review <tmp>/review.csv`, then it returns `1`, and the file holds the header row and the uid 3 row only.
- S4.5 (boundary) Given `build_parser()`, when it parses `["run"]`, then `review` is `None`; and when `main()` runs with no subcommand in a directory that holds `config.yaml`, then `cmd_run` gets `review` as `None`.

### S5. Shipped files

- S5.1 Given `config.example.yaml` and an environment with `IMAP_USERNAME` and `IMAP_PASSWORD` set, when `load_config` reads it, then the category names are `["BILLING", "ACTION", "PERSONAL", "MONITOR", "BULK"]`, in that order, `ACTION` has threshold `0.7`, and `senders_file` is `""` (Decide 2, ruled A by Mike Crowe, 2026-10-26: the five replace `invoice`, `urgent` and `spam`).
- S5.2 Given `senders.example.csv` at the repository root, when `tier0.load_senders` reads it, then it returns a non-empty table, and every key ends with `@example.com`.
- S5.3 Given the branch, when `git check-ignore senders.csv sender-census.csv` runs at the repository root, then it prints both names; and `git check-ignore senders.example.csv` prints nothing and exits 1.
- S5.4 Given the branch, when `README.md` is read, then its "How it works" section names the four Tier 0 rules in order and says a hit skips Jev, and its config section shows `senders_file`, the move order rule and `run --dry-run --review <path>`; and `CLAUDE.md`'s pipeline list has a Tier 0 step before the `classify` step.

### S6. The live sample

- S6.1 Given the engineer's mailbox, `config.yaml` with `max_emails_per_run: 200` and the five categories, and the engineer's `senders.csv`, when `./jev-mail run --dry-run --review /tmp/gh3-review.csv` runs, then it exits 0, the file has 200 rows after its header, and the count of rows for each of `census`, `heuristic` and `jev` is reported, counts only. The `jev` count is below 200, the Phase 0 count, because Phase 0 sends each of the same 200 emails to Jev. Posting both numbers on GH-3 is a comment, and waits for the engineer's yes.

## Must NOT

- M1. Every test in `tests/` that passes at `ba47cef` still passes, with no existing test function changed. Proven by the `tests` layer and `git diff ba47cef -- tests/` showing added lines only in existing files.
- M2. An email with no Tier 0 hit gets the same single `decide` call, the same matched categories and the same actions as at `ba47cef`, except that a second `move` is skipped (S3.5). Proven by M1 and S3.1.
- M3. A dry run calls no mailbox write method and creates no `state.db`; `--review` writes only the file it names. Proven by GH-2's `tests/test_cli.py::test_dry_run_marks_nothing_and_creates_no_state_db` (M1) and S4.1 to S4.3.
- M4. A config with no `senders_file` and none of the five categories behaves as at `ba47cef`. Proven by S1.8, S2.5 and M1.
- M5. No new dependency: `pyproject.toml` and `uv.lock` do not change. Proven by `git diff --stat ba47cef -- pyproject.toml uv.lock` showing nothing.
- M6. No file under `jev_mail/providers/` or `jev_mail/mailbox/` changes. Proven by `git diff --stat ba47cef -- jev_mail/providers/ jev_mail/mailbox/` showing nothing.
- M7. No real sender data is committed: `senders.example.csv` and the tests hold only `example.com` addresses, and the live run reports counts only. Proven by S5.2, the `secrets` layer, and a diff reading of every added CSV and test line.
- M8. The keyword stays the source of truth: the state row is written only after `mark_processed`. Proven by GH-2's `tests/test_cli.py::test_real_run_marks_processed_then_writes_one_state_row` (M1).

## Touches

- `jev_mail/tier0.py`: new; the OTP pattern, `load_senders(path) -> dict[str, str]` and `decide(mail, senders, config) -> tuple[Category, str] | None`.
- `jev_mail/cli.py`: `_process_unprocessed` takes `senders` and an optional review writer, tries Tier 0 before `classify`, passes the source to `state.record`, prints the Tier 0 dry-run line, skips every `move` after the first; `cmd_run` loads the table, checks `--review`, opens the CSV; `cmd_watch` loads the table; `build_parser` adds `--review` to `run`; `main` sets `review` to `None` on the no-subcommand path.
- `jev_mail/config.py`: `AppConfig.senders_file: str = ""`; `load_config` reads the `senders_file` key; `save_config` writes it when it is not empty.
- `config.example.yaml`: replace `invoice`, `urgent` and `spam` with the five categories in the order BILLING, ACTION, PERSONAL, MONITOR, BULK, so a bill that Jev also calls bulk moves to BILLING, `ACTION` keeping `threshold: 0.7` and the `webhook`; a comment on the move order; and a commented `senders_file: senders.csv` line (Decide 2, Mike Crowe, 2026-10-26).
- `senders.example.csv`: new; a `sender,verdict` header and one fake `example.com` row per verdict.
- `.gitignore`: `senders.csv` and `sender-census.csv`.
- `tests/test_tier0.py`: new; S1.1 to S1.10, S2.1 to S2.4, S5.2.
- `tests/test_cli.py`: S2.6, S3.1 to S3.9, S4.1 to S4.5.
- `tests/test_config.py`: S2.5, S2.7, S5.1.
- `README.md`, `CLAUDE.md`: as S5.4 says.
- `spec-evidence/2026-10-26-GH-3/EVIDENCE.md` (in build): the S5.3 and S5.4 readings, the M5 to M7 diff readings, and the S6.1 counts.

## Documentation

- `README.md`, sections "How it works" (line 147) and "Config, if you'd rather skip the TUI" (line 166): the Tier 0 rules, `senders_file`, the move order and `--review` (S5.4).
- `CLAUDE.md`, section "Architecture": a Tier 0 step in the pipeline list, and the `senders_file` key in the Config paragraph (S5.4).

## Known limits

- A Tier 0 hit is final, so the email gets one category only: a bill from a bulk sender never gets `BILLING`. The fix is a `keep` row for that sender (GH-3 decision comment of 2026-10-25).
- A noreply receipt that carries `List-Unsubscribe` lands in `BULK`, because rule 3 comes before rule 4 (same comment).
- The OTP phrases are English only, and the noreply rule matches only the three exact local parts, so `noreply-billing@` and similar go to Jev. The noreply rule keeps to the brief's three literals, and a bare number in a subject is not taken as a one-time code, because order and invoice numbers must reach Jev for `BILLING`.
- The `From` header is not authenticated. A spoofed `From` of a table sender gets that sender's verdict. A spoofed `keep` sender only goes to Jev.
- The `--review` check refuses paths inside `--dir` only. A path inside some other repository is allowed.
- `senders.csv` is git-ignored, so git does not back it up.
- An email that Jev scores as both `ACTION` and `BULK` is flagged and then moved to `BULK`, out of the inbox, because `ACTION` has no `move` (Decide 3).

## Verification contract

| Layer | What it gates | Threshold |
|---|---|---|
| tests | S1.1 to S5.2, M1 to M4, M8 | `mise exec -- uv run pytest -q` exits 0 |
| secrets | committed content, M7 | `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` reports no leak |
| diff reading | S5.3, S5.4, M1, M5, M6, M7 | the cited lines, `git check-ignore` and `git diff` commands show only the allowed changes |
| live run | S6.1 | exit 0, 200 rows, the `jev` count below 200; counts only |
