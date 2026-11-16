---
status: draft
issue: 1960
author: olafkfreund
---

# Intent: agent and originator on every emitted signal and agent PR

## Problem

Epic #1960 wants every artefact the fleet emits to say whether a change was
agent-authored and who asked for it. Measured on `dev` today:

- AIFactory completion events (terminal, usage snapshot, worker) carry no
  `agent_identity` or `originator`, although the task's `requirements.json`
  records both.
- PFactory's docs run signature carries both, but its completion event does not.
- TFactory records neither anywhere: the ingest request has no field for them,
  so its completion envelope cannot carry them.
- The PR AIFactory opens (`_pr_title_body`) names neither. Commit trailers
  exist (AIFactory#2015) but the PR body does not.

## Proposed outcome

- Every AIFactory, PFactory and TFactory completion event has `agent_identity`
  and `originator` keys, each independently nullable (agent format `agent:<svc>/<id>`,
  `human:...` as already used).
- AIFactory hands both to TFactory at verify handoff; TFactory stores them in
  `context/source.json` and echoes them in its envelope.
- An agent-opened PR body states "Authored by <agent_identity>" and
  "Originator: <originator>" when known.

## Affected users and systems

AIFactory (`completion.py`, `pr_endgame.py`, `pfactory/tfactory_client.py`),
PFactory (`plan/completion.py`), TFactory (`routes/specs.py`, ingest workspace,
`triager.py`), CFactory as a consumer of additive keys.

## Constraints

- Additive only: old consumers keep working; missing values are null, never invented.
- No new credential. GitHub PR *author* stays whoever the token is (needs the
  GitHub App, owner's #1973); the body states the agent identity instead.
- Values are untrusted text: single printable line before they enter a PR body.
- The factory-gitops flag `AIFACTORY_AGENT_COMMIT_TRAILERS` is already set
  (factory-gitops PR #326, merged), so no gitops PR is needed. The deployed image
  (sha-1c4cc96) predates AIFactory#2015, so build Jobs honour it only after the
  next release.

## Open questions

None. Out of scope: GitHub App identity, branch protection, revocation, the live
check that the agent can write the canonical spec dir in a build Job pod
(owner/post-release action).
