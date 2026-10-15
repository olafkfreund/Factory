---
status: approved
issue: 3591
spec: spec/2026-10-15-3591-rejected-designs-note.md
---

# Plan: make rejected designs easy to find before proposing one again

Approved decisions (from the spec): no `rejected/` directory and no
generated index. One README bullet documents `intent/`, `spec/`, `plan/`
and says rejected designs live in each spec's (or RFC's)
`## Alternatives rejected` section, how to search them, and that a
re-proposal needs new evidence.

## Steps

1. `README.md:79-80`: after the `scripts/` bullet (ends "rather than in a
   copy.") and before "Program planning", insert:
   ```
   - `intent/`, `spec/`, `plan/` — the why, what and how of each task, one
     `YYYY-MM-DD-<issue>-<slug>.md` per task. A design that was considered and
     rejected is recorded, with the reason, in the `## Alternatives rejected`
     section of the spec (or RFC in `docs/rfc/`) that rejected it; there is no
     separate `rejected/` index (#3591). Search them before proposing a design:
     `git grep -n -A15 '^## .*Alternatives' spec docs/rfc`. Proposing a
     rejected design again needs new evidence, cited in the new spec.
   ```
   → verify `git grep -c '^## .*Alternatives' spec docs/rfc | wc -l` > 0 and
   `git diff --stat` shows only `README.md`.
   Traps: README is not in the Jekyll `docs/` site; no other doc needs it.
   Match the existing bullet style (em dash, two-space wrapped lines).
2. Commit naming step 1, push, PR `Closes #3591`.

## Tests

No code. The grep above returns the existing sections.

## Rollback

Revert the README hunk.
