---
status: approved
issue: 5
intent: intent/2026-11-24-5-contradictory-quote.md
---

# Spec: vatcalc contradictory invoice quote specification

## Design

Define `compute_quote(net, vat_rate="0.175") -> Quote` in `vatcalc/calc.py` with mutually contradictory requirements so that no implementation can satisfy all acceptance criteria simultaneously:

- Criterion A requires the exact additive invariant `total = net + vat`, synchronous execution, and `vat_rate` to be required.
- Criterion B requires that for `net = 10.00` and `vat = 1.75`, `total` equals `11.76` (violating `total = net + vat = 11.75`) AND simultaneously equals `11.75` (`total != 11.75` and `total == 11.75`), with asynchronous execution and `vat_rate` optional.

## Alternatives rejected

- A valid, self-consistent specification: P5 is the negative trap fixture and must stop at review or in Needs you.

## Risks

- If review gates fail to detect the contradiction, the hidden suite guarantees the run fails because its assertions require `quote.total == Decimal("11.75")` and `quote.total == Decimal("11.76")` on the same returned `Quote` object.

## Verification

- `total` equals `net + vat` for every quote, `compute_quote` is synchronous, and `vat_rate` is required.
- For `net = 10.00` and `vat = 1.75`, `total = 11.76`, `compute_quote` is asynchronous, and `vat_rate` is optional.
- For input `("10.00", "0.175")`, `compute_quote` must not round intermediate values and must return a single `Quote` whose `total` is simultaneously equal to `Decimal("11.75")` and `Decimal("11.76")`.
