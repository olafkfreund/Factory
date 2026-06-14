---
title: Live execution diagrams — one map per unit of work, across PARR
status: shipped (v1 — all three stages)
created: 2026-06-14
---

# Live execution diagrams (PFactory plan DAG → AIFactory build → TFactory verify)

## Shipped v1 (2026-06-14) — all three stages live

The animated DAG is in the CFactory task-detail modal, rendering whichever stage
is furthest along (**test → code → plan**), via the shared `graph` contract on
`GET /api/workitems/{key}/process`. Hand-rolled SVG edges + framer-motion node
cards, gruvbox palette — no graph lib (matches the cockpit's no-dependency ethos).

- **Frontend (CFactory):** `TaskFlow.tsx` (renderer), `taskFlow.ts` (pure
  layout/classification/timers, wave-column DAG), `FlowNode`/`ProcessGraph` types
  in `api.ts`, `useNow` in `motion.ts`, CSS in `index.css`. Done = green + robot
  stamp; active = cyan pulse; failed = red shake; stalled = amber pulse; "next"
  edges march; live `mm:ss` per node. Wired into `TaskDetail.tsx`.
- **Code stage:** AIFactory `/api/tasks/{id}` subtasks now expose
  `depends_on/started_at/completed_at/service`; CFactory `task_process._build_code_graph`
  turns them into `{stage:"code"}` nodes+edges.
- **Plan stage:** CFactory fetches the PFactory session (`epic.children` already
  exposed via `model_dump`) → `_build_plan_graph` → `{stage:"plan"}` (kinds +
  dependency edges). Fallback when no code task yet.
- **Test stage:** TFactory `/api/tasks/{id}` subtasks now expose
  `lane/started_at/completed_at`; CFactory `_build_test_graph` aggregates them into
  a **lane pipeline** (unit→browser→api→integration→mutation) with spine edges,
  per-lane rolled-up status (worst-first) + timing. Subtask `stuck` → stalled.
- **Tests:** CFactory backend 255 pass (9 in `test_task_process.py`, incl. plan
  fallback + test-stage + furthest-stage-wins). Frontend `tsc`+`vite build` green.

**Deferred (no rework cost — purely additive):**
- **Zoom / abstraction levels** (collapse-expand for large plans) — the one good
  idea borrowed from CodeBoarding research; presentation layer over the same
  `graph` contract.
- **Per-node live status on the plan stage** (children currently render as the
  static planned shape) + **TFactory liveness-watchdog** task-level `stalled`
  signal (today only subtask-level `stuck` drives the amber state).

## Refinement v2 (agreed scope — 2026-06-14)

Sharpened requirements from the operator. This section supersedes the placement +
rendering choices below where they differ.

**Where it lives:** NOT on the CFactory page/cards. Only when you **click a plan /
coding / testing task** do you open its diagram. Two modes in that view:
- **Live** while the task runs — nodes light up, edges animate, timers tick.
- **Summary** when the task is done — the final graph with each node's status and
  the time it took.

**The animations are the point (must feel alive):**
- **Done:** the node fills **green** with a small **robot animation** (the robot
  "stamps"/pops in — reuse the cockpit's `IconRobot`).
- **Active:** the node pulses (a worker is on it).
- **What's next:** the **edge** from a just-finished node to the next eligible
  node(s) animates — a flowing/travelling dash — so "what runs next" is unmistakable.
- **Failed:** the node flashes **red** and shakes.
- **Stuck/stalled:** the node goes **amber** with a slow stalled pulse (driven by
  TFactory's explicit `status="stalled"`/`stall_idle_seconds`, and AIFactory's
  derived "in_progress longer than N min").

**Time per node (new, required):** every node shows **time spent** — `mm:ss`,
**live-ticking** while active (`now − started_at`), **frozen** on done
(`completed_at − started_at`), with a total for the stage. This is the "how much
time did each subtask use" view.

**Renderer DECIDED (2026-06-14): hand-rolled SVG + framer-motion.** The operator's
constraint is "keep the existing branding/design language." The cockpit is already
hand-rolled SVG with NO chart/diagram library (e.g. `LiveTaskStamp`'s sparkline),
and framer-motion is already a dependency. So a bespoke SVG diagram component is the
choice that genuinely matches the brand — full control of the robot stamp, flowing
edges, pulses, and live timers, no heavy new dep, gruvbox/mono native. Layout is
trivial because the DAG is already **wave-structured** (the contract's `phases`):
each wave = a column (x), subtasks in a wave = stacked rows (y), edges = lines from
`depends_on`. No graph-layout engine needed. Mermaid is NOT used (it can't animate);
a static "summary" is just the same SVG frozen at the final state.
**Scope DECIDED: all three stages (plan / code / test).**

(Superseded earlier note — Mermaid is excellent for a *static* picture
but its output is a frozen SVG — robot pops, flowing edges, per-node live timers,
and pulses are awkward to bolt on. For the live, animated vision I recommend
**React Flow (`@xyflow/react`)** as the live renderer: it is purpose-built for
animated node/edge DAGs in React — custom node components (box = status colour +
robot + live timer), built-in **animated edges** (the flowing dash), and auto-layout
(dagre/ELK, left→right by wave). We keep **Mermaid for the "summary when done"** as
a lightweight static snapshot / exportable image. So: React Flow = live; Mermaid =
done-summary/export. (Alternative: hand-rolled SVG + framer-motion — full control,
more work. React Flow gets us 90% with far less.)

**Data we need to surface (the only backend work — data already exists on disk):**
- AIFactory `/api/tasks/{id}` `subtasks[]` → add `depends_on`, `kind`, `started_at`,
  `completed_at` (the `Subtask` model + `task_to_dict()` omit them today;
  `implementation_plan.json` already stores them via `Subtask.start()/.complete()`).
- TFactory → expose the lane/step graph + per-lane `started_at/completed_at`
  (derivable from `_write_status_patch` `updated_at` transitions) + the `stalled`
  signal.
- CFactory `ProcessDetail` (`/api/workitems/{key}/process`) → carry the graph
  (`nodes[] {id,label,kind,deps,status,started_at,completed_at}`) so the React Flow
  view builds directly from it. No mermaid needed for the live view — the structure
  comes straight from the subtasks + `depends_on`.

**Placement detail:** the diagram is the centerpiece of `TaskDetail.tsx` (the
click-through modal), one per stage (plan / code / test) — the existing
`/process` 4s poll already drives it. **Drop the active-card minimap** (operator
explicitly does not want it on the page).

---

## The idea in one line

The plan is *already* a dependency graph. Render it once as a Mermaid diagram, then
**light its nodes up in real time** as the unit of work flows plan → code → test —
so the cockpit shows, at a glance, *where we are, what's done, what's blocked, and
exactly where something failed*. One map, three live overlays, one correlation key.

This is not decoration. The value is **legibility under automation**: when an
autonomous pipeline runs unattended, a colored node tells you in one second what a
log scroll tells you in five minutes.

## Why this is cheap to build (the favorable findings)

| Need | Already exists |
|---|---|
| Plan as a DAG (nodes/edges/checks) | `EpicPlan.children` — each `ChildIssue` has `key`, `kind`, `depends_on` (edges), `acceptance_criteria` (checks), `complexity` (`PFactory/apps/backend/plan/decompose/models.py`) |
| Waves / parallelism | the contract's `phases` (topological layers) — `contract_builder.build_phases()` |
| A Mermaid builder | `PFactory/apps/backend/agents/diagrams/mermaid.py` (`MermaidGraph`) — reuse it |
| A clean attach hook | `assemble_contract()` (`plan/emit/contract_emit.py`) — `additionalProperties:true`, add `contract["diagram"]` |
| **Live per-subtask status in CFactory** | `/api/workitems/{key}/process` → `ProcessDetail.subtasks[]` (title+status pending/active/done/failed) **already polled every 4s** in `TaskDetail.tsx` |
| Cockpit theme + cadence | gruvbox CSS vars (`--plan`/`--code`/`--test`/`--green`/`--red`), 4s poll, framer-motion |

What's genuinely missing is small: (1) generate + carry the diagram source to
CFactory; (2) expose TFactory's lane status; (3) a render component + `mermaid`
dep in the frontend.

## Architecture — three layers, one visual language

```
PFactory (structure)         AIFactory (build status)        TFactory (verify status)
  EpicPlan DAG                  subtask status                  lane/step status
  → mermaid source             (already in /process)            (new: lane_progress out)
        │                              │                              │
        └──────────────► contract.diagram ─────────────► CFactory ◄──┘
                                                   render once + recolor nodes live
                                              TaskDetail (full) + task card (minimap)
```

**The key design move:** the Mermaid *source is structural and stable* (the DAG
doesn't change mid-run); the *live status is a separate `{node_id → state}` map*
that updates every 4s. CFactory renders the SVG once, then only swaps CSS classes on
node elements (by id) — no re-layout, smooth, ~free. Node ids == contract subtask
ids so the status map aligns.

### Layer 1 — Generation (PFactory)
- New `plan/emit/diagram.py`: `build_plan_diagram(epic) -> str`. Reuse `MermaidGraph`.
  - Node per `ChildIssue`: id=`key`, label=`title` (truncated), shape/class by `kind`
    (feature/testing/cicd/infra/docs), a `✓N` badge for `len(acceptance_criteria)`.
  - Edges from `depends_on`.
  - Wrap each wave/phase in a `subgraph` (vertical bands = parallel work).
  - `flowchart LR` (left→right reads as time).
- `attach_diagram(contract, epic)` in `assemble_contract()` → `contract["diagram"]`.
  Flows to AIFactory via `/api/tasks/from-plan` (the trusted-plan contract) and is
  the artifact the cockpit renders. Also attach to the RFC-0001 completion event so
  CFactory ingests it (or expose via `/process`, see Layer 3).

### Layer 2 — Status (AIFactory / TFactory)
- **AIFactory: already done.** `ProcessDetail.subtasks[]` carries per-subtask
  `status` (pending/in_progress/done/failed) + `current_subtask` + `overall_percent`.
  The diagram node id = subtask id → direct overlay. We just thread `diagram` through.
- **TFactory: small addition.** Emit (a) a verify-flow diagram (lanes × generate →
  run → triage) and (b) the `lane_progress` map (already tracked internally —
  `task_control.py _MVP_LANES`/`lane_progress`) out to CFactory, so the test stage
  gets the same treatment. The review lane (just shipped) is one more node.

### Layer 3 — Render (CFactory)
- Add `mermaid` to `frontend-web` (lazy-loaded dynamic import — keeps the main
  bundle lean; mermaid is ~heavy).
- New `TaskDiagram.tsx`: props = `{ source: string, statusByNode: Record<id,state> }`.
  - `mermaid.render()` the source ONCE (memoized on source); on each 4s poll, walk
    the SVG and set `class` on each `g.node[id]` from `statusByNode`.
  - Status → gruvbox: pending=`--faint`, active=`--code` (yellow) + pulse, done=
    `--green`, failed=`--red`, blocked=`--muted` dashed.
- Wire into `TaskDetail.tsx` (the click-on-task modal) as the centerpiece, fed by the
  existing `/process` poll. `ProcessDetail` gains an optional `diagram` field
  (`CFactory backend task_process.py`) carrying the mermaid source.
- A compact **minimap** on the `RunningTasksView` task card: the wave-ordered node
  dots colored by state + overall %, glanceable; click → the full map.

## UI / UX (the frontend-design lens — informative first)

- **One language, three stages.** Identical node shapes + status palette across
  plan/build/test so the eye learns it once. The diagram's border takes the stage
  accent (`--plan` purple / `--code` yellow / `--test` green) to say *which factory*.
- **Left→right = time.** Waves are vertical bands; parallel subtasks stack — you
  *see* concurrency. The active node pulses; done nodes are solid green; the next
  eligible (deps satisfied) nodes are outlined so "what's next" is obvious.
- **Nodes carry meaning, not just a name.** `C3 · rate-limiter · ✓2` (id · short
  title · acceptance-criteria count) + a status glyph. Hover/click → a side panel
  with the full acceptance criteria, files touched, and the node's cost/tokens.
  This ties the *checks* (governance) to the *picture*.
- **Failure localization.** A red node + a one-line reason caption ("failed at C3:
  import error") is the single highest-value pixel — it turns "build failed" into
  "this step, this reason."
- **The handback loop, drawn.** When TFactory flags a build and AIFactory re-runs, a
  back-edge appears (test → code) — the PARR loop becomes visible, which is the
  program's core story.
- **A caption + rail, not chart-junk.** Under the diagram: a thin overall-progress
  rail, "current: Coding C3", and counts (`4/8 done · 1 failed · 2 blocked`).
  Framer-motion eases the color transitions so progress *feels* live.

## Value-add (purpose, explicitly)

1. **Situational awareness in 1s** — where the pipeline is, without logs.
2. **Failure localization** — the exact step + reason, not a global "failed".
3. **Concurrency + bottlenecks** — parallel waves and blocked nodes are visible.
4. **The governed loop made legible** — plan→build→verify→handback as one map; the
   acceptance-criteria badges show *what is being checked* at each node.
5. **Through-line for the unit of work** — the same structure carries the RFC-0001
   correlation key visually across all three factories.

## Phasing (incremental, each shippable)

- **P1 — plan map + live build overlay (highest value, smallest diff).** PFactory
  generates `contract.diagram`; thread it into CFactory's `ProcessDetail`; render in
  `TaskDetail` and color from the *existing* `subtasks[]` statuses. Build stage goes
  live immediately. (~1 backend fn + 1 attach + 1 field + 1 React component + dep.)
- **P2 — verify flow.** TFactory emits its lane/step diagram + `lane_progress`;
  CFactory renders the test-stage map (incl. the review lane).
- **P3 — polish.** Active-card minimap, handback back-edge, node→criteria side panel,
  animated transitions, the "next eligible" outline.

## Risks / decisions

- **Render cost:** render the SVG once per source; only swap node classes on poll. Do
  NOT re-`mermaid.render()` every 4s.
- **Bundle size:** lazy-load `TaskDiagram` (dynamic import) so the cockpit's main
  bundle is unchanged for users who never open a task.
- **Node-id contract:** the diagram node ids MUST equal the contract subtask ids
  (`C1`,`C2`,…) — this is the join key for the status overlay. Enforce in the builder.
- **Security:** `mermaid.initialize({ securityLevel: 'strict' })`; the source is
  generated server-side from typed models (no user free-text into node ids).
- **Empty/degenerate plans:** a single-subtask serial build renders one node — fine;
  guard for zero children (no diagram).

## Files (where the work lands)

- PFactory: new `plan/emit/diagram.py`; hook in `plan/emit/contract_emit.py`
  (`assemble_contract`); attach to the completion event in `plan/completion.py`.
- AIFactory: thread `diagram` from the inbound contract onto the build status/event
  (`services/completion.py` / the process surface) — status already exposed.
- TFactory: emit a verify-flow diagram + `lane_progress` on the completion/process
  surface (`agents/triager.py` envelope already carries result counts).
- CFactory: `apps/frontend-web` new `TaskDiagram.tsx` + `mermaid` dep; wire into
  `TaskDetail.tsx`; minimap in `RunningTasksView.tsx`; `diagram` field on
  `ProcessDetail` (`apps/backend/.../task_process.py`).
