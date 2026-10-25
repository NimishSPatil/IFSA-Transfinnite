"""
inventory_iface.py - the Supply -> Inventory interface, in its simple prompt-1 form.

Prompt 2 builds the Inventory module properly (depot-level cover, allocation, transfers, ageing).
Here, deliberately simple and pooled nationally:
    fg_position()      finished goods per flavor at the depots as last reported, and how much of it the
                       modern-trade / quick-commerce channels still accept (age filter, g01-g02)
    supply_to_fg()     what the supply balance means for depot stock: the day national stock of each flavor
                       runs out, given ingredient-limited production (the Supply -> Inventory lag)
HOOKS for prompt 2 (keep these signatures):
    fg_position(w, ctl) -> {sku: {...}}                  replace pooling with depot rows
    supply_to_fg(w, ctl, sim) -> {sku: {...}}            replace with depot allocation of `made`
    forecast.depot_forecast(w, ctl, weeks)               depot x flavor demand, shares with shrinkage
"""
from datetime import timedelta
from functools import lru_cache

import numpy as np

from ..data import store
from . import forecast as F

PROMPT2 = "Inventory module: coming in prompt 2"


@lru_cache(maxsize=64)
def fg_position(w, ctl):
    s = store()
    s._inv_extra()
    inv = s.inv[(s.inv.week_start == w) & s.inv.report_received]
    b = s.batches[s.batches.week_start == w]
    max_age = ctl["g01"] - ctl["g02"]                       # oldest bottle MT / QC still take
    daily = F.daily_by_sku(w, ctl, 28, "p_fg")
    missing = sorted(s.inv[(s.inv.week_start == w) & ~s.inv.report_received].depot_id.unique().tolist())
    out = {}
    for sku in F.SKUS:
        on = float(inv[inv.sku_id == sku].closing_stock.sum())
        bs = b[b.sku_id == sku]
        tot_b = float(bs.units.sum())
        mtqc_share = float(bs[bs.age_days <= max_age].units.sum()) / tot_b if tot_b else None   # share from the batch table itself
        mtqc = on * mtqc_share if mtqc_share is not None else 0.0
        rate = float(daily[sku][:14].mean())
        out[sku] = dict(on_hand=on, mtqc_ok=mtqc, mtqc_share=mtqc_share, rate=rate,
                        cover=on / rate if rate else None, missing=missing)
    return out


def supply_to_fg(w, ctl, sim):
    """Pooled national finished-goods projection: FG(t) = FG0 + made(t) - demand(t, P50)."""
    fg = fg_position(w, ctl)
    p50 = F.daily_by_sku(w, ctl, len(sim["days"]), "p50")
    out = {}
    for sku in F.SKUS:
        level = fg[sku]["on_hand"] + np.cumsum(sim["made"][sku] - p50[sku])
        j = next((i for i, v in enumerate(level) if v < 0), None)
        out[sku] = dict(runs_out=sim["days"][j] if j is not None else None, level=level,
                        lag=None)
    return out
