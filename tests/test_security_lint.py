"""The security-sink gate must be demonstrable FAILING, not just observed passing.

Standard rule 4.10: "if this had done nothing at all, would the output look
different?" A gate whose only evidence is a green run is indistinguishable from
a gate that scans nothing — Factory#694 and #697 are both that defect. So every
test here is a mutation: plant the thing the gate exists to catch, assert red;
remove it, assert green.

These run ruff for real. There is no mock: mocking the subprocess would test the
reconciliation logic against a fiction, and the failure this suite is insurance
against ("the rule is not actually selected") lives entirely in the config file
that a mock would skip.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared" / "factory-seclint"))

import security_lint

_CONFIG = Path(__file__).resolve().parents[1] / "shared" / "factory-seclint" / "ruff-security.toml"

# The canonical primitive: pickle.load on a path the process does not own.
_PICKLE_RCE = """
import pickle
from pathlib import Path


def load(cache: Path) -> object:
    with open(cache, "rb") as handle:
        return pickle.load(handle)
"""

_CLEAN = """
import json
from pathlib import Path


def load(cache: Path) -> object:
    with open(cache, encoding="utf-8") as handle:
        return json.load(handle)
"""


@pytest.fixture(scope="session")
def ruff() -> str:
    found = shutil.which("ruff")
    if found is None:  # pragma: no cover - CI always installs ruff
        pytest.skip("ruff is not on PATH")
    return found


def _run(tmp_path: Path, _ruff: str, allowlist: str | None) -> tuple[int, str]:
    """Run the gate inside tmp_path (it resolves paths relative to CWD)."""
    listing = tmp_path / "security-lint-allowlist.toml"
    if allowlist is not None:
        listing.write_text(allowlist, encoding="utf-8")
    argv = [
        sys.executable,
        str(Path(security_lint.__file__)),
        "--config",
        str(_CONFIG),
        "--allowlist",
        str(listing),
        ".",
    ]
    proc = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, check=False)  # noqa: S603
    return proc.returncode, proc.stdout + proc.stderr


def test_a_planted_pickle_load_turns_the_gate_red(tmp_path: Path, ruff: str) -> None:
    """THE mutation. If this passes, nothing below means anything."""
    (tmp_path / "cache.py").write_text(_PICKLE_RCE, encoding="utf-8")
    code, out = _run(tmp_path, ruff, allowlist=None)
    assert code == 1, out
    assert "S301" in out
    assert "cache.py" in out


def test_removing_the_pickle_turns_it_green_again(tmp_path: Path, ruff: str) -> None:
    """The other half of the mutation: red must be caused by the plant."""
    target = tmp_path / "cache.py"
    target.write_text(_PICKLE_RCE, encoding="utf-8")
    assert _run(tmp_path, ruff, allowlist=None)[0] == 1
    target.write_text(_CLEAN, encoding="utf-8")
    code, out = _run(tmp_path, ruff, allowlist=None)
    assert code == 0, out


def test_an_allowlist_entry_suppresses_exactly_that_finding(tmp_path: Path, ruff: str) -> None:
    (tmp_path / "cache.py").write_text(_PICKLE_RCE, encoding="utf-8")
    allowed = """
[[allow]]
path = "cache.py"
rule = "S301"
reason = "fixture"
issue = "Factory#721"
"""
    code, out = _run(tmp_path, ruff, allowlist=allowed)
    assert code == 0, out


def test_deleting_the_entry_brings_the_finding_back(tmp_path: Path, ruff: str) -> None:
    """Proves the allowlist is doing the suppressing and not something else."""
    (tmp_path / "cache.py").write_text(_PICKLE_RCE, encoding="utf-8")
    code, out = _run(tmp_path, ruff, allowlist="")
    assert code == 1, out
    assert "S301" in out


def test_an_entry_without_an_issue_reference_fails(tmp_path: Path, ruff: str) -> None:
    """The no-orphan check. This is what stops the allowlist being permanent."""
    (tmp_path / "cache.py").write_text(_PICKLE_RCE, encoding="utf-8")
    orphan = """
[[allow]]
path = "cache.py"
rule = "S301"
reason = "fixture"
"""
    code, out = _run(tmp_path, ruff, allowlist=orphan)
    assert code == 1, out
    assert "issue" in out
    # And it must not be silently treated as a valid suppression on the way out.
    assert "PASS" not in out


def test_a_malformed_issue_reference_fails(tmp_path: Path, ruff: str) -> None:
    (tmp_path / "cache.py").write_text(_PICKLE_RCE, encoding="utf-8")
    vague = """
[[allow]]
path = "cache.py"
rule = "S301"
reason = "fixture"
issue = "see the security channel"
"""
    assert _run(tmp_path, ruff, allowlist=vague)[0] == 1


def test_a_second_occurrence_beyond_the_count_fails(tmp_path: Path, ruff: str) -> None:
    """count is a ceiling. A new sink in an already-listed file is still new."""
    (tmp_path / "cache.py").write_text(
        _PICKLE_RCE + _PICKLE_RCE.replace("def load", "def load2"), encoding="utf-8"
    )
    one = """
[[allow]]
path = "cache.py"
rule = "S301"
count = 1
reason = "fixture"
issue = "Factory#721"
"""
    code, out = _run(tmp_path, ruff, allowlist=one)
    assert code == 1, out
    assert "OVERRUN" in out


@pytest.mark.parametrize("declared", [1, 2, 3])
def test_removing_an_entry_returns_exactly_its_declared_count(
    tmp_path: Path, ruff: str, declared: int
) -> None:
    """Deleting an allowlist entry must surface EXACTLY `count` findings.

    Every other red-path test here asserts a boolean: exit 1, or a keyword in
    the output. A boolean cannot be wrong in an informative way — "it went red"
    is satisfied by the gate breaking for any reason at all, including reasons
    that have nothing to do with what the test claims to prove.

    This one compares against a number the ALLOWLIST ITSELF declares, so the
    check has something to be wrong against. That is not hypothetical: running
    this by hand against the four service repos, a buggy probe reported 2 for an
    entry declaring `count = 1`, and the contradiction is the only reason the
    probe's bug was found rather than published as a result. The expected value
    living in the artefact under test is what made it self-naming.

    Parametrised over several counts because a check that only ever sees 1
    cannot distinguish "reports the declared count" from "reports one finding".
    """
    sinks = "".join(_PICKLE_RCE.replace("def load", f"def load{i}") for i in range(declared))
    (tmp_path / "cache.py").write_text(sinks, encoding="utf-8")

    covered = f"""
[[allow]]
path = "cache.py"
rule = "S301"
count = {declared}
reason = "fixture"
issue = "Factory#721"
"""
    assert _run(tmp_path, ruff, allowlist=covered)[0] == 0, "the entry should cover them all"

    code, out = _run(tmp_path, ruff, allowlist="")
    assert code == 1, out
    assert f"NEW SECURITY-SINK FINDINGS ({declared})" in out, (
        f"removing an entry declaring count={declared} must surface exactly "
        f"{declared} finding(s); got:\n{out}"
    )

    # And the headline number must equal the findings actually LISTED beneath it.
    # Rule 4.10 turned on this gate's own report: a summary count sourced from a
    # different list than the detail lines is a status channel reporting on
    # something other than what it produced. The count above would still pass
    # while the operator reads a shorter list and fixes fewer sinks.
    #
    # Derived from the output rather than hardcoded, so it cannot drift out of
    # sync with the `declared` fixture the way a second literal would.
    listed = re.findall(r"^\s+\S+\.py:\d+: S\d+ ", out, re.M)
    assert len(listed) == declared, (
        f"the report claims {declared} finding(s) but lists {len(listed)}:\n{out}"
    )


def test_a_stale_entry_fails_so_the_list_can_only_shrink(tmp_path: Path, ruff: str) -> None:
    (tmp_path / "cache.py").write_text(_CLEAN, encoding="utf-8")
    stale = """
[[allow]]
path = "cache.py"
rule = "S301"
reason = "already fixed"
issue = "Factory#721"
"""
    code, out = _run(tmp_path, ruff, allowlist=stale)
    assert code == 1, out
    assert "STALE" in out


def test_the_guards_apply_to_every_entry_not_just_the_first(tmp_path: Path, ruff: str) -> None:
    """A multi-entry allowlist, with both violations on NON-first entries.

    Every other allowlist test in this file uses exactly ONE entry, and with one
    entry "checks the first" and "checks every one" are the same observation.
    The shipped allowlists carry four to six. That gap was measured, not
    imagined: restricting the over-count guard to `list(allowed.items())[:1]`
    left all twenty-three other tests green.

    It matters because of the DIRECTION it fails. A parser that read only the
    first entry would fail closed — every later entry stops covering its
    finding, the gate reddens, someone looks. The over-count guard fails OPEN:
    it is the check that stops a NEW sink hiding inside a file that already has
    an entry, so if it only ran for entry one, a fresh `pickle.load` added
    beside any of entries 2..N would ship silently. That is the gate's whole
    purpose failing in the one shape no test covered.

    Credit where due: this is g3-tokens' n=1 blind spot, found in its own token
    suite (every fixture held one profile, so "seals the first" and "seals every
    one" were indistinguishable — and the pool exists to hand out several).
    Same mechanism, different subject, same day.
    """
    # first.py: one sink, correctly covered. second.py: TWO, entry allows one.
    (tmp_path / "first.py").write_text(_PICKLE_RCE, encoding="utf-8")
    (tmp_path / "second.py").write_text(
        _PICKLE_RCE + _PICKLE_RCE.replace("def load", "def load2"), encoding="utf-8"
    )
    (tmp_path / "third.py").write_text(_CLEAN, encoding="utf-8")

    listing = """
[[allow]]
path = "first.py"
rule = "S301"
count = 1
reason = "genuinely covered, and deliberately first"
issue = "Factory#721"

[[allow]]
path = "second.py"
rule = "S301"
count = 1
reason = "covers one; the file now has two"
issue = "Factory#721"

[[allow]]
path = "third.py"
rule = "S301"
reason = "the finding is gone - this entry is stale"
issue = "Factory#721"
"""
    code, out = _run(tmp_path, ruff, allowlist=listing)
    assert code == 1, out
    # The overrun is on entry TWO and the stale entry is THREE. A guard that
    # stops after the first entry reports neither.
    assert "OVERRUN" in out, f"the second entry's extra sink was not caught:\n{out}"
    assert "second.py" in out
    assert "STALE" in out, f"the third entry matched nothing and was not reported:\n{out}"
    assert "third.py" in out
    # And entry one must NOT be implicated - a guard that reports everything is
    # as useless as one that reports nothing.
    assert "first.py" not in out.split("STALE")[0].split("OVERRUN")[-1]


def test_an_expired_entry_fails(tmp_path: Path, ruff: str) -> None:
    (tmp_path / "cache.py").write_text(_PICKLE_RCE, encoding="utf-8")
    expired = """
[[allow]]
path = "cache.py"
rule = "S301"
reason = "fixture"
issue = "Factory#721"
expires = "2020-01-01"
"""
    code, out = _run(tmp_path, ruff, allowlist=expired)
    assert code == 1, out
    assert "expired" in out


def test_scanning_zero_files_is_a_failure_not_a_pass(tmp_path: Path, ruff: str) -> None:
    """Rule 4.10 directly: an empty scan produces zero findings and means nothing."""
    (tmp_path / "notes.md").write_text("no python here", encoding="utf-8")
    code, out = _run(tmp_path, ruff, allowlist=None)
    assert code == 1, out
    assert "ZERO files" in out


def test_a_broken_ruff_invocation_fails_closed(tmp_path: Path) -> None:
    """Rule 4.7: a gate that cannot read its artefact must not report success."""
    (tmp_path / "cache.py").write_text(_PICKLE_RCE, encoding="utf-8")
    argv = [
        sys.executable,
        str(Path(security_lint.__file__)),
        "--config",
        str(_CONFIG),
        "--ruff",
        "ruff-that-does-not-exist",
        ".",
    ]
    proc = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, check=False)  # noqa: S603
    assert proc.returncode != 0


@pytest.mark.usefixtures("ruff")
def test_the_self_test_passes_against_the_real_config() -> None:
    """The proof that ships to every service. It must work with what ships."""
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(Path(security_lint.__file__)),
            "--config",
            str(_CONFIG),
            "--self-test",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.usefixtures("ruff")
def test_the_self_test_fails_when_the_config_stops_selecting_s301(tmp_path: Path) -> None:
    """Mutate the SELF-TEST, not just the code. Otherwise the proof is decorative.

    Drop S301 from the select list and the self-test must notice, because the
    scenario it is insurance against is a rule silently leaving the config.
    """
    weakened = tmp_path / "weak.toml"
    weakened.write_text('target-version = "py311"\n[lint]\nselect = ["S102"]\n', encoding="utf-8")
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(Path(security_lint.__file__)),
            "--config",
            str(weakened),
            "--self-test",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1, proc.stdout
    assert "did NOT produce S301" in proc.stdout


@pytest.mark.parametrize(
    ("snippet", "rule"),
    [
        ("import subprocess\nsubprocess.run('ls ' + x, shell=True)\n", "S602"),
        ("eval(payload)\n", "S307"),
        ("exec(payload)\n", "S102"),
        ("import yaml\nyaml.load(blob)\n", "S506"),
        ("import requests\nrequests.get(url, verify=False)\n", "S501"),
        ("import os\nos.system('rm ' + x)\n", "S605"),
        ("import tarfile\ntarfile.open(p).extractall('/out')\n", "S202"),
    ],
)
def test_each_headline_sink_is_actually_selected(
    tmp_path: Path, ruff: str, snippet: str, rule: str
) -> None:
    """A select list is a claim. This asserts the claim against ruff's behaviour.

    Without this, a typo'd or renamed rule code sits in the config looking
    enforced forever — the config parses, the gate is green, and the sink is
    unwatched. That is the same shape as the defect this whole gate addresses.
    """
    (tmp_path / "sink.py").write_text(snippet, encoding="utf-8")
    code, out = _run(tmp_path, ruff, allowlist=None)
    assert code == 1, out
    assert rule in out, f"{rule} is in the select list but ruff did not report it:\n{out}"
