---
status: approved
issue: 324
intent: intent/2026-11-07-324-soc2-gap-assessment.md
---

# Spec: SOC 2 gap assessment and ISO 27001 gap summary

## Design

Docs only, in four files under `docs/compliance/`.

### 1. New `docs/compliance/soc2-gap-assessment.md`

The header follows `statement-of-applicability.md` and `risk-register.md`: Owner
(Security Owner, see `roles.md`), review cadence (annually and at each
management review), framework (AICPA 2017 Trust Services Criteria, revised
points of focus 2022), and assessment date 2026-11-07.

Sections, in order:

1. **Scope.** Security (common criteria CC1-CC9, mandatory), Availability (A1)
   and Confidentiality (C1). Processing Integrity is excluded on an assumption
   the Security Owner must confirm: no transaction-accuracy commitment is made to
   customers. Privacy is deferred, not dropped: the control matrix maps data
   governance to "C1, P-series", and the PII exposure stays visible through
   C1.1/C1.2 and R-004 (#320). Either decision is reversed at sign-off by adding
   the category.
2. **Status legend.** Met, Partial and Gap use the SoA's definitions
   (Implemented, Partial, Planned). Five rules prevent overclaiming:
   - **Met** needs evidence that covers the whole criterion, and that evidence
     must be an operating output, not just a config file (the README's "control
     existed as a file rather than an effect" lesson).
   - **The SoA ceiling.** Each row names every SoA control it relies on. Its
     status can be no better than the worst of those, ranked Implemented > Partial
     > Planned. A Not Applicable SoA row gives no credit. For a criterion such as
     CC6.4 (physical access), that state is shown as written, not as Met.
   - **Unmapped criteria.** Some criteria have no entry in the control matrix's
     "SOC 2 (TSC)" column: CC6.4, CC6.5, CC6.7 and A1.1, plus anything under the
     open-ended "CC-series". These are Gap unless the row cites a specific SoA row
     or domain-document section that answers them.
   - **Accepted risk gives no implementation credit.** A criterion whose only
     answer is an accepted risk is Partial at best.
   - **Doubt rounds down.** When the status is in doubt, the lower one is used.
3. **One table per category**, one row per criterion, 38 rows in all: CC1.1-1.5,
   CC2.1-2.3, CC3.1-3.4, CC4.1-4.2, CC5.1-5.3, CC6.1-6.8, CC7.1-7.5, CC8.1,
   CC9.1-9.2, A1.1-1.3, C1.1-1.2. The columns are:
   `Criterion | Requirement (one-line paraphrase) | Status | Control and evidence (incl. SoA rows) | Gap | Risk (register) | Issue`.
   - *Control and evidence* cites an existing domain document, SoA row, file or
     workflow, using the pointer those documents already give. Nothing new is
     asserted.
   - *Risk (register)* is the risk-register ID with the inherent score as the
     register records it (e.g. `R-001 15 High`), or `-` when none applies. An
     accepted risk adds `accepted` and its log reference (`AR-001`, `AR-002`, or
     the dated log entry for R-014 and R-016). The section intro says plainly that
     these are the register's recorded scores with their assessment dates, not a
     new risk assessment. Where the register text is older than newer evidence,
     the row adds a one-line note and leaves the register as it is: R-008 says
     there is no cluster-wide signature gate, while the control matrix and AR-001
     cite Kyverno `Enforce`. Correcting the register is out of scope.
   - The criterion-to-domain mapping comes from the control matrix's
     "SOC 2 (TSC)" column, split down to single criteria.
4. **Summary.** Counts of Met, Partial and Gap per category, and the
   criteria whose current risk is High.
5. **Accepted risks.** AR-001 (R-012), AR-002 (R-015), R-014 and R-016, each
   linked to its risk-register entry, not restated.
6. **ISO 27001:2022 gap summary.** The SoA's row-level counts (54 Implemented,
   4 Partial, 18 Planned, 17 Not Applicable), the 4 Partial controls by ID, the
   18 Planned grouped by driving issue, and a link to the SoA as the ISO
   control-by-control view.
7. **Residual-risk sign-off.** A blank table for the Security Owner, with
   columns `Framework | Current exposure accepted? | Scope decisions confirmed | Signed by | Date`,
   one row each for SOC 2 and ISO 27001. Above it, one sentence: the signature
   accepts current exposure, not a future target residual. Nobody signs it in
   this change.

### 2. `docs/compliance/statement-of-applicability.md` summary table (lines 180-186)

Add a Partial column and correct the counts to the row-level totals per theme,
so the table sums to 54 / 4 / 18 / 17.

### 3. `docs/compliance/control-matrix.md`

- The #324 row in the mapping table goes from Gap to Partial.
- The #324 row in the status table says what runs today. Implementing control:
  the evidence-collector daily CronJob (factory-gitops#74, `factory-evidence/<date>/`:
  audit anchor, image-digest baseline, backups index) and the access-review push
  (AIFactory#1018). Top gap: the code-scanning snapshot is blocked on the
  `evidence-github-token` secret, and there is no per-framework sign-off yet.
  Add a link to the SOC 2 gap assessment.
- The "Automated evidence collection (planned)" section becomes "Automated
  evidence collection", describing the same live jobs. It points to
  `factory-gitops/docs/evidence-collection.md` and names the blocked
  code-scanning slice.

### 4. `docs/compliance/README.md`

Add one bullet to "How this is organized" for `soc2-gap-assessment.md`.

## Alternatives rejected

- **A separate ISO 27001 gap-assessment document.** It would duplicate the SoA,
  which already gives status, evidence and owner for each Annex A control. A
  summary section that links to the SoA is enough.
- **Adding SOC 2 columns to the SoA or the control matrix.** That mixes two
  frameworks' granularity into one table and makes both harder to read.
- **Including Privacy (P1-P8) now.** It roughly doubles the rows for a category
  the user has not committed to. The decision is left visible for sign-off.
- **A machine-readable TSC catalog in `apis/control-catalog.json`.** Nobody
  consumes it yet, so it is YAGNI.
- **Readiness checklist and mock audit.** These are #324 item (c), a human
  exercise, and out of scope here.

## Risks

- **Overclaiming.** A Met row that an assessor cannot evidence is worse than a
  Gap. Mitigation: the two status rules, plus a cross-check in review against
  the SoA and the domain documents.
- **Drift.** The assessment goes stale as controls land. Mitigation: the
  assessment date and the review cadence are in the header, the same as the SoA.
- No runtime, host or cluster impact.

## Verification

The plan copies these commands verbatim. Here `F=docs/compliance/soc2-gap-assessment.md`.

- **The exact criterion set, each once:**
  `diff <(grep -oE '^\| (CC[1-9]|A1|C1)\.[0-9]+ ' $F | tr -d '| ' | sort) <(printf '%s\n' CC1.{1..5} CC2.{1..3} CC3.{1..4} CC4.{1..2} CC5.{1..3} CC6.{1..8} CC7.{1..5} CC8.1 CC9.{1..2} A1.{1..3} C1.{1..2} | sort)`
  prints nothing.
- **Allowed statuses only:**
  `awk -F'|' '/^\| (CC|A1|C1)[0-9]/{print $4}' $F | tr -d ' ' | sort | uniq -c`
  shows only Met, Partial and Gap.
- **Every Met or Partial row has evidence:**
  `awk -F'|' '/^\| (CC|A1|C1)[0-9]/ && $4 ~ /Met|Partial/ && $5 ~ /^ *-? *$/' $F`
  prints nothing.
- **The summary reconciles:** the counts in the Summary table equal the
  `uniq -c` output, per category.
- **Every risk ID cited exists:**
  `for id in $(grep -oE '\b(A?R)-0[0-9]{2}\b' $F | sort -u); do grep -q "$id" docs/compliance/risk-register.md || echo "missing $id"; done`
  prints nothing.
- **The sign-off is unsigned:** the "Signed by" and "Date" cells in the sign-off
  table are empty.
- **The SoA summary:** for each status S,
  `grep -cE "^\| A\.[0-9.]+ \|[^|]*\| $S \|" docs/compliance/statement-of-applicability.md`
  equals the summary table's Total for S (54 / 4 / 18 / 17).
- **Links resolve:** for each changed file, every `](<relative path>)` target
  exists, checked with a grep and `test -e` loop.
- **Pre-commit hooks pass** on commit.
- **Manual check (final reviewer):** sample at least 10 rows, including every
  Met row in CC6 and CC7. For each, check that the evidence covers the whole
  criterion and that the SoA ceiling holds.
- The final review is a fresh Opus agent given the plan and the diff, plus
  codex and agy.
