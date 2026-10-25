"""
forecast.py - forecasting at signal-layer depth (PulpSense Forecasting Model Build Specification).

Layer 1  baseline:  last year's same-week demand (the seasonal shape) x a level, blended between the
                    planned growth (f23) and the realised year-on-year level of the last f06 weeks (f05).
                    Dragon Passion has no last year: its recent run-rate x the Passionfruit Punch + Dragonfruit
                    Bloom seasonal shape; before data exists, the launch allocation (f21), known only once
                    Marketing has told Procurement (f22, case F36).
                    Censored weeks (stock-outs) never count as low demand (f07).
                    Ranges: P_q = P50 x (1 + z_q x error / 0.7979)  (normal errors; 0.7979 = mean |z|).
Layer 2  sensing:   daily quick-commerce sell-through vs its own lagged baseline, EWMA + one-sided CUSUM,
                    N consecutive days, minimum volume, stock-out mask. Alerts are classified with evidence
                    and projected under three persistence scenarios.
Depot split:        national x depot share; shares recency-weighted and shrunk toward the region (k = f20);
                    Dragon Passion starts from the average of its parents' (PP, DB) shares.

Accuracy is never claimed from this sample. The replay reports detection dates and lead times only.
"""
from datetime import date, timedelta
from functools import lru_cache
from statistics import NormalDist

import numpy as np
import pandas as pd

from ..data import REGIONS, store

SKUS = ["MPB", "GC", "PP", "DB", "DP"]
CHANNELS = ["C_GT", "C_MT", "C_QC"]
CH_NAMES = {"C_GT": "General trade", "C_MT": "Modern trade", "C_QC": "Quick commerce"}
MAD = 0.7979                                      # mean |z| of a standard normal: MAPE -> sigma
FCAST_WEEKS = 16                                  # long enough for the import lever (12 weeks, spec 3.3)


def z(p):
    return NormalDist().inv_cdf(p / 100.0) if 0 < p < 100 else 0.0


def launch_date(sku):
    s = store()
    v = s.sku.set_index("sku_id").launch_date.get(sku, "")
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return None


# ------------------------------------------------------------------------------------- estimated demand
@lru_cache(maxsize=4)
def estimated(method):
    """week x sku x channel: sold, ordered, censored flag and estimated demand (method stated)."""
    s = store()
    d = (s.dem.groupby(["week_start", "sku_id", "channel_id"])[["units_sold", "units_ordered", "units_lost"]]
         .sum().reset_index().sort_values("week_start"))
    d["censored"] = d.units_lost > 0.01 * d.units_ordered
    if method == "orders":
        d["est"] = d.units_ordered.astype(float)
    elif method == "exclude":
        d["est"] = d.units_sold.where(~d.censored).astype(float)
    else:                                             # impute: pre-stock-out run-rate (last 4 clean weeks)
        clean = d.units_sold.where(~d.censored).astype(float)
        d["est"] = (clean.groupby([d.sku_id, d.channel_id])
                    .transform(lambda x: x.rolling(4, min_periods=1).mean().shift(1).ffill()))
        d.loc[~d.censored, "est"] = d.loc[~d.censored, "units_sold"]
    return d.set_index(["week_start", "sku_id", "channel_id"])


def _get(e, wk, s, c):
    try:
        v = e.at[(wk, s, c), "est"]
        return None if v != v else float(v)
    except KeyError:
        return None


# ------------------------------------------------------------------------------------- layer 1
@lru_cache(maxsize=64)
def national(w, ctl):
    """Forecast for the FCAST_WEEKS weeks starting K = w + 7. One row per week x flavor x channel."""
    st = store()
    e = estimated(ctl["f07"])
    K = w + timedelta(7)
    n = int(ctl["f06"])
    known = [x for x in st.weeks if x <= w][-n:]
    g, wt = ctl["f23"], ctl["f05"]
    weeks = [K + timedelta(7 * i) for i in range(FCAST_WEEKS)]
    rows, notes = [], []
    lvl = {}
    for s in SKUS:
        for c in CHANNELS:
            num = sum(v for v in (_get(e, x, s, c) for x in known) if v is not None)
            den = [_get(e, x - timedelta(364), s, c) for x in known]
            den_ok = [v for v in den if v is not None]
            ratio = num / sum(den_ok) if den_ok and sum(den_ok) > 0 and len(den_ok) == len(known) else None
            rr = num / max(len(known), 1)
            lvl[(s, c)] = (ratio, rr)

    dp_launch = launch_date("DP")
    for wk in weeks:
        base = {}
        for s in SKUS:
            for c in CHANNELS:
                ratio, rr = lvl[(s, c)]
                ly = _get(e, wk - timedelta(364), s, c)
                if s == "DP" and dp_launch:
                    continue
                if ly is None or ly <= 0:
                    p50, how = rr, "run-rate (no last-year history)"
                else:
                    plan = ly * (1 + g)
                    p50 = (1 - wt) * plan + wt * (ly * ratio if ratio is not None else plan)
                    how = "last year's week x blended level"
                base[(s, c)] = (p50, how)
        if dp_launch:
            for c in CHANNELS:
                dp_known = [x for x in known if x >= dp_launch]
                vals = [_get(e, x, "DP", c) for x in dp_known]
                vals = [v for v in vals if v is not None]
                if wk < dp_launch:
                    p50, how = 0.0, "not launched"
                elif len(vals) >= 2:
                    def ppdb(x):
                        a = [_get(e, x - timedelta(364), p, c) for p in ("PP", "DB")]
                        return sum(v for v in a if v) if all(v is not None for v in a) else None
                    shp_now = [ppdb(x) for x in dp_known[-len(vals):]]
                    shp_now = [v for v in shp_now if v]
                    shp_t = ppdb(wk)
                    shape = (shp_t / (sum(shp_now) / len(shp_now))) if shp_now and shp_t else 1.0
                    p50, how = (sum(vals[-n:]) / len(vals[-n:])) * shape, "new flavor: run-rate x PP+DB seasonal shape"
                elif K >= dp_launch - timedelta(int(ctl["f22"])):
                    others = sum(v[0] for (s2, c2), v in base.items() if c2 == c)
                    p50, how = ctl["f21"] * others / max(1 - ctl["f21"], 1e-9), "launch allocation (Assumed f21)"
                else:
                    p50, how = 0.0, "launch not yet notified"
                base[("DP", c)] = (p50, how)
        for (s, c), (p50, how) in base.items():
            if ctl["b11"] == s and c == "C_QC" and wk >= K + timedelta(int(ctl["b13"])):
                p50, how = p50 * ctl["b12"], how + " + scenario shock (b11-b13)"
            rows.append(dict(week=wk, sku=s, channel=c, p50=max(p50, 0.0), method=how))
    df = pd.DataFrame(rows)
    err = ctl["f02"]
    for p in (10, 50, 80, 90):
        df[f"p{p}"] = df.p50 * np.maximum(0, 1 + z(p) * err / MAD)
    df["p_raw"] = df.p50 * np.maximum(0, 1 + z(ctl["f03"]) * err / MAD)       # pulp percentile
    df["p_fg"] = df.p50 * np.maximum(0, 1 + z(ctl["f04"]) * err / MAD)        # finished-goods percentile
    return df


def weekly_by_sku(w, ctl, col="p50"):
    f = national(w, ctl)
    return f.groupby(["week", "sku"])[col].sum().unstack("sku").reindex(columns=SKUS).fillna(0)


def daily_by_sku(w, ctl, days, col="p_raw"):
    """National daily demand per flavor for `days` days from K: weekly forecast / 7."""
    wk = weekly_by_sku(w, ctl, col)
    K = w + timedelta(7)
    out = {s: np.zeros(days) for s in SKUS}
    for i in range(days):
        d = K + timedelta(i)
        ws = d - timedelta(d.weekday())
        if ws in wk.index:
            for s in SKUS:
                out[s][i] = wk.at[ws, s] / 7.0
        else:
            for s in SKUS:
                out[s][i] = out[s][i - 1] if i else 0.0
    return out


def recipe(ctl):
    """kg of each ingredient per bottle of each flavor (Assumed recipe, controls d01-d04)."""
    k = ctl["d01"]
    mg, pc = ctl["d02"], ctl["d03"]
    if mg + pc > 1:                                   # shares above 100%: scale mango and peach down, no basil
        mg, pc = mg / (mg + pc), pc / (mg + pc)
    mpb_b = max(0.0, 1 - mg - pc)
    return {
        "MPB": {"mango": k * mg, "peach": k * pc, "basil": k * mpb_b},
        "GC": {"guava": k},
        "PP": {"passionfruit": k},
        "DB": {"dragonfruit": k},
        "DP": {"passionfruit": k * ctl["d04"], "dragonfruit": k * (1 - ctl["d04"])},
    }


@lru_cache(maxsize=32)
def pulp_requirement(w, ctl):
    """kg per ingredient per week at P50 and at the pulp percentile."""
    f = national(w, ctl)
    R = recipe(ctl)
    rows = []
    for wk, g in f.groupby("week"):
        by = g.groupby("sku")[["p50", "p_raw"]].sum()
        for ing in ["passionfruit", "dragonfruit", "mango", "peach", "basil", "guava"]:
            a = sum(by.at[s, "p50"] * R[s].get(ing, 0) for s in by.index)
            b = sum(by.at[s, "p_raw"] * R[s].get(ing, 0) for s in by.index)
            rows.append(dict(week=wk, ingredient=ing, kg_p50=a, kg_plan=b))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------- layer 2: detector
@lru_cache(maxsize=1)
def _qc_frames():
    s = store()
    q = s.qc
    nat = q.groupby(["date", "sku_id"]).units_sold.sum().unstack("sku_id").sort_index()
    oos = q.groupby(["date", "sku_id"]).out_of_stock.sum().unstack("sku_id").reindex(nat.index).fillna(0)
    ndep = q.groupby("sku_id").depot_id.nunique()
    dep = q.pivot_table(index="date", columns=["sku_id", "depot_id"], values="units_sold", aggfunc="sum").sort_index()
    dep_oos = q.pivot_table(index="date", columns=["sku_id", "depot_id"], values="out_of_stock", aggfunc="max").sort_index()
    dep = dep.where(dep_oos.reindex_like(dep).fillna(0) == 0)          # stock-out days are unobservable, not zero
    return nat, oos, ndep, dep


def _ly_series(nat, sku, idx):
    """Same-day-last-year national QC sales for this flavor; Dragon Passion borrows PP + DB."""
    src = [sku] if sku != "DP" else ["PP", "DB"]
    if any(s not in nat for s in src):
        return None
    ly = nat[src].sum(axis=1)
    out = pd.Series([ly.get(d - timedelta(364), np.nan) for d in idx], index=idx)
    return None if out.isna().all() else out


def _detect_series(x, oos_share, ctl, start_ok=None, down=False, ly=None):
    """Run the detector over one daily series. Returns per-day state and the list of alert episodes.
    ly: same-day-last-year series. If given, each day's ratio is divided by last year's ratio over the
    SAME window, so the normal seasonal rise is not read as a spike (control f26)."""
    lam, thr, k, h, N = ctl["f08"], ctl["f09"], ctl["f10"], ctl["f11"], int(ctl["f12"])
    L, minv = int(ctl["f14"]), ctl["f13"]
    vals = x.values.astype(float)
    lyv = ly.values.astype(float) if ly is not None else None
    days = list(x.index)
    zt, S, Sd, run, runoff = 1.0, 0.0, 0.0, 0, 0
    out, eps, cur = [], [], None
    for i, d in enumerate(days):
        lo, hi = max(0, i - 7 - L + 1), max(0, i - 7 + 1)
        idx = [j for j in range(lo, hi) if start_ok is None or days[j] >= start_ok]
        win = vals[idx] if idx else np.array([])
        ok = ~np.isnan(win)
        base = float(win[ok].mean()) if ok.sum() >= 7 else None
        sf = 1.0
        if lyv is not None and base and lyv[i] == lyv[i]:
            lw = lyv[idx][ok] if idx else np.array([])
            lw = lw[~np.isnan(lw)]
            if len(lw) >= 7 and lw.mean() > 0:
                sf = min(max(lyv[i] / lw.mean(), 0.5), 2.0)
        censored = oos_share.iloc[i] >= 1 / 3
        st = dict(date=d, x=vals[i], base=base, ratio=None, ewma=None, cusum=None, censored=bool(censored),
                  thin=base is not None and base < minv, alert=False, sf=sf)
        if base and base >= minv and not censored:
            r = vals[i] / base / sf
            zt = lam * r + (1 - lam) * zt
            S = max(0.0, S + r - 1 - k)
            Sd = max(0.0, Sd + (1 - r) - k)
            st.update(ratio=r, ewma=zt, cusum=S)
            hit = (zt < 2 - thr or Sd > h) if down else (zt > thr or S > h)
            run = run + 1 if hit else 0
            runoff = 0 if hit else runoff + 1
            if run >= N and cur is None:
                cur = dict(start=d, first_hit=days[i - N + 1], peak_ratio=r, end=None)
                eps.append(cur)
            if cur is not None:
                cur["peak_ratio"] = max(cur["peak_ratio"], r)
                if runoff >= 7:
                    cur["end"] = d
                    cur = None
                    S, Sd = 0.0, 0.0
            st["alert"] = cur is not None
        out.append(st)
    return out, eps


@lru_cache(maxsize=64)
def detect(w, ctl, sku, upto=None):
    """Detector for one flavor on national quick-commerce sales, using only days up to W + 6."""
    nat, oos, ndep, dep = _qc_frames()
    last = upto or (w + timedelta(6))
    if sku not in nat:
        return [], []
    x = nat[sku][nat.index <= last]
    o = (oos[sku] / ndep.get(sku, 9))[oos.index <= last]
    return _detect_series(x, o, ctl, start_ok=launch_date(sku), ly=_ly(ctl, sku, x))


def _ly(ctl, sku, x):
    if ctl["f26"] != "yes":
        return None
    nat, *_ = _qc_frames()
    return _ly_series(nat, sku, x.index)


def _fixed_rule(x, jump=1.5):
    """Benchmark: alert when 7-day sales are `jump` x the previous 7 days (first day of each run)."""
    r = x.rolling(7).mean() / x.rolling(7).mean().shift(7)
    hit = (r > jump).astype(int)
    return [d for d, a, b in zip(x.index, hit, hit.shift(1, fill_value=0)) if a == 1 and b == 0]


@lru_cache(maxsize=8)
def method_test(ctl, runs=40, seed=7):
    """Injected-scenario test (spec section 8). Clearly synthetic: seeded series built from the sample's
    smoothed Guava Chilli seasonal curve with 10% daily noise; half the runs get an injected spike
    (2-4x, 7-day ramp, decaying). Reports detection delay, misses and false alerts per method.
    Evidence for choosing a detector on synthetic data. It is not an accuracy figure."""
    nat, *_ = _qc_frames()
    sm = nat["GC"].rolling(28, center=True, min_periods=7).mean()
    idx = [d for d in sm.index if date(2025, 1, 15) <= d <= date(2025, 7, 31)]
    rng = np.random.default_rng(seed)
    zero = pd.Series(0.0, index=idx)
    res = {m: dict(delays=[], missed=0, false=0, spikes=0) for m in ("adjusted", "raw", "fixed")}
    for r in range(runs):
        cur = sm.reindex(idx).values * np.exp(rng.normal(0, 0.10, len(idx)))
        ly = pd.Series(sm.reindex([d - timedelta(364) for d in idx]).values * np.exp(rng.normal(0, 0.10, len(idx))), index=idx)
        spike_at = None
        if r % 2 == 0:
            spike_at = int(rng.integers(45, 120))
            m = float(rng.choice([2.0, 3.0, 4.0]))
            t = np.arange(len(idx)) - spike_at
            ramp = np.clip(t / 7, 0, 1) * 0.5 ** (np.clip(t - 7, 0, None) / 30)
            cur = cur * (1 + (m - 1) * ramp)
        x = pd.Series(cur, index=idx)
        found = {"adjusted": [e["start"] for e in _detect_series(x, zero, ctl, ly=ly)[1]],
                 "raw": [e["start"] for e in _detect_series(x, zero, ctl)[1]],
                 "fixed": _fixed_rule(x)}
        for k, starts in found.items():
            starts = [d for d in starts if d >= idx[42]]            # after the detector has a baseline
            if spike_at is None:
                res[k]["false"] += len(starts)
                continue
            res[k]["spikes"] += 1
            s0 = idx[spike_at]
            hits = [d for d in starts if s0 <= d <= s0 + timedelta(21)]
            res[k]["false"] += len([d for d in starts if d < s0])
            if hits:
                res[k]["delays"].append((hits[0] - s0).days)
            else:
                res[k]["missed"] += 1
    out = []
    names = {"adjusted": "EWMA + CUSUM on the seasonally adjusted ratio", "raw": "EWMA + CUSUM on the raw ratio",
             "fixed": "Fixed rule: 7-day sales +50% on the week before"}
    for k, v in res.items():
        out.append(dict(key=k, method=names[k], spikes=v["spikes"], caught=v["spikes"] - v["missed"],
                        median_delay=float(np.median(v["delays"])) if v["delays"] else None,
                        false=v["false"], runs=runs))
    return out


def breadth(w, ctl, sku, day):
    """Share of depots whose own 7-day sales are above the threshold vs their lagged baseline."""
    nat, oos, ndep, dep = _qc_frames()
    if sku not in dep.columns.get_level_values(0):
        return None, []
    d = dep[sku]
    d = d[d.index <= day]
    L = int(ctl["f14"])
    now = d.iloc[-7:].mean()                       # stock-out days are already NaN (censored)
    base = d.iloc[-7 - L:-7].mean()
    r = (now / base).dropna()
    above = r[r > ctl["f09"]]
    return (len(above) / len(r) if len(r) else None), sorted(above.index.tolist())


def classify(w, ctl, sku, ep, day=None):
    """Rules from spec 4.2, each with its evidence, judged on the latest day seen. Returns (class, evidence)."""
    ev = []
    ld = launch_date(sku)
    day = day or ep["start"]
    since = (day - ld).days if ld else None
    b, deps = breadth(w, ctl, sku, day)
    nat, *_ = _qc_frames()
    x = nat[sku][nat.index <= day]
    w1, w0 = x.iloc[-7:].mean(), x.iloc[-14:-7].mean()
    cur = [x for x in detect(w, ctl, sku, upto=day)[0] if x["ratio"] is not None]
    lvl = cur[-1]["ewma"] if cur else None
    sudden = (w0 > 0 and w1 / w0 >= 1.5) or (lvl is not None and lvl >= 2)
    ev.append(f"Week-on-week change {w1 / w0:.1f}x; smoothed level {lvl:.1f}x its baseline" if w0 > 0 and lvl
              else "No prior week to compare")
    _, oos, _, _ = _qc_frames()
    o7 = oos[sku][(oos.index > day - timedelta(7)) & (oos.index <= day)]
    if o7.sum() > 0:
        ev.append(f"{int(o7.sum())} depot-days out of stock in the last 7 days: sales understate demand (censored)")
    if b is not None:
        ev.append(f"{b:.0%} of depots above {ctl['f09']:g}x their own baseline ({', '.join(deps) or 'none'})")
    in_launch = since is not None and 0 <= since <= ctl["f15"]
    if in_launch:
        ev.append(f"{since} days after launch (launch window {ctl['f15']:.0f} days)")
    ev.append("Promotion calendar not available to the model (gap G34), so a promotion cannot be ruled out")
    ev.append("Pantry-loading test needs retailer orders and shelf sell-through as separate series; "
              "the quick-commerce feed has sell-through only")
    if b is not None and b >= ctl["f16"] and sudden:
        cls = "Viral burst" + (" (inside launch window)" if in_launch else "")
    elif in_launch:
        cls = "Launch ramp"
    elif b is not None and b < ctl["f16"]:
        cls = "Local surge"
    else:
        cls = "Unclassified rise"
    return cls, ev


def persistence(ctl, base_daily, mult, days):
    """Extra daily demand above baseline under hold / decay / fade (spec 4.2; G20)."""
    t = np.arange(days)
    ex = max(mult - 1, 0) * base_daily
    return {"holds": ex * np.ones(days),
            "decays": ex * 0.5 ** (t / ctl["f17"]),
            "fades": ex * 0.5 ** (t / ctl["f18"])}


@lru_cache(maxsize=32)
def alerts(w, ctl):
    """Active and recent demand alerts as of week w, one per flavor episode (last 35 days)."""
    out = []
    last = w + timedelta(6)
    for s in SKUS:
        st, eps = detect(w, ctl, s)
        for ep in eps:
            if ep["start"] < last - timedelta(35):
                continue
            first_cls, _ = classify(w, ctl, s, ep)
            judged = min(ep["start"] + timedelta(10), last if ep["end"] is None else ep["end"])
            cls, ev = classify(w, ctl, s, ep, day=judged)
            if first_cls != cls:
                ev.insert(0, f"Read as '{first_cls}' on the alert day; reclassified as more days arrived")
            cur = st[-1]
            mult = cur["ewma"] if cur["ewma"] else ep["peak_ratio"]
            out.append(dict(id=f"DA-{s}-{ep['start'].isoformat()}", sku=s, channel="C_QC", start=ep["start"],
                            first_hit=ep["first_hit"], active=ep["end"] is None, end=ep["end"],
                            ratio=mult, peak=ep["peak_ratio"], base=cur["base"], cls=cls, evidence=ev))
    return out


# ------------------------------------------------------------------------------------- replay
def _planning_sees(day):
    """When the consolidated sales for `day` reach Planning (demand_weekly.visible_to_planning; case F30)."""
    s = store()
    wk = day - timedelta(day.weekday())
    v = s.dem[s.dem.week_start == wk].visible_to_planning
    try:
        return date.fromisoformat(str(v.iloc[0])) if len(v) else None
    except ValueError:
        return None


@lru_cache(maxsize=16)
def replay_spike(ctl, sku="DP", frm=date(2026, 3, 2), to=date(2026, 4, 30)):
    """Run the detector day by day through the spike window. Detection date and lead over month-end."""
    st, eps = detect(None, ctl, sku, upto=to)
    eps = [e for e in eps if e["start"] >= frm]
    ser = [dict(date=x["date"], x=x["x"], base=x["base"], ewma=x["ewma"], alert=x["alert"], censored=x["censored"])
           for x in st if frm - timedelta(14) <= x["date"] <= to]
    if not eps:
        return dict(sku=sku, detected=None, series=ser)
    e = eps[0]
    sees = _planning_sees(e["start"])
    month_end = date(e["start"].year + (e["start"].month == 12), e["start"].month % 12 + 1, 1) - timedelta(1)
    return dict(sku=sku, detected=e["start"], first_hit=e["first_hit"], peak=e["peak_ratio"],
                planning_sees=sees, month_end=month_end,
                lead_planning=(sees - e["start"]).days if sees else None,
                lead_month_end=(month_end - e["start"]).days, series=ser)


@lru_cache(maxsize=16)
def replay_censoring(ctl, frm=date(2026, 5, 11), to=date(2026, 6, 30)):
    """Downward ('demand collapse') detector on PP and DP through the stock-out window, with and without the mask."""
    nat, oos, ndep, dep = _qc_frames()
    res = []
    for s in ("PP", "DP"):
        x = nat[s][nat.index <= to]
        o = (oos[s] / ndep.get(s, 9))[oos.index <= to]
        ly = _ly(ctl, s, x)
        _, with_mask = _detect_series(x, o, ctl, start_ok=launch_date(s), down=True, ly=ly)
        _, no_mask = _detect_series(x, o * 0, ctl, start_ok=launch_date(s), down=True, ly=ly)
        f = lambda eps: [e for e in eps if frm <= e["start"] <= to]
        cens = int((o[(o.index >= frm)] >= 1 / 3).sum())
        res.append(dict(sku=s, masked=len(f(with_mask)), unmasked=len(f(no_mask)), censored_days=cens,
                        first_unmasked=f(no_mask)[0]["start"] if f(no_mask) else None))
    return res


# ------------------------------------------------------------------------------------- depot split
@lru_cache(maxsize=32)
def depot_shares(w, ctl):
    """Depot share of each flavor's national demand, recency-weighted and shrunk toward the region."""
    st = store()
    e = estimated(ctl["f07"])
    known = [x for x in st.weeks if x <= w][-13:]
    hl, k = ctl["f19"], ctl["f20"]
    wts = {x: 0.5 ** ((w - x).days / 7 / hl) for x in known}
    d = st.dem[st.dem.week_start.isin(known)].copy()
    d["est"] = d.units_ordered if ctl["f07"] == "orders" else d.units_sold
    d["wt"] = d.week_start.map(wts)
    dep_reg = st.depots.set_index("depot_id").region
    ndep_reg = dep_reg.value_counts()
    out = {}
    for s in SKUS:
        g = d[d.sku_id == s]
        if g.est.sum() <= 0:
            out[s] = None
            continue
        weekly = g.groupby(["week_start", "depot_id"]).est.sum().unstack().fillna(0)
        wv = np.array([wts[x] for x in weekly.index])
        share_w = weekly.div(weekly.sum(axis=1), axis=0)
        s_d = (share_w.mul(wv, axis=0).sum() / wv.sum())
        n_d = float(wv.sum())
        reg = s_d.groupby(dep_reg).sum()
        s_reg = pd.Series({dd: reg[dep_reg[dd]] / ndep_reg[dep_reg[dd]] for dd in s_d.index})
        shrunk = (n_d * s_d + k * s_reg) / (n_d + k)
        method = f"recency-weighted ({len(weekly)} weeks), shrunk to region (k={k:g})"
        if s == "DP" and len(weekly) < 4 and out.get("PP") is not None and out.get("DB") is not None:
            prior = 0.5 * (out["PP"]["share"] + out["DB"]["share"])
            shrunk = (n_d * s_d + max(k, 1) * prior.reindex(s_d.index).fillna(0)) / (n_d + max(k, 1))
            method = f"new flavor: {len(weekly)} weeks blended with the PP + DB average (prior)"
        shrunk = shrunk / shrunk.sum()
        out[s] = dict(share=shrunk, raw=s_d, region=s_reg, method=method, weeks=len(weekly))
    return out


@lru_cache(maxsize=16)
def depot_forecast(w, ctl, weeks=4):
    """Hook for prompt 2 (Inventory): depot x flavor P50 / finished-goods percentile for the next `weeks` weeks."""
    f = national(w, ctl)
    sh = depot_shares(w, ctl)
    rows = []
    for (wk, s), g in f.groupby(["week", "sku"]):
        if wk >= w + timedelta(7 * (weeks + 1)) or sh.get(s) is None:
            continue
        zf = z(ctl["f04"])
        for dd, x in sh[s]["share"].items():
            p50 = float(g.p50.sum() * x)
            rows.append(dict(week=wk, depot_id=dd, sku=s, p50=p50,
                             p_fg=max(0.0, p50 * (1 + zf * ctl["f01"] / MAD)),       # depot-level error f01 (F28)
                             p80=max(0.0, p50 * (1 + z(80) * ctl["f01"] / MAD)),
                             share=float(x), share_method=sh[s]["method"]))
    return pd.DataFrame(rows)


def plan_share(w, sku):
    """Share used by the current monthly depot plan (forecast_monthly), for comparison."""
    s = store()
    s._dem_extra()
    m = f"{w.year}-{w.month:02d}"
    f = s.fc[(s.fc.month == m) & (s.fc.sku_id == sku)]
    if f.empty or f.p50_units.sum() <= 0:
        return None
    return (f.set_index("depot_id").p50_units / f.p50_units.sum())
