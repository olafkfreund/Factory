# Agentic-AI Governance

- **Domain:** Agentic-AI governance (Factory#323)
- **Parent epic:** Factory#310
- **Frameworks addressed:**
  - **NIST AI RMF 1.0** — GOVERN (policies, roles, accountability for AI risk), MAP (context and model inventory), MEASURE (evaluation, test-and-eval before deployment), MANAGE (risk response, monitoring, incident handling)
  - **ISO/IEC 42001:2023** — AI management system: A.6 (AI system life cycle — objectives, verification/validation, deployment), A.7 (data for AI systems), A.8 (information for interested parties), A.9 (responsible use, human oversight), A.10 (third-party / model-provider relationships)
  - **EU AI Act** — provider obligations for the AI system life cycle: risk management (Art. 9), data governance (Art. 10), technical documentation and logging (Arts. 11-12), transparency (Art. 13), human oversight (Art. 14), accuracy/robustness/cybersecurity (Art. 15). Scoped as a general-purpose development tool; not asserting a specific risk classification here.
  - **ISO/IEC 27001:2022** — A.5.23 (information security for use of cloud/AI services), A.8.25-A.8.29 (secure development life cycle, security testing, outsourced development), A.5.29-A.5.30 (during disruption — cross-references BC/DR, Factory#321)
  - **SOC 2** — CC5 (control activities), CC6.1/CC6.6 (logical access, boundary protection), CC7.1-CC7.2 (change/anomaly monitoring), CC8.1 (change management); SOX ITGC change-control overlap tracked in Factory#316

## Purpose

This document is the AI-specific control domain for the Factory fleet: the governance
that applies specifically because autonomous LLM agents plan, write, and verify code that
can change a regulated system. It is the assessor-facing answer to the hardest question an
autonomous code factory faces — *can an AI change a regulated system, and is every agent
action attributable, bounded, and reversible?*

It does not restate the general controls (access, encryption, logging, DR) that live in
their own domain documents. It covers the four AI-specific control areas an assessor
mapping NIST AI RMF / ISO 42001 / the EU AI Act will look for:

1. Model governance — what models are approved, how a model change is evaluated and gated.
2. Trust boundary for agent inputs — prompt-injection containment and egress control.
3. Trust boundary for agent authority — signed task contracts and human-in-the-loop gates.
4. Independent verification — evidence gates and assurance levels applied to AI output.

This domain is a **relative strength** for the fleet. The engineering controls below are
real, shipped, and exceed what most AI-assisted SDLCs have. The gaps are governance
*artifacts and lifecycle* around those controls, not missing mechanism.

## Current state (grounded)

As of 2026-07-24. All file paths are real and relative to the repo roots under
`/mnt/data/Source-home/GitHub/`.

### Signed task contracts (agent-authority trust boundary) — credited

The handoff from an upstream authority (PFactory authoring, CFactory governance) to the
AIFactory builder is cryptographically verified, not a trusted string:

- `AIFactory/apps/backend/trusted_plan.py` — an **HMAC-SHA256 signature** over the
  canonical plan JSON plus approval metadata (`sign_plan`, `verify_plan_signature`,
  `verify_trusted_plan`). Any tamper to the plan or the approval envelope invalidates the
  signature. A `CONTRACT_VERSION` guards against signer/verifier drift, and a completeness
  checklist (unique subtask ids, acyclic `depends_on`) must also pass before a plan is
  treated as trusted-complete. This is what lets the builder skip re-planning and go
  straight to execution *only* for a plan a governance authority actually signed.
- Formalized in `Factory/docs/rfc/0002-task-contract.md`.
- Maps to: NIST AI RMF MANAGE (bounded authority), EU AI Act Art. 12 (traceability),
  ISO 42001 A.6 (life-cycle control), SOC 2 CC8.1 (change authorization).

### Prompt-injection containment (agent-input trust boundary) — credited

External attacker-controllable text (GitHub issue/PR bodies, `HUMAN_INPUT.md`, fetched
pages, KG memory) is contained before it reaches a model:

- `AIFactory/apps/backend/security/prompt_guard.py` — `wrap_untrusted()` is the single
  containment helper applied at every untrusted sink: delimiter-wraps the content,
  neutralizes attempts to close the wrapper from inside, and prepends a "treat as DATA,
  not instructions" preamble. The module is explicit that this is a *mitigation, not a
  guarantee*.
- `AIFactory/apps/backend/runners/github/sanitize.py` — strips HTML comments (hidden
  instructions), enforces length limits, validates AI output format before acting (OWASP
  LLM guidance).
- `AIFactory/apps/backend/security/content_scan.py` — configurable scan of untrusted text.
- Threat model: `Factory/docs/security/untrusted-content-threat-model.md`.
- Maps to: EU AI Act Art. 15 (cybersecurity/robustness), NIST AI RMF MANAGE, ISO 27001
  A.8.28 (secure coding).

### Egress control (agent-action trust boundary) — credited

- `AIFactory/apps/backend/security/egress.py` — a command-layer, fail-closed egress guard
  (`off`/`deny`/`allowlist` via `AIFACTORY_EGRESS_POLICY`). In allowlist mode a network
  command whose targets cannot be fully parsed is **blocked, not allowed**. Documented as
  the in-process compensating control for a pod-level default-deny NetworkPolicy (runtime
  isolation is Factory#322).

### Model configuration and routing — credited (config exists)

Per-stage model selection is real and centralized:

- `AIFactory/apps/backend/phase_config.py` — `MODEL_ID_MAP` is the fleet's model inventory
  in code (Opus/Sonnet/Haiku aliases -> pinned model ids, with legacy pins retained), plus
  per-phase thinking-budget mapping.
- `AIFactory/apps/backend/routing_policy.py` — RFC-0014 per-stage routing
  (planning/coding/qa -> tiers), opt-in and **fail-closed** (a broken policy falls through
  to defaults, never mis-routes).
- `PFactory/apps/backend/core/model_config.py` — utility-model config for PFactory.
- A LiteLLM admin gateway with a KMS-wrapped master key and per-tenant enforcement exists
  (`AIFactory/apps/web-server/server/services/litellm_admin_client.py`), giving a real
  choke point where an approved-model list could be enforced.
- Maps to: NIST AI RMF MAP (model inventory), ISO 42001 A.6/A.10. **Note:** this is
  configuration, not a *governance* artifact — see gaps.

### Independent verification and evidence gates (output trust boundary) — credited (strong)

AI output is not trusted on the agent's say-so; an independent service must prove it:

- **Evidence gates** — `Factory/docs/rfc/0001a-completion-evidence-gates.md`: a completion
  claim must carry verifiable evidence, not a self-reported "done".
- **Coder test-honesty gate** (#851) — no green checkbox without a real test command that
  ran.
- **Verification Assurance Levels** — `Factory/docs/rfc/0006-verification-assurance-levels.md`,
  enforced in TFactory (`TFactory/apps/backend/agents/verification_gate.py`,
  `equivalence_runner.py`, `deploy_policy.py`). Independent "dishonest-coder" verification.
- **Standards-conformance gate** (RFC-0012) — `standards_conformance` fails the build when
  a retrieved standard is ignored (`TFactory/apps/backend/prompts_pkg/prompts.py`;
  authoring side in `AIFactory/apps/backend/prompts_pkg/prompts.py`).
- **Governed trajectory capture** — `Factory/docs/rfc/0004-governed-trajectory-capture.md`:
  agent actions are recorded for attribution.
- Maps to: NIST AI RMF MEASURE (test-and-eval before deployment), EU AI Act Arts. 9/15,
  ISO 42001 A.6.2, SOC 2 CC7/CC8.

### Output secret-scanning — partial credit

- `AIFactory/apps/backend/security/git_validators.py` scans **staged files** for secrets
  before commit (`scan_files` from `scan_secrets`). This is a real output-side control, but
  it is secret-*pattern* based — it is not a broader data-loss / exfiltration scan (see
  gaps).

## Gaps

Prioritized. Each is an artifact- or lifecycle-level gap, not a missing mechanism.

1. **No formal AI/model governance policy (no approved-model registry, no model cards, no
   model-swap eval gate).** `phase_config.MODEL_ID_MAP` and `routing_policy` are
   configuration a developer can edit; there is no governance artifact defining which
   models are *approved* for production, no model cards (provider, version, intended use,
   known limitations, eval results), and no gate requiring an evaluation to pass before a
   new/changed model is promoted. NIST AI RMF MEASURE and ISO 42001 A.6.2 both expect a
   documented test-and-eval step before a model change reaches production. *(config exists;
   governance does not.)*

2. **No output-side DLP beyond secret-scan.** `git_validators.py` catches secret patterns
   in staged files, but there is no scan of agent-authored commit content, PR titles/bodies,
   or comments for data exfiltration (embedded credentials via novel formats, PII,
   customer data, injected callback URLs). Prompt-injection wrapping is a mitigation, not a
   guarantee, so a successful injection could still cause the agent to write sensitive data
   into an output artifact that no gate inspects. Maps to EU AI Act Art. 15, ISO 27001
   A.8.25, SOC 2 CC6.6.

3. **Trusted-plan signing keys have no rotation or revocation flow.** `trusted_plan.py`
   loads keys from `AIFACTORY_TRUSTED_PLAN_KEY_<AUTHORITY>` env vars. There is no key id
   (`kid`) in the envelope, no expiry on a signature, and no documented rotation or
   revocation procedure — a leaked authority key is valid indefinitely and cannot be
   distinguished from a new one. This weakens the strongest control in the domain. Maps to
   ISO 27001 A.8.24 (key management), SOC 2 CC6.1; cross-references Secrets management
   (Factory#315).

4. **No model provenance / version pinning discipline as an evidenced control.** Model ids
   are pinned in `MODEL_ID_MAP`, but there is no recorded provenance trail tying a given
   build's output to the exact model id + provider + routing decision that produced it, as
   an assessor-checkable artifact. Trajectory capture (RFC-0004) records actions; it does
   not yet surface a per-build "which model, which version, which route" attestation. Maps
   to EU AI Act Art. 12 (logging), NIST AI RMF MAP.

5. **Human-oversight controls exist but are not documented as a control mapping.** HITL
   confirm gates exist in code (intake/poller, CLI confirm paths) and the signed-contract
   handoff enforces upstream approval, but there is no written control statement mapping
   *"no autonomous change to a regulated system without human approval"* to SOX
   change-control / EU AI Act Art. 14 (human oversight), with pointers to where each gate
   lives and what evidence it emits. The mechanism is ahead of the documentation.

6. **No AI-incident response linkage.** No documented procedure for an AI-specific incident
   (model producing unsafe output, successful prompt injection, model-provider outage or
   deprecation). Cross-references Incident response (Factory#319) — this domain owns the
   AI-specific playbook content.

## Remediation plan

Phased. Phase 1 closes the highest-risk, lowest-effort governance gaps; later phases build
the evaluation and DLP machinery.

### Phase 1 — Governance artifacts (documentation-led, low mechanism change)

- Write the **AI/model governance policy**: approved-model registry (a versioned
  `models.yaml` or equivalent listing each approved model id, provider, intended stage,
  and status), and a **model card** per approved model. Seed the registry from the real
  `MODEL_ID_MAP`.
- Write the **HITL -> change-control mapping**: a control statement naming each human-approval
  gate (signed-contract handoff, intake confirm, PR merge approval) and the evidence each
  emits, mapped to SOX ITGC / EU AI Act Art. 14. Cross-reference Factory#316.
- Document the **AI-incident playbook** (unsafe output, injection success, provider
  deprecation) and link it from Factory#319.

### Phase 2 — Trusted-plan key lifecycle

- Add a key id (`kid`) and issued-at/expiry to the approval envelope in `trusted_plan.py`
  (bump `CONTRACT_VERSION`; keep verify-side backward compatibility for unexpired v2 plans).
- Define and document a rotation + revocation procedure (rotate on a schedule and on
  suspected compromise; a revoked `kid` fails verification). Wire keys through the existing
  secrets/rotation broker (Factory#315, credential broker #292) rather than bare env vars.

### Phase 3 — Model-swap eval gate

- Define a minimal evaluation suite (a fixed set of representative tasks scored by the
  existing TFactory verification path) that must pass before a model id is added to or
  changed in the approved-model registry. Gate the registry change in CI. This reuses
  RFC-0018 regression infrastructure rather than building a new eval harness.

### Phase 4 — Output-side DLP and model-provenance attestation

- Extend the pre-output scan (`git_validators.py` sink) from secret-pattern-only to a DLP
  pass over agent-authored commit/PR/comment content (PII, customer-data markers, novel
  credential formats, injected URLs); fail-closed on high-confidence hits.
- Emit a per-build **model-provenance attestation** (model id + provider + routing decision
  + trusted-plan `kid`) into the existing evidence/trajectory store, so an assessor can tie
  any output to the exact model that produced it.

## Acceptance criteria

- [ ] AI/model governance policy published under `Factory/docs/compliance/policies/`.
- [ ] Approved-model registry exists (versioned), seeded from `phase_config.MODEL_ID_MAP`,
      with a model card per approved model.
- [ ] Model-swap eval gate: no model added to / changed in the registry without a
      documented evaluation passing; enforced in CI.
- [ ] Output-side DLP scan runs on agent-authored commit content, PR bodies, and comments,
      fail-closed on high-confidence hits — beyond the current secret-pattern scan.
- [ ] Trusted-plan signing keys have a documented rotation + revocation procedure; envelope
      carries a key id and expiry; keys sourced from the secrets broker, not bare env vars.
- [ ] Per-build model-provenance attestation (model id + version + route + trusted-plan
      `kid`) is recorded and retrievable for any build.
- [ ] Documented HITL -> change-control mapping ("no autonomous change to a regulated system
      without human approval") with evidence pointers, cross-referenced to Factory#316/#319.
- [ ] AI-specific incident playbook documented and linked from Factory#319.

## Evidence artifacts

Artifacts an assessor can inspect today (existing) or that this plan produces (planned):

| Control | Artifact | Status |
|---|---|---|
| Signed task contract | `AIFactory/apps/backend/trusted_plan.py`; `Factory/docs/rfc/0002-task-contract.md` | Existing |
| Prompt-injection containment | `AIFactory/apps/backend/security/prompt_guard.py`, `.../runners/github/sanitize.py`, `.../security/content_scan.py`; `Factory/docs/security/untrusted-content-threat-model.md` | Existing |
| Egress control | `AIFactory/apps/backend/security/egress.py` | Existing |
| Model inventory / routing | `AIFactory/apps/backend/phase_config.py`, `.../routing_policy.py`; `Factory/docs/rfc/0014-cost-aware-model-and-runtime-routing.md` | Existing |
| Model gateway choke point | `AIFactory/apps/web-server/server/services/litellm_admin_client.py` | Existing |
| Evidence gates | `Factory/docs/rfc/0001a-completion-evidence-gates.md`; coder test-honesty gate (#851) | Existing |
| Verification Assurance Levels | `Factory/docs/rfc/0006-verification-assurance-levels.md`; `TFactory/apps/backend/agents/verification_gate.py` | Existing |
| Standards-conformance gate | RFC-0012; `TFactory/apps/backend/prompts_pkg/prompts.py` | Existing |
| Trajectory capture | `Factory/docs/rfc/0004-governed-trajectory-capture.md` | Existing |
| Output secret-scan | `AIFactory/apps/backend/security/git_validators.py` (+ `scan_secrets`) | Existing (partial) |
| Approved-model registry + model cards | `Factory/docs/compliance/policies/` (Phase 1) | Planned |
| Model-swap eval gate | CI gate + eval suite (Phase 3, reuses RFC-0018) | Planned |
| Output-side DLP | extended pre-output scan (Phase 4) | Planned |
| Trusted-plan key rotation | envelope `kid`/expiry + rotation procedure (Phase 2) | Planned |
| Model-provenance attestation | per-build attestation in evidence store (Phase 4) | Planned |
| HITL -> change-control mapping | control statement (Phase 1) | Planned |
