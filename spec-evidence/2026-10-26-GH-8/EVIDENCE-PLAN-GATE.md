# Gate 2a, evidence against the plan

verdict: ready
story: GH-8
process: spec-evidence 0.16.2
model: claude-sonnet-5-5
tokens: 82995/1657
record: work/evidence-plan-record.json
graded: 2026-10-26T10:47:56.693Z

## Reasons

none

## Record

```json
{"gaps":["S4.1 cites README.md:218 to :219, but the note runs to line 221. The cited lines hold the live-verified and not-yet-tested wording, so this does not change the grade.","I did not open tests/test_cli.py. The test ids come from the mapping rows, and the gauntlet `tests` layer (107 passed) is the report's proof that they pass."],"items":[{"scenario":"S1.1","status":"proven","evidence":"test tests/test_cli.py::test_failing_email_is_reported_and_the_next_is_processed, mapping row S1.1, gauntlet tests layer"},{"scenario":"S1.2","status":"proven","evidence":"test tests/test_cli.py::test_failing_email_gets_no_state_row, mapping row S1.2"},{"scenario":"S1.3","status":"proven","evidence":"test tests/test_cli.py::test_dry_run_reports_failing_email_and_prints_the_others, mapping row S1.3"},{"scenario":"S1.4","status":"proven","evidence":"test tests/test_cli.py::test_no_failure_returns_zero, mapping row S1.4"},{"scenario":"S2.1","status":"proven","evidence":"test tests/test_cli.py::test_run_exits_1_when_an_email_failed, mapping row S2.1"},{"scenario":"S2.2","status":"proven","evidence":"test tests/test_cli.py::test_run_finishes_every_account_before_exiting_1, mapping row S2.2"},{"scenario":"S2.3","status":"proven","evidence":"test tests/test_cli.py::test_run_exits_0_when_nothing_failed, with a break check by mutant, mapping row S2.3"},{"scenario":"S3.1","status":"proven","evidence":"test tests/test_cli.py::test_watch_keeps_going_after_a_failing_email, mapping row S3.1"},{"scenario":"S4.1","status":"proven","evidence":"CLAUDE.md:36 reads \"The OpenRouter and TypeSafe-direct adapters are verified against a live key. The Vercel adapter is built from docs only.\" and no longer holds \"Only the OpenRouter adapter is verified\". README.md:218-219 reads \"The OpenRouter and TypeSafe-direct paths are live-verified. The Vercel-gateway adapter is built from its published docs but not yet tested against a live key\"."}],"decisions":[{"id":"A1","status":"complete"},{"id":"A2","status":"complete"},{"id":"A3","status":"complete"},{"id":"A4","status":"complete"}]}
```
