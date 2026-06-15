---
layout: default
title: "RFC-0007: Access Discovery & Authenticated-Test Provisioning"
permalink: /rfc/access-provisioning/
---

# RFC-0007 — Access Discovery & Authenticated-Test Provisioning

> **Status:** Proposed · **Created:** 2026-06-15 · **Extends:** [RFC-0002](./0002-task-contract.md) (task contract), [RFC-0005](./0005-environment-manifest-and-toolchain-provisioning.md) (provisioning), [RFC-0006](./0006-verification-assurance-levels.md) (assurance levels), [RFC-0001a](./0001a-completion-evidence-gates.md) (evidence gates) · **Affects:** PFactory, AIFactory, TFactory, CFactory
> RFC-0005 said *provision the toolchain*. RFC-0006 said *declare how much was proven, never overclaim*. This RFC fills the gap between them: **discover what access a feature needs to be tested, curate that access (human-verified when it must be), and let the assurance ladder stay honest when access cannot be obtained.** The single rule carried forward: we never claim something is tested when the access to test it was never available.

## 1. The problem — the access ceiling

RFC-0006 names the verifiability ceiling and notes VAL-3 "needs a disposable
target + credentials". It never says **how those credentials are discovered,
obtained, or refused.** That is this RFC.

A feature is frequently un-testable not because we lack a toolchain (RFC-0005)
but because we lack *access*: a test must reach an authenticated API, a cloud
account, a database, or a login-gated web app — and that gate is often **MFA /
2FA**, which exists precisely to stop non-interactive automation from logging in.

Two failure modes must both be avoided:

1. **Silent under-test** — the pipeline lints the code, can't reach the real
   target, and reports it as done. (RFC-0006's cardinal sin.)
2. **Unsafe over-reach** — the pipeline is handed broad production credentials
   and a way to bypass MFA, and tests against something it can damage.

The honest path is neither. It is to **classify the access, route each class to
a non-interactive mechanism where one legitimately exists, require a one-time
human-verified bootstrap where it doesn't, and declare the residue un-automatable**
— letting the VAL gate record exactly how far testing got.

## 2. The reframe — you do not "solve" MFA, you classify access

MFA is a control designed to block non-interactive login. A pipeline that
"solves" it is either storing a bypass or scraping a human's session — both lose
credibility. So we do not try. Instead every resource a test needs is sorted
into one of four **access classes**, and each class has a defined route:

| Class | What it is | How the pipeline authenticates | MFA in path? | Human role |
|---|---|---|---|---|
| **A — Machine-native** | Cloud workload identity / OIDC federation (GitHub Actions to AWS/GCP/Azure), service accounts, scoped API tokens | Federated short-lived credentials; no password, no MFA prompt | No | None |
| **B — Bootstrap-once, machine-reused** | OAuth device-code / refresh tokens; a **TOTP seed held as a secret** (codes generated in-process); a captured browser `storageState` session | Human clears MFA once at bootstrap; secret stored and refreshed; pipeline reuses | Cleared once | One-time bootstrap |
| **C — Ephemeral target (the default for VAL-3)** | A throwaway resource the pipeline owns: LocalStack / testcontainers, an ephemeral Keycloak realm, a disposable cloud project | No production credential at all — provision, seed a test identity, tear down | None | None (cost-guarded) |
| **D — Un-automatable** | Push-approval, hardware key (WebAuthn / FIDO2), SMS or email code sent to a person | Cannot, and must not, be faked | Hard block | Assisted run, or refuse |

Design consequences, stated plainly:

- **Most "test against the cloud" cases are Class A.** The correct answer makes
  MFA irrelevant via federated identity — it is not "defeated", it is never in
  the path. Reach for this first.
- **TOTP-as-a-secret is legitimate (Class B):** we hold the seed, not a phone,
  and generate codes in-process. SMS, push, and hardware keys are *not* reducible
  this way — those are Class D.
- **Class C is usually the best answer** for integration fidelity without
  touching anything credentialed; prefer it over real credentials whenever the
  artifact's effects are simulable.
- **Class D is where honesty bites.** The pipeline stops at the highest level it
  could reach (typically VAL-2) and the gate records, e.g.,
  `VAL-3 not_run — requires interactive MFA (push approval), human-driven`.
  Optionally an **assisted run**: a human performs the login out-of-band and hands
  back a time-boxed `storageState`; the pipeline resumes but never claims it
  logged in itself.

## 3. Where it plugs in — discover, curate, test, gate

```
spec
  |
  v
PFactory  access-discovery  (new planning step)
  |   per target, emit: { resource, auth_class A|B|C|D, credential_ref, bootstrap: human|none }
  v
Task Contract  $defs.access   (new block, sibling of RFC-0005 environment)
  |
  v
Curation gate  (human-verified WHEN bootstrap = human)
  |   device-code login | store TOTP seed | approve sandbox account
  |   recorded in the audit chain (RFC-0001a); on success flips the
  |   "credentials" / "sandbox_target" capability into the `available` set
  v
TFactory  maps access -> existing .tfactory.yml credential refs; runs egress-gated lanes
  |
  v
verification_gate  VAL-3 achievable ONLY if access was curated; else not_run + honest reason
```

The leverage point: **the honest downgrade already exists.** RFC-0006's
`verification_profiles.py` marks VAL-3 `requires: ["sandbox_target","credentials"]`,
and `verification_gate.py` already downgrades VAL-3 to `not_run` with a reason
when those are absent from `available`. Discovery and curation therefore only
have to decide **whether those capabilities enter `available`** — no component
needs to learn a new way to be honest; the gate already is.

## 4. The contract block

A new optional top-level `access` block in the RFC-0002 task contract,
populated by PFactory discovery and updated by the curation gate. Proposed
`$defs.access` (additive; absence means "no external access required"):

```json
"access": {
  "type": "object",
  "additionalProperties": false,
  "description": "RFC-0007 access requirements discovered at planning time. Absent => the task needs no external/authenticated resource. The curation gate sets curated/human_approval; TFactory consumes credential_ref; the VAL gate treats un-curated requirements as a VAL-3 not_run.",
  "required": ["requirements"],
  "properties": {
    "requirements": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["resource", "auth_class", "bootstrap"],
        "properties": {
          "resource":      { "type": "string", "description": "What is being reached, e.g. 'staging-api', 'sandbox-aws', 'keycloak-realm'." },
          "auth_class":    { "type": "string", "enum": ["A-machine-native", "B-bootstrap-once", "C-ephemeral-target", "D-un-automatable"] },
          "credential_ref":{ "type": ["string", "null"], "description": "Existing broker ref the test will use: env:NAME | vault:path#field | store:<id>. Never an inline secret." },
          "env_required":  { "type": "array", "items": { "type": "string" }, "description": "Env var names the auth needs at runtime." },
          "bootstrap":     { "type": "string", "enum": ["none", "human"], "description": "human => a one-time human-verified login/seed/approval is required before this is usable." },
          "curated":       { "type": "boolean", "description": "Set true by the curation gate once the credential/target is provisioned and validated. VAL-3 stays not_run until true." },
          "human_approval":{
            "type": ["object", "null"],
            "additionalProperties": false,
            "properties": {
              "approved_by": { "type": "string" },
              "approved_at": { "type": "string" },
              "scope":       { "type": "string", "description": "What was granted, e.g. 'sandbox account, read+deploy, auto-teardown'." }
            }
          },
          "mvp_note":      { "type": ["string", "null"], "description": "For class D: the honest reason testing cannot pass this gate autonomously." }
        }
      }
    }
  }
}
```

## 5. The honesty contract (carried from RFC-0006)

- A Class D requirement, or any requirement with `curated: false`, **caps the
  achievable VAL at the highest level reachable without it** (usually VAL-2). The
  gate records the un-run higher level with `reason` and `risk`. No exception.
- The curation gate is the **only** thing that may set `curated: true`, and only
  after the credential/target is provisioned and a liveness check passes. A
  human bootstrap (Class B/D-assisted, or real-credential Class C) is recorded
  in the RFC-0001a audit chain: who approved, when, what scope.
- Secrets never enter the contract — only refs (`env:` / `vault:` / `store:`).
  Artifacts (logs, JUnit, HAR, verdicts) are scrubbed by TFactory's existing
  redaction layer before surfacing; this is a hard requirement, not best-effort.
- CFactory surfaces the access state in plain language:
  "VAL-2 reached; VAL-3 blocked — interactive MFA, human-driven" — never a bare
  green check.

## 6. What already exists (reuse, do not rebuild)

- **TFactory** has the runtime plumbing: an encrypted credential vault
  (`/api/test-credentials`), a default-DENY egress gate, a `.tfactory.yml` auth
  schema (`form` / `api_token` / `basic_auth` / `totp`, ordered `LoginStep` SSO,
  `RefAuth`), Playwright `storageState` login-once, and a redaction layer. Gaps:
  live credential-to-Evaluator wiring (their task 4b.2) and interactive MFA
  (out of scope there — addressed as Class D here). See TFactory #107.
- **PFactory** has read-only cloud-discovery (#133) and the same credential vault
  (#107) — but no spec-driven step that populates an `access` block. Today the
  only signal is a single `requires_auth` boolean tagged after planning.
- **Factory hub** has the assurance ladder, profiles registry, and the
  never-overclaim gate (`scripts/verification_{profiles,gate,runner}.py`) that
  already gate VAL-3 on `credentials` / `sandbox_target` capabilities.

This RFC is therefore mostly **connective**: a planning-time discovery step, a
typed contract block, and a curation gate that flips capabilities — wired onto
storage and a gate that already exist.

## 7. Phasing

- **Phase 0 — this RFC + `$defs.access`** in the contract schema (additive; no
  behavior change until a producer emits it).
- **Phase 1 — PFactory discovery:** classify each target into A/B/C/D from the
  spec + `.pfactory.yml`; emit `access.requirements`; extend `auth_tagging` to
  validate (credential exists? class D? bootstrap needed?).
- **Phase 2 — profiles map artifact type to credential class** in
  `verification_profiles.py` (terraform to cloud identity, web-app-auth to
  form/totp, etc.) so discovery has a default per technology.
- **Phase 3 — curation gate:** human-verified bootstrap (device-code / TOTP-seed
  / sandbox-approve), recorded in the audit chain; flips `curated`/capability.
  Class C ephemeral provisioning with cost guard + mandatory teardown.
- **Phase 4 — TFactory consumption:** map `access` to existing `.tfactory.yml`
  refs; finish live wiring + redaction; run an end-to-end credentialed lane
  against a Class C ephemeral target.
- **Phase 5 — CFactory surfacing:** honest access state in the cockpit.

## 8. Non-goals

- Defeating, bypassing, or storing a bypass for any MFA control. Class D is
  refused or assisted, never faked.
- A new secret store. We reuse the existing vault / broker (`env:` / `vault:` /
  `store:`) and the ExternalSecret operator pattern.
- VAL-4 (production) automation — unchanged from RFC-0006: never autonomous.
