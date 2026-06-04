---
layout: default
title: "Canonical local port map & run-all guide"
permalink: /dev/local-ports/
---

# Canonical local port map & run-the-whole-factory locally

> Part of the **PARR spine** (issue [#1](https://github.com/olafkfreund/Factory/issues/1),
> [#5](https://github.com/olafkfreund/Factory/issues/5)). Resolves the historical
> `:3102` collision between PFactory and TFactory by giving each product a fixed,
> non-overlapping port. **Updated:** 2026-06-04.

## Why this exists

Each product ships its own web server. Run two at once on their old defaults and they
fought over **`:3102`** (PFactory and TFactory both claimed it). This document is the
single source of truth for who binds what, so the four products run side by side and
CFactory can reach them all.

## Canonical port map

| Product | Backend (API + MCP) | Notes |
|---|---|---|
| **AIFactory** | **`3101`** | Act — build/QA web server |
| **PFactory** | **`3102`** | Plan — planning portal API + `mcp__pfactory__*` |
| **TFactory** | **`3103`** | Verify — was `3102`; **moved to `3103`** to resolve the collision |
| **CFactory** | **`3110`** / **`3111`** | Cockpit — API `3110`, realtime/stream `3111` |

Rules:

- These are **backend** ports (REST + WebSocket + MCP). A product's dev **frontend**
  (Vite, etc.) runs on its own separate port and proxies to its backend — see each
  repo's README.
- A product MUST default to its assigned port and MUST allow an env override
  (e.g. PFactory `APP_PORT`) for users who need to relocate it.
- New products take the **next free** backend port and update this table by PR.

## Resolving the collision

- **PFactory** keeps `3102` (its existing default — `apps/web-server` `APP_PORT=3102`).
- **TFactory** moves its web server off `3102` → **`3103`** (TFactory-repo change;
  update its `APP_PORT` default, `.env.example`, frontend proxy, and README).

No PFactory change is required — it is already canonical.

## Run the whole factory locally

Each product runs the same way: a Python backend on its canonical port + (optionally)
its dev frontend. Start them in four terminals, or use the snippet below.

```bash
# 1) AIFactory — Act (:3101)
( cd AIFactory/apps/web-server && APP_PORT=3101 python -m server.main ) &

# 2) PFactory — Plan (:3102)
( cd PFactory/apps/web-server && APP_PORT=3102 python -m server.main ) &

# 3) TFactory — Verify (:3103)
( cd TFactory/apps/web-server && APP_PORT=3103 python -m server.main ) &

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
AIFactory  :3101   (Act)
PFactory   :3102   (Plan)
TFactory   :3103   (Verify)
CFactory   :3110   (Cockpit API)  + :3111 (stream)
```
