# Factory program facts sheet, 2026-08-10 to 2026-11-15

Sources: merged-PR list (Factory-prs.txt, 166 PRs, hub #680 to #3707), origin/main docs/roadmap.md (last updated 2026-10-24), origin/main docs/rfc/*.md, `gh issue` on olafkfreund/Factory. Links: PR `https://github.com/olafkfreund/Factory/pull/N`, issue `.../issues/N`. Other-repo refs are written Repo#N. Factory deploys from main, so merged = shipped. The GitHub API rate limit was hit at the end, so some cross-repo searches (RFC-0017, RFC-0022/0023/0025) are incomplete.

Note on closed issues: of ~300+ closed in the window, nearly all are auto-filed watchdog alerts (fleet-match, job-watchdog, restart-watchdog, parr-regression). Excluding those, only 14 are human-authored. Do not quote the alert count as "issues closed".

## 1. Themes shipped in the window

1. **Compliance programme (epic #310): six of nine remaining domain epics closed on 2026-10-24.** Closed: audit logging/retention #313, secrets rotation #315, vulnerability management #317, supply-chain integrity #318, data governance/PII #320, runtime isolation #322. Still open: IAM #312, encryption at rest #314, evidence/audit-readiness #324. Evidence PRs: retention windows per framework #3650, sub-processors/residency #3649, SLSA Build L2 target #3647, manual agenix rotation accepted as risk #3652, pen-test residual accepted #3654, runtime isolation baseline AR-001 #3655, regulated projects always scrub outbound PII #3651. In November: SOC 2 TSC and ISO gap assessment #3678, risk register/SoA/SOC 2 ratings refresh #3682, control-matrix status with FFIEC column #3706, encryption policy status #3707.
2. **Access control (epic #312, still open): design and first slices.** Fleet RBAC role model and quarterly access review, intent+spec #3663 and plan #3666; cockpit per-factory scoped keys #3680; WebSocket event org filtering #3683, issue #3679 closed 2026-11-15. CFactory#500 (2026-10-26) made /api and /connect fail closed with no keys (Factory#312 slice 1).
3. **Security sweep and gates hardening (August, ~100 PRs).** Canonical `sanitize_log` #717 and SSRF guard `url_safety` #734 in factory-common; security-sink lint gate #726; gitleaks scanning #758 and PR-diff secret scan required in all five repos #925; CodeQL at security-and-quality breadth #712, actions language scanned #735, measured two-directional fork validation #770, CodeQL ratchet reusable workflow #3646 (closes epic #813, 2026-10-24); SHA-pinned actions #775/#777; liveness check for scheduled gates #764; P0 acceptance suite required on dev #942; "a gate that has never been green" scored #837. Standards additions: 3.8-3.12 and 4.11-4.12 #719, 4.13 #751/#822, 4.14 #765.
4. **Branch protection and change control.** Protection cannot be stripped by its own applier #757; public repos must accept private vulnerability reports #692; dev branches must be up to date #845; `enforce_admins` on main of the five code repos #3606 (issue #943 closed 2026-10-22); protection requires AIFactory autonomy-matrix gate #3542, TFactory ruff-format #2967, declared live CodeQL checks #2955; factory-github canonical drift required on service repos #3593; a check named "blocking" must be able to block #3586.
5. **Agentic SDLC operating model (epic #1958, still open): two of four playbook gaps closed.** Closed: control catalog keyed to control matrix #3582 (#1961, 2026-10-14), autonomy matrix generated from code #3543/#3544/#3542 (#1962, 2026-10-08), verify gate declared model-assisted with a deterministic floor (#1963, closed 2026-10-24; docs #3648). Open: model access gateway #1959, agent identity #1960 (premise-check intent #3661).
6. **Language and toolchain provisioning.** Declarative language descriptors, Swift and Kotlin onboarded #1707, ambiguous registries refused plus `add-a-language` skill #1713, descriptors registered in the verification-core drift gate #1711; Kotlin in-cluster lane (#1712, #2824/#2825); Gradle-Java lane design #3514 (issue #3151 closed 2026-10-08); a long run of Nix provisioner fixes (#996, #1001, #1007, #1010, #1011, #1015, #1019, #1021, #3584, #2143); provider-install uv port design #2993 (issue #2823 closed 2026-09-24).
7. **Job dispatch and runtime plumbing.** Ephemeral-storage limit on dispatched Jobs #3207 (AIFactory#1425); opt-in service-account token for Jobs that dispatch Jobs #2404, requiring an explicit service account #2420; opt-in GCP credential mounted as a file #952; artifact-store never packs a symlink unpack would reject #944; extension-registry: a mandatory extension must be enabled #2826; extension-registry drift check design #3583.
8. **Design records and RFCs (three new RFCs, one design-record habit).** RFC-0023 repository onboarding at scale #968 (2026-08-25), RFC-0025 planning from observed infrastructure #972 (merged 2026-10-24), RFC-0024 package-owned runtime invariants #3592 (2026-10-15, issue #818 closed). Intent/spec/plan artifacts landed for #971 terminal-status audit #3590 (13 issues filed) and fix #3595, #1003 shared runner images #3587, #2586 merger closing the loop #2820, #1710 Node vs glibc #2822. Rejected designs now recorded in a `rejected/` directory #3594 (issue #3591). Kyverno image-signature hardening: tag@digest bypass (issue #3664, closed 2026-10-30), fail-closed on unverified first-party images (issue #3665, closed 2026-11-14), skills_service digest re-registered #3668.

Smaller items usable as colour: Fides change-gate verdict assertion re-landed #695/#696; demo runbook for the three handovers #954.

## 2. RFC table (all files in docs/rfc/ on origin/main)

"Last change" = date of last commit touching the file on origin/main (git log). It is not the RFC's own Updated date. README.md in docs/rfc/ was excluded.

| File | No. | Title | Short status | Permalink | Last change |
|---|---|---|---|---|---|
| 0001-correlation-key-and-completion-event.md | 0001 | Correlation Key & Completion-Event Schema | Implemented | /rfc/correlation-key/ | 2026-10-15 |
| 0001a-completion-evidence-gates.md | 0001a | Completion-Event Evidence Gates | Implemented | /rfc/evidence-gates/ | 2026-06-14 |
| 0002-task-contract.md | 0002 | Factory Task Contract v2 | Implemented | /rfc/task-contract/ | 2026-07-17 |
| 0003-github-agentic-integration.md | 0003 | GitHub Agentic Integration | Accepted | /rfc/github-agentic/ | 2026-07-11 |
| 0004-governed-trajectory-capture.md | 0004 | Governed-Trajectory Capture | Proposed (research) | /rfc/trajectory-capture/ | 2026-06-09 |
| 0005-environment-manifest-and-toolchain-provisioning.md | 0005 | Environment Manifest & Ephemeral Toolchain Provisioning | Implemented | /rfc/environment-provisioning/ | 2026-06-17 |
| 0006-verification-assurance-levels.md | 0006 | Verification Assurance Levels & Honest Reporting | Implemented | /rfc/verification-assurance/ | 2026-10-15 |
| 0007-access-and-credential-provisioning.md | 0007 | Access Discovery & Authenticated-Test Provisioning | Implemented | /rfc/access-provisioning/ | 2026-06-17 |
| 0008-autonomous-parr-completion.md | 0008 | Autonomous PARR Completion | Partially implemented | /rfc/autonomous-completion/ | 2026-06-20 |
| 0009-ci-gated-auto-merge.md | 0009 | Provider-Agnostic CI-Gated Auto-Merge | Partially implemented | /rfc/ci-gated-auto-merge/ | 2026-06-28 |
| 0010-code-aware-planning-and-behavioral-equivalence.md | 0010 | Code-Aware Planning over Existing Repositories | Implemented | /rfc/code-aware-planning/ | 2026-06-20 |
| 0011-label-driven-intake-and-difficulty-tiers.md | 0011 | Label-Driven Intake & Difficulty Tiers | Implemented | /rfc/label-driven-intake/ | 2026-06-20 |
| 0012-external-knowledge-grounding.md | 0012 | External-Knowledge Grounding from Backstage | Implemented | /rfc/external-knowledge-grounding/ | 2026-06-20 |
| 0013-deployment-aware-planning.md | 0013 | Deployment-Aware Planning | Implemented | /rfc/deployment-aware-planning/ | 2026-07-11 |
| 0014-cost-aware-model-and-runtime-routing.md | 0014 | Cost-Aware, Capability-Aware Model & Runtime Routing | Accepted (v1 scope) | /rfc/cost-aware-routing/ | 2026-07-11 |
| 0015-spec-driven-interop-and-validated-gap-features.md | 0015 | Spec-Driven Interop, Adversarial Spec Review, Traceability & Declarative Extension Registry | Implemented | /rfc/spec-driven-interop/ | 2026-06-28 |
| 0016-horizontal-concurrent-execution.md | 0016 | Horizontal & Concurrent Execution | Core implemented | /rfc/horizontal-concurrent-execution/ | 2026-06-27 |
| 0017-full-job-native-execution-and-scale-out.md | 0017 | Full Job-Native Default Execution & Control-Plane Scale-Out | In progress | /rfc/job-native-scale-out/ | 2026-06-29 |
| 0018-regression-suite-and-continuous-verification.md | 0018 | Regression Suite & Continuous Verification | Implemented (shipped 2026-06-22) | /rfc/regression-suite-and-continuous-verification/ | 2026-06-22 |
| 0019-agent-native-planning-control-plane.md | 0019 | Agent-Native Planning Control Plane | Proposed | /rfc/agent-native-planning-control-plane/ | 2026-07-25 |
| 0019-spike-build-vs-integrate.md | 0019 spike | RFC-0019 Phase 0 Spike: build natively vs integrate utter.ae | Complete, awaiting decision | /rfc/agent-native-planning-control-plane-spike/ | 2026-07-25 |
| 0020-multi-provider-git-integration-and-tenant-configured-projects.md | 0020 | Multi-Provider Git Integration and Tenant-Configured Projects | Proposed | /rfc/multi-provider-git-integration/ | 2026-07-25 |
| 0021-earned-memory-and-promotion-gates.md | 0021 | Earned Memory and Promotion Gates | Proposed (§1 corrected 2026-07-27) | /rfc/earned-memory-and-promotion-gates/ | 2026-07-27 |
| 0022-work-item-and-code-seams.md | 0022 | Work-Item and Code Seams | Proposed | /rfc/work-item-and-code-seams/ | 2026-07-27 |
| 0023-repository-onboarding-at-scale.md | 0023 | Repository Onboarding at Scale | Proposed | /rfc/repository-onboarding-at-scale/ | 2026-08-25 |
| 0024-package-owned-runtime-invariants.md | 0024 | Package-Owned Runtime Invariants | Proposed | /rfc/package-owned-runtime-invariants/ | 2026-10-15 |
| 0025-planning-from-observed-infrastructure.md | 0025 | Planning from Observed Infrastructure | Proposed | /rfc/planning-from-observed-infrastructure/ | 2026-10-24 |

No RFC in the directory says "Superseded". Status lines for 0017 and 0016 are long; the short labels above are my reading of them.

RFCs created or changed inside the window: 0023 (new 08-25), 0025 (new, merged 10-24), 0024 (new 10-15), plus 0001 and 0006 edited 10-15 (0006 gained a "See also RFC-0024" line). Everything else last changed before 2026-08-10.

### Status lines contradicted by evidence

- **RFC-0020 "Proposed" vs shipped.** Epic Factory#361 closed 2026-07-28; roadmap.md calls it "implemented ... all phases closed". Merged PRs: CFactory#206 (shared git-provider abstraction, GitLab), #208 (issue import), #209 (tenant-scoped git config + Settings panel), #210 (encrypted per-tenant credential store); AIFactory#1025, TFactory#824, PFactory#358. The CFactory MCP here also exposes git-connection tools. The RFC file was last touched 2026-07-25, before those landed, so the Status line was never updated.
- **RFC-0019 "Proposed" vs shipped.** CFactory#200 (planning cards table + CRUD, Phase 1), CFactory#203 (programmatic-equivalence parity check, Phase 5), CFactory#205 (GitHub card<->issue sync, Phase 6), and `/.well-known/agent-skills/index.json` in PFactory#351, AIFactory#1019, TFactory#816 (Phase 4), all merged 2026-07-25. Epic #302 closed 2026-07-26 (its body still says "Proposed - not scheduled"). The CFactory MCP in this environment exposes card create/move/plan/run tools. Phases 2 and 3 (MCP board tools, board to intake) are not individually verified by me.
- **RFC-0019 spike "Complete, awaiting decision"** recommends build native; the native build is what shipped (CFactory#200 etc.), so the decision has in effect been taken.
- **RFC-0017 "In progress" vs roadmap.** The roadmap says the Job-native build and verify default flips "went live in July". The RFC (last changed 2026-06-29) says they are not yet live. I did not find a merged PR proving the flip (search hit the rate limit); treat as unverified, one of the two documents is stale.
- **RFC-0014 "Accepted (v1 scope)"** vs roadmap listing cost-aware model routing as shipped in the July competitive-gap epic #270 (closed 2026-07-23); `cost_router_core` is vendored in PFactory (PFactory#374). Consistent with "v1 accepted"; could be moved to Implemented only if the RFC's v1 scope is confirmed met. Unverified.
- **RFC-0021 "Proposed" vs partial work.** Epic #389 is open, but AIFactory#1035 (Phase 0, project-level memory, 2026-07-27), AIFactory#1856 (duplicate-rate baseline, 2026-10-24) and AIFactory#2019 / PFactory#992 / TFactory#1497 (Phase 1 exact-repeat gate, 2026-11-14/15) are merged. Better label: In progress.
- **RFC-0001 vs roadmap.** Roadmap says the legacy completion envelope is gone and every service speaks CloudEvents (July). RFC-0001 Status says "Implemented ... Version 1.3, Updated 2026-07-11" and I did not check whether its body describes the CloudEvents cutover. Flag for a check, not a confirmed contradiction.
- **RFC-0007**: no contradiction found. Roadmap (June section) describes it as "proposed"; the RFC says Implemented (updated 2026-06-17). The roadmap June bullet is stale (see section 3).
- No contradiction found for 0022, 0023, 0024, 0025: no merged implementation PRs found. RFC-0024 has a PFactory pilot referenced in its own text (PFactory#622); the hub carries an approved plan (commit 5632c2d) but implementation is not complete.

## 3. docs/roadmap.md: done or stale

The file's own "last updated" is 2026-10-24 but the narrative stops at July.

Stale or done:
- "Seven further epics remain open" and the "Now" list of nine domains: now six are closed (#313, #315, #317, #318, #320, #322, all 2026-10-24). Open: #312, #314, #324. Also, "Now" lists #324 as open with the control matrix; that has advanced (#3706, #3682, #3678).
- "Image signature verification currently fails for every fleet image (#430)": issue closed 2026-08-05. Kyverno follow-ups #3664 and #3665 closed 10-30 and 11-14.
- "Five production CronJobs exist only as cluster state (#429)": closed 2026-07-30.
- "Epic #431 silent fallbacks ... running alongside": closed 2026-08-01.
- Next list, "GTM demos (epic #240)": closed 2026-08-22.
- Roadmap's epic #270 (competitive-gap) closed 2026-07-23 and #241 (pre-demo hardening) closed 2026-07-17; both are listed under "Recently shipped (July)", which is accurate but now old.
- "RFC-0007 (proposed; epic with sub-issues filed)" in the June section: RFC-0007 Status is Implemented.
- "Multi-node workspace consumption remains" (RFC-0017) and the RFC-0017 status: see section 2, unverified.
- "Next: Repository onboarding (RFC-0023), Planning from observed infrastructure (RFC-0025)": RFCs exist but no implementation found; still "next". The RFC-0025 claim that no planning agent reads the account with the broker is unverified.
- "Jira and Bitbucket (RFC-0022, epic #392)": still open, correct.
- "Earned memory (RFC-0021, epic #389)": still open but Phase 0 and Phase 1 PRs have merged, so the roadmap understates progress.
- Missing from the roadmap entirely: Agentic SDLC epic #1958, the August security/gates sweep, the CodeQL epic #813 (closed 10-24), branch protection `enforce_admins` (#943), RFC-0024, language descriptors, the RBAC design.
- RFC-0020 and RFC-0018 are described as *implemented* in the roadmap while RFC-0020 says Proposed (see section 2).

## 4. Real "next" list: open epics on Factory (checked 2026-11-15)

Label `epic` returns #1958, #324, #314, #312, #310 plus playbook children #1959, #1960; a title search for "[Epic]" adds #389 and #392.

- **#310 Security & compliance programme** (parent): open; three child domain epics left.
  - **#312 IAM & access control** (MFA, retire shared wildcard token, RBAC, access reviews): in design/slices (#3663, #3666, #3680, #3683; follow-up #3679 closed 11-15).
  - **#314 Encryption at rest & key management** (DB/MinIO/KMS): policy status doc #3707, implementation still open.
  - **#324 Evidence & audit-readiness** (control matrix, automated evidence, gap assessments): matrix/gap docs #3706, #3682, #3678 landed, epic open.
- **#1958 Agentic SDLC operating model**: open children #1959 model access gateway (routes, not provider keys in every service) and #1960 agent identity distinct from human identity (intent #3661).
- **#389 RFC-0021 earned memory and promotion gates**: Phase 1 exact-repeat gate merged 2026-11-14/15 in AIFactory/PFactory/TFactory.
- **#392 RFC-0022 work-item and code seams (Jira, Bitbucket, mixed tenants)**: no implementation PRs seen.
- Newly filed, not epics: #3708 (PFactory and TFactory agents inherit the control plane's env; closed 2026-11-15, so already done by the time of this check).
- Not epics but in the roadmap's Next list, no epic found: RFC-0023 repository onboarding, RFC-0025 planning from observed infrastructure, RFC-0024 invariants rollout (PFactory first).

Unchecked: whether other-repo epics (AIFactory, PFactory, TFactory, CFactory) should be added; this sheet covers the Factory hub only.
