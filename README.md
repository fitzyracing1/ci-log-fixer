# ci-log-fixer

Read a failing GitHub Actions log, name the common cause, and suggest a concrete fix.

This helper is **rule-based** (no AI, no extra dependencies, offline). You paste or pipe a job log; it prints a report of every matched cause. The original log is never overwritten.

Related tools: [spin-software-ci](https://github.com/fitzyracing1/spin-software-ci), [ci-doctor](https://github.com/fitzyracing1/ci-doctor), [darks](https://github.com/fitzyracing1/darks), [fakegreen](https://github.com/fitzyracing1/fakegreen). Sponsor: [github.com/sponsors/fitzyracing1](https://github.com/sponsors/fitzyracing1).

## Install

```bash
pipx install git+https://github.com/fitzyracing1/ci-log-fixer
```

Or from a checkout:

```bash
pip install -e .
```

## Usage

```bash
ci-log-fixer job.log
python -m ci_log_fixer job.log
ci-log-fixer - < job.log
```

Write the report to `job.tidy.txt` (the log is not changed):

```bash
ci-log-fixer --write job.log
```

The process exits `1` when at least one cause is found, and `0` when nothing matched.

## What it detects

| Rule | Looks for | Suggested fix |
|------|-----------|----------------|
| `missing-module` | `ModuleNotFoundError`, `Cannot find module` | Declare and install the missing package |
| `version-mismatch` | Node engine errors, unsupported Python | Pin `setup-node` / `setup-python` to a matching version |
| `deprecated-action` | Node 16/20 action warnings, `::set-output` | Bump official actions; use `$GITHUB_OUTPUT` |
| `permission-denied` | `EACCES`, `Resource not accessible by integration` | Grant the missing `permissions:` or fix file modes |
| `lockfile-mismatch` | `npm ci` out of sync with `package-lock.json` | Refresh and commit the lockfile |
| `test-failure` | pytest/Jest/Go failures with `file:line` | Open that location and fix the assertion |
| `timeout` | Timed out or cancelled jobs | Check hangs; then consider `timeout-minutes` |
| `oom` | `Killed`, `MemoryError`, exit 137 | Cut parallelism or use a larger runner |
| `rate-limit` | HTTP 429, Docker/GitHub pull rate limits | Authenticate and cache downloads |
| `network-fetch` | 403/404 on curl, npm, or other fetches | Check the URL, package name, and token |

Sample logs used in the tests live in `tests/samples/` and were written for this project.

## License

MIT. Copyright (c) 2026 Joshua Almeida (fitzyracing1).
