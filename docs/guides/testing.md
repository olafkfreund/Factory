---
layout: default
title: "Testing scenarios: deciding what verified means"
permalink: /guides/testing/
---

# Testing scenarios

**User story.** As a tech lead, I want to choose how strongly a change is
verified and to trust the answer, so that "passed" means something I would stake
a release on.

---

## The failure mode this is all built against

A gate that reports success without checking anything is worse than no gate. It
is not neutral: it actively converts "we do not know" into "we are fine", and
teams reasonably stop reading a signal that is always green.

Two real examples from this codebase, both of which passed for months:

**A probe that measured a login page.** A seam check requested a service's API,
was redirected to the identity provider, followed the redirect, and recorded the
login page's `200` as a pass. Its predicate accepted anything under 500 that was
not a 404 — which a `302` and a `401` both satisfy.

**A gate that crashed before its first request.** A post-deploy check died on a
malformed URL and the caller discarded the exit code with `|| true` inside a job
already marked `continue-on-error`. Either mechanism alone would have kept a
failure from blocking the deploy; together they made the probe incapable of
reporting anything.

Both are why the guidance below insists on evidence rather than colour.

---

## Verification levels

Pick the level per project. Higher levels cost more time and catch more.

| Level | Asserts | Use when |
|---|---|---|
| Build | it compiles and unit tests pass | prototypes |
| Acceptance | the acceptance criteria hold | most work |
| Regression | plus no previously passing test broke | shared services |
| Visual | plus rendered UI matches accepted baselines | user-facing |

Regression and visual baselines are shipped and have live endpoints:

```
GET  /api/projects/{project_id}/regression
POST /api/projects/{project_id}/regression/run
GET  /api/tfactory/tasks/{spec_id}/visual-baselines
POST /api/tfactory/tasks/{spec_id}/visual-baselines/{target}/{snapshot}/accept
```

Accepting a visual baseline is a human act by design. A tool that accepts its
own baselines verifies nothing.

---

## Coverage on a pull request

```
GET /api/coverage?repo=<owner/name>&sha=<commit>
```

Keyed on **commit**, not pull request — a PR's head SHA is what has coverage,
and the caller already knows it.

Absent coverage returns `200` with `coverage_pct: null` and a stated reason:

```json
{"coverage_pct": null,
 "reason": "no regression run has recorded coverage for 91741f4d (PR #852);
            checked project(s): olafkfreund-TFactory"}
```

**Not a 404.** A 404 is what a missing endpoint looks like, and for months a
missing endpoint was indistinguishable from missing data — the caller read both
as "N/A". Being able to tell "no coverage yet" from "no such endpoint" is the
whole point of that design.

---

## Checking that a gate actually ran

The habit worth building. In any CI interface, a skipped check and a passing
check look alike.

**Read step conclusions, not job conclusions.** A job is green if its steps were
skipped.

**Look for the check's own output.** A gate that prints what it found is one you
can audit:

```
TechDocs inputs are up to date.
16 passed, 1 warning in 336.31s
```

"16 passed" tells you it ran. A green tick does not.

**Watch the counts change.** When a new module came under a drift gate, the
gate's own report went from "4 vendored modules" to 5. That increment is the
evidence it is being compared rather than silently skipped.

---

## Mutation-checking your own gates

Before trusting a gate you added, break the thing it watches and confirm it
complains.

```bash
# gate is green
check.py --service x --root ./svc      # exit 0

# break exactly what it should catch
printf '\n# drift\n' >> ./svc/vendored_file.py
check.py --service x --root ./svc      # expect exit 1, naming the file

# restore
git checkout -- ./svc/vendored_file.py
check.py --service x --root ./svc      # exit 0
```

If step two does not fail, the gate is decoration. This takes two minutes and is
the difference between a check and a comfort blanket.

---

## Options reference

| Setting | Options | Default | Unset behaviour |
|---|---|---|---|
| Coverage lookup | `repo` + `sha`, optional `pr`, `project_id` | — | 200 with a reason, never 404 |
| Regression run | per project | not run | no trend recorded |
| Visual baseline | accept per snapshot | not accepted | differences reported, not blocking |

---

## Next

- [Enterprise scale]({{ '/guides/enterprise-scale/' | relative_url }}) — audit obligations
- [Working as a team]({{ '/guides/teams/' | relative_url }}) — who reviews what
