"""Stage T+C — TFactory equivalence verify + RFC-0006 reporting (TFactory venv).

Runs the equivalence lane (Python oracle vs the compiled Rust parity_harness)
on the faithful build, then injects a bug, rebuilds, and re-verifies — showing
the loop catches divergence and reports it honestly (a bad rewrite is never
green).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from agents import equivalence_lane as el
from agents.val_block import build_verification_block

loop = Path(os.environ["LOOP"])
legacy = loop / "legacy"
crate = loop / "worktree" / "rust" / "port"
contract = json.loads((loop / "contract.json").read_text())
binary = crate / "target" / "debug" / "parity_harness"


def oracle_runner(_harness, root, stdin):
    (Path(root) / "vectors.json").write_text(stdin)
    (Path(root) / "h.py").write_text(el.generate_python_oracle_harness())
    r = subprocess.run(
        [sys.executable, "h.py", "vectors.json"], cwd=root, capture_output=True, text=True
    )
    return type("R", (), {"stdout": r.stdout})()


def candidate_runner(_harness, _root, stdin):
    vf = crate / "vectors.json"
    vf.write_text(stdin)
    r = subprocess.run([str(binary), str(vf)], cwd=crate, capture_output=True, text=True)
    return type("R", (), {"stdout": r.stdout})()


def verify(label: str, spec_name: str) -> dict:
    spec = loop / spec_name
    spec.mkdir(exist_ok=True)
    res = el.run_from_spec(
        spec, loop / "worktree", contract,
        oracle_runner=oracle_runner, candidate_runner=candidate_runner,
    )
    verdicts = json.loads((spec / "findings" / "verdicts.json").read_text())["verdicts"]
    block = build_verification_block(verdicts)
    print(f"   [{label}] parity={res['parity_ratio']:.0%} passed={res['passed']}")
    print(f"           claim: {res['claim']}")
    print(f"           VAL target={block['target_level']} achieved={block['achieved_level']}")
    return res


verify("faithful", "tf_spec_faithful")

# inject a real bug into the Rust fee() rate, rebuild, re-verify
src = crate / "src" / "pay" / "refund.rs"
src.write_text(src.read_text().replace("0.029", "0.039"))
subprocess.run(["cargo", "build", "--quiet", "--bins"], cwd=crate, check=True)
verify("buggy", "tf_spec_buggy")
