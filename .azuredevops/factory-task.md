# Factory task — Azure DevOps work-item template (RFC-0011)

Azure DevOps does not store issue templates as files in the repo the way GitHub
(`.github/ISSUE_TEMPLATE/`) and GitLab (`.gitlab/issue_templates/`) do. ADO work
items are typed (Issue / Task / User Story / Bug), and a reusable template is
defined **in the project**, not committed to git. This file documents the
canonical Factory task template so it can be recreated identically in any ADO
project and kept in step with the GitHub/GitLab forms.

The Factory poller reads work-item **tags** (the ADO equivalent of labels — see
`scripts/sync_labels.py` and AIFactory's `AzureDevOpsProvider`). Tags drive
routing exactly as `factory:*` labels do elsewhere.

See https://factory.freundcloud.com/rfc/label-driven-intake/

## Fields

| Field | Value / mapping |
|---|---|
| **Work Item Type** | Issue (or Task) |
| **Title** | `[task] <one-line summary>` |
| **Tags** | `pfactory` **and exactly one of** `factory:low` / `factory:medium` / `factory:hard` |
| **Description** | The Context + Acceptance criteria + Target repo + Change mode (template below) |

Difficulty (the tag) drives model / planning / human gate / verification floor /
merge, identically to the other hosts:

- `factory:low` — cheap/local model (ollama→haiku), no planning, no human,
  auto-merge when green.
- `factory:medium` — sonnet, light planning, async approval.
- `factory:hard` — opus, full PFactory plan, blocking approval, deepest
  verification.

A **migration** (rewrite/port) forces `factory:hard` and an equivalence check
(RFC-0010/0011); also tag `plan-type:migration`.

## Description body (paste into the work item)

```
## Context
<What needs to happen and why. Link relevant code, docs, or prior work items.>

## Acceptance criteria
- <testable condition 1>
- <testable condition 2>

## Target repository
<owner/repo or ADO repo/project path the change lands in>

## Change mode
create | modify | migration   (migration = rewrite/port — forces factory:hard)
```

## How to register this template in an ADO project

1. Project settings → Boards → **Team configuration** → **Templates**.
2. Choose the work-item type (Issue/Task) → **Add template** → name it
   `Factory task`.
3. Pre-fill **Tags** with `pfactory; factory:medium` (operators change the tier
   tag per task) and paste the Description body above.
4. Ensure the `factory:*` tags exist — run
   `python3 scripts/sync_labels.py --provider azure_devops --org <url> --project <name> --apply`
   (or let them be created on first apply).

Because the tier is a **tag**, no conditional automation is needed on ADO: the
operator selects the tier tag directly when creating the work item, and the
poller picks it up.
