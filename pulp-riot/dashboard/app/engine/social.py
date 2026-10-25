"""
social.py - the Social Signal Desk. SIMULATED FEED, ILLUSTRATIVE ONLY.

Pulp Riot has no social-listening data (gap G35). This module generates a seeded, synthetic mention feed so the
desk's logic can be shown and tested. Its events are placed only where the CASE says something happened:
    launch buzz        Dragon Passion launch, early March (F51; date from sku.csv)
    influencer reel    two weeks after launch (F52)
    stock-out chatter  PP and DP ran out (F59), from 14 days into the May closure (F43, F55)
    rival chatter      a rival dragonfruit-passionfruit drink within 6 weeks of the stock-outs (F62)
    one false alarm    a meme spike on Guava Chilli that never reaches sales (a test of the "verify" rule)
The hidden test data (data/v2/_hidden) is never read.

Rule: social alone never triggers procurement. A social alert creates a VERIFY task against quick-commerce
sell-through; only a QC-confirmed rise feeds the demand scenarios, and every card needs a human decision.
"""
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from ..data import REGIONS, store
from . import forecast as F

TIERS = ["nano", "micro", "macro", "mega"]
TIER_REACH = {"nano": "under 10k followers", "micro": "10k–100k", "macro": "100k–1M", "mega": "over 1M"}
TOPICS = ["taste", "availability", "price", "competitor", "launch"]
SEED = 2026
SHARES = {"MPB": 0.38, "GC": 0.20, "PP": 0.16, "DB": 0.14, "DP": 0.12}     # case F09-F13, summer mix


@lru_cache(maxsize=1)
def feed():
    """Daily mentions: date x flavor x region x tier, with sentiment and topic mix. Deterministic (seed 2026)."""
    s = store()
    rng = np.random.default_rng(SEED)
    nat, *_ = F._qc_frames()
    tot = nat.sum(axis=1)
    season = (tot.rolling(28, min_periods=1).mean() / tot.rolling(28, min_periods=1).mean().max()).clip(0.15, 1)
    days = [d for d in nat.index if d >= date(2025, 10, 1)]
    dp_launch = F.launch_date("DP")
    c26 = s.closures[(s.closures.closed == "Y") & (s.closures.year == 2026)]
    close = c26.start.iloc[0] if len(c26) else date(2026, 5, 11)
    so = close + timedelta(14)                                                  # F43: ~2 weeks of pulp
    rows = []
    for d in days:
        for sku, sh in SHARES.items():
            if sku == "DP" and dp_launch and d < dp_launch:
                continue
            for reg in REGIONS:
                for tier, tw in zip(TIERS, (0.62, 0.28, 0.08, 0.02)):
                    lam = 120 * sh * float(season.get(d, 0.5)) * tw
                    sent, avail, comp, launch = 0.35, 0.05, 0.02, 0.0
                    if sku == "DP" and dp_launch:
                        t = (d - dp_launch).days
                        if 0 <= t < 10:
                            lam *= 1.6
                            launch = 0.4
                        t2 = (d - (dp_launch + timedelta(14))).days          # F52: reel two weeks after launch
                        if 0 <= t2:
                            boost = (8 if tier in ("macro", "mega") else 4) * np.exp(-t2 / 18)
                            lam *= 1 + boost
                            sent = 0.6
                    if sku in ("PP", "DP") and so <= d <= so + timedelta(25):     # F59 stock-outs
                        lam *= 2.2
                        sent, avail = -0.45, 0.55
                    if sku == "DP" and so + timedelta(25) < d <= so + timedelta(42):  # F62 rival launch
                        lam *= 1.5
                        comp, sent = 0.45, 0.0
                    if sku == "GC" and date(2026, 2, 9) <= d <= date(2026, 2, 12) and tier in ("macro", "mega") and reg == "South":
                        lam *= 15                                              # synthetic false alarm
                    n = int(rng.poisson(max(lam, 0.01)))
                    if n == 0:
                        continue
                    rows.append(dict(date=d, sku=sku, region=reg, tier=tier, mentions=n,
                                     sentiment=float(np.clip(rng.normal(sent, 0.15), -1, 1)),
                                     avail=avail, competitor=comp, launch=launch))
    return pd.DataFrame(rows)


def _velocity(series, day, L=28):
    x = series[series.index <= day]
    now = x.iloc[-7:].mean() if len(x) >= 7 else np.nan
    base = x.iloc[-7 - L:-7].mean() if len(x) >= 14 else np.nan
    return (now / base) if base and base == base and base > 0 else None, float(now) if now == now else 0.0


@lru_cache(maxsize=64)
def desk(w, ctl):
    """Social alerts as of the end of week w, each with its QC verification and a decision card."""
    f = feed()
    last = w + timedelta(6)
    f = f[f.date <= last]
    if f.empty:
        return dict(alerts=[], table=[], last=last, n_mentions=0)
    by = f.groupby(["date", "sku"]).mentions.sum().unstack().fillna(0).sort_index()
    table, alerts = [], []
    for sku in by.columns:
        v, now = _velocity(by[sku], last)
        g = f[(f.sku == sku) & (f.date > last - timedelta(7))]
        m = g.mentions.sum() or 1
        sent = float((g.sentiment * g.mentions).sum() / m)
        big = float(g[g.tier.isin(["macro", "mega"])].mentions.sum() / m)
        avail = float((g.avail * g.mentions).sum() / m)
        comp = float((g.competitor * g.mentions).sum() / m)
        launch = float((g.launch * g.mentions).sum() / m)
        regs = g.groupby("region").mentions.sum()
        reg_v = {}
        for r in REGIONS:
            sr = f[(f.sku == sku) & (f.region == r)].groupby("date").mentions.sum()
            reg_v[r] = _velocity(sr.reindex(by.index).fillna(0), last)[0]
        tier_v = {}
        for t in TIERS:
            st = f[(f.sku == sku) & (f.tier == t)].groupby("date").mentions.sum()
            tier_v[t] = _velocity(st.reindex(by.index).fillna(0), last)[0]
        if avail > 0.3 and sent < -0.2:
            cls = "Availability complaints"
        elif comp > 0.3:
            cls = "Competitor chatter"
        elif v and v >= ctl["f24"] and big >= ctl["f27"]:
            cls = "Influencer burst"
        elif launch > 0.3:
            cls = "Launch buzz"
        elif v and v >= ctl["f24"]:
            cls = "Organic buzz"
        else:
            cls = "Background"
        row = dict(sku=sku, velocity=v, per_day=now, sentiment=sent, big=big, cls=cls, region_v=reg_v, tier_v=tier_v,
                   top_region=regs.idxmax() if len(regs) else None)
        table.append(row)
        if v is not None and now >= ctl["f25"] and (v >= ctl["f24"] or cls in ("Availability complaints", "Competitor chatter")):
            alerts.append(_card(w, ctl, row, last))
    return dict(alerts=alerts, table=table, last=last, n_mentions=int(f[f.date > last - timedelta(7)].mentions.sum()))


def _card(w, ctl, row, last):
    """Verify against quick-commerce sell-through; scenarios only from a QC-confirmed multiplier."""
    sku = row["sku"]
    st, eps = F.detect(w, ctl, sku)
    cur = st[-1] if st else None
    o7 = [x for x in st[-7:] if x["censored"]]
    if cur is None or cur["base"] is None:
        verdict, mult = "QC baseline not yet available", None
    elif o7:
        verdict, mult = f"QC unobservable: stock-outs on {len(o7)} of the last 7 days (sales understate demand)", cur["ewma"]
    elif cur["ewma"] and cur["ewma"] >= ctl["f09"]:
        verdict, mult = f"Confirmed: QC sell-through {cur['ewma']:.1f}x its baseline", cur["ewma"]
    elif cur["ewma"] and cur["ewma"] >= 1.1:
        verdict, mult = f"Partly visible: QC {cur['ewma']:.1f}x baseline, below the {ctl['f09']:g}x alert line", None
    else:
        verdict, mult = "Not visible in QC sell-through: watch, no supply action", None
    if row["cls"] == "Availability complaints":
        action = "Check depot and dark-store stock for this flavor (complaints point to stock-outs, not new demand)"
    elif row["cls"] == "Competitor chatter":
        action = "Brief Marketing and the COO; no supply action from chatter alone"
    else:
        action = "Planning to verify against QC sell-through daily and prepare the demand scenarios"
    scen = None
    if mult and cur and cur["base"]:
        from .supply import demand_scenarios
        scen = demand_scenarios(w, ctl, sku, float(cur["base"]), float(mult))
    return dict(id=f"SOC-{sku}-{last.isoformat()}", sku=sku, cls=row["cls"], velocity=row["velocity"], sentiment=row["sentiment"],
                big=row["big"], verdict=verdict, confirmed=verdict.startswith("Confirmed"), action=action, scenarios=scen,
                top_region=row["top_region"],
                note="Simulated feed. Social alone never triggers procurement (rule); this card can only ask for verification.")
