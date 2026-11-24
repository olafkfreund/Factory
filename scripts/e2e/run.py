"""Offline-first entry point for the minimum viable campaign slice."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.e2e.config import HOSTS
from scripts.e2e.evidence import safe_fields
from scripts.e2e.journey import STAGES, Journey
from scripts.e2e.report import summarize


def selected(journeys: list[str], slice_name: str | None) -> list[Journey]:
    if slice_name == "mvr":
        return [
            *(
                Journey("P1", surface, "Claude", repeat)
                for surface in ("cli", "mcp")
                for repeat in (1, 2)
            ),
            Journey("P5", "cli", "Claude", 1),
        ]
    result = []
    for item in journeys:
        parts = item.split(":")
        if (
            len(parts) != len(("project", "surface", "repeat"))
            or parts[0] not in {"P1", "P5"}
            or parts[1] not in {"cli", "mcp"}
        ):
            raise ValueError("journey must be P1|P5:cli|mcp:repeat")
        repeat = int(parts[2])
        if repeat < 1:
            raise ValueError("repeat must be positive")
        result.append(Journey(parts[0], parts[1], "Claude", repeat))
    return result


def planned_calls(journey: Journey) -> list[str]:
    descriptions = {
        "S1": "guarded GitHub repo create, starter push, three project onboardings",
        "S2": "guarded factory submit of fixture triple",
        "S3": "poll AIF task and usage with budget stop",
        "S4": "read GitHub PR, checks and merge",
        "S5": "guarded factory test at merge SHA, then local hidden suite",
        "X": "read CFactory card timeline",
    }
    return [
        f"{journey.project} {journey.surface} #{journey.repeat}: {stage} {descriptions[stage]}"
        for stage in STAGES
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--journey", action="append", default=[])
    choice.add_argument("--slice", choices=["mvr"])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--campaign", default=datetime.now(UTC).strftime("e2e-campaign-%Y-%m-%d"))
    parser.add_argument("--evidence-root", type=Path, default=Path("evidence"))
    args = parser.parse_args(argv)
    try:
        runs = selected(args.journey, args.slice)
    except ValueError as exc:
        parser.error(str(exc))
    if args.live:
        # No task may start until the API can prove ownership for every created
        # resource and the server's stop and cleanup routes are confirmed.
        raise NotImplementedError(
            "live campaign blocked: project/card ownership and cleanup routes are not confirmed"
        )
    rows: list[dict[str, Any]] = []
    for run in runs:
        for call in planned_calls(run):
            print(call)  # noqa: T201
        rows.append(
            safe_fields(
                {
                    "project": run.project,
                    "surface": run.surface,
                    "model": run.model,
                    "repeat": run.repeat,
                    "status": "planned",
                },
                {"project", "surface", "model", "repeat", "status"},
            )
        )
    path = args.evidence_root / args.campaign / "run.meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"journeys": rows, "hosts": HOSTS}, sort_keys=True) + "\n")
    print(json.dumps(summarize(rows), indent=2))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
