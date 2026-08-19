#!/usr/bin/env python3
"""Fail CI when a security-relevant file forked across sibling repos diverges.

Factory security-cleanup review (2026-08-13). CodeQL reports per-repo, so an
unscanned fork reads clean even when its sibling copy carries a live bug.
Today's evidence, five separate times: ``artifact_store.py`` (tarslip), an
SSRF guard, a workspace lock permission (0o644), ``skills_service.py``
(pickle-vs-JSON), ``bump-version.js`` (fs-race). Each was fixed in one repo
while the others kept the bug, because nothing compared the copies.

READS COMMITTED REFS, NOT WORKING-TREE FILES. Learned the hard way: an
earlier version of this gate read plain files under ``--fleet-root``, and
promptly produced a false positive on ``artifact_store.py`` (Factory#729) —
the local PFactory/AIFactory checkouts on the machine running it had a `dev`
branch sitting at a different point than their own `origin/dev` (clean
working tree, but local HEAD had diverged from the remote), so the gate
faithfully compared ambient disk state that was not the fleet's actual
published state. Same root cause, same day, as the Gate 5 scope bug
(check_banned_constructs.py wandering into `.venv-ci/`, `site-packages/`, a
nested worktree — see that script) — "the gate reads whatever happens to be
on disk" rather than a defined scope. The fix here is the same discipline
one level down: read each repo's REGISTERED ref (``origin/main`` for the hub,
``origin/dev`` for the four services) via ``git show <ref>:<path>``, which
resolves from the git object database and is unaffected by a dirty tree, a
detached HEAD, a stale local branch, or an agent's feature branch checked out
in the same directory.

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
  disabled, which is worse than no gate. But bare "allow any difference"
  would silently swallow a REAL security drift too, which is the original
  bug this gate exists to catch.

  The fix, in the same shape as Gate 5's allowlist: a forked pair's CURRENT
  divergence must be REGISTERED (a name, the exact digest of each side, a
  reason, an issue ref). A registered divergence passes. Any OTHER
  divergence — a new one, or the registered one drifting further — fails,
  because nothing vouched for it.

- ``kind="forked-code"`` (e.g. ``assert-hub-pin-on-main.sh``, Factory#819):
  the registered-divergence model above, applied to the script's EXECUTABLE
  BODY rather than its bytes — whole-line ``#`` comments and blank lines are
  removed before hashing (``strip_shell_comments``; the shebang survives).
  Added for a shell guard whose four copies each document their own repo's
  inventory of hub-pinned workflows in the header. Under plain ``forked``
  that entry would need a hub re-registration every time one repo adds a
  workflow and updates a COMMENT, and a gate that goes red on documentation
  edits is a gate someone eventually deletes. Under ``forked-code`` the
  registration pins what is executed, and only a real change to the logic —
  in one repo and not its siblings — turns it red.

Usage:
    python scripts/check_security_fork_drift.py --fleet-root /path/to/GitHub
        # fleet-root contains Factory/, PFactory/, AIFactory/, TFactory/, CFactory/
        # git checkouts. Content is read via `git show REPO_REFS[repo]:path`
        # inside each — the working tree is never touched.

    python scripts/check_security_fork_drift.py --self-test

Exit codes:
    0 - every vendored entry's present copies match; every forked entry's
        divergence (if any) matches a registered snapshot
    1 - drift detected: an unregistered/changed divergence, or a registration
        with no issue ref
    2 - bad invocation
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from gate_evidence import expect, gate_argparser, parse_or_self_test, report_self_test, temp_repo

# The ref each repo is compared AT. The hub releases from `main`; the four
# service repos are gated on `dev` (same convention chart-vs-gitops.yml
# documents: PRs land on dev, main is the release branch). Read via `origin/`
# so a local branch of the same name that has diverged is never consulted.
REPO_REFS: dict[str, str] = {
    "Factory": "origin/main",
    "PFactory": "origin/dev",
    "AIFactory": "origin/dev",
    "TFactory": "origin/dev",
    "CFactory": "origin/dev",
}

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
    # Factory#819. The guard that decides whether a hub pin names a commit on
    # hub `main` — the thing standing between a fork PR and a gate bypass —
    # was itself shipped as four independent copies with nothing comparing
    # them. Measured on 2026-08-19 at each repo's origin/dev: four distinct
    # blobs, and with whole-line comments stripped the executable bodies
    # differ by EXACTLY ONE line, the tracking issue named in the failure
    # message (Factory#806 / TFactory#1049 / AIFactory#1281 / CFactory#373).
    #
    # `forked-code`, not `vendored` or `forked`, and the choice is the whole
    # point of the entry. Byte-identity is unreachable: each copy's header
    # documents ITS OWN repo's inventory of hub-pinned workflows, which is
    # correct where it is and not shareable. Registering the RAW digests
    # (plain `forked`) would work today and then go red the next time any one
    # repo adds a hub-pinned workflow and updates its inventory comment — a
    # doc edit forcing a hub re-registration, which is the churn that gets a
    # gate switched off. Comparing the comment-stripped body pins the part
    # that matters (the 40-hex check, the compare-API call, the exit-code
    # contract) and lets the per-repo prose move freely.
    "assert-hub-pin-on-main.sh (hub-pin-on-main reachability guard)": {
        "_kind": "forked-code",
        "PFactory": ".github/scripts/assert-hub-pin-on-main.sh",
        "AIFactory": ".github/scripts/assert-hub-pin-on-main.sh",
        "TFactory": ".github/scripts/assert-hub-pin-on-main.sh",
        "CFactory": ".github/scripts/assert-hub-pin-on-main.sh",
    },
}

# Registered divergences for `kind="forked"` entries. Each entry's `digests`
# must match the CURRENT full sha256 of every present copy AT ITS REGISTERED
# REF exactly, or the divergence is treated as new/changed and the gate
# fails. An entry with no `issue` is itself a gate failure (same
# anti-unreviewed-grandfather rule as Gate 5's allowlist).
FORK_DIVERGENCES: list[dict[str, object]] = [
    {
        "name": "skills_service.py (skills cache + suggestion service)",
        "digests": {
            "PFactory": "b544a0d31da89df68ecbe8e66efe6c2048d3413ebf628d3eed2444a7a6deee28",
            "AIFactory": "ee07b54e4c906513957b644289c09b40808d324bfcd241dcdac7cb0f61bf6fb5",
        },
        "reason": (
            "Re-derived from origin/dev (git show origin/dev:<path> | sha256sum) "
            "on 2026-08-15, per Factory#729 — never from a working tree, which "
            "is how these were wrong once already. "
            "THE DIVERGENCE IS PERMANENT AND ARCHITECTURAL, not a grandfather "
            "awaiting a decision: Factory#727 is closed deciding that "
            "suggest_selected_skills/suggestion_to_selected stays AIFactory-only. "
            "Its only caller is AIFactory's routes/execution.py, and PFactory "
            "has no execution route — executing a plan is AIFactory's stage of "
            "PARR. Porting it would add an uncalled public function to a shared "
            "file purely to make this digest comparison simpler. Reversible if "
            "PFactory ever grows an execution route: drop this entry and the "
            "files go back to byte-identical. "
            "The typing-style difference (Optional[X] vs X | None) is gone — "
            "Factory#725 modernized PFactory to match. "
            "Both prior security divergences are closed on both sides: the "
            "pickle-cache RCE that first flagged this pair, and the two "
            "py/empty-except sites AIFactory fixed in 9fc70e14 which PFactory "
            "had not followed — a silently-suppressed chmod(0o600) failure on "
            "the skills cache, and a bare except around a scandir loop. That "
            "second one is what Factory#753 caught, and it is the whole point "
            "of this registry: one fork taking a security fix while the other "
            "does not."
        ),
        "issue": "Factory#727",
    },
    {
        "name": "assert-hub-pin-on-main.sh (hub-pin-on-main reachability guard)",
        # sha256 of strip_shell_comments(git show origin/dev:<path>), taken on
        # 2026-08-19. Re-derive by reading each repo at `git show origin/dev:`
        # and hashing strip_shell_comments() of the result -- never from a
        # working tree (Factory#729). The gate's own failure message prints
        # the current value of every copy, so a re-registration needs no
        # scripting: run it, copy the four digests it names.
        # The four bodies are 1085/1086/1087/1088 bytes — the length spread is
        # exactly the length spread of the four issue references below, which
        # is the corroboration that nothing else in the logic differs.
        "digests": {
            "PFactory": "35bc80a6a19ef7f3df8de3f45b0577e3025c48f518265f53040d498668414770",
            "AIFactory": "312ae5ed94724d30ad5d3f2939b31e03311fc8e0211df45e8b4afa28fe32eeb0",
            "TFactory": "2d4ba6300a405503239d36e6c87d46ed6e35fa562dacd579546ae06807afee7c",
            "CFactory": "da9e74fb28c43d9c49ac2ba967d296258869183d7e341dfc87e39f4f9acc76c1",
        },
        "reason": (
            "Measured, not assumed (Factory#819): with whole-line comments "
            "stripped, the four copies' executable bodies differ by EXACTLY ONE "
            "line — the tracking issue named in the failure message. PFactory "
            "cites Factory#806, TFactory TFactory#1049, AIFactory "
            "AIFactory#1281, CFactory CFactory#373. That is deliberate: the "
            "message tells a maintainer in THAT repo where the decision is "
            "recorded, and a hub issue number in a CFactory failure log sends "
            "them to the wrong tracker. "
            "Everything the guard actually does is identical across all four: "
            "the ^[0-9a-f]{40}$ check, the `gh api repos/olafkfreund/Factory/"
            "compare/main...<sha>` call with no `|| true`, the "
            "identical|behind pass set, and the exit-code contract. Those are "
            "what this registration pins. "
            "WHY NOT A HUB CANONICAL: making the copies byte-identical would "
            "mean deleting each header's inventory of that repo's own "
            "hub-pinned workflows — six in TFactory, a different set in "
            "PFactory — which is the most useful documentation in the file and "
            "is genuinely per-repo. Templating it back in trades a real "
            "reader-facing comment for a vendoring step. Reversible: if the "
            "per-repo prose ever leaves the file, drop this entry and promote "
            "the registry entry to `vendored`."
        ),
        "issue": "Factory#819",
    },
]


def _identity(data: bytes) -> bytes:
    return data


def strip_shell_comments(data: bytes) -> bytes:
    """A shell script's executable body: whole-line comments and blank lines removed.

    Only lines whose FIRST non-space character is ``#`` are dropped, so a ``#``
    inside a string or a trailing comment on a real command is never touched —
    a logic change cannot hide behind this. The ``#!`` shebang is kept: swapping
    the interpreter is an executable change, and it lives on a comment-shaped
    line. Line 1 only, because that is the only line on which `#!` means
    anything to the kernel — a `#!...` further down IS just a comment.
    """
    kept: list[bytes] = []
    for index, line in enumerate(data.split(b"\n")):
        stripped = line.strip()
        if index == 0 and stripped.startswith(b"#!"):
            kept.append(line)
            continue
        if not stripped or stripped.startswith(b"#"):
            continue
        kept.append(line)
    return b"\n".join(kept) + b"\n"


# What each kind compares. `forked-code` exists because a shared shell guard
# can carry per-repo documentation that is correct where it is (see the
# assert-hub-pin-on-main.sh entry above); everything else is compared whole.
_NORMALISERS: dict[str, Callable[[bytes], bytes]] = {"forked-code": strip_shell_comments}

# Kinds whose copies are ALLOWED to diverge, provided the divergence is
# registered in FORK_DIVERGENCES with a reason and an issue ref.
_REGISTERED_DIVERGENCE_KINDS = frozenset({"forked", "forked-code"})


def _digest_bytes(data: bytes) -> str:
    """Same citation format as gate_evidence.digest(), for content read via git show
    (which never has a Path on disk representing the exact bytes compared)."""
    return f"sha256:{sha256(data).hexdigest()[:12]} {len(data)}B"


def read_ref(repo_dir: Path, ref: str, rel_path: str) -> bytes | None:
    """Content of *rel_path* AT *ref* inside the git repo at *repo_dir*.

    None if the path does not exist at that ref (repo has no copy — not a
    failure). Deliberately does NOT touch the working tree: a dirty tree, a
    detached HEAD, or a stale local branch checked out in *repo_dir* cannot
    affect the answer, because `git show` reads the object database.
    """
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_dir), "show", f"{ref}:{rel_path}"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _present_ref_copies(
    fleet_root: Path, copies: dict[str, str | None], repo_refs: dict[str, str]
) -> dict[str, bytes]:
    present: dict[str, bytes] = {}
    for repo, rel in copies.items():
        if repo == "_kind" or rel is None:
            continue
        ref = repo_refs.get(repo)
        if ref is None:
            continue
        content = read_ref(fleet_root / repo, ref, rel)
        if content is not None:
            present[repo] = content
    return present


def _matching_divergence(name: str, digests: dict[str, str]) -> dict[str, object] | None | str:
    for entry in FORK_DIVERGENCES:
        if entry["name"] != name:
            continue
        if entry["digests"] == digests:
            return entry
        return "MISMATCH"  # a registration exists for this name but the bytes moved
    return None


_MIN_COPIES_TO_COMPARE = 2  # 0 or 1 present copies means nothing to compare


def check_drift(fleet_root: Path, repo_refs: dict[str, str] | None = None) -> list[str]:
    """Return one problem string per registry entry that fails its truth condition."""
    repo_refs = REPO_REFS if repo_refs is None else repo_refs
    problems: list[str] = []
    for name, copies in REGISTRY.items():
        kind = copies.get("_kind", "vendored")
        present = _present_ref_copies(fleet_root, copies, repo_refs)
        if len(present) < _MIN_COPIES_TO_COMPARE:
            continue
        # What is compared is what is cited: for a `forked-code` entry both the
        # digest and the printed evidence are of the comment-stripped body, so
        # a reader can reproduce the number the gate actually decided on.
        normalise = _NORMALISERS.get(str(kind), _identity)
        compared = {repo: normalise(data) for repo, data in present.items()}
        file_digests = {repo: sha256(data).hexdigest() for repo, data in compared.items()}
        reference_repo, reference_digest = next(iter(file_digests.items()))
        diverged = any(d != reference_digest for d in file_digests.values())
        if not diverged:
            continue

        cited = ", ".join(f"{repo}={_digest_bytes(data)}" for repo, data in compared.items())

        if kind not in _REGISTERED_DIVERGENCE_KINDS:
            problems.append(
                f"{name}: copies diverge across repos at their registered refs "
                f"({cited}); reference was {reference_repo}"
            )
            continue

        # forked / forked-code: diverging is expected; it must be a REGISTERED
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


def run_check(fleet_root: Path, repo_refs: dict[str, str] | None = None) -> int:
    repo_refs = REPO_REFS if repo_refs is None else repo_refs
    problems = check_drift(fleet_root, repo_refs)
    refs_cited = ", ".join(f"{repo}@{ref}" for repo, ref in repo_refs.items())
    # Rule 4.10, applied to this gate's own output: state exactly what was
    # read, not just the verdict — a run that silently scanned a different
    # scope than last time must not look identical to a real pass/regression.
    print(  # noqa: T201
        f"security-fork-drift: fleet root {fleet_root}, {len(REGISTRY)} registered "
        f"file(s), read at [{refs_cited}]"
    )
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


def _init_git_repo(root: Path, files: dict[str, str]) -> None:
    """A tiny real git repo with `files` committed on a `main` branch.

    Used only by the self-test, so `check_drift`'s ref-reading path is
    exercised against real git plumbing rather than a stub.
    """
    root.mkdir(parents=True, exist_ok=True)

    def run(*args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(  # noqa: S603
            ["git", "-C", str(root), *args],  # noqa: S607
            check=True,
            capture_output=True,
        )

    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "test")
    run("checkout", "-q", "-b", "main")
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        run("add", rel)
    if files:
        run("commit", "-q", "-m", "init")
    else:
        run("commit", "-q", "-m", "init", "--allow-empty")


def _commit(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(["git", "-C", str(root), "add", rel], check=True, capture_output=True)  # noqa: S603, S607
    subprocess.run(  # noqa: S603
        ["git", "-C", str(root), "commit", "-q", "-m", "update"],  # noqa: S607
        check=True,
        capture_output=True,
    )


def _self_test_vendored(root: Path, refs: dict[str, str], failures: list[str]) -> None:
    """Vendored-kind cases: byte-exact at the ref, always. Split out of
    ``_self_test`` (PLR0915 — one function covering both kinds ran past the
    fleet's 50-statement cap, the same structural discipline this batch's
    gates enforce on everything else)."""
    REGISTRY["vendored-thing.py"] = {
        "_kind": "vendored",
        "RepoA": "sub/thing.py",
        "RepoB": "sub/thing.py",
        "RepoC": "sub/thing.py",
    }
    expect(failures, check_drift(root, refs) == [], "identical vendored copies must not drift")

    # A DIRTY WORKING TREE must not affect the verdict — this is the exact
    # bug (Factory#729) this rewrite exists to close. Edit the file on disk
    # WITHOUT committing; the gate must still read the last commit via git
    # show and see no drift.
    (root / "RepoB" / "sub" / "thing.py").write_text("SAFE = 0  # uncommitted, not a real change\n")
    expect(
        failures,
        check_drift(root, refs) == [],
        "an uncommitted working-tree edit must NOT be seen as drift (Factory#729)",
    )
    # Restore the working tree so later commits are made against a matching base.
    (root / "RepoB" / "sub" / "thing.py").write_text("SAFE = 1\n")

    # A repo with no copy of the path at its ref is skipped, not a failure.
    _init_git_repo(root / "RepoD_no_copy", {})
    REGISTRY["vendored-thing-optional.py"] = {
        "_kind": "vendored",
        "RepoA": "sub/thing.py",
        "RepoD": "sub/thing.py",
    }
    refs["RepoD"] = "main"
    expect(
        failures,
        check_drift(root, refs) == [],
        "a repo with no copy of the path at its ref must be skipped, not flagged",
    )
    del REGISTRY["vendored-thing-optional.py"]
    del refs["RepoD"]

    # Mutation: RepoB gets a REAL commit reverting the fix.
    _commit(root / "RepoB", "sub/thing.py", "SAFE = 0  # bug reintroduced\n")
    problems = check_drift(root, refs)
    expect(failures, len(problems) == 1, f"exactly one vendored entry must drift, got {problems}")
    expect(
        failures, run_check(root, refs) == 1, "run_check must fail when a vendored fork diverges"
    )
    _commit(root / "RepoB", "sub/thing.py", "SAFE = 1\n")
    expect(
        failures, run_check(root, refs) == 0, "run_check must pass once vendored copies match again"
    )

    REGISTRY.clear()


def _self_test_forked(root: Path, failures: list[str]) -> None:
    """Forked-kind cases: registered-divergence model, same ref-reading."""
    _init_git_repo(root / "ForkA", {"sub/forked.py": "BASE = 1\n"})
    _init_git_repo(root / "ForkB", {"sub/forked.py": "BASE = 1\n"})
    fork_refs = {"ForkA": "main", "ForkB": "main"}
    REGISTRY["forked-thing.py"] = {
        "_kind": "forked",
        "ForkA": "sub/forked.py",
        "ForkB": "sub/forked.py",
    }
    expect(
        failures,
        check_drift(root, fork_refs) == [],
        "identical forked copies must not drift (nothing to register)",
    )

    # Case: a NEW, unregistered divergence, committed for real -> fails.
    _commit(root / "ForkB", "sub/forked.py", "BASE = 1\nEXTRA_FEATURE = True\n")
    problems = check_drift(root, fork_refs)
    expect(
        failures,
        len(problems) == 1 and "NO registered divergence" in problems[0],
        f"an unregistered forked divergence must be flagged, got {problems}",
    )
    expect(
        failures,
        run_check(root, fork_refs) == 1,
        "run_check must fail on an unregistered forked divergence",
    )

    # Register it with the exact current (committed) digests -> passes.
    a_digest = sha256((root / "ForkA" / "sub" / "forked.py").read_bytes()).hexdigest()
    b_digest = sha256((root / "ForkB" / "sub" / "forked.py").read_bytes()).hexdigest()
    FORK_DIVERGENCES.append(
        {
            "name": "forked-thing.py",
            "digests": {"ForkA": a_digest, "ForkB": b_digest},
            "reason": "ForkB carries an extra feature, deliberately not ported",
            "issue": "FAKE-1",
        }
    )
    expect(
        failures,
        run_check(root, fork_refs) == 0,
        "run_check must pass once the divergence is registered with an issue ref",
    )

    # Case: the registered divergence then drifts FURTHER (a new commit) ->
    # must fail again, not stay silently green.
    _commit(root / "ForkB", "sub/forked.py", "BASE = 1\nEXTRA_FEATURE = True\nEVEN_MORE = 2\n")
    problems = check_drift(root, fork_refs)
    expect(
        failures,
        len(problems) == 1 and "do NOT match the registered snapshot" in problems[0],
        f"a divergence that moves past its registration must be re-flagged, got {problems}",
    )

    # Case: a registration with NO issue ref fails outright, same as Gate 5.
    FORK_DIVERGENCES.clear()
    new_b_digest = sha256((root / "ForkB" / "sub" / "forked.py").read_bytes()).hexdigest()
    FORK_DIVERGENCES.append(
        {
            "name": "forked-thing.py",
            "digests": {"ForkA": a_digest, "ForkB": new_b_digest},
            "reason": "no issue ref on purpose",
            "issue": "",
        }
    )
    expect(
        failures,
        run_check(root, fork_refs) == 1,
        "a registered divergence with no issue ref must fail, not pass",
    )


_SHELL_A = """#!/usr/bin/env bash
# PFactory's own inventory of hub-pinned workflows.
set -euo pipefail
if ! printf '%s' "${sha}" | grep -qE '^[0-9a-f]{40}$'; then exit 1; fi
"""

# Same executable body, different header prose: a doc-only edit of the kind a
# repo makes when it adds a hub-pinned workflow. Must NOT be drift.
_SHELL_B_COMMENT_ONLY = """#!/usr/bin/env bash
# TFactory's own inventory of hub-pinned workflows, which is a longer list.
#
#   factory-common-drift.yml  factory_common/.hub-sha  -> codeload tarball
set -euo pipefail
if ! printf '%s' "${sha}" | grep -qE '^[0-9a-f]{40}$'; then exit 1; fi
"""


def _self_test_forked_code(root: Path, failures: list[str]) -> None:
    """forked-code kind: comments are noise, the executable body is the assertion.

    The pair of mutations below is the whole reason this kind exists
    (Factory#819), so both directions are proved rather than one:
    a header-only edit must stay green, and a one-character change to the
    40-hex check must go red.
    """
    _init_git_repo(root / "CodeA", {"guard.sh": _SHELL_A})
    _init_git_repo(root / "CodeB", {"guard.sh": _SHELL_B_COMMENT_ONLY})
    refs = {"CodeA": "main", "CodeB": "main"}
    REGISTRY["guard.sh"] = {"_kind": "forked-code", "CodeA": "guard.sh", "CodeB": "guard.sh"}

    expect(
        failures,
        sha256(_SHELL_A.encode()).hexdigest() != sha256(_SHELL_B_COMMENT_ONLY.encode()).hexdigest(),
        "sanity: the two fixtures really are different FILES, so a green verdict "
        "below is the stripping working and not two identical inputs",
    )
    expect(
        failures,
        check_drift(root, refs) == [],
        "a comment-only difference must not be drift under forked-code",
    )

    # Mutation: one character of the executable body, in ONE repo. `{40}` ->
    # `{4}` would let a 4-hex pin through; nothing else in the file changes.
    _commit(root / "CodeB", "guard.sh", _SHELL_B_COMMENT_ONLY.replace("{40}", "{4}"))
    problems = check_drift(root, refs)
    expect(
        failures,
        len(problems) == 1 and "NO registered divergence" in problems[0],
        f"a one-character executable change in one repo must be flagged, got {problems}",
    )
    expect(failures, run_check(root, refs) == 1, "run_check must fail on forked-code logic drift")

    # And the registered-divergence path works for this kind too: register the
    # CODE digests and the same state passes.
    def code_digest(repo: str) -> str:
        body = strip_shell_comments(read_ref(root / repo, "main", "guard.sh") or b"")
        return sha256(body).hexdigest()

    digests = {repo: code_digest(repo) for repo in ("CodeA", "CodeB")}
    FORK_DIVERGENCES.append(
        {"name": "guard.sh", "digests": digests, "reason": "registered", "issue": "FAKE-2"}
    )
    expect(
        failures,
        run_check(root, refs) == 0,
        "a registered forked-code divergence with an issue ref must pass",
    )
    # ...and a FURTHER comment-only edit must not invalidate that registration,
    # which is the churn `forked-code` exists to avoid.
    _commit(
        root / "CodeB",
        "guard.sh",
        _SHELL_B_COMMENT_ONLY.replace("{40}", "{4}").replace(
            "# TFactory's", "# one more inventory line\n# TFactory's"
        ),
    )
    expect(
        failures,
        run_check(root, refs) == 0,
        "a comment-only edit must not invalidate a registered forked-code divergence",
    )

    REGISTRY.clear()
    FORK_DIVERGENCES.clear()


def _self_test_strip_shell_comments(failures: list[str]) -> None:
    """The stripper must not eat anything executable."""
    expect(
        failures,
        strip_shell_comments(b'#!/bin/sh\n# c\n\necho "a # b"\n') == b'#!/bin/sh\necho "a # b"\n',
        "a `#` inside a string, and the shebang, must both survive",
    )
    expect(
        failures,
        strip_shell_comments(b"#!/bin/sh\ncmd --flag  # trailing\n")
        == b"#!/bin/sh\ncmd --flag  # trailing\n",
        "a trailing comment on a real command must not be stripped (the line is executable)",
    )
    expect(
        failures,
        strip_shell_comments(b"#!/bin/bash\n") != strip_shell_comments(b"#!/bin/sh\n"),
        "swapping the interpreter is an executable change and must be visible",
    )


def _self_test() -> int:
    failures: list[str] = []

    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)  # noqa: S607
    except (OSError, subprocess.CalledProcessError):
        print("SELF-TEST SKIPPED: git binary not available")  # noqa: T201
        return 0

    with temp_repo() as root:
        for repo in ("RepoA", "RepoB", "RepoC"):
            _init_git_repo(root / repo, {"sub/thing.py": "SAFE = 1\n"})
        # `local` refs, not `origin/`: this self-test has no remote, so it
        # points repo_refs at the local `main` — the mechanism under test is
        # "read a named ref via git show", not the specific ref string.
        refs = {"RepoA": "main", "RepoB": "main", "RepoC": "main"}

        registry_backup = dict(REGISTRY)
        divergences_backup = list(FORK_DIVERGENCES)
        try:
            REGISTRY.clear()
            FORK_DIVERGENCES.clear()
            _self_test_vendored(root, refs, failures)
            _self_test_forked(root, failures)
            REGISTRY.clear()
            FORK_DIVERGENCES.clear()
            _self_test_forked_code(root, failures)
            _self_test_strip_shell_comments(failures)
        finally:
            REGISTRY.clear()
            REGISTRY.update(registry_backup)
            FORK_DIVERGENCES.clear()
            FORK_DIVERGENCES.extend(divergences_backup)

    return report_self_test(failures)


# --fleet-root plus a per-repo --ref: the CLI takes both a directory AND a ref
# per repo, unlike the single-repo gates above it, because this comparator's
# whole point is reading several repos at once (see REPO_REFS's docstring).
def main(argv: list[str] | None = None) -> int:
    parser = gate_argparser(__doc__)
    parser.add_argument(
        "--fleet-root",
        help=(
            "directory containing Factory/, PFactory/, AIFactory/, TFactory/, "
            "CFactory/ git checkouts"
        ),
    )
    parser.add_argument(
        "--ref",
        action="append",
        default=[],
        metavar="REPO=REF",
        help=(
            "override the ref a repo is read at, e.g. --ref PFactory=HEAD. "
            "Default is REPO_REFS (origin/main for the hub, origin/dev for "
            "the services) — the right default for an ad-hoc run against a "
            "real fleet checkout on a dev machine, where a LOCAL branch may "
            "have drifted from what actually shipped (Factory#729). In CI, "
            "where actions/checkout guarantees the working tree already IS "
            "the intended ref, pass --ref <repo>=HEAD for each freshly "
            "checked-out repo instead, which sidesteps needing a "
            "remote-tracking ref to exist at all."
        ),
    )
    early, args = parse_or_self_test(parser, argv, _self_test)
    if early is not None:
        return early
    assert args is not None  # noqa: S101 - parse_or_self_test guarantees this when early is None
    if not args.fleet_root:
        parser.error("--fleet-root is required (or pass --self-test)")
    repo_refs = dict(REPO_REFS)
    for override in args.ref:
        repo, _, ref = override.partition("=")
        if not repo or not ref:
            parser.error(f"--ref must be REPO=REF, got: {override!r}")
        repo_refs[repo] = ref
    return run_check(Path(args.fleet_root), repo_refs)


if __name__ == "__main__":
    sys.exit(main())
