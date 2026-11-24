"""Invoice net, VAT, and total calculator."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Quote:
    """Computed invoice quote with net, VAT, and total amounts."""

    net: Decimal
    vat: Decimal
    total: Decimal


def compute_quote(net: Decimal | str, vat_rate: Decimal | str = "0.175") -> Quote:
    """Compute `(net, vat, total)` for the given net amount and VAT rate."""
    _ = (net, vat_rate)
    msg = "compute_quote is not implemented yet"
    raise NotImplementedError(msg)
