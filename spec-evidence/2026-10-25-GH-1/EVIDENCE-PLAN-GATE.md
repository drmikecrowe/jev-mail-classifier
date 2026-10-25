# Gate 2a, evidence against the plan

verdict: ready
story: GH-1
process: spec-evidence 0.16.2
model: claude-sonnet-5-5
tokens: 54104/1419
record: work/evidence-plan-record.json
graded: 2026-10-25T21:08:21.774Z

## Reasons

none

## Record

```json
{"gaps":["Test ids were accepted as named in the mapping. I did not open the test files, so I did not check that each test body holds its scenario's Given/When/Then.","The S2.1 to S2.3 live run records were written by the doer from captured output, and no gate re-ran them (the report says so).","The report says the adversary did not review fd261d7. This is outside scenario grading and is noted only."],"items":[{"scenario":"S1.1","status":"proven","evidence":"tests/test_mailbox.py::test_starttls_with_ca_file_upgrades_before_login, mapping row S1.1"},{"scenario":"S1.2","status":"proven","evidence":"tests/test_mailbox.py::test_starttls_without_ca_file_uses_default_context, mapping row S1.2"},{"scenario":"S1.3","status":"proven","evidence":"tests/test_mailbox.py::test_config_without_tls_keys_connects_with_implicit_tls, mapping row S1.3"},{"scenario":"S1.4","status":"proven","evidence":"tests/test_config.py::test_tls_settings_round_trip_through_save_and_load, mapping row S1.4"},{"scenario":"S1.5","status":"proven","evidence":"tests/test_config.py::test_unknown_tls_value_is_rejected, mapping row S1.5"},{"scenario":"S1.6","status":"proven","evidence":"tests/test_tui.py::test_wizard_keeps_hand_set_tls_settings, mapping row S1.6"},{"scenario":"S2.1","status":"proven","evidence":"Live run record S2.1: exit code 0, 6 lines (5 classification lines, 1 cap notice, 0 other), counts 5238/5238 before and after"},{"scenario":"S2.2","status":"proven","evidence":"Live run record S2.2: add and remove raised no error, first read held $JevProcessed, second read did not, outcome 'accepted'"},{"scenario":"S2.3","status":"proven","evidence":"Live run record S2.3: exit code 1, outcome 'fails', error line 'ProviderError: TypeSafe API request failed: 400 Bad Request', count 5238 before and after"}],"decisions":[{"id":"A1","status":"complete"},{"id":"A2","status":"complete"},{"id":"A3","status":"complete"},{"id":"A4","status":"complete"},{"id":"A5","status":"complete"}]}
```
