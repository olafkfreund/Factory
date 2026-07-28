---
layout: default
title: "Cloud development"
permalink: /guides/cloud-development/
---

# Cloud development

**User story.** As a platform engineer, I want the factory to build services that
target real cloud infrastructure and to tell me before it deploys whether the
change is deployable, so that infrastructure mistakes surface at plan time
rather than at 3am.

---

## What is shipped

| Capability | Endpoint |
|---|---|
| Cloud readiness assessment | `GET/POST /api/cloud/assessment`, `/api/cloud/assessments`, `/api/cloud/assessments/run` |
| Deployment-aware planning | plans record deployment intent |
| Dry-run deploy lane | verification runs the deploy without committing it |

Deployment-aware planning means the plan states what the change needs to run --
not only what code to write. A service that needs a database, a queue and an
egress rule is planned as such, and the gap is visible before anyone builds it.

---

## Turn by turn

**1. Register the project and describe the target.**

Acceptance criteria should include the infrastructure expectations, because
those are what gets verified:

```markdown
## Acceptance Criteria
- AC#1: the service starts with no network access beyond its declared egress
- AC#2: configuration comes from environment, with no secrets in the image
- AC#3: a health endpoint answers 200 within 500ms of container start
```

**2. Run a cloud assessment.**

```bash
curl -X POST -H "Authorization: Bearer $FACTORY_TOKEN" \
  https://tfactory.<your-domain>/api/cloud/assessments/run
```

**Checkpoint.** An assessment record you can read back from
`/api/cloud/assessments`. Read it before building; that is the point of running
it first.

**3. Plan, approve, build** as in [Onboarding]({{ '/guides/onboarding/' | relative_url }}).

**4. Verify with the deploy lane.**

The dry-run lane exercises the deployment path without committing to it. A
change that builds but cannot deploy fails here rather than in production.

**Checkpoint.** A verdict that names what it exercised. "Deploy dry-run passed"
with no detail is worth less than a list of what it actually did.

---

## Things that bite

**A deploy can succeed and change nothing.** Two merges close together can
cancel each other's pipelines, leaving the newest commit built but never
deployed -- with every check green, because a cancelled run reports neither
success nor failure. Compare the deployed image tag against the newest commit
that should have deployed, rather than trusting the pipeline's own colour.

**"Synced" is not "running what you asked for".** A GitOps controller reporting
`Synced` means synced to the last revision it fetched. One service here ran a
30-minute-old image while its application showed `Synced, Healthy` and auto-sync
was enabled. Compare the controller's revision to the repository HEAD.

**Docs-only commits legitimately do not deploy.** If your deploy workflow ignores
`docs/**`, the newest commit is not always the one that should be live. Compare
against the newest *deployable* commit or you will chase phantom drift.

---

## Options reference

| Setting | Options | Default | Unset behaviour |
|---|---|---|---|
| Assessment | run per project | not run | no readiness record exists |
| Deploy lane | dry-run | dry-run | nothing is committed to the target |
| Deploy paths-ignore | glob list | `docs/**`, `**/*.md` | every commit triggers a deploy |

---

## Next

- [Enterprise scale]({{ '/guides/enterprise-scale/' | relative_url }})
- [Testing scenarios]({{ '/guides/testing/' | relative_url }})
