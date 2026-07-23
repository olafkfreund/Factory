---
layout: default
title: Environment Flags Reference
---

# Environment Flags Reference

The fleet-wide reference for the environment variables and feature flags each
Factory service reads. It answers three questions per flag: what it does, its
default (and whether it is on or off by default), and when you would change it.

This is a hub-level index compiled from the service code. Each service also has
its own canonical sources (listed under [Per-service sources](#per-service-sources));
where those disagree with this page, the code wins — file an issue so this page
can be corrected.

## Conventions

- **Prefixes.** Service-local flags use the service prefix: `PFACTORY_`,
  `AIFACTORY_`, `TFACTORY_`, `CFACTORY_`. Shared web-server settings use `APP_`
  (pydantic `BaseSettings`). Frontend build-time flags use `VITE_`. A handful of
  cross-cutting names are unprefixed (`DATABASE_URL`, `APP_API_TOKEN`).
- **Default on vs off.** "on" means the behaviour is active unless you set the
  flag to `0`/`false`. "off" means it is inert unless you opt in with
  `1`/`true`. Truthiness is parsed permissively (`1`, `true`, `yes`).
- **Where to set a flag** (in order of how the live fleet is configured):
  1. **gitops manifests** — `factory-gitops/apps/<svc>/manifests/manifests.yaml`
     `env:` list. This is the live source of truth for the cluster; ArgoCD syncs
     it. Example: `TFACTORY_TRIAGER_GIT_WRITE`.
  2. **Helm values** — `charts/<svc>/values.yaml` for services deployed by chart.
  3. **`.env` / `.env.example`** — local dev and the documented per-service set.
  4. **Per-project overrides** — AIFactory PR-endgame flags also read
     `<repo>/.aifactory/.env` first, then global env.
- **Sensitivity legend** used below:
  - `[sec]` security- or auth-affecting (auth bypass, egress, sandbox, secrets).
  - `[write]` performs an outward side-effect (pushes commits, posts comments,
    publishes docs).
  - `[on!]` default-ON in a way that is easy to miss.

## Read this first: high-impact flags

These change real behaviour or carry a side-effect and are the ones most worth
knowing before operating the fleet.

| Flag | Service | Default | Why it matters |
|---|---|---|---|
| `APP_DISABLE_AUTH` | AIFactory, PFactory | off | `[sec]` Bypasses all auth. Refuses to start on a non-loopback bind, but never enable in a shared cluster. |
| `TFACTORY_TRIAGER_GIT_WRITE` | TFactory | off (dry-run) | `[write]` `=1` commits accepted tests back onto the PR branch. Currently ON in gitops (surfaces the verify verdict on PRs, #964). |
| `TFACTORY_TRIAGER_PR_COMMENT` | TFactory | off (dry-run) | `[write]` `=1` posts the triage report as a `gh pr comment`. |
| `TFACTORY_PR_STATUS` | TFactory | off (dry-run) | `[write]` `=1` publishes the quality-gate commit status. |
| `TFACTORY_TRIAGER_HARVEST` | TFactory | **on** | `[on!]` Promotes high-confidence accepts into the project template library (writes files). |
| `AIFACTORY_INTAKE_AUTO_HANDOFF` | AIFactory | **on** | `[on!]` Intake builds auto-hand off to TFactory for verification. |
| `AIFACTORY_ALLOW_API_KEY` / `AIFACTORY_HEADLESS_PREFER_API_KEY` | AIFactory | off | `[sec]` Opt into metered `ANTHROPIC_API_KEY` billing; default is OAuth-only and the key is scrubbed. |
| `AIFACTORY_BUILD_BACKEND` | AIFactory | `subprocess` | Selects in-pod subprocess vs per-build k8s Job (`kubejob`). The live default is `kubejob`. |
| `AIFACTORY_RUNTIMES` | AIFactory | default runtime only | Operator allowlist of enabled build runtimes (e.g. `claude,copilot`). A runtime needs both this AND contract opt-in. |
| `PFACTORY_ALLOW_API_KEYS` / `PFACTORY_EGRESS_ENABLED` / `PFACTORY_RED_TEAM_REVIEW` | PFactory | off | `[sec]` Metered-key policy, secret-broker egress, red-team review lens. |
| `CFACTORY_API_KEYS` / `CFACTORY_MULTI_TENANT` / `CFACTORY_AUDIT_HMAC_SECRET` | CFactory | off / off / dev secret | `[sec]` Enables scoped-key auth, tenant scoping, and the tamper-evident audit chain. |
| `<svc>_EGRESS_ENABLED` | AIFactory/PFactory/TFactory | off | `[sec]` Allows the secret backend network egress. |

## Factory hub

The hub repo runs no long-lived service; these are read by its scripts and demo
templates.

| Flag | Default | On/off | Purpose |
|---|---|---|---|
| `PARR_NO_TEARDOWN` | unset | off | Keep PARR seam-probe artifacts instead of tearing them down (debugging). |
| `{PFACTORY,AIFACTORY,TFACTORY,CFACTORY}_API` | prod hostnames | - | Override each factory's base endpoint for the regression driver. |
| `{svc}_TOKEN` / `FACTORY_TOKEN` | `""` | - | Per-service bearer, falling back to the shared `FACTORY_TOKEN`; empty makes the regression job self-skip. |
| `AIFACTORY_URL` | default | - | Base URL for the benchmark pipeline driver. |
| `APP_API_TOKEN` | `""` | - | Host-wide service-principal bearer for the pipeline driver. |
| `FACTORY_SERVICE_NAME` | `"the Factory"` | - | Identity string the GitLab Duo agent goal references. |
| `GITLAB_TOKEN` / `AZDO_TOKEN` | `""` | - | `[sec]` Auth for syncing issue labels to the GitLab / Azure DevOps mirrors. |
| `TFACTORY_TARGET_URL` | `http://localhost:8080` | - | Target base URL the cloud-deploy Playwright acceptance test drives. |
| `VITE_{PFACTORY,AIFACTORY,TFACTORY,CFACTORY}_URL` | prod portal URLs | - | Portal-switcher destination links (build-time). |
| `DATABASE_URL` / `REDIS_{HOST,PORT,PASSWORD,SSL}` | see template | - | Postgres/Redis config for the scaffolded `templates/cloud-deploy` demo app. |

## PFactory (plan)

**Auth / access.** `APP_API_TOKEN` (shared bearer), `APP_DISABLE_AUTH` `[sec]` (off),
`APP_ALLOW_INSECURE_AUTH` `[sec]` (off), `PFACTORY_MCP_SECRET` / `PFACTORY_MCP_DEV` /
`PFACTORY_MCP_KEY` (MCP RPC auth), `PFACTORY_ALLOW_API_KEYS` `[sec]` (off, allow metered
provider keys), `METRICS_SCRAPE_TOKEN` (scrape `/metrics`), `APP_OIDC_*` (SSO login +
group-to-role).

**Auto-pipeline (code-aware planning).** `PFACTORY_AUTO_PLAN` / `AUTO_GENERATE` /
`AUTO_EVALUATE` / `AUTO_TRIAGE` (all default **on**; set `0` to skip a stage),
`PFACTORY_TRIAGER_GIT_WRITE` `[write]` (off), `PFACTORY_TRIAGER_PR_COMMENT` `[write]` (off),
`PFACTORY_TRIAGER_HARVEST` `[on!]` / `_HARVEST_GLOBAL`, `MIGRATIONS_AUTO_APPLY` (on,
alembic upgrade on boot).

**Model / routing.** `PFACTORY_ROUTING_POLICY` (JSON routing policy),
`PFACTORY_PLANNER_PINNED_MODEL` (escape hatch), `PFACTORY_EXECUTION_MODEL` (pin the
AIFactory build model), `UTILITY_MODEL_ID` / `UTILITY_THINKING_BUDGET`, `QA_LLM_PROVIDER`,
`INSIGHT_EXTRACTION_ENABLED` (on), `USE_CLAUDE_MD` (off), `AIFACTORY_BASH_SANDBOX` (on).

**Feasibility / enrichment.** `PFACTORY_BUDGET_MONTHLY_USD` (spend cap),
`PFACTORY_ENRICH_ADAPTERS` / `_CONNECTORS` (cloud enrich adapters),
`PFACTORY_RECON_TOKEN` / `_GIT_HOST` / `PFACTORY_GITHUB_API_BASE` (DORA recon + clone).
Cloud-cred presence (`AWS_*`, `AZURE_*`, `GOOGLE_*`, `KUBECONFIG`) is probed to decide
whether a target env is reachable.

**Lifecycle / persistence.** `PFACTORY_MAX_CONCURRENT_PLANS` (4),
`PFACTORY_PLAN_PERSIST` (off) / `_PLAN_STORE_DIR`, `PFACTORY_WORKSPACES_DIR` /
`PFACTORY_WORKSPACE_ROOT`, `DATABASE_URL` (presence switches jobstore to Postgres),
`PFACTORY_STALL_DEADLINE_SECONDS`.

**Handoff / signing.** `PFACTORY_AIFACTORY_HANDSHAKE` (off, read-back created task),
`AIFACTORY_TRUSTED_PLAN_KEY_<AUTHORITY>` `[sec]` (HMAC signing key for the trusted-plan fast
path), `PFACTORY_AIFACTORY_API_URL` / `_API_TOKEN` / `_ROOT`, `PFACTORY_HANDBACK_PREPARE` /
`_SEND` / `_MAX_CYCLES`.

**Security / execution.** `PFACTORY_STRICT_COMMAND_PARSING` `[sec]` (off),
`PFACTORY_EGRESS_ENABLED` `[sec]` (off), `PFACTORY_RED_TEAM_REVIEW` `[sec]` (off) /
`_RISK_THRESHOLD`, `PFACTORY_EXTENSION_REGISTRY`, `PFACTORY_CONTAINER_BIN` (docker),
`APP_SKILLS_PATH` / `PFACTORY_SKILLS_DIR`.

**Events / ops.** `PFACTORY_COMPLETION_SENTINEL` / `_DIR` / `_WEBHOOK` / `_TIMEOUT`,
`PFACTORY_STAGE_EVENT_*`, `PFACTORY_BATCH_*` (insight batching), `PFACTORY_COPILOT_DISPATCH_ENABLED`,
`PFACTORY_PLAN_REVIEW_COMMENT` `[write]`, `PFACTORY_RMUX_ENABLED`, `PFACTORY_DOCS_*` `[write]`,
`APP_LIVENESS_SWEEP_ENABLED` (off), `APP_HOST` / `APP_PORT` (3114) / `APP_CORS_ORIGINS`,
`GRAPHITI_*` (memory backend).

## AIFactory (build / coder)

**Build / job-native execution.** `AIFACTORY_BUILD_BACKEND` (`subprocess`; live default
`kubejob`), `AIFACTORY_BUILD_IMAGE` / `AIFACTORY_IMAGE` (build-Job image, precedence 1 then
2), `AIFACTORY_SANDBOX_REPO_PVC` (`aifactory-data`), `AIFACTORY_NIX_STORE_PVC`,
`AIFACTORY_DATA_ROOT`, `AIFACTORY_SANDBOX_NAMESPACE` (`factory`), `AIFACTORY_BUILD_SA`
(`aifactory-sandbox`), `AIFACTORY_BUILD_DEADLINE_SECONDS` (6h), `APP_BACKEND_PATH`,
`AIFACTORY_PACK_WORKSPACE` (off, pack `/work` to object store for multi-node),
`AIFACTORY_PACKED_NIX_IN_IMAGE` (off).

> **Build-Job env allowlist.** A build Job inherits none of the control-plane env; only the
> `_PASSTHROUGH_BUILD_ENV` allowlist in `build_backend.py` is forwarded when present (provider
> base-URLs/tokens, `GITHUB_TOKEN`/`GH_TOKEN`, S3 creds, `AIFACTORY_GRAPHIFY_ENABLED`, ...).
> `ANTHROPIC_API_KEY*` is deliberately excluded (OAuth-only). A new build-time flag that must
> reach the coder has to be added to this allowlist.

**Auth.** `APP_DISABLE_AUTH` `[sec]` (off), `APP_API_TOKEN`, `AIFACTORY_ALLOW_API_KEY` `[sec]`
(off), `AIFACTORY_HEADLESS_PREFER_API_KEY` `[sec]` (off), `APP_OIDC_*` / `SAML_ENABLED` /
`SCIM_ENABLED`, `AIFACTORY_TRUSTED_PLAN_KEY_<AUTHORITY>` `[sec]`.

**Intake.** `AIFACTORY_INTAKE_PARALLEL` (off) / `_WORKERS`, `AIFACTORY_INTAKE_AUTO_HANDOFF`
`[on!]` (on), `AIFACTORY_INTAKE_POLLER` (off) / `_INTERVAL_S` (30) / `_REQUEUE_AFTER_S` (600) /
`_REPOS` / `_DB`.

**PR endgame** (read per-project `.aifactory/.env` first). `AIFACTORY_AUTO_PR` (off),
`AIFACTORY_AUTO_MERGE` (off, needs AUTO_PR), `AIFACTORY_PR_REVIEWER` (`aifactory`),
`AIFACTORY_COPILOT_DISPATCH_ENABLED` (off). Note: `AIFACTORY_AUTO_DEPLOY` is documented but
has no reader in service code (skill-driven) — see [gaps](#coverage-gaps).

**Model / agent.** `UTILITY_MODEL_ID` / `UTILITY_THINKING_BUDGET`, `QUICK_MODE` (off),
`AIFACTORY_SOLO_MODE` (off), `AIFACTORY_CONTEXT_SUMMARY` (off),
`AIFACTORY_CLAUDE_ENFORCEMENT_ENABLED` (off), `AIFACTORY_GRAPHIFY_ENABLED` (off, code-graph
MCP at build), `AIFACTORY_AGENT_STALL_TIMEOUT` (600), `AIFACTORY_FIRST_TOKEN_TIMEOUT` (120),
`AIFACTORY_RUNTIMES` (runtime allowlist).

**Security / sandbox.** `AIFACTORY_BASH_SANDBOX` `[sec]` (on), `AIFACTORY_EXTRA_ALLOWED_COMMANDS`,
`AIFACTORY_AGENT_SANDBOX` `[sec]` (off) / `_PIDNS`, `AIFACTORY_SANDBOX_GATES` / `_NETWORK`,
`AIFACTORY_ACT_GUARDRAIL`, `AIFACTORY_EGRESS_POLICY` `[sec]` (off) / `_ALLOWED_HOSTS`,
`AIFACTORY_TEST_EVIDENCE_GATE` (off, honesty gate).

**Tenant / crypto / audit.** `AIFACTORY_MULTI_TENANT` `[sec]` (off), `TENANT_ISOLATION_ENABLED`
`[sec]` (off), `APP_KMS_BACKEND` (fernet), `AUDIT_ANCHOR_PER_TENANT` (off), `TENANT_*`.

**Control plane / misc.** `AIFACTORY_MCP_REMOTE_ENABLED` (off), `AIFACTORY_RMUX_ENABLED` (off,
live agent console) / `_PANES_DIR`, `AIFACTORY_COMPLETION_WEBHOOK` / `_SENTINEL` / `_TIMEOUT` /
`_OUTBOX` / `_OUTBOX_DB`, `AIFACTORY_EVENT_SOURCE`, `APP_MAX_CONCURRENT_TASKS` (5),
`APP_AGENT_MONITOR_SYNC_INTERVAL` / `_MAX_CONTINUATION_ROUNDS`, `MIGRATIONS_AUTO_APPLY` (on),
`APP_WORKSPACE_S3_URI_BASE`, `REDIS_URL` / `_CHANNEL`, `CFACTORY_SEARCH_URL` / `_READ_KEY`,
`APP_CORS_ORIGINS`, `AIFACTORY_BATCH_*`.

## TFactory (verify / test)

**Pipeline gates.** `TFACTORY_AUTO_PLAN` / `AUTO_GENERATE` / `AUTO_EVALUATE` / `AUTO_TRIAGE`
(all default **on**; `=0` skips the stage). Note the verify Job force-sets EVALUATE/TRIAGE off
and drives them explicitly.

**Triager side-effects** (all default dry-run unless noted). `TFACTORY_TRIAGER_GIT_WRITE`
`[write]` (`=1` commits accepted tests to the PR branch — currently ON in gitops),
`TFACTORY_TRIAGER_PR_COMMENT` `[write]` (`=1` posts the triage report), `TFACTORY_PR_STATUS`
`[write]` (`=1` publishes the gate commit status), `TFACTORY_TRIAGER_GIT_SIGN` (GPG-sign),
`TFACTORY_TRIAGER_HARVEST` `[on!] [write]` (**on**, promotes accepts into the template lib) /
`_HARVEST_GLOBAL`.

**Completion / stage events.** `TFACTORY_COMPLETION_WEBHOOK` / `_TIMEOUT` (5),
`TFACTORY_COMPLETION_SENTINEL`, `TFACTORY_COMPLETION_OUTBOX` / `_BACKOFF_BASE` / `_BACKOFF_CAP` /
`_MAX_ATTEMPTS`, `TFACTORY_EVENT_SOURCE`, `TFACTORY_STAGE_EVENT_SENTINEL` / `_WEBHOOK` /
`_WEBHOOK_TIMEOUT`.

**Handback loop.** `TFACTORY_HANDBACK_PREPARE` (off) / `_SEND` `[write]` (off) / `_MAX_CYCLES`,
`TFACTORY_SELF_API_URL`.

**VAL-3 disposable target.** `TFACTORY_VAL3_K8S_JOB` (off) / `_JOB_IMAGE`,
`TFACTORY_VAL3_LOCAL_VM` (off), `TFACTORY_VAL3_CLOUD` (off), `TFACTORY_VAL3_TARGET_IS_PROD`
`[sec]` (off, prod-safety guard that blocks destructive VAL-3), `TFACTORY_TARGET_URL`
(exported to the SUT test process).

**Nix runner / verify backend.** `TFACTORY_NIX_IN_IMAGE` (off) / `_NIX_RUNNER_IMAGE` /
`_NIX_STORE_PVC`, `TFACTORY_IMAGE` / `TFACTORY_VERIFY_IMAGE`, `TFACTORY_VERIFY_BACKEND`
(`nixjob`/`docker`/`host`), `TFACTORY_VERIFY_EXEC` (`kubejob` vs in-pod), `TFACTORY_RUNNER_MODE`
(host-pytest fallback), `TFACTORY_CONTAINER_BIN` (docker), `TFACTORY_CI_PARITY` (on),
`TFACTORY_EQUIVALENCE_LANE` (off) / `_BACKEND` / `_IMAGE`, `TFACTORY_REVIEW_LANE` (off).

**Verify-Job credential injection** `[sec]`. `TFACTORY_VERIFY_OAUTH_SECRET_NAME` / `_KEY`
(source Claude OAuth via k8s secretKeyRef), `TFACTORY_VERIFY_PROVIDER_SECRET_NAME`,
`TFACTORY_VERIFY_CLI_CREDS_SECRET`.

**Infra / paths / auth.** `TFACTORY_WORKSPACE_ROOT` / `TFACTORY_WORKSPACES_PVC`,
`TFACTORY_SANDBOX_NAMESPACE` (factory), `TFACTORY_DATA_ROOT`, `TFACTORY_AIFACTORY_ROOT` /
`_API_URL`, `TFACTORY_API_URL` / `_API_TOKEN_FILE` / `TFACTORY_MCP_KEY`, `TFACTORY_PORTAL_PORT`
(3103), `TFACTORY_STALL_DEADLINE_SECONDS`, `TFACTORY_EGRESS_ENABLED` `[sec]` (off),
`TFACTORY_AGE_IDENTITY` `[sec]`.

**Misc.** `TFACTORY_VERDICT_VOTES` (3), `TFACTORY_DEP_AGE_CHECK` (on),
`TFACTORY_BATCH_*` (insight batching), `TFACTORY_DOCS_EMIT` / `_GIT_WRITE` `[write]` / `_DIR` /
`_BACKSTAGE` / `_CONFLUENCE`, `TFACTORY_BACKSTAGE_*`.

## CFactory (cockpit)

**Backend** (`CFACTORY_*` unless noted). Ports: `CFACTORY_BACKEND_PORT` (3111) /
`CFACTORY_FRONTEND_PORT` (3110). Upstreams: `CFACTORY_AIFACTORY_API_URL` (3101) /
`_PFACTORY_API_URL` (3105) / `_TFACTORY_API_URL` (3103) / `_OBSERVE_API_URL` (5080).
Auth / secrets `[sec]`: `CFACTORY_UPSTREAM_TOKEN` (bearer to siblings),
`CFACTORY_AIFACTORY_TOKEN` (live-agent WS proxy), `CFACTORY_API_KEYS` (scoped-key auth; unset =
open single-user), `CFACTORY_MCP_SECRET` (MCP transport bearer), `CFACTORY_AUDIT_HMAC_SECRET`
(tamper-evident audit chain; hard-warns if left at the dev default), `CFACTORY_MULTI_TENANT`
(off). Data / live view: `CFACTORY_DATABASE_URL` (unset = local SQLite),
`CFACTORY_SUBSCRIBE_UPSTREAMS` (off), `CFACTORY_LIVE_PROGRESS` (off) /
`CFACTORY_POLL_INTERVAL_SECONDS` (3.0), `CFACTORY_STALL_DEADLINE_SECONDS` (900).
Copilot: `CFACTORY_COPILOT_MODEL` (claude-opus-4-8) / `_COPILOT_PROVIDER` (claude) /
`_OLLAMA_CLOUD_BASE_URL` / `_OLLAMA_API_KEY`. Display: `CFACTORY_PUBLIC_API_URL`,
`CFACTORY_WORKSPACE_ROOT`, `ANTHROPIC_API_KEY` (Claude copilot).

**Frontend** (`VITE_*`, build-time). `VITE_OBSERVE_URL` (OpenObserve link-out; `""` hides it),
`VITE_PFACTORY_URL` / `VITE_AIFACTORY_URL` / `VITE_TFACTORY_URL` (tab external-link targets).
The SPA calls its backend via a relative `/api` nginx proxy, so there is no frontend API-base
flag.

## Per-service sources

The canonical, code-adjacent sources for each service (this page indexes them):

- **Factory hub** — `docs/dev/secrets-and-tokens.md`, `scripts/README-parr-regression.md`.
- **PFactory** — `docs/dev/environment-reference.md` (exhaustive, code-verified), `.env.example`.
- **AIFactory** — `docs/docs/environment-reference.md` (exhaustive) + `docs/docs/configuration-reference.md`,
  `apps/backend/.env.example`, `apps/web-server/.env.example`.
- **TFactory** — `docs/environment-reference.md` (exhaustive, backend + web-server), `.env.example`, `README.md`.
- **CFactory** — `docs/dev/environment-reference.md` (public) + `techdocs/dependencies.md` (the
  `CFACTORY_*` table), `charts/cfactory/values.yaml`.

## Coverage gaps

As of the 2026-07-23 documentation refresh, every service now ships an exhaustive,
code-verified `environment-reference.md` (linked above): each was produced by grepping the
service for every `os.environ` / `os.getenv` / pydantic `Settings` field and reconciling the
result against `.env.example`, so the prior "no per-service central reference" gap for
PFactory and TFactory is closed (TFactory added ~40 previously-undocumented vars — the whole
web-server security surface; PFactory reconciled 219 vars and added 33 to `.env.example`).

One residual item to close at source:

- **Documented-but-unread:** `AIFACTORY_AUTO_DEPLOY` appears in the AIFactory configuration
  reference but has no reader in service code (it is handled by the deploy-then-verify skill).
  Either wire it or annotate it as skill-only.

When adding a new flag, put the authoritative row in the service's own `environment-reference.md`
and mirror the security- and side-effect-bearing ones (`[sec]` / `[write]` / `[on!]`) into the
high-impact section above — especially default-ON writers like `TFACTORY_TRIAGER_HARVEST` and
`AIFACTORY_INTAKE_AUTO_HANDOFF`, and the auth-bypass `APP_DISABLE_AUTH`.
