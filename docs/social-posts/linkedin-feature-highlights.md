# LinkedIn: feature highlights (short series)

Platform: LinkedIn. Tone: one feature, one concrete point, one link. ~80-120
words each. Post as a series over several days rather than all at once.

---

## Baked toolchains

Small infrastructure changes beat clever ones. Our build and verify pods used to
install their agent CLIs at startup over the network. On a slow registry that
stalled rollouts for minutes and stranded in-flight work. We baked every provider
CLI into the image instead. Pods are ready the moment they schedule, and a whole
class of flakiness is gone. Sometimes the win is deleting the network call, not
optimizing it.

Detail: [BLOG_URL]

---

## Cached code graphs

Giving a coding agent a scoped map of the repository beats making it read blindly.
We build a code graph with a static parser (no tokens spent) and cache it in
object storage keyed by repository and commit. A per-task job reuses it instead of
rebuilding. Measured result: [METRIC] fewer input tokens with no drop in quality.

Detail: [BLOG_URL]

---

## Mutation-checked verdicts

A passing test is worthless if it also passes when the feature is removed. Every
test our verifier accepts is mutation-checked: we break the code under test and
confirm the test goes red. A verdict carries stability, mutation, and CI-parity
signals, not just a green count. Trust has to be earned per test.

Detail: [BLOG_URL]

---

## Per-spec isolation

Concurrency bugs hide in shared state. Each verification spec now runs in its own
git worktree, so two specs verifying the same project cannot read each other's
tree. We caught it working during a live run: a probe branch would not delete
because its own task worktree still held it. That is the isolation doing its job.

Detail: [BLOG_URL]
