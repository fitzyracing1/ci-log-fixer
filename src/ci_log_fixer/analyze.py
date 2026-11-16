"""Rule-based analysis of GitHub Actions job logs.

Patterns are informed by fitzyracing1/spin-software-ci, ci-doctor, darks and
fakegreen, but this helper only reads a log (no workflow scan, no network).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    """One matched cause in a log, with a concrete suggested fix."""

    rule: str
    title: str
    evidence: str
    fix: str
    location: str | None = None  # file:line when a test failure names one

    def lines(self) -> list[str]:
        out = [f"[{self.rule}] {self.title}"]
        if self.location:
            out.append(f"  location: {self.location}")
        evidence = self.evidence.strip()
        if evidence:
            clipped = evidence if len(evidence) <= 240 else evidence[:237] + "..."
            out.append(f"  evidence: {clipped}")
        out.append(f"  fix:      {self.fix}")
        return out


@dataclass
class Analysis:
    source: str
    findings: list[Finding] = field(default_factory=list)

    def report(self) -> str:
        lines = [f"ci-log-fixer report for {self.source}"]
        if not self.findings:
            lines.append("No common failure cause matched. The log may be incomplete or already green.")
            lines.append("")
            return "\n".join(lines)
        lines.append(f"Found {len(self.findings)} issue(s):")
        lines.append("")
        for finding in self.findings:
            lines.extend(finding.lines())
            lines.append("")
        return "\n".join(lines)


def _clip_line(line: str) -> str:
    # GitHub Actions timestamps prefix most log lines.
    return re.sub(
        r"^\d{4}-\d{2}-\d{2}T[0-9:.]+Z\s+",
        "",
        line,
    ).rstrip()


def _first_match(pattern: re.Pattern[str], lines: list[str]) -> str | None:
    for raw in lines:
        if pattern.search(raw):
            return _clip_line(raw)
    return None


# file:line locations from common test runners.
_PYTEST_NODE = re.compile(
    r"^(?:E\s+)?(?:FAILED\s+)?(?P<path>[\w./\\-]+\.py)(?::(?P<line>\d+))?(?:::\S+)?"
)
_PYTEST_IN = re.compile(
    r"(?P<path>[\w./\\-]+\.py):(?P<line>\d+)(?::\s|$)"
)
_JEST = re.compile(
    r"\((?P<path>[\w./\\-]+\.(?:js|jsx|ts|tsx|mjs|cjs)):(?P<line>\d+)(?::\d+)?\)"
)
_GO = re.compile(
    r"(?P<path>[\w./\\-]+_test\.go):(?P<line>\d+):"
)
_GENERIC_FAIL = re.compile(
    r"(?P<path>[\w./\\-]+\.(?:py|js|jsx|ts|tsx|go|rb|java|rs)):(?P<line>\d+)"
)


def _test_location(lines: list[str]) -> str | None:
    for raw in lines:
        clipped = _clip_line(raw).strip()
        for pattern in (_PYTEST_IN, _PYTEST_NODE, _JEST, _GO):
            match = pattern.search(clipped)
            if match and match.group("line"):
                return f"{match.group('path')}:{match.group('line')}"
    # Fall back to a generic path:line near an assertion/failure word.
    for raw in lines:
        clipped = _clip_line(raw)
        if re.search(r"FAIL|Error|assert|AssertionError|Error:", clipped, re.I):
            match = _GENERIC_FAIL.search(clipped)
            if match:
                return f"{match.group('path')}:{match.group('line')}"
    return None


def _module_name(evidence: str) -> str | None:
    match = re.search(
        r"No module named ['\"]([^'\"]+)['\"]",
        evidence,
    )
    if match:
        return match.group(1)
    match = re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", evidence)
    if match:
        return match.group(1)
    return None


# Each rule: (id, title, pattern, fix-builder)
# Applied in order; each rule reports at most once (first evidence line).
def _rules() -> list[tuple[str, str, re.Pattern[str], str]]:
    return [
        (
            "missing-module",
            "Missing Python or Node module",
            re.compile(
                r"ModuleNotFoundError|ImportError: No module named|"
                r"Cannot find module ['\"][^'\"]+['\"]|"
                r"npm ERR!.*code ELSPROBLEMS|"
                r"Unable to resolve module",
                re.I,
            ),
            "Add the missing package to your dependency file "
            "(pyproject.toml, requirements.txt, or package.json) and install it "
            "in the workflow before the failing step.",
        ),
        (
            "version-mismatch",
            "Node or Python version mismatch",
            re.compile(
                r"The engine ['\"]node['\"] is incompatible|"
                r"error node@\S+?: The engine|"
                r"This package requires Node\.?js|requires a Node version|"
                r"Current Python version .{0,40}is not (?:supported|compatible)|"
                r"SyntaxError: (?:invalid syntax|future feature|cannot use|'match')|"
                r"EBADENGINE|"
                r"requires Python (?:>=|~=|>)\s*3\.\d",
                re.I,
            ),
            "Pin a matching language version in the workflow "
            "(actions/setup-node or actions/setup-python) and in engines/requires-python.",
        ),
        (
            "deprecated-action",
            "Deprecated action, Node runtime, or workflow command",
            re.compile(
                r"Node\.js 16 (?:actions are deprecated|is deprecated)|"
                r"Node\.js 20 (?:actions are deprecated|is deprecated)|"
                r"The `set-output` command is deprecated|"
                r"::set-output\s+name=|"
                r"deprecated and will be disabled soon|"
                r"Please update the following actions to use Node\.js",
                re.I,
            ),
            "Bump official actions to current majors (checkout@v7, setup-node@v7, "
            "setup-python@v7, cache@v6, upload-artifact@v7, download-artifact@v8) "
            "and replace ::set-output with echo \"name=value\" >> \"$GITHUB_OUTPUT\". "
            "config-tidy can apply those edits.",
        ),
        (
            "permission-denied",
            "Permission denied or GITHUB_TOKEN lacks a scope",
            re.compile(
                r"Permission denied|EACCES|Error: Permission|"
                r"Resource not accessible by integration|"
                r"HTTP 403.*github\.com|"
                r"denied: permission|"
                r"GITHUB_TOKEN.*does not have|lacks permission",
                re.I,
            ),
            "Grant the missing job permission (for example `permissions: contents: write` "
            "or `pull-requests: write`), or chmod the path if a local file is not executable. "
            "Do not widen GITHUB_TOKEN more than the step needs.",
        ),
        (
            "lockfile-mismatch",
            "Lockfile does not match package.json (npm ci)",
            re.compile(
                r"`npm ci` can only install packages when your package\.json and "
                r"package-lock\.json(?: / npm-shrinkwrap\.json)? are in sync|"
                r"npm ERR!.*(cipm|ce.*package-lock)|"
                r"Missing: .* from lock file|"
                r"npm ci.*(?:out of sync|needs a package-lock)|"
                r"yarn.lock is outdated|"
                r"pnpm-lock\.yaml.*out of date|ERR_PNPM_OUTDATED_LOCKFILE|"
                r"poetry\.lock is not consistent",
                re.I,
            ),
            "Reproduce the install locally (`npm install`, `pnpm install`, or `poetry lock`), "
            "commit the updated lockfile, and keep using `npm ci` / `pnpm i --frozen-lockfile` in CI.",
        ),
        (
            "test-failure",
            "A test failed and named a file:line",
            re.compile(
                r"FAILED\s+[\w./\\-]+\.py|"
                r"={3,}\s+\d+\s+failed|"
                r"AssertionError|"
                r"FAIL\s+\S+\.(?:test|spec)\.(?:js|ts|jsx|tsx)|"
                r"--- FAIL:|"
                r"Tests: \d+ failed|"
                r"FAILED tests?/",
                re.I,
            ),
            "Open the reported test location, inspect the assertion, and fix the code or the expectation.",
        ),
        (
            "timeout",
            "Job or step timed out or was cancelled",
            re.compile(
                r"The action has timed out|"
                r"The operation was canceled|"
                r"exited because of timeout|"
                r"##\[error\].*timed out|"
                r"Error: The operation was cancelled|"
                r"cancelled by \w+|job cancelled|"
                r"cancellationToken",
                re.I,
            ),
            "Raise `timeout-minutes` only after checking for a hang or a stuck network call. "
            "If the log ends in 'cancelled', look at a newer run or a concurrency group cancel.",
        ),
        (
            "oom",
            "The runner ran out of memory",
            re.compile(
                r"\bKilled\b|out of memory|MemoryError|"
                r"OSError: \[Errno 12\]|Cannot allocate memory|"
                r"JavaScript heap out of memory|"
                r"FATAL ERROR: Reached heap limit|"
                r"exit code 137",
                re.I,
            ),
            "Cut parallelism (`pytest -n`, webpack workers), add swap only as a last resort, "
            "or move the job to a larger runner.",
        ),
        (
            "rate-limit",
            "API or registry rate limit was hit",
            re.compile(
                r"API rate limit|HTTP 429|toomanyrequests|"
                r"pull rate limit exceeded|"
                r"You have exceeded a secondary rate limit|"
                r"403 Forbidden.*rate limit|"
                r"npm ERR! 429",
                re.I,
            ),
            "Authenticate to the registry or API so the job gets a higher quota, cache downloads, "
            "and avoid unauthenticated GitHub API calls from GITHUB_TOKEN-less scripts.",
        ),
        (
            "network-fetch",
            "Network fetch returned 403 or 404",
            re.compile(
                r"(?:curl|wget|fetch|GET|HTTP).*?\b(403|404)\b|"
                r"\b403 Forbidden\b|\b404 Not Found\b|"
                r"Failed to fetch \S+|"
                r"npm ERR! 404|"
                r"ERROR 403:|ERROR 404:|"
                r"Error: Failed to download|"
                r"The requested URL returned error: 40[34]",
                re.I,
            ),
            "Check the URL, package name, and whether the token or secret used to fetch it is still valid. "
            "A 404 often means a typo or a private package; a 403 often means auth or permissions.",
        ),
    ]


_TEST_RULE = "test-failure"


def analyze(text: str, source: str = "log") -> Analysis:
    """Return every matched cause in *text*, in rule order, each at most once."""
    lines = text.splitlines() or [text]
    findings: list[Finding] = []
    seen: set[str] = set()
    for rule, title, pattern, fix in _rules():
        evidence = _first_match(pattern, lines)
        if evidence is None:
            continue
        if rule in seen:
            continue
        seen.add(rule)
        location = None
        concrete_fix = fix
        if rule == "missing-module":
            name = _module_name(evidence)
            if name:
                concrete_fix = (
                    f"Install and declare `{name}` "
                    "(add it to pyproject.toml / requirements.txt / package.json "
                    "and install it in the workflow before this step)."
                )
        if rule == _TEST_RULE:
            location = _test_location(lines)
            if location:
                concrete_fix = (
                    f"Open {location}, inspect the assertion, "
                    "and fix the code or the expectation."
                )
        findings.append(
            Finding(
                rule=rule,
                title=title,
                evidence=evidence,
                fix=concrete_fix,
                location=location,
            )
        )
    return Analysis(source=source, findings=findings)
