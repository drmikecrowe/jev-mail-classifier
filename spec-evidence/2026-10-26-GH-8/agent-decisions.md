# Agent decisions: GH-8 one ProviderError on one email aborts the whole run

### A1. `_process_unprocessed` returns the count of failing emails

- Other option: return the list of failing UIDs, or raise one aggregate exception after the loop.
- Why: `cmd_run` needs only "did any fail"; a count is the smallest return, and the existing callers that ignore the return keep working.
- Command: hotfix

### A2. The error line goes to stderr

- Other option: print it to stdout, beside the dry-run lines.
- Why: every other `error:` in `cli.py` goes to stderr, and stdout keeps only dry-run lines, so GH-2's byte-identical dry-run check still holds.
- Command: hotfix

### A3. Only `ProviderError` is caught per email

- Other option: catch every `Exception` per email.
- Why: the brief names `ProviderError`; a broader catch would hide real bugs, such as a failing action or a state write, behind one stderr line.
- Command: hotfix

### A4. `run` exits 1 for a partial failure, the same code as every other error

- Other option: a distinct exit code, for example 2, for "some emails failed".
- Why: one nonzero code is what a cron wrapper checks, and the error lines already say which emails failed.
- Command: hotfix
