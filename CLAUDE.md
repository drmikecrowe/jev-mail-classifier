# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## PUBLIC REPOSITORY: review every commit

`origin` (drmikecrowe/jev-mail-classifier) is a **public** GitHub fork. Everything committed or pushed, including issue and PR text, is world-readable and permanent in history.

- Before every commit, show the user the full staged diff (`git diff --cached`) and get an explicit yes. Never commit or push unreviewed.
- Never commit secrets, tokens, or personal mail data: `.env`, `config.yaml`, `state.db`, MSAL/OAuth token caches, `senders.csv`, `sender-census.csv`, real email addresses, subjects, or bodies. Test fixtures use fake addresses (`example.com`).
- New local data files get a `.gitignore` entry in the same commit that introduces the code that writes them.
- Run `git status --short` and check for untracked data files before staging. Stage files by name, never `git add -A` or `git add .`.

## Commands

```bash
mise exec -- uv sync --extra dev                             # dev setup into .venv (uv is not on PATH directly)
mise exec -- uv run pytest                                   # all tests
mise exec -- uv run pytest tests/test_config.py::test_name   # one test
./jev-mail run --dry-run                                     # classify without touching the mailbox
./jev-mail configure | run | watch                           # TUI wizard / one pass / IMAP IDLE loop
```

`mise.toml` pins Python 3.14 and activates `.venv` on `cd`, so in an interactive shell `pytest` and `jev-mail` resolve directly. `install.sh` and the README use plain `pip` + venv for end users; leave them as they are. `./jev-mail` is a bash wrapper that execs `.venv/bin/jev-mail --dir <repo>`, so `config.yaml` and `.env` always resolve to the repo root. With no subcommand, the CLI runs `configure` if `config.yaml` is missing, otherwise `run`. There is no linter or formatter configured. Pytest runs with `asyncio_mode = "auto"`, so async tests need no decorator.

## Architecture

Pipeline per email (`jev_mail/cli.py::_process_unprocessed`):

1. `Mailbox.fetch_unprocessed` (`jev_mail/mailbox/imap.py`, behind the `MailBackend` Protocol in `jev_mail/mailbox/base.py`) searches IMAP for `UNKEYWORD $JevProcessed`, newest first, capped at the account's `max_emails_per_run`. "Unprocessed" is the keyword, not `\Seen`. The keyword is the source of truth; `state.db` (`state.py`, beside `config.yaml`) is a local record written after each keyword, and nothing reads it yet.
2. `classify` (`classify.py`) sends every category to Jev in a **single** `decide()` call. Each category is an independent yes/no ("noul") question, so results are multi-label.
3. `matched_categories` compares each probability against the category's `threshold`, falling back to `jev.default_threshold`.
4. `run_action` (`actions.py`) dispatches on `Action.type` to `Mailbox` primitives or an `httpx.post` webhook.
5. The email is marked `$JevProcessed` even when nothing matched, so it is never re-billed. `--dry-run` skips both actions and marking.

**Providers** (`jev_mail/providers/`): `JevClient` is a Protocol with one method, `decide(state, {name: description}) -> {name: probability}`. `get_jev_client` picks a backend from the `_BACKENDS` tuple, in priority order `TYPESAFE_API_KEY` > `OPENROUTER_API_KEY` > `AI_GATEWAY_API_KEY`, unless `jev.provider` pins one. Shared helpers in `base.py` build the questions payload (`build_noul_questions`) and normalize answers (`extract_probabilities` accepts either a `noul` or a `boolean` key, because Vercel answers with `boolean`). Only the OpenRouter adapter is verified against a live key. The TypeSafe-direct and Vercel adapters are built from docs only.

**Config** (`config.py`): plain dataclasses (`AppConfig`, `MailboxConfig`, `JevSettings`, `Category`, `Action`). Valid action types are in `ACTION_TYPES`. Adding an action type means updating `ACTION_TYPES`, `Action.to_dict`, `run_action`, and the category edit screen's checklist.
- Secrets live only in `.env` (git-ignored). `config.yaml` refers to them as `${VAR}`. `load_config` loads `.env` with `override=False`, so real environment variables win.
- `${VAR}` interpolation is applied only to `mailbox.host`, `username`, and `password`. Action fields (for example a webhook `url`) are not interpolated.
- `save_config` always writes `${IMAP_USERNAME}` / `${IMAP_PASSWORD}`, never the literal values.
- `config.yaml` holds either one `mailbox:` block or an `accounts:` list, never both. `AppConfig.mailbox` is the first account; accounts 2 to n are written back from their raw entries. `run` processes each account in turn; `watch` refuses more than one.
- `save_env` merges: an empty value **deletes** that key. The credentials screen pre-fills from the existing `.env`, so a cleared field means "remove it".

**TUI** (`jev_mail/tui/`, Textual): `JevMailConfigApp` chains three screens: Credentials (writes `.env`, has a "Test key" button) -> Mailbox -> Categories (with `CategoryEditScreen` as a modal). Each screen dismisses with its data, and callbacks on the app (`_after_credentials`, `_after_mailbox`, `_after_categories`) wire it into `self.config` before `save_config`. All CSS lives in the `CSS` string in `app.py`.

## Testing conventions

- IMAP: inject a `MagicMock` as `Mailbox(config, server=fake_server)`. There is no real network.
- Providers: `monkeypatch` the client's `httpx.post` with a fake that returns `httpx.Response(..., request=httpx.Request(...))`.
- TUI: async tests drive `JevMailConfigApp(tmp_path / "config.yaml", tmp_path / ".env")` through Textual's `run_test()` pilot, then assert on the files it wrote.
