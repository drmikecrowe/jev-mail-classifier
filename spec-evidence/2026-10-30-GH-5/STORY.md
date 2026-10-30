---
id: GH-5
type: feature
source:
  tracker: github
  external_id: GH-5
  url: https://github.com/drmikecrowe/jev-mail-classifier/issues/5
  version: 2026-10-25T11:47:49Z
---
# Office 365 backend over Microsoft Graph
## Description
Who: the owner of a pinnsg.com Office 365 mailbox who runs jev-mail on it. IMAP is not an option for the pinnsg.com tenant (basic auth off).
What: a third mail backend. `GraphMailbox` in `jev_mail/mailbox/graph.py` implements the `MailBackend` Protocol (`jev_mail/mailbox/base.py`) over Microsoft Graph, so `run` and `watch` classify an Office 365 Inbox and act on it. Sign-in uses the delegated device-code flow with scopes `Mail.ReadWrite offline_access`.
Done looks like: AC-1 to AC-8 below.
Example: A test message from `news@example.com` arrives in the Inbox. `./jev-mail run` matches it to category `BULK`. The message gets the Outlook categories `BULK` and `JevProcessed` and moves to the folder `Bulk`. A second `run` does not fetch it again.
Drafted by the assistant from the author's text; approved by the author 2026-10-30.
## Acceptance criteria
- AC-1: The account is `backend: o365` and has no token file. `./jev-mail auth-o365` shows a device-code URL and code. After sign-in, it writes `o365-token.json` beside `config.yaml` with mode `0600`; boundary: with no token file, `run` and `watch` refuse that account before any Graph call and name `auth-o365`; negative: `o365-token.json` is in `.gitignore` and is never committed.
- AC-2: The token file's access token has expired (more than 1 hour old). `run` gets a new access token from the refresh token and shows no device-code prompt; boundary: the refreshed cache is written back to the token file, so the next run reuses it; negative: if Microsoft rejects the refresh token, `run` stops that account with an error that names `auth-o365`, and it does not prompt.
- AC-3: `run` fetches Inbox messages that have no `JevProcessed` category and no `state.db` row, up to `max_emails_per_run`, newest first. Bodies come back as text (`Prefer: outlook.body-content-type="text"`). On the first run, with no cursor yet, the whole Inbox is eligible; boundary: an Outlook rule removed `JevProcessed` from a message, but the message has a `state.db` row, so `run` does not fetch it again; negative: a message moved back into the Inbox with a `receivedDateTime` older than the cursor is not fetched.
- AC-4: 30 new messages arrive and `max_emails_per_run` is 25. One `run` processes the newest 25, and the next `run` processes the other 5; boundary: the cursor never moves past a message that has not been processed; negative: no message received after the cursor is left unprocessed across runs.
- AC-5: A matched category with a `tag` action of `BULK` adds the Outlook category `BULK` to the message and keeps its other categories; boundary: when the message already has `BULK`, no second `BULK` is added; negative: the tag changes no other field on the message.
- AC-6: A `move` action to `Bulk` moves the message to that folder; boundary: when no top-level folder `Bulk` exists, jev-mail creates it and then moves the message; negative: when several matched categories have a `move`, only the first in config order runs.
- AC-7: `set_flag(True)` sets `flagStatus` to `flagged`, and `set_seen(True)` sets `isRead` to true; boundary: `set_flag(False)` sets `notFlagged`, and `set_seen(False)` sets `isRead` to false; negative: neither changes the message's categories or folder. After classification, the message gets the category `JevProcessed` and a `state.db` row, even when no category matched; `run --dry-run` adds neither.
- AC-8: `./jev-mail watch` on one `o365` account runs a pass, waits `poll_interval_seconds` (default 60), and runs again; boundary: a message that arrives during the wait is processed on the next pass; negative: `watch` refuses more than one account, as it does today.
## Constraints
- Step 0: a tenant admin grants delegated consent for `Mail.ReadWrite offline_access` to client `14d82eec-204b-4c2f-b7e8-296a70dab67e` (Microsoft Graph Command Line Tools) before any Graph code runs. No app registration of our own.
- `msal` is the one new dependency, and it is approved. `httpx` is already present.
- Fetch uses `$filter` on `receivedDateTime` with a per-account cursor, not `/delta`.
- Graph mapping: `add_tag` uses `PATCH /me/messages/{id}` with `categories` (read, then append). `move` uses `POST /me/messages/{id}/move` with `destinationId`, and creates the folder with `POST /me/mailFolders` when it is missing. `set_flag` uses `PATCH` with `flag.flagStatus`. `set_seen` uses `PATCH` with `isRead`.
- The `configure` wizard does not change. The account is added to `config.yaml` by hand, as for Gmail.
## Author notes
- SR-DEFER: "where the per-account cursor is stored". engineering checks at the plan review
