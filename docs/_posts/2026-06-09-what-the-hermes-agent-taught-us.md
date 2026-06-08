---
layout: post
title: "What the Hermes agent taught us"
subtitle: "We read Nous Research's open-source agent end to end. Here's what we're stealing — and what reading other people's code does for a project like ours."
date: 2026-06-09
author: Olaf Freund
---

One of the quiet superpowers of building in the open is that everyone else is too. When
[Nous Research](https://nousresearch.com) put [**Hermes Agent**](https://github.com/NousResearch/hermes-agent)
out under an MIT license, they didn't just ship a product — they shipped a fully worked
answer to a hard question: *how do you make a long-running, tool-using agent that doesn't
fall over?* We sat down and read it. Not skimmed the README — read the code. This post is
the honest write-up of what we found, what we're adopting into the Factory suite, and where
we deliberately part ways.

We have no affiliation with Nous. We're just grateful the code was there to learn from, and
this is us paying that forward by being specific about what we took and why.

## Two very different animals

It's worth being clear about shape up front, because it changes what's worth borrowing.

**Hermes is one brilliant generalist.** A single self-improving agent that lives wherever you
do — terminal, Telegram, Discord — keeps a long conversation, writes its own skills from
experience, curates its own memory, and can run on a $5 VPS or hibernate serverless when
idle. It's a *companion*.

**Factory is a governed assembly line.** Four products — PFactory plans, AIFactory builds,
TFactory verifies, CFactory watches — each useful alone, each handing one unit of work to the
next along the PARR pipeline, with human approval gates and signed contracts between stages.
It's a *factory*.

So we weren't shopping for architecture. We were shopping for **mechanics** — the hard-won
runtime details that keep an agent honest over a long, messy task. And Hermes has those in
abundance.

> A caveat in the spirit of honesty: the repo is large and partly refactored into an `agent/`
> package, so a couple of the exact file paths below may have moved by the time you read this.
> The *patterns* are what matter, and those we verified against real code.

## What we're taking

### 1. Stop the agent from spinning

The failure mode everyone who builds agents knows: the model retries the same broken edit,
or re-reads the same file, *looking* busy while making zero progress, until some hard cap
finally trips. Hermes has a clean answer in `agent/tool_guardrails.py`: a
`ToolCallGuardrailController` that fingerprints every call as a `ToolCallSignature`
(tool name + a hash of its arguments) and runs three blunt, effective policies —

- block an *identical failing call* after 5 tries,
- halt when the *same tool* fails 8 times in a turn,
- block a read-only call that returns the *same result* 5 times in a row (the no-progress tell).

We loved this because it complements work we'd *just* finished. Our test→fix handback loop
already has a bounded retry and "assertion pinning" so a coder agent can't quietly weaken a
failing test instead of fixing the code. But pinning stops *test drift*; it doesn't stop
*spinning*. A no-progress detector is the missing half. It's now
[AIFactory#474](https://github.com/olafkfreund/AIFactory/issues/474), and when it halts, the
reason rides out on our completion event so CFactory's cockpit can tell you *why* a work item
stalled — not just that it did.

### 2. Compress context before you hit the wall, not after

Long build runs accumulate conversation and tool output until the context window fills and
things degrade. Hermes' `ContextCompressor` (`agent/context_compressor.py`) does the grown-up
thing: it compresses at **50% of the window**, not at the cliff edge. It protects the system
prompt, the first few messages, and a ~20K-token recent tail, then summarizes the middle into
a **structured nine-section template** — Active Task, Goal, Completed Actions, Pending Asks,
and so on. Two details we particularly admired: a cheap pre-pass that dedups stale tool
outputs by content hash, and an **anti-thrash guard** that simply stops compressing if the
last two passes each saved less than 10%. And if the summarizer model is down, it falls back
to a deterministic, hand-written summary rather than failing the turn.

The bonus realization: that structured "Active Task" summary is *exactly* what a CFactory
work-item panel wants to show a human. The thing you build to save tokens is also the thing
you build to explain the run. That's [AIFactory#475](https://github.com/olafkfreund/AIFactory/issues/475).

### 3. Checkpoint before you cut

Hermes snapshots before every destructive action — `ensure_checkpoint(work_dir, "before …")`
runs ahead of any `write_file`, `patch`, or destructive shell command, and it keeps a per-turn
ledger of what actually changed so it can verify, at the end of the turn, that the mutations
match what the agent *said* it did. AIFactory already isolates work in git worktrees, which is
the big rock. This is the gravel: per-mutation checkpoints and a claimed-vs-actual check give
us cheap rollback and cleaner evidence to hand TFactory.
[AIFactory#476](https://github.com/olafkfreund/AIFactory/issues/476).

### 4. Test the way CI tests — or don't believe the green

This one isn't code, it's a *rule*, and it's the best line in their `AGENTS.md`: tests run
only through one canonical runner, **never raw pytest**, because the runner unsets ambient
credentials, forces UTC, and enforces isolation to match CI. Run pytest by hand and you get a
green that lies. They go further: before trusting a module, E2E test the *real* import chain —
not mocks — against a throwaway home directory.

For a product whose entire reason to exist is *trustworthy* verdicts, this lands hard.
TFactory already grades inside a locked-down sandbox (`--network=none --read-only`); we're
extending that to full environment parity and adding a signal that flags suites which only
pass because they mocked out the very thing under test.
[TFactory#302](https://github.com/olafkfreund/TFactory/issues/302).

### 5. The idea we're still chewing on: verified trajectories

Hermes records every run as a **trajectory** — ShareGPT-format JSONL, success and failure
files kept separately — explicitly to train the next generation of tool-calling models. That
sparked the most interesting thought of the whole exercise. Factory produces something a
single agent structurally cannot: **governed, verified** trajectories. Every PARR run threads
`plan → code → branch/PR → tests → verdict`, gated by human approval and labelled by an
independent five-signal grade. That's an unusually high-signal dataset — and we have it as a
byproduct of just doing the work. We've opened [Factory#30](https://github.com/olafkfreund/Factory/issues/30)
to figure out capture, privacy, and whether the first use is simply a regression harness for
our own agents before anything else.

## Where we part ways (on purpose)

Reading Hermes also sharpened what we *won't* copy, which is just as useful:

- **We won't collapse into one mega-agent.** The separation of concerns — and the human
  approval gate in front of work — is the point of Factory, not an inconvenience to optimize
  away.
- **We keep our contracts.** Hermes is a single process, so it has no inter-service contract
  to maintain. Our [RFC-0001 completion-event envelope](/rfc/correlation-key/) and
  [RFC-0002 signed Task Contract](/rfc/task-contract/), threaded by a shared correlation key,
  are a genuine strength precisely because we *are* distributed.
- **We keep verification independent.** Hermes self-checks; TFactory grades from the outside.
  For the trust-and-governance layer we're trying to be, an external verdict beats a
  self-assessment.

And the honest admission: the one place Hermes is clearly ahead of us is the **learning loop**.
It gets better with use — skills self-improve, memory deepens. We don't, yet. Naming that gap
out loud is half the value of reading someone else's code.

## The real takeaway

The specific patterns are great, and they're all tracked under
[Factory#31](https://github.com/olafkfreund/Factory/issues/31) if you want to follow along.
But the meta-point is the one we keep relearning: **open source makes everyone better because
we get to read each other's hard-won answers.** Nous solved the "agent that doesn't fall over"
problem in a hundred small, careful ways, and because they did it in the open, we got a year
of lessons in an afternoon. The least we can do is be specific about what we learned, credit
where it came from, and put our own work back out in the same spirit.

If you're building in this space too — read our code. Tell us what's wrong with it. That's how
this is supposed to work.

*Thanks to the [Nous Research](https://nousresearch.com) team for shipping Hermes Agent under
an open license. Go read it: [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).*
