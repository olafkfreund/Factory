---
status: draft
issue: 324
spec: spec/2026-11-07-324-soc2-gap-assessment.md
coders:
  1: coder   # judgment-heavy authoring of 38 cited rows; Sonnet reads the domain docs; not mechanical, not small
  2: codex   # small but exact: recount a status table and keep totals reconciled; easy to get one cell wrong
  3: agy     # mechanical doc edits to two matrix rows and one section, text fully given below
  4: agy     # one README bullet, text fully given below; batched with step 3 in the same handoff
reviewers:
  - codex    # cross-check that Met/Partial rows do not overclaim; fresh context, so independent of its step-2 edit
  - agy      # second model on the same diff; disagreement with codex is the signal
---

# Plan: SOC 2 gap assessment and ISO 27001 gap summary

Docs only, in the Factory repo, on branch `docs/324-soc2-gap-assessment`
(based on `main`). Four files under `docs/compliance/`. No code, manifests or
cluster changes.

Approved decisions, carried over from the spec:

- **Scope.** Security CC1-CC9 is mandatory. Availability (A1) and
  Confidentiality (C1) are included. Processing Integrity is excluded, on the
  assumption that no transaction-accuracy commitment is made to customers; the
  Security Owner confirms that. Privacy is deferred: the matrix maps data
  governance to "C1, P-series", and the PII exposure stays visible through the
  C1.1/C1.2 rows and R-004 (#320). Either decision is reversed at sign-off by
  adding the category.
- **Criterion rows.** 38 rows: CC1.1-1.5, CC2.1-2.3, CC3.1-3.4, CC4.1-4.2,
  CC5.1-5.3, CC6.1-6.8, CC7.1-7.5, CC8.1, CC9.1-9.2, A1.1-1.3, C1.1-1.2.
- **Status rules.** Met, Partial and Gap use the SoA's definitions of
  Implemented, Partial and Planned (`statement-of-applicability.md:12-19`).
  - Met needs evidence that covers the whole criterion, and the evidence must be
    an operating output, not just a config file.
  - The SoA ceiling: each row names every SoA control it relies on, and its
    status is no better than the worst of them (Implemented > Partial > Planned).
    A Not Applicable SoA row gives no credit.
  - Unmapped criteria (CC6.4, CC6.5, CC6.7, A1.1, and anything under
    "CC-series") are Gap unless the row cites a specific SoA row or domain-doc
    section that answers them.
  - An accepted risk gives no implementation credit; such a row is Partial at
    best.
  - When in doubt, round down.
- **Risk column.** The column is "Risk (register)": the ID plus the inherent
  score the register records. Accepted risks add `accepted` and their log
  reference (AR-001, AR-002, or the dated log entries for R-014 and R-016). The
  intro says these are the register's recorded scores with their assessment
  dates (2026-07-24 for R-001 to R-013, 2026-10-24 for R-014 to R-016, per the
  register), not a new assessment.
  Where the register text is outdated, the row gets a note: R-008 says there is
  no signature gate, while the matrix and AR-001 cite Kyverno `Enforce`. The
  register itself is not edited.
- **Sign-off.** The table is left unsigned. The signature accepts current
  exposure, not a future target.
- **ISO.** No separate document. A summary section in the SOC 2 document links
  to the SoA, and the SoA's stale summary table is fixed.
- **Out of scope:** the readiness checklist, the mock audit, a P-series
  assessment, a machine-readable TSC catalog, and edits to the risk register.
- **Rejected alternatives:** a separate ISO gap document (it would duplicate the
  SoA), and SOC 2 columns added to the SoA or the matrix (that mixes
  granularities).
- **Deviation from the spec:** the spec's Verification regexes `(CC|A1|C1)[0-9]`
  miss the A1 and C1 rows, and its link check misreads `https:` URLs. Tests 2,
  3 and 8 below are corrected versions. The intent of each check is unchanged.

## Steps

1. **New `docs/compliance/soc2-gap-assessment.md`** (coder)
   - Header, in the style of `docs/compliance/risk-register.md:1-8`: Owner
     (Security Owner, see [roles.md](roles.md)); review cadence (annually and at
     each management review); framework (AICPA 2017 Trust Services Criteria,
     revised points of focus 2022); assessment date 2026-11-07.
   - Sections, in this order: Scope; Status legend (the five rules above);
     Security CC1-CC9 table; Availability A1 table; Confidentiality C1 table;
     Summary (Met, Partial and Gap counts per category, plus the criteria whose
     register risk is High); Accepted risks (AR-001/R-012, AR-002/R-015, R-014,
     R-016, each linked to `risk-register.md` and not restated); ISO 27001:2022
     gap summary; Residual-risk sign-off.
   - Table columns:
     `| Criterion | Requirement | Status | Control and evidence (incl. SoA rows) | Gap | Risk (register) | Issue |`.
     The Criterion cell is the bare ID, e.g. `| CC6.1 |`, so the checks match.
   - Sources, the only ones allowed for evidence:
     - `docs/compliance/control-matrix.md`: its "SOC 2 (TSC)" column is the
       domain-to-criterion map.
     - `docs/compliance/statement-of-applicability.md`: the status of each SoA
       row and its evidence text.
     - `docs/compliance/policies/*.md`: the domain documents' "current state" and
       "gaps" sections.
     - `docs/compliance/risk-register.md`.
     - `factory-gitops/docs/evidence-collection.md`: the evidence-collector,
       which runs daily and completes (`kubectl get jobs -n factory` showed
       Complete for 2026-11-04 to 11-06).
     Copy evidence pointers as those documents give them; never invent a path.
   - ISO section:
     - Row-level counts: 54 Implemented, 4 Partial, 18 Planned, 17 Not Applicable.
     - The Partial rows: A.5.21, A.8.8, A.8.21, A.8.23.
     - The 18 Planned rows, grouped by driving issue, taken from the SoA rows.
     - A link to [statement-of-applicability.md](statement-of-applicability.md).
   - Sign-off table:
     `| Framework | Current exposure accepted? | Scope decisions confirmed | Signed by | Date |`,
     with rows for `SOC 2` and `ISO 27001` and empty cells for the last four
     columns. Above it, one sentence saying the signature accepts current
     exposure, not a future target residual.
   - Verify by running the Tests 1-6 commands below.
   - Traps:
     - Do not mark anything Met on a config file alone.
     - CC6.4 maps to the SoA A.7 rows, which are Not Applicable or Planned, so
       CC6.4 cannot be Met.
     - Line wrap is about 85 columns in prose, but table rows are single lines.
     - British-neutral plain English, as in the existing docs.

2. **`docs/compliance/statement-of-applicability.md:180-186`: summary table**
   (codex)
   - Replace the table with this one, which has a Partial column:
     ```
     | Theme | Controls | Implemented | Partial | Planned | Not Applicable |
     |---|---|---|---|---|---|
     | A.5 Organizational | 37 | 25 | 1 | 10 | 1 |
     | A.6 People | 8 | 4 | 0 | 1 | 3 |
     | A.7 Physical | 14 | 0 | 0 | 2 | 12 |
     | A.8 Technological | 34 | 25 | 3 | 5 | 1 |
     | **Total** | **93** | **54** | **4** | **18** | **17** |
     ```
     These counts come from the row-level grep on 2026-11-07.
   - Verify by running Test 7.
   - Traps: change nothing else in the SoA. The legend at lines 12-19 already
     defines Partial.

3. **`docs/compliance/control-matrix.md`** (agy)
   - Line 38, the last cell of the #324 row: `Gap` becomes `Partial`.
   - Line 61, the #324 status row, becomes:
     ```
     | Evidence & audit-readiness | This directory; daily evidence-collector CronJob (factory-gitops#74) snapshots audit anchor, running-image digests and backups index to `factory-evidence/<date>/`; access-review NDJSON push (AIFactory#1018); [SOC 2 gap assessment](soc2-gap-assessment.md) | Code-scanning snapshot blocked on a new `evidence-github-token` secret (security_events:read); per-framework residual-risk sign-off not yet given | #324 |
     ```
   - Lines 72-79: the heading `## Automated evidence collection (planned)`
     becomes `## Automated evidence collection`, and the body becomes:
     > A daily CronJob (`apps/evidence-collector` in factory-gitops, 03:00 UTC)
     > snapshots what the cluster can produce on its own into the versioned
     > `factory-evidence` MinIO bucket, one dated prefix per run: the audit-chain
     > head and verdict, the image digests actually running, and the Postgres
     > backup objects present. A control-plane job pushes the fleet access review
     > as NDJSON to `factory-evidence/control-plane-push/access-review/<date>.ndjson`
     > (AIFactory#1018). The operator and assessor guide is
     > `factory-gitops/docs/evidence-collection.md`. Still missing: the
     > code-scanning (CodeQL) snapshot, which needs a read token the collector does
     > not have (#324). Until then, each repo's weekly CodeQL ratchet job reports
     > its alert count.
   - Verify with
     `grep -n 'soc2-gap-assessment.md\|## Automated evidence collection$' docs/compliance/control-matrix.md`,
     which returns 2 lines, and
     `grep -c '(planned)' docs/compliance/control-matrix.md`, which returns 0.
   - Traps: keep the table's column count. The status row has 4 cells and the
     mapping row has 8.

4. **`docs/compliance/README.md`, after the `signed-commits-and-sod.md` bullet
   (line 39-42)** (agy, in the same handoff as step 3)
   - Add this bullet:
     ``- [`soc2-gap-assessment.md`](soc2-gap-assessment.md) — the SOC 2 (TSC) criterion-by-criterion gap assessment (Security, Availability, Confidentiality) with current risk, an ISO 27001 gap summary pointing at the SoA, and the unsigned residual-risk sign-off. Factory#324.``
   - Verify with `grep -c soc2-gap-assessment docs/compliance/README.md`, which
     returns 1.
   - Traps: none.

## Tests

Run these from the repo root, with `F=docs/compliance/soc2-gap-assessment.md`.

1. **The exact criterion set.** This prints nothing:
   `diff <(grep -oE '^\| (CC[1-9]|A1|C1)\.[0-9]+ ' $F | tr -d '| ' | sort) <(printf '%s\n' CC1.{1..5} CC2.{1..3} CC3.{1..4} CC4.{1..2} CC5.{1..3} CC6.{1..8} CC7.{1..5} CC8.1 CC9.{1..2} A1.{1..3} C1.{1..2} | sort)`
2. **Statuses, by category.** Only Met, Partial and Gap appear, and the CC, A1
   and C1 totals are 33, 3 and 2:
   `awk -F'|' '/^\| (CC[1-9]|A1|C1)\.[0-9]+ /{c=$2; gsub(/ /,"",c); sub(/[0-9]*\..*/,"",c); if(c!="A"&&c!="C")c="CC"; s=$4; gsub(/ /,"",s); print c, s}' $F | sort | uniq -c`
   This prints counts by category: CC, A (for A1) and C (for C1).
3. **Evidence present.** This prints nothing:
   `awk -F'|' '/^\| (CC[1-9]|A1|C1)\.[0-9]+ / && $4 ~ /Met|Partial/ && $5 ~ /^ *-? *$/' $F`
4. **The summary reconciles.** Every per-category count from Test 2 appears in
   the Summary table. Check with `sed -n '/^## Summary/,/^## /p' $F` next to the
   Test 2 output: the numbers are equal, and each category's Met + Partial + Gap
   equals its row total.
5. **Risk IDs exist.** This prints nothing:
   `for id in $(grep -oE '\b(A?R)-0[0-9]{2}\b' $F | sort -u); do grep -q "$id" docs/compliance/risk-register.md || echo "missing $id"; done`
6. **Unsigned.** The "Signed by" and "Date" cells in the sign-off table are
   empty. Inspect them by eye, or
   `grep -A4 'Signed by' $F`.
7. **The SoA reconciles.** This gives 54, 4, 18 and 17, matching the table's
   Total row:
   `for S in Implemented Partial Planned "Not Applicable"; do grep -cE "^\| A\.[0-9.]+ \|[^|]*\| $S \|" docs/compliance/statement-of-applicability.md; done`
8. **Links.** This prints nothing:
   `for f in docs/compliance/{soc2-gap-assessment,control-matrix,README,statement-of-applicability}.md; do grep -oE '\]\([^)]+\)' $f | sed 's/^](//; s/)$//; s/#.*//' | grep -v '://' | grep -v '^$' | while read l; do test -e "$(dirname $f)/$l" || echo "$f -> $l"; done; done`
9. **Pre-commit** (gitleaks) passes on commit.
10. **Final review.** A fresh Opus agent gets this plan's path and the
    `git diff main...`. It samples at least 10 rows, including every Met row in
    CC6 and CC7, against the cited evidence and the SoA ceiling. Codex and agy
    review the same diff, read-only.

## Rollback

Revert the PR. The changes are docs only, and nothing consumes them.
