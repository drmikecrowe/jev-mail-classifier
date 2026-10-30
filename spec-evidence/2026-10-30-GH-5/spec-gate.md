# Gate 1a, spec readiness

verdict: not-ready
story: GH-5
process: spec-evidence 0.18.0
model: claude-sonnet-5-5
tokens: 54949/2201
record: work/spec-record.json
graded: 2026-10-30T20:13:42.875Z

## Reasons

- finding 1: PR-SCOPE: Name the acceptance criterion that S4.3's `ConfigError` refusal serves, or drop S4.3 and its Known-limits line.

## Record

```json
{"input":"Plan","gaps":["prompt 2: S4.3 refuses an `o365` account whose `folder` is not the Inbox, and no acceptance criterion asks for that refusal.","prompt 3: \"complete fetch\" in \"The cursor\" says the cursor stays when the walk ended \"because the cap was reached\", but not what happens when the last page ends with exactly `max_emails_per_run` eligible messages, so an implementer could treat that fetch as complete or as capped."],"deferred":[{"ac":"AC-3","heading":"The cursor"},{"ac":"AC-4","heading":"The cursor"}],"findings":[{"rule":"PR-SCOPE","quote":"The story names the Inbox (AC-3) and does not ask for this refusal; it is added so that a `folder` key is never silently ignored.","smallest_fix":"Name the acceptance criterion that S4.3's `ConfigError` refusal serves, or drop S4.3 and its Known-limits line."}]}
```
