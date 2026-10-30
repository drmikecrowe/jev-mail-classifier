# Agent decisions: GH-5: Office 365 backend over Microsoft Graph

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
