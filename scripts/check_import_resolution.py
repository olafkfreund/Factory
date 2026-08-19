#!/usr/bin/env python3
"""Fail CI when a module imports a first-party path that does not exist.

Factory#834, from a real incident. TFactory#1121 deleted a forked
``server/services/url_safety.py`` and repointed the call sites visible on its
branch; ``context.py`` was not one of them. TFactory#1125 was concurrent,
merged first, and carried that import forward. Both PRs were green and both
were CORRECT -- each tree was self-consistent. The diffs did not overlap
textually, so nothing conflicted and ``mergeStateStatus`` read ``CLEAN`` on
both. The defect existed only in the merged result, which no CI run had
evaluated. ``dev`` got nine collection errors and five red jobs (TFactory#1126).

It was caught at all only because nine test modules imported ``context.py``
transitively. **A stale import in a module no test imports would have shipped
silently** and surfaced as an ImportError in production, at whatever moment
that code path was first exercised. That is the gap this closes.

WHOLE-REPO, NOT DIFF-SCOPED
---------------------------
Deliberately, and for the same reason as ``security-lint.yml`` (Factory#786):
a diff-scoped version cannot see the module that went stale *without being
edited*, which is precisely the case that broke. ``context.py`` is not in
#1121's diff. Scanning only changed files would have reported CLEAN.

SCOPE -- what this checks and what it deliberately does not
-----------------------------------------------------------
IN scope: first-party imports. A dotted target whose top-level name is a
package or module living in this tree (``server.services.url_safety`` when
``server/`` is a package here). Also relative imports (``from .x import y``),
resolved against the importing file's own package position.

OUT of scope, deliberately:
  - Third-party and stdlib imports. A missing dependency is a different
    failure with a different fix (a lockfile/requirements change, not a code
    change), it is already caught by any install step, and resolving it here
    would make the gate's verdict depend on which venv CI happened to build.
    Top-level names that are not present in the tree are skipped, silently.
  - Attribute-vs-submodule for ``from pkg.mod import name`` where ``pkg.mod``
    is a *module*: whether ``name`` exists inside it cannot be decided without
    executing the module. Only the module path is checked. (``from pkg import
    name`` where ``pkg`` is a *package* IS checked -- see ``_package_binds``.)

KNOWN CEILING, stated rather than hidden: first-party-ness is decided by the
TOP-LEVEL name. If an entire top-level package is deleted, every import of it
becomes indistinguishable from a third-party import and is skipped. The
incident this gate exists for is the common case -- a submodule deleted from a
package that still exists -- and that is caught. Deleting a whole top-level
package is loud enough on its own (nothing in the repo resolves) that it does
not need this gate; closing the gap properly would need a declared list of the
repo's own top-level names, which is a config file to keep in sync, i.e. a
second thing that can silently go stale.

NOTHING IS IMPORTED FOR REAL. Everything is ``ast`` parsing plus path lookup.
Executing arbitrary module top-level code in CI is slow and unsafe, and would
make the gate's verdict depend on import side effects.

CONDITIONAL AND OPTIONAL IMPORTS ARE REAL AND ARE NOT REPORTED
---------------------------------------------------------------
Three legitimate shapes, all handled by tracking the AST ancestry of each
import rather than by pattern-matching lines:
  - inside ``try:`` whose ``except`` catches ImportError/ModuleNotFoundError/
    Exception (the optional-dependency idiom)
  - inside ``with contextlib.suppress(ImportError):``
  - inside ``if TYPE_CHECKING:`` (the target may legitimately be a stub, or
    live behind a dependency not installed at runtime)
``pytest.importorskip("x")`` is not an import statement at all, so it never
reaches this gate. There is also an inline opt-out for anything else:
a ``# import-resolution-exempt: <reason>`` comment on the import's line.

Usage:
    python scripts/check_import_resolution.py --root .
    python scripts/check_import_resolution.py --self-test

Exit codes:
    0 - every first-party import target in the tree resolves
    1 - at least one does not
    2 - bad invocation, or nothing was scanned (a zero-file scan is an
        unknown verdict, never a pass)
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

from gate_evidence import expect, gate_argparser, parse_or_self_test, report_self_test, temp_repo

# Written on one line rather than as a block literal: the same names in the same
# order over `check_sink_coverage.py`'s import header is a jscpd clone worth 10
# lines, and it is a clone of boilerplate, not of logic (Factory#403's budget).
_SKIP_DIRS = frozenset(
    {"node_modules", "__pycache__", "dist", "build", "vendor", "site-packages", "migrations"}
)

_OPT_OUT = "import-resolution-exempt:"

# An unknown verdict. Never 0: a scan that examined nothing must not be
# indistinguishable from a tree whose every import resolved.
_UNKNOWN = 2

# Catching bare `Exception` counts: `except Exception: pass` around an import
# is the same optional-dependency idiom written less precisely, and reporting
# it would be a style opinion, not a broken import.
_OPTIONAL_EXC = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _is_skippable(path: Path) -> bool:
    """Same dot-directory rule as ``check_sink_coverage.py``.

    A bare named skip-set lets a scan walk into ``.venv/``, ``.tox/`` and a
    nested ``.claude/worktrees/<agent>/`` checkout -- which for THIS gate would
    be worse than noise, since a vendored site-packages tree defines top-level
    names that make third-party imports look first-party.
    """
    return any(part in _SKIP_DIRS or part.startswith(".") for part in path.parts)


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    target: str
    why: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.target} -- {self.why}"


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if not _is_skippable(p.relative_to(root)))


def _package_of(path: Path) -> list[str]:
    """The dotted package a file lives in, walked up by ``__init__.py`` presence.

    Root-independent on purpose: it answers "what does ``from .x import y``
    mean *here*", which depends on the package boundary, not on whichever
    directory happens to be on ``sys.path``.
    """
    parts: list[str] = []
    directory = path.parent
    while (directory / "__init__.py").is_file():
        parts.insert(0, directory.name)
        directory = directory.parent
    return parts


def _source_roots(root: Path, files: list[Path]) -> list[Path]:
    """Directories that behave as import roots: they hold a package but are not in one.

    Covers the layouts in this fleet without configuration -- a repo-root
    package, a ``src/`` layout, and a monorepo app dir (TFactory's
    ``apps/web-server/server/``). A directory that is itself inside a package
    is not a root, which is what keeps ``server/routes/`` from making
    ``import routes.context`` resolve.
    """
    roots = {root}
    for file in files:
        if file.name != "__init__.py":
            continue
        package_top = file.parent
        while (package_top.parent / "__init__.py").is_file():
            package_top = package_top.parent
        roots.add(package_top.parent)
    return sorted(roots)


class Resolver:
    """Path-only resolution of a dotted module name against the tree's roots."""

    def __init__(self, roots: list[Path]) -> None:
        self.roots = roots
        self._top_level: set[str] = set()
        for source_root in roots:
            if not source_root.is_dir():
                continue
            for child in source_root.iterdir():
                if _is_skippable(Path(child.name)):
                    continue
                if child.is_dir() and (child / "__init__.py").is_file():
                    self._top_level.add(child.name)
                elif child.suffix in {".py", ".pyi"}:
                    self._top_level.add(child.stem)

    def is_first_party(self, dotted: str) -> bool:
        return dotted.split(".", maxsplit=1)[0] in self._top_level

    def find(self, dotted: str) -> tuple[bool, bool]:
        """``(resolved, is_package)`` for *dotted*, by path lookup only."""
        parts = dotted.split(".")
        for source_root in self.roots:
            candidate = source_root.joinpath(*parts)
            if candidate.is_dir() and (candidate / "__init__.py").is_file():
                return True, True
            for suffix in (".py", ".pyi"):
                if candidate.with_suffix(suffix).is_file():
                    return True, False
        return False, False

    def package_dir(self, dotted: str) -> Path | None:
        for source_root in self.roots:
            candidate = source_root.joinpath(*dotted.split("."))
            if candidate.is_dir() and (candidate / "__init__.py").is_file():
                return candidate
        return None


def _package_binds(package: Path, name: str) -> bool:
    """Whether ``from <package> import <name>`` can be satisfied without executing it.

    True if *name* is a submodule on disk, or is bound anywhere in the
    package's ``__init__.py``. Bindings are collected with ``ast.walk``, so a
    conditionally-defined name counts -- this is the permissive direction on
    purpose: a false PASS here costs one uncaught stale import, a false FAIL
    gets the whole gate switched off.
    """
    if name.startswith("__"):
        # `from pkg import __file__ / __path__ / __version__`: module dunders
        # the interpreter supplies. CFactory's tests do this to locate the
        # installed package on disk; it is valid and always resolves.
        return True
    if (package / f"{name}.py").is_file() or (package / f"{name}.pyi").is_file():
        return True
    if (package / name / "__init__.py").is_file():
        return True
    try:
        tree = ast.parse((package / "__init__.py").read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return True
    return any(_node_binds(node, name) for node in ast.walk(tree))


def _node_binds(node: ast.AST, name: str) -> bool:
    """Whether one ``__init__.py`` node makes *name* available on the package."""
    if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
        # A star-import (like a module __getattr__ below) means the package's
        # namespace is not decidable from its source. Give up rather than guess.
        return True
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return node.name in {name, "__getattr__"}
    if isinstance(node, ast.Import | ast.ImportFrom):
        return any((a.asname or a.name.split(".", 1)[0]) == name for a in node.names)
    if isinstance(node, ast.Name):
        return isinstance(node.ctx, ast.Store) and node.id == name
    # A bare string equal to *name* covers `__all__ = [...]` and any other
    # re-export table, without having to find the assignment it belongs to.
    return isinstance(node, ast.Constant) and node.value == name


def _is_type_checking_guard(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _suppresses_import_error(node: ast.With) -> bool:
    for item in node.items:
        call = item.context_expr
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        target = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if target == "suppress" and any(
            isinstance(a, ast.Name) and a.id in _OPTIONAL_EXC for a in call.args
        ):
            return True
    return False


def _handles_import_error(node: ast.Try) -> bool:
    for handler in node.handlers:
        if handler.type is None:
            return True
        raised = handler.type
        names = raised.elts if isinstance(raised, ast.Tuple) else [raised]
        if any(isinstance(n, ast.Name) and n.id in _OPTIONAL_EXC for n in names):
            return True
    return False


def _unguarded_imports(tree: ast.AST) -> list[ast.Import | ast.ImportFrom]:
    """Every import statement NOT inside an optional/typing-only guard.

    Walks the body explicitly rather than using ``ast.walk`` because the whole
    point is the ancestry: the same statement is a finding at module level and
    legitimate inside ``try: ... except ImportError:``.
    """
    found: list[ast.Import | ast.ImportFrom] = []

    def visit(node: ast.AST, guarded: bool) -> None:
        if isinstance(node, ast.Import | ast.ImportFrom):
            if not guarded:
                found.append(node)
            return
        if isinstance(node, ast.Try):
            body_guarded = guarded or _handles_import_error(node)
            for child in node.body:
                visit(child, body_guarded)
            for other in (*node.handlers, *node.orelse, *node.finalbody):
                visit(other, guarded)
            return
        if isinstance(node, ast.If) and _is_type_checking_guard(node.test):
            for child in node.body:
                visit(child, True)
            for child in node.orelse:
                visit(child, guarded)
            return
        if isinstance(node, ast.With):
            body_guarded = guarded or _suppresses_import_error(node)
            for child in node.body:
                visit(child, body_guarded)
            return
        for descendant in ast.iter_child_nodes(node):
            visit(descendant, guarded)

    visit(tree, False)
    return found


def _targets(node: ast.Import | ast.ImportFrom, package: list[str]) -> list[tuple[str, list[str]]]:
    """``(dotted module, names imported from it)`` for one import statement."""
    if isinstance(node, ast.Import):
        return [(alias.name, []) for alias in node.names]
    names = [alias.name for alias in node.names if alias.name != "*"]
    if node.level == 0:
        return [(node.module or "", names)]
    if len(package) < node.level - 1:
        return [("", names)]
    base = package[: len(package) - (node.level - 1)]
    dotted = ".".join([*base, *([node.module] if node.module else [])])
    return [(dotted, names)]


def _scan_file(path: Path, root: Path, resolver: Resolver) -> tuple[list[Finding], int]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [], 0
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Not this gate's job. A file that does not parse fails ruff, mypy and
        # pytest collection loudly; double-reporting it here would only make
        # this gate's finding list harder to read.
        return [], 0
    lines = source.splitlines()
    relative = path.relative_to(root)
    package = _package_of(path)
    findings: list[Finding] = []
    checked = 0
    for node in _unguarded_imports(tree):
        line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
        if _OPT_OUT in line:
            continue
        for dotted, names in _targets(node, package):
            if not dotted:
                findings.append(
                    Finding(relative, node.lineno, ".", "relative import beyond the top package")
                )
                continue
            if not resolver.is_first_party(dotted):
                continue
            checked += 1
            resolved, is_package = resolver.find(dotted)
            if not resolved:
                findings.append(
                    Finding(relative, node.lineno, dotted, "no such module in the tree")
                )
                continue
            if not is_package:
                continue
            package_dir = resolver.package_dir(dotted)
            if package_dir is None:
                continue
            for name in names:
                if not _package_binds(package_dir, name):
                    findings.append(
                        Finding(
                            relative,
                            node.lineno,
                            f"{dotted}.{name}",
                            "not a submodule of that package, and not bound in its __init__.py",
                        )
                    )
    return findings, checked


def run_check(root: Path) -> int:
    files = _python_files(root)
    if not files:
        print(f"ERROR: no Python files found under {root} -- nothing was gated.")  # noqa: T201
        return _UNKNOWN
    resolver = Resolver(_source_roots(root, files))
    findings: list[Finding] = []
    checked = 0
    for path in files:
        file_findings, file_checked = _scan_file(path, root, resolver)
        findings.extend(file_findings)
        checked += file_checked
    for finding in findings:
        print(f"FAIL {finding}")  # noqa: T201
    # The counts print on every run, pass or fail. A gate that says only "OK"
    # cannot be told apart from one that examined zero items (Factory#832).
    print(  # noqa: T201
        f"Scanned {len(files)} files, {checked} first-party import targets, "
        f"{len(findings)} unresolved."
    )
    return 1 if findings else 0


def _self_test() -> int:
    failures: list[str] = []
    with temp_repo() as root:
        # The real incident, reconstructed: a package whose forked module was
        # deleted, still imported by a route module NO TEST IMPORTS.
        pkg = root / "server"
        (pkg / "services").mkdir(parents=True)
        (pkg / "routes").mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "services" / "__init__.py").write_text("")
        (pkg / "routes" / "__init__.py").write_text("")
        (pkg / "error_ref.py").write_text("class InputRejectedError(Exception): pass\n")
        context = pkg / "routes" / "context.py"
        context.write_text(
            "from server.error_ref import InputRejectedError\n"
            "from server.services.url_safety import assert_safe_outbound_url\n"
        )
        expect(failures, run_check(root) == 1, "a deleted first-party module must be reported")

        (pkg / "services" / "url_safety.py").write_text("def assert_safe_outbound_url(u): ...\n")
        expect(failures, run_check(root) == 0, "the same tree must pass once the module exists")
        (pkg / "services" / "url_safety.py").unlink()

        # The fix TFactory#1126 actually landed: repoint at the canonical.
        (root / "factory_common").mkdir()
        (root / "factory_common" / "__init__.py").write_text("")
        (root / "factory_common" / "url_safety.py").write_text("def assert_safe(u): ...\n")
        context.write_text(
            "from factory_common.url_safety import assert_safe_outbound_url\n"
            "from server.error_ref import InputRejectedError\n"
        )
        expect(failures, run_check(root) == 0, "the repointed import must resolve")

        # Third-party is out of scope: a package not in the tree is not this
        # gate's failure, and reporting it would make the verdict depend on
        # which venv CI built.
        context.write_text("import httpx\nfrom fastapi import APIRouter\n")
        expect(failures, run_check(root) == 0, "third-party imports must not be reported")

        # Optional and typing-only imports are legitimate and must stay silent.
        context.write_text(
            "from typing import TYPE_CHECKING\n"
            "import contextlib\n"
            "try:\n"
            "    from server.services.optional import thing\n"
            "except ImportError:\n"
            "    thing = None\n"
            "with contextlib.suppress(ImportError):\n"
            "    from server.services.other import gone\n"
            "if TYPE_CHECKING:\n"
            "    from server.services.stubs import Kind\n"
            "from server.services.waived import x  # import-resolution-exempt: Factory#834 demo\n"
        )
        expect(failures, run_check(root) == 0, "guarded/exempt imports must not be reported")

        # ...but the SAME target unguarded is a finding. Without this pair the
        # case above proves only that the gate is quiet, not that it is right.
        context.write_text("from server.services.optional import thing\n")
        expect(failures, run_check(root) == 1, "the same import unguarded must be reported")

        # Relative imports resolve against the importing file's package.
        context.write_text("from ..error_ref import InputRejectedError\nfrom . import sibling\n")
        expect(failures, run_check(root) == 1, "a missing relative sibling must be reported")
        (pkg / "routes" / "sibling.py").write_text("")
        expect(failures, run_check(root) == 0, "a present relative sibling must resolve")

        # `from <package> import <name>`: submodule or __init__ binding.
        context.write_text("from server.services import url_safety\n")
        expect(failures, run_check(root) == 1, "a missing submodule of a package must be reported")
        (pkg / "services" / "__init__.py").write_text("url_safety = object()\n")
        expect(
            failures, run_check(root) == 0, "a name bound in __init__.py must satisfy the import"
        )

        # Module dunders are supplied by the interpreter, never on disk.
        context.write_text("from server import __file__ as here\n")
        expect(failures, run_check(root) == 0, "a module dunder must not be reported")

        # A sys.path root that is not a package's parent: invisible without
        # --source-root, which is the difference between gating this repo's own
        # modules and reporting a green that examined none of them.
        # A package nested in a monorepo app dir (TFactory's
        # apps/web-server/server/) must resolve without configuration: its
        # parent is an import root because it holds a package and is not in one.
        (root / "apps" / "web" / "helper").mkdir(parents=True)
        (root / "apps" / "web" / "helper" / "__init__.py").write_text("")
        context.write_text("from helper.gone import VALUE\n")
        expect(
            failures,
            run_check(root) == 1,
            "a missing submodule under a nested app dir must be reported",
        )
        (root / "apps" / "web" / "helper" / "gone.py").write_text("VALUE = 1\n")
        expect(failures, run_check(root) == 0, "...and must pass once that submodule exists")

    # A gate that scans nothing must not report success.
    with temp_repo() as empty:
        expect(failures, run_check(empty) == _UNKNOWN, "an empty tree must be unknown, not green")

    return report_self_test(failures)


def main(argv: list[str] | None = None) -> int:
    parser = gate_argparser(__doc__)
    parser.add_argument("--root", help="repo root to scan")
    early, args = parse_or_self_test(parser, argv, _self_test)
    if early is not None:
        return early
    assert args is not None  # noqa: S101 - parse_or_self_test guarantees this when early is None
    if not args.root:
        parser.error("--root is required (or pass --self-test)")
    return run_check(Path(args.root).resolve())


if __name__ == "__main__":
    sys.exit(main())
