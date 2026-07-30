# When a gate is green and wrong

Factory#504. Three defects found on 2026-07-30 were the same defect wearing
different clothes. This is the taxonomy they produced, the guard each variant
needs, and — the part that matters for anyone reading this to decide what to
trust — which of those guards is a **control** in this repo today and which is
still a **convention**.

## The three variants

### 1. False pass — passes when it should fail

The control is absent and the check does not care.

- Factory#499: a NetworkPolicy chart template cited as ISO evidence, correct,
  on by default, and never rendered against the cluster it was credited to.
  Nobody had asked what would be different if it were absent. Nothing.
- A `cosign verify-attestation` run with `--certificate-identity-regexp '.*'`,
  which accepts any signer. It would have passed against an image signed by
  someone else entirely.
- Factory#519: a drift gate comparing a vendored copy against **its own pin**,
  so it cannot detect staleness at all. It reddens only if someone edits the
  vendored mirror, which is the one thing nobody does to a vendored file.

**Guard: every check must have been observed FAILING when its control is
removed.** Not "should be tested" — observed, once, with the result recorded.

### 2. False report — misreads a control that is fine

A Kyverno audit read the `subject` field where the rule used `subjectRegExp` and
printed `keyless subject: None`, which reads as "no signer constraint at
admission". The policy was healthy; the reader was broken. This variant
fabricates a finding rather than missing one, and every mutation table built for
variant 1 passes it: you can remove the control, watch the check go red, and it
is still lying about what the control says.

**Guard: every verdict carries the raw fragment it was derived from — on the
PASS path too, not only on absent.** Printing the source only for things reported
absent covers the direction that costs an investigation and leaves the direction
that costs a missing control: a reader that reports PRESENT for something that is
not the control at all prints nothing, and nobody goes looking.

### 3. Silent scope loss — stops looking and calls it success

Factory#523: deleting one service's layout entry un-gated a vendored file
entirely. The copy stayed on disk, kept being imported, was free to drift
forever, and the gate reported success. The only trace was
`(6 vendored module(s))` becoming `(5)`.

**Guard: mutate the gate's OWN CONFIGURATION, not just its subject.** Every
mutation table written for these gates moved the subject — drift a file, delete a
file, break a signature. None moved the gate's scope, which is why #523 sat open
under a gate with sixteen green cases.

Variants 1 and 3 both under-report, which is the direction that matters:
over-reporting is noisy and self-correcting, under-reporting is green because
nothing looked.

## The corollary: a count is not a check

`6 vendored modules`, `16 pins`, `93 controls`, `the built-in high-precision
set`. Each of those falls silently to variant 3, because a headline number is
something nobody re-derives. A pin count went 12, then 14, then 16 with two
people watching it. A four-member pattern set was cited unenumerated in a
docstring, a PR body and an environment reference while two of its four members
never reached the wire (AIFactory#1139).

**Emit the list, not the number.** A reader can falsify a list at a glance and
cannot falsify a number at all.

## What is a control here, and what is not

| Guard | Status | Where |
|---|---|---|
| Enumeration instead of a count, on every hub gate | **control** | `tests/test_gate_honesty.py::test_every_gate_is_covered_here_or_named_as_exempt` plus one case per gate |
| Every verdict carries its fragment (digest, both sides, pass path included) | **control**, for the byte-comparison gates | the same cases: each asserts one `sha256:` per side per compared item |
| Deleting one entry from a gate's own configuration turns it red | **control**, for the three drift gates | the same cases, each holding the subject constant across the mutation |
| Every new gate is either asserted or named as exempt with a reason | **control** | the registry is enumerated against `scripts/check_*.py`, so an unregistered gate fails rather than widening the blind spot |
| Variant 2 — the extraction is checked against the raw object | **convention** | the digest makes a byte comparison auditable, but nothing mechanises "this parser read the right field" for a gate that parses structure (Kyverno rules, rendered YAML). A parsing gate must fixture this itself. |
| Variant 1 in general — every check observed failing | **convention** | asserted per gate by hand. There is no mechanism that enumerates a gate's checks and demands a negative fixture for each. |
| Counts outside the hub gates | **convention** | pin counts, control counts, pattern-set sizes in docstrings and PR bodies are prose. Nothing lints them. |

The convention rows are the honest half of this document. They are the rows
where "we agreed to do this" is the whole mechanism, and where the failure mode
is a person under time pressure, which is exactly the condition the top four rows
were built to survive.

## The mechanism that found all of this, and why it does not scale

Every real finding on 2026-07-30 came out of a disagreement settled the same way:
**neither party conceded on assertion; both went and ran the command.** A pod
label off a stale checkout, re-fetched rather than restated. A chart policy
asserted to cover some pods, checked with `get networkpolicy` rather than
accepted. Two different pin counts, neither adopted, both re-derived, both wrong,
and a third number right.

Uniform pattern: the disagreement located the defect, the command settled it.
That needed two people holding one subject simultaneously, both willing to spend
a command rather than win an argument. It is a good norm attached to a staffing
coincidence, not a control. On any day where one person owns a subject alone, or
the second is fractionally less stubborn, every one of those findings stays
green.

A check that only fires when two people happen to disagree is not a check. That
is the case for the top four rows of the table above, and the reason the bottom
three are worth writing down as unfinished rather than describing as done.
