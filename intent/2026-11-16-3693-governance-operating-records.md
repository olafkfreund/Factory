---
status: approved
issue: 3693
author: olafkfreund
---

# Intent: Governance operating procedures and mappings (#3693, #3694, #3695, #3696, #3699, #3700)

Covers Factory#3693, #3694, #3695, #3696, #3699 and #3700, all found by the
#310 gap pass on 2026-11-14. Parent: #310. One change set because the six
issues edit the same few files (SoA, SOC 2 gap assessment, control matrix,
README) and cross-refer to each other.

## Problem

The compliance program defines policies but lacks the operating procedures and
records an assessor tests:

- No training content, cadence or completion record (A.6.3, CC1.4, NYDFS 500.14).
- No internal-audit programme and no minute template for the quarterly
  management review (clauses 9.2, 9.3, A.5.35, CC1.2, CC4.2).
- No published vendor and sub-processor list, processor-terms checklist or
  annual re-review procedure (A.5.20, A.5.22, CC9.2).
- No operator endpoint standard although operator laptops hold the agenix
  identity and GitHub credentials (A.8.1, A.7.7, A.7.9, CC6.4).
- No measurable security objectives (clause 6.2, CC3.1) and no fraud-risk entry
  (CC3.3).
- Seven NYDFS Part 500 sections (500.8, .9, .10, .14, .16, .17(b), .19) map to
  no control anywhere in `docs/compliance`, and no document covers the whole Part.

## Proposed outcome

- A procedure or standard for each of the first four, each with a blank record
  template whose date, attendee and signature fields are empty.
- Measurable objectives in the Information Security Policy and a fraud-risk
  entry in the risk register.
- A NYDFS Part 500 mapping covering every section 500.1 to 500.24, written as
  conditional on the applicability decision in #3697 and separating two cases:
  the operator being a covered entity itself (direct duties), and a customer
  being one (the operator then answers as a third-party service provider under
  500.11 only).
- SoA, SOC 2 gap assessment, control matrix and README link to the new
  documents. No SoA or SOC 2 status is upgraded: every row stays Planned/Gap
  until the owner holds the first event and the dated record exists.

## Affected users and systems

Documentation under `docs/compliance/` in the Factory repo only. The owner
(Security Owner) performs the first events. No code, manifests or cluster.

## Constraints

- Never write a record that a review, training, audit or sign-off took place.
  Templates leave date, attendees and signature empty.
- Do not decide #3697. The NYDFS mapping states it applies only if #3697
  finds the operator or a customer is a covered entity.
- Do not claim the operator hosts meet the endpoint standard; evidence is the
  owner's to attach.
- The six issues stay open until each one's own completion checklist (spec,
  "Completion per issue") is met by the owner. Merging this change completes
  none of them.

## Open questions

None for approval. The owner holds #3697 and the first-event dates.
