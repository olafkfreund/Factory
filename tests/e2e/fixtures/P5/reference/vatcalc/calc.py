"""Invoice net, VAT, and total calculator (reference implementation)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class Quote:
    """Computed invoice quote with net, VAT, and total amounts."""

    net: Decimal
    vat: Decimal
    total: Decimal


def compute_quote(net: Decimal | str, vat_rate: Decimal | str = "0.175") -> Quote:
    """Compute `(net, vat, total)` for the given net amount and VAT rate."""
    net_dec = Decimal(str(net)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    rate_dec = Decimal(str(vat_rate))
    if net_dec < Decimal("0.00"):
        msg = "net amount must be non-negative"
        raise ValueError(msg)
    if rate_dec < Decimal("0.00"):
        msg = "vat_rate must be non-negative"
        raise ValueError(msg)
    vat_dec = (net_dec * rate_dec).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    total_dec = net_dec + vat_dec
    return Quote(net=net_dec, vat=vat_dec, total=total_dec)
