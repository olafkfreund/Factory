---
status: approved
issue: 1960
author: olafkfreund
---

# Intent: agent identity distinct from human identity in git records

Epic: olafkfreund/Factory#1960. Related: #1961 (artifact header `agent_identity` / `originator`), #1962 (autonomy matrix).

## Problem

The epic's plan (stage 4) says agent-authored commits carry the human as git author. Checked on 2026-10-26, that holds for some commits and not for others:

| Where | Author today | Source |
|---|---|---|
| Factory repos' own history (`AIFactory@origin/dev` etc.) | the human | Claude Code sessions on a workstation, with the human's git config, squash-merged through the human's GitHub account. These are not factory-agent commits. |
| Branch commits a factory agent makes in a target repo | `AIFactory <aifactory@container>` | `AIFactory/Dockerfile:507-508` sets this global git identity in the image. Example: `olafkfreund/aifactory-demo`, `pfactory-friends-demo` (`aifactory: subtask-1-1 - ...`). |
| The same work on the target's default branch, after merge | **the human** (committer `GitHub`) | AIFactory merges with `--squash` by default (`runners/github/providers/github_provider.py:194,243`, `gh_client.py:589`). GitHub writes the PR author as the squash commit's author. The agent survives only as a `Co-authored-by: AIFactory <aifactory@container>` trailer. |

So the gap is not on branch commits. Every factory agent already commits under one distinct identity there. The gaps are:

1. **On the default branch the human is the author** of agent-written code. The squash merge rewrites authorship to the GitHub account that opened the PR. That account is the human's, because the factories act with the human's token.
2. **The agent identity is one shared string**, `AIFactory <aifactory@container>`. It names no agent, run, key or tier. The email cannot be routed, and GitHub does not link it to anything. It cannot be revoked, and nothing can query it.
3. **The human is not recorded on branch commits at all.** Author and committer are both `AIFactory`. The originator is not known inside the build: PFactory captures no actor, and AIFactory's from-issue poller drops the issue author (plan, "The human half").

## Why the requested first slice stops here

The requested slice was: a distinct agent git author on factory commits, behind a flag that defaults to current behaviour.

- **Branch commits:** already done. A flag to rename `AIFactory <aifactory@container>` to, for example, `aifactory-agent <...@users.noreply.github.com>` changes a label and closes none of the gaps above. A `users.noreply.github.com` address that belongs to no account is also a plausible-looking but meaningless value, which #1961 warns against.
- **Default-branch commits (gap 1):** the author there is whichever GitHub identity opens and merges the PR. Making that an agent needs a GitHub App or a bot account. This lane may not create either, so the slice stops after this intent, as briefed.
- **Without a new identity**, the only lever is the merge method: `merge` or `rebase` instead of `squash` keeps the branch commits' author on the default branch. That changes merge behaviour for every factory-merged repo and how their history reads. It is a decision for the owner, not a flag-off slice.
- **Recording the human (gap 3)** needs the originator, which stage 3 (intake capture) produces. A trailer written before stage 3 lands would be empty or guessed.

## Proposed outcome (whole epic)

- Every agent commit, on branches and on the default branch, names an agent identity of the form `agent:<service>/<key_id>`. That identity can be queried, revoked and tied to an autonomy tier.
- The human who started the run is recorded next to it as `human:<provider>/<subject>`, or as an explicit null where there is none (scheduled runs).
- A PR needs an approving review from an identity other than its author, enforced by branch protection, and an agent identity cannot give that approval.

## Remaining slices, in order

1. **Stage 2: autonomy ceiling on `acw_` keys. Chosen as the first code slice (decision 2026-10-26).** Additive, needs no GitHub identity, and has a clear test. Add a nullable autonomy ceiling to the `ApiKey` model (`apps/web-server/server/database/models.py`, with an alembic migration), give each key `agent_identity = agent:aifactory/<key_id>`, and add a pure helper in `merge_policy.py` that returns the effective tier: the stricter of the key's ceiling and the merge decision. A key without a ceiling records null and leaves the decision unchanged. `mcp_stdio/auth.py` is left alone: AIFactory #1885 is changing it. Wiring the ceiling into the live merge path comes after slice 2, which tells the merge path which key started the run.
   - Shipped in AIFactory #1887. Only org admins may set a ceiling, and `acw_` keys cannot mint keys. A key with no ceiling stays unrestricted for backward compatibility.
   - **Hard gate before slice 2:** before `cap_disposition` gates the merge path, keys without a ceiling must either default to the strictest tier (`hard`) or be refused for agent work. Slice 2 does not ship without one of the two.
2. **Stage 3: capture the originator at intake.** MCP/CLI first, since `require_acw_scope` already resolves the key owner. From-issue second (cross-repo, changes the `FromIssueBody` contract). Portal last or never; that depends on the owner's auth decision.
3. **Git trailers on branch commits** (no GitHub identity needed): `Agent-Identity: agent:aifactory/<key_id>` and `Originator: human:github/<login>`. Write them only once slices 1 and 2 supply real values. Inject them where the factory commits: the agent subprocess env (`core/client.py` `sdk_env`), `core/worktree.py` `commit_in_worktree`, and the safety-net commit in `agents/utils.py`. Behind a flag that defaults to off.
4. **Factory GitHub App opens and merges agent PRs.** Decided by the owner on 2026-10-26: default-branch attribution uses a GitHub App identity, not a change of merge method. Squash merges then carry the App as author, and stage 5 gets an identity to exclude from approval. **Needs the owner to create the App and its private key**; no lane creates either. Linked to AIFactory #1701, the existing issue on using the App installation token.
5. **Stage 1: required reviews in branch protection** on all four repos, after the auto-merge path has an approving identity. Otherwise it stops `watch_and_finish` (plan, unknown 2).
6. **Revocation and expiry** for agent identities.
   - **6b.** Once an agent identity is issued, stop agents overriding `GIT_AUTHOR_*`/`GIT_COMMITTER_*` (`security/ast_parser.py` `_SAFE_GIT_KEYS`). Decided yes on 2026-10-26; not changed now.

## How the autonomy tier is carried later

- **Source of truth:** a field on the `acw_` key record (slice 1), in the vocabulary `merge_policy.py` already uses. Risk classes `low`/`medium`/`hard` (R1-R3) map to dispositions `AUTO_MERGE`/`HOLD_ASYNC`/`HOLD_BLOCKING` (A3-A1), with the RFC-0013 environment overlay on top. The key carries the ceiling the agent may act at. `merge_policy.py` still decides per change, and the effective tier is the lower of the two.
- **Run artifacts:** `autonomy_tier` in PFactory's run signature header (#1961) is stamped from the effective tier, next to `agent_identity` and `originator`.
- **Git:** an `Autonomy-Tier: A3` trailer next to `Agent-Identity:` (slice 3). It is not encoded in the author name or email, so changing a tier never forks an identity.
- **Published matrix:** #1962 generates it from `merge_policy.py`. The key-level ceiling is an extra input to that generator, not a second hand-written table.
- An absent tier is written as null, never as a default value, consistent with #1961's rule against fabricated governance fields.

## Affected users and systems

AIFactory (container git identity, commit paths, merge provider, `acw_` keys), PFactory (intake actor, run signature), the four Factory repos' branch protection, and every target repo the factories merge into.

## Constraints

- Create no GitHub accounts or apps in this lane. Change no branch protection, gitops or cluster config, and lock out no human or service login.
- Every flag defaults to current behaviour.
- Write no plausible-looking placeholder identity into a governance field. Write null instead.
- Agents may set `GIT_AUTHOR_*`/`GIT_COMMITTER_*` in their own commands (`security/ast_parser.py` `_SAFE_GIT_KEYS`). Git authorship is therefore attribution, not proof. Proof needs a credential the agent cannot set, which slice 4(a) provides.

## Decisions (2026-10-26)

- First code slice: the autonomy ceiling on `acw_` keys (slice 1).
- Default-branch attribution: a Factory GitHub App opens and merges agent PRs (slice 4), not a change of merge method. The owner creates the App and its key; see AIFactory #1701.
- `_SAFE_GIT_KEYS`: lock agents out of setting their own author once an agent identity exists (slice 6b), not now.

## Open questions

None for slice 1. Slice 4 waits on the owner creating the GitHub App and its key.
