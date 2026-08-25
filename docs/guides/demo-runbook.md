---
layout: default
title: "Demo runbook: driving a card through plan, code and test"
permalink: /guides/demo-runbook/
---

# Demo runbook

**User story.** As someone about to show Factory to people who have not seen it,
I want to drive a card from an idea to verified, evidenced code without touching
anything manually mid-demo, so that the pipeline is what the audience watches
rather than my configuration.

This covers the three handovers separately (plan, code, test), the sequence run
that does all three, and the same operations from Claude Code. It also records
the failure modes that look like success, because those are what turn a demo
into a debugging session.

## What you need first

One repository registered identically in all four portals. The registration is
per-service and they must agree, or a stage dispatches into nothing:

| Service | Where it is registered | Must match |
| --- | --- | --- |
| CFactory | `tenant_git_config` + `git_repository` (with `default_for_tenant`) | the repo, and the AIFactory project id |
| AIFactory | `projects.json`, keyed by project id | the project id CFactory points at |
| PFactory | `projects.json` | the same repo |
| TFactory | `projects.json` | the same repo |

Verify rather than assume — a repo present in three of four is the most common
cause of a card that dispatches and does nothing:

```bash
# CFactory: the default the dispatcher uses
kubectl --context k3d-factory exec -n factory <cfactory-pod> -c cfactory -- python3 -c "
import sqlite3
c = sqlite3.connect('/home/nonroot/.cfactory/cfactory.db')
for r in c.execute('SELECT project, default_for_tenant, aifactory_project_id FROM git_repository'):
    print(r)"
```

`default_for_tenant` is the field that decides. A repo can be registered and
still unused because a different row holds the default.

## The three handovers, separately

Each stage is one POST against CFactory. Port **3111**, and the container has no
`curl` -- use `python3`:

```bash
POD=$(kubectl --context k3d-factory get pods -n factory --no-headers \
      | awk '/^cfactory-[0-9a-f]/&&$3=="Running"{print $1;exit}')

kubectl --context k3d-factory exec -n factory "$POD" -c cfactory -- python3 -c "
import os, json, urllib.request
key = os.environ.get('CFACTORY_API_KEYS','').split(':')[0]
req = urllib.request.Request(
    'http://localhost:3111/api/cards/FCT-4/actions/code',   # plan | code | test
    data=b'{}', method='POST',
    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
print(json.load(urllib.request.urlopen(req, timeout=120)))"
```

| Action | Goes to | Produces |
| --- | --- | --- |
| `actions/plan` | PFactory | a plan, and the RFC-0005 `environment` manifest |
| `actions/code` | AIFactory | a branch, commits, a PR |
| `actions/test` | TFactory | generated tests, verdicts, evidence |

**The stages are not independent.** `test` refuses with `no_build_to_verify`
unless the card has a completed `code` stage and a `correlation_key`. `code` on
a card with no tier refuses with `no_tier`. The refusals are deliberate: they
exist so a stage never runs against nothing and reports success.

## All three together

```
cfactory_run_card(card_key="FCT-4")
```

Dispatches only the first stage still owed; each later stage goes out when the
previous reaches terminal success. It **resumes** a part-finished card rather
than restarting it, and a failed stage stops the sequence with the card blocked
and the reason recorded.

Use this for the demo. Use the individual actions when you want to show a single
handover in isolation, or when re-running one stage after a fix.

## From Claude Code

CFactory exposes the same operations as MCP tools, so the whole pipeline is
drivable from a conversation:

| Tool | Does |
| --- | --- |
| `cfactory_create_card` | create the work item |
| `cfactory_plan_card` | hand over to PFactory |
| `cfactory_code_card` | hand over to AIFactory |
| `cfactory_test_card` | hand over to TFactory |
| `cfactory_run_card` | plan then code then test |
| `cfactory_get_card` / `cfactory_get_timeline` | what happened |
| `cfactory_get_anomalies` | what went wrong |

This is worth showing: the same pipeline an operator drives from the portal is
drivable from an agent, with the same refusals and the same audit trail.

## Re-running a card

Three things must be cleared, and **skipping any one of them makes the dispatch
return success while building nothing**:

1. **The AIFactory task.** Otherwise the dispatch returns `dispatched: true` and
   no build starts -- the task sits in `human_review` and is silently reused.
2. **The completed Kubernetes Job.** A name collision surfaces as a bare 500.
3. **`cards.stage_runs`.** Otherwise `409 stage_already_running`.

```bash
# 1. delete the task            DELETE /api/tasks/<url-encoded task_id>   (AIFactory, :3101)
# 2. delete the Job             kubectl delete job factory-aifactory-<...> -n factory
# 3. clear the stage record     UPDATE cards SET status='backlog', stage_runs='{}' WHERE card_key=...
```

`scripts/reset-demo.sh` does all three, in the order that works, and verifies
the result rather than assuming it:

```bash
CARDS="FCT-1 FCT-2 FCT-3 FCT-4" ./scripts/reset-demo.sh
```

Two things it encodes that are easy to get wrong by hand. **Producers first,
CFactory last** -- CFactory polls its producers, so clearing it first just
repopulates it. And it clears `job_states`, because a stale row there
resurrects a deleted task through the reconcile loop. It deliberately does
*not* delete the `aifactory/*` branches: those hold the only evidence a
previous run built anything, and a re-run overwrites them anyway.

The first of those is the one that bites. A dispatch that returns `200` with a
`task_id` looks identical whether it started a build or adopted a finished one.

## Verifying the result

Do not read the card's colour. Read the artifacts.

**Did it build anything?** Compare the branch against its base. A build that
committed nothing has a branch tip identical to `origin/main`:

```bash
git rev-list --count origin/main..origin/aifactory/<spec-id>   # 0 means nothing was built
```

**Did the tests run?** In TFactory's `status.json` for the spec:

| Field | Healthy | Meaning when wrong |
| --- | --- | --- |
| `committed_count` | > 0 | 0 means no test was committed, so no lane ran |
| `flagged_count` | 0 | every flagged test is one the evaluator would not vouch for |
| `ac_fidelity.verified_fraction` | `n/n` | `0/n` means no acceptance criterion was exercised |
| `lane_progress` | lanes `executed` | `error` is a lane that could not run; `pending` is one nothing reached |

That `lane_progress` row was wrong in the first edition of this guide, which
said all-`pending` meant nothing executed. It meant nothing at all: the field
was written `pending` by two initialisers and never advanced, so it read
identically for a clean run and a dead one. TFactory#1161 makes it say
something. On a run from before that landed, ignore the field and use
`committed_count` and `ac_fidelity`, which were always real.

`triager_warnings` states it plainly when nothing was verified:
`"0/8 acceptance criteria verified - no committed test exercises any
acceptance criterion."` A card can be green with that warning attached.

**Is the evidence real?** Screenshots and video land in the branch. Check the
byte sizes differ from any committed copies -- identical sizes mean you are
looking at the checkout, not new output.

## Failure modes that look like success

Every one of these has happened:

- **A green Job with an empty branch.** The subtask counter said complete; the
  worktree had gained nothing. Diff the branch.
- **A dispatch that adopts a finished task.** Returns `200` and a `task_id`,
  starts no build. Delete the task first.
- **Tests that pass against the wrong API.** The coder writes the tests too, so
  a suite can be green while implementing none of the functions the card named.
  Check the exports against the acceptance criteria.
- **`0` from a failed measurement.** A count of zero and a command that errored
  look the same through a pipe. Never `|| echo 0` a measurement.
- **A lane that reports flaky when it is unconfigured.** `stability=error`
  across three runs is what a missing sandbox looks like, not a bad test.

## Known gaps at the time of writing

- **`skip_planning`** is set for every low- and medium-tier card, so no plan and
  no `environment` manifest is written. Anything keyed off that manifest is
  inert for those cards. Run a card at a tier that plans if you need it.
- **The browser lane** needed the repo to carry its own `flake.nix`, because
  the contract's environment block is absent under `skip_planning`. TFactory#1161
  gives the lane a generated browser flake when there is neither, so a repo
  without one is no longer a dead end. A repo-owned flake still wins.

## Cleaning up between demos

Cards back to `backlog` with empty `stage_runs`, AIFactory tasks deleted, and
leftover Jobs removed. The portal shows completed work items from previous runs,
which is usually what you want on stage -- an empty cockpit demonstrates less
than four finished pipelines.
