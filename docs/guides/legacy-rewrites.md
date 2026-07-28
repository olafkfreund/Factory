---
layout: default
title: "Legacy rewrites"
permalink: /guides/legacy-rewrites/
---

# Legacy rewrites

**User story.** As a developer inheriting a system nobody remembers writing, I
want the factory to read the code before it plans, so that changes fit what is
actually there rather than what a specification imagines.

---

## What makes brownfield different

Greenfield planning can start from the requirement. Brownfield cannot: the
constraint is the existing code, and a plan that ignores it produces a change
that does not apply.

Factory reads the repository during planning. Plans reference real modules,
real call sites and real conventions, rather than inventing a structure.

Two consequences worth knowing before you start:

- **The plan will be shaped by what exists**, including the parts you dislike.
  That is correct behaviour. Changing the shape is a separate, deliberate act.
- **Language and framework are taken from the repository**, not assumed.

---

## Turn by turn

**1. Register the existing repository as a project.** Point at the real
checkout. Nothing is modified by registration.

**2. Establish what currently passes.**

Before changing anything, record the baseline:

```bash
curl -X POST -H "Authorization: Bearer $FACTORY_TOKEN" \
  https://tfactory.<your-domain>/api/projects/{project_id}/regression/run
```

**Checkpoint.** A regression record exists. If the suite is already red, you
have learned something important before spending any effort on the change.

**This step is the one people skip and regret.** Without a baseline, the first
verification cannot distinguish "my change broke this" from "this was already
broken".

**3. Write acceptance criteria in terms of observable behaviour.**

Legacy systems rarely have a specification to point at, so describe what must
remain true:

```markdown
## Acceptance Criteria
- AC#1: POST /orders still accepts the v1 payload shape
- AC#2: existing callers receive the same status codes
- AC#3: the new field is optional and absent by default
```

Criterion 3 is the characteristic brownfield criterion: it constrains the
change, not just the feature.

**4. Plan and read the plan properly.** This is the highest-value review in a
rewrite. The plan tells you what the machine believes about your codebase; a
wrong belief here is much cheaper to correct now than after the change.

**5. Build, then verify against the baseline** from step 2. Regression is the
level that matters here — acceptance alone tells you the new thing works, not
that the old things still do.

---

## Strangler-style incremental work

For a rewrite too large for one change, the pattern that works is many small
threaded changes rather than one big one:

- one issue per seam you are replacing
- acceptance criteria that assert the old path still works
- regression verification on every step

Each card threads on its own correlation key, so progress is visible per seam
rather than as a single opaque effort.

---

## Things that bite

**Tests that were never run.** A repository can carry a suite that has not
passed in years. Establishing the baseline first turns that from a mid-change
surprise into a known starting condition.

**Assumed language.** If a repository is polyglot, be explicit in the spec about
which component you mean.

**Coverage that does not exist yet.** A coverage lookup for a commit with no
recorded run returns `null` and says so, rather than reporting a stale figure
from an earlier commit. Treat null as "not measured", never as "zero".

---

## Options reference

| Setting | Options | Default | Unset behaviour |
|---|---|---|---|
| Verification level | build / acceptance / regression | acceptance | new behaviour checked, old behaviour not |
| Baseline | recorded per project | none | first run has nothing to compare against |

---

## Next

- [Testing scenarios]({{ '/guides/testing/' | relative_url }})
- [Enterprise scale]({{ '/guides/enterprise-scale/' | relative_url }})
