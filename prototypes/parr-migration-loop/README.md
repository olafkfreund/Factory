# PARR migration loop (RFC-0010) — local end-to-end

A real, closed-loop demonstration of a **Python → Rust migration** through the
PARR pipeline, run locally without the deployed fleet. Every stage uses the real
service code; the only stand-in is the LLM coder (the Rust rewrite is
hand-authored in `stage_a_rust.sh` so the run is deterministic).

```
P  PFactory   real planner          -> signed `migration` contract (equivalence block)
A  AIFactory  real migration_mapper  -> oracle mounted read-only + Rust crate scaffolded
              + faithful Rust impl    -> real `cargo build` of a `parity_harness`
T  TFactory   real equivalence lane  -> Python oracle vs the compiled Rust, over one
                                         golden corpus (the language-neutral harness protocol)
C  reporting  RFC-0006 VAL block      -> a divergent rewrite is capped to VAL-0, never green
```

## Run

Requires the four sibling repos checked out with their `apps/backend/.venv`
built, plus a Rust toolchain (`cargo`).

```bash
FACTORY_ROOT=/path/to/GitHub ./run.sh
```

Expected output: the faithful rewrite reaches **100% parity / VAL-2 PASS**; an
injected bug (wrong `fee()` rate) is caught at **50% parity / VAL-0 FAIL** with
the honest claim "1 CRITICAL vector diverged — NOT equivalent".

## Files

- `run.sh` — orchestrator (P → A → T+C)
- `stage_p_plan.py` — PFactory planning (PFactory venv)
- `stage_a_prepare.py` — AIFactory rewrite-mode workspace prep (AIFactory venv)
- `stage_a_rust.sh` — the coder stand-in: faithful Rust + `parity_harness` + `cargo build`
- `stage_t_verify.py` — TFactory equivalence verify + RFC-0006 reporting (TFactory venv)

## What this proves vs. what it doesn't

Proves the **contract → rewrite-mode workspace → compiled target → differential
equivalence → honest reporting** loop on real artifacts, including the
cross-service `parity_harness` protocol (AIFactory scaffolds it; TFactory drives
it). It does **not** exercise the live LLM coder, the in-cluster k8s-Job sandbox,
or GitHub/CFactory surfaces — those need the deployed fleet.
