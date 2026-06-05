# Architecture

PFactory is a planning pipeline that converts an unstructured plan into governed,
reviewable GitHub issues.

## Pipeline

```
ingest ─▶ enrich ─▶ decompose ─▶ review gates ─▶ human approval ─▶ emit
 (idea/    (live      (tasks +     (architecture/   (governance      (governed
  spec/    cloud +     acceptance   security/        gate)            GitHub
  MCP/     Backstage   criteria)    best-practices/                   issues)
  issue)   context)                 feasibility,
                                    scored 0–1 + citations)
```

| Stage | What it does |
|---|---|
| **Ingest** | Accept a plan from docx/pdf/md, an MCP client, or an existing issue. |
| **Enrich** | Pull live org/cloud and Backstage context so the plan is grounded. |
| **Decompose** | Break the plan into tasks with explicit acceptance criteria. |
| **Review gates** | Score architecture / security / best-practices / feasibility (0–1) with citations to the evidence behind each verdict. |
| **Human approval** | The governance gate — a human approves or rejects before anything is emitted. |
| **Emit** | Create governed GitHub issues; the first issue number becomes the suite-wide correlation key. |

## Shared skeleton

PFactory shares the Factory technical skeleton: **Python 3.13 + FastAPI**
(REST + WebSocket), the **Claude Agent SDK** provider factory, **Graphiti** memory
(served as an MCP on the backend port), and a **credential broker** for secrets.

## Outputs & handoff

On a terminal status PFactory emits one RFC-0001 completion event
(`emitted` → `emit`, or `rejected` → `review`). The governed issues it creates are
consumed by **AIFactory**, which carries the issue number as provenance. See
[API & Contracts](api.md) for the event envelope.
