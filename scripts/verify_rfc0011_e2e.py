#!/usr/bin/env python3
"""RFC-0011 end-to-end verification harness (tier-policy mapping).

WHAT THIS EXERCISES (here, in-process, no live fleet)
-----------------------------------------------------
Given the per-repo RFC-0011 modules land, this harness asserts the *contract* of
the difficulty-tier routing — i.e. that each tier maps to exactly its row in the
normative routing table (RFC-0011 §3):

    | tier   | model  | review_tier | skip_planning | tfactory lanes              | merge          |
    |--------|--------|-------------|---------------|-----------------------------|----------------|
    | low    | haiku* | auto        | True          | unit (+api)                 | auto-merge     |
    | medium | sonnet | async       | True          | unit, api, integration      | async approval |
    | hard   | opus   | blocking    | False         | + mutation (+equivalence)   | blocking       |

    (*) low's contract model is ``haiku``; AIFactory resolves ``ollama:<m>`` at
        runtime (resolve_low_tier_model) and falls back to haiku.

It also asserts the two precedence rules:
  * **highest-wins** classification (hard > medium > low) when multiple tier
    labels are present, and
  * a **rewrite forces hard** (``change_mode == "migration"`` ⇒ tier hard) and
    pulls in the **equivalence** lane.

HOW IT GETS THE MAPPING
-----------------------
It prefers the *real* implementations so this harness verifies live code, not a
stale copy:
  * AIFactory ``pfactory.tiers``      — ``classify_tier`` / ``tier_for`` (precedence + migration).
  * PFactory  ``plan.emit.tier_profile`` — ``apply_tier`` (tier ⇒ execution/tfactory).
If a sibling repo is not importable (e.g. running in CI with only Factory
checked out), it falls back to a LOCAL COPY of the policy table embedded below
and clearly says so in the output. Either way the assertions are identical.

WHAT STILL NEEDS THE LIVE FLEET (out of scope here; tracked by RFC-0011 §6)
--------------------------------------------------------------------------
This harness does NOT spin up the poller, hosts, or the model providers. The
following are documented as the live-fleet acceptance steps (see RFC-0011 §10),
to be run against the demo repos once the poller + endpoints are deployed:
  * One labelled demo issue per tier on ``aifactory-demo`` (+ a rewrite) and
    asserting the *emitted* contract matches the row (model resolved, PR opened).
  * Idempotency: poll twice / kill mid-tick / delete the SQLite DB ⇒ exactly one
    downstream POST and one ``factory:queued`` label.
  * Cross-tracker: repeat the ``low`` case on a GitLab and an ADO project.
  * Merge gate: a green ``low`` with ``ci_parity=yes`` auto-merges; an
    under-verified change is held with a named reason.

Run:  python3 scripts/verify_rfc0011_e2e.py            # human-readable report
      python3 scripts/verify_rfc0011_e2e.py --selftest # same, exits non-zero on failure
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# Normative policy table (RFC-0011 §3). This is the single source of truth the
# assertions check against; it mirrors the RFC doc and the per-repo modules.
# --------------------------------------------------------------------------- #
POLICY = {
    "low": {
        "model": "haiku",  # contract default; ollama:<m> resolved at runtime
        "review_tier": "auto",
        "skip_planning": True,
        "lanes_required": {"unit"},
        "lanes_forbidden": {"mutation", "equivalence"},
        "merge": "auto-merge-when-green",
    },
    "medium": {
        "model": "sonnet",
        "review_tier": "async",
        "skip_planning": True,
        "lanes_required": {"unit", "api", "integration"},
        "lanes_forbidden": {"mutation"},
        "merge": "async-approval",
    },
    "hard": {
        "model": "opus",
        "review_tier": "blocking",
        "skip_planning": False,
        "lanes_required": {"unit", "api", "integration", "mutation"},
        "lanes_forbidden": set(),
        "merge": "blocking-approval",
    },
}


# --------------------------------------------------------------------------- #
# Try to import the real per-repo modules; fall back to local shims.
# --------------------------------------------------------------------------- #
def _sibling_paths() -> list[Path]:
    here = Path(__file__).resolve()
    siblings = here.parent.parent.parent  # .../GitHub/
    return [
        siblings / "AIFactory" / "apps" / "backend",
        siblings / "AIFactory" / "apps" / "backend" / "pfactory",
        siblings / "PFactory" / "apps" / "backend",
        siblings / "PFactory" / "apps" / "backend" / "plan" / "emit",
    ]


def _load_real_modules():
    """Return (classify_tier, tier_for, Tier, apply_tier) from the real repos,
    or (None, ...) for each that can't be imported."""
    for p in _sibling_paths():
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))

    classify_tier = tier_for = Tier = apply_tier = None
    try:
        from tiers import Tier as _Tier  # type: ignore
        from tiers import classify_tier as _ct  # type: ignore
        from tiers import tier_for as _tf  # type: ignore

        classify_tier, tier_for, Tier = _ct, _tf, _Tier
    except Exception:  # noqa: BLE001 — fall back to local shim
        pass

    try:
        from tier_profile import apply_tier as _at  # type: ignore

        apply_tier = _at
    except Exception:  # noqa: BLE001
        # phase_config (a PFactory dep of tier_profile) may be missing; that's fine.
        pass

    return classify_tier, tier_for, Tier, apply_tier


# --------------------------------------------------------------------------- #
# Local shims (used when a sibling repo is not importable). These mirror the
# real modules' behaviour for the slice this harness checks.
# --------------------------------------------------------------------------- #
class _Tier(str):
    LOW = "low"
    MEDIUM = "medium"
    HARD = "hard"


_RANK = {"low": 1, "medium": 2, "hard": 3}
_MODEL = {"low": "haiku", "medium": "sonnet", "hard": "opus"}
_REVIEW = {"low": "auto", "medium": "async", "hard": "blocking"}
_SKIP = {"low": True, "medium": True, "hard": False}


def _local_classify_tier(labels):
    best = None
    for name in labels or []:
        n = str(name).lower().replace("::", ":")
        if n.startswith("factory:"):
            t = n.split(":", 1)[1]
            if t in _RANK and (best is None or _RANK[t] > _RANK[best]):
                best = t
    return best


def _local_tier_for(tier, change_mode=None):
    t = tier or "medium"
    if change_mode and str(change_mode).lower() == "migration":
        return "hard"
    return t


def _local_apply_tier(contract, tier):
    t = (tier or "").lower()
    if ":" in t:
        t = t.rsplit(":", 1)[-1]
    if t not in _RANK:
        return contract
    ex = contract.setdefault("execution", {})
    ex["model"] = _MODEL[t]
    ex["review_tier"] = _REVIEW[t]
    ex["skip_planning"] = _SKIP[t]
    ex["autonomy_tier"] = t
    tf = contract.get("tfactory")
    if isinstance(tf, dict):
        lanes = list(tf.get("lanes") or ["unit"])
        if t == "medium":
            for L in ("api", "integration"):
                if L not in lanes:
                    lanes.append(L)
        elif t == "hard":
            for L in ("api", "integration", "mutation"):
                if L not in lanes:
                    lanes.append(L)
        tf["lanes"] = lanes
    return contract


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def _tier_value(tier_obj) -> str:
    """Normalise a Tier enum / shim / string to its lowercase value."""
    val = getattr(tier_obj, "value", tier_obj)
    return str(val).lower()


def run() -> tuple[list[Result], dict[str, bool]]:
    real_ct, real_tf, real_Tier, real_at = _load_real_modules()

    classify_tier = real_ct or _local_classify_tier
    tier_for = real_tf or _local_tier_for
    apply_tier = real_at or _local_apply_tier

    using_real = {
        "classify_tier": real_ct is not None,
        "tier_for": real_tf is not None,
        "apply_tier": real_at is not None,
    }

    results: list[Result] = []

    def check(name, cond, detail=""):
        results.append(Result(name, bool(cond), detail))

    # 1. Each tier maps to its policy-table row via apply_tier.
    for tier, row in POLICY.items():
        contract = {
            "execution": {},
            "tfactory": {"lanes": ["unit"]},
        }
        apply_tier(contract, tier)
        ex = contract["execution"]
        lanes = set(contract["tfactory"]["lanes"])

        check(
            f"{tier}: model == {row['model']}",
            ex.get("model") == row["model"],
            f"got model={ex.get('model')!r}",
        )
        check(
            f"{tier}: review_tier == {row['review_tier']}",
            ex.get("review_tier") == row["review_tier"],
            f"got review_tier={ex.get('review_tier')!r}",
        )
        check(
            f"{tier}: skip_planning == {row['skip_planning']}",
            ex.get("skip_planning") == row["skip_planning"],
            f"got skip_planning={ex.get('skip_planning')!r}",
        )
        check(
            f"{tier}: autonomy_tier stamped == {tier}",
            ex.get("autonomy_tier") == tier,
            f"got autonomy_tier={ex.get('autonomy_tier')!r}",
        )
        check(
            f"{tier}: lanes ⊇ {sorted(row['lanes_required'])}",
            row["lanes_required"].issubset(lanes),
            f"got lanes={sorted(lanes)}",
        )
        check(
            f"{tier}: lanes ∌ {sorted(row['lanes_forbidden']) or '∅'}",
            not (row["lanes_forbidden"] & lanes),
            f"got lanes={sorted(lanes)}",
        )

    # 2. Precedence: highest-wins classification.
    check(
        "precedence: {low,hard} -> hard",
        _tier_value(classify_tier(["factory:low", "factory:hard"])) == "hard",
        f"got {classify_tier(['factory:low', 'factory:hard'])!r}",
    )
    check(
        "precedence: {low,medium} -> medium",
        _tier_value(classify_tier(["factory:low", "factory:medium"])) == "medium",
    )
    check(
        "classify: no tier label -> None",
        classify_tier(["type:feature", "pfactory"]) is None,
    )

    # 3. Rewrite forces hard (migration ⇒ hard), regardless of label.
    classified = classify_tier(["factory:low"])
    forced = tier_for(
        _Stub(classified) if real_tf is None else _RealStub(classified, real_Tier),
        change_mode="migration",
    )
    check(
        "migration: factory:low + change_mode=migration -> hard",
        _tier_value(forced) == "hard",
        f"got {forced!r}",
    )

    # 4. A hard rewrite pulls in the equivalence lane (RFC-0010 attaches it; the
    #    contract must carry it for TFactory). We assert the contract shape: when
    #    a rewrite is hard, the tfactory block must allow + require equivalence.
    rewrite_contract = {
        "execution": {},
        # migration_block (PFactory) attaches the equivalence lane upstream; we
        # model that here and verify apply_tier(hard) does not drop it.
        "tfactory": {"lanes": ["unit", "equivalence"]},
    }
    apply_tier(rewrite_contract, "hard")
    lanes = set(rewrite_contract["tfactory"]["lanes"])
    check(
        "rewrite: hard contract retains equivalence lane + adds mutation",
        "equivalence" in lanes and "mutation" in lanes,
        f"got lanes={sorted(lanes)}",
    )

    return results, using_real


class _Stub:
    """Carries a tier value for the local tier_for shim."""

    def __init__(self, tier):
        self.tier = tier


class _RealStub:
    """Carries a real Tier enum for the real tier_for (which reads .tier)."""

    def __init__(self, tier_value, RealTier):
        if tier_value is None:
            self.tier = None
        elif RealTier is not None and not isinstance(tier_value, RealTier):
            try:
                self.tier = RealTier(_tier_value(tier_value))
            except Exception:  # noqa: BLE001
                self.tier = tier_value
        else:
            self.tier = tier_value


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    strict = "--selftest" in argv or "--strict" in argv

    results, using_real = run()

    print("RFC-0011 E2E tier-policy harness")
    print("  source modules:")
    for name, real in using_real.items():
        print(f"    - {name}: {'REAL (' + name + ')' if real else 'LOCAL SHIM (sibling repo not importable)'}")
    print()

    failed = [r for r in results if not r.ok]
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        line = f"  [{mark}] {r.name}"
        if not r.ok and r.detail:
            line += f"  — {r.detail}"
        print(line)

    print()
    print(f"  {len(results) - len(failed)}/{len(results)} checks passed.")
    print()
    print("  NOTE: this harness verifies the tier-policy MAPPING in-process.")
    print("  The live-fleet steps (poller pickup, idempotency, cross-tracker,")
    print("  merge gate) are documented in RFC-0011 §6/§10 and run against the")
    print("  demo repos once the poller + endpoints are deployed.")

    if failed and strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
