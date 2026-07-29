---
layout: default
title: "Working as a team"
permalink: /guides/teams/
---

# Working as a team

**User story.** As an engineering manager, I want to know where a human must
decide and where the pipeline may proceed alone, so that automation speeds the
team up without anyone losing control of what ships.

---

## Where humans are in the loop

Three gates. Each exists because the cost of getting it wrong is borne by a
person, not the machine.

| Gate | Who acts | What happens if nobody does |
|---|---|---|
| Plan approval | reviewer | work waits; nothing is built |
| Human review | reviewer | the task sits in `human_review` indefinitely |
| Merge | code owner | the PR stays open |

**A task waiting on a human is not stalled.** This distinction matters more than
it sounds: on a live board recently, three tasks had waited 19, 28 and 38 hours
in `human_review` and were entirely healthy, while a fourth had been dead for 27
hours. The oldest task was the healthiest one. Anything that judges staleness by
age alone will reach the wrong conclusion.

---

## Roles

Factory does not impose an org chart. In practice teams settle on:

- **Requester** — files the issue, writes acceptance criteria. Often not an engineer.
- **Approver** — signs off the plan before anything is built. The cheapest place
  to catch a misunderstanding.
- **Reviewer** — reviews the produced change, as they would any pull request.

The approver and reviewer can be the same person on a small team. They should
not be the requester on a change that matters, for the ordinary reason.

---

## Acceptance criteria are the contract

The requester writes them; verification checks against them. This is why
PFactory refuses a spec without them rather than accepting one and guessing.

Good criteria are checkable by someone who did not write them:

```markdown
## Acceptance Criteria
- AC#1: GET /healthz returns 200 within 500ms
- AC#2: the response body is {"status": "ok"}
- AC#3: an unauthenticated request returns 401, not 302
```

That third one is the kind of criterion worth writing explicitly. A service
behind an authenticating proxy answers unauthenticated calls with a redirect,
and a check that accepts "anything that is not a 5xx" will pass on the login
page. State which you mean.

---

## Reading the cockpit honestly

CFactory reports what the records say. When a record is wrong, the cockpit is
faithfully wrong, and the fix belongs upstream rather than in the display.

| You see | Usually means |
|---|---|
| `running` with no recent progress | the worker may have died; see below |
| `in review` for days | nobody has looked; that is a people problem |
| `failed` | read the reason before re-running |

**Orphaned tasks.** A task's status is written by the worker executing it. If
that worker dies — pod evicted, node drained, out of memory — nothing writes the
terminal status and the task shows as active forever. Report them with:

```
GET  /api/maintenance/stale-tasks
POST /api/maintenance/stale-tasks/reap
```

The `GET` reports only. The `POST` marks each orphan `cancelled` with the
reason recorded on it, and defaults to `dry_run=true` so the destructive form
has to be asked for explicitly.

`cancelled` rather than `failed` for a specific reason: `failed` is not a status
the task board accepts, and anything it does not recognise it maps back to
`backlog` — so marking an orphan `failed` would return it to the queue looking
like fresh work. `cancelled` leaves the active board and lands in the cockpit's
failed column, without claiming the task succeeded.

Tasks awaiting a human are never reaped, at any age. Neither are tasks in a
status the reaper was not taught about: guessing wrong in that direction
destroys live work, whereas guessing wrong the other way merely leaves an
orphan visible, which is the situation without a reaper at all.

Reaped is terminal, so a task cannot be reaped twice or cycle back round on the
next sweep.

---

## Conventions worth agreeing early

**One issue, one outcome.** A card threads on a correlation key across plan,
build and verify. An issue asking for three unrelated things produces one thread
that cannot cleanly succeed or fail.

**Label deliberately.** The intake label picks the tier, and the tiers behave
differently — `factory:low` builds directly, `factory:hard` plans first. Agree
who may apply which.

**Write the acceptance criteria before the plan, not after.** Criteria written
to match what was built are not criteria, they are a description.

---

## Options reference

| Setting | Options | Default | Unset behaviour |
|---|---|---|---|
| Intake label | `factory:low` / `medium` / `hard` / `parallel` | none | issue ignored |
| Stale threshold | any hours value | 4h | 4h applies |
| Reap mode | `dry_run=true` / `false` | `true` | reports only, changes nothing |

---

## Next

- [Boards and work items]({{ '/guides/boards/' | relative_url }})
- [Testing scenarios]({{ '/guides/testing/' | relative_url }}) — deciding what "verified" means
