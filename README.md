<div align="center">

```
     ██╗███████╗██╗   ██╗    ███╗   ███╗ █████╗ ██╗██╗
     ██║██╔════╝██║   ██║    ████╗ ████║██╔══██╗██║██║
     ██║█████╗  ██║   ██║    ██╔████╔██║███████║██║██║
██   ██║██╔══╝  ╚██╗ ██╔╝    ██║╚██╔╝██║██╔══██║██║██║
╚█████╔╝███████╗ ╚████╔╝     ██║ ╚═╝ ██║██║  ██║██║███████╗
 ╚════╝ ╚══════╝  ╚═══╝      ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚══════╝
```

**Your inbox, judged in milliseconds.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Powered by Jev](https://img.shields.io/badge/powered%20by-Jev-purple)](https://typesafe.ai)
[![TUI: Textual](https://img.shields.io/badge/TUI-Textual-orange)](https://github.com/textualize/textual)

*Tag, move, flag, and notify -- no LLM prompt engineering, no JSON parsing, no per-email API bill that adds up.*

https://github.com/user-attachments/assets/4604d2ff-6e59-4938-983e-305d355be5d2

</div>

---

## Why

Classifying email with a normal LLM means writing a prompt, hoping it returns valid
JSON, and paying full chat-completion prices for what is really just "does this apply:
yes or no." [Jev](https://typesafe.ai), TypeSafe's **System One model**, skips all of
that: you send it your inbox state and a set of yes/no questions, and it hands back
calibrated probabilities directly -- typically in well under a second, for a fraction of
a cent per email.

### What makes Jev different from calling an LLM

Chat LLMs are trained with RLHF to produce fluent, human-pleasing *text* -- great for
conversation, but that same optimization is what makes them mode-drop, hedge, and
overstate confidence when what you actually need is a reliable decision buried inside
software. Jev is TypeSafe's first **System One model**: instead of generating a
sentence you have to parse, it's trained with **Reinforcement Learning for Calibrated
Decisions (RLCD)** to output typed, calibrated probabilities directly -- "more like
code: reliable, fast, self-consistent, and type-safe" than like a chatbot reply.

That shows up as a very different cost and latency profile for exactly the kind of
question `jev-mail-classifier` asks per email ("is this an invoice, yes or no"):

- **~193x faster** than a general-purpose LLM on this class of task
- **~238x cheaper** per token than Claude ($42 per billion input tokens)
- In TypeSafe's own benchmark, an equivalent workflow ran in **0.114s for $0.000081**
  on Jev vs. **8.566s for $0.014** on an LLM

Because the output is a calibrated probability rather than free text, you also get a
knob a chat completion doesn't give you for free: a **threshold per category**. Set
`urgent` to fire at `0.7` and `spam` at `0.9`, and Jev's own confidence -- not a second
prompt asking "are you sure?" -- decides whether an action runs.

**jev-mail-classifier** wraps that in something you can actually run against a real
mailbox: connect over IMAP, define categories in plain language, and let each category
tag, move, flag, or ping a webhook -- all from a terminal UI, no code required.

## Quickstart

```bash
git clone https://github.com/parth-kp/jev-mail-classifier
cd jev-mail-classifier
./install.sh
```

That's it -- `install.sh` sets up a virtualenv, installs the package, and drops you
straight into the setup wizard. Paste **one** Jev API key (TypeSafe, OpenRouter, or
Vercel AI Gateway -- whichever you have), your IMAP login, and start adding categories.

Once configured, run it with `./jev-mail` from inside the project directory --
`install.sh` installs into a local `.venv`, and `./jev-mail` is a small wrapper that
finds it for you, so there's no venv to activate and nothing to add to your shell PATH:

```bash
./jev-mail run             # classify unprocessed mail once, then exit (cron-friendly)
./jev-mail run --dry-run   # see what WOULD happen, without touching your mailbox
./jev-mail watch           # keep classifying new mail as it arrives (IMAP IDLE)
./jev-mail configure       # reopen the TUI to add/edit categories or credentials any time
```

Re-running `./install.sh` later is safe -- it won't ask for your key/login again if
`config.yaml` already exists, and the credentials screen always shows what's already
saved (masked) rather than blank fields.

> **Coming soon:** `pipx install jev-mail-classifier` -- for now, `install.sh` after
> cloning is the whole setup.

## Getting your IMAP username & password

The wizard asks for these on the first screen. "Username" is just your email address;
"password" is where people get stuck, because **if your account has 2-factor
authentication on, your normal login password will not work over IMAP** -- you need a
separate *app password* instead.

**Gmail**
1. Turn on IMAP: Gmail Settings (gear icon) -> **See all settings** -> **Forwarding and
   POP/IMAP** tab -> enable IMAP -> Save.
2. Create an app password: go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   (requires 2-Step Verification to be on -- turn it on first if it isn't). Name it
   anything (e.g. "jev-mail"), copy the 16-character password it gives you.
3. Use your full Gmail address as the username, and that 16-character code as the
   password. Host: `imap.gmail.com`, port `993`.

**Outlook / Microsoft 365**
1. Go to [account.microsoft.com/security](https://account.microsoft.com/security) ->
   **Advanced security options** -> **App passwords** -> create one.
2. Username is your full email address, password is the app password. Host:
   `outlook.office365.com`, port `993`.

**Yahoo Mail**
1. Account Info -> **Account Security** -> turn on 2-step verification -> **Generate
   app password**. Host: `imap.mail.yahoo.com`, port `993`.

**Any other provider**
Look for "IMAP settings" in your provider's account/security settings -- you need the
IMAP host and port (almost always `993`), and, if 2FA is on, an app-specific password
generated the same way. If 2FA is off, your regular email password usually works, but
an app password is safer since it can be revoked without changing your main password.

## What it looks like

`jev-mail configure` is a three-step terminal UI:

1. **Credentials** -- paste your Jev key and IMAP login (masked input, written straight
   to a git-ignored `.env` -- you never hand-edit a config file for secrets)
2. **Mailbox** -- host, port, folder to watch, poll interval
3. **Categories** -- a live list you manage with single keystrokes:
   `a` add &middot; `e` edit &middot; `d` delete &middot; `s` save & exit

<p align="center">
  <img src="media/screenshots/tui-1-credentials.png" alt="Credentials screen: paste one Jev key and your IMAP login" width="49%">
  <img src="media/screenshots/tui-2-mailbox.png" alt="Mailbox screen: IMAP host, port, folder, poll interval" width="49%">
</p>
<p align="center">
  <img src="media/screenshots/tui-3-categories.png" alt="Categories screen: live list of configured categories" width="49%">
  <img src="media/screenshots/tui-4-category-edit.png" alt="Edit category screen: description plus a checklist of actions" width="49%">
</p>

Each category is a plain-language description plus a checklist of actions -- tag, move,
flag, mark read, or hit a webhook -- no YAML syntax to remember.

## How it works

```
   IMAP inbox                    Jev                      your mailbox
 ┌──────────────┐   subject+body   ┌───────────┐   probabilities   ┌──────────────┐
 │  unprocessed │ ───────────────► │  one call, │ ────────────────► │ tag / move / │
 │    email     │                  │ one yes/no │                    │ flag / hook  │
 │              │ ◄─────────────── │  question  │ ◄──────────────── │              │
 └──────────────┘   marked          │ per category│    threshold      └──────────────┘
                     processed       └───────────┘     per category
```

Every configured category becomes one independent yes/no question in a **single** Jev
call per email (multi-label: an email can match several categories at once). Each
category's probability is checked against its threshold, and every action attached to a
matching category runs. Processed mail is marked with a private IMAP keyword
(`$JevProcessed`), which stays the source of truth. A real run also writes a local
record of each processed email to `state.db` beside `config.yaml`; a dry run writes nothing.

Before Jev, a local **Tier 0** step tries four rules in order, and the first that fires
gives the email one category and **skips the Jev call**:

1. The sender is in your sender table (`senders_file`): `unsubscribe` gives `BULK`,
   `auto-archive` gives `MONITOR`. A `keep` sender skips the other rules and always goes to Jev.
2. A one-time-code subject ("verification code", "2FA", ...) gives `MONITOR`.
3. A `List-Unsubscribe` header gives `BULK`.
4. A `noreply@`, `no-reply@` or `donotreply@` sender gives `MONITOR`.

A rule whose category is not in your config does not fire. The `state.db` row records
which path decided: `census`, `heuristic` or `jev`.

## Config, if you'd rather skip the TUI

`config.yaml` (see [`config.example.yaml`](config.example.yaml)) is plain and hand-editable:

```yaml
categories:
  invoice:
    description: "Invoice, billing statement, or payment request"
    actions:
      - type: tag
        value: Invoice
      - type: move
        folder: Invoices

  urgent:
    description: "Time-sensitive, needs action today"
    threshold: 0.7
    actions:
      - type: flag
      - type: webhook
        url: ${SLACK_WEBHOOK_URL}
```

`mailbox.max_emails_per_run` (default `25`) caps how many unprocessed emails get
classified in a single `run` or poll cycle -- protects against a huge backlog burning
through your Jev quota or a run taking forever the first time you point this at a real
inbox. If a run hits the cap, it prints a notice and picks up the rest next time.
"Unprocessed" means missing the `$JevProcessed` keyword, not `\Seen`/unread -- opening
an email doesn't skip it. When capped, the newest unprocessed mail is classified first.

`senders_file: senders.csv` (optional, relative to `config.yaml`) names the Tier 0 sender
table: a CSV with `sender` and `verdict` columns, each verdict `unsubscribe`,
`auto-archive` or `keep` (see [`senders.example.csv`](senders.example.csv)). It is
git-ignored. A missing file, an unknown verdict or a sender listed twice stops the run.

When several matched categories have a `move` action, only the first `move` in
`categories:` order runs; a matched category with no `move` does not block a later one.
Every other action runs for every match.

`jev-mail run --dry-run --review <path>` writes one CSV row per email with its decision
source and every category's probability, for tuning thresholds. The path must be
outside the project directory, because the rows hold real subjects.

| Action        | What it does                                   |
| ------------- | ----------------------------------------------- |
| `tag`         | Adds a custom IMAP keyword to the message        |
| `move`        | Moves the message to another folder (creates it if missing) |
| `flag`        | Sets the `\Flagged` (star) system flag           |
| `unflag`      | Clears it                                        |
| `mark_read`   | Sets `\Seen`                                     |
| `mark_unread` | Clears it                                        |
| `webhook`     | `POST`s `{category, probability, subject}` to a URL |

## Three ways to power it

Set **one** of these in `.env` (the wizard writes it for you) -- checked in this order:

| Priority | Env var               | Backend                                   |
| -------- | ---------------------- | ------------------------------------------ |
| 1        | `TYPESAFE_API_KEY`     | TypeSafe's own API, direct                  |
| 2        | `OPENROUTER_API_KEY`   | Via OpenRouter's Decisions endpoint         |
| 3        | `AI_GATEWAY_API_KEY`   | Via Vercel AI Gateway                       |

Or set `jev.provider` in `config.yaml` to pin one explicitly instead of auto-detecting.

> The OpenRouter and TypeSafe-direct paths are live-verified. The Vercel-gateway adapter
> is built from its published docs but not yet tested against a live key -- if it
> breaks for you, `jev_mail/providers/` is the one place to look, and pull
> requests are very welcome.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## License

MIT -- see [LICENSE](LICENSE).
