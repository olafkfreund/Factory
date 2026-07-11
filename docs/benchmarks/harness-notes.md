# SWE-bench Official Harness — Local Run Notes

Date: 2026-07-11. Host: NixOS dev box, x86_64, 128 CPUs, 251 GiB RAM.

## Versions

- swebench: 4.1.0 (PyPI, `pip install swebench`)
- Python: 3.14.6 (host venv at `bench-harness/venv`)
- Docker: 29.6.1 (daemon running, overlayfs). Podman 5.8.4 also present but NOT needed — real docker daemon works, so no podman socket shim was required.

## NixOS gotcha (the only setup wrinkle)

numpy's manylinux wheel needs `libstdc++.so.6`, which is not on the default
library path on NixOS. Fix, before any `swebench` invocation:

```
export LD_LIBRARY_PATH=/nix/store/8lahnh9pn3lrrnhax5nk7ibvjcbjmnkm-gcc-15.2.0-lib/lib
```

(Portable form: `export LD_LIBRARY_PATH=$(dirname $(gcc -print-file-name=libstdc++.so.6))`.)

## Smoke test (gold-patch sanity)

- Dataset: `SWE-bench/SWE-bench_Verified` (500 instances, HF download ~seconds)
- Instance: `sympy__sympy-22914` (smallest sympy gold patch in Verified, 277 bytes)
- Predictions: `predictions.jsonl` with `model_patch` = the gold patch, `model_name_or_path` = `gold-sanity`
- Command:

```
python -m swebench.harness.run_evaluation \
  -d SWE-bench/SWE-bench_Verified -p predictions.jsonl \
  -i sympy__sympy-22914 -id gold-smoke --max_workers 1
```

- Result: **PASSED — resolved 1/1** (`completed 1, resolved 1, unresolved 0, errors 0`),
  eval wall time 79.6 s (after image pull)
- Report: `gold-sanity.gold-smoke.json` (resolved_ids = ["sympy__sympy-22914"])

## Footprint observed

- Per-instance eval image: 3.77 GB (prebuilt `swebench/sweb.eval.x86_64.sympy_1776_sympy-22914`,
  pulled from Docker Hub in ~1 min). With the default `--cache_level env` the
  instance image is deleted after the run, so disk use is transient — budget
  ~4 GB per concurrent worker plus env images (a few GB each, shared per repo).
- RAM: negligible (single worker; box barely moved off 24 GiB used).
- venv: 421 MB. Logs: KBs per instance.
- One instance end-to-end (pull + run + report): ~3 min.
- The x86_64 prebuilt image pulled fine — `--namespace none` (local build)
  was never needed.

## Gotchas

- Harness default namespace is `swebench` — it pulls prebuilt per-instance
  eval images from Docker Hub (`swebench/sweb.eval.x86_64.<id>`). Use
  `--namespace none` to force local base/env/instance image builds if a pull
  fails or the arch image doesn't exist.
- The report JSON lands in the CWD as `{model_name_or_path}.{run_id}.json`;
  per-instance logs under `logs/run_evaluation/{run_id}/`.
- `--cache_level env` (default) keeps env images between runs; per-instance
  images are removed after each instance. For a 50-task batch on this box,
  `--cache_level instance` avoids re-pull churn at the cost of disk
  (~3-4 GB/instance observed). Root disk is 98% full (21 GB free) — keep
  cache_level at `env` (default) or point docker's data-root elsewhere
  before a 50-task batch; at `env` a 50-task run only needs ~4 GB per
  concurrent worker transiently.
- Predictions jsonl needs exactly: `instance_id`, `model_name_or_path`,
  `model_patch` (unified diff).

## Wrapper

`evaluate.py` — thin argv shim over the official
`swebench.harness.run_evaluation`; pins Verified as default dataset, accepts
an instance-ids JSON file (list of ids or of objects with `instance_id`),
prints the report path. No scoring logic of our own.
