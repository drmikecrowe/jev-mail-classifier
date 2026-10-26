Gortex MCP integration failure. I could not build the context pack, so I am not emitting a record.

The brief at /tmp/gh-hotfix/brief.md read fine. Every read of the repository tree was blocked by the Gortex hook:
- Glob on `**/*.py` was blocked.
- Read of /home/mcrowe/Programming/AI/jev-mail-classifier/jev_mail/cli.py was blocked.
- Grep for `ProviderError|_process_unprocessed` was blocked.

The hook says to use the Gortex `explore`, `read` and `search` tools. My tool list holds only Read, Grep, Glob and SubagentHandback, so those tools are not callable here. The Gortex rules say to report this and stop, with no CLI or shell fallback, so I stopped.

A pack built without reading the tree would name paths I have not confirmed exist. Per the brief, `likely_touched` must name only paths that exist.

The brief and CLAUDE.md point to these likely targets, but I have not verified any of them:
- jev_mail/cli.py (`_process_unprocessed`)
- jev_mail/providers/ (where `ProviderError` is defined)
- CLAUDE.md (the line saying only the OpenRouter adapter is verified)
- tests/

To proceed, either:
- spawn me with the Gortex tools exposed, or
- allow native Read, Grep and Glob for this run.
