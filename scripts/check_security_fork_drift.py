#!/usr/bin/env python3
"""Fail CI when a security-relevant file forked across sibling repos diverges.

Factory security-cleanup review (2026-08-13). CodeQL reports per-repo, so an
unscanned fork reads clean even when its sibling copy carries a live bug.
Today's evidence, five separate times: ``artifact_store.py`` (tarslip), an
SSRF guard, a workspace lock permission (0o644), ``skills_service.py``
(pickle-vs-JSON), ``bump-version.js`` (fs-race). Each was fixed in one repo
while the others kept the bug, because nothing compared the copies.

Two DIFFERENT relationships need two different truth conditions, discovered
while validating this gate against real state (the ``skills_service.py``
finding below):

- ``kind="vendored"`` (e.g. ``artifact_store.py``): the copies are supposed
  to be the SAME file everywhere. Byte-identical is the only correct
  assertion, exactly as ``check_factory_github_drift.py`` et al already do
  for formally vendored trees — except these were pasted independently at
  different relative paths, so there is no single hub canonical to diff
  against; every present copy is compared to every other present copy.

- ``kind="forked"`` (e.g. ``skills_service.py``): the copies started as the
  same file but have legitimately diverged — AIFactory carries a feature
  (``suggest_selected_skills``) PFactory has no caller for, plus an unrelated
  typing-style difference. Byte-identity is the WRONG assertion here: it
  would make the entry permanently red, and a permanently-red gate gets
  disabled, which is worse than no gate (the exact origin of the diff-scoped
  enforcement hole this whole batch exists to close). But bare "allow any
  difference" would silently swallow a REAL security drift too, which is the
  original bug this gate exists to catch.

  The fix, in the same shape as Gate 5's allowlist: a forked pair's CURRENT
  divergence must be REGISTERED (a name, the exact digest of each side, a
  reason, an issue ref). A registered divergence passes. Any OTHER
  divergence — a new one, or the registered one drifting further — fails,
  because nothing vouched for it. Widening a known-divergent pair on
  purpose means updating the registration in the same PR, which is a
  deliberate, reviewed act rather than a silent one.

Usage:
    python scripts/check_security_fork_drift.py --fleet-root /path/to/GitHub
        # fleet-root contains Factory/, PFactory/, AIFactory/, TFactory/, CFactory/

    python scripts/check_security_fork_drift.py --self-test

Exit codes:
    0 - every vendored entry's present copies match; every forked entry's
        divergence (if any) matches a registered snapshot
    1 - drift detected: an unregistered/changed divergence, or a registration
        with no issue ref
    2 - bad invocation
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

from gate_evidence import digest

# Registry: logical name -> {repo_name: repo-relative path or None, "_kind": "vendored"|"forked"}.
# Built from what is ACTUALLY duplicated today (found by hashing candidate
# paths across the fleet checkout), not guessed. `None` = repo has no copy of
# this file; it is simply skipped for that repo, not treated as a violation.
REGISTRY: dict[str, dict[str, str | None]] = {
    "artifact_store.py (tarslip guard)": {
        "_kind": "vendored",
        "Factory": "scripts/artifact_store.py",
        "PFactory": "apps/backend/runners/artifact_store.py",
        "AIFactory": "apps/backend/core/artifact_store.py",
        "TFactory": "apps/backend/tools/runners/artifact_store.py",
        "CFactory": None,
    },
    "skills_service.py (skills cache + suggestion service)": {
        "_kind": "forked",
        "PFactory": "apps/web-server/server/services/skills_service.py",
        "AIFactory": "apps/web-server/server/services/skills_service.py",
    },
}

# Registered divergences for `kind="forked"` entries. Each entry's `digests`
# must match the CURRENT full sha256 of every present copy exactly, or the
# divergence is treated as new/changed and the gate fails. An entry with no
# `issue` is itself a gate failure (same anti-unreviewed-grandfather rule as
# Gate 5's allowlist).
FORK_DIVERGENCES: list[dict[str, object]] = [
    {
        "name": "skills_service.py (skills cache + suggestion service)",
        "digests": {
            "PFactory": "4af978efd18ae29aa14ffac080dceb046f5332fdb471fafd143a5e440f435f31",
            "AIFactory": "27baadd8d4f2f3e19ed75e7c07f40b76a9d079c0f3730273ee8c0b6e9facb9b7",
        },
        "reason": (
            "AIFactory carries suggest_selected_skills/suggestion_to_selected "
            "(a feature PFactory has no caller for, deliberately not ported) "
            "plus an Optional[X] vs X | None typing-style difference (tracked "
            "separately, Factory#725). The pickle-cache RCE that originally "
            "flagged this pair is closed on both sides. Factory#727 tracks the "
            "actual hub-canonical decision (port suggest_selected_skills to "
            "PFactory, or keep it AIFactory-only permanently) — NOT Factory#718, "
            "which is Gate 5's unrelated ratchet-flip-date issue."
        ),
        "issue": "Factory#727",
    },
]


def _repo_root(fleet_root: Path, repo: str) -> Path:
    return fleet_root / repo


def _full_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _present_copies(fleet_root: Path, copies: dict[str, str | None]) -> dict[str, Path]:
    present = {
        repo: (_repo_root(fleet_root, repo) / rel)
        for repo, rel in copies.items()
        if repo != "_kind" and rel is not None
    }
    return {repo: path for repo, path in present.items() if path.is_file()}


def _matching_divergence(name: str, digests: dict[str, str]) -> dict[str, object] | None:
    for entry in FORK_DIVERGENCES:
        if entry["name"] != name:
            continue
        if entry["digests"] == digests:
            return entry
        return "MISMATCH"  # a registration exists for this name but the bytes moved
    return None


def check_drift(fleet_root: Path) -> list[str]:
    """Return one problem string per registry entry that fails its truth condition."""
    problems: list[str] = []
    for name, copies in REGISTRY.items():
        kind = copies.get("_kind", "vendored")
        present = _present_copies(fleet_root, copies)
        if len(present) < 2:
            continue  # nothing to compare — 0 or 1 present copies
        file_digests = {repo: _full_digest(path) for repo, path in present.items()}
        reference_repo, reference_digest = next(iter(file_digests.items()))
        diverged = any(d != reference_digest for d in file_digests.values())
        if not diverged:
            continue

        cited = ", ".join(f"{repo}={digest(path)}" for repo, path in present.items())

        if kind == "vendored":
            problems.append(
                f"{name}: copies diverge across repos ({cited}); reference was {reference_repo}"
            )
            continue

        # kind == "forked": diverging is expected; it must be a REGISTERED
        # divergence with an issue ref, matching the CURRENT bytes exactly.
        match = _matching_divergence(name, file_digests)
        if match is None:
            problems.append(
                f"{name}: forked copies diverge with NO registered divergence "
                f"({cited}) — register it in FORK_DIVERGENCES with a reason and "
                f"an issue ref, or this is an unreviewed drift"
            )
        elif match == "MISMATCH":
            problems.append(
                f"{name}: forked copies diverge but do NOT match the registered "
                f"snapshot ({cited}) — the divergence changed since it was "
                f"registered; re-register with the new digests and a reason"
            )
        elif not match.get("issue"):  # type: ignore[union-attr]
            problems.append(
                f"{name}: registered divergence has no `issue` ref — an "
                "unreviewed grandfather is not a grandfather"
            )
    return problems


def run_check(fleet_root: Path) -> int:
    problems = check_drift(fleet_root)
    print(f"security-fork-drift: fleet root {fleet_root}, {len(REGISTRY)} registered file(s)")  # noqa: T201
    if problems:
        print("DRIFT DETECTED — a security-relevant forked file diverges unexpectedly:")  # noqa: T201
        for problem in problems:
            print(f"  - {problem}")  # noqa: T201
        print(  # noqa: T201
            "\nA VENDORED entry must be byte-identical everywhere — port the fix. "
            "A FORKED entry may diverge, but only via a reviewed registration in "
            "FORK_DIVERGENCES with a reason and an issue ref."
        )
        return 1
    print("OK: every vendored entry matches; every forked divergence is registered.")  # noqa: T201
    return 0


def _self_test() -> int:
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for repo in ("RepoA", "RepoB", "RepoC"):
            (root / repo / "sub").mkdir(parents=True)

        registry_backup = dict(REGISTRY)
        divergences_backup = list(FORK_DIVERGENCES)
        try:
            REGISTRY.clear()
            FORK_DIVERGENCES.clear()

            # --- vendored kind: unchanged behaviour, byte-exact always ---
            REGISTRY["vendored-thing.py"] = {
                "_kind": "vendored",
                "RepoA": "sub/thing.py",
                "RepoB": "sub/thing.py",
                "RepoC": "sub/thing.py",
            }
            for repo in ("RepoA", "RepoB", "RepoC"):
                (root / repo / "sub" / "thing.py").write_text("SAFE = 1\n")
            expect(check_drift(root) == [], "identical vendored copies must not drift")

            (root / "RepoC" / "sub" / "thing.py").unlink()
            expect(check_drift(root) == [], "a missing vendored copy must not itself count as drift")
            (root / "RepoC" / "sub" / "thing.py").write_text("SAFE = 1\n")

            # Mutation: RepoB's vendored copy silently reverts.
            (root / "RepoB" / "sub" / "thing.py").write_text("SAFE = 0  # bug reintroduced\n")
            problems = check_drift(root)
            expect(len(problems) == 1, f"exactly one vendored entry must drift, got {problems}")
            expect(run_check(root) == 1, "run_check must fail when a vendored fork diverges")
            (root / "RepoB" / "sub" / "thing.py").write_text("SAFE = 1\n")
            expect(run_check(root) == 0, "run_check must pass once vendored copies match again")

            REGISTRY.clear()

            # --- forked kind: registered-divergence model ---
            for repo in ("RepoA", "RepoB"):
                (root / repo / "sub").mkdir(parents=True, exist_ok=True)
            REGISTRY["forked-thing.py"] = {
                "_kind": "forked",
                "RepoA": "sub/forked.py",
                "RepoB": "sub/forked.py",
            }

            (root / "RepoA" / "sub" / "forked.py").write_text("BASE = 1\n")
            (root / "RepoB" / "sub" / "forked.py").write_text("BASE = 1\n")
            expect(check_drift(root) == [], "identical forked copies must not drift (nothing to register)")

            # Case: a NEW, unregistered divergence appears -> must fail. This is
            # the case a bare byte-compare (or a bare "forks may differ") would
            # get wrong in opposite directions: byte-compare stays red forever,
            # "may differ" never catches a real regression.
            (root / "RepoB" / "sub" / "forked.py").write_text("BASE = 1\nEXTRA_FEATURE = True\n")
            problems = check_drift(root)
            expect(
                len(problems) == 1 and "NO registered divergence" in problems[0],
                f"an unregistered forked divergence must be flagged, got {problems}",
            )
            expect(run_check(root) == 1, "run_check must fail on an unregistered forked divergence")

            # Register it with the exact current digests -> passes.
            a_digest = _full_digest(root / "RepoA" / "sub" / "forked.py")
            b_digest = _full_digest(root / "RepoB" / "sub" / "forked.py")
            FORK_DIVERGENCES.append(
                {
                    "name": "forked-thing.py",
                    "digests": {"RepoA": a_digest, "RepoB": b_digest},
                    "reason": "RepoB carries an extra feature, deliberately not ported",
                    "issue": "FAKE-1",
                }
            )
            expect(run_check(root) == 0, "run_check must pass once the divergence is registered with an issue ref")

            # Case: the registered divergence then drifts FURTHER (RepoB
            # changes again) -> must fail again, not stay silently green.
            (root / "RepoB" / "sub" / "forked.py").write_text("BASE = 1\nEXTRA_FEATURE = True\nEVEN_MORE = 2\n")
            problems = check_drift(root)
            expect(
                len(problems) == 1 and "do NOT match the registered snapshot" in problems[0],
                f"a divergence that moves past its registration must be re-flagged, got {problems}",
            )

            # Case: a registration with NO issue ref fails outright, same as Gate 5.
            FORK_DIVERGENCES.clear()
            new_b_digest = _full_digest(root / "RepoB" / "sub" / "forked.py")
            FORK_DIVERGENCES.append(
                {
                    "name": "forked-thing.py",
                    "digests": {"RepoA": a_digest, "RepoB": new_b_digest},
                    "reason": "no issue ref on purpose",
                    "issue": "",
                }
            )
            expect(
                run_check(root) == 1,
                "a registered divergence with no issue ref must fail, not pass",
            )
        finally:
            REGISTRY.clear()
            REGISTRY.update(registry_backup)
            FORK_DIVERGENCES.clear()
            FORK_DIVERGENCES.extend(divergences_backup)

    if failures:
        print("SELF-TEST FAILED:")  # noqa: T201
        for failure in failures:
            print(f"  - {failure}")  # noqa: T201
        return 1
    print("SELF-TEST OK: security-fork-drift gate behaves as specified.")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fleet-root",
        help="directory containing Factory/, PFactory/, AIFactory/, TFactory/, CFactory/ checkouts",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.fleet_root:
        parser.error("--fleet-root is required (or pass --self-test)")
    return run_check(Path(args.fleet_root))


if __name__ == "__main__":
    sys.exit(main())
