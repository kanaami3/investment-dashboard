"""Position sizing for OANDA index / FX instruments.

For JP225_JPY the quote currency is JPY and 1 unit corresponds to
1 JPY per index point move. So:

    risk_money_jpy = nav_jpy * (risk_pct / 100)
    sl_distance_pts = atr_value * sl_atr_mult
    units = floor(risk_money_jpy / sl_distance_pts)

For FX pairs the quote currency might differ from account currency
(e.g. account JPY, instrument EUR_USD). The simplified version below
treats 1 unit = 1 unit of the base currency exposed; for non-JPY-quoted
FX the caller should multiply by the JPY conversion factor obtained
from the pricing endpoint.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SizingResult:
    units: int
    sl_distance: float
    risk_money: float
    capped: bool


def size_index_units(nav: float, risk_pct: float, atr_value: float,
                     sl_atr_mult: float, max_units: int) -> SizingResult:
    if nav <= 0 or atr_value <= 0 or sl_atr_mult <= 0 or risk_pct <= 0:
        return SizingResult(units=0, sl_distance=0.0, risk_money=0.0, capped=False)
    sl_distance = atr_value * sl_atr_mult
    risk_money = nav * (risk_pct / 100.0)
    raw_units = math.floor(risk_money / sl_distance)
    capped = False
    if max_units > 0 and raw_units > max_units:
        raw_units = max_units
        capped = True
    return SizingResult(units=int(raw_units), sl_distance=sl_distance,
                        risk_money=risk_money, capped=capped)
