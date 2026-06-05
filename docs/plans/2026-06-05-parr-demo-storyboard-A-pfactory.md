# Screencast A — PFactory-centric (Plan & Govern)

**Runtime target:** ~3–4 min · **Audience:** customers (value) + developers (mechanics)
**On screen:** PFactory portal (`http://localhost:3115`) + a terminal · **Capture:** GIFs per beat into `docs/assets/screenshots/demo/`
**Real artifacts from the verified run:** repo `olafkfreund/factory-demo-api-gateway`, PFactory session `001-factory-demo-api-gateway-simple-fastapi-gateway`, epic issue **#1** (+ children #2–#9).

| # | Scene | On-screen action | Narration (script) | Duration |
|---|-------|------------------|--------------------|----------|
| 1 | Cold open | Backstage catalog entry for `factory-demo-api-gateway` (already scaffolded) | "Our service already exists — scaffolded from a golden-path Backstage template: FastAPI, uv, CI, a Nix flake, and a catalog entry. We're not here to show Backstage; we're here to show what happens next." | 0:20 |
| 2 | Enter PFactory | Open the PFactory portal, paste the one-paragraph brief with an `## Acceptance Criteria` block | "PFactory turns intent into a *governed* plan. We hand it a plain-English brief and six acceptance criteria — including a strict one: rate-limited requests must return 429 with a correct `Retry-After` header." | 0:30 |
| 3 | Decompose | Show the epic + 8 child issues materialise | "It decomposes the brief into an epic and eight child tasks — one per acceptance criterion, plus testing and CI/CD." | 0:25 |
| 4 | Review gates | Show the four lenses: architecture 1.0, security 1.0, best-practices 1.0, feasibility 1.0 → aggregate **1.0** vs threshold 0.75 | "Every plan runs review gates — architecture, security, best-practices, feasibility — each scored with citations. Ours clears the 0.75 bar." | 0:30 |
| 5 | Governance beat (optional B-roll) | Toggle cloud enrichment on to show a *failing* gate (security 0.6 from live AWS findings) | "And when something's wrong, the gate holds the line — here live cloud enrichment flags real open security groups and blocks approval until a human signs off. That's the point: no plan ships ungoverned." | 0:25 |
| 6 | Human approval | Click approve (approver = olaf@freundcloud.com) → board state `done` | "A human approves — recorded, attributable." | 0:15 |
| 7 | Emit | Emit → terminal/`gh` shows epic **#1** + children #2–#9 created with `handoff:aifactory` labels | "PFactory emits governed GitHub issues. The epic's issue number — #1 — becomes the correlation key that threads the entire pipeline." | 0:25 |
| 8 | Handoff | Highlight the `handoff:aifactory` label on the issues | "Those `handoff:aifactory` labels are the baton. Next stop: AIFactory." → cut to Screencast B | 0:15 |

**Capture notes**
- Pre-create the repo labels before emit (see the `factory-demo` skill) so the emit is clean on camera.
- If demoing the governance beat (scene 5), run it *before* the clean run so the final on-camera state is green.
- Keep a terminal visible for scenes 7–8 to show the real `gh issue list` output.
