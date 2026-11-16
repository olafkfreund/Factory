---
status: draft
issue: 3710
author: olafkfreund
---

# Intent: Project .env allowlist in PFactory and TFactory

## Problem

PFactory and TFactory copy every key from `<project>/.pfactory/.env` and
`<project>/.tfactory/.env` into the environment of the runner they start
(`agent_service.py`, two project-file loaders each, and `pr_review_service.py`
`_load_env_file`). The file lives in the project checkout, so the repository
controls it. A repo can set `PYTHONPATH`, `LD_PRELOAD` or `NODE_OPTIONS` and run
code inside the runner with its full credentials, before any agent env
scrubbing (#3708) applies. AIFactory fixed this earlier with an allowlist
(`project_env.py`, #1745/#1795); the other two never got it.

## Proposed outcome

Only a named list of supported project settings is loaded from the project
`.env`. Every other key is ignored and logged by name (never by value). A test
loads a `.env` with `PYTHONPATH`, `LD_PRELOAD` and `NODE_OPTIONS` and asserts none
reaches the runner env.

## Affected users and systems

PFactory and TFactory web-server (`server/services/agent_service.py`,
`pr_review_service.py`). AIFactory was checked: its project `.env` already goes
through the allowlist; only the trusted backend `.env` uses the raw loader. No
AIFactory change.

## Constraints

- The backend `.env` (operator-owned) keeps its current loading; only the
  project file is restricted.
- Every key the Settings UI writes to the project `.env` must still load.
- Never log values.

## Open questions

None.
