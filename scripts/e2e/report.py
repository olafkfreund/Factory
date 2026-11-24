"""Campaign report over benchmark meta records with hidden-suite outcomes."""

import json
import statistics
from pathlib import Path

from scripts.benchmarks.report import load_file, to_run

GAPS = (
    "Surface and model are not crossed on one fixture",
    "P3 has no Gemini run",
    "P4 has no Codex run",
    "P5 runs Claude only",
    "Dropped-event probe deferred: no safe seam",
)


def summarize(records: list[dict]) -> dict:
    costs = [
        to_run(row).cost_usd
        for row in records
        if row.get("hidden_green") is True
        and to_run(row).passed
        and to_run(row).cost_usd is not None
        and row.get("billing_mode") != "subscription"
    ]
    return {
        "journeys": len(records),
        "median_cost_per_accepted_build_usd": statistics.median(costs) if costs else None,
        "results": [
            {
                key: row.get(key)
                for key in (
                    "instance_id",
                    "project",
                    "surface",
                    "model",
                    "status",
                    "stage_results",
                    "billing_mode",
                    "total_tokens",
                )
            }
            | {
                "cost_usd": None
                if row.get("billing_mode") == "subscription"
                else row.get("cost_usd")
            }
            for row in records
        ],
        "known_gaps": GAPS,
    }


def main(path: Path) -> str:
    files = (
        sorted(path.glob("*.meta.json")) + sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    )
    records = [row for file in files for row in load_file(file)]
    return json.dumps(summarize(records), indent=2)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("records", type=Path)
    print(main(parser.parse_args().records))  # noqa: T201
