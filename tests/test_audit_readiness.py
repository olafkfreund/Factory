"""Factory#324: the audit-readiness page must not point at things that do not exist."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs/compliance/audit-readiness.md"
TEXT = PAGE.read_text(encoding="utf-8")


def test_relative_links_resolve():
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", TEXT):
        if target.startswith("http"):
            continue
        assert (PAGE.parent / target).exists(), target


def test_repo_paths_exist():
    for path in re.findall(r"`((?:docs|tests|scripts)/[^`\s]+)`", TEXT):
        assert (ROOT / path).exists(), path


def test_tracker_links_well_formed():
    for url in re.findall(r"\]\((https://github\.com/[^)]+)\)", TEXT):
        assert re.fullmatch(r"https://github\.com/olafkfreund/[\w.-]+/issues/\d+", url), url


def test_statuses_allowed():
    body = TEXT.split("## Readiness checklist")[1].split("## Mock")[0]
    rows = re.findall(r"^\| [^|]+ \| (\w+) \|", body, re.M)
    rows = [r for r in rows if r != "Status"]
    assert rows and set(rows) <= {"Ready", "Open", "Owner"}
