---
name: run-aws-demo
description: Set up and run the PARR deploy-then-verify demo on REAL AWS — scaffolds 2 FastAPI services, deploys them to AWS App Runner via deterministic Terraform, proves the live API, runs the acceptance tests against the live endpoints, then tears everything down (cost-guarded). Optionally records an asciinema screencast. Use when the user types /run-aws-demo or asks to (re)run the AWS deploy-then-verify demo / factory App Runner demo / "the aws demo".
---

# /run-aws-demo — deploy-then-verify on real AWS

Reproduces the demo proven on 2026-06-11: a unit of work goes from a CLI to a
live, tested API on **real AWS App Runner**, then is **torn down**. One command.

## What it does (the steps, automated by `conductor.sh`)
1. Verify prereqs + AWS identity.
2. Scaffold 2 FastAPI services (tic-tac-toe `frontend`, auth'd `scoreboard`) + 5 AC tests.
3. Generate **deterministic** App Runner Terraform (every resource tagged
   `factory-ephemeral`/`spec_id`; ECR `force_delete`).
4. Create ECR repos + IAM role.
5. Build + push both images to ECR.
6. `terraform apply` → 2 live App Runner HTTPS endpoints.
7. Prove the live API (curl: `win:X`, `401` auth).
8. Run the AC tests against the **live** endpoints (TFactory-style, via
   `TFACTORY_TARGET_URL`).
9. **Teardown** (`terraform destroy`) — runs even on failure (EXIT trap);
   confirms App Runner is empty and existing infra is untouched.

## Prerequisites (the runbook MUST check first)
- Tools: `terraform`, `docker` (daemon up), `aws` CLI, `python3` (with `pytest`+`httpx`), `curl`.
- AWS creds file (default `/home/olafkfreund/Source/Calitti/Synechron_ARC/sarc/.envrc`,
  with `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`). Override with `ENVRC=...`.
- Real AWS spend (a few cents; App Runner is pay-per-use and torn down immediately).

## How to run it (what Claude should do for /run-aws-demo)
1. **Confirm scope** with the user (this provisions REAL AWS, then destroys it). If they're ready, proceed.
2. `pip install -q pytest httpx` if not present.
3. Run the conductor (the script lives next to this SKILL.md):
   ```bash
   bash ~/.claude/skills/run-aws-demo/conductor.sh
   ```
   Use a long timeout (~10 min — App Runner provisioning is the slow part).
4. **To record a screencast** (the user asked for a "console-cli" recording before):
   ```bash
   asciinema rec --overwrite -c "bash ~/.claude/skills/run-aws-demo/conductor.sh" /tmp/run-aws-demo.cast
   # then (headless casts play near-instant — re-time + convert to GIF):
   #   re-time the .cast (spread timestamps ~1.1s/event, hold banners), then:
   nix run nixpkgs#asciinema-agg -- /tmp/run-aws-demo-timed.cast /tmp/run-aws-demo.gif
   ```
   Deliver the GIF with SendUserFile. (agg isn't installed by default; `nix run nixpkgs#asciinema-agg` fetches it.)
5. **Report**: live URLs, the curl results, the pytest verdict (`5 passed`), and the teardown confirmation.

## Options
- `bash conductor.sh --keep` — leave the services running (skip teardown). Remind the user to destroy later: `terraform -chdir=/tmp/run-aws-demo/infra destroy -auto-approve`.
- `ENVRC=/path REGION=eu-west-1 SPEC=mydemo bash conductor.sh` — override creds/region/name.

## Cost guard (teardown is the #1 invariant)
- The EXIT trap always runs `terraform destroy` (even on failure or Ctrl-C).
- Every resource is tagged `factory-ephemeral=true` + `spec_id=<spec>` and named
  `factory-<spec>-*`, so teardown (and any sweeper) can NEVER touch non-Factory infra.
- After a run, verify nothing leaked:
  ```bash
  aws apprunner list-services --region <region> --query "ServiceSummaryList[?contains(ServiceName,'factory-')].ServiceName" --output json   # → []
  aws ecr describe-repositories --region <region> --query "repositories[?contains(repositoryName,'factory-')].repositoryName" --output json # → []
  ```

## The autonomous (GitHub Actions) variant — also proven
The same deterministic templates run in CI: push the app + generated
`.github/workflows/{deploy,destroy}.yml` + `infra/` to a repo with `on: push`
matching the branch, set AWS keys as repo secrets (`gh secret set`), and the
**push auto-triggers** the deploy to App Runner. Needs an **S3 backend**
(`factory-tfstate-<account>` bucket) so deploy + destroy share state across
runners. GOTCHA: `destroy.yml` via `gh workflow run` 404s unless it's on the
repo's **default branch** — so the durable teardown is the tagged sweeper +
direct `terraform destroy` on the S3 state, not dispatch. (See the AIFactory
`deploy_templates.py` / `deploy_endgame.py` for the productionized version.)

## Provenance
Built + proven this in-session: deterministic templates (`deploy_templates.py`,
13 tests), real deploy+teardown on acct 533267307120 / eu-west-2 (twice: local
terraform + GitHub Actions), screencast published at
factory.freundcloud.com/blog/2026/06/11/deploy-then-verify-on-real-aws/.
