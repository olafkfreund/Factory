#!/usr/bin/env python3
"""Fail CI when a ``test_*.py`` file sits outside the paths CI actually collects.

Factory#844, from a real incident with a ten-week fuse.
``run_autonomous_agent`` is defined nowhere in PFactory, so ``pfactory build``
cannot run (PFactory#607). A test asserting exactly that property has been in
the tree since the fork commit on 2026-06-03::

    from agents import coder
    assert hasattr(coder, "run_autonomous_agent")

It has never executed. It lives in ``apps/backend/agents/test_refactoring.py``,
and CI collects ``pytest tests/ apps/web-server/tests/``. Ten weeks of green CI
over a broken entry point, with the alarm for it present in the tree the whole
time. The fleet-wide sweep found 57 such files across three repos -- 421 tests
that pass when run by hand and have never once run in CI, plus several that are
red for real reasons nobody has heard.

This is the fleet's dominant failure mode again: **absence that looks like
presence**. The tooling works. The measurement is empty, and an empty
measurement is indistinguishable from a clean one.

WHAT THIS GATE DOES AND DELIBERATELY DOES NOT DO
------------------------------------------------
It does NOT widen any repo's collection and does NOT fix the red tests. That is
a separate, larger job whose cost needs sizing first (issue #844, step 2). This
is step 3: the durable half. Without it, doing the migration just resets the
clock -- the 58th file lands next month and nothing notices.

HOW THE COLLECTED PATHS ARE DETERMINED -- the design decision
-------------------------------------------------------------
They are DERIVED from the repo's own ``.github/workflows/*.yml``, by finding
every ``pytest`` invocation and taking its path arguments. They are not
configured, and not hardcoded here.

The rejected alternative was a declared list (in this file, or in each repo's
registry). It is simpler to write and it reproduces the exact defect this gate
exists to close: the day a workflow's ``pytest`` line changes and the declared
list does not, the gate keeps reporting a confident verdict about a collection
boundary that has moved. A second thing to keep in sync is a second thing that
goes stale silently. Deriving costs a small amount of shell-ish parsing and can
never disagree with what CI runs, because it *is* what CI runs.

The cost of deriving is paid in three explicit unknown-verdict exits rather
than in silence -- see ``_UNKNOWN`` below. Each one is a case where the derived
answer might be wrong in the FALSE-CLEAN direction, so the gate refuses to
report instead of guessing:

  * no ``pytest`` invocation found in any workflow -- "this repo collects
    nothing" and "I failed to parse it" must not look alike
  * ``--ignore`` / ``--deselect`` on a pytest line -- those NARROW collection,
    so ignoring them would report files as collected that are not
  * a derived path that does not exist in the tree -- either the workflow is
    stale or the parse is wrong; either way the boundary is not what was read

A bare ``pytest`` with no path arguments (CFactory's ``PYTHONPATH=apps/backend
pytest -v``) collects the whole repo from the rootdir, unless a root pytest
config narrows it with ``testpaths``, which is read for that reason.

WHEN CI RUNS PYTEST AGAINST A PATH THIS REPO DOES NOT HAVE
-----------------------------------------------------------
TFactory's ``portal-ui-runner-image.yml`` runs ``python -m pytest
/app/portal_testing`` inside the runner image, where ``/app/portal_testing`` is
this repo's ``portal_testing/`` mounted (or vendored) in. Those tests DO run in
CI -- 33 of them -- but the derivation cannot map a container path back to a
repo directory, so they read as uncollected and get registered with a reason
that is true and permanent. A registry entry that says "covered, but the gate
cannot see it" converts a covered area into a documented gap (TFactory#1134).

So a workflow may ANNOTATE one pytest invocation with the repo path it
corresponds to::

    - run: |
        docker run --rm "${IMAGE}" \
          sh -c 'python -m pytest /app/portal_testing -q'  # test-collection: portal_testing

The directive is not a declared list: it is attached to a real ``pytest``
invocation in a real workflow, and it names only that invocation's paths. Delete
the step and the directive goes with it; move it and the directive moves. What
it buys is the one fact the parse cannot recover -- which repo directory the
container path is.

It is deliberately narrow, because it is the one place a workflow author can
widen the boundary by assertion:

  * the line must contain a genuine ``pytest`` invocation. A directive on a
    comment, a step ``name:``, or a ``pip install`` line does nothing.
  * ``.``, absolute paths and anything containing ``..`` are REJECTED as a bad
    directive (an unknown verdict, exit 2). ``# test-collection: .`` from a
    comment would mark the whole repo collected -- the false clean this gate
    exists to close, handed out as a feature.
  * every directive path still has to EXIST in the tree, by the same guard that
    catches a stale workflow path. A typo is an unknown verdict, not a pass.
  * ``--ignore``/``--deselect`` on the annotated line still make the verdict
    unknown; a directive says what the invocation points at, not that the
    author has modelled pytest's ignore semantics.

WHEN A TEST IS RUN AS A SCRIPT, NOT BY PYTEST
----------------------------------------------
factory-gitops has no ``pytest`` invocation anywhere in its workflows. Its five
CI helper tests live in ``.github/scripts/`` and four of them run as::

    - run: python3 .github/scripts/test_cred_sync.py

Two separate blind spots met there (Factory#926). The scan skipped every
dot-prefixed path component -- a rule meant for ``.venv``/``.git``/caches that
swallowed ``.github`` as collateral -- so those files were never even looked at,
and the repo read as "ZERO items examined". And the derivation only understood
``pytest``, so narrowing the skip alone would have converted one blind spot into
five registry entries saying "covered, but the gate cannot see it".

So the skip is now a NAMED list of directories (dot ones included), and a direct
``python <path>/test_x.py`` run is read as collecting that file. Being executed
by CI is the entire question this gate asks, and a script run answers it. It
stays narrow on purpose:

  * the boundary is the EXACT FILE named on the line, never its directory. A
    directive-free way to widen a boundary to a directory is the false clean
    this gate exists to close; one file cannot do that.
  * only a ``test_*.py`` / ``*_test.py`` script counts. ``python3
    scripts/deploy.py`` is a build step, and reading it as a boundary would
    hand out coverage on the strength of a script that runs no tests.
  * only python's FIRST positional counts, so ``python -m ...`` (a module) and
    ``python -c ...`` (a code string) decline on their own, and a lint step
    like ``python -m pyflakes .github/scripts/test_x.py`` cannot be read as
    proof that file runs. A python inside ``docker run`` runs the image's.

The one thing this cannot check is whether the script actually asserts
anything: ``test_extract_all_embedded.py`` had no ``__main__`` driver, so the
repo's convention would have imported it and exited 0 having executed nothing.
That is check_gate_liveness.py's question, not this one.

THE REGISTRY, AND WHY A DEAD ENTRY IS RED
------------------------------------------
Each repo carries ``uncollected-tests-allowlist.toml`` at its root, same shape
as ``security-lint-allowlist.toml``: an exact ``path``, a written ``reason``,
and an ``issue``. Four rules, all enforced here rather than by convention:

  * An entry that matches NOTHING fails the gate (fleet policy, Factory#788).
    A stale exemption silently widening coverage is this entire defect family;
    an allowlist that only ever grows is an ignore list with better manners.
    When a file gets collected, its entry must be deleted in the same PR.
  * ``reason`` is validated: placeholders (``TODO``, ``TBD``, ``N/A``,
    ``none``, ``placeholder``, ``grandfathered``) are REJECTED, as is anything
    under six words. Same rule as ``check_gate_liveness.py`` and PFactory's
    ``factory_invariants``.
  * ``issue`` is REQUIRED and must look like ``Repo#123``. An uncollected test
    with nobody's name on it is a permanent exception wearing a temporary hat.
  * Exact paths only, no globs. A glob is how one entry quietly comes to cover
    a directory nobody reviewed -- which is the defect, not the fix. 57 lines
    of allowlist is a reviewable diff, and that is the point.

Usage:
    python scripts/check_test_collection.py --root .
    python scripts/check_test_collection.py --root . --registry path/to.toml
    python scripts/check_test_collection.py --self-test

Exit codes:
    0 - every test file in the tree is collected, or registered with a reason
    1 - an unregistered uncollected file, a dead entry, or a bad entry
    2 - bad invocation, or the collection boundary could not be established
        (including a tree with no test files at all: a scan that examined
        nothing is an unknown verdict, never a pass)
"""

from __future__ import annotations

import re
import shlex
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from gate_evidence import expect, gate_argparser, parse_or_self_test, report_self_test, temp_repo

REGISTRY_NAME = "uncollected-tests-allowlist.toml"

# An unknown verdict. Never 0: a scan that examined nothing, or that could not
# find the collection boundary, must not be indistinguishable from a clean tree.
_UNKNOWN = 2

# Directories that hold other people's code or machine output. Dot-directories
# are named INDIVIDUALLY rather than matched by a `part.startswith(".")` rule,
# which is what this list used to be. That rule swallowed `.github/` too, and
# `.github/scripts/` is where a repo's CI helper tests live -- five of them in
# factory-gitops, one of which had not run since Factory#711 and was found by
# hand rather than by this gate (Factory#926). A deny-list goes stale toward
# scanning a new cache directory, which is noisy; the generic rule went stale
# toward not scanning real tests, which is the false-clean direction.
_SKIP_DIRS = frozenset(
    {
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        "vendor",
        "site-packages",
        "migrations",
        ".git",
        ".venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
    }
)

# Rejected reasons, and the floor on a real one. Same shape as
# `check_gate_liveness.py` and PFactory's `factory_invariants._PLACEHOLDER`;
# copied in spirit rather than imported because those live in other repos.
_PLACEHOLDER_REASON = re.compile(r"^\s*(todo|tbd|n/?a|none|placeholder|grandfathered)\b", re.I)
_MIN_REASON_WORDS = 6
_ISSUE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*#\d+$")

# pytest flags that consume the NEXT token. Without this, `-m "not slow"` makes
# "not slow" look like a collected path, and `-o asyncio_mode=auto` makes the
# whole repo look collected. Long options overwhelmingly use `--opt=value`.
_VALUE_FLAGS = frozenset(
    {
        "-m",
        "-k",
        "-n",
        "-p",
        "-o",
        "-c",
        "-W",
        "--rootdir",
        "--junitxml",
        "--maxfail",
        "--durations",
    }
)

# Flags that NARROW what pytest collects. Handling them properly means
# reimplementing pytest's ignore semantics; not handling them means reporting a
# file as collected when it is not, which is the false-clean direction. So the
# gate declines to answer instead.
_NARROWING_FLAGS = ("--ignore", "--deselect")

# Invocations that run no tests at all. Found the hard way: PFactory's
# runner-images.yml smoke-tests a built image with `pytest --version`, and
# reading that as a path-argument-free invocation made the ENTIRE repo look
# collected -- a silent clean verdict over 8 uncollected files. A probe is not
# evidence of a collection boundary.
_NON_COLLECTING = frozenset(
    {"--version", "-V", "--help", "-h", "--fixtures", "--markers", "--co", "--collect-only"}
)

# `docker run <image> pytest ...` runs the IMAGE's tests, not this repo's, so
# its paths say nothing about what this repo collects. Same false-clean shape
# as the probe above and found in the same file.
_FOREIGN_RUNNERS = frozenset({"docker", "podman", "nerdctl", "kubectl", "ssh"})

# `pip install pytest pytest-asyncio jsonschema httpx` is not a test run, and
# read as one it says the repo collects a directory called `httpx`. The hub's
# own contracts.yml has exactly that line -- caught here only because the
# "collected path does not exist" guard refused to report a verdict.
_NOT_AN_INVOCATION = frozenset({"pip", "pip3", "uv", "poetry", "conda", "npm", "install"})

_SHELL_BREAKS = frozenset({"&&", "||", ";", "|", "&"})

# A YAML mapping entry whose key is not `run` is not a command, however much it
# looks like one. Found wiring this gate into CFactory (Factory#844): that repo's
# only pytest step is titled `name: Backend pytest`, which shlex-splits to
# ["name:", "Backend", "pytest"] -- a pytest token with no path arguments after
# it, i.e. "the whole repo is collected". CFactory's real invocation is a bare
# `pytest` too, so the verdict happened to be right; but narrow that line to
# `pytest tests/` and the job TITLE would have kept the boundary at `.` and the
# newly-orphaned files would have read clean. A false clean sourced from a
# step's name is the same defect this gate exists to close, one level up.
#
# Only `run` survives, so an `args:`-style pytest invocation through a custom
# action is skipped as well. That errs toward a NARROWER boundary -- more files
# reported uncollected -- which is the loud direction, not the false-clean one.
# Lines inside a `run: |` block are bare commands and match no key, so they are
# unaffected.
_YAML_KEY = re.compile(r"^\s*(?:-\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*:")

# `# test-collection: <repo path> [...]` on the same logical line as a pytest
# invocation: the repo directory a container path corresponds to. See the module
# docstring for why this is an annotation on a real invocation and not a list.
_DIRECTIVE = re.compile(r"#\s*test-collection:\s*(.+?)\s*$")
_RUNS_PYTEST = re.compile(r"(?:^|[\s/\'\"])py\.?test\b")

# `python3 .github/scripts/test_cred_sync.py` -- a test run that is not a pytest
# run. Four of factory-gitops' five CI helper tests are invoked exactly this way
# and no pytest appears anywhere in that repo's workflows, so without this the
# gate has nothing to derive a boundary from and answers "unknown" forever
# (Factory#926). The file IS executed by CI, which is the whole question this
# gate asks, so it is collected -- as itself and nothing else. An exact-file
# boundary cannot widen past the file named on the line, which is why this is
# safe in a way that a directory guess would not be.
_PYTHON = re.compile(r"^python(?:3(?:\.\d+)?)?$")


class BadEntryError(ValueError):
    """A registry entry that cannot be allowed to exist."""


class BadDirectiveError(ValueError):
    """A `# test-collection:` directive that must not be believed."""


@dataclass(frozen=True)
class Exemption:
    """One registered uncollected test file, validated on construction.

    Validated in ``__post_init__`` so a placeholder cannot reach the registry
    at all: an entry reading ``reason = "TODO"`` satisfies any check that only
    asks whether a reason is present.
    """

    path: str
    reason: str
    issue: str

    def __post_init__(self) -> None:
        if not self.path:
            raise BadEntryError("an entry needs a `path`")
        if not _ISSUE.match(self.issue):
            raise BadEntryError(
                f"{self.path}: `issue` must look like Repo#123 -- an uncollected test with "
                f"nobody's name on it is a permanent exception; got {self.issue!r}"
            )
        if _PLACEHOLDER_REASON.match(self.reason) or len(self.reason.split()) < _MIN_REASON_WORDS:
            raise BadEntryError(
                f"{self.path}: `reason` must say why this file is not collected and why that "
                f"is not a defect; got {self.reason!r}"
            )


def _is_skippable(path: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.parts)


def _is_test_name(name: str) -> bool:
    """Both naming conventions. Shared so the scan and the derivation agree."""
    return name.startswith("test_") or name.removesuffix(".py").endswith("_test")


def _test_files(root: Path) -> list[str]:
    """Every ``test_*.py`` / ``*_test.py`` in the tree, as posix paths from *root*.

    Both conventions, unconditionally. Deciding which convention "applies" in a
    repo would mean the second one arriving is invisible until someone notices.
    """
    found = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if _is_skippable(relative):
            continue
        if _is_test_name(path.name):
            found.append(relative.as_posix())
    return sorted(found)


def _logical_lines(text: str) -> list[str]:
    """Workflow text with ``\\`` continuations joined into one logical line.

    A ``run: |`` block writes multi-line pytest invocations with the paths on
    continuation lines (AIFactory's ci.yml does), and reading only the first
    line would see no path arguments and conclude the whole repo is collected
    -- a false clean, and the exact shape where this gate reports nothing while
    looking healthy.

    Comments are NOT filtered here: ``shlex.split(..., comments=True)`` in
    ``_pytest_path_args`` already drops everything from a ``#`` onward, and a
    second mechanism doing the same job means neither one has a test that fails
    when it is removed.
    """
    joined: list[str] = []
    buffer = ""
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        joined.append(buffer + stripped)
        buffer = ""
    if buffer:
        joined.append(buffer)
    return joined


def _pytest_path_args(line: str) -> tuple[list[str], bool] | None:
    """``(path arguments, narrowed)`` for a pytest invocation, or None if there is none.

    *narrowed* is True when the line carries a flag that shrinks what pytest
    collects; the caller turns that into an unknown verdict rather than
    guessing in the false-clean direction.
    """
    key = _YAML_KEY.match(line)
    if key and key.group(1) != "run":
        return None
    declared = _DIRECTIVE.search(line)
    if declared:
        return _annotated(line[: declared.start()], declared.group(1))
    try:
        tokens = shlex.split(line, comments=True)
    except ValueError:
        return None
    invocation = _invocation_args(tokens)
    if invocation is not None:
        return invocation
    script = _script_run(tokens)
    return ([script], False) if script is not None else None


def _invocation_args(tokens: list[str]) -> tuple[list[str], bool] | None:
    """The same, for a line whose pytest call the shell split leaves visible."""
    for index, token in enumerate(tokens):
        if token.rsplit("/", 1)[-1] not in {"pytest", "py.test"}:
            continue
        prefix = [t.rsplit("/", 1)[-1] for t in tokens[:index]]
        if any(t in _FOREIGN_RUNNERS or t in _NOT_AN_INVOCATION for t in prefix):
            return None
        rest = tokens[index + 1 :]
        if any(token.split("=", 1)[0] in _NON_COLLECTING for token in rest):
            return None
        return _args_after(rest)
    return None


def _script_run(tokens: list[str]) -> str | None:
    """The test file a direct ``python3 path/test_x.py`` invocation executes.

    Only a test-named script counts. `python3 scripts/deploy.py` is a build
    step, not a collection boundary, and reading it as one would mark a
    directory collected on the strength of a script that runs no tests.
    """
    for index, token in enumerate(tokens):
        if not _PYTHON.match(token.rsplit("/", 1)[-1]):
            continue
        prefix = [t.rsplit("/", 1)[-1] for t in tokens[:index]]
        if any(t in _FOREIGN_RUNNERS or t in _NOT_AN_INVOCATION for t in prefix):
            return None
        for arg in tokens[index + 1 :]:
            if arg in _SHELL_BREAKS:
                return None
            if arg.startswith("-"):
                continue
            # Python's FIRST positional is the script, and only it. Scanning the
            # whole line for a test-named `.py` would read `python -m pyflakes
            # .github/scripts/test_x.py` -- a lint step -- as proof that file
            # runs. `python -m ...` and `python -c ...` land on a module name or
            # a code string here and decline on their own.
            name = PurePosixPath(arg).name
            return arg if name.endswith(".py") and _is_test_name(name) else None
        return None
    return None


def _annotated(command: str, raw: str) -> tuple[list[str], bool] | None:
    """A ``# test-collection:``-annotated line: the paths the author declares.

    Read TEXTUALLY, not from the token walk above, because the invocation this
    exists for is ``sh -c 'pip install pytest && python -m pytest /app/...'`` --
    one shell word, with pytest inside the quotes, which the walk cannot see
    (that is precisely why the derivation cannot resolve it).

    Three things still hold, and they are what keep this from being a hand-
    declared list: the line must really run pytest, ``--ignore``/``--deselect``
    still make the verdict unknown, and a probe collects nothing however it is
    annotated. Path safety is in ``_directive_paths`` and existence is checked
    by the caller's usual stale-path guard.
    """
    if not _RUNS_PYTEST.search(command):
        return None
    words = [word.strip("\"'") for word in command.split()]
    if any(word.split("=", 1)[0] in _NON_COLLECTING for word in words):
        return None
    narrowed = any(word.split("=", 1)[0] in _NARROWING_FLAGS for word in words)
    return _directive_paths(raw), narrowed


def _directive_paths(raw: str) -> list[str]:
    """Repo paths from a ``# test-collection:`` directive, or raise.

    Rejecting rather than ignoring: a directive nobody parsed is a workflow
    author believing a boundary that was never read, which is the same
    false-clean shape one level up.
    """
    paths = raw.split()
    if not paths:
        raise BadDirectiveError("`# test-collection:` names no path")
    for path in paths:
        parts = PurePosixPath(path).parts
        if path.startswith(("/", "-")) or path in {".", ""} or ".." in parts:
            raise BadDirectiveError(
                f"`# test-collection: {path}` must name a repo-relative path inside the tree; "
                "`.` would mark the whole repo collected from a comment"
            )
    return [path.rstrip("/") for path in paths]


def _args_after(tokens: list[str]) -> tuple[list[str], bool]:
    paths: list[str] = []
    narrowed = False
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token in _SHELL_BREAKS:
            break
        if token.startswith("-"):
            narrowed = narrowed or token.split("=", 1)[0] in _NARROWING_FLAGS
            skip_next = token in _VALUE_FLAGS
            continue
        # `tests/foo.py::test_case` selects one case out of a file; the file is
        # what decides collection.
        paths.append(token.split("::", 1)[0].rstrip("/"))
    return paths, narrowed


def _testpaths(root: Path) -> list[str]:
    """``testpaths`` from a root pytest config, which narrows a bare ``pytest``.

    Read for the false-clean direction only: without it, a repo whose CI runs a
    bare ``pytest`` while ``testpaths`` narrows collection to ``tests/`` would
    be reported as collecting everything.
    """
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            return []
        options = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
        declared = options.get("testpaths", [])
        if isinstance(declared, str):
            return declared.split()
        return [str(item) for item in declared]
    for name in ("pytest.ini", "tox.ini", "setup.cfg"):
        config = root / name
        if not config.is_file():
            continue
        match = re.search(r"^\s*testpaths\s*=(.*)$", config.read_text(encoding="utf-8"), re.M)
        if match:
            return match.group(1).split()
    return []


@dataclass(frozen=True)
class Boundary:
    """What CI collects, and the workflow lines that say so."""

    paths: tuple[str, ...]
    evidence: tuple[str, ...]
    narrowed: bool
    bad_directives: tuple[str, ...] = ()


def _collected(root: Path) -> Boundary:
    """Derive the collection boundary from the repo's own workflows."""
    paths: set[str] = set()
    evidence: list[str] = []
    bad_directives: list[str] = []
    narrowed = False
    workflows = root / ".github" / "workflows"
    for workflow in sorted(workflows.glob("*.y*ml")) if workflows.is_dir() else []:
        try:
            text = workflow.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in _logical_lines(text):
            try:
                parsed = _pytest_path_args(line)
            except BadDirectiveError as exc:
                bad_directives.append(f"{workflow.name}: {exc}")
                continue
            if parsed is None:
                continue
            args, line_narrowed = parsed
            narrowed = narrowed or line_narrowed
            evidence.append(f"{workflow.name}: {' '.join(args) or '<whole repo>'}")
            # No path arguments: pytest collects from the rootdir, narrowed only
            # by a `testpaths` setting.
            paths.update(args or _testpaths(root) or ["."])
    return Boundary(tuple(sorted(paths)), tuple(evidence), narrowed, tuple(bad_directives))


def _is_collected(relative: str, collected: tuple[str, ...]) -> bool:
    return any(
        prefix in (".", relative) or relative.startswith(f"{prefix}/") for prefix in collected
    )


def _load_registry(path: Path) -> tuple[dict[str, Exemption], list[str]]:
    if not path.is_file():
        return {}, []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return {}, [f"{path.name} is not readable TOML: {exc}"]
    entries: dict[str, Exemption] = {}
    problems: list[str] = []
    for raw in data.get("allow", []):
        try:
            entry = Exemption(
                path=str(raw.get("path", "")),
                reason=str(raw.get("reason", "")),
                issue=str(raw.get("issue", "")),
            )
        except BadEntryError as exc:
            problems.append(str(exc))
            continue
        if entry.path in entries:
            problems.append(f"{entry.path}: listed twice")
            continue
        entries[entry.path] = entry
    return entries, problems


def run_check(root: Path, registry_path: Path | None = None) -> int:
    registry_path = registry_path or root / REGISTRY_NAME
    files = _test_files(root)
    boundary = _collected(root)
    entries, problems = _load_registry(registry_path)

    if not files:
        # Named as such: a zero-item check. "Scanned nothing" and "found
        # nothing wrong" must never print the same verdict (Factory#832).
        print(f"ERROR: no test files found under {root} -- this gate examined ZERO items.")  # noqa: T201
        return _UNKNOWN
    if not boundary.evidence:
        print(  # noqa: T201
            f"ERROR: no pytest invocation found in {root}/.github/workflows -- the collection "
            "boundary is unknown, which is not the same as 'nothing is collected'."
        )
        return _UNKNOWN
    if boundary.narrowed:
        print(  # noqa: T201
            "ERROR: a workflow pytest invocation carries --ignore/--deselect, which narrows "
            "collection. This gate cannot model that, and guessing would report uncollected "
            "files as collected."
        )
        return _UNKNOWN
    if boundary.bad_directives:
        for problem in boundary.bad_directives:
            print(f"ERROR: {problem}")  # noqa: T201
        print(  # noqa: T201
            "A `# test-collection:` directive that cannot be read is an unknown boundary, not a "
            "line to skip past."
        )
        return _UNKNOWN
    missing = [p for p in boundary.paths if p != "." and not (root / p).exists()]
    if missing:
        print(  # noqa: T201
            "ERROR: workflows collect paths that do not exist in the tree "
            f"({', '.join(missing)}) -- either the workflow is stale or the boundary was "
            "misread; a verdict against the wrong boundary is worse than none."
        )
        return _UNKNOWN

    uncollected = [path for path in files if not _is_collected(path, boundary.paths)]
    unregistered = [path for path in uncollected if path not in entries]
    dead = sorted(set(entries) - set(uncollected))

    for path in unregistered:
        print(f"FAIL {path}: a test file outside every collected path, with no registry entry")  # noqa: T201
    for path in dead:
        print(  # noqa: T201
            f"FAIL {path}: registry entry matches nothing -- the file is collected or gone. "
            "Delete the entry (Factory#788)."
        )
    for problem in problems:
        print(f"FAIL {registry_path.name}: {problem}")  # noqa: T201

    # Counts on every verdict, pass or fail. A gate that says only "OK" cannot
    # be told apart from one that examined zero items.
    print(  # noqa: T201
        f"Examined {len(files)} test files against {len(boundary.paths)} collected path(s) "
        f"[{', '.join(boundary.paths)}] from {len(boundary.evidence)} workflow pytest "
        f"invocation(s); {len(uncollected)} uncollected, {len(entries)} registered, "
        f"{len(unregistered)} unregistered, {len(dead)} dead entries."
    )
    return 1 if (unregistered or dead or problems) else 0


def _pfactory_tree(root: Path) -> Path:
    """PFactory's layout at the moment #607 went undetected, minimised."""
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "jobs:\n  backend:\n    steps:\n"
        "      # the sweep in Factory#844 read exactly this line\n"
        "      - run: apps/backend/.venv/bin/pytest tests/ apps/web-server/tests/ -m 'not slow'\n"
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_collected.py").write_text("def test_ok(): assert True\n")
    (root / "apps" / "web-server" / "tests").mkdir(parents=True)
    (root / "apps" / "web-server" / "tests" / "test_web.py").write_text("def test_ok(): ...\n")
    agents = root / "apps" / "backend" / "agents"
    agents.mkdir(parents=True)
    alarm = agents / "test_refactoring.py"
    alarm.write_text(
        "from agents import coder\n"
        "def test_entry_point():\n"
        "    assert hasattr(coder, 'run_autonomous_agent')\n"
    )
    return alarm


_GOOD_REASON = (
    "Asserts an entry point that does not exist yet (PFactory#607); collecting it "
    "turns CI red on a real defect that is being fixed separately."
)


def _registry(
    root: Path, *, path: str, reason: str = _GOOD_REASON, issue: str = "PFactory#607"
) -> None:
    (root / REGISTRY_NAME).write_text(
        f'[[allow]]\npath = "{path}"\nreason = """{reason}"""\nissue = "{issue}"\n'
    )


def run_check_text(root: Path, workflow: Path, text: str) -> int:
    """Write *text* as the repo's workflow and re-run the gate. Self-test only."""
    workflow.write_text(text)
    return run_check(root)


def _self_test() -> int:
    failures: list[str] = []
    with temp_repo() as root:
        _pfactory_tree(root)
        # The real case: the alarm for PFactory#607, uncollected and unlisted.
        expect(failures, run_check(root) == 1, "an uncollected test file with no entry is red")

        _registry(root, path="apps/backend/agents/test_refactoring.py")
        expect(failures, run_check(root) == 0, "...and green once registered with a real reason")

        for placeholder in ("TODO", "n/a", "grandfathered", "flaky"):
            _registry(root, path="apps/backend/agents/test_refactoring.py", reason=placeholder)
            expect(failures, run_check(root) == 1, f"a {placeholder!r} reason is rejected")

        _registry(root, path="apps/backend/agents/test_refactoring.py", issue="nobody")
        expect(failures, run_check(root) == 1, "an entry without a Repo#123 issue is rejected")

        # Factory#788: an entry that matches nothing must fail, or the list
        # becomes an ignore list that only ever grows.
        _registry(root, path="apps/backend/agents/test_deleted.py")
        expect(failures, run_check(root) == 1, "a registry entry matching nothing is red")

        # The same file, once CI actually collects it: the entry is now dead.
        _registry(root, path="apps/backend/agents/test_refactoring.py")
        workflow = root / ".github" / "workflows" / "ci.yml"
        original = workflow.read_text(encoding="utf-8")
        workflow.write_text(original.replace("tests/ apps", "tests/ apps/backend apps"))
        expect(failures, run_check(root) == 1, "widening collection makes the entry dead, not moot")
        workflow.write_text(original)

    _self_test_boundary(failures)
    _self_test_dot_directories(failures)
    return report_self_test(failures)


def _self_test_dot_directories(failures: list[str]) -> None:
    """Factory#926: `.github/scripts/` is inside the boundary, `.venv/` is not.

    The rule this replaced skipped every dot-prefixed path component, so five
    real test files in factory-gitops were invisible to the scan -- one of them
    had not run since Factory#711 and was found by hand. Narrowing the skip is
    only half of it: those tests run as `python3 .github/scripts/test_X.py`, and
    a derivation that only knows `pytest` turns one blind spot into five
    registry entries.
    """
    with temp_repo() as root:
        _pfactory_tree(root)
        _registry(root, path="apps/backend/agents/test_refactoring.py")
        helpers = root / ".github" / "scripts"
        helpers.mkdir(parents=True)
        (helpers / "test_cred_sync.py").write_text("assert True\n")
        workflow = root / ".github" / "workflows" / "ci.yml"
        steps = "jobs:\n  backend:\n    steps:\n      - run: |\n"
        real = steps + "          pytest tests/ apps/web-server/tests/\n"
        ran = real + steps + "          python3 .github/scripts/test_cred_sync.py\n"

        expect(
            failures,
            run_check_text(root, workflow, real) == 1,
            "a test file under .github/ is scanned, not skipped as a dot-directory",
        )
        expect(
            failures,
            run_check_text(root, workflow, ran) == 0,
            "...and a direct `python3 <path>/test_x.py` run collects exactly that file",
        )

        # The deny-list must still skip what the old rule skipped. A vendored
        # tree full of test files is the reason the rule existed at all.
        vendored = root / ".venv" / "lib" / "site" / "pytest"
        vendored.mkdir(parents=True)
        (vendored / "test_vendored.py").write_text("assert True\n")
        (root / ".mypy_cache" / "3.13").mkdir(parents=True)
        (root / ".mypy_cache" / "3.13" / "test_cached.py").write_text("assert True\n")
        expect(
            failures,
            run_check_text(root, workflow, ran) == 0,
            ".venv/ and .mypy_cache/ are still skipped by name",
        )

        # The boundary is the FILE. Its neighbour in the same directory does
        # not run, and a directory-shaped boundary would report it clean.
        (helpers / "test_never_run.py").write_text("assert True\n")
        expect(
            failures,
            run_check_text(root, workflow, ran) == 1,
            "a script run collects that file, never its directory",
        )
        (helpers / "test_never_run.py").unlink()

        # A script run only counts when the script is a test. Otherwise every
        # `python3 scripts/deploy.py` step would declare a collection boundary.
        for command, why in (
            ("python3 scripts/deploy.py", "a non-test script is not a collection boundary"),
            (
                "python -m pyflakes .github/scripts/test_cred_sync.py",
                "a `python -m` lint step over a test file is not a test run",
            ),
            ("python3 -c 'import sys'", "`python -c` runs no file"),
            ("docker run img python3 .github/scripts/test_cred_sync.py", "a foreign runner"),
        ):
            expect(
                failures,
                run_check_text(root, workflow, real + steps + f"          {command}\n") == 1,
                f"{why} leaves .github/scripts/test_cred_sync.py uncollected",
            )


def _self_test_boundary(failures: list[str]) -> None:
    """The derived-boundary half: the parses whose failure mode is a false clean."""
    with temp_repo() as root:
        alarm = _pfactory_tree(root)
        workflow = root / ".github" / "workflows" / "ci.yml"
        steps = "jobs:\n  backend:\n    steps:\n      - run: |\n"

        _self_test_directive(failures, root, workflow, steps)

        # A multi-line invocation. Read line-by-line it has no path arguments,
        # so the whole repo looks collected and the alarm disappears.
        workflow.write_text(steps + "          pytest \\\n            tests/ \\\n            -q\n")
        expect(failures, run_check(root) == 1, "a `\\`-continued pytest line keeps its paths")

        # A comment quoting a pytest command must not widen the boundary.
        workflow.write_text(
            "# CI runs `pytest apps/backend` -- prose, not a command\n"
            + steps
            + "          pytest tests/\n"
        )
        expect(failures, run_check(root) == 1, "a commented pytest line does not collect anything")

        # A step TITLED after pytest is not a pytest invocation. CFactory's only
        # pytest step is `name: Backend pytest`, which reads as a bare pytest --
        # the whole repo collected -- from a line that runs nothing
        # (Factory#844). The `run:` below is what the boundary must come from.
        workflow.write_text(
            "jobs:\n  backend:\n    steps:\n"
            "      - name: Backend pytest\n"
            "        run: pytest tests/\n"
        )
        expect(failures, run_check(root) == 1, "a step named after pytest is not an invocation")
        expect(failures, _collected(root).paths == ("tests",), "...and does not widen the boundary")

        # `-m "not slow"` must not read as a collected path called "not slow".
        workflow.write_text(steps + '          pytest -m "not slow" tests/\n')
        boundary = _collected(root)
        expect(failures, boundary.paths == ("tests",), "a -m value is not a collected path")

        # The PFactory runner-images.yml trap, both halves. Each of these read
        # as "a pytest invocation with no path arguments", i.e. the whole repo
        # collected, i.e. a clean verdict over the uncollected alarm.
        probe = steps + "          pytest tests/\n" + steps + "          pytest --version\n"
        expect(
            failures,
            run_check_text(root, workflow, probe) == 1,
            "`pytest --version` collects nothing",
        )
        foreign = (
            steps + "          pytest tests/\n" + steps + "          docker run img pytest -q\n"
        )
        expect(
            failures,
            run_check_text(root, workflow, foreign) == 1,
            "a pytest inside `docker run` is the image's tests, not this repo's",
        )

        # The hub's own contracts.yml line. Read as an invocation it claims the
        # repo collects directories named `jsonschema` and `httpx`.
        install = (
            steps
            + "          pytest tests/\n"
            + steps
            + "          pip install pytest jsonschema httpx\n"
        )
        expect(
            failures,
            run_check_text(root, workflow, install) == 1,
            "`pip install pytest ...` is not a pytest invocation",
        )

        # A bare pytest collects everything -- so nothing is uncollected.
        workflow.write_text(steps + "          PYTHONPATH=apps/backend pytest -v\n")
        expect(failures, run_check(root) == 0, "a bare pytest collects the whole repo")

        # ...unless testpaths narrows it. Without this the tree above reads clean.
        (root / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
        )
        expect(failures, run_check(root) == 1, "testpaths narrows a bare pytest invocation")
        (root / "pyproject.toml").unlink()

        # Narrowing flags and stale paths are unknown verdicts, not passes.
        workflow.write_text(steps + "          pytest . --ignore=apps/backend\n")
        expect(failures, run_check(root) == _UNKNOWN, "--ignore is unknown, never a pass")
        workflow.write_text(steps + "          pytest tests/ apps/gone/tests\n")
        expect(failures, run_check(root) == _UNKNOWN, "a collected path that is absent is unknown")

        # No pytest anywhere: "I could not find the boundary", not "clean".
        workflow.write_text("jobs:\n  lint:\n    steps:\n      - run: ruff check .\n")
        expect(failures, run_check(root) == _UNKNOWN, "no pytest invocation is unknown, not green")

        # A tree with no test files at all is the zero-item case.
        workflow.write_text(steps + "          pytest tests/\n")
        alarm.unlink()
        (root / "tests" / "test_collected.py").unlink()
        (root / "apps" / "web-server" / "tests" / "test_web.py").unlink()
        expect(failures, run_check(root) == _UNKNOWN, "a tree with no test files is unknown")


def _self_test_directive(failures: list[str], root: Path, workflow: Path, steps: str) -> None:
    """The container-path directive (TFactory#1134), and what it must refuse.

    Leaves the tree exactly as it found it: the cases after this one in
    ``_self_test_boundary`` end by emptying the tree of test files, and a
    leftover directory would make the zero-item case stop being one.
    """
    container = root / "portal_testing"
    container.mkdir()
    (container / "test_container.py").write_text("def test_ok(): ...\n")
    _registry(root, path="apps/backend/agents/test_refactoring.py")
    real = steps + "          pytest tests/ apps/web-server/tests/\n"
    docker = real + steps + "          docker run img sh -c 'pytest /app/portal_testing -q'"

    # The reading TFactory#1134 is about: the mounted directory's tests DO run,
    # and the derivation has no way to know that from `/app/portal_testing`.
    expect(
        failures,
        run_check_text(root, workflow, docker + "\n") == 1,
        "a container pytest path reads as uncollected with no directive",
    )
    expect(
        failures,
        run_check_text(root, workflow, docker + "  # test-collection: portal_testing\n") == 0,
        "...and the directive maps it back to the repo directory it mounts",
    )

    # The three ways an annotation could hand out a false clean.
    for bad, why in (
        (".", "`# test-collection: .` marks the whole repo collected from a comment"),
        ("../elsewhere", "a directive pointing outside the tree"),
        ("/app/portal_testing", "a directive that just repeats the container path"),
    ):
        expect(
            failures,
            run_check_text(root, workflow, f"{docker}  # test-collection: {bad}\n") == _UNKNOWN,
            f"{why} is rejected, not believed",
        )
    expect(
        failures,
        run_check_text(root, workflow, docker + "  # test-collection: portal_typo\n") == _UNKNOWN,
        "a directive naming a path absent from the tree is unknown, never a pass",
    )

    # It annotates an INVOCATION. On anything else it is prose.
    prose = real + "      # test-collection: portal_testing\n"
    expect(
        failures,
        run_check_text(root, workflow, prose) == 1,
        "a directive on a line that runs no pytest collects nothing",
    )
    expect(
        failures,
        run_check_text(root, workflow, docker + " --ignore=x  # test-collection: portal_testing\n")
        == _UNKNOWN,
        "--ignore on an annotated line is still an unknown verdict",
    )

    (container / "test_container.py").unlink()
    container.rmdir()
    (root / REGISTRY_NAME).unlink()


def main(argv: list[str] | None = None) -> int:
    parser = gate_argparser(__doc__)
    parser.add_argument("--root", help="repo root to scan")
    parser.add_argument("--registry", help=f"registry file (default: <root>/{REGISTRY_NAME})")
    early, args = parse_or_self_test(parser, argv, _self_test)
    if early is not None:
        return early
    assert args is not None  # noqa: S101 - parse_or_self_test guarantees this when early is None
    if not args.root:
        parser.error("--root is required (or pass --self-test)")
    root = Path(args.root).resolve()
    return run_check(root, Path(args.registry).resolve() if args.registry else None)


if __name__ == "__main__":
    sys.exit(main())
