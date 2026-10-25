"""
supply.py - the raw-material supply risk engine (handoff sections 4-6).

    balance()      daily material balance per ingredient for g06 days from K (the Monday after the as-of week):
                   closing = opening + confirmed receipts + planned receipts - use
                   * opening   = both plants' closing pulp of week W, pooled (A41), less any quality hold (b09)
                   * confirmed = purchase orders placed by K and not yet received; overdue and not-shipped
                                 orders are NOT counted (R12); road orders due inside a closure are held
                   * planned   = the normal standing orders, sized to the forecast requirement and arriving after
                                 the lead time; shown separately because they are not confirmed (A44)
                   * use       = production to the pulp-percentile forecast (f03), capped by plant capacity
                   First unsafe day = first day below the safety buffer (g05 days of use); run-out = below zero.
    risks()        the R01-R27 rules: status, evidence, first unsafe day, fastest lever, lead-time gap.
    mitigations()  compare-and-choose table for the passionfruit / dragonfruit flavors (pathway C), the guava
                   ladder (B) and the Mango Peach Basil check (A). The winner becomes a review candidate.
Nothing here executes anything. Costs are premiums actually implied by case figures; contribution figures
are exposure estimates (uniform ₹ margin proxy), never "avoided savings".
"""
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
from scipy.optimize import linprog

from ..data import store
from . import forecast as F

INGS = ["passionfruit", "dragonfruit", "mango", "peach", "basil", "guava"]
ING_SKUS = {"passionfruit": ["PP", "DP"], "dragonfruit": ["DB", "DP"], "mango": ["MPB"], "peach": ["MPB"],
            "basil": ["MPB"], "guava": ["GC"]}
SUP_ING = {"S_PASSION": "passionfruit", "S_DRAGON_DOM": "dragonfruit", "S_DRAGON_IMP": "dragonfruit",
           "S_MANGO": "mango", "S_PEACH": "peach", "S_BASIL": "basil", "S_GUAVA1": "guava", "S_GUAVA2": "guava"}
SKUS = F.SKUS


def contribution(ctl):
    return ctl["d05"] * ctl["d06"]


def unit_cost(ctl):
    return ctl["d05"] * (1 - ctl["d06"])


def cap_daily(ctl):
    return ctl["e01"] * 1e7 * 12 / 365 * ctl["e02"]


# ----------------------------------------------------------------------------------------- closures
def closures(w, ctl):
    """Closure windows the planner can know at K, plus the hypothetical one (b01/b02)."""
    s = store()
    K, last = w + timedelta(7), w + timedelta(6)
    out = []
    for r in s.closures[s.closures.closed == "Y"].itertuples():
        if r.start is None or r.start != r.start:
            continue
        if r.start <= K and (r.start > last or r.end >= last):          # still closed on the last known day
            end = r.start + timedelta(int(ctl["b02"]) - 1)
            note = f"under way since {r.start:%d %b}; end unknown, planned at {int(ctl['b02'])} days (b02)"
            if end < K:
                end = K + timedelta(6)
                note = f"under way since {r.start:%d %b}, already longer than {int(ctl['b02'])} days; reviewed weekly"
            out.append(dict(start=r.start, end=end, kind="known", note=note))
    if ctl["b01"] >= 0:
        st = K + timedelta(int(ctl["b01"]))
        out.append(dict(start=st, end=st + timedelta(int(ctl["b02"]) - 1), kind="hypothetical",
                        note=f"hypothetical, from day {int(ctl['b01'])} for {int(ctl['b02'])} days (b01, b02)"))
    return out


def _closed(day, wins):
    return any(c["start"] <= day <= c["end"] for c in wins)


def _reopen(day, wins):
    for c in wins:
        if c["start"] <= day <= c["end"]:
            return c["end"] + timedelta(1)
    return day


def landslide_months():
    """Months in which closures on record started (Derived from closures_history; dates Assumed there)."""
    s = store()
    c = s.closures[s.closures.closed == "Y"]
    return sorted({d.month for d in c.start if d == d and d is not None})


# ----------------------------------------------------------------------------------------- inputs
def opening(w, ctl):
    s = store()
    p = s.pulp[s.pulp.week_start == w].groupby("ingredient").closing_kg.sum()
    return {i: float(p.get(i, 0.0)) * (1 - ctl["b09"]) for i in INGS}


def confirmed(w, ctl, wins):
    """Open purchase orders at K: ETA (with scenario delays), and those excluded with a reason."""
    s = store()
    K = w + timedelta(7)
    po = s.po[(s.po.order_date <= K) & (s.po.received_date.isna() | (s.po.received_date >= K))
              & (s.po.promised_date >= K - timedelta(30))]                 # older unfilled orders are closed
    rows, excluded = [], []
    for r in po.itertuples():
        ing = SUP_ING.get(r.supplier)
        if ing is None:
            continue
        if str(r.status).startswith("not shipped"):
            excluded.append(dict(po=r.po_id, ing=ing, kg=r.qty_kg, why="not shipped (road closed)"))
            continue
        delay = ctl["a09"] if r.mode == "sea" else (ctl["a10"] if r.mode == "road" else 0)
        eta = r.promised_date + timedelta(int(delay))
        if r.promised_date < K:
            excluded.append(dict(po=r.po_id, ing=ing, kg=r.qty_kg, why=f"overdue since {r.promised_date:%d %b}; ETA unconfirmed"))
            continue
        held = False
        if ing == "passionfruit" and r.mode == "road" and _closed(eta, wins):
            eta = _reopen(eta, wins) + timedelta(int(ctl["a01"]))
            held = True
        if r.supplier == "S_GUAVA1" and ctl["b04"] > 0 and (r.promised_date - timedelta(int(ctl["a04"]))) >= K:
            excluded.append(dict(po=r.po_id, ing=ing, kg=r.qty_kg, why="guava supplier 1 stopped before dispatch (b04)"))
            continue
        rows.append(dict(po=r.po_id, ing=ing, supplier=r.supplier, mode=r.mode, kg=float(r.qty_kg), eta=eta,
                         held=held, ordered=r.order_date))
    return rows, excluded


# ----------------------------------------------------------------------------------------- simulation
def _plan(w, ctl, H, prod_scale=None, shock=None, col="p_fg"):
    """Daily production plan per flavor = demand at the chosen percentile, capped by capacity (pro rata).
    col p_fg = finished-goods percentile (f04, expected run); p_raw = pulp percentile (f03, stress run)."""
    dem = F.daily_by_sku(w, ctl, H, col)
    K = w + timedelta(7)
    cap = np.full(H, cap_daily(ctl))
    for i in range(H):
        if i < ctl["b08"]:
            cap[i] *= (1 - ctl["b07"])
        cap[i] *= (1 - ctl["b10"])
    plan = {s: dem[s].copy() for s in SKUS}
    if shock:
        for s, add in shock.items():
            plan[s] = plan[s] + add
    tot = sum(plan[s] for s in SKUS)
    scale = np.where(tot > cap, cap / np.maximum(tot, 1e-9), 1.0)
    base_plan = {s: plan[s] * scale for s in SKUS}                    # what standing pulp orders are sized on
    plan = {s: base_plan[s] * (np.asarray(prod_scale.get(s, 1.0)) if prod_scale else 1.0) for s in SKUS}
    return plan, dem, cap, tot, base_plan


PCD = ("PP", "DB", "DP")


def _day_lp(R, plan_j, pf, dfk, floor):
    """One day's allocation of scarce passionfruit / dragonfruit across PP, DB, DP: most bottles,
    every flavor at least `floor` of its plan if that is possible (otherwise the floor is dropped and flagged)."""
    A = [[R["PP"]["passionfruit"], 0, R["DP"]["passionfruit"]], [0, R["DB"]["dragonfruit"], R["DP"]["dragonfruit"]]]
    for fl in (floor, 0.0):
        r = linprog([-1, -1, -1], A_ub=A, b_ub=[pf, dfk], bounds=[(fl * plan_j[s], plan_j[s]) for s in PCD], method="highs")
        if r.status == 0:
            return dict(zip(PCD, r.x)), fl == floor
    return {s: 0.0 for s in PCD}, False


def simulate(w, ctl, prod_scale=None, extra=None, planned=True, shock=None, col="p_fg", alloc="prorata"):
    """Day-by-day balance. extra: {ingredient: np.array kg/day} of approved incremental receipts (options).
    prod_scale: {flavor: float or per-day array} multiplying the production plan (options).
    alloc: how short pulp is shared on a day - 'prorata' (no action) or 'lp' (joint allocation, handoff 5.2)."""
    H = int(ctl["g06"])
    K = w + timedelta(7)
    days = [K + timedelta(i) for i in range(H)]
    wins = closures(w, ctl)
    R = F.recipe(ctl)
    plan, dem, cap, tot, base_plan = _plan(w, ctl, H, prod_scale, shock, col)
    open_ = opening(w, ctl)
    conf, excl = confirmed(w, ctl, wins)
    rc = {i: np.zeros(H) for i in INGS}
    for c in conf:
        j = (c["eta"] - K).days
        if 0 <= j < H:
            rc[c["ing"]][j] += c["kg"]
    req = {i: sum(plan[s] * R[s].get(i, 0) for s in SKUS) for i in INGS}
    req_orders = {i: sum(base_plan[s] * R[s].get(i, 0) for s in SKUS) for i in INGS}   # orders follow the forecast
    rp = {i: np.zeros(H) for i in INGS}
    if planned:
        for i in INGS:
            lead = int(ctl["a01"] if i == "passionfruit" else ctl["a04"])
            share = ctl["d11"] if i == "dragonfruit" else 1.0
            for j in range(lead, H):
                d = days[j]
                if i == "passionfruit" and (_closed(d, wins) or _closed(d - timedelta(lead), wins)):
                    continue
                q = req_orders[i][j] * share
                if i == "guava" and j - lead < ctl["b04"]:
                    q *= (1 - ctl["b05"])
                if i in ("mango", "peach", "basil") and j - lead < ctl["b06"]:
                    q *= ctl["c06"]                      # only a confirmed alternate processor supplies (R01-R03)
                rp[i][j] = q
    ex = {i: (extra.get(i, np.zeros(H)) if extra else np.zeros(H)) for i in INGS}

    stock = {i: open_[i] for i in INGS}
    unc = {i: open_[i] for i in INGS}
    closing = {i: np.zeros(H) for i in INGS}
    closing_unc = {i: np.zeros(H) for i in INGS}
    made = {s: np.zeros(H) for s in SKUS}
    floor_miss = 0
    for j in range(H):
        for i in INGS:
            inc = rc[i][j] + rp[i][j] + ex[i][j]
            stock[i] += inc
            unc[i] += inc - req[i][j]
            closing_unc[i][j] = unc[i]
        fill_i = {}
        for i in INGS:
            need = req[i][j]
            fill_i[i] = 1.0 if need <= 0 else max(0.0, min(1.0, stock[i] / need))
        for s in SKUS:
            f = min([fill_i[i] for i in R[s]] or [1.0])
            made[s][j] = plan[s][j] * f
        if alloc == "lp" and (fill_i["passionfruit"] < 1 or fill_i["dragonfruit"] < 1):
            x, floor_ok = _day_lp(R, {s: plan[s][j] for s in PCD}, stock["passionfruit"], stock["dragonfruit"], ctl["g07"])
            for s in PCD:
                made[s][j] = x[s]
            floor_miss += 0 if floor_ok else 1
        for i in INGS:
            stock[i] -= sum(made[s][j] * R[s].get(i, 0) for s in SKUS)
            stock[i] = max(stock[i], 0.0)
            closing[i][j] = stock[i]

    res = {}
    for i in INGS:
        avg = float(req[i][:14].mean()) if H >= 14 else float(req[i].mean())
        safety = ctl["g05"] * avg
        unsafe = next((days[j] for j in range(H) if closing_unc[i][j] < safety), None)
        out = next((days[j] for j in range(H) if closing_unc[i][j] < 0), None)
        res[i] = dict(open=open_[i], confirmed=rc[i], planned=rp[i], extra=ex[i], use=req[i], closing=closing[i],
                      closing_unc=closing_unc[i], safety=safety, avg_use=avg, cover=open_[i] / avg if avg else None,
                      first_unsafe=unsafe, first_out=out,
                      days_to_unsafe=(unsafe - K).days if unsafe else None, days_to_out=(out - K).days if out else None)
    short = {s: float((plan[s] - made[s]).sum()) for s in SKUS}             # pulp-limited shortfall
    return dict(days=days, K=K, ing=res, plan=plan, made=made, demand=dem, short=short, cap=cap, tot=tot,
                conf=conf, excluded=excl, closures=wins, col=col, floor_miss=floor_miss,
                unmet={s: float((dem[s] - made[s]).clip(min=0).sum()) for s in SKUS},
                cap_short=float((tot - cap).clip(min=0).sum()))


@lru_cache(maxsize=64)
def balance(w, ctl):
    """planned: expected run (finished-goods percentile f04) with normal standing orders.
    stress: demand at the pulp percentile f03. confirmed_only: expected run, confirmed orders only."""
    return dict(planned=simulate(w, ctl), stress=simulate(w, ctl, col="p_raw"),
                confirmed_only=simulate(w, ctl, planned=False))


# ----------------------------------------------------------------------------------------- levers
def levers(w, ctl, ing):
    """Response levers for an ingredient, with lead time and whether they are available now."""
    wins = closures(w, ctl)
    K = w + timedelta(7)
    road_closed = _closed(K, wins)
    L = []
    if ing == "passionfruit":
        L.append(dict(name="Reorder from the cooperative (road)", lead=ctl["a01"], ok=not road_closed,
                      why="road closed" if road_closed else "", ref="a01 · F40"))
        L.append(dict(name="Air freight", lead=ctl["a05"], ok=ctl["c04"] > 0, why="" if ctl["c04"] > 0 else "no air capacity set (c04)",
                      ref="a05 · G16"))
        L.append(dict(name="Cooperative surge before a closure", lead=ctl["a01"], ok=ctl["c05"] > 0 and not road_closed,
                      why="surge capacity not confirmed (c05 = 0)" if ctl["c05"] <= 0 else ("road closed" if road_closed else ""), ref="c05 · G31"))
        L.append(dict(name="Second supplier", lead=None, ok=False, why="none qualified (F35); a qualification project, not an order",
                      ref="F35"))
    elif ing == "dragonfruit":
        L.append(dict(name="Extra domestic dragonfruit", lead=ctl["a04"], ok=ctl["c03"] > 0,
                      why="" if ctl["c03"] > 0 else "spare capacity not confirmed (c03 = 0); 60% is a mix, not a cap", ref="c03 · G30"))
        L.append(dict(name="New import order", lead=ctl["a02"], ok=True, why="", ref="a02-a03 · F16"))
    elif ing == "guava":
        L.append(dict(name="Guava supplier 2 ramp-up", lead=ctl["c02"] + ctl["a04"], ok=ctl["c01"] > 0,
                      why="" if ctl["c01"] > 0 else "extra capacity not confirmed (c01 = 0)", ref="c01-c02 · G29"))
    else:
        L.append(dict(name=f"Alternate {ing} processor", lead=ctl["a04"], ok=ctl["c06"] > 0,
                      why="" if ctl["c06"] > 0 else "no qualified alternate confirmed (c06 = 0)", ref="c06 · G32"))
        L.append(dict(name=f"Normal {ing} reorder", lead=ctl["a04"], ok=ctl["b06"] <= 0, why="supplier outage (b06)" if ctl["b06"] > 0 else "",
                      ref="a04 · G07"))
    return L


def lead_gap(w, ctl, ing, r):
    """Days to the first unsafe day minus the fastest available lever's lead time."""
    L = [x for x in levers(w, ctl, ing) if x["ok"] and x["lead"] is not None]
    if r["first_unsafe"] is None:
        return None, (min(L, key=lambda x: x["lead"]) if L else None)
    if not L:
        return None, None
    best = min(L, key=lambda x: x["lead"])
    return r["days_to_unsafe"] - best["lead"], best


# ----------------------------------------------------------------------------------------- mitigation options
def _air_kg(w, ctl, sim):
    """Air freight plan: c04 kg/day from booking + a05 until the road reopens (+ transit)."""
    H = int(ctl["g06"])
    K = sim["K"]
    wins = sim["closures"]
    arr = np.zeros(H)
    for j in range(int(ctl["a05"]), H):
        d = K + timedelta(j)
        if _closed(d, wins) or _closed(d - timedelta(int(ctl["a01"])), wins):
            arr[j] = ctl["c04"]
    return arr


def normal_freight_per_kg(ctl):
    if ctl["d10"] > 0:
        return ctl["d10"], "Assumed (d10)"
    s = store()
    a = s.po[(s.po["mode"] == "air") & s.po.freight_cost_inr.notna()]
    if a.empty or a.qty_kg.sum() <= 0:
        return 0.0, "not derivable"
    return float(a.freight_cost_inr.sum() / ctl["a06"] / a.qty_kg.sum()), "Derived: sample air spend ÷ a06 ÷ kg airlifted"


def short_window(sim):
    """Last day index on which pulp limits PP, DB or DP production (None if never)."""
    gap = sum(sim["plan"][s] - sim["made"][s] for s in PCD)
    idx = np.nonzero(gap > 1.0)[0]
    return int(idx[-1]) if len(idx) else None


def _window_scale(H, end, value):
    a = np.ones(H)
    a[: end + 1] = value
    return a


def joint_schedule(sim, ctl, extra=None):
    """Joint allocation of passionfruit and dragonfruit to PP, DB, DP over the whole horizon (handoff 5.2),
    with stock carried day to day: on every day t, pulp used up to t <= opening + receipts up to t.
    Maximises bottles (equal margin per bottle); a tiny weight prefers earlier bottles. Service floor g07 is
    applied per flavor over the horizon; if it cannot be met, that is reported, not hidden.
    Returns per-day production multipliers for the daily balance to re-check."""
    R = F.recipe(ctl)
    H = len(sim["days"])
    plan = {s: sim["plan"][s] for s in PCD}
    n = 3 * H
    c = np.zeros(n)
    for k, s in enumerate(PCD):
        c[k * H:(k + 1) * H] = -(1 - 1e-4 * np.arange(H) / H)
    A, b = [], []
    for ing in ("passionfruit", "dragonfruit"):
        r = sim["ing"][ing]
        inflow = np.cumsum(r["confirmed"] + r["planned"] + (extra.get(ing, 0) if extra else 0)) + r["open"]
        coef = {s: R[s].get(ing, 0) for s in PCD}
        for t in range(H):
            row = np.zeros(n)
            for k, s in enumerate(PCD):
                row[k * H: k * H + t + 1] = coef[s]
            A.append(row)
            b.append(inflow[t])
    floor = ctl["g07"]
    floor_ok = True
    for k, s in enumerate(PCD):
        if floor > 0 and plan[s].sum() > 0:
            row = np.zeros(n)
            row[k * H:(k + 1) * H] = -1
            A.append(row)
            b.append(-floor * plan[s].sum())
    bounds = [(0, plan[s][t]) for s in PCD for t in range(H)]
    r = linprog(c, A_ub=np.array(A), b_ub=np.array(b), bounds=bounds, method="highs")
    if r.status != 0 and floor > 0:
        floor_ok = False
        A, b = A[:2 * H], b[:2 * H]
        r = linprog(c, A_ub=np.array(A), b_ub=np.array(b), bounds=bounds, method="highs")
    if r.status != 0:
        return None, False
    x = r.x
    scale = {s: np.where(plan[s] > 0, x[k * H:(k + 1) * H] / np.maximum(plan[s], 1e-9), 1.0) for k, s in enumerate(PCD)}
    return scale, floor_ok


@lru_cache(maxsize=32)
def mitigations(w, ctl):
    """Pathway C (PP / DB / DP): compare options on the same horizon, choose, and hand to review."""
    base = balance(w, ctl)["planned"]
    m = contribution(ctl)
    pf, df = base["ing"]["passionfruit"], base["ing"]["dragonfruit"]
    relevant = ("PP", "DB", "DP")
    unmet0 = sum(base["unmet"][s] for s in relevant)
    nf, nf_src = normal_freight_per_kg(ctl)
    opts = []

    def add(key, name, sim, cost, lead, feasible, why, note=""):
        unmet = sum(sim["unmet"][s] for s in relevant)
        protected = (unmet0 - unmet) * m
        opts.append(dict(key=key, name=name, unmet=unmet, by={s: sim["unmet"][s] for s in relevant},
                         exposure=unmet * m, protected=protected, cost=cost, net=protected - cost, lead=lead,
                         feasible=feasible, why=why, note=note,
                         pf_unsafe=sim["ing"]["passionfruit"]["first_unsafe"], df_unsafe=sim["ing"]["dragonfruit"]["first_unsafe"],
                         sim=sim))

    add("none", "No action", base, 0.0, 0, True, "", "produce to forecast; when pulp runs short, PP, DB and DP share it pro rata")
    H = int(ctl["g06"])
    end = short_window(base)

    # case response: cut PP to protect DP (F58), while pulp is short
    if end is not None:
        cut = simulate(w, ctl, prod_scale={"PP": _window_scale(H, end, 1 - ctl["d13"])})
        add("cut_pp", f"Cut Passionfruit Punch by {ctl['d13']:.0%} while pulp is short (the case's response)", cut, 0.0, 0,
            True, "", "F58 · d13")

        # joint optimisation over the horizon, stock carried day to day (handoff 5.2)
        sc, floor_ok = joint_schedule(base, ctl)
        if sc is not None:
            sim = simulate(w, ctl, prod_scale=sc)
            add("joint", "Joint pulp allocation across PP, DB, DP", sim, 0.0, 0, True, "",
                "linear program over the horizon with dated receipts: most bottles from the pulp (equal margin per bottle); "
                f"service floor g07 = {ctl['g07']:.0%}" + ("" if floor_ok else " could NOT be met for every flavor: dropped and flagged"))

    # air freight (passionfruit), alone and with the joint allocation
    air = _air_kg(w, ctl, base)
    if air.sum() > 0 and ctl["c04"] > 0 and end is not None:
        cost = float(air.sum()) * nf * (ctl["a06"] - 1)
        sim = simulate(w, ctl, extra={"passionfruit": air})
        add("air", f"Air-freight passionfruit ({ctl['c04']:,.0f} kg/day while the road is shut)", sim, cost, ctl["a05"], True, "",
            f"{air.sum():,.0f} kg; premium {ctl['a06'] - 1:g}x normal freight of {nf:,.0f} ₹/kg ({nf_src})")
        sc2, _ = joint_schedule(sim, ctl, extra={"passionfruit": air})
        if sc2 is not None:
            sim2 = simulate(w, ctl, prod_scale=sc2, extra={"passionfruit": air})
            add("air_joint", "Air freight + joint allocation", sim2, cost, ctl["a05"], True, "", "both levers")
    else:
        opts.append(dict(key="air", name="Air-freight passionfruit", feasible=False, unmet=None, exposure=None,
                         protected=None, cost=None, net=None, lead=ctl["a05"], note="",
                         why=("no air capacity set (c04)" if ctl["c04"] <= 0 else
                              "road open for the whole horizon" if air.sum() == 0 else "no pulp shortage to fix"), by={}))

    # domestic dragonfruit expansion
    if ctl["c03"] > 0:
        ex = np.zeros(int(ctl["g06"]))
        ex[int(ctl["a04"]):] = ctl["c03"]
        sim = simulate(w, ctl, extra={"dragonfruit": ex})
        add("dom_df", f"Extra domestic dragonfruit ({ctl['c03']:,.0f} kg/day, confirmed)", sim, 0.0, ctl["a04"], True, "",
            "price premium unknown (G33): cost not counted")
    else:
        opts.append(dict(key="dom_df", name="Extra domestic dragonfruit", feasible=False, unmet=None, exposure=None,
                         protected=None, cost=None, net=None, lead=ctl["a04"], note="",
                         why="needs a confirmed figure from the supplier (c03 = 0, G30)", by={}))

    # co-packer: adds bottles, not pulp (R25)
    from .copacker import evaluate as cp_eval
    cp = cp_eval(w, ctl)
    opts.append(dict(key="copacker", name="Call the co-packer", feasible=False, unmet=None, exposure=None, protected=None,
                     cost=None, net=None, lead=ctl["d09"], note="",
                     why="adds bottling capacity, not pulp: the same scarce pulp would be routed to it (R25)"
                     + ("" if cp["eligible"] else "; also not eligible this week"), by={}))

    # second supplier
    opts.append(dict(key="second", name="Qualify a second passionfruit supplier", feasible=False, unmet=None, exposure=None,
                     protected=None, cost=None, net=None, lead=None, note="",
                     why="none qualified (F35): a medium-term project, not an executable order", by={}))

    # choose: feasible, starts before the first run-out, best net; ties -> lowest cost, then shortest lead
    first_out = min([d for d in (pf["first_out"], df["first_out"]) if d], default=None)
    for o in opts:
        o["in_time"] = (first_out is None or o["lead"] is None or o["lead"] is not None and base["K"] + timedelta(int(o["lead"] or 0)) <= first_out)
    cands = [o for o in opts if o["feasible"] and o["in_time"] and o["unmet"] is not None]
    win = None
    if end is not None and cands:
        win = max(cands, key=lambda o: (round(o["net"], -3), -(o["cost"] or 0), -(o["lead"] or 0)))
        if win["key"] == "none":
            win = None
    for o in opts:
        o["winner"] = win is not None and o["key"] == win["key"]
    rec = None
    if win:
        rec = dict(id=f"SUP-C-{w.isoformat()}-{win['key']}", title=f"Pathway C: {win['name']}", module="Supply",
                   owner="COO" if win["cost"] and win["cost"] > 0 else "Production",
                   detail=f"Leaves {win['unmet']:,.0f} bottles of PP/DB/DP unmet over {int(ctl['g06'])} days vs "
                          f"{unmet0:,.0f} with no action. Extra cost ₹{win['cost']:,.0f}.")
    return dict(options=opts, winner=win, rec=rec, unmet0=unmet0, first_out=first_out, nf=nf, nf_src=nf_src,
                margin=m, need=end is not None, end=base["days"][end] if end is not None else None)


@lru_cache(maxsize=64)
def demand_scenarios(w, ctl, sku, base_daily, mult, src="QC"):
    """What a demand rise on one flavor's quick commerce would threaten, under hold / decay / fade (spec 4.2-4.3).
    For each scenario: extra bottles, the first unsafe day of that flavor's pulp, whether demand breaks plant
    capacity, and warning time vs each lever's response time."""
    from .copacker import evaluate as cp_eval
    H = int(ctl["g06"])
    R = F.recipe(ctl)
    base = balance(w, ctl)["planned"]
    out = []
    levers_rt = [("Air freight (passionfruit)", ctl["a05"]), ("Co-packer", ctl["d09"]), ("Depot transfer", ctl["a07"]),
                 ("Domestic pulp reorder", ctl["a04"]), ("Import order (dragonfruit)", ctl["a02"])]
    for name, extra in F.persistence(ctl, base_daily, mult, H).items():
        sim = simulate(w, ctl, shock={sku: extra})
        hit = []
        for ing in R[sku]:
            r, r0 = sim["ing"][ing], base["ing"][ing]
            if r["first_unsafe"] and (r0["first_unsafe"] is None or r["first_unsafe"] < r0["first_unsafe"]):
                hit.append(dict(ing=ing, day=r["first_unsafe"], days=r["days_to_unsafe"],
                                before=r0["first_unsafe"]))
        over = next((d for d, t, c in zip(sim["days"], sim["tot"], sim["cap"]) if t > c), None)
        first = min([h["days"] for h in hit], default=None)
        warn = first if first is not None else ((over - sim["K"]).days if over else None)
        out.append(dict(name=name, extra=float(extra.sum()), hit=hit, cap_from=over, warning=warn,
                        levers=[dict(lever=l, response=rt, in_time=(warn is None or rt <= warn)) for l, rt in levers_rt],
                        short=float(sum(sim["short"].values()) - sum(base["short"].values()))))
    return out


@lru_cache(maxsize=16)
def replay_closure(ctl, w=date(2026, 5, 4)):
    """Replay of the May 2026 closure as the engine would have seen it on the Monday it began (K = 11 May).
    Reports the pre-season warning, detection, projected unsafe / run-out days, when air had to be booked,
    and the lead over the month-end signal Planning gets today (F30)."""
    s = store()
    sim = balance(w, ctl)["planned"]
    pf = sim["ing"]["passionfruit"]
    K = sim["K"]
    c = s.closures[(s.closures.closed == "Y") & (s.closures.year == K.year)]
    start = c.start.iloc[0] if len(c) else None
    season = landslide_months()
    pre = None
    for wk in [x for x in s.weeks if K - timedelta(70) <= x < w + timedelta(1)]:
        kk = wk + timedelta(7)
        cov = balance(wk, ctl)["planned"]["ing"]["passionfruit"]["cover"]
        if ((kk + timedelta(28)).month in season or kk.month in season) and cov is not None and cov < ctl["b02"] + ctl["g05"]:
            pre = kk
            break
    book_by = pf["first_unsafe"] - timedelta(int(ctl["a05"])) if pf["first_unsafe"] else None
    air = s.po[(s.po["mode"] == "air") & (s.po.order_date.apply(lambda d: d.year) == K.year)]
    booked = air.order_date.min() if len(air) else None
    month_end = date(K.year + (K.month == 12), K.month % 12 + 1, 1) - timedelta(1)
    sees = s.dem[s.dem.week_start == (pf["first_out"] - timedelta(pf["first_out"].weekday()))].visible_to_planning if pf["first_out"] else None
    try:
        sees = date.fromisoformat(str(sees.iloc[0])) if sees is not None and len(sees) else month_end
    except ValueError:
        sees = month_end
    return dict(start=start, detected=K if start and start <= K else None, pre_warning=pre,
                pre_lead=(start - pre).days if pre and start else None,
                first_unsafe=pf["first_unsafe"], first_out=pf["first_out"], book_by=book_by, booked=booked,
                book_gap=(booked - book_by).days if booked and book_by else None,
                planning_sees=sees, lead=(sees - K).days if sees else None, cover=pf["cover"])


def illustrative_allocation(ctl):
    """Handoff 5.5, made-up numbers, recomputed with the current recipe: PP-priority vs a DP-heavy mix."""
    R = F.recipe(ctl)
    pf, dfk, pp_d, dp_d = 3000.0, 1800.0, 40000.0, 80000.0
    pp1 = min(pp_d, pf / R["PP"]["passionfruit"])
    dp1 = min(dp_d, (pf - pp1 * R["PP"]["passionfruit"]) / R["DP"]["passionfruit"], dfk / R["DP"]["dragonfruit"])
    dp2 = min(dp_d, dfk / R["DP"]["dragonfruit"], pf / R["DP"]["passionfruit"])
    pp2 = min(pp_d, (pf - dp2 * R["DP"]["passionfruit"]) / R["PP"]["passionfruit"])
    return [dict(mix="PP first", pp=pp1, dp=dp1, total=pp1 + dp1, pp_fill=pp1 / pp_d),
            dict(mix="Most bottles from the pulp", pp=pp2, dp=dp2, total=pp2 + dp2, pp_fill=pp2 / pp_d)]


# ----------------------------------------------------------------------------------------- pathways A and B
@lru_cache(maxsize=32)
def guava_ladder(w, ctl):
    """Pathway B: supplier-1 stop -> pipeline bridge -> supplier-2 ramp -> partial/full reallocation."""
    sim = balance(w, ctl)["planned"]
    g = sim["ing"]["guava"]
    need = g["avg_use"]
    s1 = ctl["b05"] * need
    conf = [c for c in sim["conf"] if c["ing"] == "guava"]
    pipe = sum(c["kg"] for c in conf)
    bridge_days = (g["open"] + pipe - g["safety"]) / need if need else None
    ramp_at = ctl["c02"] + ctl["a04"]
    cover_s2 = min(1.0, ctl["c01"] / s1) if s1 > 0 else 1.0
    if ctl["b04"] <= 0:
        verdict, step = "No guava outage reported. Ladder shown with today's numbers.", 0
    elif cover_s2 >= 1 and bridge_days is not None and bridge_days >= ramp_at:
        verdict, step = "Supplier 2 can replace supplier 1 before stock falls below the buffer: keep Guava Chilli output.", 3
    elif cover_s2 > 0:
        verdict, step = f"Supplier 2 covers {cover_s2:.0%} of the lost guava: partial ramp + selective reallocation.", 4
    else:
        verdict, step = "No confirmed supplier-2 capacity: plan reallocation; ask supplier 2 for a figure (c01).", 4
    steps = [
        dict(n=1, t="Supplier 1 stops", d=f"Loses {s1:,.0f} kg/day ({ctl['b05']:.0%} of {need:,.0f} kg/day, split Assumed G06) "
                                          f"for {int(ctl['b04'])} days (b04)."),
        dict(n=2, t="Bridge on stock + confirmed pipeline", d=f"On hand {g['open']:,.0f} kg + {pipe:,.0f} kg dispatched and due "
                                                              f"= {bridge_days:.1f} days above the buffer." if bridge_days is not None else "No guava use."),
        dict(n=3, t="Ask supplier 2 to ramp", d=f"Confirmed extra {ctl['c01']:,.0f} kg/day (c01) arriving from day {ramp_at:.0f} "
                                                f"(c02 + a04): covers {cover_s2:.0%} of the loss."),
        dict(n=4, t="If short: reallocate", d="Partial ramp + produce other flavors only up to genuinely substitutable demand "
                                              f"(switching share d12 = {ctl['d12']:.0%}, a hypothesis)."),
        dict(n=5, t="Reassess daily", d="As arrivals, demand and supplier restoration plans change; approval before any order."),
    ]
    rec = None
    if ctl["b04"] > 0:
        rec = dict(id=f"SUP-B-{w.isoformat()}-{int(ctl['b04'])}", title="Pathway B: guava supplier switch", module="Supply",
                   owner="Procurement", detail=verdict)
    return dict(steps=steps, verdict=verdict, step=step, bridge_days=bridge_days, ramp_at=ramp_at, cover_s2=cover_s2,
                caution="Three days of transit is not three days of guaranteed supply: it exists only for volume already "
                        "dispatched and still due (handoff 4, caution).", rec=rec, first_unsafe=g["first_unsafe"])


@lru_cache(maxsize=32)
def mpb_check(w, ctl):
    """Pathway A: any one of mango, peach or basil limits Mango Peach Basil."""
    sim = balance(w, ctl)["planned"]
    R = F.recipe(ctl)
    rows = []
    for i in ("mango", "peach", "basil"):
        r = sim["ing"][i]
        avail = r["open"] + r["confirmed"].sum() + r["planned"].sum() - r["safety"]
        rows.append(dict(ing=i, cover=r["cover"], first_unsafe=r["first_unsafe"], max_bottles=avail / R["MPB"][i] if R["MPB"][i] else None))
    lim = min(rows, key=lambda x: x["max_bottles"] if x["max_bottles"] is not None else 1e18)
    plan = float(sim["plan"]["MPB"].sum())
    short = max(0.0, plan - (lim["max_bottles"] or 0))
    from .inventory_iface import fg_position
    fg = fg_position(w, ctl)["MPB"]
    return dict(rows=rows, limiting=lim["ing"], max_bottles=lim["max_bottles"], plan=plan, short=short,
                fg_days=fg["cover"], switch=short * ctl["d12"],
                note="Check excess MPB finished goods at depots before changing production; switching to other "
                     "flavors only up to the hypothetical share d12, and only if pulp, capacity and delivery allow.")
