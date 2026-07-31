# Actions workflow permissions (repo setting, and a stated dependency)

Status: RECORDED. This documents a repo-level GitHub setting that one workflow
now depends on, the security trade-off it carries, and which repos have it on.

Companion to [branch-protection.md](branch-protection.md) — same class of
control (repo-level settings that decide who may land what), different setting.

## The setting

`Settings > Actions > General > Workflow permissions >`
**"Allow GitHub Actions to create and approve pull requests"**

Readable and writable over the API:

```bash
gh api repos/olafkfreund/<repo>/actions/permissions/workflow
# {"default_workflow_permissions":"read","can_approve_pull_request_reviews":false}

gh api -X PUT repos/olafkfreund/<repo>/actions/permissions/workflow \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
```

## Fleet state (read 2026-07-31)

| Repo | `can_approve_pull_request_reviews` | Why |
| --- | --- | --- |
| AIFactory | **true** | required by `base-image pins` (AIFactory#1104) |
| Factory | false | nothing needs it |
| PFactory | false | nothing needs it |
| TFactory | false | nothing needs it |
| CFactory | false | nothing needs it |
| factory-gitops | false | its writers use `GITOPS_PAT`, not `GITHUB_TOKEN` |

`default_workflow_permissions` is `read` everywhere. Jobs that need more request
it explicitly in their own `permissions:` block, which is the right default —
leave it alone.

## What depends on it

**AIFactory `.github/workflows/base-image-pin-liveness.yml`, job `pins-bump`.**

That job exists because Dependabot's docker ecosystem is configured in AIFactory
and has never produced a single PR, while the identical config in PFactory and
TFactory bumps within a minute (AIFactory#1104). Meanwhile the pins genuinely
rot — `chainguard/python:latest-dev` moved through three digests in about a day
— and once a superseded Chainguard digest is garbage-collected, `docker (P0
acceptance)` cannot start a build at all (AIFactory#1091).

Without this setting the job still works, but stops one step short: it pushes
`bot/base-image-pins` with the diff ready and fails with a one-click link. With
it, the job opens the PR itself.

## The trade-off, stated plainly

**The same toggle grants both "create" and "approve".** There is no way to
allow one without the other. Turning it on means a workflow in that repo *can*
approve a pull request.

That matters here specifically because
[change-management-sod.md](policies/change-management-sod.md) records the gap
that "one actor can author, self-approve". This setting adds a second way that
could happen — a workflow rather than a person — so it should be read as
widening the same finding, not as unrelated.

It was enabled on AIFactory as a deliberate decision, with that trade-off known,
to make the base-image bump fully automatic. It is **not** a fleet default:
leave it `false` on any repo with nothing that needs it.

### What it does not do

- It does not let a workflow bypass branch protection or required reviews. If
  a branch requires a review from a human code owner, a workflow approval does
  not satisfy that; configure protection accordingly (see
  [branch-protection.md](branch-protection.md)).
- It does not change `default_workflow_permissions`, which stays `read`.

### If you would rather not enable it

Two alternatives, both avoiding the toggle:

1. **Accept the one click.** The bot pushes a ready branch and fails loudly with
   the compare URL. Nothing is weakened; a human opens the PR.
2. **Give the workflow a PAT** with `repo` scope. This is *better* on one axis —
   a PAT-opened PR triggers CI, which a `GITHUB_TOKEN`-opened one does not, so
   `docker (P0 acceptance)` runs on the bump automatically — at the cost of
   holding another long-lived secret.

The `GITHUB_TOKEN` path's inability to trigger CI is a real caveat of the
current AIFactory setup: the bot's PR body tells the reviewer to close and
reopen so the build actually runs before merge.

## Re-checking this

The table above is a point-in-time read. To re-derive it:

```bash
for r in Factory AIFactory PFactory TFactory CFactory factory-gitops; do
  printf '%-16s ' "$r"
  gh api "repos/olafkfreund/$r/actions/permissions/workflow"
  echo
done
```

Nothing currently alerts when this setting changes. If it becomes load-bearing
in more than one repo, it belongs in `scripts/apply_branch_protection.sh`'s
sibling — settings-as-code — rather than in a table someone has to remember to
re-read.
