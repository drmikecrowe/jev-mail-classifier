{
  "clean_claims": [
    "jev_mail/mailbox/graph.py fetch_unprocessed cap and cursor arithmetic. I traced the 30-message, cap-25 case, an exact-cap page, a break in the middle of a page, and a ProviderError leaving a uid in pending. The cursor stays correct in each.",
    "jev_mail/cli.py:46-107 and :170-176. State is created before the first fetch on a real run and in watch, so GraphMailbox._open_state finds state.db. mark_processed runs before state.record, and a classify failure `continue`s without marking.",
    "jev_mail/mailbox/graph.py _message_path quoting, _folder_id quote escaping ('' doubling), and _write_token reuse (gmail.py:163-168 does set 0600 on every write).",
    "jev_mail/state.py: the new cursor table is created with IF NOT EXISTS and the processed table is untouched."
  ],
  "finding": [
    {
      "file": "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/graph.py",
      "line": 332,
      "severity": "advisory",
      "rule": "none",
      "defect": "A dry run can still write the cursor to state.db. SPEC 'The cursor' states that a dry run never moves it. GraphMailbox opens state.db itself whenever the file exists, and a complete fetch that finds no eligible mail leaves pending = (newest, empty set). _advance_cursor then writes it on the next fetch or at __exit__.",
      "trigger": "state.db exists, every Inbox message is already processed, and the user runs `run --dry-run`.",
      "consequence": "A write to state.db happens during a dry run. The written cursor is semantically safe, because everything the fetch saw was already processed. The documented 'dry run adds neither' guarantee and the SPEC statement are false, and no test covers a dry run with zero eligible mail."
    },
    {
      "file": "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/graph.py",
      "line": 392,
      "severity": "advisory",
      "rule": "none",
      "defect": "Token-path errors outside GraphError are not handled. cache.deserialize(token.read_text()) raises ValueError on a corrupt or truncated o365-token.json. The same happens in authorize_o365 at line 422 and in msal.initiate_device_flow. cli catches only OSError, IMAP4.error, ConfigError, GmailError and GraphError.",
      "trigger": "o365-token.json holds invalid JSON, for example after an interrupted write (_write_token uses O_TRUNC, so it is not atomic).",
      "consequence": "`run`, `watch` and `auth-o365` end in a raw traceback instead of 'run auth-o365'. For `run` and `watch`, the AC-2 promise of an error that names auth-o365 does not hold."
    },
    {
      "file": "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/cli.py",
      "line": 125,
      "severity": "advisory",
      "rule": "none",
      "defect": "msal reaches the network through `requests`. A network failure inside acquire_token_silent_with_error (graph.py:400) surfaces as requests.ConnectionError, which is an OSError, not a GraphError. cli's OSError branch then prints 'couldn't connect to graph.microsoft.com:993', and 993 is the IMAP default port from MailboxConfig.",
      "trigger": "The network is down or DNS fails at token renewal.",
      "consequence": "The message names a wrong port that has nothing to do with Graph. It points the user at IMAP settings instead of the connection. No test covers it."
    }
  ],
  "hunch": [
    {
      "file": "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/graph.py",
      "line": 395,
      "rule": "none",
      "defect": "The MSAL account is matched by comparing the cached `username` (the UPN) to config.username. The mailbox's primary email address can differ from the UPN, for example under an alias or a mail-nickname change.",
      "consequence": "If the two differ, the account lookup fails with 'no sign-in for X -- run auth-o365' even right after a successful auth-o365. It looks like a loop. I could not confirm how often the UPN differs from the address in the target tenant."
    },
    {
      "file": "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/graph.py",
      "line": 342,
      "rule": "none",
      "defect": "_is_processed skips a message when state.db holds a row for the same internetMessageId. Two different Inbox messages that share a Message-ID (for example a list copy and a direct copy) mean the second is never fetched and never gets the JevProcessed category.",
      "consequence": "A silently unclassified duplicate. The IMAP path keys state rows the same way, so this may be accepted behavior."
    }
  ],
  "coverage": {
    "calls_used": "3/10",
    "hunts_not_reached": [
      "6 (invariants in surrounding code, only partly read)",
      "8 (no EVIDENCE report in the diff)",
      "9 (not checked: msal API names such as has_state_changed and acquire_token_silent_with_error against the pinned 1.39.0)",
      "10 (the SPEC Documentation section names README.md and CLAUDE.md, and both are in the diff)"
    ],
    "sites_not_opened": [
      "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/config.py:170 (whether an o365 account with an empty username is refused)",
      "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/actions.py (callers of add_tag, move, set_flag, set_seen)",
      "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/base.py (Protocol signatures versus GraphMailbox)"
    ]
  }
}
{
  "clean_claims": [
    "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/graph.py fetch_unprocessed and cursor logic: I traced the capped, dry-run, failed-email and empty-fetch paths and found no way for the cursor to skip an unmarked message",
    "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/state.py State.record, has, cursor and set_cursor: the key used (message_id or uid:<id>) matches the key GraphMailbox._is_processed builds",
    "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/cli.py lines 110-125 and 167-210: the call sites that open a GraphMailbox catch GraphError and ConfigError, and State is created after __enter__ and before fetch, so the state.db existence check in _open_state holds on a first run"
  ],
  "finding": [],
  "hunch": [
    {
      "file": "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/graph.py",
      "line": 68,
      "rule": "none",
      "defect": "__exit__ calls _advance_cursor, which runs a sqlite write (set_cursor). A sqlite3.Error there is not a GraphError or OSError, so the cli handlers do not catch it. It would also replace any exception already propagating out of the with-block.",
      "consequence": "A locked or read-only state.db at shutdown would crash the run with a traceback and hide the original error."
    },
    {
      "file": "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/graph.py",
      "line": 84,
      "rule": "none",
      "defect": "@odata.nextLink is passed straight to the client with the Bearer token attached, and the host is not checked.",
      "consequence": "Only a hostile or compromised Graph response could point it elsewhere, which would leak the token. The risk is low."
    },
    {
      "file": "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/graph.py",
      "line": 93,
      "rule": "none",
      "defect": "A capped fetch never moves the cursor. With max_emails_per_run set, every run pages from the old cursor through all the already-processed newest mail before it reaches unprocessed items.",
      "consequence": "Slow runs and many Graph requests on a large backlog. Results stay correct."
    }
  ],
  "coverage": {
    "calls_used": "4/10",
    "hunts_not_reached": [
      "1 (no merge gate exists, so there was nothing to compare)",
      "8 (I did not read the EVIDENCE report)",
      "10 (I did not check the SPEC's Documentation section)"
    ],
    "sites_not_opened": [
      "/home/mcrowe/Programming/AI/jev-mail-classifier/tests/test_graph.py",
      "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/config.py:160-180 (the o365 validation, only seen through grep)",
      "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/mailbox/gmail.py (_write_token, which graph.py imports)",
      "/home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/tui (whether the config wizard preserves backend: o365)",
      "/home/mcrowe/Programming/AI/jev-mail-classifier/spec-evidence/2026-10-30-GH-5/work/diff.txt (too large to read whole; I read the HEAD source instead)"
    ]
  }
}
