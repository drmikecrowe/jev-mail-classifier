# Gate 1a, spec readiness

verdict: not-ready
story: GH-1
process: spec-evidence 0.16.2
model: claude-sonnet-5-5
tokens: 48109/1349
record: work/spec-record.json
graded: 2026-10-25T15:40:13.569Z

## Reasons

- finding 1: PR-REFERENT: State what Decide 1 and Decide 2 each decided, in a sentence each, or drop the references. The plan defines neither.
- finding 2: PR-REFERENT: Define Phase 1 and the SQLite-only processed set in the Definitions section, or replace the sentence with the literal text the record must hold.
- finding 3: PR-CONTEXT: Restate in the plan the brief's constraint that allows one transport-level config change. A builder without the issue text cannot check that boundary.

## Record

```json
{"input":"Plan","gaps":["prompt 3: S1.6 says the pilot 'walks the credentials screen' without saying what to enter or press, so an implementer could build the walk-through several ways.","prompt 3: S2.2 says a `rejected` record 'states that Phase 1 needs a SQLite-only processed set', but the plan never says what Phase 1 is, so the implementer cannot tell what the follow-up work is."],"deferred":[],"findings":[{"rule":"PR-REFERENT","quote":"Decide 1, `tls_ca_file`, governs S1.1, S1.4 and the Touches entry for `jev_mail/config.py` (Mike Crowe, 2026-10-25). Decide 2, dry-run, governs S2.3","smallest_fix":"State what Decide 1 and Decide 2 each decided, in a sentence each, or drop the references. The plan defines neither."},{"rule":"PR-REFERENT","quote":"A `rejected` record also states that Phase 1 needs a SQLite-only processed set.","smallest_fix":"Define Phase 1 and the SQLite-only processed set in the Definitions section, or replace the sentence with the literal text the record must hold."},{"rule":"PR-CONTEXT","quote":"Brief: issue GH-1, \"Goal / Steps / Check / Note\". ... the brief allows one transport-level config change.","smallest_fix":"Restate in the plan the brief's constraint that allows one transport-level config change. A builder without the issue text cannot check that boundary."}]}
```
