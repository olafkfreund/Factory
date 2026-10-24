---
status: draft
issue: 813
spec: spec/2026-10-24-813-codeql-ratchet.md
---

# Plan: a CodeQL ratchet for the fleet

Approved decisions: a stdlib script counts open alerts in four buckets
(critical, high, error, medium; one bucket per alert, security severity first,
else rule severity), compares with `.github/codeql-baseline.json` in the caller,
prints the delta and exits 1 on any increase. A reusable workflow in Factory
runs it; each of PFactory, AIFactory, TFactory, CFactory gets a weekly caller
(pinned `@main`) and a baseline of today's counts. One PR per repo.

## Steps

1. scripts/codeql_ratchet.py: new; `count`, `compare`, `main`, `--self-test`
   → verify by `python3 scripts/codeql_ratchet.py --self-test`
   Traps: stdlib only; pass `--paginate` to gh api; never print tokens.
2. tests/test_codeql_ratchet.py: new; run the self-test and a few cases
   → verify by `pytest tests/test_codeql_ratchet.py`
   Traps: scripts/ is on sys.path via tests/conftest.py.
3. .github/workflows/codeql-ratchet.yml (Factory): new reusable workflow
   → verify by `python3 -c "import yaml;yaml.safe_load(open(...))"`
   Traps: workflow-level permissions as specified; pin actions by SHA as the
   other workflows do.
4. For each of PFactory, AIFactory, TFactory, CFactory (base dev):
   `.github/workflows/codeql-ratchet.yml` caller and `.github/codeql-baseline.json`
   → verify by running the script with `GH_TOKEN` against that repo and seeing exit 0
   Traps: baseline is the live count at PR time; caller PRs link to these files.

## Tests

`python3 scripts/codeql_ratchet.py --self-test` and `pytest tests/test_codeql_ratchet.py`: pass.

## Rollback

Revert the PRs; the workflows are additive and nothing depends on them.
