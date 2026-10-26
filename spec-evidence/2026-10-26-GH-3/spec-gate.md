# Gate 1a, spec readiness

verdict: not-ready
story: GH-3
process: spec-evidence 0.16.2
model: claude-opus-5-5,claude-sonnet-5-5
tokens: 85709/1328
record: work/spec-record.json
graded: 2026-10-26T13:01:53.812Z

## Reasons

- finding 1: PR-REFERENT: Replace 'the A9 order' with the order written out: BILLING, ACTION, PERSONAL, MONITOR, BULK. Do the same for 'A10, A11' in Known limits by stating the decisions they point to, because the plan never defines A9, A10 or A11.

## Record

```json
{"input":"Plan","gaps":["prompt 3: Where Tier 0 and `--review` meet `cmd_watch`, the plan only says it loads the table, so an implementer could read it as also writing review rows or leave the watch path untested.","prompt 3: S3.5 says only the first matched `move` in config order runs, but it does not say whether a skipped `move` still appears as a state-row action or a dry-run line for the second category."],"deferred":[],"findings":[{"rule":"PR-REFERENT","quote":"replace `invoice`, `urgent` and `spam` with the five categories in the A9 order","smallest_fix":"Replace 'the A9 order' with the order written out: BILLING, ACTION, PERSONAL, MONITOR, BULK. Do the same for 'A10, A11' in Known limits by stating the decisions they point to, because the plan never defines A9, A10 or A11."}]}
```
