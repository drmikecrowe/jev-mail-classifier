# GH-8: One ProviderError on one email aborts the whole run

## Summary

This change stops one failing email from aborting the whole run. Today, when the Jev provider raises `ProviderError` for one email (an HTTP 400 such as `max_tokens_exceeded`, a 5xx, a timeout, or a malformed answer), the exception leaves `_process_unprocessed`. `cmd_run` does not catch it, so the run ends with a traceback, and every email after it in that run is skipped. The failing email is never marked `$JevProcessed`. `fetch_unprocessed` searches for unmarked mail and returns the newest first, so the next run fetches the same email first again and fails on it again.

What changes: `_process_unprocessed` in `jev_mail/cli.py` catches `ProviderError` for each email. It prints one `error:` line to stderr that names the email's UID and the error, leaves that email unmarked, and goes on to the next email. It returns the number of emails that failed. `cmd_run` exits 1 when any email in any account failed, after it has processed every account. `CLAUDE.md` and `README.md` stop saying that only the OpenRouter adapter is verified, because the TypeSafe-direct adapter answered a live key during the GH-2 build.

The acceptance criteria, in plain words:

- An email whose classify call raises `ProviderError` gets one `error:` line on stderr, and no keyword, no action and no state row. The emails after it are still processed.
- A dry run does the same: the failing email gets its `error:` line, and the other emails still print their dry-run lines.
- `run` exits 1 when any email failed, and only after every account has been processed. With no failure it still exits 0.
- `watch` keeps going after a failing email, and retries that email on the next pass.
- `CLAUDE.md` and `README.md` name the TypeSafe-direct adapter as verified against a live key.

What must not change: the existing tests, the dry-run stdout for emails that succeed, the startup `error:` for a missing or unknown provider, the provider code, and the dependency list. Unit tests prove every criterion except the docs, which are proven by citing the changed lines. Open decisions: none.

## Orientation

- Lane: engineering, because this is a robustness fix found during the GH-2 build, in the CLI's error handling; there is no product author.
- Change: catch `ProviderError` per email in `_process_unprocessed`, report it, leave the email unmarked, continue, and make `run` exit 1 when any email failed.
- Why: one provider error on one email aborts the run and, because that email stays the newest unprocessed one, aborts every later run too.
- Touches: `jev_mail/cli.py`, `tests/test_cli.py`, `CLAUDE.md`, `README.md`.
- Decide: Decide 1, which stale "not live-tested" texts change; Decide 2, what happens to an email that fails on every run.
- Decided: Decide 1 ruled that `CLAUDE.md` and `README.md` change and the adapter docstring does not; it governs S4.1, the Touches entries for both docs, and the Documentation section (Mike Crowe, 2026-10-26). Decide 2 ruled that a failing email stays unmarked and is retried on every run; it governs the first Known limits line (Mike Crowe, 2026-10-26).
- Brief: issue GH-8. Scope guard: no provider code change and no new dependency.
- Tier: 2
- Issue: GH-8
- Isolation: branch `GH-8-provider-error-per-email` from `GH-2-mailbox-backend` at `b29cc70`, because it changes the `_process_unprocessed` that GH-2 rewrote.

## Definitions

- **Failing email**: an email whose `classify(client, config, mail.state)` call raises `ProviderError`.
- **Error line**: the stderr line `error: email uid <uid>: <ProviderError message> -- left unprocessed, will retry next run`.

## Scenarios

### S1. One failing email does not stop the others

- S1.1 Given a fake backend that returns `Email(uid=3, subject="Big", body="b")` then `Email(uid=2, subject="Invoice #1", body="b")`, a client whose `decide` raises `ProviderError("TypeSafe API request failed: 400 Bad Request")` on the first call and returns `{"Invoice": 0.9}` on the second, and a category `Invoice` with one `tag` action of value `Invoice`, when `_process_unprocessed` runs with `dry_run=False`, then `mark_processed` is called once, with `2`; `add_tag` is called once, with `(2, "Invoice")`; stderr is exactly `"error: email uid 3: TypeSafe API request failed: 400 Bad Request -- left unprocessed, will retry next run\n"`; and the call returns `1`.
- S1.2 (negative) Given the S1.1 inputs with `Email(uid=3, ..., message_id="<big@example.com>")`, `Email(uid=2, ..., message_id="<ok@example.com>")` and a `State` on `tmp_path / "state.db"`, when `_process_unprocessed` runs with `dry_run=False` and `state` set, then `state.db` holds exactly one state row, with message id `<ok@example.com>`.
- S1.3 Given the S1.1 inputs, when `_process_unprocessed` runs with `dry_run=True`, then stdout is exactly `"[dry-run] 'Invoice #1': Invoice (0.90) -> tag\n"`, stderr is the S1.1 error line, `mark_processed` is never called, and the call returns `1`.
- S1.4 (boundary) Given a fake backend that returns one email and a client that returns `{"Invoice": 0.9}`, when `_process_unprocessed` runs with `dry_run=False`, then it returns `0` and stderr is empty.

### S2. The exit code of `run`

- S2.1 Given a directory with a one-account `config.yaml`, `jev_mail.cli.Mailbox` replaced with a fake that returns the S1.1 emails, and `jev_mail.cli.get_jev_client` replaced with the S1.1 client, when `cmd_run` runs without `--dry-run`, then it returns `1`, and the fake's `mark_processed` was called with `2` only.
- S2.2 Given a two-account `config.yaml` where the fake returns one email per account, and a client that raises `ProviderError` on its first call and returns `{"Invoice": 0.9}` on its second, when `cmd_run` runs without `--dry-run`, then the fake is built with both accounts in order, `mark_processed` is called once, for the second account's email, and `cmd_run` returns `1`.
- S2.3 (boundary) Given the S2.1 setup with a client that returns `{"Invoice": 0.9}` on every call, when `cmd_run` runs without `--dry-run`, then it returns `0`.

### S3. `watch` keeps going

- S3.1 Given a one-account `config.yaml`, the S1.1 fake emails and client, and a fake whose `supports_idle` raises `ConnectionResetError` to end the loop after the first pass, when `cmd_watch` runs, then `mark_processed` is called with `2` only, stderr contains the S1.1 error line, and `supports_idle` was reached (the failing email did not end the first pass).

### S4. The docs

- S4.1 Given the branch, when `CLAUDE.md` is read, then its Providers paragraph says the OpenRouter and TypeSafe-direct adapters are verified against a live key and the Vercel adapter is built from docs only, and it no longer says "Only the OpenRouter adapter is verified"; and `README.md`'s provider note says the OpenRouter and TypeSafe-direct paths are live-verified and the Vercel-gateway adapter is not yet tested against a live key (Decide 1, Mike Crowe, 2026-10-26).

## Must NOT

- M1. Every test in `tests/` that passes at `b29cc70` still passes, with no existing test function changed. Proven by the `tests` layer and `git diff b29cc70 -- tests/` showing added lines only.
- M2. The dry-run stdout of emails that do not fail is unchanged. Proven by S1.3 and GH-2's `tests/test_cli.py::test_dry_run_output_is_unchanged` (M1).
- M3. A `ProviderError` from `get_jev_client` at startup (no key, unknown provider) still prints `error:` and exits 1 before any mailbox connects. Proven by a new test in `tests/test_cli.py`: given a valid one-account `config.yaml`, `jev_mail.cli.get_jev_client` replaced with a function that raises `ProviderError("no Jev API key found")`, and `jev_mail.cli.Mailbox` replaced with a fake that records each build, when `cmd_run` runs, then it returns `1`, stderr is exactly `"error: no Jev API key found\n"`, and the fake is never built.
- M4. A failing email gets no keyword, no action and no state row. Proven by S1.1 and S1.2.
- M5. No file under `jev_mail/providers/` changes, unless Decide 1 rules otherwise. Proven by `git diff --stat b29cc70 -- jev_mail/providers/`.
- M6. No new dependency: `pyproject.toml` and `uv.lock` do not change. Proven by `git diff --stat b29cc70 -- pyproject.toml uv.lock` showing nothing.
- M7. Only `ProviderError` is caught per email; any other exception still leaves `_process_unprocessed`. Proven by a new test where `decide` raises `RuntimeError` and the exception propagates.

## Touches

- `jev_mail/cli.py`: `_process_unprocessed` catches `ProviderError` around `classify`, prints the error line, skips the email, and returns the count of failing emails; `cmd_run` sums the counts over all accounts and returns 1 when the sum is above 0; `cmd_watch` ignores the count and keeps looping.
- `tests/test_cli.py`: S1.1 to S1.4, S2.1 to S2.3, S3.1, M3, M7.
- `CLAUDE.md`: the Providers paragraph's verification sentence (S4.1).
- `README.md`: the provider note at lines 218 to 221 (S4.1).
- `spec-evidence/2026-10-26-GH-8/EVIDENCE.md` (in build): the S4.1 citation and the M1, M5, M6 diff readings.

## Documentation

- `CLAUDE.md:36` and `README.md:218` to `:221`: change as S4.1 says (Decide 1). The docstring at `jev_mail/providers/typesafe_direct.py:11` stays as it is (Decide 1, M5).

## Known limits

- A failing email stays unprocessed and is retried, and possibly billed again, on every run (Decide 2, ruled A by Mike Crowe, 2026-10-26).
- The docstring of `TypeSafeDirectClient` still says the adapter is not live-tested and is flagged in the README (Decide 1).
- When at least `max_emails_per_run` of the newest unprocessed emails fail on every run, a run makes no progress. It still exits 1 and names each of them.
- `watch` retries a failing email on every poll.
- An error inside an action (for example a webhook `httpx` error) is not a `ProviderError` and still aborts the run (M7).

## Verification contract

| Layer | What it gates | Threshold |
|---|---|---|
| tests | S1.1 to S3.1, M1 to M4, M7 | `mise exec -- uv run pytest -q` exits 0 |
| secrets | committed content | `mise exec gitleaks@8.30.1 -- gitleaks git --no-banner .` reports no leak |
| diff reading | S4.1, M1, M5, M6 | the cited lines and `git diff` commands show only the allowed changes |
