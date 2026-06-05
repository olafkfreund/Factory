# Architecture

TFactory is an agent pipeline that generates, runs and grades tests in a sandbox.

## Pipeline

```
branch + acceptance criteria
   ─▶ planner ─▶ gen-functional ─▶ executor ─▶ evaluator ─▶ triager
                  (write tests)    (Docker     (5-signal    (report +
                                    sandbox)    verdict)      handback)
```

| Stage | What it does |
|---|---|
| **Planner** | Decide what to test from the branch + acceptance criteria. |
| **Gen-functional** | Generate test code across the relevant lanes. |
| **Executor** | Run the suite in an isolated **Docker sandbox**. |
| **Evaluator** | Grade with the 5-signal verdict (below). |
| **Triager** | Post a triage report to the PR; route a handback on failure. |

## Lanes

`unit` · `browser` · `api` · `integration` · `mutation` — a generated test belongs
to one modality lane.

## The 5-signal verdict

| Signal | Meaning |
|---|---|
| **Coverage delta** | Net coverage the generated tests add. |
| **Stability** | Agreement across re-runs (flake resistance). |
| **Mutation** | Fraction of injected mutants the suite kills. |
| **Lint** | Test-code quality gate. |
| **Semantic relevance** | How well tests map to the acceptance criteria. |

## Outputs & handoff

On completion TFactory emits an RFC-0001 event (`triaged` / `triaged_empty` /
`triager_failed` → `test`). When tests fail it POSTs the failing set to
**AIFactory**'s `/api/tasks/{id}/qa-fix` — a bounded, closed correction loop. See
[API & Contracts](api.md).
