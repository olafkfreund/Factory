# cloud-deploy: the Factory's managed-web-app deploy templates

The canonical, **proven** patterns the Factory scaffolds from to build and deploy a
small managed web app (no Kubernetes) to a public cloud, then have TFactory test it.
One cloud-agnostic app, one Terraform + CI workflow per cloud.

```
app/            cloud-agnostic FastAPI + game UI (Redis supports plain or TLS+AUTH)
Dockerfile      single image, runs on Cloud Run / App Service / App Runner
gcp/            Cloud Run + Cloud SQL + Memorystore  (PROVEN end to end)
azure/          App Service + Postgres Flexible + Azure Cache for Redis (READY)
aws/            App Runner + RDS + ElastiCache (reference)
tests/          the TFactory Playwright e2e + .tfactory.yml
```

## How the Factory uses this

The Factory **never applies infrastructure autonomously** (RFC-0013): the deploy
always runs in the target repo's CI with **that repo's** cloud secrets. The flow:

1. **Plan** (PFactory) — the plan issue names the cloud + managed services.
2. **Code** (AIFactory) — scaffolds the app from `app/` and the cloud's `*/main.tf`
   + `*/deploy.yml`, parameterizing names/regions. (These templates are the
   deterministic deploy pattern AIFactory lacked for GCP/Azure.)
3. **Deploy** (CI) — `<cloud>/deploy.yml` runs `terraform apply` with the repo
   secrets, producing a live URL.
4. **Test** (TFactory) — the Playwright lane plays the game and verifies the
   scoreboard against the live URL (`.tfactory.yml`).

## Credentials

Per `docs/cloud-credentials.md`: deploy creds live in the **target repo's GitHub
secrets** (GCP_SA_KEY / AZURE_CREDENTIALS+ARM_* / AWS_ACCESS_KEY_ID). The deploy
identity needs **Contributor-level** rights (not Reader) on the target
project/subscription/account.

## The one rule learned the hard way

Use a **remote Terraform backend** (GCS / Azure Storage / S3) from the first run —
without it, a CI re-run starts stateless and re-creates resources (409s).

## Still open (for full autonomy)

These templates close the "no GCP/Azure deploy pattern" gap. Making the Factory
emit them **without a human** still needs: PFactory PaaS-target detection (RFC-0013
service layer) and an AIFactory deploy-codegen step that picks the right template
from the contract's `deployment` block.
