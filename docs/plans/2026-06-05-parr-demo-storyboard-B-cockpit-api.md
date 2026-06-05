# Screencast B — Cockpit + API (Act → Reflect → Review)

**Runtime target:** ~4–5 min · **Audience:** developers (mechanics) + customers (autonomy story)
**On screen:** CFactory cockpit (`http://localhost:3110`) split with a terminal (asciinema) · **Capture:** asciinema cast + cockpit GIFs into `docs/assets/screenshots/demo/`
**Correlation key:** epic issue **#1** threads everything below.

| # | Scene | On-screen action | Narration (script) | Duration |
|---|-------|------------------|--------------------|----------|
| 1 | The cockpit | Open CFactory cockpit; the WorkItem for #1 already shows the PFactory "plan" stage green | "This is CFactory — the control tower. One WorkItem per unit of work, keyed by the GitHub issue. PFactory's already reported in: plan, done." | 0:25 |
| 2 | Kick off Act | Terminal: `POST /api/projects` then `POST /api/tasks` + `/start` against AIFactory `:3101` | "We hand the governed issue to AIFactory. It clones the repo into an isolated worktree and runs planner → coder → QA." | 0:30 |
| 3 | Watch the build | Cockpit timeline updates as AIFactory streams progress; show `GET /api/tasks/{id}/status` | "No black box — AIFactory streams its build. The cockpit threads it onto the same WorkItem: plan → code." | 0:40 |
| 4 | The PR | AIFactory opens a PR on `olafkfreund/factory-demo-api-gateway`; show the diff (proxy routing, rate-limiter, `/health/upstreams`) | "Minutes later: a pull request. Config-driven routing, per-client rate limiting, upstream health — built from the plan." | 0:30 |
| 5 | Reflect (TFactory) | Terminal: create + run a TFactory spec `:3102`; show the 5-signal verdict (coverage, stability, mutation, lint, semantic) | "TFactory doesn't trust a green bar. It generates tests and grades them on five signals — coverage, stability, mutation score, lint, semantic relevance." | 0:35 |
| 6 | **Handback loop** | A test fails: the strict `Retry-After` AC. TFactory posts triage → handback to AIFactory `qa-fix` | "Here's the payoff. The 429 works but the `Retry-After` header is missing — TFactory fails it and routes a handback to AIFactory automatically." | 0:35 |
| 7 | Self-correction | AIFactory applies the bounded fix; TFactory re-runs → green | "AIFactory fixes exactly that, TFactory re-runs, and now it's green. A closed, autonomous correction loop — no human in the inner loop." | 0:30 |
| 8 | Review & spend | Cockpit shows WorkItem #1 fully threaded plan→code→PR→tests, all green; `GET /api/usage` shows aggregated tokens/cost | "Back in the cockpit: one WorkItem, fully threaded, all green — with the total spend aggregated across all four services. Idea to verified change, governed end to end." | 0:30 |

**Capture notes**
- Record the terminal with asciinema (`asciinema rec demo-B.cast`) for crisp, embeddable playback.
- The handback (scenes 6–7) is the money shot — seed it via the strict `Retry-After` acceptance criterion in the brief so it reliably fails the first pass, then re-passes.
- Keep the cockpit (`:3110`) as the persistent left pane; the terminal/PR/TFactory views rotate on the right.
