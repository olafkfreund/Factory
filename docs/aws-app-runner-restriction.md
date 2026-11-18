---
layout: default
title: "AWS App Runner: account cannot create new services"
permalink: /aws-app-runner-restriction/
---

# AWS App Runner: account cannot create new services

Every Factory AWS deploy path (the `run-aws-demo` conductor,
`templates/cloud-deploy/aws`, the AIFactory deploy templates) creates an
**AWS App Runner** service. On some accounts AWS has closed App Runner to new
services, and `terraform apply` fails at `CreateService`:

```
InvalidRequestException: Account <id> can't create new App Runner services.
```

First seen on account 533267307120, eu-west-2, on 2026-11-18 (Factory#3839;
request ids 12b71da4-65d4-49f3-adda-4e608c2495dd and
f8bad538-28d9-478f-bb25-ff6803d8d753). The same account deployed the demo on
2026-06-11, so this is an account-level change, not a template bug. ECR, IAM
and image push still work.

## What the Factory does now

- The conductor (`.claude/skills/run-aws-demo/conductor.sh`) **fails closed**:
  a failed apply stops the run, quotes the AWS error, prints the owner step
  below, tears down and exits non-zero. It never prints "GREEN" unless the
  acceptance tests passed against non-empty live URLs.
- A read-only pre-flight (`aws apprunner list-services`) catches wrong
  credentials, region or permissions before anything is built. It **cannot**
  detect this restriction: no non-creating eligibility check is known, and a
  canary `CreateService` would create a billable resource. The restriction
  therefore shows at the apply step.

## Owner step (cannot be done by an agent)

1. In the AWS console open **Support Center > Create case > Account and
   billing / Service limit** (or Technical support) for the affected account.
2. Ask: "Please enable creation of new AWS App Runner services in region
   eu-west-2 for account <id>. CreateService returns `InvalidRequestException:
   Account <id> can't create new App Runner services` (request ids above)."
3. Meanwhile, use an account that can still create services. Whether support
   can lift the restriction is not confirmed.
4. After AWS confirms, rerun `/run-aws-demo` once; it is the only real proof
   that the template and conductor work end to end.

## Recommended follow-up (design decision, not done here)

Move the AWS target off App Runner to **ECS Fargate** (or Lightsail
containers) so the Factory does not depend on one closed service. This changes
the compute target in every AWS template and is tracked as a follow-up to
Factory#3839.
