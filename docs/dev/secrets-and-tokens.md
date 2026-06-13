---
layout: default
title: Secrets and Tokens
permalink: /dev/secrets-and-tokens/
---

# Secrets and Tokens — what they are, where to get them, how to wire them up

This is the operator runbook for every credential the Factory program uses across
its five repositories (Factory + AIFactory + PFactory + TFactory + CFactory) and
the deployed fleet. It explains, for each token: **what it is**, **where the value
comes from**, **how to set it**, and **how to rotate or react if it leaks**.

> One-command setup: `scripts/wire-tokens.sh` (in this repo) sets the CI tokens
> across all repos consistently. Read this page first so you know which values to
> hand it.

---

## Current state (audit snapshot, 2026-06-13)

| Secret | Repo(s) | Set today | What it does |
|---|---|---|---|
| `GITHUB_TOKEN` | all | **auto** (no action) | per-run token GitHub Actions injects |
| `GHCR_PAT` | AIF, PF, TF, CF | **set** | push container images to GHCR |
| `GITOPS_PAT` | AIF, PF, TF, CF | **set** | commit image-tag bumps to `factory-gitops` (ArgoCD then syncs) |
| `FACTORY_TOKEN` | Factory (nightly) | **MISSING** | fleet bearer token the PARR seam-regression uses to call the live services |
| `AIFACTORY_TOKEN` | AIFactory | **MISSING** | bearer token the `aifactory:run` dispatch + copilot review use to call the AIFactory API |
| `PFACTORY_TOKEN` | PFactory | **MISSING** | same, for PFactory |
| `TFACTORY_TOKEN` | TFactory | **MISSING** | same, for TFactory |
| `AIFACTORY_URL` | AIFactory | **MISSING** | AIFactory base URL; when unset, copilot review falls back to a local run |
| `PFACTORY_URL` | PFactory | **MISSING** | PFactory base URL (analogous) |
| `*_API` (repo **variables**) | seam-gate | optional | override the probe target (e.g. a disposable project) — see "Seam-gate" below |

**Why the missing ones aren't set automatically:** their values are real
credentials. A bot cannot (and should not) fabricate or copy a production token
into CI. Worse, several are *interlocked*: setting `AIFACTORY_URL` without
`AIFACTORY_TOKEN` would route copilot review at the live API and fail auth,
breaking the working local fallback. So set each token **together with its URL**,
using `scripts/wire-tokens.sh`.

---

## The two PATs that are already set (`GHCR_PAT`, `GITOPS_PAT`)

These are GitHub **Personal Access Tokens** (or fine-grained tokens). They already
work; documented here for rotation.

- **`GHCR_PAT`** — scope: `write:packages` (+ `read:packages`). Used by each
  `deploy.yml` to `docker login ghcr.io` and push the service image.
- **`GITOPS_PAT`** — scope: `repo` / fine-grained **Contents: write** on
  `olafkfreund/factory-gitops`. Used to push the image-tag bump that ArgoCD syncs.
  > Security note: this PAT can push to the shared gitops repo from any of the four
  > service runners, so a single compromised runner reaches the whole cluster. Prefer
  > a fine-grained token scoped to *only* `factory-gitops`, short expiry, and add an
  > `environment:` protection gate on the deploy job.

**Create/rotate:** GitHub → Settings → Developer settings → Personal access tokens
→ generate with the scope above → `gh secret set GHCR_PAT --repo olafkfreund/<repo>`.

---

## `FACTORY_TOKEN` and the per-service `*_TOKEN`s — the fleet API tokens

### What they are
`scripts/parr_regression.py` and the dispatch/review workflows call the **deployed**
services at `https://{pfactory,aifactory,tfactory,cfactory}.freundcloud.org.uk`
and send `Authorization: Bearer <token>`. Each picks `{SVC}_TOKEN` if present, else
falls back to `FACTORY_TOKEN`. So all of these are **the same kind of value**: a
bearer token the live factory APIs accept.

A valid value is one of:
1. The services' **`APP_API_TOKEN`** — the host-wide service principal each factory
   runs with. **Works, but broad** — it's an admin-equivalent wildcard shared across
   siblings (see AIFactory#318 / the audit), so spreading it into CI widens the blast
   radius. Use only if you can't mint a scoped key.
2. **A scoped `acw_` API key** (recommended) — least-privilege, revocable.

### Where to find the `APP_API_TOKEN` value
It is wired into each app via `factory-gitops/apps/<svc>/manifests/manifests.yaml`,
pulled from a Kubernetes Secret. Get the live value from whatever backs those
manifests:
```bash
# from the cluster (replace namespace/secret name as deployed):
kubectl -n <namespace> get secret <svc>-secrets \
  -o jsonpath='{.data.APP_API_TOKEN}' | base64 -d
```
…or from your secret source (agenix / SOPS / sealed-secrets), or the value you set
at deploy time.

### Recommended: mint a scoped `acw_` key instead
1. Open a running factory's portal (or call its API) as an admin.
2. Create an API key (`acw_…`) with **write** scope to the ingest endpoints the
   smoke probes hit (see caveat below) — read-only is *not* enough.
3. Use that single key as `FACTORY_TOKEN` (it is accepted by all four services if
   they share an auth backend; otherwise mint one per service and set each
   `{SVC}_TOKEN`).
4. Record the key id so you can revoke it later.

### ⚠️ Before you enable the seam-gate against production
`parr_regression.py --smoke` is **not purely read-only** — it POSTs probe artifacts:
- `pfactory POST /api/plan/sessions/ingest-text` (creates a probe plan session)
- `tfactory POST /api/specs/ingest` (shape/validation probe)

So the token needs **write** scope. The probes now **clean up after themselves**
(best-effort): the AIFactory `--full` task is DELETEd and the PFactory probe session
is rejected/closed (PFactory has no plan-session DELETE). Cleanup never fails the
gate; set `PARR_NO_TEARDOWN=1` to keep artifacts when debugging. Note the PFactory
session is *closed*, not hard-deleted, so it still persists in the DB — so for a
fully clean prod you may still prefer a disposable target. Before activating:
- point the gate at a **disposable project** by setting the `*_API` repo *variables*
  (below), **and/or**
- add a teardown step to `parr_regression.py`.

Until `FACTORY_TOKEN` is set, the `seam-check` job and the nightly **self-skip** —
they are safe no-ops, never touching the fleet.

---

## The Seam-gate (`seam-check` jobs + nightly) — how it's wired

- Each service `deploy.yml` has a `seam-check` job (`needs:` the deploy job,
  `continue-on-error: true`) that checks out this repo and runs
  `python scripts/parr_regression.py --smoke`. It is a **soft gate**: a probe failure
  can never break or roll back the deploy.
- The nightly (`.github/workflows/parr-nightly.yml`) runs the same harness on a cron.
- **Inputs it reads:**
  - secret `FACTORY_TOKEN` (or per-service `{SVC}_TOKEN`) — required to do anything;
    unset ⇒ skip.
  - variables `PFACTORY_API` / `AIFACTORY_API` / `TFACTORY_API` / `CFACTORY_API` —
    optional; override the target URL per service. Unset ⇒ the script's defaults
    (the prod fleet). Set these to a disposable environment to avoid probing prod:
    ```bash
    gh variable set PFACTORY_API --repo olafkfreund/<repo> --body "https://pfactory.staging.example"
    ```

---

## Runtime service secrets (not CI — they live in the cluster)

These are set in the deployment env (k8s Secrets in `factory-gitops`), **not** in
GitHub Actions. Listed so you know they exist and where to rotate them:

| Secret | Service | Purpose |
|---|---|---|
| `APP_API_TOKEN` | all | host-wide service principal (see above) |
| `AIFACTORY_TRUSTED_PLAN_KEY_<authority>` | AIFactory ⇄ PFactory | HMAC key that signs/verifies the trusted-plan contract (RFC-0002) |
| `PFACTORY_MCP_SECRET` | PFactory | bearer for the `/mcp` endpoint (fails closed when unset, post-#128) |
| `CFACTORY_AUDIT_HMAC_SECRET` | CFactory | tamper-evidence for the audit chain (must not be the dev default in prod) |
| `JWT_SECRET`, OIDC client id/secret | all portals | session + SSO |
| `CLAUDE_CODE_OAUTH_TOKEN` | AIFactory/PFactory/TFactory | **LLM auth for the `claude` CLI.** Planning is pinned to Claude (`phase_config.DEFAULT_PHASE_MODELS` → `sonnet`), so when this expires **every build fails** at planning with a 0-token stub plan — see the refresh procedure below. |
| `GEMINI_API_KEY` | AIFactory | LLM auth for the `gemini`/`antigravity` CLI (Gemini-provider builds) |

All three factories share one `factory-secrets` k8s Secret in namespace `factory`.
Rotate these in `factory-gitops` (or directly on the cluster Secret) and restart the
pods; they are not touched by `wire-tokens.sh`.

### Refreshing the Claude / Gemini provider credentials

`CLAUDE_CODE_OAUTH_TOKEN` is a `claude setup-token` OAuth token (`sk-a…`, ~108 chars)
and **expires**. When it lapses, the `claude` CLI returns `401 Invalid authentication
credentials`; because planning is Claude-pinned, the symptom is that *all* AIFactory
builds finish in ~30s having produced `implementation_plan.json = {"phase":
"spec_creation"}` and the log line `Invalid or minimal implementation plan detected`.

Refresh it (operator-only — a bot cannot mint an OAuth token):

```bash
# 1. On a trusted machine, generate a fresh token (interactive browser login):
claude setup-token          # prints the new sk-a... token

# 2. Put it in a file (no trailing newline issues — the patch below strips it):
printf '%s' '<paste-token>' > /tmp/token.txt

# 3. Patch the live Secret WITHOUT echoing the value (stringData → k8s base64-encodes):
python3 -c 'import json;print(json.dumps({"stringData":{"CLAUDE_CODE_OAUTH_TOKEN":open("/tmp/token.txt").read().strip()}}))' > /tmp/p.json
kubectl patch secret factory-secrets -n factory --type merge --patch-file /tmp/p.json
rm -f /tmp/p.json /tmp/token.txt

# 4. Restart the factories so the new env is picked up:
kubectl rollout restart deploy/aifactory deploy/pfactory deploy/tfactory -n factory

# 5. Verify (must print PONG, no 401):
kubectl exec -n factory deploy/aifactory -- claude -p 'reply with exactly: PONG' --model claude-sonnet-4-6
```

Gemini: the API key rarely changes, but headless builds also need
`GEMINI_CLI_TRUST_WORKSPACE=true` on the AIFactory deployment env (set in
`factory-gitops apps/aifactory/manifests/manifests.yaml`) — without it the
gemini/antigravity CLI refuses to run in an "untrusted" workspace and exits before
any API call. Verify with `kubectl exec -n factory deploy/aifactory -- gemini
--skip-trust -m gemini-2.5-pro -p 'say PONG'`.

---

## How to wire it all up (the finisher)

Once you have the values, run from this repo:
```bash
# interactive — prompts for each value, sets it on the right repos:
scripts/wire-tokens.sh

# or non-interactive, e.g. just the seam-gate fleet token:
FACTORY_TOKEN=acw_xxx scripts/wire-tokens.sh --only factory-token
```
The script never prints token values and only sets secrets that you supply.

Verify (you can confirm a secret is *set*, never read its value back):
```bash
for r in Factory AIFactory PFactory TFactory CFactory; do
  echo "$r:"; gh secret list --repo olafkfreund/$r
done
```

---

## How to react if a token leaks

1. **Revoke at the source first**, then rotate in CI:
   - `acw_` key → revoke it in the factory's key management; mint a new one.
   - `APP_API_TOKEN` → regenerate in `factory-gitops` and redeploy (this rotates the
     fleet's service principal).
   - `GHCR_PAT` / `GITOPS_PAT` → delete the PAT in GitHub Developer settings; generate
     a replacement.
2. Update CI: `gh secret set <NAME> --repo olafkfreund/<repo>` with the new value
   (or re-run `scripts/wire-tokens.sh`).
3. GitHub Actions secrets cannot be read back, so verify only that the secret is
   *present* and re-run the affected workflow.
4. If the leaked token was the shared `APP_API_TOKEN`, treat every sibling service as
   exposed (that is the wildcard blast-radius the audit flags) — prefer migrating to
   scoped `acw_` keys so a single leak is contained.

---

*Keep this page current when you add a new secret: update the status table, the
finisher script, and the rotation steps.*
