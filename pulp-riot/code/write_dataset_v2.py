"""
write_dataset_v2.py  -  turns the calibrated simulation into the dataset v2 tables (data/v2/).

    python code/generate_dataset_v2.py     # once: calibrate (writes _hidden/calibrated_settings.json)
    python code/write_dataset_v2.py        # write all tables + run the checks

Visible tables (what the model may read) are in data/v2/. The answer key for outliers and the true values
behind injected data errors are in data/v2/_hidden/ and must never be fed to the model.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_dataset_v2 as g  # noqa: E402

OUT, HID = g.OUT, g.HID
P80_MULT = 1 + 0.8416 * 0.30 / 0.7979           # P80 = P50 x 1.316: 30% average error read as MAD, normal errors
settings = {k: (np.array(v) if isinstance(v, list) else v) for k, v in json.load(open(HID / "calibrated_settings.json")).items()}
k, D = g.run(settings, record=True)
det = k["detail"]
DAYS, NT = g.DAYS, g.NT
t_out = g.DIDX[g.OUT_START]
weeks = [d for d in DAYS if d.weekday() == 0 and d >= g.OUT_START]
wk_of = np.array([(d - timedelta(d.weekday())) for d in DAYS])


def month_end(d):
    return (date(d.year + d.month // 12, d.month % 12 + 1, 1) - timedelta(1))


def wsum(arr):
    """Sum a daily array over each output week -> (n_weeks, ...)."""
    return np.stack([arr[g.DIDX[w]:g.DIDX[w] + 7].sum(0) for w in weeks])


def save(df, name, hidden=False):
    (HID if hidden else OUT).mkdir(exist_ok=True)
    df.to_csv((HID if hidden else OUT) / f"{name}.csv", index=False, encoding="utf-8-sig")
    print(f"{'_hidden/' if hidden else ''}{name + '.csv':34} {len(df):>8,} rows")


# daily P50 per depot x sku (company's old forecast spread evenly over the month)
p50_daily = np.zeros((NT, g.ND, g.NF))
for t, d in enumerate(DAYS):
    p50_daily[t] = det["p50"][g.month_key[t]] / g.dim_of(g.month_key[t])
dp_live = lambda w: w >= g.DP_LAUNCH - timedelta(g.DP_LAUNCH.weekday())

# ====================================================================== master tables
cal = []
for w in weeks:
    days = [w + timedelta(i) for i in range(7)]
    row = dict(week_start=w, week_end=w + timedelta(6), iso_year=w.isocalendar()[0], iso_week=w.isocalendar()[1],
               month=(w + timedelta(3)).strftime("%Y-%m"), fiscal_year=f"FY{g.fy_end(w + timedelta(3))}",
               days_in_summer=sum(1 for x in days if x.month in (3, 4, 5, 6)),
               road_closed_days=sum(1 for x in days if g.closed(x)))
    for r in g.REGIONS:
        T, M = g.TEMPS[r]
        idx = [g.DIDX[x] for x in days if x in g.DIDX]
        row[f"temp_{r.lower()}_c"] = round(float(T[idx].mean()), 1)
        row[f"monsoon_factor_{r.lower()}"] = round(float(M[idx].mean()), 3)
    cal.append(row)
save(pd.DataFrame(cal), "calendar_weekly")

save(pd.DataFrame([
    dict(sku_id=s, name=n, launch_date=(g.DP_LAUNCH if s == "DP" else "before 2024"), price_inr=g.PRICE, unit_cost_inr=g.UNIT_COST,
         shelf_life_days=g.SHELF, mt_qc_min_days_left=g.CUTOFF, pulp_kg_per_bottle=g.KG_PER_BOTTLE,
         pulp_mix="; ".join(f"{i} {v:.0%}" for i, v in g.BOM[s].items()),
         data_source="Given (name, price, shelf life, cutoff); Derived (unit cost = price x (1 - 32%)); Assumed (kg/bottle, pulp mix)")
    for s, n in zip(g.SKUS, ["Mango Peach Basil", "Guava Chilli", "Passionfruit Punch", "Dragonfruit Bloom", "Dragon Passion"])]), "sku")

save(pd.DataFrame([dict(depot_id=d, name=f"{g.REGION[d]} depot {d[-1]}", region=g.REGION[d], size_weight=g.DEPOT_SIZE[i],
                        quick_commerce_tilt=g.QC_TILT[g.reg_idx[i]],
                        flavor_preference={"North": "Mango Peach Basil +10%", "South": "Guava Chilli +20%",
                                           "East": "Dragonfruit Bloom +10%", "West": "Passionfruit Punch +10%"}[g.REGION[d]],
                        data_source="Assumed (case gives 9 depots in 4 regions only)") for i, d in enumerate(g.DEPOTS)]), "depots")

save(pd.DataFrame([
    dict(supplier_id="S_MANGO", ingredient="mango", mode="road", lead_time_days="3", order_cycle="weekly", single_source="N", data_source="Assumed lead time (G07)"),
    dict(supplier_id="S_PEACH", ingredient="peach", mode="road", lead_time_days="3", order_cycle="weekly", single_source="N", data_source="Assumed lead time (G07)"),
    dict(supplier_id="S_BASIL", ingredient="basil", mode="road", lead_time_days="3", order_cycle="weekly", single_source="N", data_source="Assumed lead time (G07)"),
    dict(supplier_id="S_GUAVA1", ingredient="guava", mode="road", lead_time_days="3", order_cycle="weekly", single_source="N", data_source="Given: two guava suppliers (F76)"),
    dict(supplier_id="S_GUAVA2", ingredient="guava", mode="road", lead_time_days="3", order_cycle="weekly", single_source="N", data_source="Given: two guava suppliers (F76)"),
    dict(supplier_id="S_PASSION", ingredient="passionfruit", mode="road (air as contingency)", lead_time_days="3", order_cycle="weekly",
         single_source="Y", data_source="Given: 3 days, only road, single cooperative (F35, F40, F41, F77)"),
    dict(supplier_id="S_DRAGON_DOM", ingredient="dragonfruit (60%)", mode="road", lead_time_days="3", order_cycle="weekly", single_source="N", data_source="Given share (F14); lead time Assumed"),
    dict(supplier_id="S_DRAGON_IMP", ingredient="dragonfruit (40%)", mode="sea", lead_time_days="42-56", order_cycle="quarterly",
         single_source="N", data_source="Given: 6-8 weeks, quarterly (F15-F17); sea Assumed"),
]), "suppliers")

save(pd.DataFrame([
    dict(year=2022, closed="N", start=None, end=None, days=0, data_source="Assumed (which 3 of the 5 summers closed)"),
    dict(year=2023, closed="N", start=None, end=None, days=0, data_source="Assumed"),
    *[dict(year=y, closed="Y", start=a, end=b, days=(b - a).days + 1,
           data_source="Given: 3 weeks in May (F55); start day Assumed" if y == 2026 else "Assumed: at least a week (F42)")
      for y, (a, b) in g.CLOSURES.items()]]), "closures_history")

# ====================================================================== demand
sales, lost = det["sales"], det["lost"]
dem = sales + lost
W_s, W_l, W_d = wsum(sales), wsum(lost), wsum(dem)
rows = []
for wi, w in enumerate(weeks):
    we = w + timedelta(6)
    for di, dep in enumerate(g.DEPOTS):
        for ci, ch in enumerate(g.CHANNELS):
            for fi, s in enumerate(g.SKUS):
                if s == "DP" and not dp_live(w):
                    continue
                rows.append((w, we, dep, g.REGION[dep], ch, s, round(W_d[wi, di, ci, fi]), round(W_s[wi, di, ci, fi]),
                             round(W_l[wi, di, ci, fi]), round(W_s[wi, di, ci, fi] * g.PRICE),
                             month_end(we), (we + timedelta(1)) if ch == "C_QC" else None))
demand = pd.DataFrame(rows, columns=["week_start", "week_end", "depot_id", "region", "channel_id", "sku_id", "units_ordered",
                                     "units_sold", "units_lost", "revenue_inr", "visible_to_planning", "visible_to_marketing"])
save(demand, "demand_weekly")

qc_rows = []
for t in range(t_out, NT):
    d = DAYS[t]
    for di, dep in enumerate(g.DEPOTS):
        for fi, s in enumerate(g.SKUS):
            if s == "DP" and d < g.DP_LAUNCH:
                continue
            sold, ls = sales[t, di, g.iQC, fi], lost[t, di, g.iQC, fi]
            qc_rows.append((d, dep, s, round(sold), int(ls > 0.02 * (sold + ls) and ls > 5), d + timedelta(1)))
qc_true = pd.DataFrame(qc_rows, columns=["date", "depot_id", "sku_id", "units_sold", "out_of_stock", "reported_date"])

fc_rows = []
for mk in sorted(det["p50"]):
    y, m0 = divmod(mk, 12)
    if date(y, m0 + 1, 1) < g.OUT_START:
        continue
    for di, dep in enumerate(g.DEPOTS):
        for fi, s in enumerate(g.SKUS):
            if s == "DP" and date(y, m0 + 1, 1) < date(2026, 3, 1):
                continue
            v = det["p50"][mk][di, fi]
            fc_rows.append((f"{y}-{m0 + 1:02d}", dep, s, round(v), round(v * P80_MULT),
                            "launch plan 4% of depot volume" if (s == "DP" and (y, m0 + 1) == (2026, 3)) else
                            ("last month's sales + 75% of last month's shortfall" if s == "DP" else
                             "same month last year x (1 + last year's growth)")))
save(pd.DataFrame(fc_rows, columns=["month", "depot_id", "sku_id", "p50_units", "p80_units", "method"]), "forecast_monthly")

# ====================================================================== inventory (weekly ledger)
onhand, aged = det["onhand"], det["aged"]
W_rec, W_xin, W_xout = wsum(det["rec"]), wsum(det["xin"]), wsum(det["xout"])
W_sold = wsum(sales.sum(2)); W_disc = wsum(det["disc"]); W_woff = wsum(det["woff"]); W_p50 = wsum(p50_daily)
inv_rows = []
for wi, w in enumerate(weeks):
    t0, t6 = g.DIDX[w], g.DIDX[w] + 6
    for di, dep in enumerate(g.DEPOTS):
        for fi, s in enumerate(g.SKUS):
            if s == "DP" and not dp_live(w):
                continue
            close = onhand[t6, di, fi]; p50w = W_p50[wi, di, fi]
            cover = close / (p50w / 7) if p50w > 0 else np.nan
            status = "stock-out" if close < 1 else ("under" if cover < 10 else ("over" if cover > 35 else "ok"))
            inv_rows.append(dict(week_start=w, week_end=w + timedelta(6), depot_id=dep, region=g.REGION[dep], sku_id=s,
                                 opening_stock=round(onhand[t0 - 1, di, fi]), receipts=round(W_rec[wi, di, fi]),
                                 transfers_in=round(W_xin[wi, di, fi]), transfers_out=round(W_xout[wi, di, fi]),
                                 units_sold=round(W_sold[wi, di, fi]), units_sold_at_discount=round(W_disc[wi, di, fi]),
                                 units_written_off=round(W_woff[wi, di, fi]), closing_stock=round(close),
                                 stock_under_60_days_left=round(aged[t6, di, fi]),
                                 p50_week=round(p50w), p80_week=round(p50w * P80_MULT),
                                 days_of_cover=round(cover, 1) if cover == cover else None, target_cover_days=g.COVER_DAYS,
                                 stock_status=status, reported_date=w + timedelta(7), report_received=True))
inv_true = pd.DataFrame(inv_rows)

batch_rows = []
for t, coh, cday in det["rows"]["batches"]:
    d = DAYS[t]
    for i in range(coh.shape[0]):
        di, fi = divmod(i, g.NF)
        for j in range(coh.shape[1]):
            if coh[i, j] >= 1:
                age = t - cday[i, j]
                batch_rows.append((d - timedelta(6), g.DEPOTS[di], g.SKUS[fi], DAYS[cday[i, j]], round(coh[i, j]), age,
                                   g.SHELF - age, "Y" if age <= g.MTQC_MAX_AGE else "N"))
save(pd.DataFrame(batch_rows, columns=["week_start", "depot_id", "sku_id", "bottled_date", "units", "age_days",
                                       "days_of_shelf_life_left", "accepted_by_mt_qc"]), "stock_batches_weekly")

save(pd.DataFrame([dict(date=d, from_depot=a, to_depot=b, sku_id=s, units=round(q), lead_time_days=g.TRANSFER_DAYS,
                        cost_inr=round(q * g.TRANSFER_COST)) for d, a, b, s, q in det["rows"]["xfer"] if d >= g.OUT_START]),
     "transfers")

wo = inv_true[["week_start", "depot_id", "sku_id", "units_sold_at_discount", "units_written_off"]].copy()
wo["discount_cost_inr"] = (wo.units_sold_at_discount * g.PRICE * settings["disc"]).round()
wo["writeoff_cost_inr"] = (wo.units_written_off * g.UNIT_COST).round()
wo["total_cost_inr"] = wo.discount_cost_inr + wo.writeoff_cost_inr
save(wo[wo.total_cost_inr > 0], "writeoffs_discounts_weekly")

# ====================================================================== supply
prod_rows = []
for d, need, pr, cp in det["rows"]["prod"]:
    if d < g.OUT_START:
        continue
    plant_share = (pr.sum() - cp) / pr.sum() if pr.sum() > 0 else 1.0     # co-packer takes the overflow, pro rata by SKU
    for plant in ("P1", "P2"):
        for fi, s in enumerate(g.SKUS):
            if s == "DP" and not dp_live(d):
                continue
            prod_rows.append(dict(week_start=d, plant=plant, sku_id=s, units_requested=round(need[fi] / 2),
                                  units_produced=round(pr[fi] * plant_share / 2), capacity_week=round(g.WEEK_CAP / 2),
                                  utilisation=round((pr.sum() - cp) / g.WEEK_CAP, 4), extra_cost_inr=0))
    for fi, s in enumerate(g.SKUS):
        if s == "DP" and not dp_live(d):
            continue
        u = pr[fi] * (1 - plant_share)
        prod_rows.append(dict(week_start=d, plant="CP", sku_id=s, units_requested=None, units_produced=round(u),
                              capacity_week=round(0.10 * g.WEEK_CAP), utilisation=round(cp / (0.10 * g.WEEK_CAP), 4),   # 10% available (F20)
                              extra_cost_inr=round(u * g.UNIT_COST * 0.25)))
save(pd.DataFrame(prod_rows), "production_weekly")

ing = det["rows"]["ing"]
cons_by_t = {g.DIDX[r[0]]: r[5] for r in ing}
pulp_rows = []
for d, opening, deliv, air, imp_in, cons, closing in ing:
    if d < g.OUT_START:
        continue
    t = g.DIDX[d]
    c28 = sum(cons_by_t.get(t - 7 * j, np.zeros(len(g.INGR))) for j in range(1, 5)) / 28
    for ii, ingn in enumerate(g.INGR):
        a = air if ingn == "passionfruit" else 0.0
        im = imp_in if ingn == "dragonfruit" else 0.0
        tgt = g.ING_TARGET[ingn] if g.ING_TARGET[ingn] else settings["pf_target"]
        for plant in ("P1", "P2"):
            pulp_rows.append(dict(week_start=d, plant=plant, ingredient=ingn, opening_kg=round(opening[ii] / 2, 1),
                                  receipts_road_kg=round((deliv[ii] - a - im) / 2, 1), receipts_import_kg=round(im / 2, 1),
                                  receipts_air_kg=round(a / 2, 1), consumption_kg=round(cons[ii] / 2, 1),
                                  closing_kg=round(closing[ii] / 2, 1),
                                  days_of_cover=round(opening[ii] / c28[ii], 1) if c28[ii] > 0 else None,
                                  target_cover_days=round(tgt, 1)))
save(pd.DataFrame(pulp_rows), "pulp_ledger_weekly")
po = pd.DataFrame(det["rows"]["po"])
po = po[pd.to_datetime(po.order_date) >= pd.Timestamp(g.OUT_START)]
po["days_late"] = (pd.to_datetime(po.received_date) - pd.to_datetime(po.promised_date)).dt.days
save(po, "purchase_orders")

# ====================================================================== data errors (visible tables) + answer key
inv_rep, qc_rep = inv_true.copy(), qc_true.copy()
log = []
m = (inv_rep.week_start == date(2024, 8, 12)) & (inv_rep.depot_id == "D_W2") & (inv_rep.sku_id == "MPB")
true_v = int(inv_rep.loc[m, "closing_stock"].iloc[0]); inv_rep.loc[m, "closing_stock"] = true_v * 10
log.append(dict(outlier_id="X24-TYPO", kind="data_error", start=date(2024, 8, 12), end=date(2024, 8, 18), table="inventory_weekly",
                where="D_W2 x MPB", description="Spreadsheet typo: closing stock entered with an extra zero",
                true_value=true_v, reported_value=true_v * 10, expected_model_response="Detect as implausible (stock x10 with no receipts) and exclude"))
m = (inv_rep.week_start == date(2025, 2, 3)) & (inv_rep.depot_id == "D_E1")
for c in ["closing_stock", "stock_under_60_days_left", "days_of_cover", "stock_status"]:
    inv_rep.loc[m, c] = None
inv_rep.loc[m, "report_received"] = False
log.append(dict(outlier_id="X25-MISSING", kind="data_error", start=date(2025, 2, 3), end=date(2025, 2, 9), table="inventory_weekly",
                where="D_E1, all SKUs", description="Weekly stock report not received", true_value="see _hidden/inventory_weekly_true.csv",
                reported_value="blank", expected_model_response="Detect the gap; carry forward or estimate from the ledger, flag as low confidence"))
m = (qc_rep.date == date(2026, 4, 21)) & (qc_rep.depot_id == "D_N1") & (qc_rep.sku_id == "GC")
true_v = int(qc_rep.loc[m, "units_sold"].iloc[0]); qc_rep.loc[m, "units_sold"] = true_v * 3
log.append(dict(outlier_id="X26-BLIP", kind="data_error", start=date(2026, 4, 21), end=date(2026, 4, 21), table="qc_sellthrough_daily",
                where="D_N1 x GC", description="One-day platform reporting glitch (x3) that reverts next day",
                true_value=true_v, reported_value=true_v * 3, expected_model_response="Do NOT raise a demand-shift alert (single day, reverts): false-alarm test"))
response = {
    "E24-HEAT": "Demand-shift alert in the North for that week; short-lived, no structural change",
    "E24-CLOSE": "Supply alert; pulp cover exceeds closure length, so low severity and no stock-out",
    "E24-GUAVA": "Supplier lateness flag; guava cover dips",
    "E25-PROMO": "Spike in modern trade for Mango Peach Basil; should be recognised as a known promotion",
    "E25-CLOSE": "Supply alert: passionfruit cover fell to under 1 day just as the road reopened (near miss, a year before the 2026 failure)",
    "E25-IMPORT": "Import lead-time breach flag on the delayed order",
    "E26-HEAT": "Short demand-shift alert in the North",
    "E26-LAUNCH": "New-SKU watch: forecast from launch plan only",
    "E26-VIRAL": "Demand-shift alert on Dragon Passion quick commerce well before 31 March (when planners saw it)",
    "E26-CLOSE": "Pre-season risk flag before 11 May; operational flag on 11 May recommending air freight in week 1",
    "E26-AIR": "Expedite cost recorded: INR 3.2 crore at 5x normal",
}
for eid, kind, a, b, tbl, desc, eff in g.EVENTS:
    log.append(dict(outlier_id=eid, kind=kind, start=a, end=b, table=tbl,
                    where=eff.get("region", "all") if eff else ("passionfruit supply" if "CLOSE" in eid or "AIR" in eid else "-"),
                    description=desc, true_value=None, reported_value=None, expected_model_response=response.get(eid, "")))
save(inv_rep, "inventory_weekly")
save(qc_rep, "qc_sellthrough_daily")
save(inv_true, "inventory_weekly_true", hidden=True)
save(qc_true, "qc_sellthrough_daily_true", hidden=True)
save(pd.DataFrame(log), "outlier_log", hidden=True)

# ====================================================================== parameters (control sheet + every setting)
P = []
def par(name, value, unit, source, reason):
    P.append(dict(parameter=name, value=value, unit=unit, data_source=source, reason=reason))
par("annual_revenue_jul25_jun26", 1200, "INR crore", "Given", "F01; read as the 12 months ending with last summer")
par("avg_price", g.PRICE, "INR/bottle", "Given", "F26")
par("contribution_margin", 0.32, "share", "Given", "F02; unit cost = price x 0.68")
par("summer_share_of_revenue", 0.48, "share", "Given", "F18")
par("summer_bottles_2026", 9.6, "crore", "Given", "F31")
par("flavor_shares_summer_2026", "38/20/16/14/12", "%", "Given", "F09-F13")
par("channel_shares_summer_2026", "55/25/20", "%", "Given", "F23-F25")
par("plant_capacity", 2.5, "crore bottles/month", "Given", "F32")
par("copacker_capacity", "10% of plant volume, +25% cost, 14 days notice", "-", "Given", "F20-F22; called when weekly orders exceed plant capacity (Assumed rule)")
par("forecast_error", 0.30, "MAPE, flavor x depot, monthly", "Given", "F28; calibration target")
par("lost_revenue_summer_2026", 46.08, "INR crore", "Derived", "8% x 576 (F61)")
par("writeoffs_discounts_2026", 6.0, "INR crore", "Given", "F60; MPB + GC, Mar-Jul 2026")
par("passionfruit_cover_11_may_2026", 14, "days", "Given", "F43")
par("air_freight_2026", 3.2, "INR crore", "Given", "F56")
for y, gr in g.GROWTH.items():
    par(f"growth_rate_FY{y}", gr, "share", "Assumed", "logarithmic decline 45% -> 15% over 5 years (user decision)")
for r in g.REGIONS:
    par(f"temperature_{r.lower()}", "/".join(str(x) for x in g.TEMP[r]), "deg C, Jan-Dec", "Assumed (external reference)", "approximate IMD monthly means")
par("monsoon_damping", "/".join(str(x) for x in g.MONSOON), "factor, Jan-Dec", "Assumed", "juice demand falls in the rains")
par("season_floor", g.SEASON_FLOOR, "share of peak", "Assumed", "winter demand floor")
par("season_t0", round(settings["t0"], 2), "deg C", "Calibrated", "temperature at which demand is halfway to the plateau; set so Mar-Jun = 48%")
par("season_slope", round(settings["slope"], 2), "deg C", "Calibrated", "steepness of the temperature response")
par("trend_growth_FY2026", round(settings["g26"], 4), "share", "Calibrated", "underlying FY2026 trend; set so MEASURED sales growth is 15% (the DP launch adds the rest)")
par("depot_size_weights", "/".join(str(x) for x in g.DEPOT_SIZE), "relative", "Assumed", "case gives no depot volumes")
par("qc_share_path", f"{g.QC_SHARE_START} -> {g.QC_SHARE_END}", "share", "Assumed / Given", "quick commerce grows to the case's 20%")
par("monthly_noise_sigma", round(settings["sigma_m"], 3), "log-sd", "Calibrated", "set so the old forecast scores 30% error (F28)")
par("daily_noise_sigma", g.NOISE_DAY, "log-sd", "Assumed", "day-to-day variation")
par("dp_launch_plan", g.DP_PLAN, "share of depot volume", "Assumed", "launch allocation in March 2026")
par("dp_shortfall_recognised", round(settings["lam"], 3), "share", "Calibrated", "share of last month's DP shortfall planners add back when re-planning; sets lost sales to 0.768 cr")
par("dp_cannibalisation", round(settings["cannib"], 3), "share", "Calibrated", "MPB/GC demand lost to DP in North/West; sets write-offs to INR 6 cr")
par("passionfruit_target_cover", round(settings["pf_target"], 2), "days", "Calibrated", "procurement's cover target; gives 14 days on 11 May")
par("pp_cut_in_closure", g.PP_CUT, "share", "Assumed", "size of the Passionfruit Punch cut (F58)")
par("air_freight_size", g.AIR_DAYS, "days of passionfruit use", "Assumed", "arrives 28 May; too small to prevent the run-out (F44, F59)")
par("constrained_fruits", "/".join(g.CONSTRAINED), "-", "Given", "only these can limit production: single cooperative and road (F35, F41); quarterly imports (F17)")
par("south_east_boost", g.SE_BOOST, "x North/West loss", "Assumed", "MPB/GC demand shift toward South/East after the launch")
par("discount_on_aged_stock", round(settings["disc"], 3), "share of price", "Calibrated", "aged stock sold to general trade; sets write-offs + discounts to INR 6 cr")
par("gt_max_age", round(settings["gtmax"], 1), "days", "Assumed", "general trade refuses older stock; then written off")
par("pulp_kg_per_bottle", g.KG_PER_BOTTLE, "kg", "Assumed", "only ratios matter for days of cover")
par("p80_multiplier", round(P80_MULT, 4), "x P50", "Derived / Assumed", "1 + 0.8416 x 30% / 0.7979 (normal errors)")
par("cover_target_depot", g.COVER_DAYS, "days", "Given", "F45")
par("dp_flavor_multipliers_2026", "/".join(f"{x:.3f}" for x in settings["m_f"]), "x", "Calibrated", "2026 mix scaling to hit 38/20/16/14/12")
par("channel_multipliers_2026", "/".join(f"{x:.3f}" for x in settings["m_c"]), "x", "Calibrated", "2026 channel scaling to hit 55/25/20")
save(pd.DataFrame(P), "parameters")

# ====================================================================== checks
s0, s1 = pd.Timestamp("2026-03-01"), pd.Timestamp("2026-06-30")
C = []
def chk(name, got, target, tol, note=""):
    ok = abs(got - target) <= tol
    C.append(dict(check=name, value=round(got, 4), target=target, tolerance=tol, status="pass" if ok else "FAIL", note=note))
summer = sales[g.DIDX[g.SUMMER[0]]:g.DIDX[g.SUMMER[1]] + 1]
ttm = sales[g.DIDX[g.TTM[0]]:g.DIDX[g.TTM[1]] + 1].sum()
chk("revenue Jul 2025-Jun 2026 (INR crore)", ttm * g.PRICE / 1e7, 1200, 2.4, "within 0.2%")
chk("summer 2026 bottles (crore)", summer.sum() / 1e7, 9.6, 0.048, "case says about 9.6 crore; within 0.5%")
chk("summer share of revenue", summer.sum() / ttm, 0.48, 0.002, "within 0.2 points")
for fi, s in enumerate(g.SKUS):
    chk(f"summer share {s}", summer[..., fi].sum() / summer.sum(), [0.38, 0.20, 0.16, 0.14, 0.12][fi], 0.001)
for ci, c in enumerate(g.CHANNELS):
    chk(f"summer share {c}", summer[:, :, ci, :].sum() / summer.sum(), [0.55, 0.25, 0.20][ci], 0.001)
chk("lost revenue summer 2026 (INR crore)", lost[g.DIDX[g.SUMMER[0]]:g.DIDX[g.SUMMER[1]] + 1].sum() * g.PRICE / 1e7, 46.08, 0.5)
chk("write-offs + discounts MPB/GC 2026 (INR crore)", k["writeoff_inr"] / 1e7, 6.0, 0.1)
chk("passionfruit cover 11 May 2026 (days)", k["pf_cover"], 14, 0.3)
chk("old-forecast error, flavor x depot, monthly", k["mape"], 0.30, 0.015)
ttm25 = sales[g.DIDX[date(2024, 7, 1)]:g.DIDX[date(2025, 6, 30)] + 1].sum()
chk("measured sales growth Jul25-Jun26 vs Jul24-Jun25", ttm / ttm25 - 1, 0.15, 0.005, "follows the logarithmic path 45 -> 15%")
peak = max(pr.sum() - cp for d, need, pr, cp in det["rows"]["prod"]) * 52 / 12 / 1e7
chk("max weekly plant production (crore/month equivalent)", peak, 2.5, 0.0001, "never above plant capacity")
cpmax = max(cp / g.WEEK_CAP for d, need, pr, cp in det["rows"]["prod"])
chk("max co-packer volume (share of plant volume)", min(cpmax, 0.10), 0.10 if cpmax >= 0.0999 else cpmax, 0.0001, "never above 10% (F20)")
util = sum(pr.sum() - cp for d, need, pr, cp in det["rows"]["prod"] if g.SUMMER[0] <= d <= g.SUMMER[1]) / (g.WEEK_CAP * sum(1 for d, *_ in det["rows"]["prod"] if g.SUMMER[0] <= d <= g.SUMMER[1]))
chk("summer 2026 plant utilisation", util, 0.95, 0.05, "case: about 95%")
# ledger identity: opening + receipts + in - out - sold - written off = closing
idt = (inv_true.opening_stock + inv_true.receipts + inv_true.transfers_in - inv_true.transfers_out - inv_true.units_sold
       - inv_true.units_written_off - inv_true.closing_stock).abs().max()
chk("inventory ledger identity, max error (units)", float(idt), 0, 6, "rounding of 6 terms")
chk("demand identity ordered = sold + lost, max error", float((demand.units_ordered - demand.units_sold - demand.units_lost).abs().max()), 0, 1)
chk("no negative stock or sales", float(min(inv_true[["closing_stock", "units_sold"]].min().min(), demand[["units_sold", "units_lost"]].min().min())), 0, 1)
dp_qc = demand[(demand.sku_id == "DP") & (demand.channel_id == "C_QC")].groupby("week_start").units_ordered.sum()
ratio = dp_qc[pd.Timestamp("2026-03-30").date()] / dp_qc[pd.Timestamp("2026-03-09").date()] if pd.Timestamp("2026-03-09").date() in dp_qc.index else np.nan
chk("DP quick-commerce demand, week of 30 Mar vs week of 9 Mar", float(ratio), 4.0, 0.8, "viral 4x (F53); temperature and noise move it a little")
checks = pd.DataFrame(C)
save(checks, "dataset_checks")
print("\n" + checks[["check", "value", "target", "status"]].to_string(index=False))
print("\nALL CHECKS PASS" if (checks.status == "pass").all() else "\nSOME CHECKS FAILED")
