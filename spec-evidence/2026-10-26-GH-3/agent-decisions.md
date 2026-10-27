# Agent decisions: GH-3 Tier 0, decide known senders and obvious bulk mail before Jev

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
