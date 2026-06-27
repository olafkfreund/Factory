---
layout: default
title: "Cloud credentials: adding GCP and Azure"
permalink: /cloud-credentials/
---

# Cloud credentials: adding GCP and Azure

The Factory uses cloud credentials in **two distinct places**, for two different
jobs. Keep them separate — that is the single most important thing to get right.

| Where | What it does | Who reads it |
|---|---|---|
| **Factory services (Helm values / env)** | *Plan-time discovery* — the MCP layer probes what cloud resources exist so PFactory can plan against reality. **Never deploys.** | PFactory MCP credentials layer |
| **The target repo (GitHub Actions secrets)** | *Deploy-time apply* — a CI workflow runs `terraform apply` to stand the app up. This is where real deploys happen. | The repo's `deploy.yml` workflow |
| **TFactory** | *Test-time* — drives a browser against the deployed URL. **Needs no cloud creds**, only the public app URL. | TFactory Playwright lane |

The Factory is designed to **never run a production `apply` autonomously**
(RFC-0013). So the actual deploy always runs in CI with the repo's own secrets —
not with the Factory's planning credentials.

---

## 1. The fastest path: deploy credentials in the target repo

This is what you need for a repo that the Factory builds and deploys (e.g.
`factory-gcp-test`, `factory-azure-test`).

### GCP

1. Create a deploy service account in your project and grant it the roles your app
   needs (Cloud Run + Cloud SQL + Memorystore example):

   ```bash
   PROJECT=your-project; REGION=europe-west2
   gcloud iam service-accounts create factory-deploy --project "$PROJECT" \
     --display-name "Factory deploy"
   SA="factory-deploy@${PROJECT}.iam.gserviceaccount.com"
   for r in run.admin cloudsql.admin redis.admin artifactregistry.admin \
            vpcaccess.admin iam.serviceAccountUser serviceusage.serviceUsageAdmin \
            storage.admin compute.networkAdmin; do
     gcloud projects add-iam-policy-binding "$PROJECT" \
       --member "serviceAccount:$SA" --role "roles/$r" --condition=None
   done
   gcloud iam service-accounts keys create key.json --iam-account "$SA"
   ```

2. Add the key + project + region as repo secrets:

   ```bash
   gh secret set GCP_SA_KEY     --repo OWNER/REPO < key.json
   printf '%s' "$PROJECT" | gh secret set GCP_PROJECT_ID --repo OWNER/REPO
   printf '%s' "$REGION"  | gh secret set GCP_REGION     --repo OWNER/REPO
   rm -f key.json
   ```

3. The deploy workflow authenticates with `google-github-actions/auth` using
   `${{ secrets.GCP_SA_KEY }}`, then `terraform apply`. Use a **GCS bucket as the
   Terraform backend** so state survives across CI runs (without it, a re-run
   re-creates resources and fails with 409s — this is the one gotcha to remember).

### Azure

1. Create a service principal scoped to a subscription:

   ```bash
   az ad sp create-for-rbac --name factory-deploy --role Contributor \
     --scopes /subscriptions/SUBSCRIPTION_ID --sdk-auth   # prints the JSON below
   ```

2. Add it as repo secrets (both the `azure/login` JSON and the Terraform `ARM_*`
   form):

   ```bash
   az ad sp ... --sdk-auth | gh secret set AZURE_CREDENTIALS --repo OWNER/REPO
   printf '%s' "$AZURE_CLIENT_ID"       | gh secret set ARM_CLIENT_ID       --repo OWNER/REPO
   printf '%s' "$AZURE_CLIENT_SECRET"   | gh secret set ARM_CLIENT_SECRET   --repo OWNER/REPO
   printf '%s' "$AZURE_TENANT_ID"       | gh secret set ARM_TENANT_ID       --repo OWNER/REPO
   printf '%s' "$AZURE_SUBSCRIPTION_ID" | gh secret set ARM_SUBSCRIPTION_ID --repo OWNER/REPO
   ```

3. The deploy workflow uses `azure/login@v2` with `AZURE_CREDENTIALS`; Terraform's
   `azurerm` provider reads the `ARM_*` vars automatically.

> Tip: if you keep these in a local `.envrc`, you can wire all of the above in one
> pass without ever printing a secret value — pipe each into `gh secret set` via
> stdin, never on the command line.

---

## 2. Planning credentials in the Factory services (optional)

Only needed if you want PFactory to *discover* live cloud state at plan time. These
are mounted into the PFactory deployment, not used for deploys.

- **GCP**: set `GOOGLE_APPLICATION_CREDENTIALS` to a mounted SA JSON (Helm:
  `mcpCredentials.providers.gcp`).
- **Azure**: set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (Helm:
  the `azure` provider block).

PFactory's `core/mcp_credentials.py` probes these and exposes them to the MCP
discovery tools. They are read-only planning aids and are never used to apply
infrastructure.

---

## 3. How a full run uses them

1. **Plan** (PFactory) — ingests the GitHub issue; uses the *planning* creds (if
   configured) to reason about the target. Emits child issues.
2. **Code** (AIFactory) — writes the app, the Terraform, and the `deploy.yml`
   workflow. Uses **no** cloud creds.
3. **Deploy** (CI) — the workflow runs `terraform apply` with the **repo secrets**,
   producing a live URL.
4. **Test** (TFactory) — its Playwright lane hits the live URL (from
   `.tfactory.yml` `targets[].base_url`); **no** cloud creds.

## 4. Teardown

The deploy is metered. Always tear down a showcase when done:

```bash
cd infra && terraform destroy   # or delete the run/sql/redis/connector + the state bucket by hand
```

## 5. Security rules

- Secrets go in **env or files (0600) or GitHub secrets** — **never** on a command
  line or in argv (visible in `ps` / process listings).
- Never commit a key or `.env` to a repo.
- Give the deploy SA/SP the **minimum roles** for the app; scope Azure SPs to a
  single subscription or resource group.
