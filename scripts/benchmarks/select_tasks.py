#!/usr/bin/env python3
"""Deterministically select a 50-task stratified subset of SWE-bench Verified.

Stratification:
  1. repo  -- proportional (largest-remainder) over repos with >= 10 instances
              in the full 500; repos below that threshold are excluded (they
              are 11/500 = 2.2% of the dataset).
  2. difficulty -- within each repo, proportional over the dataset's own
              `difficulty` annotation (OpenAI annotation effort).

Pure stdlib. Data is fetched from the HF datasets-server rows API (public,
no token) and cached locally as swebench_verified_rows.json.

Reproduce:  python3 select_tasks.py
"""
import json
import random
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

DATASET = "princeton-nlp/SWE-bench_Verified"
API = ("https://datasets-server.huggingface.co/rows"
       "?dataset=princeton-nlp%2FSWE-bench_Verified&config=default&split=test")
HERE = Path(__file__).parent
CACHE = HERE / "swebench_verified_rows.json"
SEED = 42
TARGET = 50
MIN_REPO_INSTANCES = 10
KEEP = ("instance_id", "repo", "base_commit", "created_at", "difficulty")


def fetch_rows():
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    rows = []
    for offset in range(0, 500, 100):
        with urllib.request.urlopen(f"{API}&offset={offset}&length=100") as r:
            page = json.load(r)
        for item in page["rows"]:
            row = {k: item["row"][k] for k in KEEP}
            row["problem_statement_chars"] = len(item["row"]["problem_statement"])
            rows.append(row)
    assert len(rows) == 500, f"expected 500 rows, got {len(rows)}"
    CACHE.write_text(json.dumps(rows, indent=1))
    return rows


def apportion(counts, total):
    """Largest-remainder apportionment of `total` slots over {key: count}."""
    pop = sum(counts.values())
    quotas = {k: total * c / pop for k, c in counts.items()}
    alloc = {k: int(q) for k, q in quotas.items()}
    leftover = total - sum(alloc.values())
    # deterministic tie-break: remainder desc, then key
    for k in sorted(counts, key=lambda k: (-(quotas[k] - alloc[k]), k))[:leftover]:
        alloc[k] += 1
    # cap at available instances (redistribute is not needed at our sizes,
    # but assert so we notice if it ever is)
    assert all(alloc[k] <= counts[k] for k in alloc)
    return alloc


def main():
    rows = fetch_rows()
    repo_counts = Counter(r["repo"] for r in rows)
    eligible = {k: v for k, v in repo_counts.items() if v >= MIN_REPO_INSTANCES}
    repo_alloc = apportion(eligible, TARGET)

    rng = random.Random(SEED)
    by_repo = defaultdict(list)
    for r in rows:
        if r["repo"] in eligible:
            by_repo[r["repo"]].append(r)

    selected = []
    for repo in sorted(repo_alloc):
        pool = sorted(by_repo[repo], key=lambda r: r["instance_id"])
        diff_counts = Counter(r["difficulty"] for r in pool)
        diff_alloc = apportion(diff_counts, repo_alloc[repo])
        for diff in sorted(diff_alloc):
            cell = [r for r in pool if r["difficulty"] == diff]
            selected.extend(rng.sample(cell, diff_alloc[diff]))

    selected.sort(key=lambda r: r["instance_id"])

    # sanity checks
    ids = [r["instance_id"] for r in selected]
    assert len(ids) == TARGET and len(set(ids)) == TARGET, "need 50 unique ids"
    source_ids = {r["instance_id"] for r in rows}
    assert set(ids) <= source_ids, "selected id not in source dataset"

    out = [{"instance_id": r["instance_id"], "repo": r["repo"],
            "base_commit": r["base_commit"],
            "problem_statement_chars": r["problem_statement_chars"],
            "difficulty": r["difficulty"], "created_at": r["created_at"]}
           for r in selected]
    (HERE / "swebench-verified-50.json").write_text(json.dumps(out, indent=2) + "\n")

    # distribution tables
    full_diff = Counter(r["difficulty"] for r in rows)
    sel_diff = Counter(r["difficulty"] for r in selected)
    sel_repo = Counter(r["repo"] for r in selected)

    def table(title, full, sel, full_total, sel_total):
        lines = [f"### {title}", "",
                 f"| {title} | full ({full_total}) | full % | selected ({sel_total}) | selected % |",
                 "|---|---|---|---|---|"]
        for k in sorted(full, key=lambda k: -full[k]):
            lines.append(f"| {k} | {full[k]} | {100*full[k]/full_total:.1f}% "
                         f"| {sel.get(k, 0)} | {100*sel.get(k, 0)/sel_total:.1f}% |")
        return "\n".join(lines)

    repo_table = table("repo", repo_counts, sel_repo, 500, TARGET)
    diff_table = table("difficulty", full_diff, sel_diff, 500, TARGET)
    print(repo_table, "\n\n", diff_table, sep="")

    report = ["# SWE-bench Verified 50-task subset -- selection report", "",
              f"Source: `{DATASET}` (test split, 500 instances, via HF datasets-server rows API).",
              f"Selection: seed {SEED}, stratified by repo (proportional largest-remainder over "
              f"repos with >= {MIN_REPO_INSTANCES} instances; smaller repos, "
              f"{500 - sum(eligible.values())}/500 instances, excluded) then by the dataset's "
              "`difficulty` annotation within each repo.", "",
              "Reproduce:", "", "```", "python3 select_tasks.py", "```", "",
              "## Stratification vs. full dataset", "",
              repo_table, "", diff_table, "",
              "## Selected instances", "",
              "| instance_id | repo | difficulty |", "|---|---|---|"]
    report += [f"| {r['instance_id']} | {r['repo']} | {r['difficulty']} |" for r in selected]
    (HERE / "selection_report.md").write_text("\n".join(report) + "\n")
    print(f"\nWrote swebench-verified-50.json ({TARGET} tasks) and selection_report.md")


if __name__ == "__main__":
    main()
