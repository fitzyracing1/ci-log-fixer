"""ci-log-fixer: name the cause of a failing GitHub Actions log and suggest a fix."""

from ci_log_fixer.analyze import Finding, analyze

__version__ = "0.1.0"
__all__ = ["Finding", "analyze", "__version__"]
