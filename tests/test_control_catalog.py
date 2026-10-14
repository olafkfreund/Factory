"""Keep the control catalog aligned with the framework mapping matrix."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_control_catalog_matches_matrix() -> None:
    catalog = json.loads((ROOT / "apis/control-catalog.json").read_text(encoding="utf-8"))
    matrix = (ROOT / "docs/compliance/control-matrix.md").read_text(encoding="utf-8")
    table = matrix.split("## Framework mapping\n", 1)[1].split("\n## ", 1)[0]
    rows = [
        (int(match.group(2)), match.group(1))
        for line in table.splitlines()
        if (match := re.fullmatch(r"\| (.+) \(#(\d+)\) \|.*", line))
    ]
    controls = catalog["controls"]
    ids = [control["id"] for control in controls]

    assert len(rows) == 14
    assert {control["issue"] for control in controls} == {issue for issue, _ in rows}
    assert [(control["issue"], control["domain"]) for control in controls] == rows
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", control_id) for control_id in ids)
    assert type(catalog["version"]) is int and catalog["version"] > 0
