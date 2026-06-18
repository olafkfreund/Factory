---
layout: post
title: "Planning that reads your code"
subtitle: "How PFactory stopped guessing — reconnoitring an existing repo to plan real changes, and proving a Python-to-Rust rewrite behaves the same (RFC-0010)"
date: 2026-06-18
author: Olaf Freund
---

A planner that has never read your code is guessing. It can read your spec, enrich it
with live cloud and catalog context, decompose it into governed work — and still hand the
builder a plan that says "modify the service" without knowing a single file that exists.
For a greenfield service that is fine. For a change to code that already exists, it is the
difference between a grounded plan and a hopeful one.

[RFC-0010](/rfc/code-aware-planning/) closes that gap. PFactory now **reads the target
repository** before it plans — and, crucially, reads it *statically*: a shallow read-only
checkout, manifest and AST parsing, an infrastructure scan. It never executes the repo's
code. The one place untrusted code is ever run is TFactory's existing hardened sandbox.
That bright line is what lets planning become code-aware without becoming dangerous.

## Scenario A — "change our EKS Terraform"

A team submits a plan to scale an existing EKS cluster. Before RFC-0010, PFactory would
read the words, guess the language from keywords, and emit a contract with empty file
lists — the builder would then quietly discover the real files at build time, and the
human had approved a plan grounded in nothing.

Now a **reconnaissance** stage runs between detection and decomposition. It clones the
repo read-only, runs the detectors PFactory already had (but never wired into planning),
and adds a static infrastructure probe. For Terraform that means the actual resources and
the files they live in: the `aws_eks_cluster` in `eks.tf`, the `aws_eks_node_group` in
`node_groups.tf`, the modules and providers. The result is a `RepoMap` the plan is built
on.

From there the plan is **delta-aware**. Decomposition matches each acceptance criterion
against the real layout, so a task to raise the node-group size emits
`files_to_modify: ["node_groups.tf"]` instead of an empty list. The contract's language
comes from the repo, not a keyword guess — which also fixes a long-standing trap where a
spec's language silently lost to the repo's. And a new readiness check surfaces the change
footprint and a blast radius (including destructive-IaC warnings) for the human to approve.
If the plan claims to modify a repo that reconnaissance could not read, that check **hard-fails** —
no more approving guesses.

The approval is bound to what was seen: a stable digest of the baseline commit, the change
mode, and the resolved language folds into the approval hash. Re-run the plan on the same
commit and the approval still holds; if the repo drifts underneath it, the approval
invalidates. You sign off on a specific tree, not a vibe.

## Scenario B — "rewrite this from Python to Rust"

A rewrite is the hardest case, because correctness is not "does it pass tests" but "does
it behave like the original." Three things had to change.

First, PFactory has to recognise a **migration** rather than a conflict. "Rewrite the
payments module from Python to Rust" against a Python repo used to look like a
language mismatch to halt on. A directional classifier now reads the intent — the verb,
the *from* language matching the repo, the *to* language — and records both `source_language`
and `target_language`. It then reads the Python statically to extract a behavioral
contract: the public API and signatures, the existing tests, the module import graph. From
that it plans the rewrite module-by-module in dependency order and declares a **golden
corpus** — which functions to capture input/output vectors for. It declares; it does not
execute.

Second, AIFactory builds in **rewrite mode**. The legacy Python is mounted as a read-only
**reference oracle**; the coder is pointed at a new, coexisting Rust crate and told to
generate there — never to edit the Python in place. The original keeps running as the
oracle during the transition.

Third, TFactory **proves equivalence**. A new differential lane captures the legacy
behaviour in its sandbox (the only place that untrusted code runs), then feeds the *same*
corpus to the new Rust and compares — with numeric tolerance, structural comparison, and a
cross-language error-class map so a Python `ValueError` and a Rust `InvalidInput` count as
the same outcome. The verdict is a parity ratio, and it is reported **honestly** under our
assurance-level rules: equivalence sits at VAL-2, partial parity can never read as full,
critical-vector divergence fails the lane outright, and modules the corpus did not cover
are reported as unproven rather than passed. A 95%-parity run says exactly that — "142 of
150 vectors, two modules unproven" — not "done."

## Why static-only matters

Everything above hangs on one rule: the planner reads, it does not run. No `npm install`,
no `terraform init`, no build scripts, no git hooks, no submodule fetch — a shallow clone
with execution vectors disabled, into a temp dir that is always torn down, degrading to
greenfield rather than failing if a repo is unreachable. The planner stays a pure,
side-effect-free component. The single point where the original code must actually execute —
capturing the migration oracle — lives inside the sandbox that was already built to run
untrusted code safely.

The user's side of this is unchanged: submit a spec, point at a repo and a branch. The
reconnaissance is automatic, the migration is auto-detected, and the reviewer approves a
plan grounded in what the planner actually saw — real files, the real language, a real
change footprint, and, for a rewrite, proof that the new code behaves like the old.

The details, the contract changes, and the phase breakdown are in
[RFC-0010](/rfc/code-aware-planning/).
