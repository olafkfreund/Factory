# Demo Runbook: Animated Cockpit Execution DAG (Hero Shot)

Status: Runbook ready. Recording is a follow-up.
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

## Proof takeaway

A black-box tool asks you to trust a "done." This view shows the work:
observable autonomy (you watch each unit run and pass) plus governance you can
see (which stage, which lane, what passed, what failed, and the self-correcting
handback when it does). The DAG is the argument: the factory is not a promise on
a slide, it is a process you can watch execute and verify itself.
