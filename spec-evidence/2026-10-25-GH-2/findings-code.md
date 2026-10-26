## Round 1 (read e393a22...6e57a47)

{
  "clean_claims": [
    "jev_mail/mailbox/base.py and __init__.py: Email field order keeps keyword construction, Protocol lists the six pipeline methods and no IDLE methods (read in diff only)",
    "tests/test_state.py, tests/test_package.py: scenarios S3.5, S3.6, S1.1, S1.2 map to assertions (read in diff only)",
    "cmd_watch single-account guard and the dry-run branch of _process_unprocessed: no state write on dry run (read in diff only)"
  ],
  "finding": [
    {
      "file": "jev_mail/config.py",
      "line": 110,
      "severity": "advisory",
      "rule": "none",
      "defect": "The accounts: branch passes each raw entry straight to _load_account, which calls .get on it, with no type check on the list or its entries.",
      "trigger": "config.yaml with `accounts:` as a mapping, or a list holding a string or a null entry (`accounts:\\n  -`).",
      "consequence": "An AttributeError traceback escapes load_config. cmd_run and cmd_watch catch only ConfigError and ProviderError, so the user gets a crash instead of an `accounts[i]` message. The new multi-account parser has no negative test for malformed entries."
    },
    {
      "file": "jev_mail/cli.py",
      "line": 63,
      "severity": "advisory",
      "rule": "none",
      "defect": "state.record runs after mark_processed with no sqlite3.Error handling, and State(...) is built inside the try that catches only OSError and imaplib errors.",
      "trigger": "state.db is locked, read-only or corrupt, or the directory is unwritable.",
      "consequence": "A raw sqlite3 traceback aborts the run, and in `run` every remaining account is skipped. The SPEC records this as A5 and a known limit, so it is a design choice. The message is not user-readable, and sqlite3.OperationalError is not an OSError. No test covers a failing state write."
    },
    {
      "file": "jev_mail/cli.py",
      "line": 54,
      "severity": "advisory",
      "rule": "none",
      "defect": "The `applied` list stores action.to_dict() verbatim, so webhook action URLs are written into state.db.",
      "trigger": "A category with a webhook action whose URL carries a token or secret path.",
      "consequence": "State rows hold secrets in a local file. CLAUDE.md says secrets live only in .env and action URLs are not interpolated. state.db is gitignored, but it is a new plaintext copy of the URL. The SPEC does not address it."
    }
  ],
  "hunch": [
    {
      "file": "jev_mail/state.py",
      "line": 467,
      "rule": "none",
      "defect": "The `uid:<uid>` fallback key combines with INSERT OR REPLACE. Two Message-ID-less mails with the same UID in different folders of one account (the account key has no folder) overwrite each other's row.",
      "consequence": "Silent loss of a state row. The SPEC lists the key as unique only within one folder, but a replace is silent."
    },
    {
      "file": "jev_mail/config.py",
      "line": 175,
      "rule": "none",
      "defect": "After a wizard save, account 1's credentials become ${IMAP_USERNAME} and ${IMAP_PASSWORD} even when the file named other variables.",
      "consequence": "Account 1 can lose its working credentials if .env lacks those two names. The SPEC lists this under known limits."
    },
    {
      "file": "jev_mail/mailbox/imap.py",
      "line": 108,
      "rule": "none",
      "defect": "A folded Message-ID header (continuation line) is not unfolded, so the key could contain a newline or extra whitespace. I did not verify how email.message_from_bytes handles this.",
      "consequence": "Unstable dedupe key. State rows are never read in this phase."
    }
  ],
  "coverage": {
    "calls_used": "3/10",
    "hunts_not_reached": [
      "2 (callers of changed functions outside the diff: the Grep was blocked by the Gortex hook and I have no Gortex tools; tui/ and classify.py were not opened)",
      "8",
      "9"
    ],
    "sites_not_opened": [
      "jev_mail/tui/app.py",
      "jev_mail/tui/screens/mailbox_screen.py",
      "jev_mail/classify.py",
      "jev_mail/cli.py (cmd_run header, where config_path is defined)",
      "tools/gauntlet-layers.json",
      "spec-evidence/2026-10-25-GH-2/EVIDENCE.md (not in the diff, so hunt 8 was not possible)"
    ]
  }
}

## Round 2 (read e393a22...ca7e032)

{"clean_claims":["/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/base.py and __init__.py: the Protocol has the six pipeline methods and no IDLE methods, and the new Email fields default to empty strings after body (as read in diff.txt)","/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/config.py load_config: the both-keys check, the empty-list check and the non-list/non-dict check all run before any account is built (as read in diff.txt only)","/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/state.py: INSERT OR REPLACE on the (account, message_id) primary key matches S3.6; the uid fallback matches S3.5"],"finding":[{"file":"/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/cli.py","line":99,"severity":"advisory","rule":"none","defect":"cmd_run and cmd_watch catch only OSError and imaplib.IMAP4.error, but the new State(...) constructor and state.record() raise sqlite3.Error, which is not an OSError subclass, so a failure surfaces as a raw traceback.","trigger":"The config directory is read-only, or state.db is locked or corrupt. For example, `run` starts, the first email is processed, mark_processed sets the keyword, and then record() raises sqlite3.OperationalError.","consequence":"The run crashes with a traceback instead of a clean `error:` line and exit code 1. In `run`, later accounts are skipped. The spec's Known limits cover only the failed-write case (a failed record() after the keyword is set), not this unhandled exception class or a failed State() open."}],"hunch":[{"file":"/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/cli.py","line":123,"rule":"none","defect":"The account key is `host/username` and leaves out the folder.","consequence":"Two accounts entries with the same host and user but different folders share one key. Messages without a Message-ID fall back to `uid:N`, so those state rows would overwrite each other through INSERT OR REPLACE."},{"file":"/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/config.py","line":283,"rule":"none","defect":"save_config always rewrites the first account's username and password as ${IMAP_USERNAME} and ${IMAP_PASSWORD}.","consequence":"If account 1 used other variable names (for example ${A_USER}), a wizard save silently repoints it at different variables while accounts 2 to n keep theirs. The spec lists this as a known limit, so it is not a spec violation, but it is silent."}],"coverage":{"calls_used":"4/10","hunts_not_reached":["1 (there is no merge gate, so only the manifest could have been compared)","2 for callers outside the diff: the tui, tests, and any other user of config.mailbox or _mailbox_error_message","4 for input fuzzing of the YAML accounts shapes","9","10"],"sites_not_opened":["/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/tui/app.py (the Gortex hook blocked Grep and Read on indexed source, and I have no Gortex tools, so I could not check how _after_mailbox and other config.mailbox users behave with accounts)","/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/config.py:_interpolate (behaviour with an unset ${VAR} in accounts 2 to n)","/home/mcrowe/Programming/AI/jev-mail-classifier/spec-evidence/2026-10-25-GH-2/work/diff.txt lines 621-1408 (the test diffs and the remaining evidence files were not read)","/home/mcrowe/Programming/AI/jev-mail-classifier/tools/gauntlet-layers.json"]}}
