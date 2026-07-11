#!/usr/bin/env python3
"""Thin wrapper around the OFFICIAL SWE-bench evaluation harness.

We never self-score: this just shells out to
`python -m swebench.harness.run_evaluation` with our pinned defaults and
prints where the report landed.

Usage:
  python evaluate.py -p predictions.jsonl -id my-run \
      [-d SWE-bench/SWE-bench_Verified] [--instance-ids-file tasks.json] \
      [--max-workers 4] [--timeout 1800] [--namespace swebench]

instance-ids-file: JSON file that is either a list of instance_id strings or
a list of objects with an "instance_id" key (our 50-task file works as-is).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_instance_ids(path):
    data = json.loads(Path(path).read_text())
    return [x if isinstance(x, str) else x["instance_id"] for x in data]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-p", "--predictions", required=True, help="predictions.jsonl path")
    ap.add_argument("-id", "--run-id", required=True)
    ap.add_argument("-d", "--dataset", default="SWE-bench/SWE-bench_Verified")
    ap.add_argument("--instance-ids-file", help="JSON file limiting which instances to score")
    ap.add_argument("--max-workers", default="4")
    ap.add_argument("--timeout", default="1800")
    ap.add_argument("--namespace", default="swebench",
                    help='image namespace; use "none" to force local builds')
    args = ap.parse_args()

    cmd = [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", args.dataset,
        "--predictions_path", args.predictions,
        "--run_id", args.run_id,
        "--max_workers", args.max_workers,
        "--timeout", args.timeout,
        "--namespace", args.namespace,
    ]
    if args.instance_ids_file:
        cmd += ["--instance_ids", *load_instance_ids(args.instance_ids_file)]

    print("+", " ".join(cmd), flush=True)
    rc = subprocess.run(cmd).returncode
    if rc:
        sys.exit(rc)

    # Harness writes {model_name_or_path}.{run_id}.json into the CWD.
    with open(args.predictions) as f:
        model = json.loads(f.readline())["model_name_or_path"]
    report = Path(f"{model.replace('/', '__')}.{args.run_id}.json")
    print(f"\nReport: {report.resolve() if report.exists() else report} "
          f"({'found' if report.exists() else 'NOT FOUND - check logs/run_evaluation/' + args.run_id})")


if __name__ == "__main__":
    main()
