# Demo Runbook: Animated Cockpit Execution DAG (Hero Shot)

Status: Runbook ready. Hero still + looping GIF captured 2026-07-30 and committed
(see [Captured assets](#captured-assets)); two of the four shots are still open on
known product gaps (see [What is not captured yet](#what-is-not-captured-yet)).
Tracks: Factory#244. This is the HERO SHOT of the demo set: the single most
visually striking view of the whole Factory.

## The point (one line)

You can watch the factory think and work in real time: the task graph lights up
node by node as plan, then build, then verify runs, so autonomy is something you
observe rather than take on faith.

## What is real here (ground truth)

The CFactory cockpit renders a live, animated execution DAG of a PARR run. As a
run progresses, the task/subtask graph lights up stage by stage
(plan -> build -> verify), driven by real backend data, not a canned animation.

- Feature: live execution diagrams, shipped 2026-06-14 (CFactory #94), with
  plan-stage live status added in #95. All three PARR stages render.
- Where it lives: CFactory task-detail modal (`TaskDetail.tsx`), renderer in
  `TaskFlow.tsx` with pure layout/classification in `taskFlow.ts`. Hand-rolled
  SVG plus framer-motion, no graph library (cockpit ethos).
- Data contract: `GET /api/workitems/{key}/process` returns
  `graph: { stage: "plan"|"code"|"test", nodes: [{ id, label, kind, status,
  started_at, completed_at, deps: [ids] }] }`, built in `cfactory/task_process.py`.
  It prefers the furthest-along stage (test -> code -> plan).
- Node states come straight from the run: done shows green with a robot stamp,
  active pulses cyan with a live mm:ss timer, failed shakes red, stalled pulses
  amber, and the "next" edges march toward the node about to run.
- Design doc: `docs/plans/2026-06-14-live-execution-diagrams.md` (status: shipped v1).

Because the graph is backed by the process contract and the producers
(PFactory epic children, AIFactory subtasks, TFactory lane-tagged subtasks), the
handback loop on a verification failure is visible too: the test stage shows the
failing lane red, and when the build re-runs the code graph reactivates.

## Setup

Goal: have one PARR run in flight (or replayable) so the DAG has live state to
show, ideally captured across a stage transition.

1. Pick a project small enough to move through all three stages within a short
   window but real enough to have several subtasks (a multi-file service, so the
   code graph has more than one node and the test graph fans out into lanes).
2. Kick off a PARR run through the factory (PFactory -> AIFactory -> TFactory).
   See the through-factory run procedure; do not drive services directly.
3. Open the CFactory cockpit, go to the task list, and open the work item's
   task-detail modal. This is the view that renders the DAG.
4. Confirm the modal is pulling live data: the active node shows a running
   mm:ss timer and the process contract responds at
   `GET /api/workitems/{key}/process`.
5. For the cleanest hero shot, aim to capture around a stage boundary, for
   example the moment the plan graph completes and the code graph takes over, or
   a verify failure driving a handback. If timing live is hard, do a dry capture
   run first to learn the pacing, then record the real one.

## Shot list (hero capture)

Frame the task-detail modal so the DAG fills the shot. The hero is the graph
itself, not the surrounding chrome.

1. Cold open on the DAG with the plan stage active: plan nodes present, one node
   pulsing cyan with its live timer, "next" edges marching to the following node.
2. Plan completes: nodes flip to green with the robot stamp in sequence. Hold a
   beat on the fully-green plan graph.
3. Stage handover: the view switches to the code (build) graph. Build subtasks
   appear as nodes with dependency edges; watch them go queued -> running ->
   passed as AIFactory works.
4. Verify stage: the test graph renders the lane pipeline
   (unit -> browser -> api -> integration -> mutation). Lanes light up as they run.
5. The money shot (choose one as the hero freeze):
   - Clean run: the full graph green end to end, robot stamps across all three
     stages, one frame that says "the machine did all of this."
   - Handback loop: a verify lane goes red and shakes, the run hands back, the
     code graph reactivates (cyan) to fix it, then verify re-runs green. This is
     the strongest single sequence because it shows autonomy plus self-correction.

Node-state legend to make visible during narration:
- queued: dim/idle
- running: cyan pulse with mm:ss timer
- passed/done: green with robot stamp
- rejected/failed: red shake
- stalled: amber pulse

### Framing and zoom notes

- Record at a fixed window size; do not resize mid-take (layout is a wave-column
  algorithm and will re-lay-out on resize).
- Zoom so the active node and its immediate neighbours are large enough that the
  color change and the timer are legible at thumbnail size. Wide plans may not
  fit; if so, frame on the active region rather than the whole graph. (Zoom and
  abstraction levels for very large plans are a deferred enhancement, so favor a
  moderate-size run for the hero.)
- Keep the cursor still or off-frame during state transitions. The animation is
  the subject; movement competes with it.
- Prefer a dark background (gruvbox palette) so the cyan/green/red pops.
- Let each transition breathe. Cut on completed animations, not mid-pulse.

## Narration

- "This is one job moving through the factory. Every box is a real unit of work."
- "Right now it is planning. That cyan node is running this second, and that
  timer is real elapsed time."
- "Plan is done. Green means passed, and the stamp means a machine did it, not a
  person."
- "Now it is building. Each of these is a subtask the coder is writing, in
  dependency order."
- "Verification. These lanes are the tests: unit, browser, api, integration,
  mutation."
- (Clean) "Green all the way through. Nobody touched it."
- (Handback) "That lane failed. Watch: the job hands itself back, the build
  reopens to fix it, and verification runs again, this time green. That is the
  factory correcting itself, in the open."

## Existing assets vs fresh capture

Existing stills in `docs/assets/screenshots/cfactory` (mission-control.png,
running-tasks.png, pipeline.png) and the `docs/assets/screenshots/tour` set are
static frames and useful for context and thumbnails, but they cannot carry this
demo. The hero shot IS the motion: static frames show a graph but not the thing
that makes it a wow, the lighting-up.

This needs a fresh, clean recording. Reasons:
- The value is the animation across stage transitions, which no existing asset
  captures.
- The handback loop is the strongest sequence and must be captured live.
- Framing and pacing matter (see notes), so a purpose-shot take beats reusing
  incidental captures.

Capture a short screen recording of the task-detail modal, then pull one or two
hero freeze-frames from it for stills use.

## Captured assets

Captured 2026-07-30 from the live cockpit (`cfactory-frontend:sha-285a2e1`,
matching CFactory `main`), driving a real PARR run end to end: a plan ingested and
governed by PFactory, emitted as GitHub epic olafkfreund/aifactory-demo#451 with
ten child issues, then built by AIFactory.

| Asset | Shows |
| --- | --- |
| `docs/assets/screenshots/cfactory/execution-dag.png` | The landing-page hero. A finished run's (#432) code graph: dependency fan-in into a serial chain, every node green and stamped, `stage complete`, with the plan/code stage switcher and the Plan · Code · Test header. |
| `docs/assets/screenshots/cfactory/execution-dag.gif` | Looping time-lapse of work item #451's build graph: ten subtasks queued, then all ten complete and stamped. Placed in the CFactory section rather than at the top, because the node labels visibly degrade from the acceptance criteria to `Subtask 1..10` at the moment the build lands (AIFactory#1110) — real, but it reads as a glitch in a hero slot. |
| `docs/assets/screenshots/cfactory/pipeline-board.png` | Shot 3 — the three-column plan/code/test board with the live filter chips (All / Running / In review / Queued / Failed / Finished). |

How they were captured (repeatable): port-forward the frontend
(`kubectl --context factory -n factory port-forward svc/cfactory-frontend 3110:80`)
so the SPA self-authenticates through nginx, then drive it with Playwright against
the system's Chrome. Clip every frame to a **fixed** box (modal header down through
a full-height `.tf-canvas`, which is capped at 420px) so the PNGs are identical in
size and `ffmpeg` can stitch them straight into a GIF. Note that the cockpit's
`fit` control only fits the graph's *width*: a ten-node column only fits
vertically at ~30% zoom, where the labels are unreadable, so frame on the graph at
100% instead of shrinking it.

## What is not captured yet

Three things the shot list asks for could not be captured honestly, each blocked on
a real product gap rather than on the capture technique. They are listed here
rather than faked, and each has an issue.

- **Shot 1's live mid-build state (active node, cyan pulse, running mm:ss timer).**
  AIFactory publishes no per-subtask progress on the trusted-plan path:
  `executionProgress` stays `null` and every subtask stays `pending` for the whole
  build, then all of them flip to `completed` at once. So the states that make the
  diagram *live* never occur — AIFactory#1110. The GIF therefore time-lapses the
  real transition it does produce (all-queued to all-complete) rather than a
  node-by-node walk.
- **Shot 2, a failure state (node shakes red).** No run in the window produced a
  failed DAG node, and a failure must never be hand-set. Still open.
- **Shot 4's cost-by-task bar chart.** Mission Control's count-up stats are live
  and real, but `USAGE BY TASK`, `TOKENS` and `AVG LATENCY` are empty because no
  upstream publishes task usage — CFactory#257. Committing a shot of an empty panel
  would sell the opposite of the point, so it is not included.

Two further defects hit during the capture, both fixed or worked around at the
time and worth knowing about before the next take:

- Dispatched Job pods carry `app=<service>`, which enrols them in that service's
  API Service endpoints, so roughly two thirds of in-cluster calls to AIFactory
  fail while builds run — Factory#458. Symptom while filming: the cockpit's DAG
  flapped between the plan and code stage on alternating polls.
- CFactory treats an unreachable upstream as "that stage does not exist" and
  silently downgrades the diagram to an earlier stage, then latches there — so a
  running build renders as a finished plan stage, with the stage switcher gone —
  CFactory#249.

## Proof takeaway

A black-box tool asks you to trust a "done." This view shows the work:
observable autonomy (you watch each unit run and pass) plus governance you can
see (which stage, which lane, what passed, what failed, and the self-correcting
handback when it does). The DAG is the argument: the factory is not a promise on
a slide, it is a process you can watch execute and verify itself.
