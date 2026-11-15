---
layout: post
title: "What shipped in the Factory, August to November 2026"
subtitle: "The program view: a compliance programme that closed six domain epics, a security sweep across the five repos, branch protection as code, and four product posts with the detail. Several of the access-control pieces are still shadow or warn-only."
date: 2026-11-15 09:00:00
author: Olaf Freund
---

This is the program update for 10 August to 15 November 2026. The Factory hub has
no releases, so "shipped" means merged to `main`, which deploys. The record is the
[merged pull request list](https://github.com/olafkfreund/Factory/pulls?q=is%3Apr+is%3Amerged+base%3Amain).
The products have their own posts, with release tags:

- [PFactory](https://pfactory.freundcloud.com/blog/2026/11/15/what-shipped-august-to-november/): 26 releases, v0.6.17 to v0.6.42. Several replicas on a shared store, org-scoped access control mostly in shadow mode.
- [AIFactory](https://aifactory.freundcloud.com/blog/what-shipped-august-to-november): releases v3.6.74 to v3.10.16. Auto-merge gated on evidence, and the coding agent treated as untrusted.
- [TFactory](https://tfactory.freundcloud.com/blog/2026/11/15/what-shipped-august-to-november/): 24 releases, v0.9.26 to v0.9.49. Verdicts that say only what was measured, and Kotlin and Java run in-cluster.
- [CFactory](https://cfactory.freundcloud.com/blog/2026/11/15/what-shipped-august-to-november/): no releases, so the post lists merged pull requests. A cockpit that does not overstate, and stalled work that stays on the board.

## The compliance programme

[Epic #310](https://github.com/olafkfreund/Factory/issues/310) is audit readiness for ISO 27001, SOC 2 and other frameworks. On 2026-10-24 six
of its nine remaining domain epics closed: audit logging
([#313](https://github.com/olafkfreund/Factory/issues/313)), secrets rotation ([#315](https://github.com/olafkfreund/Factory/issues/315)), vulnerability management
([#317](https://github.com/olafkfreund/Factory/issues/317)), supply-chain integrity ([#318](https://github.com/olafkfreund/Factory/issues/318)), data governance
([#320](https://github.com/olafkfreund/Factory/issues/320)) and runtime isolation ([#322](https://github.com/olafkfreund/Factory/issues/322)). The evidence went in
as documents and decisions, for example retention windows per framework
([#3650](https://github.com/olafkfreund/Factory/pull/3650)), sub-processors and residency ([#3649](https://github.com/olafkfreund/Factory/pull/3649)), a SLSA Build L2
target ([#3647](https://github.com/olafkfreund/Factory/pull/3647)) and the runtime-isolation baseline
([#3655](https://github.com/olafkfreund/Factory/pull/3655)). Manual secret rotation and a pen-test residual were accepted
as risks, on the record ([#3652](https://github.com/olafkfreund/Factory/pull/3652), [#3654](https://github.com/olafkfreund/Factory/pull/3654)).

In November the work moved to the assessments: a SOC 2 and ISO gap assessment
([#3678](https://github.com/olafkfreund/Factory/pull/3678)), a refreshed risk register and statement of applicability
([#3682](https://github.com/olafkfreund/Factory/pull/3682)), and control-matrix and encryption-policy status
([#3706](https://github.com/olafkfreund/Factory/pull/3706), [#3707](https://github.com/olafkfreund/Factory/pull/3707)).

Three domain epics are still open: IAM ([#312](https://github.com/olafkfreund/Factory/issues/312)), encryption at rest
([#314](https://github.com/olafkfreund/Factory/issues/314)) and evidence and audit-readiness ([#324](https://github.com/olafkfreund/Factory/issues/324)).

## Access control: designs merged, implementation in progress

IAM ([epic #312](https://github.com/olafkfreund/Factory/issues/312)) has its designs merged in the hub: the fleet role model
and quarterly access review ([#3663](https://github.com/olafkfreund/Factory/pull/3663), [#3666](https://github.com/olafkfreund/Factory/pull/3666)), per-factory
cockpit keys ([#3680](https://github.com/olafkfreund/Factory/pull/3680)) and WebSocket event filtering by org
([#3683](https://github.com/olafkfreund/Factory/pull/3683)). Those are hub design and plan documents. The runtime pieces are on `dev` in the
product repos and not released: per-factory tokens
([CFactory#510](https://github.com/olafkfreund/CFactory/pull/510)) and org-filtered `/ws/events`
([PFactory#994](https://github.com/olafkfreund/PFactory/pull/994),
[TFactory#1500](https://github.com/olafkfreund/TFactory/pull/1500),
[AIFactory#2027](https://github.com/olafkfreund/AIFactory/issues/2027)).
What is released: CFactory returns 401 on `/api` and `/connect` when no keys
are set ([CFactory#500](https://github.com/olafkfreund/CFactory/pull/500)).
Most of the rest is not enforcing yet: PFactory runs role checks on
task routes in shadow mode ([PFactory v0.6.38](https://github.com/olafkfreund/PFactory/releases/tag/v0.6.38)),
TFactory does the same ([TFactory v0.9.46](https://github.com/olafkfreund/TFactory/releases/tag/v0.9.46)),
and CFactory's events auth is warn-only ([CFactory#502](https://github.com/olafkfreund/CFactory/pull/502)). Each product
post says which flag turns enforcement on.

## A security sweep across the five repos

August was a security and gates sweep. A shared `sanitize_log`
([#717](https://github.com/olafkfreund/Factory/pull/717)) and SSRF guard ([#734](https://github.com/olafkfreund/Factory/pull/734)) went into the common library, a
security-sink lint gate was added ([#726](https://github.com/olafkfreund/Factory/pull/726)), and secret scanning with
gitleaks was made required on pull requests in all five repos
([#758](https://github.com/olafkfreund/Factory/pull/758), [#925](https://github.com/olafkfreund/Factory/pull/925)). CodeQL runs at security-and-quality breadth
([#712](https://github.com/olafkfreund/Factory/pull/712)),
and a reusable CodeQL ratchet workflow closed [epic #813](https://github.com/olafkfreund/Factory/issues/813)
([#3646](https://github.com/olafkfreund/Factory/pull/3646)). GitHub Actions are pinned to commit SHAs
([#775](https://github.com/olafkfreund/Factory/pull/775), [#777](https://github.com/olafkfreund/Factory/pull/777)).

## Branch protection and change control

Protection cannot be stripped by its own applier ([#757](https://github.com/olafkfreund/Factory/pull/757)), and
`enforce_admins` is on for `main` of the five code repos ([#3606](https://github.com/olafkfreund/Factory/pull/3606)). A check
named "blocking" must be able to block ([#3586](https://github.com/olafkfreund/Factory/pull/3586)), and the dev branches
must be up to date ([#845](https://github.com/olafkfreund/Factory/pull/845)).

## The agentic SDLC operating model

[Epic #1958](https://github.com/olafkfreund/Factory/issues/1958) is still open. A control catalog keyed to the control matrix
([#3582](https://github.com/olafkfreund/Factory/pull/3582)) and a generated autonomy matrix
([#3543](https://github.com/olafkfreund/Factory/pull/3543), [#3544](https://github.com/olafkfreund/Factory/pull/3544)) landed, and the verify gate is declared
model-assisted with a deterministic floor ([#3648](https://github.com/olafkfreund/Factory/pull/3648)). The model access gateway
([#1959](https://github.com/olafkfreund/Factory/issues/1959)) and agent identity ([#1960](https://github.com/olafkfreund/Factory/issues/1960)) are open.

## Languages, jobs and image signatures

- Declarative language descriptors onboarded Swift and Kotlin
  ([#1707](https://github.com/olafkfreund/Factory/pull/1707)), and a Kotlin in-cluster lane followed ([#2824](https://github.com/olafkfreund/Factory/pull/2824), [#2825](https://github.com/olafkfreund/Factory/pull/2825)).
- Dispatched Jobs have an ephemeral-storage limit ([#3207](https://github.com/olafkfreund/Factory/pull/3207)). A Job that dispatches
  Jobs needs an opt-in service-account token ([#2404](https://github.com/olafkfreund/Factory/pull/2404)).
- Kyverno image-signature checks: the tag@digest bypass ([#3664](https://github.com/olafkfreund/Factory/issues/3664)) and
  unverified first-party images ([#3665](https://github.com/olafkfreund/Factory/issues/3665)) were closed.

## New RFCs

Three RFCs were added, all *Proposed*: repository onboarding at scale
([RFC-0023](/rfc/repository-onboarding-at-scale/), [#968](https://github.com/olafkfreund/Factory/pull/968)), package-owned runtime
invariants ([RFC-0024](/rfc/package-owned-runtime-invariants/), [#3592](https://github.com/olafkfreund/Factory/pull/3592)) and
planning from observed infrastructure
([RFC-0025](/rfc/planning-from-observed-infrastructure/), [#972](https://github.com/olafkfreund/Factory/pull/972)). Rejected designs are now
kept in a `rejected/` directory ([#3594](https://github.com/olafkfreund/Factory/pull/3594)). The [RFC index](/rfc/) shows each
RFC's own status. Some of those statuses lag the code, which is a separate task.

## In progress

Merged to `dev` in the product repos on 14 and 15 November and not in any release:

- Scoped `acw_` keys on WebSockets and org-filtered `/ws/events`, in PFactory
  ([#991](https://github.com/olafkfreund/PFactory/pull/991),
  [#994](https://github.com/olafkfreund/PFactory/pull/994)), TFactory
  ([#1496](https://github.com/olafkfreund/TFactory/pull/1496),
  [#1500](https://github.com/olafkfreund/TFactory/pull/1500)) and AIFactory
  ([#2017](https://github.com/olafkfreund/AIFactory/issues/2017),
  [#2027](https://github.com/olafkfreund/AIFactory/issues/2027)).
- An allowlisted environment for agent child processes in PFactory
  ([#997](https://github.com/olafkfreund/PFactory/pull/997)) and TFactory
  ([#1501](https://github.com/olafkfreund/TFactory/pull/1501)). AIFactory shipped its
  own earlier, in [v3.10.3](https://github.com/olafkfreund/AIFactory/releases/tag/v3.10.3)
  ([#1762](https://github.com/olafkfreund/AIFactory/issues/1762)); what is on `dev` there is
  keeping the control plane's GitHub token out of agent children
  ([#2030](https://github.com/olafkfreund/AIFactory/issues/2030)).
- An exact-repeat gate on memory writers (RFC-0021 Phase 1)
  ([PFactory#992](https://github.com/olafkfreund/PFactory/pull/992),
  [TFactory#1497](https://github.com/olafkfreund/TFactory/pull/1497),
  [AIFactory#2019](https://github.com/olafkfreund/AIFactory/issues/2019)).
- CFactory's model-gateway route
  ([#513](https://github.com/olafkfreund/CFactory/pull/513)) and per-factory tokens
  ([#510](https://github.com/olafkfreund/CFactory/pull/510)).

Open epics: [#310](https://github.com/olafkfreund/Factory/issues/310),
[#312](https://github.com/olafkfreund/Factory/issues/312), [#314](https://github.com/olafkfreund/Factory/issues/314), [#324](https://github.com/olafkfreund/Factory/issues/324), [#1958](https://github.com/olafkfreund/Factory/issues/1958),
[#389](https://github.com/olafkfreund/Factory/issues/389) (earned memory) and [#392](https://github.com/olafkfreund/Factory/issues/392) (Jira and Bitbucket seams).
