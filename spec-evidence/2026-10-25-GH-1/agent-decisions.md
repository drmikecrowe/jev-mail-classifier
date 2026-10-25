### A1. The configure wizard carries `tls` and `tls_ca_file` through unchanged, with no new widget

- Other option: add a select for `tls` and an input for `tls_ca_file` to the mailbox screen.
- Why: the brief allows one transport-level change and asks for no wizard work; carrying the values through stops a save from erasing them, at the cost of editing `config.yaml` by hand.
- Command: hotfix

### A2. `tls_ca_file` is read only in `starttls` mode

- Other option: pass the same context to `IMAPClient(ssl_context=...)` in `ssl` mode too.
- Why: only Bridge, which uses STARTTLS, needs a custom certificate in this phase; the `ssl` path stays exactly as it is at `469c7a2`.
- Command: hotfix

### A3. The live runs use folder INBOX with `max_emails_per_run: 5`

- Other option: another folder, or the default cap of 25.
- Why: the engineer named no folder; a cap of 5 bounds provider cost on a 5238-mail folder, and a dry run never marks mail, so every rerun bills again.
- Command: build

### A4. S2.2 probes the newest UID in the folder

- Other option: any other UID the engineer picks.
- Why: the newest UID is a deterministic pick that needs no subject read; the probe removes the keyword in a `finally`, so the pick leaves no trace.
- Command: build

### A5. S2.1's line-shape rule was revised instead of rerunning with no cap

- Other option: raise the cap above 5238 so the cap notice never prints, and keep the single-quote wording.
- Why: the old wording also rejects any subject that holds an apostrophe, which the CLI prints double-quoted, so no rerun could pass it; classifying every mail costs one provider call each for no added proof.
- Command: build
