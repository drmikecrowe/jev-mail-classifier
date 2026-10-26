# Gate 2a, evidence against the plan

verdict: ready
story: GH-2
process: spec-evidence 0.16.2
model: claude-opus-5-5,claude-sonnet-5-5
tokens: 60743/2153
record: work/evidence-plan-record.json
graded: 2026-10-26T01:36:36.082Z

## Reasons

none

## Record

```json
{"gaps":["S4.1 and S5.2 rest on the report's own account of a diff reading and a live run, not on a test id. I could not re-run either. The SPEC's verification contract names 'diff reading' and 'live run' as layers, so I graded both proven."],"items":[{"scenario":"S1.1","status":"proven","evidence":"tests/test_package.py::test_mailbox_package_keeps_every_import, mapping row S1.1"},{"scenario":"S1.2","status":"proven","evidence":"tests/test_package.py::test_mail_backend_names_the_pipeline_methods_and_not_idle"},{"scenario":"S1.3","status":"proven","evidence":"tests/test_actions.py::test_run_action_drives_any_mail_backend"},{"scenario":"S1.4","status":"proven","evidence":"tests/test_mailbox.py::test_fetch_unprocessed_reads_message_id_sender_and_list_unsubscribe"},{"scenario":"S1.5","status":"proven","evidence":"tests/test_mailbox.py::test_missing_headers_are_empty_strings"},{"scenario":"S2.1","status":"proven","evidence":"tests/test_config.py::test_mailbox_form_loads_as_one_account"},{"scenario":"S2.2","status":"proven","evidence":"tests/test_config.py::test_accounts_list_loads_every_account"},{"scenario":"S2.3","status":"proven","evidence":"tests/test_config.py::test_mailbox_and_accounts_together_is_refused"},{"scenario":"S2.4","status":"proven","evidence":"tests/test_config.py::test_empty_or_invalid_accounts_is_refused (2 cases); test_malformed_accounts_is_refused (3 cases)"},{"scenario":"S2.5","status":"proven","evidence":"tests/test_config.py::test_one_account_saves_exactly_as_before, expected text captured at e393a22"},{"scenario":"S2.6","status":"proven","evidence":"tests/test_config.py::test_wizard_edit_keeps_other_accounts_as_written"},{"scenario":"S3.1","status":"proven","evidence":"tests/test_cli.py::test_real_run_marks_processed_then_writes_one_state_row"},{"scenario":"S3.2","status":"proven","evidence":"tests/test_cli.py::test_dry_run_marks_nothing_and_creates_no_state_db"},{"scenario":"S3.3","status":"proven","evidence":"tests/test_cli.py::test_run_processes_each_account_in_turn"},{"scenario":"S3.4","status":"proven","evidence":"tests/test_cli.py::test_watch_refuses_more_than_one_account"},{"scenario":"S3.5","status":"proven","evidence":"tests/test_state.py::test_missing_message_id_is_stored_as_uid"},{"scenario":"S3.6","status":"proven","evidence":"tests/test_state.py::test_recording_the_same_email_again_replaces_its_row"},{"scenario":"S4.1","status":"proven","evidence":"diff reading layer: git diff -M e393a22 on mailbox.py and imap.py, 88% similarity, changed lines listed; tests/test_mailbox.py shows 3 removed lines, the patch targets"},{"scenario":"S5.1","status":"proven","evidence":"tests/test_cli.py::test_dry_run_output_is_unchanged, run on the branch and against the e393a22 worktree"},{"scenario":"S5.2","status":"proven","evidence":"live run layer: e393a22 exit 1 with cause max_tokens_exceeded; branch exit 0, 5 dry-run lines and 1 cap notice, unprocessed 5238 before and after, no state.db; counts only"},{"scenario":"S6.1","status":"proven","evidence":"tests/test_mailbox.py::test_state_sends_at_most_20000_body_characters"},{"scenario":"S6.2","status":"proven","evidence":"tests/test_mailbox.py::test_state_keeps_a_body_of_exactly_20000_characters"}],"decisions":[{"id":"A1","status":"complete"},{"id":"A2","status":"complete"},{"id":"A3","status":"complete"},{"id":"A4","status":"complete"},{"id":"A5","status":"complete"},{"id":"A6","status":"complete"},{"id":"A7","status":"complete"},{"id":"A8","status":"complete"}]}
```
