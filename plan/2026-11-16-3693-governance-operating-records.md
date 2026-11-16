---
status: draft
issue: 3693
spec: spec/2026-11-16-3693-governance-operating-records.md
coders:
  1: lead   # judgment-heavy authoring where an overclaim is the main risk
  2: lead
  3: lead
  4: lead
  5: lead
  6: lead
  7: lead   # cross-reference edits across SoA/SOC 2/matrix/README need the same context
reviewers:
  - codex   # independent read for overclaims, bad cross-references and NYDFS accuracy
# agy not named: out of use by owner decision #2748
---

# Plan: Governance operating procedures and mappings

Docs only, Factory repo, branch `docs/3693-governance-operating-records`
(from `origin/main`). Approved spec decisions carried over:

- Five new documents in `docs/compliance/`; edits to the Information Security
  Policy, risk register, roles, SoA, SOC 2 gap assessment, control matrix and
  README. Each new file starts with an owner / review cadence / frameworks
  header like `roles.md`.
- Every record template has empty date, attendee, signature and evidence
  fields, and the header line "TEMPLATE: not a record". No SoA or SOC 2 status
  is upgraded.
- NYDFS mapping is conditional on #3697 and separates the operator as covered
  entity from a covered customer (500.11 only).
- Issues stay open; each has its own completion checklist (spec, "Completion
  per issue"). Never claim that a review, training, audit or sign-off happened.

## Steps

1. `docs/compliance/training-and-awareness.md` (new, #3693). Audience: every
   human with fleet access and whoever operates agents; cadence: on joining,
   annually, and after a Sev-1 or material policy change. Curriculum: the
   Information Security, Acceptable Use, Access Control, Data Classification,
   Incident Response and Secure SDLC policies, secrets handling, prompt-injection
   and agent-misuse, phishing, reporting a suspected incident. Screening: state
   it as not applicable (SoA A.6.1 reason) with the re-scope trigger. Blank
   completion record (person, content version, date, method, signature) →
   links resolve.
   Traps: no named person or date as having trained.
2. `docs/compliance/management-review-and-internal-audit.md` (new, #3694).
   Quarterly review procedure using the `roles.md` agenda, blank minute
   template (date, attendees, inputs, decisions, actions, signature). Audit
   programme: annual, rolling coverage of the SoA themes (A.5, A.6, A.7, A.8)
   plus clauses 4-10, independence rule (auditor is not the owner of the
   control audited; for a one-operator fleet name an external or peer auditor
   and say so), findings routed to the risk register and `remediation-sla.md`,
   blank audit report. State a recorded mock audit (#324) counts as the first
   audit only if recorded as one → links resolve.
   Traps: do not state a review was held.
3. `docs/compliance/supplier-management.md` (new, #3695). Register for LLM
   providers (Anthropic, OpenAI), local Ollama, GitHub, Cloudflare and the
   hosting substrate: data processed, processor terms in force, assurance
   report, last review, all "owner to record". Owner checklist to obtain,
   evaluate and cite each provider's processor terms and SOC 2 or ISO report,
   an unobtainable item kept as a gap with a compensating note. Annual
   re-review procedure and blank record → links resolve.
   Traps: do not state terms in force or reports held.
4. `docs/compliance/operator-endpoint-standard.md` (new, #3696). Requirements:
   full-disk encryption, screen lock timeout, patching cadence, where key
   material (agenix identity, GitHub credentials) may live, MFA on the GitHub
   account, loss or theft handling. Evidence column names the NixOS option or
   command that proves each, for the owner to cite. Blank per-host attestation
   that requires evidence attached → links resolve.
   Traps: do not claim any host complies.
5. `docs/compliance/policies/information-security-policy.md`: measurable
   objectives table (objective, measure, target, data source, frequency, no
   current values) mapped to the six objectives, with a line that the owner
   reviews targets at the management review. `docs/compliance/risk-register.md`:
   add R-017 fraud risk (agent or operator falsifying verification evidence or
   the audit trail; controls: audit hash-chain and daily anchor, TFactory
   independent verification, signed contracts; limits: agents authenticate as
   the operator per `agent-identity.md`) with L, I, inherent and treatment →
   table column counts match.
6. `docs/compliance/nydfs-part500-mapping.md` (new, #3700). Sections 500.1 to
   500.24 each mapped to a control or marked administrative or exemption;
   conditional banner and the two-case split; 500.19 exemption criteria with an
   empty determination field; 500.17(b) as in the spec (April 15, both forms,
   highest-ranking executive and CISO, five-year retention, gaps route to the
   acknowledgment form) with blank forms; gaps named (500.5 annual pen test vs
   R-015/AR-002, 500.12 MFA vs R-010) → links resolve.
   Traps: every row says verify against the current rule.
7. Cross-references: `roles.md` (link the new procedures), SoA rows A.5.20,
   A.5.22, A.5.35, A.6.3, A.7.7, A.7.9, A.8.1; `soc2-gap-assessment.md` rows
   CC1.2, CC1.4, CC3.1, CC3.3, CC4.2, CC6.4, CC9.2; `control-matrix.md` NYDFS
   column and governance gaps; `README.md` index. Statuses unchanged; each row
   names the record the owner must produce → links resolve.

## Tests

- Python link and path check over `docs/compliance/**/*.md`: relative links
  resolve; backticked repo paths in new files exist.
- `grep -nE '20[0-9]{2}-[0-9]{2}-[0-9]{2}'` over new files: no date in a record
  field.
- Table column counts match in edited tables.
- `codex review --base origin/main`: findings resolved or refuted, including a
  check of 500.17(b), 500.19 and 500.24 against the DFS rule text.

## Rollback

Revert the PR. Docs only; nothing consumes these files at runtime.
