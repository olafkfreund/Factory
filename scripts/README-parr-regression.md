# PARR nightly regression (Factory#41)

A cross-service **seam gate** for the deployed PARR fleet. The June 2026 review
found that nearly every production bug lived at a *factory boundary* — Cloudflare
blocking a client, a contract rejected by payload shape, an endpoint that drifted
between releases, a completion event that never fired. Per-repo unit tests can't
see these. This catches them with a gate instead of a user.

## What it asserts

`scripts/parr_regression.py` drives the deployed fleet and checks, in order:

1. **Reachability + auth** — every factory answers on its API behind Cloudflare
   with the bearer token (catches the UA-block / auth / DNS regressions).
2. **PFactory ingest shape** — `/api/plan/sessions/ingest-text` accepts the
   documented contract (catches the plan-leg payload drift).
3. **TFactory ingest contract** — `/api/specs/ingest` validates the current
   `{project_id, spec_id, spec_text}` schema (catches the endpoint drift that
   silently routed to the old API).
4. **CFactory cockpit API** — work items / events endpoints answer (the
   observability seam).

`--full` additionally drives a real create-and-run build through AIFactory to a
terminal state (the end-to-end build seam; tens of minutes).

## Running it

```bash
# Fast seam check (~30s) against the deployed fleet:
FACTORY_TOKEN=<deployed-fleet-token> python3 scripts/parr_regression.py

# Wiring check, no calls:
python3 scripts/parr_regression.py --dry-run

# Full end-to-end (slow):
FACTORY_TOKEN=<token> python3 scripts/parr_regression.py --full
```

Endpoints default to the deployed `*.freundcloud.org.uk` services; override with
`PFACTORY_API` / `AIFACTORY_API` / `TFACTORY_API` / `CFACTORY_API`. Per-service
tokens (`AIFACTORY_TOKEN` …) override the shared `FACTORY_TOKEN`.

Exit code is non-zero and names the failed seam when a boundary regresses.

## CI

`.github/workflows/parr-nightly.yml` runs the fast check nightly (03:00 UTC) and
on demand (`workflow_dispatch`, with a `full` toggle). On failure it opens or
refreshes a `parr-regression`-labelled tracking issue with the output.

**Operator setup (one-time):** add the deployed fleet token as the repo secret
**`FACTORY_TOKEN`**. Without it the job skips cleanly (so forks don't fail). The
nightly cron only runs on the default branch once this lands there. Optionally
set repo **variables** `PFACTORY_API` / `AIFACTORY_API` / `TFACTORY_API` /
`CFACTORY_API` if the fleet moves off the default hostnames.
