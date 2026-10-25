"""
copacker.py - the co-packer rule. Eligible only if ALL three hold:
    A. the forecast for the 2 weeks the co-packer could run (after d09 days' notice) is above the combined
       plants' maximum for those 2 weeks (e01 x e02, less any breakdown / packaging loss), and
    B. the pulp for the extra bottles is there (material balance above the buffer after plant use), and
    C. the volume stays within the cap (d08 of plant volume; case F20).
Economics shown, not decided: premium d07 x unit cost (F21) against the contribution per bottle (F02, F26).
Calling it is a review candidate for a human (F71); nothing is booked.
"""
from datetime import timedelta
from functools import lru_cache

import numpy as np

from . import forecast as F
from .supply import balance, cap_daily, contribution, unit_cost


@lru_cache(maxsize=64)
def evaluate(w, ctl):
    sim = balance(w, ctl)["planned"]
    K = w + timedelta(7)
    n = int(ctl["d09"])
    H = max(int(ctl["g06"]), n + 14)
    dem = F.daily_by_sku(w, ctl, H, "p_fg")
    lo, hi = n, n + 14
    demand2 = {s: float(dem[s][lo:hi].sum()) for s in F.SKUS}
    cap = np.full(H, cap_daily(ctl))
    for i in range(H):
        if i < ctl["b08"]:
            cap[i] *= (1 - ctl["b07"])
        cap[i] *= (1 - ctl["b10"])
    plant2 = float(cap[lo:hi].sum())
    tot2 = sum(demand2.values())
    excess = tot2 - plant2
    cap_cp = ctl["d08"] * plant2
    reasons, checks = [], []

    a = excess > 0
    checks.append(dict(rule="A. Forecast above the plants' maximum for the 2 weeks after notice", ok=a,
                       detail=f"{tot2 / 1e5:,.1f} L bottles forecast (P{int(ctl['f04'])}) vs {plant2 / 1e5:,.1f} L plant maximum, "
                              f"{(K + timedelta(lo)):%d %b}–{(K + timedelta(hi - 1)):%d %b}",
                       tag="Derived: f04, d09, e01, e02 (F22, F32)"))
    if not a:
        reasons.append(f"Forecast is {(-excess) / 1e5:,.1f} L bottles BELOW plant maximum for that fortnight: the plants can make it.")

    vol = max(0.0, min(excess, cap_cp))
    mix = {s: (demand2[s] / tot2 if tot2 else 0) for s in F.SKUS}
    R = F.recipe(ctl)
    ing_ok, short_ings = True, []
    if vol > 0:
        for ing, r in sim["ing"].items():
            need = sum(vol * mix[s] * R[s].get(ing, 0) for s in F.SKUS)
            if need <= 0:
                continue
            window = r["closing_unc"][min(lo, len(r["closing_unc"]) - 1):]
            slack = float(window.min()) - r["safety"] if len(window) else -1
            if slack < need:
                ing_ok = False
                short_ings.append(f"{ing}: needs {need:,.0f} kg, slack {max(slack, 0):,.0f} kg above the buffer")
    b = vol > 0 and ing_ok
    checks.append(dict(rule="B. Pulp available for the extra bottles", ok=b if vol > 0 else None,
                       detail=("; ".join(short_ings) if short_ings else "all ingredients have slack above the buffer")
                       if vol > 0 else "not tested: no excess demand",
                       tag="Derived: material balance, g05"))
    if vol > 0 and not ing_ok:
        reasons.append("Not enough pulp for the extra bottles (" + "; ".join(short_ings) + "). The co-packer adds bottling, not pulp (R25).")
    c = excess <= cap_cp
    checks.append(dict(rule=f"C. Volume kept within the {ctl['d08']:.0%} cap", ok=True if a else None,
                       detail=(f"needs {excess / 1e5:,.1f} L, cap {cap_cp / 1e5:,.1f} L"
                               + ("" if c else f": proposal capped at {cap_cp / 1e5:,.1f} L; {(excess - cap_cp) / 1e5:,.1f} L stays unmet"))
                       if a else f"cap {cap_cp / 1e5:,.1f} L bottles", tag="Given: F20 (d08)"))
    eligible = a and b
    prem = ctl["d07"] * unit_cost(ctl)
    m = contribution(ctl)
    econ = dict(premium_per_bottle=prem, contribution=m, net_per_bottle=m - prem, volume=vol,
                premium_total=vol * prem, contribution_total=vol * m, net_total=vol * (m - prem))
    rec = None
    if eligible:
        rec = dict(id=f"CP-{w.isoformat()}", title=f"Book the co-packer for {vol / 1e5:,.1f} L bottles from {(K + timedelta(lo)):%d %b}",
                   module="Supply", owner="COO",
                   detail=f"Premium ₹{econ['premium_total']:,.0f} vs contribution ₹{econ['contribution_total']:,.0f} (uniform proxy).")
    return dict(eligible=eligible, checks=checks, reasons=reasons, excess=excess, plant2=plant2, demand2=demand2, tot2=tot2,
                cap=cap_cp, volume=vol, capped=a and not c, start=K + timedelta(lo), end=K + timedelta(hi - 1), econ=econ, rec=rec)
