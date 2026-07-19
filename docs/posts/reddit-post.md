# Reddit post template

Reusable submission template for the 2026-07-19 showcase run. Reddit punishes
self-promotion, so lead with the engineering, not the product. Post from an
account with real comment history, engage in the thread, and do not drop the
same text into five subreddits at once.

Suggested subreddits (pick one or two, read their rules first):

- r/programming — general, technical, low tolerance for marketing
- r/devops — pipeline and delivery angle lands here
- r/ExperiencedDevs — the honesty-gate angle plays best with a senior audience

---

## Title

We built an autonomous coding pipeline that refuses to certify its own broken builds

(Alternates, pick the one that fits the sub:)

- A test gate that caps a build at "unverified" when it fails one of twelve verdicts, instead of rounding up
- Plan -> build -> test -> verdict, unattended: what actually happened on one live run

## Body

We have been building a system that takes a GitHub issue in and produces a
tested pull request out, with no human in the loop. Four services: one plans,
one builds, one verifies, one watches. This is a write-up of a single live run
on 2026-07-19, including the part that went wrong.

The run: a plain issue asked for a `clamp(value, low, high)` helper. The planner
cloned the repo read-only, built a map of the languages and frameworks pinned to
an exact commit, and classified the change. The builder ran inside a throwaway
Kubernetes Job refreshed to the tip of main, wrote the code, and opened its own
pull request. The tester generated and ran the tests in a sandbox and graded the
result. Verdict: verified to the lane that applies, 5 of 5 acceptance criteria,
9 tests kept, 0 rejected, mutation probe killed, confidence 0.96 across 3 stable
runs. The higher lanes were reported as "not run" rather than faked, because
there is no API or browser surface on a pure function.

The interesting part is what happened minutes earlier. A second helper,
`slugify`, built and looked fine, then failed one of twelve test verdicts on a
unicode edge case. The verification gate did not round up to "close enough." It
capped the build at the lowest assurance level and auto-filed a handback to fix
it. It refused to certify a build with a failing test.

That refusal is the whole point. Anyone can make an autonomous coder look good on
a curated example. The behavior that matters when nobody is watching is the
refusal to ship something wrong. A green checkbox is also impossible to produce
unless a real test runner actually executed, so the build cannot fake its own
pass.

One honest caveat: this run also exposed a real gap in our own code. The verdict
is computed correctly, but its automatic post back onto the PR is currently gated
by a fix we are now tracking as an issue. We would rather say that than pretend
the run was flawless.

Happy to answer questions on the sandboxing, the assurance-level math, or the
handback loop in the comments.

---

## Comments-section FAQ (paste as needed)

**Is this just wrapping an LLM in a for-loop?**
The novel part is not the code generation, it is the verification. The tester
grades on five signals (coverage, stability, mutation, semantic relevance, CI
parity) and recomputes an assurance level from what actually ran. A failing lower
lane caps the ceiling. That is what lets it refuse a build instead of always
returning green.

**How do you know the tests actually ran and were not hallucinated?**
There is a tamper-evident evidence gate. A "tests pass" checkbox cannot be
produced unless a real test runner executed. Mutation testing on the hard lane
checks that the assertions actually bite rather than passing vacuously.

**What is the isolation model?**
Each build runs in its own disposable Kubernetes Job refreshed to the current
main, then opens its PR and is torn down. Tests run in a per-task Nix sandbox.

**Does it write whole applications by itself?**
No, and we are not claiming that. The claim is narrow: on this run, a plain issue
became a tested PR unattended, and a wrong build was caught and sent back rather
than shipped.

**Can I see it run?**
There is a live walkthrough of the four portals available on request.
