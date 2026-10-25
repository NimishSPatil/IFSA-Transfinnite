"""
inventory.py - the Inventory module (prompt 2): the teammate's rebalancing feed, reconciled and wired to the Control Panel.

Source: data/inventory_feed/dashboard_data.json (byte-identical payload to dashboard_data_1.js, which exposes
window.DASHBOARD_DATA for a static page; this server reads the JSON). Its weekly rows are dataset v2's inventory_weekly
(same receipts and P50; closing stock within 1 bottle of rounding), replayed with 113 transfers chosen by an OFFLINE optimiser.

What recalculates live (financial): loss rates h01/h02, transport per bottle a08, overstock threshold h03, write-off rate h05.
Loss is recomputed on the stored weekly rows; transport on the stored transfers.
What does not (optimiser-dependent): minimum lot h04, transit a07, sender/receiver thresholds h06/h07. The transfers are
precomputed; replicate() reports how far a transparent greedy rule reproduces them.
No accuracy is claimed from the file: P50/P80 are the file's static forecasts.
"""
import json
import math
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

FEED = Path(__file__).resolve().parents[3] / "data" / "inventory_feed"
SKUS = ["MPB", "GC", "PP", "DB", "DP"]
DEPOTS = ["D_N1", "D_N2", "D_S1", "D_S2", "D_E1", "D_E2", "D_W1", "D_W2", "D_W3"]
CR = 1e7
HANDOFF = dict(loss_before=21.79, loss_after=19.08, transport=0.76, after_total=19.84, saving=1.96, transfers=113, bottles_lakh=50.75)
YEAR_NET = {2024: -0.09, 2025: -0.23, 2026: 2.28}

WINDOWS = {
    "summer26": ("Mar–Jun 2026 (case summer)", date(2026, 3, 1), date(2026, 6, 30)),
    "y2026": ("2026", date(2026, 1, 1), date(2026, 12, 31)),
    "summer25": ("Mar–Jun 2025", date(2025, 3, 1), date(2025, 6, 30)),
    "y2025": ("2025", date(2025, 1, 1), date(2025, 12, 31)),
    "y2024": ("2024", date(2024, 1, 1), date(2024, 12, 31)),
    "all": ("Whole file (Jan 2024 – Jun 2026)", date(2024, 1, 1), date(2026, 12, 31)),
}


@lru_cache(maxsize=1)
def feed():
    raw = json.loads((FEED / "dashboard_data.json").read_text(encoding="utf-8"))
    js = (FEED / "dashboard_data_1.js").read_text(encoding="utf-8").strip()
    js_same = json.loads(js[js.index("=") + 1:].rstrip(";").strip()) == raw
    w = pd.DataFrame(raw["weekly"])
    w["ws"] = pd.to_datetime(w.week_start).dt.date
    w["year"] = [d.year for d in w.ws]
    w["ym"] = [f"{d.year}-{d.month:02d}" for d in w.ws]
    for s in ("before", "after"):
        w[f"cov_{s}"] = w[f"closing_{s}"] / (w.p50 / 7).where(w.p50 > 0)          # unrounded cover days
    # rows the stated rule does not reproduce = the unreported rows
    rule = 15.36 * np.maximum(0, w.p50 - w.closing_before) + 3.84 * np.maximum(0, w.p80 - w.closing_before)
    w["exception"] = (rule - w.loss_before).abs() > 1
    t = pd.DataFrame(raw["transfers"])
    t["ws"] = pd.to_datetime(t.week_start).dt.date
    t["year"] = [d.year for d in t.ws]
    t["ym"] = [f"{d.year}-{d.month:02d}" for d in t.ws]
    t["id"] = [f"INV-T-{r.week_start}-{r.sku}-{r.from_depot}-{r.to_depot}-{i}" for i, r in enumerate(t.itertuples())]
    return dict(meta=raw["meta"], totals=raw["totals"], monthly_file=raw["monthly"], by_sku_file=raw["by_sku"],
                w=w, t=t, js_same=js_same, path=str(FEED / "dashboard_data.json"))


def weeks():
    return sorted(feed()["w"].ws.unique())


def in_window(dates, win):
    _, a, b = WINDOWS.get(win, WINDOWS["summer26"])
    return [(a <= d <= b) for d in dates]


# ------------------------------------------------------------------------------------------- loss
def row_loss(w, side, ctl, p50=None, p80=None):
    """Shortage-only rule: h01 per bottle below P50 + h02 per bottle below P80. Unreported rows keep the file's loss."""
    p50 = w.p50 if p50 is None else p50
    p80 = w.p80 if p80 is None else p80
    c = w[f"closing_{side}"]
    loss = ctl["h01"] * np.maximum(0, p50 - c) + ctl["h02"] * np.maximum(0, p80 - c)
    return loss.where(~w.exception, w[f"loss_{side}"])


@lru_cache(maxsize=64)
def frame(ctl):
    f = feed()
    w = f["w"].copy()
    p50, p80 = w.p50, w.p80
    if ctl["f28"] == "dashboard":                       # summer weeks only: the dashboard's one-week-ahead depot forecast
        p50, p80 = _dash_forecast(ctl, w)
        w["cov_before"] = w.closing_before / (p50 / 7).where(p50 > 0)
        w["cov_after"] = w.closing_after / (p50 / 7).where(p50 > 0)
    w["p50_used"], w["p80_used"] = p50, p80
    w["lb"] = row_loss(w, "before", ctl, p50, p80)
    w["la"] = row_loss(w, "after", ctl, p50, p80)
    t = f["t"].copy()
    t["cost"] = t.bottles * ctl["a08"]
    return w, t


DASH_WINDOWS = ("summer25", "summer26")


def _dash_forecast(ctl, w):
    """Dashboard depot P50/P80 for every week inside the summer windows; the file's values elsewhere."""
    from . import forecast as FC
    allw = weeks()
    p50, p80 = w.p50.astype(float).copy(), w.p80.astype(float).copy()
    idx = w.set_index(["ws", "depot", "sku"]).index
    pos = {k: i for i, k in enumerate(idx)}
    for wk in allw[1:]:
        if not any(in_window([wk], win)[0] for win in DASH_WINDOWS):
            continue
        df = FC.depot_forecast(allw[allw.index(wk) - 1], ctl, weeks=1)
        df = df[df.week == wk]
        for r in df.itertuples():
            i = pos.get((wk, r.depot_id, r.sku))
            if i is not None:
                p50.iat[i], p80.iat[i] = r.p50, r.p80
    return p50, p80


@lru_cache(maxsize=64)
def summary(win, ctl):
    w, t = frame(ctl)
    wm = w[in_window(w.ws, win)]
    tm = t[in_window(t.ws, win)]
    before, after, tc = float(wm.lb.sum()), float(wm.la.sum()), float(tm.cost.sum())
    by = wm.groupby("sku")[["lb", "la"]].sum().join(tm.groupby("sku").cost.sum()).reindex(SKUS).fillna(0)
    by["gross"] = by.lb - by.la
    by["net"] = by.gross - by.cost
    pp_dp = float(by.la[["PP", "DP"]].sum())
    sku_rows = []
    for s, r in by.iterrows():
        if s in ("PP", "DP"):
            label = "cannot fix: short across the whole network (supply)"
        elif r.net < 0:
            label = "moving stock does not pay"
        elif r.gross > 0:
            label = "fixed by moving stock"
        else:
            label = "no loss in this window"
        sku_rows.append(dict(sku=s, before=float(r.lb), after=float(r.la), transport=float(r.cost), gross=float(r.gross),
                             net=float(r.net), label=label, n=int((tm.sku == s).sum())))
    months = sorted(wm.ym.unique())
    mon = []
    for m in months:
        mon.append(dict(ym=m, before=float(wm[wm.ym == m].lb.sum()), after=float(wm[wm.ym == m].la.sum()),
                        transport=float(tm[tm.ym == m].cost.sum())))
    wk = wm.groupby("ws")[["lb", "la"]].sum()
    years = []
    for y in sorted(w.year.unique()):
        b_, a_, c_ = float(w[w.year == y].lb.sum()), float(w[w.year == y].la.sum()), float(t[t.year == y].cost.sum())
        years.append(dict(year=int(y), before=b_, after=a_, transport=c_, net=b_ - a_ - c_, n=int((t.year == y).sum())))
    return dict(win=win, label=WINDOWS[win][0], before=before, after=after, transport=tc, after_total=after + tc,
                saving=before - after - tc, n=len(tm), bottles=float(tm.bottles.sum()), skus=sku_rows,
                pp_dp=pp_dp, pp_dp_share=pp_dp / after if after else None, months=mon,
                weekly=dict(weeks=list(wk.index), before=wk.lb.tolist(), after=wk.la.tolist()), years=years,
                weeks_in=sorted(wm.ws.unique()))


# ------------------------------------------------------------------------------------------- reconciliation
@lru_cache(maxsize=1)
def reconcile():
    """Handoff headline vs the file's totals vs a recomputation from the rows at the file's own rates."""
    f = feed()
    w, t = f["w"], f["t"]
    T = f["totals"]
    rule = lambda side: 15.36 * np.maximum(0, w.p50 - w[f"closing_{side}"]) + 3.84 * np.maximum(0, w.p80 - w[f"closing_{side}"])
    rb = float(rule("before").where(~w.exception, w.loss_before).sum())
    ra = float(rule("after").where(~w.exception, w.loss_after).sum())
    rt = float((t.bottles * 1.5).sum())
    rows = [
        ("Loss before", HANDOFF["loss_before"], T["loss_before_rs"] / CR, rb / CR, "cr"),
        ("Loss after", HANDOFF["loss_after"], T["loss_after_rs"] / CR, ra / CR, "cr"),
        ("Transport", HANDOFF["transport"], T["transport_rs"] / CR, rt / CR, "cr"),
        ("After total", HANDOFF["after_total"], T["after_total_rs"] / CR, (ra + rt) / CR, "cr"),
        ("Saving", HANDOFF["saving"], T["saving_rs"] / CR, (rb - ra - rt) / CR, "cr"),
        ("Transfers", HANDOFF["transfers"], T["transfers"], len(t), "n"),
        ("Bottles moved", HANDOFF["bottles_lakh"], T["bottles_moved"] / 1e5, t.bottles.sum() / 1e5, "lakh"),
    ]
    out = []
    for name, h, fv, rv, unit in rows:
        tol = 0.005 if unit != "n" else 0
        ok = abs(round(fv, 2) - h) <= tol + 1e-9 and abs(fv - rv) <= (0.0001 if unit != "n" else 0)
        out.append(dict(name=name, handoff=h, file=fv, recomputed=rv, unit=unit, ok=bool(ok)))
    ex = w[w.exception]
    pure = float((15.36 * np.maximum(0, w.p50 - w.closing_before) + 3.84 * np.maximum(0, w.p80 - w.closing_before)).sum())
    return dict(rows=out, all_ok=all(r["ok"] for r in out),
                exceptions=[dict(week=r.ws, depot=r.depot, sku=r.sku, loss=float(r.loss_before), status=r.status_before,
                                 closing=r.closing_before, p50=r.p50) for r in ex.itertuples()],
                exc_loss=float(ex.loss_before.sum()), pure_rule_before=pure,
                year_net=[(y, YEAR_NET[y]) for y in sorted(YEAR_NET)], js_same=f["js_same"],
                matched_rows=int((~w.exception).sum()), n_rows=len(w))


# ------------------------------------------------------------------------------------------- views
@lru_cache(maxsize=64)
def heat(week, side, ctl):
    w, _ = frame(ctl)
    g = w[w.ws == week].set_index(["depot", "sku"])
    rows = []
    for d in DEPOTS:
        cells = []
        for s in SKUS:
            if (d, s) not in g.index:
                cells.append(None)
                continue
            r = g.loc[(d, s)]
            cov = r[f"cov_{side}"]
            c = float(r[f"closing_{side}"])
            st = ("stock-out" if c <= 0 else "below P50" if c < r.p50_used else "below P80" if c < r.p80_used else "ok")
            cells.append(dict(sku=s, cover=None if cov != cov else float(cov), closing=c,
                              status=st, loss=float(r["lb" if side == "before" else "la"]),
                              exception=bool(r.exception)))
        rows.append(dict(depot=d, region=g.loc[(d, "MPB")].region if (d, "MPB") in g.index else "", cells=cells))
    return rows


def week_transfers(week, ctl):
    _, t = frame(ctl)
    tw = t[t.ws == week]
    return [dict(id=r.id, sku=r.sku, frm=r.from_depot, to=r.to_depot, bottles=int(r.bottles), cost=float(r.cost),
                 cs=float(r.cover_days_sender), cr=float(r.cover_days_receiver), reasons=list(r.reasons), approver=r.approver,
                 below_target=r.cover_days_sender < ctl["g04"], title=f"Transfer {r.bottles:,} {r.sku} {r.from_depot}→{r.to_depot}",
                 owner="Supply chain manager") for r in tw.itertuples()]


@lru_cache(maxsize=64)
def overstock(win, ctl):
    """Depot-weeks above h03 days of cover; bottles above that cover; age risk vs the saleable window (g01 - g02)."""
    w, _ = frame(ctl)
    wm = w[in_window(w.ws, win)]
    thr = ctl["h03"]
    sale = ctl["g01"] - ctl["g02"]
    out = {}
    for s in ("before", "after"):
        c = wm[f"cov_{s}"]
        over = wm[c > thr]
        above = (over[f"closing_{s}"] - thr * over.p50 / 7).clip(lower=0)
        aged = wm[c > sale]
        beyond = (aged[f"closing_{s}"] - sale * aged.p50 / 7).clip(lower=0)
        by_week = beyond.groupby(aged.ws).sum()                  # network bottles beyond the window, each week
        out[s] = dict(n=len(over), bottles=float(above.sum()), status_n=int((wm[f"status_{s}"] == "over 35d").sum()),
                      age_n=len(aged), age_bottles=float(beyond.sum()),
                      age_peak=float(by_week.max()) if len(by_week) else 0.0,
                      age_peak_week=by_week.idxmax() if len(by_week) else None,
                      by_sku={k: int((over.sku == k).sum()) for k in SKUS},
                      by_depot={k: int((over.depot == k).sum()) for k in DEPOTS})
    b, a = wm.cov_before > thr, wm.cov_after > thr
    new = wm[a & ~b].groupby(["depot", "sku"]).size().sort_values(ascending=False)
    gone = wm[b & ~a].groupby(["depot", "sku"]).size().sort_values(ascending=False)
    rate = ctl["h05"]
    # priced once, at the peak week (summing weeks would count the same bottle every week it sits): an upper bound
    wo = dict(before=out["before"]["age_peak"] * rate, after=out["after"]["age_peak"] * rate) if rate > 0 else None
    top = wm[wm.cov_before > thr].assign(excess=lambda x: x.closing_before - thr * x.p50 / 7).sort_values("excess", ascending=False).head(8)
    return dict(thr=thr, sale=sale, before=out["before"], after=out["after"], new=[(d, s, int(n)) for (d, s), n in new.items()],
                gone=[(d, s, int(n)) for (d, s), n in gone.items()], writeoff=wo, rate=rate,
                top=[dict(week=r.ws, depot=r.depot, sku=r.sku, cover=float(r.cov_before), excess=float(r.excess)) for r in top.itertuples()])


@lru_cache(maxsize=1)
def conservation():
    """Network stock before vs after must differ only by sales; anything else is stock created or lost by the replay."""
    w = feed()["w"]
    g = w.groupby(["ws", "sku"])[["closing_before", "closing_after", "sold_before", "sold_after"]].sum()
    g["net"] = (g.closing_after - g.closing_before) + (g.sold_after - g.sold_before)
    nz = g[g.net.abs() > 1].reset_index()
    dp = nz[nz.sku == "DP"]
    return dict(total=float(nz.net.sum()), rows=[dict(week=r.ws, sku=r.sku, net=float(r.net)) for r in nz.itertuples()],
                dp_weeks=len(dp), dp_from=dp.ws.min() if len(dp) else None, dp_to=dp.ws.max() if len(dp) else None,
                dp_mode=float(dp.net.mode().iloc[0]) if len(dp) else None)


# ------------------------------------------------------------------------------------------- replication
@lru_cache(maxsize=4)
def replicate(R=16.0, T=16.2, F=16.25, lot=10000):
    """A transparent greedy rule, run week by week on the file's own stock states (previous week's after-closing +
    this week's receipts; demand = max(last week's sales, this week's P50)). Receivers below R days are topped up to T;
    the sender with the most stock above F gives, in lots rounded to 1,000, at least `lot`. Returns match rates."""
    w = feed()["w"]
    t = feed()["t"]
    wk = sorted(w.ws.unique())
    W = {d: g.set_index(["depot", "sku"]) for d, g in w.groupby("ws")}
    truth = {(r.ws, r.sku, r.from_depot, r.to_depot): r.bottles for r in t.itertuples()}
    res = []
    for i in range(1, len(wk)):
        cur, prv = W[wk[i]], W[wk[i - 1]]
        for s in SKUS:
            st = {}
            for d in DEPOTS:
                if (d, s) in cur.index and (d, s) in prv.index:
                    stock = prv.at[(d, s), "closing_after"] + cur.at[(d, s), "receipts"]
                    rate = max(prv.at[(d, s), "sold_before"], cur.at[(d, s), "p50"]) / 7
                    if rate > 0:
                        st[d] = [stock, rate]
            cov = lambda d: st[d][0] / st[d][1]
            for r in sorted([d for d in st if cov(d) < R], key=cov):
                for _ in range(9):
                    need = (T - cov(r)) * st[r][1]
                    snd = [d for d in st if d != r and (cov(d) - F) * st[d][1] >= lot]
                    if not snd or need < lot / 2:
                        break
                    sd = max(snd, key=lambda d: (cov(d) - F) * st[d][1])
                    q = round(min(need, (cov(sd) - F) * st[sd][1]) / 1000) * 1000
                    if q < lot:
                        break
                    res.append((wk[i], s, sd, r, q))
                    st[sd][0] -= q
                    st[r][0] += q
    ws_t = {k[:2] for k in truth}
    rc_t = {(k[0], k[1], k[3]) for k in truth}
    sd_t = {(k[0], k[1], k[2]) for k in truth}
    pair = [k for k in res if k[:4] in truth]
    close = [k for k in pair if abs(truth[k[:4]] - k[4]) <= 0.05 * truth[k[:4]]]
    rate = len(close) / len(truth)
    return dict(proposed=len(res), truth=len(truth),
                week_sku=(len({k[:2] for k in res} & ws_t), len(ws_t)),
                receivers=(len({(k[0], k[1], k[3]) for k in res} & rc_t), len(rc_t)),
                senders=(len({(k[0], k[1], k[2]) for k in res} & sd_t), len(sd_t)),
                pairs=(len(pair), len(truth)), exact=(len(close), len(truth)), rate=rate,
                tolerance=0.90, replicated=rate >= 0.90, params=dict(R=R, T=T, F=F, lot=lot),
                proposals=res)


# ------------------------------------------------------------------------------------------- forecast source
@lru_cache(maxsize=8)
def forecast_compare(win, ctl):
    """File P50 (static) vs the dashboard's one-week-ahead national P50 (prompt 1, as known the Monday before)."""
    from . import forecast as FC
    w, _ = frame(ctl)
    wm = w[in_window(w.ws, win)]
    filep = wm.groupby(["ws", "sku"]).p50.sum()
    rows = []
    allw = weeks()
    for wk in sorted(wm.ws.unique()):
        i = allw.index(wk)
        if i == 0:
            continue
        nat = FC.national(allw[i - 1], ctl)
        d = nat[nat.week == wk].groupby("sku").p50.sum()
        for s in SKUS:
            fp = float(filep.get((wk, s), 0))
            dp_ = float(d.get(s, 0))
            if fp <= 0 and dp_ <= 0:
                continue
            rows.append(dict(week=wk, sku=s, file=fp, dash=dp_, diff=(dp_ / fp - 1) if fp > 0 else None))
    df = pd.DataFrame(rows)
    big = df[df["diff"].abs() > ctl["f29"]] if len(df) else df
    by = (df.groupby("sku")[["file", "dash"]].sum() if len(df) else pd.DataFrame())
    return dict(rows=rows, big=big.to_dict("records"), by_sku=[dict(sku=s, file=float(r.file), dash=float(r.dash),
                diff=float(r.dash / r.file - 1) if r.file else None) for s, r in by.iterrows()], n_weeks=int(df.week.nunique()) if len(df) else 0)


# ------------------------------------------------------------------------------------------- supply <-> inventory
@lru_cache(maxsize=16)
def link(win, ctl):
    """Supply -> Inventory (pulp shortfall -> production -> depot cover, with the finished-goods lag g08) and
    Inventory -> Supply (depot cover and stock-outs as signals to the detector and to pulp priorities)."""
    from ..data import store
    from . import supply as SUP
    s = store()
    w, t = frame(ctl)
    W0 = date(2026, 5, 4)                                   # closure replay: known by Monday 11 May
    sim = SUP.balance(W0, ctl)["planned"]
    K = sim["K"]
    lag = int(ctl["g08"])
    # observed timeline (data), Apr - Jun 2026
    tl_weeks = [x for x in weeks() if date(2026, 4, 6) <= x <= date(2026, 6, 29)]
    pf = s.pulp[s.pulp.ingredient == "passionfruit"].groupby("week_start").days_of_cover.min()
    prod = s.prod.groupby(["week_start", "sku_id"]).units_produced.sum()
    nat = w.groupby(["ws", "sku"])[["closing_before", "p50"]].sum()
    tl = []
    for x in tl_weeks:
        r = dict(week=x, pulp_cover=float(pf.get(x, np.nan)))
        for k in ("PP", "DP"):
            c, p = (float(nat.loc[(x, k)].closing_before), float(nat.loc[(x, k)].p50)) if (x, k) in nat.index else (0.0, 0.0)
            r[k] = dict(prod=float(prod.get((x, k), 0)), stock=c, cover=c / (p / 7) if p else None)
        tl.append(r)
    req = s.prod.groupby(["week_start", "sku_id"]).units_requested.sum()
    for r in tl:
        for k in ("PP", "DP"):
            q = float(req.get((r["week"], k), 0))
            r[k]["fill"] = r[k]["prod"] / q if q else None
    pulp_out = next((r["week"] for r in tl if r["pulp_cover"] == r["pulp_cover"] and r["pulp_cover"] < ctl["g05"]), None)
    pp_cut = next((r["week"] for r in tl if r["PP"]["fill"] is not None and r["PP"]["fill"] < 0.5), None)
    pp_zero = next((r["week"] for r in tl if r["PP"]["stock"] <= 0), None)
    # scenario projection: national stock = stock at W0 + production arriving after the lag - P50 demand
    proj = {}
    for k in ("PP", "DP"):
        fg0 = float(nat.loc[(W0, k)].closing_before) if (W0, k) in nat.index else 0.0
        made = np.concatenate([np.zeros(lag), sim["made"][k]])[: len(sim["days"])]
        dem = np.array([float(nat.loc[(d - timedelta(d.weekday()), k)].p50) / 7 if (d - timedelta(d.weekday()), k) in nat.index
                        else 0.0 for d in sim["days"]])
        lvl = fg0 + np.cumsum(made - dem)
        j = next((i for i, v in enumerate(lvl) if v < 0), None)
        short_plant = float((sim["plan"][k] - sim["made"][k]).sum())
        proj[k] = dict(fg0=fg0, runs_out=sim["days"][j] if j is not None else None, plant_short=short_plant,
                       level=lvl.tolist(), first_short_prod=next((sim["days"][i] for i in range(len(sim["days"]))
                                                                  if sim["plan"][k][i] - sim["made"][k][i] > 1), None))
    # inventory -> supply signals for the window
    wm = w[in_window(w.ws, win)]
    sig = []
    for x in sorted(wm.ws.unique()):
        g = wm[wm.ws == x]
        row = dict(week=x)
        cov = {}
        for k in ("PP", "DB", "DP"):
            gg = g[g.sku == k]
            p = gg.p50.sum()
            cov[k] = float(gg.closing_before.sum() / (p / 7)) if p > 0 else None
            row[k] = dict(cover=cov[k], zero=int((gg.closing_before <= 0).sum()))
        live = {k: v for k, v in cov.items() if v is not None}
        row["priority"] = sorted(live, key=lambda k: live[k])
        sig.append(row)
    dp_zero = [r["week"] for r in sig if r["DP"]["cover"] is not None and r["DP"]["cover"] < 1]
    censored = int((wm.closing_before <= 0).sum())
    # quantify: loss before / after / residual (supply) + supply-module scenarios
    sm = summary(win, ctl)
    mit = SUP.mitigations(W0, ctl)
    opts = {o["key"]: o for o in mit["options"]}
    pre = SUP.simulate(W0, ctl, extra={"passionfruit": _prepos(sim, ctl)})
    pre_unmet = sum(pre["unmet"][k] for k in ("PP", "DB", "DP"))
    rate = ctl["h01"] + ctl["h02"]
    scen = [dict(name="No action (closure replay, 56 days)", unmet=mit["unmet0"]),
            dict(name="Joint pulp allocation (allocation rule, g07 floor)", unmet=opts.get("joint", {}).get("unmet")),
            dict(name=f"Pre-positioned passionfruit cover ({ctl['b02'] + ctl['g05']:.0f} days at closure start)", unmet=pre_unmet),
            dict(name="Air freight + joint allocation", unmet=opts.get("air_joint", {}).get("unmet"))]
    for x in scen:
        x["delta"] = (mit["unmet0"] - x["unmet"]) if x["unmet"] is not None else None
        x["exposure"] = x["unmet"] * rate if x["unmet"] is not None else None
    gate = gating(ctl, sim, opts.get("joint"))
    return dict(W0=W0, K=K, lag=lag, tl=tl, pulp_out=pulp_out, pp_cut=pp_cut, pp_zero=pp_zero, proj=proj, days=sim["days"],
                closures=sim["closures"], sig=sig, dp_zero=dp_zero, censored=censored, sm=sm, scen=scen, rate=rate, gate=gate)


def _prepos(sim, ctl):
    """Extra passionfruit on day 0 that lifts plant cover to b02 + g05 days (the pre-positioning option)."""
    r = sim["ing"]["passionfruit"]
    need = max(0.0, (ctl["b02"] + ctl["g05"]) * r["avg_use"] - r["open"])
    a = np.zeros(len(sim["days"]))
    a[0] = need
    return a


def gating(ctl, base, opt):
    """Demand-gated reallocation: extra production of a flavor must be backed by depot-level demand it can meet
    inside the saleable window (g01 - g02 days after it reaches the depot, lag g08), net of stock already there."""
    from . import forecast as FC
    if not opt or "sim" not in opt:
        return None
    sim = opt["sim"]
    lag = int(ctl["g08"])
    sale = int(ctl["g01"] - ctl["g02"])
    shelf = max(0, sale - lag)                              # saleable days left once the bottle reaches the depot
    W0 = base["K"] - timedelta(7)
    dfc = FC.depot_forecast(W0, ctl, weeks=12)
    w, _ = frame(ctl)
    stock = w[w.ws == W0].set_index(["depot", "sku"]).closing_before
    rows = []
    for k in SKUS:
        extra = float(sim["made"][k].sum() - base["made"][k].sum())
        if extra <= 1:
            continue
        g = dfc[dfc.sku == k]
        backed = 0.0
        for d in DEPOTS:
            gd = g[g.depot_id == d]
            dem = float(gd.p50.sum()) / (7 * len(gd.week.unique()) or 1) * shelf if len(gd) else 0.0
            have = float(stock.get((d, k), 0) or 0)
            share = float(gd.share.iloc[0]) if len(gd) else 0.0
            backed += min(extra * share, max(0.0, dem - have))
        rows.append(dict(sku=k, extra=extra, backed=backed, share=backed / extra if extra else None,
                         ok=backed >= 0.99 * extra, sale=sale, lag=lag, shelf=shelf))
    return rows


# ------------------------------------------------------------------------------------------- READ_ME feed
@lru_cache(maxsize=16)
def readme_items(ctl):
    rc = reconcile()
    con = conservation()
    w, t = frame(ctl)
    sm_all = summary("all", ctl)
    ovs = overstock("all", ctl)
    below = int((t.cover_days_sender < ctl["g04"]).sum())
    out = []

    def it(bucket, sev, title, detail, link, group="Inventory (prompt 2)"):
        out.append(dict(bucket=bucket, severity=sev, title=title, detail=detail, link=link, group=group,
                        source="Inventory feed", owner="Planning"))

    ex = rc["exceptions"]
    it("Soon", "High", f"{len(ex)} unreported rows carry ₹{rc['exc_loss'] / CR:.3f} Cr of loss while showing 'ok'",
       f"East depot 1, week of {ex[0]['week']:%d %b %Y}: the file keeps a loss these rows' own stock does not produce; "
       f"₹{rc['exc_loss'] / CR:.3f} Cr equals all of 2025's loss before rebalancing. Shown, not corrected.", "/rebalance#check")
    it("Soon", "High", f"Stock not conserved in the replay: {con['total'] / 1e5:.2f} lakh bottles",
       f"Network stock after rebalancing exceeds before + sales difference. Dragon Passion carries +{con['dp_mode']:,.0f} bottles "
       f"each week from {con['dp_from']:%d %b} to {con['dp_to']:%d %b %Y} ({con['dp_weeks']} weeks); PP is off in 3 weeks around the closure.",
       "/rebalance#check")
    it("Soon", "Medium", f"{below} of {len(t)} transfers take stock from senders below the {ctl['g04']:.0f}-day target",
       "Rebalancing can push the sender short; each such transfer is flagged in the transfers table.", "/rebalance#transfers")
    neg = [y for y in sm_all["years"] if y["net"] < 0]
    it("Later", "Medium", "2024–25 transfers lost money: " + ", ".join(f"{y['year']} {y['net'] / CR:+.2f} Cr" for y in neg),
       "Transport cost more than the shortage it removed outside the 2026 summer. The default window is Mar–Jun 2026.", "/rebalance#years")
    it("Later", "Medium", "Loss rule is shortage-only and not the case's lost contribution",
       f"₹{ctl['h01']:.2f} below P50 + ₹{ctl['h02']:.2f} below P80 on closing stock is not comparable to the case's ₹14.7 Cr "
       "contribution lost (C11: 8% of revenue × 32%). The file's flat-rule ₹25.97 Cr is a third definition and is labelled wherever shown.",
       "/rebalance")
    it("Later", "Low", "Demand in stock-out weeks is a lower bound",
       "Sales cannot exceed stock, so shortage (and loss) is understated in those weeks.", "/link")
    lk = link("summer26", ctl)
    it("Soon", "Medium", f"PP depot stock reaches zero in the week of {lk['pp_zero']:%d %b}, the week pulp was expected to run out",
       f"In the data the plants never run dry: PP production is cut below half of what depots requested from the week of "
       f"{lk['pp_cut']:%d %b} (case F58), two weeks earlier, and depot stock follows. Confirm with the teammate whether PP was cut "
       "before or at the closure.", "/link")
    it("Later", "Low", "Two inventory sources: CSV snapshot (v2) and the teammate's feed",
       "Inventory module pages read the feed; Supply, the risk engine and the descriptive Inventory page read the v2 CSVs. "
       "They agree to ±1 bottle of rounding. See Data & assumptions.", "/data#sources")
    it("Later", "Medium", "Optimiser logic is offline and undocumented",
       f"A transparent greedy rule reproduces {replicate()['exact'][0]} of {replicate()['exact'][1]} transfers (receivers "
       f"{replicate()['receivers'][0]}/{replicate()['receivers'][1]}); transfers stay precomputed and their controls are locked.",
       "/rebalance#replication")
    it("Later", "Medium", f"Rebalancing raises over-{ovs['thr']:.0f}-day depot-weeks from {ovs['before']['n']} to {ovs['after']['n']}",
       "Mostly Guava Chilli, MPB and PP at the receiving depots; see Overstock & aging.", "/overstock")
    for q in QUESTIONS:
        out.append(dict(bucket="Later", severity="Low", title="Ask the teammate: " + q, detail="Open question; not blocking.",
                        link="/rebalance#questions", group="Open questions (teammate)", source="Prompt 2", owner="Planning"))
    return out


QUESTIONS = ["What are the optimiser's rules (sender/receiver thresholds, ordering, minimum lot)?",
             "Why is Dragon Passion stock not conserved, and how did the 4 unreported rows arise?",
             "How were P50/P80 produced, and are they censored by stock-outs?",
             "Why were 2024–25 transfers generated when they do not pay?",
             "Was Passionfruit Punch production cut before the closure?"]


