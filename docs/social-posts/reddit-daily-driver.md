# Reddit: daily-driver milestone

Platform: Reddit (r/programming, r/devops, r/LocalLLaMA, r/ExperiencedDevs).
Tone: honest, technical, no marketing voice. Reddit punishes hype and rewards
specifics and caveats. Pick one subreddit and adjust the framing.

Title options:
- We measured our autonomous build pipeline end-to-end instead of just claiming it works. Here is what held and what did not.
- Autonomous plan-build-verify pipeline: full-fleet test pass plus a live run on real infra (with the honest caveats)

---

Body:

We have been building a multi-service pipeline that takes an issue and produces a
tested pull request. The shape is PARR: plan, build, verify, report. One service
plans against the actual code, one builds, one verifies with real generated
tests, one is the cockpit.

This week we ran a full readiness check rather than another demo. Three things had
to hold at once:

1. Every service's own test suite green. It was, with zero failures, across four
   services (thousands of tests each; the only local skips need Redis/S3/a sandbox
   and run in CI).
2. The live fleet healthy on every boundary. A cross-service seam gate drives the
   deployed pipeline and asserts reachability, auth, both ingest contracts, and the
   cockpit API. All green.
3. A real task through the whole thing. It planned, wrote code, wrote a test, and
   ran the test to confirm, on the live cluster, to a terminal success with a
   correct diff.

Some engineering details that mattered more than the model choice:

- Toolchains are baked into the images. Installing agent CLIs at pod start over
  the network stalled rollouts for minutes on a slow registry. Baking removed a
  whole class of flakiness.
- Code graphs are cached in object storage keyed by repo and commit. The graph
  gives the coding agent a scoped map instead of blind file reads; we measured
  [METRIC] fewer input tokens with no quality loss. The build is token-free, so
  caching is close to free.
- Verification is mutation-checked. An accepted test has to go red when the code
  under test is broken, otherwise it does not count. A green checkbox that passes
  on broken code is worse than no test.
- Each verification spec runs in its own git worktree, so parallel specs cannot
  read each other's tree.

The honest caveat: this run exercised planning, coding, and the coder writing and
running its own tests in one flow. The fully independent verification leg is proven
on real repos in earlier runs and validated here at the contract and full-suite
level, but the single continuous plan-to-independent-verdict flow is the next thing
we are closing. Supervised use is ready; unattended is close but not claimed.

The readiness gate itself caught a real bug during the run: it misread one
service's project-list response shape. That is the exact class of boundary bug
unit tests never see, which is the whole reason the gate exists.

Write-up and the live run: [BLOG_URL]
Code: [REPO_URL]

Happy to answer questions about the architecture or the failure modes we hit
getting here.
