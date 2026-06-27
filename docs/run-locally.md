---
layout: default
title: "Run the whole Factory locally"
permalink: /run-locally/
---

# Run the whole Factory locally

The four products are independent services. Run them together — with **CFactory**
as the single cockpit over all three — using this canonical layout. It also
resolves the historical port collision (PFactory and TFactory both defaulted to
`3102`).

## Canonical port map

**Backends must be distinct** — CFactory connects to all three at once.

| Service | Backend (API) | Frontend (portal) | Notes |
|---|---|---|---|
| **AIFactory** | `3101` | `3100` | execution engine |
| **PFactory** | `3102` | `3100` | planning + governance |
| **TFactory** | `3103` | `3100` | test/verify *(moved from 3102 → 3103)* |
| **CFactory** | `3111` | `3110` | the cockpit over all three |

> Frontends historically all bind `3100`. When running everything at once you
> normally don't need the three product portals open — **CFactory's cockpit on
> `3110` is the unified view**. If you do want a product portal up alongside it,
> start that one portal (the others can stay headless) or give it a distinct port.

## Start each service

Each repo ships a Nix dev shell; enter it (`nix develop` or direnv) then:

```bash
# AIFactory (backend :3101)
cd AIFactory  && <its backend run command>            # see AIFactory README

# PFactory (backend :3102)
cd PFactory   && python -m server.main                # FastAPI :3102

# TFactory (backend :3103)
cd TFactory   && python -m server.main                # FastAPI :3103

# CFactory (backend :3111 + cockpit :3110)
cd CFactory   && just run        # backend
cd CFactory   && just ui         # cockpit  ->  http://localhost:3110
```

## Wire CFactory to the three services

CFactory's dev shell already points at the canonical backends — no config needed
for the default layout:

```
CFACTORY_AIFACTORY_API_URL = http://localhost:3101
CFACTORY_PFACTORY_API_URL  = http://localhost:3102
CFACTORY_TFACTORY_API_URL  = http://localhost:3103
```

Override any of them (e.g. remote hosts) via environment or `CFactory/.env`.

## How data reaches the cockpit

- **Pull / on demand** — hit **Refresh** in the cockpit (or `POST /api/refresh`);
  CFactory polls each service's REST API and hydrates the board.
- **Push / live** — each service emits a [completion event](/rfc/correlation-key/)
  when a stage finishes; point `*_COMPLETION_WEBHOOK` at
  `http://localhost:3111/api/events` and the board updates live.

Both paths thread work by the shared **correlation key** (the GitHub issue
number) defined in [RFC-0001](/rfc/correlation-key/).

## One-glance health

With all four up, open the cockpit at **http://localhost:3110** — the header pill
shows backend status and how many upstreams are wired; the board shows every work
item across plan → code → test.
