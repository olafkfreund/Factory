"""Stage A — AIFactory rewrite-mode workspace prep (run in AIFactory venv)."""

import json
import os
from pathlib import Path

from core import migration_mapper as mm

loop = Path(os.environ["LOOP"])
legacy = loop / "legacy"
wt = loop / "worktree"
wt.mkdir(parents=True, exist_ok=True)

contract = json.loads((loop / "contract.json").read_text())
summary = mm.prepare_migration_workspace(wt, legacy, contract)
print("   target_language:", summary["target_language"])
print("   oracle mounted :", (wt / ".aifactory/oracle/pay/refund.py").is_file())
print("   scaffolded     :", [p.split("worktree/")[-1] for p in summary["scaffolded"]])
