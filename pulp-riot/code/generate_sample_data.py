"""
generate_sample_data.py  -  builds the two time-series tables from the case figures.

    python code/generate_sample_data.py

Reads  : data/products.csv, channels.csv, nodes.csv, events.csv
Writes : data/demand_daily.csv       date, depot_id, channel_id, flavor_id, units
         data/inventory_snapshot.csv date, node_id, flavor_id, units_on_hand, days_of_cover,
                                     target_cover_days, stock_status, data_source

HOW THE SALES SERIES IS BUILT (every step ties to a case figure)
  1. Summer volume is 9.6 crore bottles (F31), 1 March - 30 June (F18).
  2. Flavor shares 38/20/16/14/12 (F09-F13) and channel shares 55/25/20 (F23-F25) are
     held EXACTLY: each flavor x channel pair gets its own fixed total.
  3. Depots are equal weight (A11) and months are equal in size (A10).
  4. Within each flavor x channel pair, only the TIMING of sales is shaped:
       - Dragon Passion starts 2 March (F51).
       - Dragon Passion quick-commerce ramps from 1x to 4x between 16 and 30 March, then
         holds at 4x (F52, F53; the hold is A20).
       - Passionfruit Punch and Dragon Passion run at 30% of normal 25 May - 14 Jun (A21).
     Weights are then re-scaled so the pair's total stays at its Given share.

  Because the totals are pinned, the spike and the dip change WHEN units are sold, not how
  many are sold in the summer. Realized sales only: units that could not be sold are not in
  this table; the INR figures for those losses live in loss_ledger.csv.
"""
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"

# ------------------------------------------------------------------ inputs
products = pd.read_csv(DATA / "products.csv")
channels = pd.read_csv(DATA / "channels.csv")
nodes = pd.read_csv(DATA / "nodes.csv")
depots = nodes.loc[nodes["type"] == "depot", "node_id"].tolist()

SUMMER_BOTTLES = 9.6e7                       # F31: 9.6 crore
START, END = date(2026, 3, 1), date(2026, 6, 30)   # A15: year 2026 only orders dates
days = [START + timedelta(d) for d in range((END - START).days + 1)]
DP_LAUNCH = date(2026, 3, 2)                 # EV1
VIRAL = date(2026, 3, 16)                    # EV2
PEAK = date(2026, 3, 30)                     # EV3
PULP_OUT = date(2026, 5, 25)                 # EV7
CLOSURE_START, CLOSURE_END = date(2026, 5, 11), date(2026, 5, 31)   # EV5, EV8
DIP_END = date(2026, 6, 14)                  # A21 / A23
DIP_LEVEL = 0.30                             # A21


def weight(flavor: str, channel: str, d: date) -> float:
    """Relative selling pace for one flavor x channel on one day (before re-scaling)."""
    w = 1.0
    if flavor == "DP":
        if d < DP_LAUNCH:
            return 0.0
        if channel == "C_QC":
            if d >= PEAK:
                w *= 4.0
            elif d >= VIRAL:
                w *= 1.0 + 3.0 * (d - VIRAL).days / (PEAK - VIRAL).days
    if flavor in ("PP", "DP") and PULP_OUT <= d <= DIP_END:
        w *= DIP_LEVEL
    return w


def exact_integers(x: np.ndarray, total: int) -> np.ndarray:
    """Round a float series to integers that add up to exactly `total`."""
    floor = np.floor(x).astype(np.int64)
    short = int(total - floor.sum())
    order = np.argsort(-(x - floor))
    floor[order[:short]] += 1
    return floor


# ------------------------------------------------------------------ demand_daily
rows = []
for _, f in products.iterrows():
    for _, c in channels.iterrows():
        pair_total = SUMMER_BOTTLES * f["summer_share"] * c["summer_share"]
        w = np.array([weight(f["flavor_id"], c["channel_id"], d) for d in days])
        daily = pair_total / len(depots) * w / w.sum()           # per depot, per day
        depot_totals = exact_integers(np.full(len(depots), pair_total / len(depots)), int(round(pair_total)))
        for depot, dep_total in zip(depots, depot_totals):
            units = exact_integers(daily, int(dep_total))
            rows.append(pd.DataFrame({"date": days, "depot_id": depot,
                                      "channel_id": c["channel_id"],
                                      "flavor_id": f["flavor_id"], "units": units}))
demand = pd.concat(rows, ignore_index=True)
demand.to_csv(DATA / "demand_daily.csv", index=False, encoding="utf-8-sig")
print(f"demand_daily.csv        {len(demand):>8,} rows   total {demand['units'].sum():,} bottles")

# ------------------------------------------------------------------ inventory_snapshot
# Policy from the case: each depot holds ~3 weeks of cover for every flavor (F45), based on
# the previous year's flavor mix (F46), reset monthly (F47).
# Model: opening stock each month = 21 days x planned daily sales. Supply then arrives at the
# PLANNED rate, while sales follow ACTUAL demand, so stock drifts with the plan error.
TARGET_DAYS = 21
DP_PLAN = 0.05                                                    # A22
share = products.set_index("flavor_id")["summer_share"]
plan_mix = {f: (DP_PLAN if f == "DP" else s * (1 - DP_PLAN) / (1 - share["DP"]))
            for f, s in share.items()}

monthly = demand.assign(month=pd.to_datetime(demand["date"]).dt.to_period("M"))
dim = {m: monthly.loc[monthly["month"] == m, "date"].nunique() for m in monthly["month"].unique()}
daily_actual = (demand.groupby(["date", "depot_id", "flavor_id"])["units"].sum()
                .unstack("date").sort_index(axis=1))              # rows depot x flavor
snap = []
mondays = [d for d in days if d.weekday() == 0]
for depot in depots:
    for flv in products["flavor_id"]:
        sales = daily_actual.loc[(depot, flv)]
        for d in mondays:
            m = pd.Period(d, "M")
            plan_daily = SUMMER_BOTTLES / 4 / dim[m] * plan_mix[flv] / len(depots)  # A10, A11
            month_start = date(d.year, d.month, 1)
            elapsed = [x for x in days if month_start <= x < d]
            sold = sales.loc[elapsed].sum() if elapsed else 0
            # supply arrives at the planned pace, but PP and DP supply is pulp-limited in the dip window
            supplied = sum(plan_daily * (DIP_LEVEL if flv in ("PP", "DP") and PULP_OUT <= x <= DIP_END else 1)
                           for x in elapsed)
            on_hand = TARGET_DAYS * plan_daily + supplied - sold
            if flv in ("PP", "DP") and PULP_OUT <= d <= DIP_END:
                on_hand = 0          # A21: both flavors out of finished stock in this window
            trailing = sales.loc[[x for x in days if d - timedelta(7) <= x < d]]
            pace = trailing.mean() if len(trailing) else sales.loc[d]
            cover = max(on_hand, 0) / pace if pace > 0 else np.nan
            if on_hand <= 0:
                status = "stock-out"
            elif cover < 0.5 * TARGET_DAYS:
                status = "under"
            elif cover > 1.5 * TARGET_DAYS:
                status = "over"
            else:
                status = "ok"
            snap.append((d, depot, flv, int(max(on_hand, 0)), round(cover, 1) if cover == cover else "",
                         TARGET_DAYS, status, "Assumed"))

# Plant passionfruit pulp cover (A23): 14 days -> falls to 0 on 25 May -> rebuilds by 14 Jun.
for d in days:
    if d < CLOSURE_START:
        cover = 14.0
    elif d < PULP_OUT:
        cover = 14.0 - (d - CLOSURE_START).days
    elif d <= CLOSURE_END:
        cover = 0.0
    elif d <= DIP_END:
        cover = 14.0 * (d - CLOSURE_END).days / (DIP_END - CLOSURE_END).days
    else:
        cover = 14.0
    for p in ("P1", "P2"):
        src = "Given" if d == CLOSURE_START else ("Derived" if CLOSURE_START < d <= PULP_OUT else "Assumed")
        snap.append((d, p, "PULP_PASSION", "", round(cover, 1), 14, "stock-out" if cover == 0 else
                     ("under" if cover < 7 else "ok"), src))

inv = pd.DataFrame(snap, columns=["date", "node_id", "flavor_id", "units_on_hand", "days_of_cover",
                                  "target_cover_days", "stock_status", "data_source"])
inv.to_csv(DATA / "inventory_snapshot.csv", index=False, encoding="utf-8-sig")
print(f"inventory_snapshot.csv  {len(inv):>8,} rows")
print(inv[inv.flavor_id != "PULP_PASSION"].groupby(["flavor_id", "stock_status"]).size().unstack(fill_value=0))
