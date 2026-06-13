#!/usr/bin/env python3
"""PARR cross-service seam regression — fail loudly at the boundaries.

Phase 1 of the make-it-great plan (Factory#41). The June 2026 review found that
nearly every production bug of the prior month lived at a *factory boundary*, not
inside a factory: completion side-effects that never fired, contracts rejected by
payload shape, a Cloudflare bot-block, an endpoint that drifted between releases.
Per-repo unit tests can't see these — there's no real network, no auth, no live
version skew in a unit test.

This script drives the deployed PARR fleet and asserts at each seam, exiting
non-zero (and naming the seam) the moment one breaks. Run it nightly so boundary
regressions get caught by a gate instead of by a user.

Modes:
  (default)  fast seam checks — health + auth + ingest-shape + cockpit threading.
             ~30s. Catches the regression class the first benchmark run hit
             (Cloudflare UA block, auth, endpoint drift, project resolution).
  --smoke    explicit alias for the default read-only fast path, for use as a
             pre-merge / post-deploy gate.
  --full     also drive a real create-and-run build through AIFactory to a
             terminal state and a TFactory ingest to terminal — the full
             end-to-end nightly (tens of minutes).
  --dry-run  print the seam plan and exit 0 (wiring check, no calls).

Teardown: the smoke probe creates a PFactory plan session, and --full creates an
AIFactory task. Both are cleaned up best-effort after the run (the AIFactory task
is DELETEd; the PFactory session is rejected/closed, since PFactory has no
plan-session DELETE endpoint). Cleanup never fails the gate — a teardown error is
logged, not raised — so it is safe to point at a live environment.
Set PARR_NO_TEARDOWN=1 to keep probe artifacts (e.g. to debug a failure).

Endpoints + auth come from the environment (same names the benchmark uses):
  PFACTORY_API / AIFACTORY_API / TFACTORY_API / CFACTORY_API
  AIFACTORY_TOKEN / TFACTORY_TOKEN / PFACTORY_TOKEN / CFACTORY_TOKEN
A single FACTORY_TOKEN is accepted as a fallback for all four.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULTS = {
    "pfactory": "https://pfactory.freundcloud.org.uk",
    "aifactory": "https://aifactory.freundcloud.org.uk",
    "tfactory": "https://tfactory.freundcloud.org.uk",
    "cfactory": "https://cfactory.freundcloud.org.uk",
}


def _endpoint(svc: str) -> str:
    return os.environ.get(f"{svc.upper()}_API", DEFAULTS[svc]).rstrip("/")


def _token(svc: str) -> str:
    return os.environ.get(f"{svc.upper()}_TOKEN") or os.environ.get("FACTORY_TOKEN", "")


class Seam:
    """One boundary assertion. Records pass/fail with a human-readable reason."""

    def __init__(self, name: str):
        self.name = name
        self.ok: bool | None = None
        self.detail = ""

    def passed(self, detail: str = "") -> "Seam":
        self.ok, self.detail = True, detail
        return self

    def failed(self, detail: str) -> "Seam":
        self.ok, self.detail = False, detail
        return self


def _call(svc: str, method: str, path: str, body: dict | None = None, timeout: int = 30):
    """JSON request with the Cloudflare-friendly UA + bearer auth + 5xx retry the
    live fleet needs (the exact lessons from the first benchmark run)."""
    url = f"{_endpoint(svc)}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Content-Type": "application/json",
        # Cloudflare 403s the default Python-urllib UA as a bot.
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) factory-parr-regression/1.0",
    }
    tok = _token(svc)
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                raw = resp.read().decode() or "{}"
            body_out = json.loads(raw) if raw.strip().startswith(("{", "[")) else {"raw": raw}
            return resp.status, body_out
        except urllib.error.HTTPError as exc:
            if exc.code >= 500 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            return exc.code, {"error": exc.read().decode()[:300]}
        except urllib.error.URLError as exc:
            last = str(exc)
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
    return 0, {"error": last or "unreachable"}


# ── Teardown ─────────────────────────────────────────────────────────────────

# Best-effort cleanup actions for probe artifacts created during the run. Each is
# an (svc, method, path, body) call replayed after the seams run. Never raises.
_CLEANUP: list[tuple[str, str, str, dict | None]] = []


def _register_cleanup(svc: str, method: str, path: str, body: dict | None = None) -> None:
    _CLEANUP.append((svc, method, path, body))


def _teardown() -> None:
    """Remove probe artifacts created during the run, best-effort.

    A cleanup failure MUST NOT fail the gate, so everything here is swallowed and
    logged. PFactory has no plan-session DELETE, so its probe session is rejected
    (closed) rather than hard-deleted; the AIFactory task is DELETEd."""
    if os.environ.get("PARR_NO_TEARDOWN"):
        if _CLEANUP:
            print(f"\nTeardown skipped (PARR_NO_TEARDOWN); {len(_CLEANUP)} probe artifact(s) left.")
        return
    if not _CLEANUP:
        return
    print("\nTeardown (best-effort cleanup of probe artifacts):")
    for svc, method, path, body in reversed(_CLEANUP):
        try:
            code, _ = _call(svc, method, path, body, timeout=15)
            ok = bool(code) and 200 <= code < 300
            print(f"  [{'ok  ' if ok else 'skip'}] {method} {svc}{path} -> {code}")
        except Exception as exc:  # noqa: BLE001 — cleanup must never fail the gate
            print(f"  [err ] {method} {svc}{path} -> {exc}")


# ── Seam checks ──────────────────────────────────────────────────────────────


def check_health(svc: str) -> Seam:
    """Each factory answers on its API with auth (catches Cloudflare/auth/DNS
    regressions — the class that 403'd the first benchmark run)."""
    s = Seam(f"{svc}:reachable")
    for path in ("/api/health", "/api/healthz", "/health", "/api/projects"):
        code, _ = _call(svc, "GET", path, timeout=15)
        if code and code < 500 and code != 404:
            return s.passed(f"{path} -> {code}")
    return s.failed(f"no healthy endpoint (last code {code})")


def check_pfactory_ingest_shape() -> Seam:
    """PFactory accepts the documented ingest-text contract (catches the
    'no acceptance criteria' / payload-shape drift that 400s the plan leg)."""
    s = Seam("pfactory:ingest-accepts")
    code, body = _call("pfactory", "POST", "/api/plan/sessions/ingest-text", {
        "title": "parr-regression probe", "category": "software", "channel": "portal",
        "text": "# probe\n\n## Acceptance Criteria\n- AC#1: GET /healthz returns 200",
    }, timeout=30)
    if code == 200 and (body.get("session_id") or body.get("id")):
        sid = body.get("session_id") or body.get("id")
        # PFactory has no plan-session DELETE; reject closes the probe session.
        _register_cleanup("pfactory", "POST", f"/api/plan/sessions/{sid}/reject",
                          {"reason": "parr-regression teardown"})
        return s.passed(f"session={sid}")
    return s.failed(f"ingest-text -> {code}: {str(body)[:160]}")


def check_tfactory_ingest_shape() -> Seam:
    """TFactory's ingest validates the current {project_id,spec_id,spec_text}
    contract (catches the endpoint drift that silently routed to the old API)."""
    s = Seam("tfactory:ingest-contract")
    # Empty body must 422 with the field schema — proving the v0.9.x contract is
    # live. A 404/405 means the endpoint moved (the drift we hit before).
    code, body = _call("tfactory", "POST", "/api/specs/ingest", {}, timeout=20)
    if code == 422 and "project_id" in json.dumps(body):
        return s.passed("422 names project_id/spec_id/spec_text")
    if code in (404, 405):
        return s.failed(f"endpoint drift: /api/specs/ingest -> {code}")
    return s.failed(f"unexpected -> {code}: {str(body)[:160]}")


def check_cfactory_threading() -> Seam:
    """CFactory's cockpit API answers for work items / events (the observability
    seam — events must land somewhere we can see)."""
    s = Seam("cfactory:cockpit-api")
    for path in ("/api/workitems", "/api/events", "/api/refresh"):
        code, _ = _call("cfactory", "GET", path, timeout=20)
        if code and code < 500 and code != 404:
            return s.passed(f"{path} -> {code}")
    return s.failed(f"no cockpit endpoint answered (last {code})")


# ── Full end-to-end (opt-in) ─────────────────────────────────────────────────


def check_build_lifecycle(timeout: int) -> Seam:
    """Drive a trivial create-and-run task through AIFactory to a terminal state
    — the build seam, end to end on the live cluster."""
    s = Seam("aifactory:build-lifecycle")
    code, projs = _call("aifactory", "GET", "/api/projects", timeout=20)
    items = projs if isinstance(projs, list) else projs.get("projects", [])
    pid = next((p.get("id") or p.get("project_id") for p in items
                if "aifactory-demo" in str(p.get("name", ""))), None)
    if not pid:
        return s.failed("no aifactory-demo project to build in")
    code, task = _call("aifactory", "POST", "/api/tasks", {
        "title": "PARR regression: /healthz endpoint",
        "description": "Add a GET /healthz endpoint returning {\"status\":\"ok\"}.",
        "project_id": pid, "metadata": {"scenario": "parr-regression"},
    }, timeout=30)
    tid = task.get("task_id") or task.get("id")
    if not tid:
        return s.failed(f"task create -> {code}: {str(task)[:140]}")
    _register_cleanup("aifactory", "DELETE", f"/api/tasks/{tid}")
    _call("aifactory", "POST", f"/api/tasks/{tid}/start", {"auto_continue": True}, timeout=30)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code, st = _call("aifactory", "GET", f"/api/tasks/{tid}/status", timeout=15)
        if st and not st.get("is_running", True):
            return s.passed(f"task {tid} reached terminal")
        time.sleep(20)
    return s.failed(f"task {tid} did not finish within {timeout}s")


# ── Driver ───────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full", action="store_true", help="also drive a real build lifecycle")
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="fast, read-only seam-shape checks only (the default mode; explicit "
        "for use as a pre-merge / post-deploy gate). Ignored if --full is set.",
    )
    ap.add_argument("--dry-run", action="store_true", help="print the seam plan, no calls")
    ap.add_argument("--build-timeout", type=int, default=3600)
    args = ap.parse_args()

    # --smoke is the read-only fast path (the default); --full wins if both given.
    if args.smoke and not args.full:
        args.full = False

    plan = [
        "health: pfactory, aifactory, tfactory, cfactory reachable + authed",
        "pfactory: ingest-text accepts the documented contract",
        "tfactory: /api/specs/ingest validates the current contract (no drift)",
        "cfactory: cockpit API answers for work items / events",
    ]
    if args.full:
        plan.append("aifactory: create-and-run reaches a terminal state (build seam)")

    if args.dry_run:
        print("PARR regression seam plan:")
        for p in plan:
            print(f"  - {p}")
        return 0

    seams: list[Seam] = []
    try:
        for svc in ("pfactory", "aifactory", "tfactory", "cfactory"):
            seams.append(check_health(svc))
        seams.append(check_pfactory_ingest_shape())
        seams.append(check_tfactory_ingest_shape())
        seams.append(check_cfactory_threading())
        if args.full:
            seams.append(check_build_lifecycle(args.build_timeout))
    finally:
        # Always clean up probe artifacts, even if a seam raised mid-run.
        _teardown()

    failed = [s for s in seams if not s.ok]
    print("\nPARR cross-service seam regression")
    print("=" * 50)
    for s in seams:
        mark = "PASS" if s.ok else "FAIL"
        print(f"  [{mark}] {s.name:32} {s.detail}")
    print("=" * 50)
    if failed:
        print(f"\n{len(failed)} seam(s) FAILED: " + ", ".join(s.name for s in failed))
        print("A boundary regressed — this is the bug class unit tests can't see.")
        return 1
    print(f"\nAll {len(seams)} seams green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
