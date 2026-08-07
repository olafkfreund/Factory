#!/usr/bin/env python3
"""Are the baked agent-CLI pins drifting behind npm? (Factory#459)

The three agent CLIs are pinned in each service's Dockerfile and baked into the
runtime image (TFactory#791). NOTHING proposes bumps for them: the Renovate
GitHub App is not installed on this account — zero Renovate PRs across all five
repos, ever — and Dependabot's docker ecosystem parses only ``FROM`` lines, so it
cannot see an ``npm install -g @pkg@version`` bake step. factory-gitops'
``renovate.json`` records both facts and says so plainly; its own customManager
has matched nothing since the pins moved out of the manifests.

THE FAILURE MODE THIS CONVERTS INTO A SIGNAL. "No bump PRs" and "nothing to
update" look identical from outside, which is why the same gap sat unnoticed for
nine weeks in Factory#436. A freshness assertion cannot be silently not-running:
if it stops, CI goes red. That is the property option 3 of Factory#459 has and
the other two do not, and it is why this exists even though installing the
Renovate App (option 1) would be the fuller fix — they are complementary, and
only one of them can be done without account-level authorisation.

WHY A SCHEDULED HUB WATCHDOG AND NOT A PER-REPO TEST, which is the opposite call
from Factory#552 and deliberately so. A pull request does not make a pin stale;
TIME does. A pre-merge test would fail PRs for something the PR did not cause,
which is the cry-wolf shape that gets a gate muted (Factory#538). Staleness is
watched out of band, on a clock, like every other drift here.

PROPOSES THE FIX, NEVER MERGES IT (``--open-bump-pr``, added for Factory#459).
Detection alone leaves a gap nobody closes: an alert that says "bump this" and no
hand that does it just goes red on a slower clock. So the same module that
resolves the versions also opens the pull request — one fixed branch per repo, so
a PR left sitting is refreshed in place and never joined by a second one. It stops
at the PR: the bumped CLI is baked into the image that runs agents against
untrusted repository content, and the thing that makes proposing it automatically
defensible is that each service repo's ``image-build.yml`` compiles
``target: runtime`` on the PR while the bake step runs ``claude --version`` inside
that build. That gate has to actually run, which is also why the workflow uses a
PAT: a pull request opened with ``GITHUB_TOKEN`` triggers no workflows at all.

Usage:
    python3 scripts/check_cli_freshness.py                 # live, needs network
    python3 scripts/check_cli_freshness.py --max-age-days 45
    python3 scripts/check_cli_freshness.py --open-bump-pr  # needs GH_TOKEN
    python3 scripts/check_cli_freshness.py --self-test     # offline

WHICH REF IT JUDGES: ``main``, because ``main`` is what deploys (Factory#612).
It read ``HEAD`` — the DEFAULT branch, ``dev`` in all three repos — so a bump
merged to dev silenced the alarm while the image the fleet runs still baked the
old CLI. The default branch is still read, and reported on its own line, because
"has anyone bumped it" and "is the fleet current" are two different facts and
only one of them is about what is running.

Exit codes:
    0 - every pin on the deployed ref is within the window
    1 - a pin has been behind the registry for longer than the window, or is
        AHEAD of it: a version the registry no longer serves as latest, which is
        what a yank looks like from here (Factory#615). This used to claim exit 0
        for the ahead case and exit 1 calling it "behind"; the contract and the
        behaviour now agree, and they agree on alerting, because "the version we
        deploy is not the one npm serves" is not a passing state.
    2 - a pin or a registry entry could not be read (never a silent pass:
        a check that cannot see its subject must say so, Factory#500)
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from selftest_report import SelfTest, gate_argparser

_OWNER = "olafkfreund"
_RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{ref}/Dockerfile"
_REGISTRY = "https://registry.npmjs.org/{pkg}"

# THE REF THE VERDICT IS ABOUT (Factory#612). `main`, because `main` is what
# deploys: each service's deploy.yml triggers on push-to-main, and AIFactory
# ships via release/X.Y.Z -> main. factory-gitops' cli-canary already reads main
# and says why; this watchdog read HEAD, which raw.githubusercontent resolves to
# the DEFAULT branch — `dev` in all three repos.
#
# That is an alarm that goes quiet on the wrong event. A bump merged to dev
# silenced it immediately while the image the fleet actually runs still baked the
# old CLI until a release landed, so "the watchdog is green" and "the deployed
# pin is current" quietly stopped being the same statement. Measured on
# 2026-08-07: all three default to dev, and AIFactory's dev was 19 commits ahead
# of main. The pins happened to agree, which is exactly why the gap was invisible
# — it is luck, not a guarantee, and #609's bump proposer (which targets the
# default branch, where the repos take changes) makes it reachable in normal
# operation.
_DEPLOYED_REF = "main"

# The ref that answers "has anyone bumped it yet". HEAD is the default branch, so
# this needs no API call to resolve. Reported, never alerted on: intent is not
# deployment, and only one of these two facts is about what the fleet runs.
_PROPOSED_REF = "HEAD"

# Repos that bake the agent CLIs. CFactory is deliberately absent: it is the
# cockpit and runs no agent, so it pins none of these — an absence with a reason,
# which is what Factory#401 removed dead config for stating any other way.
REPOS: tuple[str, ...] = ("AIFactory", "PFactory", "TFactory")

# The pins, as they appear in the bake step:  @scope/name@1.2.3
_PIN_RE = re.compile(r"(@[\w.-]+/[\w.-]+)@(\d+\.\d+\.\d+[^\s\\\"']*)")

# Only these three are tracked. Matching every `@scope/pkg@version` in a
# Dockerfile would sweep in build-time tooling whose version is deliberately
# frozen, and a watchdog that reports things nobody intends to bump is the noise
# that gets a real alert muted.
TRACKED: tuple[str, ...] = (
    "@anthropic-ai/claude-code",
    "@openai/codex",
    "@google/gemini-cli",
)

# How far behind the registry a pin may fall before it is an alert. Generous on
# purpose: these CLIs ship every few days, so a tight window would be red
# permanently and mean nothing (Factory#538). A month behind is neglect; a week
# behind is Tuesday.
_DEFAULT_MAX_AGE_DAYS = 30.0

_EXIT_BAD_INVOCATION = 2


class SourceUnavailableError(RuntimeError):
    """A Dockerfile or registry entry could not be read. Never a pass."""


@dataclass(frozen=True)
class Pin:
    repo: str
    package: str
    version: str


def parse_pins(repo: str, dockerfile: str) -> list[Pin]:
    """The tracked CLI pins declared in *dockerfile*."""
    found = {pkg: ver for pkg, ver in _PIN_RE.findall(dockerfile) if pkg in TRACKED}
    return [Pin(repo, pkg, found[pkg]) for pkg in TRACKED if pkg in found]


def fetch_dockerfile(repo: str, ref: str = _DEPLOYED_REF, *, timeout: int = 20) -> str:
    url = _RAW.format(owner=_OWNER, repo=repo, ref=ref)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            body: str = response.read().decode("utf-8")
            return body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceUnavailableError(f"{repo}: cannot fetch {url}: {exc}") from exc


def fetch_registry(package: str, *, timeout: int = 30) -> dict[str, Any]:
    url = _REGISTRY.format(pkg=package.replace("/", "%2f"))
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            doc: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return doc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise SourceUnavailableError(f"{package}: cannot read the npm registry: {exc}") from exc


def _published(doc: dict[str, Any], version: str) -> datetime | None:
    stamp = (doc.get("time") or {}).get(version)
    if not stamp:
        return None
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _release(version: str) -> tuple[int, ...]:
    """The numeric release part of *version*, for ordering. ``0.147.0`` -> (0, 147, 0).

    Enough for semver-shaped npm versions and deliberately no more: a pre-release
    suffix is dropped, so ``1.0.0-rc.1`` and ``1.0.0`` order equal and fall
    through to the behind branch, which then names the difference truthfully
    rather than inventing a rule about release candidates nobody here ships.
    """
    return tuple(int(part) for part in re.findall(r"\d+", version.split("-", maxsplit=1)[0])[:3])


def assess(
    pin: Pin, doc: dict[str, Any], *, now: datetime, max_age_days: float
) -> tuple[str, str | None]:
    """``(report_line, failure_or_None)`` for one pin against the registry.

    The age measured is of the LATEST release, not of the pinned one: the
    question is "how long has a newer version been available and ignored", which
    is what a missing bot causes. A pin published long ago but still latest is
    not stale — it is simply a package that has not moved.

    A pin AHEAD of latest gets its own verdict and its own wording (Factory#615).
    It used to be reported as "behind", with the age of an OLDER release offered
    as evidence of neglect:

        AIFactory/@openai/codex 0.147.0 — behind 0.146.0, published 218d ago

    Backwards, and backwards about the case that matters most: a pin ahead of
    latest is what an upstream YANK looks like from here, which is the event
    factory-gitops' cli-canary exists to catch. It still alerts — the docstring
    used to promise exit 0 for this and that promise was the wrong half to keep,
    since "the version we deploy is no longer served by the registry" is not a
    passing state. It just no longer calls it staleness, and no longer starts a
    clock on someone else's release.
    """
    latest = (doc.get("dist-tags") or {}).get("latest")
    if not latest:
        raise SourceUnavailableError(f"{pin.package}: registry has no dist-tags.latest")
    if latest == pin.version:
        return f"  {pin.repo}/{pin.package} {pin.version} — current", None
    if _release(pin.version) > _release(latest):
        return (
            f"  {pin.repo}/{pin.package} {pin.version} — AHEAD of the registry, "
            f"whose latest is {latest}",
            f"{pin.repo}: {pin.package} is pinned to {pin.version}, which is NEWER than the "
            f"registry's latest ({latest}). The pinned release is no longer the one npm "
            "serves and may have been yanked — a fresh image build would install something "
            "else. This is not staleness: check whether it was unpublished before bumping.",
        )
    released = _published(doc, latest)
    if released is None:
        # Newer version exists but the registry gave no date. Report it rather
        # than skip it: an unmeasurable age is not the same as being current.
        return (
            f"  {pin.repo}/{pin.package} {pin.version} — behind {latest} (release date unknown)",
            f"{pin.repo}: {pin.package} pinned {pin.version}, latest {latest}, "
            "publish date unreadable",
        )
    age = (now - released).total_seconds() / 86400.0
    line = f"  {pin.repo}/{pin.package} {pin.version} — behind {latest}, published {age:.0f}d ago"
    if age > max_age_days:
        return line, (
            f"{pin.repo}: {pin.package} pinned {pin.version}; {latest} has been "
            f"available for {age:.0f} days (window {max_age_days:.0f})"
        )
    return line, None


def unshipped(pin: Pin, proposed: str | None) -> str | None:
    """One report line when the default branch and *pin*'s deployed ref disagree.

    The second of the two facts Factory#612 asks for. *pin* is what ``main`` has,
    which is what the cluster runs and what the verdict above is about;
    *proposed* is what the default branch has, which answers "has anyone bumped
    it". Reported, never alerted on: a bump sitting on ``dev`` is real progress
    and turning it into its own failure would be the cry-wolf shape this job
    already refuses. But it is not silence either — while the two disagree, the
    red above means "the fix is written and has not shipped", which is a
    different instruction to the reader than "nobody bumped it".
    """
    if proposed is None:
        return (
            f"      ^ not pinned at all on the default branch; only on {_DEPLOYED_REF}. "
            "The bake step moved on one ref and not the other."
        )
    if proposed == pin.version:
        return None
    return (
        f"      ^ the default branch has {proposed}; {_DEPLOYED_REF} still has "
        f"{pin.version}, and {_DEPLOYED_REF} is the ref that deploys"
    )


# ---------------------------------------------------------------------------
# The remediation half. Detection above says a pin is behind; this proposes the
# bump, because nothing else does.
#
# WHY NOT RENOVATE, which is option 1 of Factory#459 and the option that issue
# was left open for. It needs an account-level App install only the owner can
# perform, so it cannot be built or proven here — and it would arrive with its
# own config surface in three repos to describe pins this module already parses.
# The two are not exclusive: if the App is ever installed, delete this half
# rather than let two bots rewrite the same line, exactly as AIFactory retired
# its own pins-bump job when Dependabot's docker lane started working (#1104).
#
# WHY NOT DEPENDABOT, verified rather than repeated. Dependabot is not dormant
# in these repos: it bumps `FROM node:24-bookworm-slim` and
# `FROM chainguard/python@sha256:...` in the very same Dockerfile, daily, and
# raises npm PRs from the package.json manifests. It has never raised one for
# these three CLIs, in any repo on this account, ever. The docker parser reads
# image references — FROM, and not even `COPY --from`, which .github/dependabot.yml
# already records as an uncovered gap. Twenty lines below the FROM it does bump,
# `npm install -g @anthropic-ai/claude-code@2.1.215` is a shell argument in a RUN
# layer and no `package-ecosystem` has a parser for that. This is a demonstrated
# blind spot in a live bot, not an assumption about a dormant one.
#
# WHY THE PR IS NOT MERGED, and why it must not be. The bumped pin is baked into
# the image that runs agents against untrusted repository content. What makes an
# unreviewed bump survivable is that each service repo's image-build.yml compiles
# `target: runtime` on every pull request, and the bake step itself runs
# `claude --version` inside that build — so a yanked or broken release fails the
# PR rather than the fleet. That gate genuinely runs, which is the only reason
# proposing bumps automatically is defensible at all. It is still not a reason to
# merge them automatically, and this never does: no merge call, no auto-merge.
# ---------------------------------------------------------------------------

_BUMP_BRANCH = "chore/agent-cli-pins"
_API = "https://api.github.com"
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def rewrite(dockerfile: str, updates: dict[str, str]) -> str:
    """*dockerfile* with each package in *updates* moved to its new version.

    Raises when it was asked to change something and changed nothing. A rewriter
    that matches no pin and reports success IS this issue: factory-gitops'
    renovate.json customManager is still valid, still "working", and has matched
    nothing since TFactory#791 moved the pins out of the manifests it scans. A
    silent no-op is the failure mode, so it is the one thing made loud here.
    """

    def sub(match: re.Match[str]) -> str:
        package = match.group(1)
        return f"{package}@{updates[package]}" if package in updates else match.group(0)

    out = _PIN_RE.sub(sub, dockerfile)
    if updates and out == dockerfile:
        raise SourceUnavailableError(
            f"rewrote nothing for {', '.join(sorted(updates))}: the bake step no longer "
            "matches `@scope/package@version`, so this bumper is editing a file it cannot "
            "actually see. Fix the pattern rather than shipping a no-op."
        )
    return out


def _api(method: str, path: str, token: str, body: dict[str, Any] | None = None) -> Any:
    request = urllib.request.Request(  # noqa: S310
        f"{_API}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "factory-cli-freshness",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        raw = response.read()
    return json.loads(raw) if raw else None


def _pr_body(repo: str, updates: dict[str, str], base: str) -> str:
    lines = [f"- `{pkg}` -> `{ver}`" for pkg, ver in sorted(updates.items())]
    others = ", ".join(f"`{r}`" for r in REPOS if r != repo)
    return "\n".join(
        [
            "Opened by the hub `agent-CLI freshness` job (Factory#459, #556).",
            "",
            f"Bumps the baked agent-CLI pins in the `npm install -g` step, on `{base}`:",
            "",
            *lines,
            "",
            "## Why a workflow and not a bot",
            "",
            "Nothing else proposes these. The Renovate App is not installed on this",
            "account, and Dependabot -- which bumps the `FROM` lines in this same",
            "Dockerfile every day -- cannot see an `npm install -g @scope/pkg@version`",
            "argument, because no `package-ecosystem` parses shell arguments in a RUN",
            "layer. So these three have been hand-managed with nothing watching them.",
            "",
            "## Do not merge this without the image build passing",
            "",
            "These CLIs run inside the image that executes untrusted repository content.",
            "`image-build.yml` compiles `target: runtime` on this PR and the bake step",
            "runs `claude --version` during that build, so a yanked or broken upstream",
            "release fails here rather than in the fleet. Nothing auto-merges this, on",
            "purpose.",
            "",
            f"{others} get the same branch in the same run, to the same versions.",
            "factory-gitops' `cli-canary` asserts all three repos pin identically, so",
            "merging one alone turns that check red -- merge the set.",
            "",
            "## If this sits",
            "",
            "The branch is rebased onto the base branch on every weekly run, so this PR is",
            "refreshed in place and a second one is never opened. If it is still unmerged",
            "when the newest release passes the 30-day window, the hub `cli-freshness`",
            'job goes red -- that red now means "a bump PR has been ignored" rather than',
            '"nobody bumped". Close this PR to reject the bump; the next run will reopen',
            "it, which is the point. Hold it back deliberately by raising the window with",
            "the reason, as that job's own guidance says.",
        ]
    )


def propose_bump(repo: str, registry: dict[str, dict[str, Any]], token: str) -> str:
    """Open or refresh one PR bumping every behind pin in *repo*. One line back."""
    meta = _api("GET", f"/repos/{_OWNER}/{repo}", token)
    base = meta["default_branch"]
    blob = _api("GET", f"/repos/{_OWNER}/{repo}/contents/Dockerfile?ref={base}", token)
    dockerfile = base64.b64decode(blob["content"]).decode()

    pins = parse_pins(repo, dockerfile)
    if not pins:
        raise SourceUnavailableError(
            f"{repo}: no tracked CLI pin found in its Dockerfile, so there is nothing this "
            "bumper could propose. The bake step moved again; fix the path, do not skip."
        )
    updates = {}
    for pin in pins:
        latest = (registry[pin.package].get("dist-tags") or {}).get("latest")
        if not latest:
            raise SourceUnavailableError(f"{pin.package}: registry has no dist-tags.latest")
        if latest != pin.version:
            updates[pin.package] = latest

    ref = f"/repos/{_OWNER}/{repo}/git/refs/heads/{_BUMP_BRANCH}"
    if not updates:
        # Nothing to propose. A PR left open from an earlier run is now a
        # zero-diff PR, and an automation whose PRs mean nothing is worse than no
        # automation -- it teaches people to skip the channel. Retract it.
        try:
            _api("DELETE", ref, token)
        except urllib.error.HTTPError as exc:
            # "No branch to delete" is the STEADY STATE, not an error: once the
            # pins are current this is what every weekly run does. GitHub answers
            # a delete of a missing ref with 422, not 404, and treating that as a
            # failure would turn the healthy case red every week — which is the
            # cry-wolf shape this whole job is supposed to avoid.
            if exc.code not in (_HTTP_NOT_FOUND, _HTTP_UNPROCESSABLE):
                raise
            return f"  {repo}: every tracked pin is current, nothing proposed"
        return f"  {repo}: every tracked pin is current, retracted the stale bump branch"

    summary = ", ".join(f"{pkg.split('/')[-1]} {ver}" for pkg, ver in sorted(updates.items()))
    head = _api("GET", f"/repos/{_OWNER}/{repo}/git/ref/heads/{base}", token)["object"]["sha"]

    # BUILD THE COMMIT FIRST, THEN MOVE THE BRANCH TO IT IN ONE STEP. The obvious
    # shape -- force the branch back to base, then write the file onto it -- is
    # what this did first, and it is WRONG in a way that only shows on the SECOND
    # run: between those two calls the branch is byte-identical to base, so the
    # pull request momentarily has zero commits, and GitHub CLOSES a pull request
    # whose commits all disappear. Measured, not theorised: the refresh that was
    # meant to update AIFactory#1198 and TFactory#978 closed them both instead,
    # `closed` and `head_ref_force_pushed` sharing a timestamp in the PR timeline,
    # while PFactory#483 -- opened fresh, never refreshed -- stayed open. The next
    # run then sees no open PR and opens a NEW one, every week: exactly the PR
    # churn one fixed branch exists to prevent, manufactured by the mechanism
    # meant to prevent it.
    #
    # Committing against the base tree and force-updating the ref to the finished
    # commit means the branch is never equal to base, so the PR is never emptied.
    # It still rebases onto the base every run: one clean diff, no conflict rot.
    base_tree = _api("GET", f"/repos/{_OWNER}/{repo}/git/commits/{head}", token)["tree"]["sha"]
    tree = _api(
        "POST",
        f"/repos/{_OWNER}/{repo}/git/trees",
        token,
        {
            "base_tree": base_tree,
            "tree": [
                {
                    "path": "Dockerfile",
                    "mode": "100644",
                    "type": "blob",
                    "content": rewrite(dockerfile, updates),
                }
            ],
        },
    )["sha"]
    commit = _api(
        "POST",
        f"/repos/{_OWNER}/{repo}/git/commits",
        token,
        {
            "message": f"chore(deps): bump baked agent-CLI pins ({summary})\n\nFactory#459",
            "tree": tree,
            "parents": [head],
        },
    )["sha"]
    try:
        _api("PATCH", ref, token, {"sha": commit, "force": True})
    except urllib.error.HTTPError as exc:
        if exc.code not in (_HTTP_NOT_FOUND, _HTTP_UNPROCESSABLE):
            raise
        _api(
            "POST",
            f"/repos/{_OWNER}/{repo}/git/refs",
            token,
            {"ref": f"refs/heads/{_BUMP_BRANCH}", "sha": commit},
        )

    title = f"chore(deps): bump baked agent-CLI pins ({summary})"
    body = _pr_body(repo, updates, base)
    open_prs = _api(
        "GET", f"/repos/{_OWNER}/{repo}/pulls?state=open&head={_OWNER}:{_BUMP_BRANCH}", token
    )
    if open_prs:
        # Refresh the description too: the branch just moved to newer versions
        # than the ones the body was written for.
        pull = _api(
            "PATCH",
            f"/repos/{_OWNER}/{repo}/pulls/{open_prs[0]['number']}",
            token,
            {"title": title, "body": body},
        )
        verb = "refreshed"
    else:
        pull = _api(
            "POST",
            f"/repos/{_OWNER}/{repo}/pulls",
            token,
            {"title": title, "head": _BUMP_BRANCH, "base": base, "body": body},
        )
        verb = "opened"

    # Post-condition, and the check that would have caught the bug above on the
    # run that introduced it rather than an hour later. "I pushed a branch and
    # called an endpoint" is not the same as "there is an open pull request", and
    # a bumper reporting success over a closed PR is an automation nobody merges
    # by construction. GitHub reports the state it actually has; believe that.
    if pull.get("state") != "open":
        raise SourceUnavailableError(
            f"{repo}: {verb} {pull.get('html_url')} but GitHub reports it "
            f"{pull.get('state')!r}, not open. The bump was not actually proposed."
        )
    return f"  {repo}: {verb} {pull['html_url']} -- {summary}"


def _bump(registry: dict[str, dict[str, Any]]) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        sys.stderr.write(
            "cli-freshness: --open-bump-pr needs GH_TOKEN with contents+pull-requests write "
            "on " + ", ".join(REPOS) + ". Refusing to run without it rather than reporting "
            "that it found nothing to do.\n"
        )
        return _EXIT_BAD_INVOCATION
    try:
        lines = [propose_bump(repo, registry, token) for repo in REPOS]
    except (SourceUnavailableError, urllib.error.HTTPError) as exc:
        sys.stderr.write(f"cli-freshness: cannot propose a bump: {exc}\n")
        return _EXIT_BAD_INVOCATION
    print("Bump proposals:")  # noqa: T201
    print("\n".join(lines))  # noqa: T201
    return 0


def _selftest() -> int:
    t = SelfTest("cli-freshness")
    now = datetime(2026, 8, 3, tzinfo=UTC)

    dockerfile = (
        "RUN npm install -g \\\n"
        "        @anthropic-ai/claude-code@2.1.215 \\\n"
        "        @openai/codex@0.144.6 \\\n"
        "        @google/gemini-cli@0.51.0\n"
        "RUN npm install -g @some/unrelated-tool@9.9.9\n"
    )
    pins = parse_pins("AIFactory", dockerfile)
    t.req(len(pins) == len(TRACKED), f"all tracked pins parsed (got {len(pins)})")
    t.req(
        all(p.package in TRACKED for p in pins),
        "an untracked package in the same bake step is ignored",
    )

    def doc(latest: str, when: str) -> dict[str, Any]:
        return {"dist-tags": {"latest": latest}, "time": {latest: when}}

    pin = Pin("AIFactory", "@openai/codex", "0.144.6")
    line, fail = assess(pin, doc("0.144.6", "2026-01-01T00:00:00Z"), now=now, max_age_days=30)
    t.req(fail is None, "a pin equal to latest is current, however old the release")

    line, fail = assess(pin, doc("0.146.0", "2026-07-29T00:00:00Z"), now=now, max_age_days=30)
    t.req(fail is None, "5 days behind is within a 30-day window")
    t.req("behind 0.146.0" in line, "the report names the newer version, not just a verdict")

    line, fail = assess(pin, doc("0.146.0", "2026-05-01T00:00:00Z"), now=now, max_age_days=30)
    t.req(fail is not None, "94 days behind is an alert (THE CASE WITH TEETH)")
    t.req(fail is not None and "0.146.0" in fail, "the failure names what to bump to")

    _, fail = assess(pin, doc("0.146.0", "2026-07-29T00:00:00Z"), now=now, max_age_days=0)
    t.req(fail is not None, "window=0 alerts immediately — the window is the only excuse")

    _, fail = assess(
        pin, {"dist-tags": {"latest": "0.146.0"}, "time": {}}, now=now, max_age_days=30
    )
    t.req(fail is not None, "a newer version with no publish date is reported, not skipped")

    t.req(
        set(TRACKED)
        == {
            "@anthropic-ai/claude-code",
            "@openai/codex",
            "@google/gemini-cli",
        },
        "the tracked set is enumerated, so narrowing it is visible",
    )
    t.req("CFactory" not in REPOS, "CFactory bakes no agent CLI and is deliberately absent")

    # A pin AHEAD of the registry (Factory#615). This used to read "behind
    # 0.146.0, published 218d ago" -- backwards, with an older release's age
    # offered as evidence of neglect.
    ahead = Pin("AIFactory", "@openai/codex", "0.147.0")
    line, fail = assess(ahead, doc("0.146.0", "2026-01-01T00:00:00Z"), now=now, max_age_days=30)
    t.req(fail is not None, "A PIN AHEAD OF THE REGISTRY ALERTS -- it is what a yank looks like")
    t.req("AHEAD" in line and "behind" not in line, "and is not described as being behind")
    t.req(fail is not None and "yanked" in fail, "the failure names the actual suspicion")
    t.req(
        fail is not None and "days" not in fail,
        "no staleness clock: the age of a release we are past means nothing",
    )
    _, still_behind = assess(pin, doc("0.146.0", "2026-05-01T00:00:00Z"), now=now, max_age_days=30)
    t.req(still_behind is not None, "control: genuinely behind is still behind")

    # The deployed ref (Factory#612). main is what deploy.yml ships; HEAD is the
    # default branch, which is `dev` and is not deployed.
    t.req(_DEPLOYED_REF == "main", "the verdict is about `main`, the ref that deploys")
    t.req(
        unshipped(Pin("AIFactory", "@openai/codex", "0.144.6"), "0.147.0") is not None,
        "A BUMP ON THE DEFAULT BRANCH THAT HAS NOT REACHED main IS REPORTED, not silence",
    )
    t.req(
        unshipped(Pin("AIFactory", "@openai/codex", "0.144.6"), "0.144.6") is None,
        "control: refs that agree say nothing, or the report is noise every week",
    )
    t.req(
        unshipped(Pin("AIFactory", "@openai/codex", "0.144.6"), None) is not None,
        "a pin present on main and absent from the default branch is reported too",
    )

    # The rewriter. Untested, this is the half that can silently propose nothing
    # and look like it worked -- which is the exact shape of the defect the whole
    # issue describes, so it gets the assertions with teeth.
    bumped = rewrite(dockerfile, {"@openai/codex": "0.147.0", "@google/gemini-cli": "0.54.4"})
    t.req("@openai/codex@0.147.0" in bumped, "the named pin moves to its new version")
    t.req("@google/gemini-cli@0.54.4" in bumped, "every named pin moves, not just the first")
    t.req(
        "@anthropic-ai/claude-code@2.1.215" in bumped,
        "a tracked pin NOT in the update set is left alone",
    )
    t.req("@some/unrelated-tool@9.9.9" in bumped, "an untracked package is never rewritten")
    t.req(len(parse_pins("AIFactory", bumped)) == len(TRACKED), "the result still parses")

    t.req(rewrite(dockerfile, {}) == dockerfile, "no updates is a no-op, not an error")

    matched_nothing = False
    try:
        rewrite("RUN npm install -g claude-code\n", {"@openai/codex": "0.147.0"})
    except SourceUnavailableError:
        matched_nothing = True
    t.req(matched_nothing, "A REWRITE THAT MATCHES NOTHING RAISES, it does not report success")

    t.req(
        bool(_BUMP_BRANCH) and "/" in _BUMP_BRANCH,
        "one fixed branch per repo, so a sitting PR is refreshed and never duplicated",
    )
    return t.finish()


def main(argv: list[str] | None = None) -> int:
    ap = gate_argparser(__doc__)
    ap.add_argument(
        "--max-age-days",
        type=float,
        default=_DEFAULT_MAX_AGE_DAYS,
        help=f"how long a newer release may sit unadopted (default {_DEFAULT_MAX_AGE_DAYS:.0f})",
    )
    ap.add_argument(
        "--open-bump-pr",
        action="store_true",
        help="propose the bump instead of reporting it: open or refresh one PR per repo "
        "(needs GH_TOKEN). Never merges.",
    )
    args = ap.parse_args(argv)

    if args.self_test:
        return _selftest()

    if args.open_bump_pr:
        try:
            registry = {pkg: fetch_registry(pkg) for pkg in TRACKED}
        except SourceUnavailableError as exc:
            sys.stderr.write(f"cli-freshness: {exc}\n")
            return _EXIT_BAD_INVOCATION
        return _bump(registry)

    now = datetime.now(UTC)
    report: list[str] = []
    failures: list[str] = []
    try:
        registry = {pkg: fetch_registry(pkg) for pkg in TRACKED}
        for repo in REPOS:
            pins = parse_pins(repo, fetch_dockerfile(repo, _DEPLOYED_REF))
            if not pins:
                failures.append(
                    f"{repo}: no tracked CLI pin found in its Dockerfile on {_DEPLOYED_REF}. "
                    "Either the bake step moved again (as TFactory#791 moved it out of the "
                    "manifests) or this watchdog is now looking in the wrong place — both "
                    "mean it is checking nothing here."
                )
                continue
            proposed = {
                p.package: p.version
                for p in parse_pins(repo, fetch_dockerfile(repo, _PROPOSED_REF))
            }
            report.append(f"{repo}:")
            for pin in pins:
                line, failure = assess(
                    pin, registry[pin.package], now=now, max_age_days=args.max_age_days
                )
                report.append(line)
                note = unshipped(pin, proposed.get(pin.package))
                if note:
                    report.append(note)
                if failure:
                    failures.append(failure)
    except SourceUnavailableError as exc:
        sys.stderr.write(f"cli-freshness: {exc}\n")
        return _EXIT_BAD_INVOCATION

    print("\n".join(report))  # noqa: T201
    print(  # noqa: T201
        f"\nTracked: {', '.join(TRACKED)} across {', '.join(REPOS)}; "
        f"window {args.max_age_days:.0f} days. Judged on `{_DEPLOYED_REF}`, the ref each "
        "service's deploy.yml ships; `^` lines are the default branch disagreeing."
    )
    if failures:
        print("\ncli-freshness FAILED:")  # noqa: T201
        for line in failures:
            print(f"  {line}")  # noqa: T201
        print(  # noqa: T201
            "\nBump the pin in that service's Dockerfile and let its cli-canary run "
            f"before merging, then ship it to `{_DEPLOYED_REF}` — merging to the default "
            "branch alone does not reach the cluster, and this job keeps reporting until "
            "it does (Factory#612). A `^` line above means exactly that: the bump exists "
            "and has not shipped."
        )
        return 1
    print("\ncli-freshness PASSED: every pinned agent CLI is within the window.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
