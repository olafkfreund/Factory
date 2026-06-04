---
layout: default
title: "Canonical local port map & run-all guide"
permalink: /dev/local-ports/
---

# Canonical local port map & run-the-whole-factory locally

> Part of the **PARR spine** (issue [#1](https://github.com/olafkfreund/Factory/issues/1),
> [#5](https://github.com/olafkfreund/Factory/issues/5)). Resolves the historical
> `:3102` collision by giving each product a fixed, non-overlapping port.
> **Updated:** 2026-06-04.

## Why this exists

Each product ships its own web server. Run two at once on their old defaults and they
fought over **`:3102`** (PFactory and TFactory both claimed it). This document is the
single source of truth for who binds what, so the four products run side by side and
CFactory can reach them all.

## Canonical port map

| Product | Backend port(s) | Notes |
|---|---|---|
| **AIFactory** | **`3101`** | Act — build/QA web server |
| **TFactory** | **`3102`** | Verify — keeps `3102` (uncontested once PFactory moved out) |
| **CFactory** | **`3110`** / **`3111`** | Cockpit — API `3110`, realtime/stream `3111` |
| **PFactory** | **`3114`** (API) / **`3115`** (frontend) | Plan — moved to its own pair off the `3101–3103` block |

Rules:

- The numbers above are the products' **backend/API** ports (REST + WebSocket + MCP).
  PFactory additionally pins its dev **frontend** at `3115`; other products' dev
  frontends run on their own ports — see each repo's README.
- A product MUST default to its assigned port and MUST allow an env override
  (e.g. PFactory `APP_PORT`) for users who need to relocate it.
- New products take the **next free** port and update this table by PR.

## How the `:3102` collision was resolved

PFactory **vacated `3102`** and moved to its own **`3114` (backend) / `3115`
(frontend)** pair. TFactory therefore keeps `3102` with no conflict and needs no
change. PFactory's move spans its web-server default (`APP_PORT`), CORS, the Graphiti
MCP (served on the same backend port), OIDC callback URIs, Dockerfile / compose /
helm, and the `just` recipes — see PFactory PR #54.

## Run the whole factory locally

Each product runs a Python backend on its canonical port + (optionally) its dev
frontend. Start them in separate terminals, or use the snippet below.

```bash
# 1) AIFactory — Act (:3101)
( cd AIFactory/apps/web-server && APP_PORT=3101 python -m server.main ) &

# 2) TFactory — Verify (:3102)
( cd TFactory/apps/web-server && APP_PORT=3102 python -m server.main ) &

# 3) PFactory — Plan (:3114 backend, :3115 frontend)
( cd PFactory && just backend ) &      # APP_PORT=3114
( cd PFactory && just frontend ) &     # vite --port 3115

# 4) CFactory — Cockpit (:3110/:3111)
( cd CFactory && APP_PORT=3110 STREAM_PORT=3111 <its start command> ) &

wait
```

> Each command assumes the product's virtualenv is active and deps are installed —
> see the product's own README/CLAUDE.md for setup. The exact start command for
> AIFactory / TFactory / CFactory is defined in their repos; the **ports above are
> authoritative**.

### Wiring them together

With the map fixed, point the completion-event webhook (see
[RFC-0001]({{ '/rfc/correlation-key/' | relative_url }})) at CFactory's collector so
PFactory/AIFactory/TFactory report terminal events to one cockpit, e.g. for PFactory:

```bash
PFACTORY_COMPLETION_WEBHOOK=http://localhost:3110/api/events/completion
```

## Quick reference

```
AIFactory  :3101         (Act)
TFactory   :3102         (Verify)
CFactory   :3110         (Cockpit API)  + :3111 (stream)
PFactory   :3114         (Plan API)     + :3115 (frontend)
```
