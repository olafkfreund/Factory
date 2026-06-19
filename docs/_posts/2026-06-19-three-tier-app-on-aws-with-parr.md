---
layout: post
title: "Plan to production on AWS: a 3-tier app through PARR, deployed and torn down"
subtitle: "One brief becomes a Fastify + Postgres + Redis service running on a real EKS cluster — including the parts the generator got wrong"
date: 2026-06-19
author: Olaf Freund
---

The Factory PARR pipeline — **PFactory** (plan), **AIFactory** (code), **TFactory**
(verify), watched in the **CFactory** cockpit — has done plenty of small library and
API demos. This one raised the stakes: a real **three-tier web application** with a
**managed database and cache**, plus the **infrastructure-as-code to run it on AWS**,
taken from a one-paragraph brief all the way to a live service on a real EKS cluster —
and then deleted again. As always this is the honest version, including the things the
generator got wrong, because the failures are where the interesting engineering lives.

## The brief

One scenario file describing **LinkLite**, a URL shortener:

- **Web tier:** Node / TypeScript (Fastify) REST API — `POST /shorten`, `GET /r/:code`
  (302 redirect), `GET /stats/:code`, `GET /healthz`.
- **Data tier:** PostgreSQL — the source of truth for `code -> url` plus a hit counter.
- **Cache tier:** Redis — a read-through cache so hot lookups never touch Postgres.
- **Infrastructure:** Terraform for AWS — EKS, RDS PostgreSQL, ElastiCache Redis, at the
  smallest single-AZ tiers, fully destroyable.

The one precise requirement that matters later: a cache hit must **not** query the
database. That single acceptance criterion is what separates "wired up three tiers" from
"used the third tier."

## Plan and code

PFactory planned the brief in about 50 seconds and handed a signed contract to AIFactory.
AIFactory built the whole thing in one pass — **77 minutes, 9.47M tokens, $7.35** — and it
was genuinely complete: the Fastify app split into `db.ts` / `cache.ts` / route modules, a
jest suite across unit / api / integration lanes, a multi-stage `Dockerfile`, Kubernetes
manifests, a CI workflow, and an `infra/` directory of Terraform for the full AWS stack.

## Verify: where it got interesting

TFactory's verify leg **failed** — and the failure is worth being precise about. It was not
that the app was broken; it was that TFactory's test *generation* thrashed. The cache-hit
acceptance criterion (prove the database is not consulted on a hit) is subtle, and the
planner replanned that subtask to exhaustion and committed zero tests. That is a real
robustness gap in the verify leg, and it is filed as such.

So we did what a human reviewer does on a handback: we ran the app's **own** generated
test suite. It needed exactly one one-line fix — the integration test called
`redis.connect()` unconditionally even when the client was already connected — after which:

```
unit:        9 passed
api:         8 passed
integration: 5 passed   (against real Postgres + Redis)
TOTAL:      22 passed    (covers AC#1-7, including cache-hit-bypasses-Postgres)
```

The application the pipeline produced was correct. The verify leg's test-generator needs to
get better at hard assertions — an honest, useful finding rather than a varnished one.

## Deploy: three real infrastructure bugs

`terraform apply` is where generated IaC meets reality, and it surfaced three classic
first-deploy problems — none of them in the application, all of them in the infrastructure:

1. **A stale Kubernetes version.** The generated Terraform pinned EKS `1.29`, which AWS no
   longer accepts for new clusters. Bumped to `1.33`.
2. **Security groups wired to the wrong group.** The IaC allowed database and cache traffic
   from the security group it *declared* — but an EKS **managed node group uses the
   auto-created cluster security group**, not the declared one. So the pods could not reach
   Postgres or Redis, and the load balancer could not reach the NodePort. Opening the
   NodePort and the 5432/6379 paths on the real node security group fixed it.
3. **Enforced TLS to RDS.** RDS Postgres rejects unencrypted connections; the connection
   string needed `sslmode` set.

These are exactly the things a generator that learned from yesterday's docs gets wrong, and
exactly the things a human catches in twenty minutes. They are now feedback for the IaC
generation step.

## Live on AWS

With those fixed, LinkLite ran on a real EKS 1.33 cluster (one `t3.small` node), backed by
RDS `db.t4g.micro` and ElastiCache `cache.t4g.micro`, behind a public load balancer:

```
# /healthz  (web -> Postgres + Redis)
{"status":"ok"}

# POST /shorten
{"code":"3HiFqJD","shortUrl":".../r/3HiFqJD"}

# GET /r/3HiFqJD          -> HTTP 302 -> https://www.freundcloud.com/factory  (cache miss)
# GET /r/3HiFqJD again    -> HTTP 302 (served from Redis — no DB hit)
# GET /stats/3HiFqJD      -> {"hits":1}    (the cache hit did NOT increment the DB counter)

# invalid url  -> 400
# unknown code -> 404
```

That `hits:1` after two lookups is the whole point: the second redirect was served from
Redis without touching Postgres. The third tier is doing its job, live, on AWS.

## Tear it down

The brief required the stack to be destroyable, and it was. Delete the Kubernetes
LoadBalancer service first (so AWS removes the ELB before Terraform deletes its VPC), then
`terraform destroy` removes everything else — EKS, RDS, ElastiCache, VPC — leaving no
running resources and no bill.

## What this run actually shows

The pipeline took a paragraph and produced a correct, tested, containerised three-tier
application with deployable infrastructure. The application code needed one trivial fix; the
infrastructure needed three well-understood corrections that any cloud engineer would make
on a first deploy. None of that is failure — it is the realistic shape of the work, and the
PARR spine made every step legible: a planned contract, a generated build with real
evidence, a verify leg that (loudly) told us where it is still weak, and a deploy that a
human finished. That is the honest standard we hold the Factory to.
