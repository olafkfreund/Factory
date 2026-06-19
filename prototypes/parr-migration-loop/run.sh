#!/usr/bin/env bash
# RFC-0010 end-to-end PARR migration loop (Python -> Rust), local + real.
#
# Proves the closed loop on real artifacts, without the deployed fleet:
#   P  PFactory   plans the migration            -> signed contract (real planner)
#   A  AIFactory  rewrite-mode workspace prep     -> oracle mounted + Rust crate
#                 + a faithful Rust impl built     -> real `cargo build`
#   T  TFactory   equivalence lane                -> Python oracle vs compiled Rust
#   C  reporting  RFC-0006 honest VAL block        -> a bad rewrite is never green
#
# Requires the four sibling repos checked out, their apps/backend/.venv built,
# and a Rust toolchain (cargo). Override the checkout root with FACTORY_ROOT.
#
#   ./run.sh           # faithful rewrite -> PASS, then a buggy one -> FAIL
set -euo pipefail

ROOT="${FACTORY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
PF="$ROOT/PFactory"; AF="$ROOT/AIFactory"; TF="$ROOT/TFactory"
PYPF="$PF/apps/backend/.venv/bin/python"
PYAF="$AF/apps/backend/.venv/bin/python"
PYTF="$TF/apps/backend/.venv/bin/python"
LOOP="$(mktemp -d /tmp/parr-loop.XXXX)"
export LOOP
echo "loop workspace: $LOOP"

# ---- the legacy Python "payments" module (migration source / oracle) ----
mkdir -p "$LOOP/legacy/pay" "$LOOP/legacy/tests"
: > "$LOOP/legacy/pay/__init__.py"
cat > "$LOOP/legacy/pay/refund.py" <<'PY'
def refund(amount, reason):
    if amount <= 0:
        raise ValueError("amount must be positive")
    return {"refunded": amount, "reason": reason}

def fee(amount):
    return round(amount * 0.029 + 0.30, 2)
PY
cat > "$LOOP/legacy/tests/test_refund.py" <<'PY'
from pay.refund import refund, fee
def test_refund(): assert refund(100, "x")["refunded"] == 100
def test_fee(): assert fee(100) == 3.20
PY

# ---- P: PFactory plans the migration -> contract.json --------------------
echo "== P: PFactory =="
PYTHONPATH="$PF/apps/backend" "$PYPF" "$(dirname "${BASH_SOURCE[0]}")/stage_p_plan.py"

# ---- A: AIFactory rewrite-mode workspace + real Rust build ---------------
echo "== A: AIFactory =="
PYTHONPATH="$AF/apps/backend" "$PYAF" "$(dirname "${BASH_SOURCE[0]}")/stage_a_prepare.py"
"$(dirname "${BASH_SOURCE[0]}")/stage_a_rust.sh" "$LOOP/worktree/rust/port"

# ---- T + C: TFactory equivalence verify + honest VAL reporting -----------
echo "== T+C: TFactory equivalence + RFC-0006 =="
PYTHONPATH="$TF/apps/backend" "$PYTF" "$(dirname "${BASH_SOURCE[0]}")/stage_t_verify.py"

echo "done. workspace kept at $LOOP"
