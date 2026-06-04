---
layout: default
title: Roadmap
permalink: /roadmap/
---

# Program roadmap

Factory is managed as one program across five repositories, tracked on the
[Factory Program board](https://github.com/users/olafkfreund/projects/1). The
sequencing principle is **spine first**: make the pipeline traceable end-to-end
before building deep on top of it.

## Now — standardize the PARR spine

The connective tissue that lets the four products cooperate, tracked as the
[PARR-spine epic]({{ site.repo_url }}/issues):

- **PFactory → AIFactory** inbound handoff with issue-number provenance
- A shared **correlation key** (the GitHub issue number) threaded end-to-end
- A normalized **completion-event** envelope across all three services
- A canonical local **port map** (AIFactory 3101 · PFactory 3102 · TFactory 3103 ·
  CFactory 3110/3111)

## Next — CFactory cockpit

Deliver the control tower in phases (tracked in the
[CFactory repo](https://github.com/olafkfreund/CFactory/issues)):

- **P1** — skeleton, WorkItem correlation store, read-only pipeline board
- **P2** — agentic copilot (read tools, timeline summaries, anomaly detection)
- **P3** — advise + confirm actions, audit, scoped keys
- **P4** — hardening for hosted / multi-tenant

## Ongoing — the products

- **PFactory** — deeper cloud/Backstage enrichment, living templates, more review lenses
- **AIFactory** — provider delegation, enterprise hardening, mission-control UX
- **TFactory** — more modality lanes, richer evidence, tighter handback loop

## The bet

Lead with **governance + verification + observability**. Execution is
commoditizing; the durable advantage is a factory you can trust and watch.
CFactory is how the suite proves it.

---

*Live status lives in the issues and the
[program board](https://github.com/users/olafkfreund/projects/1).*
