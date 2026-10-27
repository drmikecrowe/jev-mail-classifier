# Gate 1a, spec readiness

verdict: not-ready
story: GH-4
process: spec-evidence 0.18.0
model: claude-sonnet-5-5
tokens: 48522/1537
record: work/spec-record.json
graded: 2026-10-27T21:29:36.519Z

## Reasons

- finding 1: PR-READINGS: Add one boundary scenario for `move` to a label that is not in the label list. State whether it creates the label (as S2.2 does for `tag`) or raises an error, and give the expected `labels().create` and `modify` calls.

## Record

```json
{"input":"Plan","gaps":["prompt 3: S2.3 does not say what `move` does when the target label does not exist yet (create it, as `tag` does, or raise an error), so two builders would write different code."],"deferred":[],"findings":[{"rule":"PR-READINGS","quote":"Given labels `INBOX` and `{\"id\": \"Label_3\", \"name\": \"Receipts\"}`, when `move(\"b2\", \"Receipts\")` runs, then `modify` is called with `body={\"addLabelIds\": [\"Label_3\"], \"removeLabelIds\": [\"INBOX\"]}`","smallest_fix":"Add one boundary scenario for `move` to a label that is not in the label list. State whether it creates the label (as S2.2 does for `tag`) or raises an error, and give the expected `labels().create` and `modify` calls."}]}
```
