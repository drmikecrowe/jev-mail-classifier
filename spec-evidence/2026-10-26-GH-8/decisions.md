# Decisions — GH-8: One ProviderError on one email aborts the whole run

## Setup plan

- Isolation: branch `GH-8-provider-error-per-email` from `GH-2-mailbox-backend` at `b29cc70`. The change edits the `_process_unprocessed` that GH-2 rewrote, so branching from `master` would conflict. GH-2 must merge first, or the two PRs stack.
- Git: one commit per loop step, files staged by name, each staged diff shown to the engineer before commit (public repository, CLAUDE.md).
- New dependencies: none.
- New files: none in source; `spec-evidence/2026-10-26-GH-8/` holds the story artifacts.
- Tooling audit: as GH-2. `tests` (`mise exec -- uv run pytest -q`) and `secrets` (`mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .`) are declared in `tools/gauntlet-layers.json` and run. Lint, format, type check, coverage, mutation and randomized order: no tool declared; these stay `UNAVAILABLE`.
- Merge gate: the repository has no `.github/` directory and no `.pre-commit-config.yaml`; 0 checks transcribed.
- Context pack: the `context-pack` agent could not read the tree. The Gortex hook blocked its Read, Grep and Glob, and it holds no Gortex tools. Its report is in `context-pack.md` verbatim. The engineer chose to record it and continue; this plan rests on the doer's own reads, listed below.

## Facts this SPEC rests on

1. `jev_mail/cli.py::_process_unprocessed` at `b29cc70` calls `classify(client, config, mail.state)` for each email with no `try`. `cmd_run` catches only `OSError` and `imaplib.IMAP4.error` around it, and `cmd_watch` the same, so a `ProviderError` from `classify` ends the process with a traceback. Read at `b29cc70`.
2. `ProviderError` reaches `classify` from `client.decide`: the adapters wrap `httpx.HTTPError` in it (`typesafe_direct.py`, `openrouter.py`, `vercel_gateway.py`), and `extract_probabilities` in `jev_mail/providers/base.py:51` and `:54` raises it for a malformed answer. `get_jev_client` raises it at startup, before the loop, and `cmd_run` and `cmd_watch` already catch that at `jev_mail/cli.py:89` and `:112`. Found with `rg -n '\bProviderError\b'`.
3. `Mailbox.fetch_unprocessed` returns the newest unprocessed mail first and caps it at `max_emails_per_run` (`jev_mail/mailbox/imap.py`). A failing email that is never marked therefore comes back first on the next run.
4. GH-2's live dry run failed on an email over the provider's token limit (GH-2 `decisions.md` fact 11). GH-2's body cap removed that cause, and the branch run then exited 0 with the TypeSafe-direct adapter answering every email.
5. Three texts still say the TypeSafe-direct adapter is not live-tested: `CLAUDE.md:36`, `README.md:218` to `:219`, and the docstring at `jev_mail/providers/typesafe_direct.py:11`. Found with `rg -n -i 'live[- ]test|docs only|verified|not yet'`.
6. The existing `error:` lines in `jev_mail/cli.py` go to stderr (`print(..., file=sys.stderr)`), and the dry-run lines go to stdout.

## Restatements

- The brief's "print one `error:` line naming the uid and the provider error" is restated as the Error line in Definitions, on stderr, as every other `error:` in `cli.py` is.
- The brief's "the run exits nonzero at the end if any email failed" is restated as: `cmd_run` processes every account, then returns 1 when any email in any of them failed. `watch` has no end, so it has no such exit.
- The brief's "leave that email unmarked (no keyword, no state row)" is restated as M4, and also covers actions: no action runs for a failing email, because `classify` fails before any match exists.

## Decide calls

### Decide 1. Which stale "not live-tested" texts change?

Evidence: fact 5. The brief names `CLAUDE.md` only, and it forbids provider code changes.

- A. `CLAUDE.md` and `README.md`. Cost: the docstring in `typesafe_direct.py` still says "not yet live-tested by us -- flagged in the README", and the README no longer flags it.
- B. `CLAUDE.md`, `README.md` and the docstring. Cost: a comment-only change under `jev_mail/providers/`, against the brief's scope guard; M5 changes to allow it.
- C. `CLAUDE.md` only, as the brief says. Cost: the README, which users read, keeps telling them the TypeSafe-direct path is untested.

Default: A. Ruling: A (Mike Crowe, 2026-10-26).
Changes: S4.1 now also covers `README.md:218` to `:219`; the Touches list and the Documentation section name `README.md`; Known limits names the docstring left at `jev_mail/providers/typesafe_direct.py:11`. M5 is unchanged.

### Decide 2. What happens to an email that fails on every run?

Evidence: fact 3; Known limits in SPEC.md.

- A. Leave it unmarked, as the brief says. It is retried on every run. Cost: it can be billed again on every run, and when `max_emails_per_run` or more of the newest emails fail every time, a run makes no progress.
- B. Mark it with a second keyword such as `$JevFailed`, and leave it out of the unprocessed search. Cost: a new keyword and a change to `fetch_unprocessed`'s search; a failed email is never retried until someone removes the keyword by hand.

Default: A. Ruling: A (Mike Crowe, 2026-10-26).
Changes: the first Known limits line cites Decide 2's ruling; no scenario changes.

## Revisions

### Revision 1. Decide 1 and 2 ruled
The engineer ruled A and A in the Decide round; SPEC.md was updated with those rulings.

### Revision 2. Gate 1a round 1 fix
Finding PR-REFERENT: the Summary now states the newest-first fact itself instead of pointing at GH-2 fact 11. The judge's gap on M3 is also closed: M3 now names its input, the exact stderr text and the exit code.
