# Gate 1a, spec readiness

verdict: not-ready
story: GH-8
process: spec-evidence 0.16.2
model: claude-opus-5-5,claude-sonnet-5-5
tokens: 48006/1164
record: work/spec-record.json
graded: 2026-10-26T02:08:52.436Z

## Reasons

- finding 1: PR-REFERENT: State the fact in the plan itself (fetch_unprocessed returns newest first and the failing email is never marked, so it is fetched first again) and drop the pointer to GH-2 decisions.md fact 11.

## Record

```json
{"input":"Plan","gaps":["prompt 3: An implementer cannot see GH-2 `decisions.md` fact 11, so the claim that the failing email is retried first on every run rests on a file the plan does not carry.","prompt 3: M3 says only \"a new test\" and gives no input or expected output, so the implementer must invent the startup-failure case (which fake, which stderr text, which exit code assertion)."],"deferred":[],"findings":[{"rule":"PR-REFERENT","quote":"the next run fails on the same email again (GH-2 `decisions.md` fact 11)","smallest_fix":"State the fact in the plan itself (fetch_unprocessed returns newest first and the failing email is never marked, so it is fetched first again) and drop the pointer to GH-2 decisions.md fact 11."}]}
```
