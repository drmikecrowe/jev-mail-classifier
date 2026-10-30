# Comments on GH-5

Oldest first, pulled from the tracker.

## 1. drmikecrowe, 2026-10-25T11:41:45Z

## Decisions (2026-10-25)
- **Client ID:** Microsoft Graph Command Line Tools (first-party public client). Grant tenant admin consent once for `Mail.ReadWrite offline_access`. No app registration of our own. Rejected reusing the `az` login token: Azure CLI's preconsented Graph scopes usually lack `Mail.ReadWrite`. Trade-off: the app is shared, so the tenant consent also applies to other users of that client.
- **Dependency:** `msal` approved for device code, refresh, and the on-disk token cache.

## 2. drmikecrowe, 2026-10-25T11:44:09Z

## Tenant check (2026-10-25)
In the pinnsg.com tenant, client `14d82eec-204b-4c2f-b7e8-296a70dab67e` appears as "Microsoft Graph PowerShell" (same app as Graph Command Line Tools) and is enabled. The only tenant-wide grant (`AllPrincipals`) is `User.Read`.

**New step 0:** before any Graph code runs, a tenant admin grants delegated consent for `Mail.ReadWrite offline_access` to this client. Without that, the device-code login either fails or asks for consent on every user.

## 3. drmikecrowe, 2026-10-25T11:47:49Z

## Decisions (2026-10-25)
- **Fetch:** `$filter` on `receivedDateTime` with a per-account cursor, not `/delta`. The SQLite set dedups. Trade-off: mail moved back into the Inbox with an older date is missed.
- **Token cache:** next to `config.yaml` (see #2), git-ignored, `chmod 600`. This replaces `~/.config/jev-mail/msal_<account>.json`.

## 4. drmikecrowe, 2026-10-30T18:17:32Z

# Gate 1, story readiness

verdict: ready
story: GH-5
process: spec-evidence 0.18.0
model: claude-sonnet-5-5
tokens: 44783/1488
rubric: rubric.md 4c2886dd973af290e392b5da5cdeb6f654611d2e87b0d02ee37757bab0a040af
record: story-record.json
graded: 2026-10-30T18:17:22.987Z

## Reasons

none

## Record

```json
{"input":"Story","type":"feature","missing":[],"gaps":["prompt 2: a reader has to guess what happens to a message in AC-3 when the first run has no cursor and the Inbox holds more than max_emails_per_run messages; AC-4 covers the cap but not the cursor start","prompt 3: an implementation could satisfy every criterion and still never be consented to by the tenant admin, since Step 0 is a constraint and no criterion covers it","prompt 1: nothing says what `run` prints when a Graph call fails with a transient error such as a 429 or 5xx"],"fields":[{"name":"who","state":"present"},{"name":"what","state":"present"},{"name":"done-looks-like","state":"present"},{"name":"example","state":"present"}],"readings":[],"findings":[],"deferred":[{"ac":"AC-3","why":"where the per-account cursor is stored needs the current code layout; the author note defers it to the plan review"},{"ac":"AC-4","why":"the cursor storage is the same open question as AC-3, so the plan review carries it"}],"items":[{"ac":"AC-1","status":"proven","evidence":"Configure an o365 account with no o365-token.json and run `./jev-mail run`: it must exit before any Graph call and name auth-o365. Run `./jev-mail auth-o365`, sign in, then check that o365-token.json exists beside config.yaml with mode 0600 and that `git check-ignore o365-token.json` succeeds. It is false if any step differs."},{"ac":"AC-2","status":"proven","evidence":"Age the token file's access token past 1 hour and run `run` with the network mocked. It is false if a device-code prompt appears, if the token file is not rewritten, or if a mocked refresh-token rejection does not stop the account with an error naming auth-o365."},{"ac":"AC-3","status":"proven","evidence":"Seed a mock Inbox with one message lacking JevProcessed, one with a state.db row but no JevProcessed, and one moved in with a receivedDateTime older than the cursor. Run `run`. It is false if the second or third is fetched, or if the first is not, or if bodies do not come back as text."},{"ac":"AC-4","status":"proven","evidence":"Mock 30 new messages with max_emails_per_run set to 25. Run `run` twice. It is false if the first run does not process exactly the newest 25, or if the second does not process the other 5, or if any message received after the cursor is left unprocessed after both runs."},{"ac":"AC-5","status":"proven","evidence":"Give a mock message the categories X and run a tag action of BULK. It is false if the PATCH categories are not [X, BULK]. Repeat with a message that already has BULK; it is false if BULK appears twice. It is false if the PATCH touches any field other than categories."},{"ac":"AC-6","status":"proven","evidence":"With a mock mailbox that has no top-level Bulk folder, run a move to Bulk. It is false if there is no POST /me/mailFolders followed by a move to the new id. With two matched categories that both have a move, it is false if more than the first in config order runs."},{"ac":"AC-7","status":"proven","evidence":"Call set_flag(True), set_flag(False), set_seen(True) and set_seen(False) against a mock Graph. It is false if the PATCH values differ from flagged, notFlagged, true and false, or if categories or folder change. Run a pass where no category matches: it is false if JevProcessed and a state.db row are missing. Run with --dry-run: it is false if either is added."},{"ac":"AC-8","status":"proven","evidence":"Run `watch` on one o365 account with a fake clock and a mock Inbox. It is false if the second pass does not start after poll_interval_seconds (60 by default), or if a message added during the wait is not processed on the second pass. Run it with two accounts: it is false if watch does not refuse."}]}
```

## Story

````
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
````
