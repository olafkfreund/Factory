#!/usr/bin/env python3
"""Refuse to let a SARIF file with zero loaded rules reach codeql-action/upload-sarif.

Factory#774. ``codeql-action/analyze``'s default ``upload: always`` uploads
even when the run is cancelled mid-flight, which is how a cancelled CodeQL job
published ``rules_count=0`` as a real analysis twice in this repo's own
history (see ``check_codeql_analysis_honesty.py`` for the two confirmed
occurrences). ``codeql.yml`` now sets ``upload: never`` on the analyze step
and calls this as a separate step before its own explicit
``codeql-action/upload-sarif`` -- a job killed by ``cancel-in-progress: true``
dies before reaching a step that comes after the one that was cancelled, so
routing the upload through here means cancellation can no longer produce a
zero-rule publish at all.

This is a workflow guard, not a fleet-wide comparison gate (nothing here has
a registry that can silently shrink), so it does not carry the
``scripts/check_*.py`` self-test/GATES machinery -- see the ``_EXEMPT`` table
in ``tests/test_gate_honesty.py`` for the same reasoning applied to
``check_deploy_drift.py``.

Exit codes:
    0 - every *.sarif file in the given directory loaded at least one rule
    1 - a file loaded zero rules, or the directory has no SARIF files at all
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from gate_evidence import expect, report_self_test


def rule_count(run: dict[str, object]) -> int:
    """Rules a single SARIF ``run`` object declares it loaded.

    Most CodeQL SARIF puts its rules under ``tool.driver.rules``; some query
    packs register rules through ``tool.extensions[].rules`` instead. Sum
    both rather than picking one, or a legitimate extension-only run would
    read as zero.
    """
    tool = run.get("tool", {})
    driver = tool.get("driver", {}) if isinstance(tool, dict) else {}
    driver_rules = driver.get("rules", []) if isinstance(driver, dict) else []
    extensions = tool.get("extensions", []) if isinstance(tool, dict) else []
    ext_rules = sum(len(ext.get("rules", [])) for ext in extensions if isinstance(ext, dict))
    return (len(driver_rules) if isinstance(driver_rules, list) else 0) + ext_rules


def check_file(path: Path) -> list[str]:
    """Problems found in one SARIF file; empty means it is fine to upload."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: could not read/parse as JSON ({exc})"]
    runs = data.get("runs", [])
    if not isinstance(runs, list) or not runs:
        return [f"{path}: SARIF has no 'runs' entries"]
    problems = []
    for i, run in enumerate(runs):
        if not isinstance(run, dict):
            problems.append(f"{path}: runs[{i}] is not an object")
            continue
        count = rule_count(run)
        if count == 0:
            problems.append(f"{path}: runs[{i}] loaded zero rules")
    return problems


def check_dir(sarif_dir: Path) -> list[str]:
    """Problems across every *.sarif file in *sarif_dir*."""
    files = sorted(sarif_dir.glob("*.sarif"))
    if not files:
        return [f"{sarif_dir}: no *.sarif files found -- nothing to upload"]
    problems: list[str] = []
    for path in files:
        problems.extend(check_file(path))
    return problems


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: assert_sarif_has_rules.py <sarif-directory>")  # noqa: T201
        return 1
    problems = check_dir(Path(argv[0]))
    if problems:
        for problem in problems:
            print(f"::error::{problem}")  # noqa: T201
        print(  # noqa: T201
            "\nRefusing to upload: a SARIF with zero loaded rules is "
            "indistinguishable from a clean scan once published "
            "(Factory#774). If the analyze step was cancelled or errored, "
            "let the job go red rather than publishing partial output."
        )
        return 1
    print(f"OK: every SARIF file in {argv[0]} loaded at least one rule.")  # noqa: T201
    return 0


_SELF_TEST_ARGC = 2


def _self_test() -> int:
    """Minimal runnable self-check -- not a full gate self-test (see module docstring)."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        honest = root / "honest.sarif"
        honest.write_text(json.dumps({"runs": [{"tool": {"driver": {"rules": [{"id": "x"}]}}}]}))
        expect(failures, check_file(honest) == [], "a run with one rule must pass")

        zero = root / "zero.sarif"
        zero.write_text(json.dumps({"runs": [{"tool": {"driver": {"rules": []}}}]}))
        problems = check_file(zero)
        expect(
            failures,
            len(problems) == 1 and "zero rules" in problems[0],
            "an empty rule list must fail",
        )

        ext_only = root / "ext.sarif"
        ext_only.write_text(
            json.dumps(
                {
                    "runs": [
                        {
                            "tool": {
                                "driver": {"rules": []},
                                "extensions": [{"rules": [{"id": "y"}]}],
                            }
                        }
                    ]
                }
            )
        )
        expect(
            failures,
            check_file(ext_only) == [],
            "rules declared only via an extension must still count",
        )

        empty_dir = root / "empty"
        empty_dir.mkdir()
        problems = check_dir(empty_dir)
        expect(
            failures,
            len(problems) == 1 and "no *.sarif files" in problems[0],
            "an empty directory must fail, not silently pass",
        )

    return report_self_test(failures)


if __name__ == "__main__":
    if len(sys.argv) == _SELF_TEST_ARGC and sys.argv[1] == "--self-test":
        raise SystemExit(_self_test())
    raise SystemExit(main())
