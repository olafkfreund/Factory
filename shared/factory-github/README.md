# factory-github (canonical VCS-client layer)

This directory is the **single source of truth** for the GitHub/VCS runner layer
that PFactory, AIFactory and TFactory each duplicate under
`apps/backend/runners/github/`.

It was established by the Phase-1 deduplication work in the Factory code-quality
program (epic Factory#154, issue Factory#157): the same ~1,800 LOC of VCS-client
code (`gh_client.py` + `rate_limiter.py` + the `providers/` tree) was being
maintained three times, and the copies had already begun to diverge.

## What lives here

The canonical set is exactly the deduped layer — nothing service-specific:

| File | Role |
| --- | --- |
| `gh_client.py` | Thin async wrapper over the `gh` CLI (run, PR/issue ops, diff/file pagination, blob comparison). |
| `rate_limiter.py` | Token-bucket + GitHub rate-limit-aware throttling for the client. |
| `providers/protocol.py` | The provider `Protocol` (the abstract VCS surface). |
| `providers/factory.py` | Provider selection / construction. |
| `providers/github_provider.py` | GitHub implementation. |
| `providers/gitlab_provider.py` | GitLab implementation. |
| `providers/azure_devops_provider.py` | Azure DevOps implementation. |
| `providers/__init__.py` | Package init / re-exports. |

Service-specific files that live alongside the layer in some repos (for example
AIFactory's `bot_detection.py`, `cleanup.py`, `confidence.py`, `audit.py`) are
**not** part of this canonical contract and are intentionally out of scope.

## Provenance and the reconciliation that was done

The canonical copy is the **superset** reconciled from the three live copies.
At extraction time the three repos were *not* byte-identical:

- **AIFactory** (and TFactory, for `gh_client.py` / `rate_limiter.py`) carried the
  RFC-0011 `enable_auto_merge` method on the provider protocol and every provider
  (the "auto-merge-when-green" surface). PFactory and TFactory lagged on parts of
  this.
- **PFactory** had been reformatted under a different line-length / `datetime`
  style (e.g. `from datetime import UTC` vs `timezone.utc`, bare `TimeoutError`
  vs `asyncio.TimeoutError`) — behaviour-equivalent, formatting-only drift.
- **`gitlab_provider.py`** additionally carried a genuine per-service identity
  token: the Duo-Workflow "goal" string referenced "the <Service> enrichment
  comment", so each repo named *itself*. This is real divergence, not copy-drift.
  It is now **parameterised** (Factory#157): the canonical reads the service name
  from the `FACTORY_SERVICE_NAME` environment variable (default `"the Factory"`),
  so the file stays byte-identical across the fleet while each service supplies
  its own identity at runtime. The Duo "goal" is a human-readable hint and the
  Duo agent reads the issue regardless, so a neutral default is behaviour-equivalent.

AIFactory was chosen as the canonical because it is the functional superset (it
has the complete RFC-0011 auto-merge surface). It was vendored **byte-for-byte**
from AIFactory commit `e8da3df` (`v3.6.26-120-ge8da3df2`), then the GitLab
enrichment service-name was parameterised as described above (Factory#157).

> Status: as of the Factory#157 reconciliation, PFactory / AIFactory / TFactory
> all carry this canonical byte-for-byte and each runs the drift gate in its own
> CI (`.github/workflows/factory-github-drift.yml`). Full package consumption
> (publishing `factory-github` as an installable package and deleting the
> per-repo copies) remains a tracked follow-on.

## Consumption model (pinned-SHA, not a rewrite — yet)

Today this is a **vendor-canonical + drift-gate** model, deliberately:

1. The hub holds the canonical copy here.
2. `scripts/check_factory_github_drift.py` diffs a service's
   `apps/backend/runners/github/` tree against this canonical, file-by-file,
   byte-exact, and exits non-zero on divergence.
3. Each service is expected to vendor this layer at a **pinned hub SHA** and run
   the drift gate in its own CI so the copies cannot silently re-diverge.

We are **not** rewriting imports across the four repos in this change. Full
package consumption (publishing `factory-github` as an installable package and
deleting the per-repo copies) is a tracked follow-on; it is deferred here because
it is a cross-repo, behaviour-affecting change that deserves its own staged PRs.

The per-repo CI drift-gate **workflows** were added in the Factory#157
reconciliation: each service repo carries
`.github/workflows/factory-github-drift.yml`, which fetches this canonical at a
pinned hub SHA and runs the gate against its `apps/backend/runners/github/` tree.

## CODEOWNERS note

Because this is fleet-wide infrastructure, changes here must be reviewed: this
directory should be added to `.github/CODEOWNERS` so the VCS-layer owners review
any edit. A change to the canonical layer is a fleet change — land it here first
(CODEOWNERS-reviewed), then propagate to the service copies and re-pin their SHA.
Do **not** edit a service copy to fix the gate; fix the canonical and re-vendor.
