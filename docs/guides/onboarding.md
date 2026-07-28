---
layout: default
title: "Onboarding: from nothing to a verified change"
permalink: /guides/onboarding/
---

# Onboarding

**User story.** As a developer joining a team that runs Factory, I want to get
from an empty machine to one verified change through the pipeline, so that I
understand what each service does before I depend on it.

Budget about an hour. You will finish with a change that PFactory planned,
AIFactory built, TFactory verified, and CFactory showed you.

---

## Before you start

You need:

| Thing | Why | Check it |
|---|---|---|
| A repository you may push to | The pipeline opens pull requests | `git push --dry-run` |
| A provider token | Reading issues, opening PRs | see [Boards]({{ '/guides/boards/' | relative_url }}) |
| Access to the four services | Or run them locally | [Run locally]({{ '/run-locally/' | relative_url }}) |

If you are running locally rather than against a shared cluster, do
[Run the whole Factory locally]({{ '/run-locally/' | relative_url }}) first and
come back. The rest of this guide is identical either way; only the base URLs
change.

---

## Step 1: confirm all four services answer

Before anything else, establish that the fleet is reachable. Every later failure
is easier to read once you know this.

```bash
for s in pfactory aifactory tfactory; do
  printf '%-10s ' "$s"
  curl -s -o /dev/null -w '%{http_code}\n' \
    -H "Authorization: Bearer $FACTORY_TOKEN" \
    "https://$s.<your-domain>/api/health"
done
```

**Checkpoint.** Three `200`s.

A `401` means your token is wrong, not missing — those are different problems and
the response body says which. A `302` means you have reached an authentication
proxy rather than the service; see the note on CFactory below.

**CFactory is different on purpose.** It sits behind an OIDC proxy, so a machine
client gets a `302` to the identity provider and a browser gets a login page.
That is the correct answer, not a fault. Use a browser for CFactory.

---

## Step 2: register your project

A project is a workspace: a checkout plus the state each service keeps about it.

```bash
curl -X POST -H "Authorization: Bearer $FACTORY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/your/checkout", "name": "my-service"}' \
  https://aifactory.<your-domain>/api/projects
```

**Checkpoint.** The response carries an `id`. Keep it; several later calls take
it, and the same project must be registered in each service that will touch it.

A project registered in AIFactory is not automatically known to TFactory. This
catches people out: a build succeeds and verification reports "no such project".

---

## Step 3: write a spec PFactory will accept

PFactory rejects work it cannot plan. The most common rejection is a missing
acceptance criteria section, and the error says so plainly:

```
400 {"detail":"no acceptance criteria found - add an '## Acceptance Criteria'
     section with bullets, or 'AC#N: ...' lines."}
```

A minimal spec that is accepted:

```markdown
# Add a health endpoint

## Acceptance Criteria
- AC#1: GET /healthz returns 200
- AC#2: the response body is {"status": "ok"}
```

Send it:

```bash
curl -X POST -H "Authorization: Bearer $FACTORY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"health endpoint","category":"software","channel":"portal",
       "text":"# Add a health endpoint\n\n## Acceptance Criteria\n- AC#1: GET /healthz returns 200"}' \
  https://pfactory.<your-domain>/api/plan/sessions/ingest-text
```

**Checkpoint.** A `session_id` comes back. That identifier follows the work
through planning.

**Why acceptance criteria are mandatory.** They are what TFactory verifies
against later. A spec without them can be built but not judged, so the pipeline
declines at the point where the omission is cheap to fix.

---

## Step 4: review and approve the plan

Planning produces a plan you approve, reject, or discard.

| Action | Endpoint | When |
|---|---|---|
| Approve | `POST /api/plan/sessions/{id}/approve` | the plan is right |
| Reject | `POST /api/plan/sessions/{id}/reject` | the plan is wrong, after processing |
| Discard | `POST /api/plan/sessions/{id}/discard` | abandon before planning |

Reject and discard are not interchangeable. `reject` is a post-review verdict and
refuses a session that has not been processed:

```
400 {"detail":"process the plan before rejecting"}
```

They also take different fields — `discard` wants `actor` and `reason`, `reject`
wants `approver` and `feedback`. Sending the wrong pair returns a `422` naming
the missing field.

**Checkpoint.** After approval the session status moves on from `ingested`. Read
it back with `GET /api/plan/sessions/{id}`.

---

## Step 5: build

Hand the approved plan to AIFactory. It creates a task and runs it to a terminal
state.

**Checkpoint.** `GET /api/tasks` shows your task, and its status settles on a
terminal value rather than staying in progress. A build that reaches
`human_review` has stopped and is waiting for you — that is a normal outcome, not
a failure.

---

## Step 6: verify

TFactory checks the built change against the acceptance criteria you wrote in
step 3. This is the step that makes the rest worth doing: without it you have
automation that writes code and grades its own homework.

See [Testing scenarios]({{ '/guides/testing/' | relative_url }}) for what
verification actually asserts and how to raise the bar.

**Checkpoint.** A verdict, and a report you can read. If verification fails, the
change goes back rather than forward — the handback loop is the point.

---

## Step 7: watch it in CFactory

Open CFactory in a browser and find your work item. You should see the stages,
which one is active, and the cost so far.

**Checkpoint.** Your task appears with a status matching what the APIs told you.
If the cockpit disagrees with the services, trust the services and file an issue
— that disagreement is a bug worth knowing about.

---

## What to do when a step does not behave

Work in this order. It is roughly cheapest-first.

1. **Read the response body.** These services return reasons, not just codes.
   `"no acceptance criteria found"` and `"process the plan before rejecting"` are
   both complete explanations.
2. **Check you are talking to the service.** A `302` means a proxy answered. A
   `404` on something you expected to exist may mean the endpoint is genuinely
   absent rather than your path being wrong.
3. **Check the project is registered in the service you are calling**, not just
   in the one where you created it.
4. **Check the token, not just its presence.** `Missing Authorization header` and
   `Invalid token` are different failures with different fixes.

---

## Next

- [Working as a team]({{ '/guides/teams/' | relative_url }}) — roles and approval gates
- [Boards and work items]({{ '/guides/boards/' | relative_url }}) — drive this from issues instead of curl
