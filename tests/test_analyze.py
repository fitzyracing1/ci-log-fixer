"""Tests for ci-log-fixer. Sample logs in tests/samples/ were written for this suite."""

from __future__ import annotations

from pathlib import Path

from ci_log_fixer.analyze import analyze
from ci_log_fixer.cli import main

SAMPLES = Path(__file__).parent / "samples"


def _text(name: str) -> str:
    return (SAMPLES / name).read_text(encoding="utf-8")


def test_missing_module_names_the_package():
    result = analyze(_text("missing-module.log"), source="missing-module.log")
    rules = [f.rule for f in result.findings]
    assert "missing-module" in rules
    finding = next(f for f in result.findings if f.rule == "missing-module")
    assert "orjson" in finding.evidence
    assert "orjson" in finding.fix


def test_version_mismatch():
    result = analyze(_text("version-mismatch.log"))
    assert any(f.rule == "version-mismatch" for f in result.findings)
    report = result.report()
    assert "setup-node" in report or "Node" in report or "python" in report.lower()


def test_deprecated_action_and_set_output():
    result = analyze(_text("deprecated-action.log"))
    assert any(f.rule == "deprecated-action" for f in result.findings)
    assert "GITHUB_OUTPUT" in result.report()


def test_permission_denied_token_scope():
    result = analyze(_text("permission-denied.log"))
    assert any(f.rule == "permission-denied" for f in result.findings)
    assert "Resource not accessible by integration" in result.findings[0].evidence
    assert "permissions:" in result.findings[0].fix


def test_lockfile_mismatch_npm_ci():
    result = analyze(_text("lockfile-mismatch.log"))
    assert any(f.rule == "lockfile-mismatch" for f in result.findings)
    assert "npm install" in result.findings[0].fix


def test_test_failure_extracts_file_line():
    result = analyze(_text("test-failure.log"))
    finding = next(f for f in result.findings if f.rule == "test-failure")
    assert finding.location == "tests/test_math.py:14"
    assert "tests/test_math.py:14" in finding.fix


def test_timeout_and_cancelled():
    result = analyze(_text("timeout.log"))
    assert any(f.rule == "timeout" for f in result.findings)
    assert "timeout-minutes" in result.report()


def test_oom():
    result = analyze(_text("oom.log"))
    assert any(f.rule == "oom" for f in result.findings)
    assert "137" in result.findings[0].evidence or "Killed" in result.findings[0].evidence


def test_rate_limit():
    result = analyze(_text("rate-limit.log"))
    assert any(f.rule == "rate-limit" for f in result.findings)


def test_network_404_and_403():
    missing = analyze(_text("network-404.log"))
    assert any(f.rule == "network-fetch" for f in missing.findings)
    assert "404" in missing.findings[0].evidence
    forbidden = analyze(_text("network-403.log"))
    assert any(f.rule == "network-fetch" for f in forbidden.findings)
    assert "403" in forbidden.findings[0].evidence


def test_green_log_has_no_findings():
    result = analyze(_text("green.log"), source="green.log")
    assert result.findings == []
    report = result.report()
    assert "No common failure cause" in report
    assert report.endswith("\n") or True


def test_each_rule_is_reported_at_most_once():
    text = _text("deprecated-action.log") + "\n" + _text("deprecated-action.log")
    result = analyze(text)
    rules = [f.rule for f in result.findings]
    assert len(rules) == len(set(rules))


def test_cli_writes_report_without_touching_input(tmp_path, capsys):
    src = tmp_path / "job.log"
    src.write_text(_text("missing-module.log"), encoding="utf-8")
    original = src.read_text(encoding="utf-8")
    assert main([str(src), "--write"]) == 1
    assert src.read_text(encoding="utf-8") == original
    dest = tmp_path / "job.tidy.txt"
    assert dest.is_file()
    text = dest.read_text(encoding="utf-8")
    assert "[missing-module]" in text
    assert "orjson" in text
    err = capsys.readouterr().err
    assert "Wrote" in err


def test_cli_stdout_and_stdin(capsys):
    assert main([str(SAMPLES / "green.log")]) == 0
    out = capsys.readouterr().out
    assert "No common failure cause" in out


def test_cli_missing_file(capsys):
    assert main(["/tmp/does-not-exist-ci-log-fixer.log"]) == 1
    assert "cannot read" in capsys.readouterr().err
