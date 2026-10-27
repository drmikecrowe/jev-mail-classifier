# Agent decisions: GH-4 Gmail backend over the Gmail API

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
