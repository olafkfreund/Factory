#!/usr/bin/env python3
"""Fail CI when a portal's vendored factory-ui components drift from the hub.

The canonical copies of the shared portal chrome live in this hub at
``shared/factory-ui/`` (the single source of truth — see
``shared/factory-ui/README.md``). PFactory, AIFactory and TFactory each
hand-vendor these components into their frontends. This guard stops those copies
silently diverging from the hub canonical.

The canonical set is exactly the shared portal chrome shipped by the portal UX
program:

    CommandPalette.tsx   the cross-portal command palette (Cmd-K)
    PortalSwitcher.tsx   the topbar portal switcher

The check is **byte-exact and directional** (hub canonical -> portal copy): for
every canonical file a portal vendors, the matching file in the portal tree must
exist and be byte-identical to the hub copy. CFactory is intentionally not a
consumer (hand-rolled CSS on its own token set) and is not listed here.

This mirrors ``scripts/check_verification_core_drift.py``: pure stdlib, no
third-party imports, hard-fail (exit 1) on real drift.

Usage:
    # Check a known portal checkout against the hub canonical:
    python scripts/check_factory_ui_drift.py --service aifactory --root /path/to/AIFactory

    # List which files each known portal is expected to vendor:
    python scripts/check_factory_ui_drift.py --list

    # Override the canonical root explicitly (default: this repo's shared/factory-ui):
    python scripts/check_factory_ui_drift.py \
        --canonical shared/factory-ui --service tfactory --root /path/to/TFactory

    # Run the built-in self-test (no repo state needed):
    python scripts/check_factory_ui_drift.py --self-test

Exit codes:
    0 - portal copies match the canonical (or self-test/list succeeded)
    1 - drift detected (or self-test failed)
    2 - bad invocation / missing canonical tree / unknown service
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

# Sibling module in this same scripts/ directory. Consumers run this gate out of
# a full hub checkout, so it resolves there too (see gate_evidence's docstring).
from gate_evidence import digest

# Canonical file names as they live, flat, in the hub's shared/factory-ui/.
CANONICAL_MODULES: tuple[str, ...] = (
    "CommandPalette.tsx",
    "PortalSwitcher.tsx",
)

# Per-portal vendored layout: {canonical_file: path-relative-to-portal-root}.
# The three Tailwind portals vendor both files at the same relative path.
_VENDOR_DIR = "apps/frontend-web/src/components"
SERVICE_LAYOUTS: dict[str, dict[str, str]] = {
    "pfactory": {m: f"{_VENDOR_DIR}/{m}" for m in CANONICAL_MODULES},
    "aifactory": {m: f"{_VENDOR_DIR}/{m}" for m in CANONICAL_MODULES},
    "tfactory": {m: f"{_VENDOR_DIR}/{m}" for m in CANONICAL_MODULES},
}


def _emit(message: str) -> None:
    # Single output sink for this CLI, so the repo-wide (no-print) rule is
    # intentionally suppressed at exactly one place.
    print(message)  # noqa: T201


def _default_canonical() -> Path:
    return Path(__file__).resolve().parent.parent / "shared" / "factory-ui"


def _missing_from_contract(canonical: Path) -> list[str]:
    """Canonical component files that CANONICAL_MODULES does not list.

    An explicit tuple is the contract, but it ROTS. Factory#397 hit exactly this
    in the factory-github gate: two files were added to the canonical, nothing
    added them here, and the gate reported OK against a tree it had never looked
    at. A gate that does not check a file cannot keep it honest, and a green gate
    on an unchecked tree is worse than no gate.
    """
    if not canonical.is_dir():
        return []
    listed = set(CANONICAL_MODULES)
    return [p.name for p in sorted(canonical.glob("*.tsx")) if p.name not in listed]


def compared_evidence(service: str, root: Path, canonical: Path) -> list[str]:
    """One line per component this run compared, each carrying the bytes it read."""
    return [
        f"{module} -> {rel} [canonical {digest(canonical / module)} | portal {digest(root / rel)}]"
        for module, rel in sorted(SERVICE_LAYOUTS.get(service, {}).items())
    ]


def check_service(service: str, root: Path, canonical: Path) -> list[str]:
    """Return a list of drift messages (empty when the portal copies match)."""
    layout = SERVICE_LAYOUTS.get(service)
    if layout is None:
        return [f"unknown service {service!r}; known: {', '.join(sorted(SERVICE_LAYOUTS))}"]

    problems: list[str] = [
        f"{name}: in shared/factory-ui/ but not listed in CANONICAL_MODULES — "
        "the gate cannot check it"
        for name in _missing_from_contract(canonical)
    ]
    # Factory#523, the same hole in the sibling gate: check_service can only
    # compare what the layout points it at, so dropping one entry from a portal's
    # layout removes that component from the gate's world and the run still
    # reports a match. Every portal here vendors the WHOLE canonical set (the
    # layouts are written as comprehensions over it precisely because that is the
    # contract), so total coverage is the invariant to assert — no tree scan
    # needed, unlike the verification-core gate where subsets are legitimate.
    problems.extend(
        f"{module}: canonical, but {service}'s layout maps it nowhere — nothing "
        "compares it in this portal, so it is free to drift"
        for module in CANONICAL_MODULES
        if module not in layout
    )
    for module, rel in layout.items():
        canonical_file = canonical / module
        if not canonical_file.is_file():
            problems.append(f"canonical missing: {canonical_file}")
            continue
        service_file = root / rel
        if not service_file.is_file():
            problems.append(f"{service}: vendored copy missing: {rel}")
            continue
        if service_file.read_bytes() != canonical_file.read_bytes():
            problems.append(
                f"{service}: {rel} drifted from hub canonical shared/factory-ui/{module}"
            )
    return problems


def _self_test() -> int:
    """Byte-identical passes; a one-byte change fails. No repo state needed."""
    with tempfile.TemporaryDirectory() as tmp:
        canonical = Path(tmp) / "canonical"
        canonical.mkdir()
        for m in CANONICAL_MODULES:
            (canonical / m).write_text(f"// {m}\nexport const x = 1;\n")

        root = Path(tmp) / "svc"
        vend = root / _VENDOR_DIR
        vend.mkdir(parents=True)
        for m in CANONICAL_MODULES:
            (vend / m).write_bytes((canonical / m).read_bytes())

        SERVICE_LAYOUTS["__selftest__"] = {m: f"{_VENDOR_DIR}/{m}" for m in CANONICAL_MODULES}
        try:
            if check_service("__selftest__", root, canonical):
                _emit("self-test FAILED: byte-identical copies reported drift")
                return 1
            # introduce a one-byte drift
            target = vend / CANONICAL_MODULES[0]
            target.write_text(target.read_text() + " ")
            if not check_service("__selftest__", root, canonical):
                _emit("self-test FAILED: drift not detected")
                return 1
        finally:
            del SERVICE_LAYOUTS["__selftest__"]
    _emit("self-test OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=sorted(SERVICE_LAYOUTS), help="portal to check")
    parser.add_argument("--root", type=Path, help="path to the portal checkout")
    parser.add_argument(
        "--canonical", type=Path, default=None, help="canonical shared/factory-ui dir"
    )
    parser.add_argument(
        "--list", action="store_true", help="list expected vendored files per portal"
    )
    parser.add_argument("--self-test", action="store_true", help="run the built-in self-test")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.list:
        for svc in sorted(SERVICE_LAYOUTS):
            _emit(svc)
            for module, rel in sorted(SERVICE_LAYOUTS[svc].items()):
                _emit(f"  {module} -> {rel}")
        return 0

    if not args.service or not args.root:
        _emit("ERROR: --service and --root are required (or use --list / --self-test)")
        return 2

    canonical = (args.canonical or _default_canonical()).resolve()
    if not canonical.is_dir():
        _emit(f"ERROR: canonical tree not found: {canonical}")
        return 2

    root = args.root.resolve()
    problems = check_service(args.service, root, canonical)
    # Factory#504: name what was compared, not how many. A count is a headline
    # nobody re-derives, so a component dropping out of scope is indistinguishable
    # from one that was never in it — and the digests make the PASS verdict
    # falsifiable, not just the failures.
    _emit(f"factory-ui: {args.service} vs the canonical at {canonical}")
    _emit("  compared (each line carries the bytes the verdict was read from):")
    for line in compared_evidence(args.service, root, canonical):
        _emit(f"    - {line}")
    if problems:
        _emit(f"factory-ui drift detected for {args.service}:")
        for p in problems:
            _emit(f"  - {p}")
        return 1
    _emit(
        f"factory-ui: {args.service} matches the hub canonical — every component "
        "enumerated above matched."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
