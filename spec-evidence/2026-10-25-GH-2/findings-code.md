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
