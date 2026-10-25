### A1. The configure wizard carries `tls` and `tls_ca_file` through unchanged, with no new widget

- Other option: add a select for `tls` and an input for `tls_ca_file` to the mailbox screen.
- Why: the brief allows one transport-level change and asks for no wizard work; carrying the values through stops a save from erasing them, at the cost of editing `config.yaml` by hand.
- Command: hotfix

### A2. `tls_ca_file` is read only in `starttls` mode

- Other option: pass the same context to `IMAPClient(ssl_context=...)` in `ssl` mode too.
- Why: only Bridge, which uses STARTTLS, needs a custom certificate in this phase; the `ssl` path stays exactly as it is at `469c7a2`.
- Command: hotfix
