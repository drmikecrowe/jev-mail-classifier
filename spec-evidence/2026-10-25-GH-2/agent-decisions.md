# Agent decisions: GH-2 mail backend interface and persistent state

### A1. The state row's account key is `<host>/<username>`

- Other option: a new `name` field on each account, defaulting to some fixed value for the `mailbox:` form.
- Why: it needs no new config field and stays the same when a `mailbox:` file is rewritten as an `accounts:` list.
- Command: hotfix

### A2. A missing Message-ID is stored as `uid:<uid>`

- Other option: skip the state row for an email with no Message-ID.
- Why: the brief says the row is written alongside every keyword; a stand-in keeps that true, at the cost of a key that is unique only within one folder.
- Command: hotfix

### A3. `state.db` lives in the `--dir` directory, beside `config.yaml`

- Other option: a `state_path` setting in `config.yaml`.
- Why: `./jev-mail` already resolves `config.yaml` and `.env` from `--dir`, and a new setting is a config option nobody asked for.
- Command: hotfix

### A4. `AppConfig` keeps `mailbox` as the first account and adds `extra_accounts`, with an `accounts` property

- Other option: replace `AppConfig.mailbox` with an `accounts` list.
- Why: every existing constructor, the TUI and the tests use `config.mailbox`; keeping it means none of them change.
- Command: hotfix

### A5. A failed state write stops the run

- Other option: catch `sqlite3.Error`, print a warning, and go on.
- Why: a silent gap in the record is worse than a visible stop, and the keyword is already set, so no email is billed twice.
- Command: hotfix

### A6. The decision source written in this phase is `jev`

- Other option: leave `source` empty until Phase 2 adds other sources.
- Why: every decision in this phase comes from the Jev call, and an explicit value lets Phase 2 add others without a migration.
- Command: hotfix
