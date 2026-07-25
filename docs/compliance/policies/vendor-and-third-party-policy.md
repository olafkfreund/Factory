# Vendor and Third-Party Policy

- **Policy owner:** Security Owner (CISO function) — see [roles.md](../roles.md)
- **Applies to:** All third-party services and suppliers the fleet depends on
- **Review cadence:** Annually, and before onboarding any new vendor
- **Frameworks:** ISO/IEC 27001:2022 A.5.19-.23; SOC 2 CC9.2; NYDFS 500.11;
  GDPR Art. 28 (processors); NIST SR, SA-9

## Purpose

To ensure third parties that process fleet data or supply code into the fleet are
assessed before onboarding and periodically thereafter, so that dependency risk
(including LLM-provider data exposure and software supply-chain risk) is understood and
controlled.

## Scope

Service providers and suppliers, including: LLM providers (Anthropic, OpenAI, and any
self-hosted or local model host such as the p510 Ollama), GitHub (source, CI/CD, OIDC),
Cloudflare (edge/TLS), the cloud/hosting substrate, and upstream open-source
dependencies and base images consumed by the build.

## Policy statements

1. **Assess before onboarding.** A new vendor that processes fleet data or runs fleet
   code is assessed for security posture and data handling before it is adopted.
   Preference is given to vendors with recognized attestations (SOC 2, ISO 27001).
2. **Data-processing terms.** Vendors that process personal data must be covered by
   appropriate processor terms (GDPR Art. 28), and the sub-processor list is maintained
   and disclosable (a published sub-processor list is a tracked gap, Factory#320).
3. **Minimize data shared.** Only the data necessary for the vendor's function is
   shared. For LLM providers this means PII is redacted before egress or the request is
   routed to a local model; see
   [data-classification-and-handling-policy.md](data-classification-and-handling-policy.md).
4. **Supply-chain integrity for code vendors.** Dependencies and base images are pinned
   (`flake.lock`, lockfiles, digest-pinned Chainguard bases), scanned (Trivy P0 gate,
   Renovate), and — for the fleet's own images — signed with provenance. Consuming a new
   dependency follows the [secure-sdlc-policy.md](secure-sdlc-policy.md) gates.
5. **Least-privilege vendor credentials.** Credentials issued to or by vendors (GitHub
   PATs, provider API keys) are scoped minimally, stored per the
   [secrets-management.md](secrets-management.md) domain, and rotated.
6. **Periodic review.** Vendor risk is re-reviewed at least annually and on any material
   change (a breach at the vendor, a change in what data they process). Findings feed the
   [risk register](../risk-register.md) and the management review.
7. **Exit and continuity.** Reliance on a single provider for a critical function is a
   continuity risk; where practical, a fallback exists (for example local models as a
   fallback for managed LLM providers).

## Roles and responsibilities

- **Security Owner** — approves vendor onboarding, owns this policy, and reviews vendor
  risk at the management review.
- **Control owners** — assess vendors within their domain (data governance for LLM
  providers, supply-chain for dependencies, IAM for identity providers).
- **Contributors** — do not introduce a new third-party dependency or service outside
  the assessment and SDLC gates.

## Related controls

- [supply-chain-integrity.md](supply-chain-integrity.md) — code-supplier controls
- [data-governance.md](data-governance.md) — LLM-provider data flow
- [secrets-management.md](secrets-management.md) — vendor credential handling
- [risk-register.md](../risk-register.md) — R-004 (PII egress), R-008 (supply-chain coverage)
