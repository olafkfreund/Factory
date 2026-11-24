"""Visible starter tests for vatcalc."""

from __future__ import annotations

from decimal import Decimal

from vatcalc.calc import compute_quote


def test_compute_quote_invariant() -> None:
    quote = compute_quote("10.00", "0.175")
    assert quote.net == Decimal("10.00")
    assert quote.vat == Decimal("1.75")
    assert quote.total == quote.net + quote.vat
