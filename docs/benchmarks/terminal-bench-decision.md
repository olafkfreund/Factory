# Terminal-Bench: defer decision (2026-07-11)

Issue #271 originally scoped SWE-bench Verified plus Terminal-Bench. After a
feasibility review of Terminal-Bench 2.x and its Harbor harness, Terminal-Bench
is deferred. SWE-bench Verified remains the primary external benchmark axis.

## Rationale

Terminal-Bench measures interactive shell mastery: an agent issues a command,
observes output in real time, and iterates inside the task container. The
Factory pipeline is an asynchronous issue-to-PR system (plan, code, verify as
batched stages). Bridging the two requires an adapter that itself implements
the interactive loop, so the resulting score would primarily measure adapter
fidelity rather than the pipeline's issue-resolution capability.

Secondary factors:

- Adapter cost is not the blocker (published adapters run 150-300 LOC); the
  orchestration mismatch is. The pipeline has no real-time shell re-entry
  between stages by design.
- Terminal-Bench task domains (sysadmin, live debugging, ML ops in a shell)
  do not overlap with what the fleet sells: autonomous spec-to-verified-PR.

## Second benchmark axis (future)

If a second axis is wanted after the SWE-bench baseline lands, the review
recommends, in order:

1. Commit0 (54 Python libraries implemented from skeleton against full test
   suites) - measures repo-level coherence, self-hostable evaluation.
2. SWE-bench Multilingual (issue-to-patch in 9 languages) - same harness
   family as Verified, exercises the fleet's polyglot lanes.

## Revisit trigger

Reconsider Terminal-Bench if the fleet gains a genuinely interactive terminal
agent component (for example live incident response), where shell iteration is
the capability under test.
