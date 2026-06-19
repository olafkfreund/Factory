"""Stage P — PFactory plans the Python->Rust migration (run in PFactory venv)."""

import json
import os
from pathlib import Path

from plan import service as svc_mod
from plan.detect import source_inspector as si
from plan.emit import task_contract as tc
from plan.emit.contract_emit import assemble_contract
from plan.recon.reconnoiter import build_repo_map

loop = Path(os.environ["LOOP"])
legacy = loop / "legacy"

rmap = build_repo_map(legacy, repo="acme/payments", base_ref="main", commit="aa11bb22")
svc_mod.reconnoiter = lambda repo, base_ref=None: rmap
svc_mod.inspect_source = lambda repo, base_ref, lang: si.build_behavioral_contract(legacy, lang)

svc = svc_mod.PlanService(persist=False)
spec = (
    "# Port payments to Rust\n\nRewrite the payments module from Python to Rust.\n\n"
    "## Acceptance Criteria\n- AC#1: The Rust refund behaves identically to Python\n"
    "- AC#2: fee() returns the same value\n"
)
s = svc.ingest_text(spec, title="Port payments", channel="cli", repo="acme/payments", base_ref="main")
out = svc.process(s.session_id)
contract = assemble_contract(out.plan, out.epic, repo="acme/payments")

# Concrete golden-corpus input vectors (authored here from the existing tests;
# the planner-side extraction of these from pytest cases is a tracked refinement).
contract["tfactory"]["equivalence"]["manifest"] = {
    "functions": [
        {"module": "pay/refund.py", "name": "refund"},
        {"module": "pay/refund.py", "name": "fee"},
    ],
    "input_vectors": [
        {"id": "refund-ok", "module": "pay/refund.py", "function": "refund", "args": [100, "x"], "critical": True},
        {"id": "refund-neg", "module": "pay/refund.py", "function": "refund", "args": [-5, "y"], "critical": True},
        {"id": "fee-100", "module": "pay/refund.py", "function": "fee", "args": [100], "critical": True},
        {"id": "fee-7", "module": "pay/refund.py", "function": "fee", "args": [7.5]},
    ],
}
(loop / "contract.json").write_text(json.dumps(contract, indent=2))
print("   change_mode:", contract.get("change_mode"), "| workflow:", contract["workflow_type"])
print("   module_map:", contract["tfactory"]["equivalence"]["module_map"])
print("   schema-valid:", tc.validate_contract(contract) == [])
