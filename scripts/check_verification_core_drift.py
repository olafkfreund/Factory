#!/usr/bin/env python3
"""Fail CI when a service's vendored verification-core modules drift from the hub.

The canonical copies of the Factory verification-core layer live in this hub at
``scripts/`` (the single source of truth — see ``scripts/README-verification-core.md``).
PFactory, AIFactory and TFactory each hand-vendor a subset of these modules into
their own backends (at service-specific paths). This guard stops those copies
silently diverging from the hub canonical.

The canonical set is exactly the deduped verification-core surface (epic
Factory#154, issue Factory#158):

    verification_gate.py     RFC-0006 never-overclaim gate
    verification_profiles.py verification profile selection
    verification_runner.py   verification lane runner
    factory_sandbox.py       unprivileged-sandbox helper
    nix_provisioner.py       per-task Nix environment provisioner

The check is **byte-exact and directional** (hub canonical -> service copy): for
every canonical module a service is known to vendor, the matching file in the
service tree must exist and be byte-identical to the hub copy. Because the three
services vendor *different subsets* at *different paths*, the per-service vendored
layout is described by :data:`SERVICE_LAYOUTS`; only modules a service actually
carries are checked (a service that does not vendor a module is not penalised for
its absence).

Two guards run alongside the byte comparison, because the comparison alone can
only see what the layout points it at (Factory#523):

* :func:`_unmapped_modules` — a module declared canonical that NO service maps.
* :func:`_stray_vendored_copies` — the inverse: a file in the service tree whose
  basename is a canonical module and which THIS service's layout maps nowhere.
  Deleting one line from :data:`SERVICE_LAYOUTS` used to un-gate a vendored file
  silently; the copy stayed on disk, kept being imported and was free to drift,
  and the only trace was the module count in the success line dropping by one.

A THIRD guard covers what byte comparison structurally cannot (Factory#590):

* :func:`ported_ratchet_problems` — the fork-with-a-citation case. Some shared
  code is not vendored byte-exact and never will be: the five lint ratchets are
  structurally different programs (five package layouts, five mypy invocation
  strategies), each carrying a docstring that cites the hub original. Byte
  equality is the wrong demand there, so this gate asks the only question that
  IS answerable — does the fork IMPORT the shared rules from the byte-exact
  canonical it sits next to, or has it restated them inline? Nine inline
  restatements of one rule are what cost five PRs and shipped a half-fix.

Every verdict this gate emits — pass and fail alike — carries the bytes it was
derived from (path plus sha256 of each side), and the success report enumerates
what it compared rather than counting it. A count is not a check: nobody
re-derives a headline number, so a scope loss hides inside it. See
``docs/dev/gate-honesty.md`` (Factory#504).

This mirrors ``scripts/check_factory_github_drift.py``: pure stdlib, no third-
party imports, hard-fail (exit 1) on real drift.

RECONCILED (Factory#158): the live service copies were restored to byte-match
this canonical, behaviour-preserving — where a service copy genuinely carried more
than the hub (the nix_provisioner Tier C helpers), the canonical adopted the
superset rather than dropping tested behaviour. The gate is green fleet-wide and
each affected service runs it in its own CI to block re-divergence. See
``scripts/README-verification-core.md``.

Usage:
    # Check a known service checkout against the hub canonical:
    python scripts/check_verification_core_drift.py \
        --service tfactory --root /path/to/TFactory

    # List which modules each known service is expected to vendor:
    python scripts/check_verification_core_drift.py --list

    # Override the canonical root explicitly (default: this script's scripts/):
    python scripts/check_verification_core_drift.py \
        --canonical scripts --service aifactory --root /path/to/AIFactory

    # Run the built-in self-test (no repo state needed):
    python scripts/check_verification_core_drift.py --self-test

Exit codes:
    0 - service copies match the canonical (or self-test/list succeeded)
    1 - drift detected (or self-test failed)
    2 - bad invocation / missing canonical tree / unknown service
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
import tempfile
from pathlib import Path

# Sibling module in this same scripts/ directory. Consumers run this gate out of
# a full hub checkout, so it resolves there too (see gate_evidence's docstring).
from gate_evidence import digest

# The canonical layer is exactly the deduped verification-core surface (epic
# Factory#154, issue Factory#158). These filenames are the canonical module names
# as they live, flat, in the hub's scripts/ directory.
CANONICAL_MODULES: tuple[str, ...] = (
    "verification_gate.py",
    "factory_sandbox.py",
    "nix_provisioner.py",
    # Added 2026-07-28 (Factory#400). These are not verification-core modules;
    # they are hub shared libraries that were vendored into 3-4 services with NO
    # gate of any kind, so nothing detected them diverging and they had. The
    # mechanism this gate implements — canonical modules living flat in scripts/,
    # per-service paths, byte-exact — is exactly what they need, and a second
    # near-identical script would be another fork of the logic Factory#403 is
    # about. The gate's NAME is now narrower than its job; renaming it means
    # touching the workflow in every consumer, tracked separately.
    "artifact_store.py",  # RFC-0016
    "cost_router_core.py",  # RFC-0014
    # Added 2026-07-28 (Factory#403). The five per-repo lint ratchets had
    # forked the same three rules; Factory#410 extracted them into a single
    # canonical module and each service vendors it. Without a gate that is
    # five copies free to drift again, which is the problem #403 opened on.
    "ratchet_helpers.py",
    # Added 2026-07-30 (Factory#477). job_dispatch.py's own docstring claimed it
    # was vendored "byte-identically", and it was not: AIFactory's copy had drifted
    # in BOTH directions and no workflow compared them. The cost was concrete —
    # the #1107 pod-label defect (task pods joining their service's Service and
    # answering real traffic with connection refused) had to be found and fixed
    # twice, once per copy, and a fresh vendoring of the hub copy would have
    # re-introduced it a fourth time. Registered here only AFTER the two copies
    # were reconciled and AIFactory's pin bumped, per the standing ordering rule.
    "job_dispatch.py",
    # Added 2026-08-08 (Factory#638). The far half of job_dispatch.trace_env: the
    # bootstrap a dispatched Job calls to join the run's trace and emit. It lived
    # in AIFactory until TFactory's verify Job needed the same emitter, and the
    # cheap move — hand-copying it across — is precisely the fork-with-a-citation
    # this gate cannot see. Two copies of the bounded-exit reasoning (the 20.54s
    # -> 4.52s measurement that is the whole reason for the shape) would drift
    # the first time either was touched.
    #
    # Registered only AFTER both consumers vendored the file and bumped their
    # pins, per the standing ordering rule and because _unmapped_modules below
    # rejects a canonical module no service maps.
    "job_tracing.py",
)
# Removed 2026-07-28 (Factory#401): verification_profiles.py (397L) and
# verification_runner.py (120L) were listed here but mapped by NO service, so
# nothing vendored them and the gate never compared them anywhere. Declaring a
# module canonical when it is shared with nobody is not governance, it is
# paperwork - and it inflated the "OK: matches (N modules)" count with modules
# that were never checked. The files still live in scripts/; they are simply no
# longer claimed to be a vendored contract. _unmapped_modules() below now makes
# this state impossible to reach again silently.

# Per-service vendored layout: which canonical modules each service hand-vendors,
# and the path (relative to that service's repo root) where its copy lives. The
# services deliberately vendor *different subsets* at *different paths*, so this
# map is the contract for what the gate looks for. A service entry that omits a
# canonical module simply means that service does not vendor it (and so it is not
# checked there) — only divergence of a *vendored* copy is drift.
SERVICE_LAYOUTS: dict[str, dict[str, str]] = {
    # PFactory was removed in Factory#401 as dead config (it vendored none of the
    # verification-core modules and no workflow invoked the gate). It is back
    # because it DOES vendor two of the shared libraries added in Factory#400 —
    # which is precisely why an empty layout must never read as a pass.
    "pfactory": {
        "ratchet_helpers.py": "scripts/ratchet_helpers.py",
        "artifact_store.py": "apps/backend/runners/artifact_store.py",
        "cost_router_core.py": "apps/backend/plan/emit/cost_router_core.py",
    },
    "aifactory": {
        "ratchet_helpers.py": "scripts/ratchet_helpers.py",
        "factory_sandbox.py": "apps/backend/core/factory_sandbox.py",
        "nix_provisioner.py": "apps/backend/core/nix_provisioner.py",
        "artifact_store.py": "apps/backend/core/artifact_store.py",
        "cost_router_core.py": "apps/backend/core/cost_router_core.py",
        # Factory#477, extended by Factory#483. No longer the only consumer:
        # TFactory vendors it too, at its own path below. PFactory is still
        # deliberately absent and needs no copy — it runs a bounded pooled-worker
        # model rather than Job-per-task (RFC-0016 §5(c), PFactory#218), so it
        # builds no Job manifest at all. That is an absence with a reason, not an
        # oversight; mapping it to a path that does not exist is what Factory#401
        # removed as dead config.
        "job_dispatch.py": "apps/backend/core/job_dispatch.py",
        # Factory#638. This file WAS AIFactory's core/tracing_bootstrap.py; it is
        # now the hub canonical, vendored back here under the canonical name. The
        # old path is gone rather than left as a shim, because a shim is a second
        # name for shared code that this gate cannot see.
        "job_tracing.py": "apps/backend/core/job_tracing.py",
    },
    # CFactory vendors exactly one canonical module and nothing else. It was
    # deliberately left unregistered when ratchet_helpers.py was gated
    # (Factory#412) because it had no workflow to run this gate, and a service
    # the hub cannot actually check is the dead config Factory#401 removed.
    # Registered here together with the workflow that invokes it (CFactory#233).
    "cfactory": {
        "ratchet_helpers.py": "scripts/ratchet_helpers.py",
    },
    "tfactory": {
        "ratchet_helpers.py": "scripts/ratchet_helpers.py",
        "verification_gate.py": "apps/backend/agents/verification_gate.py",
        "nix_provisioner.py": "apps/backend/tools/runners/nix_provisioner.py",
        "artifact_store.py": "apps/backend/tools/runners/artifact_store.py",
        # Factory#483. TFactory used to restate this module's naming, labelling
        # and hardening rules by hand across its Job builders, under comments
        # naming the hub file — a fork with a citation, which this gate is
        # structurally unable to catch because there is no vendored file to
        # compare. It now vendors the file and imports the rules.
        #
        # Registered here only AFTER TFactory#907 landed the copy and bumped its
        # pin, per the standing ordering rule: a module registered for a service
        # that does not yet carry it turns every PR in that repo red.
        "job_dispatch.py": "apps/backend/tools/runners/job_dispatch.py",
        # Factory#638. TFactory's verify Job is the second boundary a trace
        # stopped at. It needed BOTH halves — trace_env on the manifest and an
        # emitter inside the Job — and the emitter had to be this shared file
        # rather than a copy, or the two would have diverged from the first fix.
        "job_tracing.py": "apps/backend/tools/runners/job_tracing.py",
    },
}

# ACKNOWLEDGED FORKS (Factory#590), as opposed to the byte-exact vendorings in
# SERVICE_LAYOUTS above. Each of these files carries a docstring citing the hub's
# scripts/ratchet_lint.py as its origin, and each has genuinely diverged: the
# five ratchets gate different package layouts and run mypy five different ways
# (in place with MYPYPATH, from inside the package with --explicit-package-bases,
# from a temp copy next to the file, from a temp dir, from a git worktree). That
# divergence is real and load-bearing, so byte equality is the wrong demand and
# registering them in SERVICE_LAYOUTS would simply turn every repo red.
#
# What is NOT legitimately divergent is the RULES, and those already have a
# byte-exact canonical next door: scripts/ratchet_helpers.py, which every one of
# these services vendors and this gate already compares. So the question this
# guard asks is the answerable one — does the fork IMPORT the shared rules, or
# has it restated them inline?
#
# It is asked because inline restatement is exactly what happened. `ruff_counts()`
# read empty ruff stdout as "no violations" when a clean run prints "[]" and empty
# stdout means ruff FAILED, so a blocking gate reported green on a linter that
# never ran. Found in TFactory#951, found independently a day later in
# PFactory#455, and the sweep found it in all five repos in BOTH the ruff and the
# mypy half: nine guards, five PRs, and TFactory#951 shipped a half-fix because
# the mypy counter sat directly below the ruff one with the identical shape.
PORTED_RATCHETS: dict[str, str] = {
    "pfactory": "scripts/ratchet_lint.py",
    "tfactory": "scripts/ratchet_lint.py",
    "cfactory": "scripts/ratchet_lint.py",
    # AIFactory's fork does not even share the filename, which is part of why no
    # byte-exact mechanism was ever going to reach it.
    "aifactory": "scripts/cq_ratchet.py",
}

# The hub's own ratchet is the FIFTH fork, and it had the same defect (fixed in
# Factory#589). It cannot be checked by this map — the map runs against a SERVICE
# checkout — so it is named here and asserted by the hub's own test suite
# (tests/test_check_verification_core_drift.py), which runs on every hub PR. Four
# out of five would be the scope loss this gate exists to catch.
HUB_PORTED_RATCHET = "scripts/ratchet_lint.py"

# Names a ported ratchet must import from ratchet_helpers rather than restate.
# Growing this tuple is how a future shared rule gets enforced across the forks:
# extract it into the canonical, re-vendor, rewire the forks, THEN add it here.
# `ruff_findings` added 2026-08-08 (Factory#648), and it lands LAST for the
# reason the header above states: this checker floats at hub main while each
# consumer's CANONICAL stays at its own HUB_PIN_SHA, so a rule registered before
# the forks rewire turns every PR in four repos red. Order was: hub canonical,
# four consumer re-vendor+pin PRs, then this.
_REQUIRED_RATCHET_RULES: tuple[str, ...] = ("require_tool_ran", "ruff_findings")

# ponytail: a verbatim-substring check, not a semantic one. It catches the idiom
# being COPIED BACK, which is the observed failure mode (the nine restatements
# were byte-identical apart from their comments) and nothing more — a re-spelling
# such as `res.returncode >= 2` slips past. Upgrade path if that ever happens: an
# ast walk for a Compare on a `.returncode` attribute inside a function that also
# calls subprocess. Not built, because the cheap check covers what actually broke.
_RESTATED_RULES: tuple[tuple[str, str], ...] = (
    ("res.returncode not in (0, 1)", "require_tool_ran"),
)

# Default canonical root, relative to the repo that contains this script: the
# hub's scripts/ directory (i.e. the directory this file lives in).
_DEFAULT_CANONICAL = Path(__file__).resolve().parent

# Exit code returned for a bad invocation (missing canonical / unknown service).
_EXIT_BAD_INVOCATION = 2

# Directories the stray-copy scan never walks. Dot-directories cover .git, .venv
# and the .claude/worktrees/ trees a local checkout accumulates (a worktree holds
# a second copy of every vendored module and would be reported as a stray on
# every developer machine). The named entries are dependency and build trees no
# service imports its own vendored modules from. This prune list is the scan's
# scope, so the report prints it: a scan whose blind spots are undocumented is
# the silent scope loss this guard exists to catch, one level up.
_SCAN_PRUNE: frozenset[str] = frozenset(
    {"node_modules", "__pycache__", "venv", "site-packages", "dist", "build", "target"}
)


def _emit(message: str) -> None:
    # This is a CLI drift gate; its stdout report IS its purpose, so the T20
    # (no-print) rule is intentionally suppressed at the single output sink.
    print(message)  # noqa: T201


def _unmapped_modules() -> list[str]:
    """Canonical modules that no service in SERVICE_LAYOUTS vendors."""
    mapped = {module for layout in SERVICE_LAYOUTS.values() for module in layout}
    return [m for m in CANONICAL_MODULES if m not in mapped]


def _stray_vendored_copies(service_root: Path, layout: dict[str, str]) -> list[str]:
    """Files in the service tree that look vendored but *layout* maps nowhere.

    The inverse of :func:`_unmapped_modules`, and the guard Factory#523 is about.
    ``check_drift`` can only compare what the layout points it at, so removing a
    single line from :data:`SERVICE_LAYOUTS` removes the file from the gate's
    world entirely: it stays on disk, stays imported, and drifts unobserved while
    the gate reports success. Asking the question from the tree's side instead of
    the layout's side catches that, and catches the original Factory#477
    condition too (AIFactory carried ``job_dispatch.py`` for months with no
    mapping registered anywhere).
    """
    canonical_names = set(CANONICAL_MODULES)
    mapped = {(service_root / rel).resolve() for rel in layout.values()}
    strays: list[str] = []
    for dirpath, dirnames, filenames in os.walk(service_root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in _SCAN_PRUNE)
        for name in sorted(filenames):
            if name not in canonical_names:
                continue
            found = Path(dirpath) / name
            if found.resolve() in mapped:
                continue
            rel = found.relative_to(service_root)
            strays.append(
                f"{name}: the service carries {rel} but this layout maps it nowhere — "
                "nothing compares it, so it is free to drift (add it to "
                "SERVICE_LAYOUTS or delete the copy)"
            )
    # Sorted: os.walk order is filesystem order, and a gate whose report reorders
    # between runs is one nobody can diff.
    return sorted(strays)


def ported_ratchet_problems(root: Path, rel_path: str) -> list[str]:
    """Problems with an acknowledged fork at *rel_path* under *root*.

    Three questions, in the order they can go wrong:

    1. Does the file exist? A registered fork that vanished means the map is
       stale, and a stale map is a check that silently stopped running — the
       Factory#401 condition, one level up.
    2. Does it IMPORT each name in :data:`_REQUIRED_RATCHET_RULES` from
       ``ratchet_helpers``, and CALL it at least once? The call matters
       separately because an unused import would normally be caught by ruff F401
       and these files are outside every repo's ruff scope (Factory#590), so an
       import added only to satisfy this gate would sit there unreferenced.
    3. Does it restate a rule inline that it is supposed to import? This is the
       one with teeth: the fork can import the canonical AND keep its old copy
       of the rule, and then the canonical fix reaches it and changes nothing.

    Parsed with :mod:`ast` rather than grepped for the import half, so a name
    inside a comment or a docstring cannot satisfy the requirement.
    """
    path = root / rel_path
    if not path.is_file():
        return [
            f"{rel_path}: registered in PORTED_RATCHETS but absent — either the fork moved "
            "(update the map) or this service no longer has one (remove the entry); a map "
            "pointing at nothing is a check that stopped running"
        ]
    source = path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"{rel_path}: could not be parsed ({exc})"]

    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "ratchet_helpers"
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    problems = [
        f"{rel_path}: does not import {rule!r} from ratchet_helpers — the shared ratchet "
        "rules are the byte-exact canonical this fork sits next to; restating them is how "
        "one defect became nine (Factory#590)"
        for rule in _REQUIRED_RATCHET_RULES
        if rule not in imported
    ]
    problems.extend(
        f"{rel_path}: imports {rule!r} but never calls it — an import nothing uses satisfies "
        "this gate while the fork still measures its own way"
        for rule in _REQUIRED_RATCHET_RULES
        if rule in imported and rule not in called
    )
    problems.extend(
        f"{rel_path}: restates the shared rule inline ({idiom!r}) instead of calling "
        f"{rule!r} — a fix to the canonical would not reach this copy"
        for idiom, rule in _RESTATED_RULES
        if idiom in source
    )
    return problems


def compared_evidence(
    canonical_root: Path,
    service_root: Path,
    layout: dict[str, str],
) -> list[str]:
    """One line per module this run compared, each carrying the bytes it read.

    This is the enumeration that replaces the module count in the success line.
    ``OK: aifactory matches the canonical (6 vendored module(s))`` is a headline
    nobody re-derives — it read 6 the day a seventh was dropped from the layout,
    and it read 5 the day one was, and neither is legible as a defect. A list is
    falsifiable at a glance.
    """
    return [
        f"{module} -> {rel_path} "
        f"[canonical {digest(canonical_root / module)} | "
        f"service {digest(service_root / rel_path)}]"
        for module, rel_path in sorted(layout.items())
    ]


def check_drift(
    canonical_root: Path,
    service_root: Path,
    layout: dict[str, str],
) -> list[str]:
    """Return drift problems comparing a service tree against the hub canonical.

    Directional and byte-exact: for every (module -> vendored path) pair in
    *layout*, the file under *service_root* must exist and match the canonical
    module under *canonical_root* byte-for-byte. Modules the service does not
    vendor (absent from *layout*) are not checked.

    Checked FIRST: that every canonical module is vendored by SOMEONE. This is
    the inverse of the factory-github gate's guard (Factory#397). There, the
    canonical is a dedicated directory, so the risk is a canonical file the
    contract omits. Here the canonical root is the hub's scripts/ - a directory
    of ~25 unrelated tools - so "every file must be listed" would be nonsense.
    The equivalent rot is a module DECLARED canonical that no service maps: it is
    unchecked by definition, and it silently inflates the count the gate reports
    as OK.

    Checked SECOND (Factory#523): the inverse — a file in the SERVICE tree whose
    basename is a canonical module and which *layout* maps nowhere. Both guards
    above ask their question from the layout's side, so neither notices a layout
    ENTRY being deleted while the vendored file stays on disk. That mutation used
    to turn the gate green on a deliberately drifted file.
    """
    problems: list[str] = [
        f"{module}: listed in CANONICAL_MODULES but vendored by no service — "
        "nothing compares it anywhere, so declaring it canonical is unenforced"
        for module in _unmapped_modules()
    ]
    problems.extend(_stray_vendored_copies(service_root, layout))
    for module, rel_path in layout.items():
        canonical_file = canonical_root / module
        service_file = service_root / rel_path
        canonical_bytes = canonical_file.read_bytes()
        if not service_file.is_file():
            problems.append(f"{module}: present in canonical, missing in service copy ({rel_path})")
            continue
        if service_file.read_bytes() != canonical_bytes:
            problems.append(
                f"{module}: differs from canonical (byte mismatch at {rel_path}) "
                f"[canonical {digest(canonical_file)} | service {digest(service_file)}]"
            )
    return problems


def run_check(canonical_root: Path, service_root: Path, service: str) -> int:
    """Run the drift check for one service and emit a report. Return an exit code."""
    if not canonical_root.is_dir():
        _emit(f"ERROR: canonical tree not found: {canonical_root}")
        return _EXIT_BAD_INVOCATION
    layout = SERVICE_LAYOUTS.get(service)
    if layout is None:
        _emit(f"ERROR: unknown service {service!r}; known: {', '.join(sorted(SERVICE_LAYOUTS))}")
        return _EXIT_BAD_INVOCATION
    # An empty layout used to return 0 here with "vendors no verification-core
    # modules (nothing to check)" — the Factory#523 mutation taken to its limit,
    # since deleting every entry is just deleting one entry repeatedly. It now
    # falls through: with nothing mapped, the stray-copy scan is the whole check,
    # and a service carrying a vendored file it maps nowhere goes red.
    problems = check_drift(canonical_root, service_root, layout)
    ported = PORTED_RATCHETS.get(service)
    # Kept separate from `problems` so the evidence line below can state the
    # verdict it actually reached. Folding it straight in made that line read
    # "checked that it imports and calls ..." even when the check had FAILED --
    # a success sentence printed regardless of outcome, which is precisely the
    # defect this gate exists to catch (Factory#590).
    ported_problems: list[str] = []
    if ported is not None:
        ported_problems = ported_ratchet_problems(service_root, ported)
        problems.extend(ported_problems)
    _emit(f"verification-core: {service} vs the hub canonical at {canonical_root}")
    _emit("  compared (each line carries the bytes the verdict was read from):")
    for line in compared_evidence(canonical_root, service_root, layout) or ["(no modules mapped)"]:
        _emit(f"    - {line}")
    _emit(
        f"  scanned {service_root} for copies of a canonical module that this "
        "layout maps nowhere; pruned: dot-directories, "
        f"{', '.join(sorted(_SCAN_PRUNE))}"
    )
    if ported is not None:
        _rules = ", ".join(_REQUIRED_RATCHET_RULES)
        if ported_problems:
            _emit(
                f"  acknowledged fork {ported} [{digest(service_root / ported)}]: FAILED "
                f"({len(ported_problems)} problem(s) listed below) — it must import and call "
                f"{_rules} from ratchet_helpers rather than restating them"
            )
        else:
            _emit(
                f"  acknowledged fork {ported} [{digest(service_root / ported)}]: imports and "
                f"calls {_rules} from ratchet_helpers rather than restating them "
                "(NOT byte-compared — these forks legitimately differ)"
            )
    if problems:
        _emit(f"verification-core drift — {service} diverges from the hub canonical:")
        for problem in problems:
            _emit(f"  - {problem}")
        _emit(
            "\nThe canonical layer is the Factory hub's scripts/ "
            "(see scripts/README-verification-core.md). There is NO allowed-divergence "
            "list: these copies are byte-identical or the gate is red. Two ways out, "
            "and only two:\n"
            "  1. The service copy is wrong -> re-vendor it from the canonical:\n"
            "       cp <factory-hub>/scripts/<module> <service>/<vendored path above>\n"
            "  2. The CHANGE is wanted -> land it in the hub canonical first via a\n"
            "     CODEOWNERS-reviewed PR, re-vendor into EVERY consumer as in (1),\n"
            "     then bump HUB_PIN_SHA in each consumer's verification-core-drift\n"
            "     workflow to the hub commit that carries it.\n"
            "Never hand-edit one copy to make this gate pass: that is the silent "
            "divergence the gate exists to catch.\n"
            "\nAn ACKNOWLEDGED FORK problem above (a ratchet that restates a shared rule "
            "instead of importing it) is a different fix: the fork is allowed to differ, "
            "so do NOT re-vendor it. Delete the inline copy of the rule and call the "
            "canonical helper from scripts/ratchet_helpers.py instead. If the rule genuinely "
            "cannot be shared, that belongs in the hub canonical as a parameter, not as a "
            "fifth private copy (Factory#590)."
        )
        return 1
    _emit(
        f"OK: {service} matches the canonical verification-core layer — every module "
        "enumerated above matched, and the tree carries no unmapped copy."
    )
    return 0


def _list_layouts() -> int:
    """Print the per-service vendored layout (what the gate looks for where)."""
    _emit("verification-core canonical modules (hub scripts/):")
    for module in CANONICAL_MODULES:
        _emit(f"  - {module}")
    _emit("\nper-service vendored layout:")
    for service in sorted(SERVICE_LAYOUTS):
        layout = SERVICE_LAYOUTS[service]
        if not layout:
            _emit(f"  {service}: (vendors none)")
            continue
        _emit(f"  {service}:")
        for module, rel_path in sorted(layout.items()):
            _emit(f"    {module} -> {rel_path}")
    _emit(
        "\nacknowledged forks (NOT byte-compared — checked only for importing and "
        f"calling {', '.join(_REQUIRED_RATCHET_RULES)} from ratchet_helpers):"
    )
    for service in sorted(PORTED_RATCHETS):
        _emit(f"  {service}: {PORTED_RATCHETS[service]}")
    _emit(f"  factory (hub, asserted by the hub's own suite): {HUB_PORTED_RATCHET}")
    return 0


def _materialise(canonical: Path, layout: dict[str, str], target: Path) -> Path:
    """Build a service tree under *target* that matches *canonical* byte-for-byte."""
    for module, rel_path in layout.items():
        path = target / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((canonical / module).read_bytes())
    return target


def _scope_self_test(canonical: Path, root: Path, layout: dict[str, str]) -> list[str]:
    """Cases that move the gate's SCOPE rather than its subject (Factory#523).

    Split out of :func:`_self_test` to keep either function readable, and because
    these four cases are one idea: the checks above all mutate the files being
    compared, and none of them can see the gate being pointed at fewer files.
    """
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    # An empty layout over a tree that carries vendored files is RED. This used
    # to assert the opposite ("empty layout must not drift"), which is #523
    # written down as a requirement: the tree carries two canonical modules, the
    # layout maps none of them, and that was a pass.
    carrying = _materialise(canonical, layout, root / "carrying")
    expect(
        check_drift(canonical, carrying, {}) != [],
        "an empty layout over a tree carrying vendored modules must be red",
    )

    # ...but an empty layout over a tree that carries nothing is clean. The guard
    # must fire on unmapped COPIES, not on every service that vendors nothing,
    # or it is red by construction and gets switched off.
    bare = root / "bare"
    (bare / "apps").mkdir(parents=True)
    (bare / "apps/main.py").write_text("# service-only\n")
    expect(check_drift(canonical, bare, {}) == [], "a tree with no copies must be clean")

    # THE Factory#523 MUTATION. The subject is held constant — the same drifted
    # file, on disk, untouched — and only the gate's own layout moves. Before the
    # stray-copy guard the second call returned [] and the run printed success,
    # with the module count as the only trace.
    drifted = _materialise(canonical, layout, root / "drifted")
    (drifted / "apps/backend/agents/verification_gate.py").write_text("# drifted\n")
    mapped = check_drift(canonical, drifted, layout)
    expect(
        any(p.startswith("verification_gate.py") for p in mapped),
        "baseline: the drifted copy must be flagged while it is mapped",
    )
    unmapped_layout = {k: v for k, v in layout.items() if k != "verification_gate.py"}
    problems = check_drift(canonical, drifted, unmapped_layout)
    expect(
        any("verification_gate.py" in p and "maps it nowhere" in p for p in problems),
        "deleting a layout entry must flag the now-unmapped copy, not go green",
    )
    SERVICE_LAYOUTS["__selftest__"] = unmapped_layout
    try:
        expect(
            run_check(canonical, drifted, "__selftest__") == 1,
            "run_check must exit 1 when a layout entry is deleted from under a copy",
        )
    finally:
        del SERVICE_LAYOUTS["__selftest__"]

    # The scan is scoped, and the scope is the documented one. A copy inside a
    # pruned directory is not a stray (a local .claude/worktrees checkout would
    # otherwise redden every developer run); a copy anywhere else is.
    pruned = root / "pruned"
    for parent in (".git", "node_modules"):
        (pruned / parent).mkdir(parents=True)
        (pruned / parent / "nix_provisioner.py").write_text("# not a vendored copy\n")
    expect(check_drift(canonical, pruned, {}) == [], "pruned directories must not be scanned")
    (pruned / "vendor").mkdir()
    (pruned / "vendor/nix_provisioner.py").write_text("# a real unmapped copy\n")
    expect(
        check_drift(canonical, pruned, {}) != [],
        "an unmapped copy outside the prune list must be flagged",
    )
    return failures


_PORTED_OK = '''\
"""Ported from the hub's scripts/ratchet_lint.py."""
from ratchet_helpers import is_test_file, require_tool_ran


def ruff_counts(res):
    require_tool_ran("ruff", res)
    return len(res.stdout)
'''

_PORTED_INLINE_RESTATEMENT = '''\
"""Ported from the hub's scripts/ratchet_lint.py."""
from ratchet_helpers import is_test_file


def ruff_counts(res):
    if res.returncode not in (0, 1):
        raise SystemExit(2)
    return len(res.stdout)
'''

_PORTED_SURVIVING_INLINE_COPY = """

def mypy_count(res):
    if res.returncode not in (0, 1):
        raise SystemExit(2)
    return 0
"""

_PORTED_UNCALLED_IMPORT = '''\
"""Ported from the hub's scripts/ratchet_lint.py."""
from ratchet_helpers import require_tool_ran


def ruff_counts(res):
    return len(res.stdout)
'''


def _ported_self_test(root: Path) -> list[str]:
    """The acknowledged-fork guard (Factory#590), which byte comparison cannot do.

    Each case holds the fork's own orchestration constant — the thing that is
    legitimately different between the five — and moves only whether the SHARED
    rule is imported, called, or restated.
    """
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    ported = root / "ported"
    (ported / "scripts").mkdir(parents=True)
    fork = ported / "scripts/ratchet_lint.py"

    fork.write_text(_PORTED_OK)
    expect(
        ported_ratchet_problems(ported, "scripts/ratchet_lint.py") == [],
        "a fork that imports and calls the shared rule is clean",
    )

    # THE Factory#590 MUTATION: the rule restated inline instead of imported.
    # This is the state all five repos were in, and no byte comparison can see it.
    fork.write_text(_PORTED_INLINE_RESTATEMENT)
    problems = ported_ratchet_problems(ported, "scripts/ratchet_lint.py")
    expect(
        any("does not import" in p for p in problems),
        "a fork that does not import the shared rule must be red",
    )
    expect(
        any("restates the shared rule" in p for p in problems),
        "an inline restatement of the shared rule must be red",
    )

    # Importing it while KEEPING the old inline copy is still red: the canonical
    # fix would reach the import and change nothing about what the fork measures.
    # This is precisely the half-fix TFactory#951 shipped and read as complete.
    fork.write_text(_PORTED_OK + _PORTED_SURVIVING_INLINE_COPY)
    expect(
        any(
            "restates the shared rule" in p
            for p in ported_ratchet_problems(ported, "scripts/ratchet_lint.py")
        ),
        "importing the rule must not excuse a surviving inline copy of it",
    )

    # An import nobody calls satisfies a naive check and measures nothing. These
    # files sit outside every repo's ruff scope, so F401 does not cover it.
    fork.write_text(_PORTED_UNCALLED_IMPORT)
    expect(
        any(
            "never calls it" in p
            for p in ported_ratchet_problems(ported, "scripts/ratchet_lint.py")
        ),
        "an imported-but-uncalled rule must be red",
    )

    # A registered fork that is not there means the map went stale.
    fork.unlink()
    expect(
        any("absent" in p for p in ported_ratchet_problems(ported, "scripts/ratchet_lint.py")),
        "a registered fork that does not exist must be red, not skipped",
    )
    return failures


def _self_test() -> int:
    """Exercise the drift logic on a synthetic canonical/service pair.

    Dependency-free and self-contained: builds tiny throwaway trees in a tmp dir
    so the gate's own logic is verified without touching any real repo.
    """
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        canonical = root / "canonical"
        canonical.mkdir(parents=True)
        for module in CANONICAL_MODULES:
            (canonical / module).write_text(f"# canonical {module}\nVALUE = 1\n")

        # A representative two-module layout vendored at nested service paths.
        layout = {
            "verification_gate.py": "apps/backend/agents/verification_gate.py",
            "nix_provisioner.py": "apps/backend/tools/runners/nix_provisioner.py",
        }

        def make_service(name: str) -> Path:
            return _materialise(canonical, layout, root / name)

        # Case 1: an identical copy -> no drift.
        identical = make_service("identical")
        expect(check_drift(canonical, identical, layout) == [], "identical copy must not drift")

        # Case 2: extra service-specific file is ignored (not part of the layer).
        (identical / "apps/backend/agents/local_helper.py").write_text("# service-only\n")
        expect(
            check_drift(canonical, identical, layout) == [],
            "extra service-only file must be ignored",
        )

        # Case 3: a byte change in a vendored file -> drift on exactly that module.
        modified = make_service("modified")
        (modified / "apps/backend/agents/verification_gate.py").write_text(
            "# canonical verification_gate.py\nVALUE = 2\n"
        )
        problems = check_drift(canonical, modified, layout)
        expect(len(problems) == 1, "single change must yield exactly one problem")
        expect(
            bool(problems) and problems[0].startswith("verification_gate.py"),
            "drift must be attributed to verification_gate.py",
        )

        # Case 4: a missing vendored file is reported as missing.
        missing = root / "missing"
        (missing / "apps/backend/tools/runners").mkdir(parents=True)
        (missing / "apps/backend/tools/runners/nix_provisioner.py").write_bytes(
            (canonical / "nix_provisioner.py").read_bytes()
        )
        problems = check_drift(canonical, missing, layout)
        expect(
            any("verification_gate.py" in p and "missing" in p for p in problems),
            "missing vendored file must be reported as missing",
        )

        # Case 5: a module the service does NOT vendor is not checked.
        partial_layout = {"nix_provisioner.py": "apps/backend/tools/runners/nix_provisioner.py"}
        partial = root / "partial"
        (partial / "apps/backend/tools/runners").mkdir(parents=True)
        (partial / "apps/backend/tools/runners/nix_provisioner.py").write_bytes(
            (canonical / "nix_provisioner.py").read_bytes()
        )
        expect(
            check_drift(canonical, partial, partial_layout) == [],
            "un-vendored modules must not be checked",
        )

        # Case 6: run_check end-to-end via a temporary service entry.
        SERVICE_LAYOUTS["__selftest__"] = layout
        try:
            expect(
                run_check(canonical, identical, "__selftest__") == 0,
                "run_check must pass on a match",
            )
            expect(
                run_check(canonical, modified, "__selftest__") == 1,
                "run_check must fail on drift",
            )
            expect(
                run_check(root / "nope", identical, "__selftest__") == _EXIT_BAD_INVOCATION,
                "run_check must return 2 when the canonical tree is absent",
            )
            expect(
                run_check(canonical, identical, "__unknown__") == _EXIT_BAD_INVOCATION,
                "run_check must return 2 for an unknown service",
            )
        finally:
            del SERVICE_LAYOUTS["__selftest__"]

        # Cases 7-10: the gate's SCOPE, not its subject (Factory#523).
        failures.extend(_scope_self_test(canonical, root, layout))

        # Cases 11-15: acknowledged forks, which byte comparison cannot reach
        # at all (Factory#590).
        failures.extend(_ported_self_test(root))

    if failures:
        _emit("SELF-TEST FAILED:")
        for failure in failures:
            _emit(f"  - {failure}")
        return 1
    _emit("SELF-TEST OK: verification-core drift gate behaves as specified.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--canonical",
        default=str(_DEFAULT_CANONICAL),
        help="path to the canonical verification-core tree (default: hub scripts/)",
    )
    parser.add_argument(
        "--service",
        choices=sorted(SERVICE_LAYOUTS),
        help="which known service to check",
    )
    parser.add_argument(
        "--root",
        help="path to the service's repo root (vendored paths are relative to it)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the per-service vendored layout and exit",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the built-in self-test and exit",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.list:
        return _list_layouts()

    if not args.service:
        parser.error("--service is required (or pass --self-test / --list)")
    if not args.root:
        parser.error("--root is required when --service is given")

    return run_check(Path(args.canonical), Path(args.root), args.service)


if __name__ == "__main__":
    sys.exit(main())
