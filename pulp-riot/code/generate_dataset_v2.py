"""
generate_dataset_v2.py  -  simulates Pulp Riot day by day and calibrates it to the case (see DATA_SPEC.md).

    python code/generate_dataset_v2.py          # calibrate, then save the simulation for write_dataset_v2.py

WHAT IT SIMULATES  (2 Jan 2023 burn-in, output from 1 Jan 2024, to 5 Jul 2026)
  demand   growth x Indian temperature season x region x flavor x channel x weekday x noise x events
  depots   weekly replenishment by the company's OLD method (same month last year, last year's mix,
           3 weeks of cover); FIFO batches that age; modern trade / quick commerce refuse stock with
           under 60 days left; older stock goes to general trade at a discount, or is written off
  plants   2.5 crore bottles/month, production limited by pulp in cold storage
  pulp     weekly road deliveries sized from recent plant usage; quarterly imports sized from the OLD
           forecast; highway closures; air freight; passionfruit shared by Passionfruit Punch and
           Dragon Passion (Dragon Passion protected during the closure, F58)
  Lost sales are what depots could not serve: they come out of the simulation, not a formula.

CALIBRATION
  Free settings are adjusted until 2026 reproduces the case: 20 cr bottles Jul 2025-Jun 2026 (₹1,200 cr),
  9.6 cr summer bottles, 38/20/16/14/12 and 55/25/20 shares, 0.768 cr lost bottles (₹46.08 cr),
  ₹6 cr write-offs and discounts, 14 days of passionfruit on 11 May, ~30% forecast error.
"""
import copy
import json
import math
import os
import pickle
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "v2"
HID = OUT / "_hidden"
OUT.mkdir(parents=True, exist_ok=True)
HID.mkdir(exist_ok=True)
SEED = 20260711

# ============================================================== dimensions
DEPOTS = ["D_N1", "D_N2", "D_S1", "D_S2", "D_E1", "D_E2", "D_W1", "D_W2", "D_W3"]
REGION = {"D_N1": "North", "D_N2": "North", "D_S1": "South", "D_S2": "South", "D_E1": "East", "D_E2": "East",
          "D_W1": "West", "D_W2": "West", "D_W3": "West"}
REGIONS = ["North", "South", "East", "West"]
CHANNELS = ["C_GT", "C_MT", "C_QC"]
SKUS = ["MPB", "GC", "PP", "DB", "DP"]
ND, NC, NF = len(DEPOTS), len(CHANNELS), len(SKUS)
reg_idx = np.array([REGIONS.index(REGION[d]) for d in DEPOTS])
iMPB, iGC, iPP, iDB, iDP = range(5)
iGT, iMT, iQC = range(3)

SIM_START, OUT_START, END = date(2023, 1, 2), date(2024, 1, 1), date(2026, 7, 5)
DAYS = [SIM_START + timedelta(i) for i in range((END - SIM_START).days + 1)]
NT = len(DAYS)
DIDX = {d: i for i, d in enumerate(DAYS)}
dates = pd.to_datetime(DAYS)
month_key = np.array([d.year * 12 + d.month - 1 for d in DAYS])


def dim_of(mk):
    y, m0 = divmod(mk, 12)
    return (date(y + (m0 + 1) // 12, (m0 + 1) % 12 + 1, 1) - date(y, m0 + 1, 1)).days


# ============================================================== case figures (Given / Derived)
PRICE = 60.0                         # F26
CM = 0.32                            # F02
UNIT_COST = PRICE * (1 - CM)         # Derived: ₹40.80 per bottle
SUMMER = (date(2026, 3, 1), date(2026, 6, 30))
TTM = (date(2025, 7, 1), date(2026, 6, 30))
TARGET = dict(ttm_bottles=1200e7 / PRICE,              # ₹1,200 cr / ₹60 = 20 cr (F01, F26)
              summer_share=0.48,                       # F18 -> 9.6 cr (F31)
              flavor=np.array([0.38, 0.20, 0.16, 0.14, 0.12]),   # F09-F13
              channel=np.array([0.55, 0.25, 0.20]),              # F23-F25
              lost_bottles=0.08 * 576e7 / PRICE,       # F61: 8% x ₹576 cr / ₹60 = 0.768 cr
              writeoff_inr=6e7,                        # F60
              pf_cover_days=14.0,                      # F43
              mape=0.30)                               # F28
PLANT_CAP_MONTH = 2.5e7              # F32, both plants
WEEK_CAP = PLANT_CAP_MONTH * 12 / 52
SHELF, CUTOFF = 90, 60               # F38, F39
MTQC_MAX_AGE = SHELF - CUTOFF        # Derived: MT/QC accept stock up to 30 days old
COVER_DAYS = 21                      # F45
DP_LAUNCH, VIRAL, PEAK = date(2026, 3, 2), date(2026, 3, 16), date(2026, 3, 30)   # F51-F53
TRANSFER_COST = 1.50                 # F50
TRANSFER_DAYS = 3                    # inside F49's 2-4 days

# ============================================================== Assumed settings (exported to parameters.csv)
GROWTH = {2022: 0.45, 2023: 0.3208, 2024: 0.2452, 2025: 0.1916, 2026: 0.15}   # 45% - 18.64% x ln(n), n = 1..5
TEMP = {"North": [14.5, 17.5, 23.0, 29.0, 33.0, 33.5, 31.0, 30.0, 29.5, 26.0, 20.5, 15.5],   # approx. IMD monthly
        "South": [24.5, 26.0, 28.0, 30.0, 31.0, 29.5, 28.5, 28.0, 28.0, 27.0, 25.5, 24.5],   # mean temperature, deg C
        "East":  [19.5, 23.0, 27.5, 30.0, 30.5, 30.0, 29.5, 29.3, 29.0, 27.5, 23.5, 20.0],
        "West":  [22.0, 23.5, 26.5, 29.0, 30.5, 29.5, 28.0, 27.5, 28.0, 28.5, 26.0, 23.0]}
MONSOON = [1, 1, 1, 1, 1, 0.90, 0.58, 0.55, 0.68, 0.90, 1, 1]   # cold-drink demand falls in the rains
DEPOT_SIZE = np.array([1.15, 0.95, 1.00, 0.85, 0.90, 0.80, 1.25, 1.10, 1.00])
BASE_MIX = np.array([0.38, 0.20, 0.16, 0.14]) / 0.88
REGION_TILT = np.array([[1.10, 0.90, 1.00, 1.00],     # North likes Mango Peach Basil
                        [0.90, 1.20, 1.00, 0.95],     # South likes Guava Chilli
                        [1.00, 1.00, 0.95, 1.10],     # East likes Dragonfruit Bloom
                        [1.00, 0.95, 1.10, 1.00]])    # West likes Passionfruit Punch
GC_DRIFT = 0.06                      # Guava Chilli share drifts up 6%/yr in South and East
QC_TILT = np.array([1.2, 0.8, 0.8, 1.2])
QC_SHARE_START, QC_SHARE_END = 0.12, 0.20
MT_SHARE = 0.25
DOW = {iGT: [1, 1, 1, 1, 1, 1.0, 0.85], iMT: [0.95, 0.95, 0.95, 1, 1.05, 1.1, 1.1], iQC: [0.95, 0.95, 1, 1, 1.05, 1.15, 1.15]}
NOISE_DAY = 0.10
DP_BASE = 0.12
DP_REGION = np.array([1.2, 0.8, 0.8, 1.2])
DP_PLAN = 0.03                       # launch plan: Dragon Passion at 3% of each depot's volume in March
CONSTRAINED = ("passionfruit", "dragonfruit")   # single cooperative + road (F35, F41); quarterly imports (F17)
SE_BOOST = 0.15                      # South/East MPB+GC demand rises by 15% of the North/West loss
PP_CUT = 0.9                         # Passionfruit Punch production cut in the closure weeks (F58; size Assumed)
DISCOUNT = 0.25
GT_MAX_AGE = 75
KG_PER_BOTTLE = 0.06
BOM = {"MPB": {"mango": 0.55, "peach": 0.35, "basil": 0.10}, "GC": {"guava": 1.0}, "PP": {"passionfruit": 1.0},
       "DB": {"dragonfruit": 1.0}, "DP": {"passionfruit": 0.5, "dragonfruit": 0.5}}
INGR = ["mango", "peach", "basil", "guava", "passionfruit", "dragonfruit"]
ING_TARGET = {"mango": 30, "peach": 30, "basil": 5, "guava": 30, "passionfruit": None, "dragonfruit": 30}
IMPORT_SHARE = 0.40                  # F15
IMPORT_LEAD = (42, 56)               # F16
CLOSURES = {2024: (date(2024, 6, 3), date(2024, 6, 9)),
            2025: (date(2025, 5, 19), date(2025, 5, 28)),
            2026: (date(2026, 5, 11), date(2026, 5, 31))}   # F55; start day Assumed (A09)
AIR_BOOKED, AIR_ARRIVES, AIR_DAYS = date(2026, 5, 18), date(2026, 5, 28), 4
AIR_COST = 3.2e7                     # F56
COVER_LO, COVER_HI = 7, 45
ORDER_SMOOTH = 0.5                   # depots close half the gap to their cover target each week (Assumed)
CP_SHARE = 0.10                      # co-packer adds up to 10% (F20), +25% cost (F21), called with 14 days notice (F22)
GUAVA_DELAY = (date(2024, 4, 8), date(2024, 4, 21))
IMPORT_DELAY_PO = date(2025, 4, 7)

EVENTS = [
    ("E24-HEAT", "real_event", date(2024, 5, 20), date(2024, 5, 26), "demand_weekly", "North heatwave: all flavors x1.35", dict(region="North", mult=1.35)),
    ("E24-CLOSE", "real_event", *CLOSURES[2024], "pulp_ledger_weekly", "Highway closure 7 days: no passionfruit by road", {}),
    ("E24-GUAVA", "real_event", *GUAVA_DELAY, "purchase_orders", "Guava supplier 1 deliveries arrive 14 days late", {}),
    ("E25-PROMO", "real_event", date(2025, 4, 14), date(2025, 4, 20), "demand_weekly", "Modern-trade promotion: Mango Peach Basil x1.8 in modern trade", dict(channel=iMT, sku=iMPB, mult=1.8)),
    ("E25-CLOSE", "real_event", *CLOSURES[2025], "pulp_ledger_weekly", "Highway closure 10 days: no passionfruit by road", {}),
    ("E25-IMPORT", "real_event", IMPORT_DELAY_PO, date(2025, 6, 16), "purchase_orders", "Imported dragonfruit order of 7 Apr 2025 arrives 14 days late", {}),
    ("E26-HEAT", "real_event", date(2026, 3, 9), date(2026, 3, 15), "demand_weekly", "Early heatwave in the North: all flavors x1.25", dict(region="North", mult=1.25)),
    ("E26-LAUNCH", "real_event", DP_LAUNCH, DP_LAUNCH, "demand_weekly", "Dragon Passion launched (F51)", {}),
    ("E26-VIRAL", "real_event", VIRAL, PEAK, "qc_sellthrough_daily", "Viral reel: Dragon Passion quick commerce 1x -> 4x over two weeks, then holds (F52, F53, A20)", {}),
    ("E26-CLOSE", "real_event", *CLOSURES[2026], "pulp_ledger_weekly", "Highway closure 3 weeks (F55)", {}),
    ("E26-AIR", "real_event", AIR_BOOKED, AIR_ARRIVES, "purchase_orders", "Air freight booked in week 2 of the closure, arrives 28 May (F44, F56)", {}),
]


# ============================================================== demand
def temp_daily(region):
    t = np.array(TEMP[region]); m = np.array(MONSOON)
    out_t, out_m = np.empty(NT), np.empty(NT)
    for i, d in enumerate(DAYS):
        mid = date(d.year, d.month, 15)
        j = d.month - 1
        k = (j + 1) % 12 if d >= mid else (j - 1) % 12
        oy = d.year + (1 if (d >= mid and d.month == 12) else 0) - (1 if (d < mid and d.month == 1) else 0)
        other = date(oy, k + 1, 15)
        w = abs((d - mid).days) / abs((other - mid).days)
        out_t[i] = t[j] * (1 - w) + t[k] * w
        out_m[i] = m[j] * (1 - w) + m[k] * w
    return out_t, out_m


TEMPS = {r: temp_daily(r) for r in REGIONS}


def fy_end(d):
    return d.year if d.month <= 6 else d.year + 1


def trend_series(day_list):
    t0 = date(2021, 7, 1)
    span = [t0 + timedelta(i) for i in range((day_list[-1] - t0).days + 1)]
    r = np.array([math.log(1 + GROWTH[min(2026, max(2022, fy_end(d)))]) / 365.25 for d in span])
    lvl = np.exp(np.cumsum(r))
    pos = {d: i for i, d in enumerate(span)}
    return np.array([lvl[pos[d]] for d in day_list])


TREND = trend_series(DAYS)
_TREND_CACHE = {}


def trend_for(g26):
    """Trend with the FY2026 growth rate set to g26 (calibrated so measured growth is 15%)."""
    key = round(float(g26), 6)
    if key not in _TREND_CACHE:
        old = GROWTH[2026]; GROWTH[2026] = key
        _TREND_CACHE[key] = trend_series(DAYS)
        GROWTH[2026] = old
    return _TREND_CACHE[key]
rng = np.random.default_rng(SEED)
NOISE_D = rng.lognormal(-NOISE_DAY ** 2 / 2, NOISE_DAY, size=(NT, ND, NC, NF))
Z_M = rng.standard_normal(size=(ND, NF, month_key.max() - month_key.min() + 1))
IMPORT_LEADS = rng.integers(IMPORT_LEAD[0], IMPORT_LEAD[1] + 1, size=20)
YRS = np.array([(d - date(2023, 1, 1)).days / 365.25 for d in DAYS])
QCS = QC_SHARE_START + (QC_SHARE_END - QC_SHARE_START) * np.clip(
    (dates - pd.Timestamp("2023-01-01")).days / (pd.Timestamp("2026-06-30") - pd.Timestamp("2023-01-01")).days, 0, 1)
DOWI = dates.weekday.values
IN26 = np.array([d >= date(2026, 1, 1) for d in DAYS])
ADOPT = np.clip(np.array([(d - DP_LAUNCH).days for d in DAYS]) / 7, 0, 1)      # DP reaches full distribution in a week
FADE_START, FADE_END = date(2026, 4, 26), date(2026, 6, 30)     # spike holds 4 weeks, then eases to 2x (rival takes shelf space, case p2)
def _viral(d):
    if d < VIRAL: return 1.0
    if d < PEAK: return 1 + 3 * (d - VIRAL).days / (PEAK - VIRAL).days
    if d < FADE_START: return 4.0
    return max(2.0, 4.0 - 2.0 * (d - FADE_START).days / (FADE_END - FADE_START).days)
VIRALM = np.array([_viral(d) for d in DAYS])
LAUNCHED = np.array([d >= DP_LAUNCH for d in DAYS])


SEASON_FLOOR = 0.15                       # demand saturates once it is hot; winter floor 15% of the peak


def season_weight(T, t0, slope):
    """Logistic response to temperature: rises through spring, plateaus in the hot months (Assumed)."""
    return SEASON_FLOOR + (1 - SEASON_FLOOR) / (1 + np.exp(-(T - t0) / slope))


def build_demand(p, noise=True):
    """Daily unconstrained demand D[t, depot, channel, sku]."""
    D = np.zeros((NT, ND, NC, NF))
    sig = p["sigma_m"] if noise else 0.0
    nm = np.exp(sig * Z_M - sig ** 2 / 2)[:, :, month_key - month_key.min()]
    for di in range(ND):
        r = reg_idx[di]; reg = REGIONS[r]
        T, M = TEMPS[reg]
        base = p["K"] * trend_for(p["g26"]) * season_weight(T, p["t0"], p["slope"]) * M * DEPOT_SIZE[di]
        drift = np.ones((NT, 4))
        if reg in ("South", "East"):
            drift[:, 1] = np.exp(GC_DRIFT * YRS)
        mix = (REGION_TILT[r] * BASE_MIX)[None, :] * drift
        mix = mix / mix.sum(1, keepdims=True)
        cann = np.ones((NT, 4))
        c = p["cannib"] * ADOPT
        if reg in ("North", "West"):
            cann[:, 0] = cann[:, 1] = 1 - c
        else:
            cann[:, 0] = cann[:, 1] = 1 + SE_BOOST * c
        fl = np.zeros((NT, NF))
        dp_raw = np.where(LAUNCHED, DP_BASE * DP_REGION[r] * ADOPT.clip(0.5, 1), 0.0)
        fl[:, :4] = mix * cann
        fl[:, iDP] = dp_raw                                                            # DP adds new demand on top
        fl = fl * p["m_f"][None, :]
        q = QCS * QC_TILT[r]
        ch = np.stack([1 - MT_SHARE - q, np.full(NT, MT_SHARE), q], axis=1)
        ch = ch / ch.sum(1, keepdims=True)
        ch = ch * p["m_c"][None, :]
        for ci in range(NC):
            dw = np.array(DOW[ci]); dw = dw / dw.mean()
            cell = base[:, None] * fl * ch[:, ci:ci + 1] * dw[DOWI][:, None]
            if ci == iQC:                                                              # observed DP QC orders = pre-viral week x v(t)
                pre = cell[DIDX[VIRAL] - 7:DIDX[VIRAL], iDP].mean()
                cell[:, iDP] = np.where(VIRALM > 1, pre * VIRALM, cell[:, iDP])
            D[:, di, ci, :] = cell * nm[di].T
    if noise:
        D *= NOISE_D
    for eid, kind, a, b, tbl, _, eff in EVENTS:
        if "mult" not in eff:
            continue
        ta, tb = DIDX[max(a, SIM_START)], DIDX[b] + 1
        dsel = [i for i, d in enumerate(DEPOTS) if eff.get("region") in (None, REGION[d])]
        csel = [eff["channel"]] if "channel" in eff else list(range(NC))
        fsel = [eff["sku"]] if "sku" in eff else list(range(NF))
        D[np.ix_(range(ta, tb), dsel, csel, fsel)] *= eff["mult"]
    return D


# ============================================================== simulation
BOM_M = np.zeros((NF, len(INGR)))
for f, comp in BOM.items():
    for ing, s in comp.items():
        BOM_M[SKUS.index(f), INGR.index(ing)] = s * KG_PER_BOTTLE
iPF, iDF, iGU = INGR.index("passionfruit"), INGR.index("dragonfruit"), INGR.index("guava")
NCOH = 14                                         # weekly cohorts kept (98 days > max general-trade age)


def closed(d):
    return any(a <= d <= b for a, b in CLOSURES.values())


def simulate(p, D, D_exp, record=False):
    n = ND * NF
    coh = np.zeros((n, NCOH)); coh_day = np.full((n, NCOH), -10 ** 6)
    sales = np.zeros((NT, ND, NC, NF)); lost = np.zeros_like(sales)
    disc = np.zeros((NT, ND, NF)); woff = np.zeros((NT, ND, NF))
    rec = np.zeros((NT, ND, NF)); xin = np.zeros((NT, ND, NF)); xout = np.zeros((NT, ND, NF))
    onhand = np.zeros((NT, ND, NF)); aged = np.zeros((NT, ND, NF))
    p50, msales, mlost = {}, {}, {}
    pulp = None
    ing_open = np.zeros((NT, len(INGR)))
    cons_hist = []                                     # (t, consumption kg per ingredient for that week)
    import_queue = []                                  # (arrival t, kg, po_id, ingredient)
    po_n = 0
    rows = dict(ing=[], prod=[], po=[], xfer=[], batches=[])
    plan_daily_ing = np.zeros(len(INGR))
    mk_cur = None
    cp_notice_t = None                                # co-packer: notice given at this t (F22: 14 days)
    for t, d in enumerate(DAYS):
        mk = month_key[t]
        # ---------------- month start: the company's OLD forecast (P50) for this month
        if mk != mk_cur:
            if mk_cur is not None:
                sel = month_key[:t] == mk_cur
                msales[mk_cur] = sales[:t][sel].sum(axis=(0, 2)); mlost[mk_cur] = lost[:t][sel].sum(axis=(0, 2))
            mk_cur = mk
            g_plan = GROWTH[min(2026, max(2022, fy_end(d) - 1))]
            ly = msales.get(mk - 12)
            if ly is None:                              # 2023: last year from the noise-free curve, deflated
                sel = (month_key == mk) if (month_key == mk).any() else None
                ly = D_exp[month_key == mk].sum(axis=(0, 2)) / (1 + GROWTH[2023])
            fc = ly * (1 + g_plan) * dim_of(mk) / dim_of(mk - 12)
            fc[:, iDP] = 0.0
            if d >= date(2026, 3, 1):
                prev_dp = msales.get(mk - 1, np.zeros((ND, NF)))[:, iDP].sum()
                if prev_dp > 0:
                    fc[:, iDP] = (msales[mk - 1][:, iDP] + p["lam"] * mlost[mk - 1][:, iDP]) * dim_of(mk) / dim_of(mk - 1)
                else:
                    fc[:, iDP] = DP_PLAN * fc[:, :4].sum(1)
            p50[mk] = fc
            ly2 = msales.get(mk - 11)
            if ly2 is None:
                ly2 = D_exp[month_key == mk + 1].sum(axis=(0, 2)) / (1 + GROWTH[2023]) if (month_key == mk + 1).any() else ly
            fc_next = ly2 * (1 + g_plan) * dim_of(mk + 1) / dim_of(mk - 11)
            fc_next[:, iDP] = fc[:, iDP] * dim_of(mk + 1) / dim_of(mk)
            plan_daily_ing = (fc.sum(0) / dim_of(mk)) @ BOM_M
            if pulp is None:
                tg = np.array([ING_TARGET[i] if ING_TARGET[i] else p["pf_target"] for i in INGR])
                pulp = tg * plan_daily_ing
        # ---------------- Monday: transfers, depot orders, pulp deliveries, production
        if d.weekday() == 0:
            if d.day <= 7 and t > 28:                    # monthly transfers after the month-end report
                pace = sales[t - 28:t].sum(axis=(0, 2)) / 28 + 1e-9
                oh = coh.sum(1).reshape(ND, NF)
                for r in range(4):
                    ds = np.where(reg_idx == r)[0]
                    for f in range(NF):
                        for a in ds:
                            for b in ds:
                                if a == b or oh[a, f] / pace[a, f] <= COVER_HI or oh[b, f] / pace[b, f] >= COVER_LO:
                                    continue
                                give = min(oh[a, f] - 30 * pace[a, f], (21 - oh[b, f] / pace[b, f]) * pace[b, f])
                                if give <= 1000:
                                    continue
                                ia, ib = a * NF + f, b * NF + f
                                take = np.minimum(np.cumsum(coh[ia]), give)          # newest cohorts first (col 0 newest)
                                moved = np.diff(np.concatenate([[0], take]))
                                coh[ia] -= moved
                                coh[ib, 0] += moved.sum()
                                xout[t, a, f] += moved.sum(); xin[t, b, f] += moved.sum()
                                oh[a, f] -= moved.sum(); oh[b, f] += moved.sum()
                                if record:
                                    rows["xfer"].append((d, DEPOTS[a], DEPOTS[b], SKUS[f], moved.sum()))
            rate = p50[mk] / dim_of(mk)
            if d.day > dim_of(mk) - 14:                      # last two weeks: build for next month if it is bigger
                rate = np.maximum(rate, fc_next / dim_of(mk + 1))
            target = rate * (7 + COVER_DAYS)
            # smoothed order-up-to: this week's forecast + half the gap to target (spreads jumps over ~2 weeks)
            order = np.maximum(0, rate * 7 + ORDER_SMOOTH * (target - rate * 7 - coh.sum(1).reshape(ND, NF)))
            need = order.sum(0)
            # ---- pulp deliveries this week
            recent = [c for (tt, c) in cons_hist if t - 14 <= tt < t]
            use_daily = (sum(recent) / 14) if len(recent) == 2 else plan_daily_ing
            plan_prod = need * min(1.0, WEEK_CAP * (1 + CP_SHARE) / max(need.sum(), 1.0))   # requests capped at capacity
            use_daily = np.maximum(use_daily, (plan_prod @ BOM_M) / 7)   # the plant knows this week's plan on Monday
            deliv = np.zeros(len(INGR)); air = 0.0
            for ii, ing in enumerate(INGR):
                tgt = ING_TARGET[ing] if ING_TARGET[ing] else p["pf_target"]
                q = max(0.0, use_daily[ii] * 7 + 0.5 * (tgt * use_daily[ii] - pulp[ii]))
                if ing == "dragonfruit":
                    q *= (1 - IMPORT_SHARE)
                arrive = d + timedelta(3)
                blocked = ing == "passionfruit" and (closed(d) or closed(arrive))
                late = ing == "guava" and GUAVA_DELAY[0] <= d <= GUAVA_DELAY[1]
                q_now = 0.0 if blocked else (0.5 * q if late else q)
                if late:
                    import_queue.append((t + 14, 0.5 * q, "late-guava", iGU))
                deliv[ii] = q_now
                if record and q > 0:
                    po_n += 1
                    rows["po"].append(dict(po_id=f"PO{po_n:05d}", supplier=_supplier(ing, po_n), ingredient=ing, mode="road",
                                           qty_kg=round(q, 1), order_date=d - timedelta(1), promised_date=arrive,
                                           received_date=None if blocked else (arrive + timedelta(14) if late else arrive),
                                           status="not shipped - road closed" if blocked else ("received late (half)" if late else "received"),
                                           cost_multiple=1.0, freight_cost_inr=None))
            if d.month in (1, 4, 7, 10) and d.day <= 7:   # quarterly import, sized from the OLD forecast
                q_imp = plan_daily_ing[iDF] * 91 * IMPORT_SHARE * 1.10
                lead = int(IMPORT_LEADS[(d.year * 4 + d.month) % len(IMPORT_LEADS)]) + (14 if d == IMPORT_DELAY_PO else 0)
                po_n += 1
                import_queue.append((t + lead, q_imp, f"PO{po_n:05d}", iDF))
                if record:
                    rows["po"].append(dict(po_id=f"PO{po_n:05d}", supplier="S_DRAGON_IMP", ingredient="dragonfruit (imported)", mode="sea",
                                           qty_kg=round(q_imp, 1), order_date=d, promised_date=d + timedelta(49),
                                           received_date=d + timedelta(lead) if t + lead < NT else None,
                                           status="received" if t + lead < NT else "in transit", cost_multiple=1.0, freight_cost_inr=None))
            imp_in = 0.0
            for item in list(import_queue):
                if t <= item[0] < t + 7:
                    deliv[item[3]] += item[1]
                    imp_in += item[1] if item[3] == iDF else 0.0
                    import_queue.remove(item)
            if d <= AIR_ARRIVES <= d + timedelta(6):
                air = AIR_DAYS * use_daily[iPF]
                deliv[iPF] += air
                if record:
                    po_n += 1
                    rows["po"].append(dict(po_id=f"PO{po_n:05d}", supplier="S_PASSION", ingredient="passionfruit", mode="air",
                                           qty_kg=round(air, 1), order_date=AIR_BOOKED, promised_date=AIR_ARRIVES, received_date=AIR_ARRIVES,
                                           status="received", cost_multiple=5.0, freight_cost_inr=AIR_COST))
            avail = pulp + deliv
            # ---- production
            prod = need.copy()
            if d.year == 2026 and (closed(d) or closed(d + timedelta(6))):
                prod[iPP] *= (1 - PP_CUT)
            for ii in range(len(INGR)):
                if INGR[ii] not in CONSTRAINED:                # case constrains only these fruits
                    continue
                req = prod * BOM_M[:, ii]
                tot = req.sum()
                if tot <= avail[ii] or tot == 0:
                    continue
                if ii == iPF:                                 # protect Dragon Passion
                    dp_ok = min(req[iDP], avail[ii])
                    prod[iDP] *= dp_ok / req[iDP] if req[iDP] > 0 else 1
                    rest = avail[ii] - dp_ok
                    if req[iPP] > 0:
                        prod[iPP] *= min(1.0, rest / req[iPP])
                else:
                    users = req > 0
                    prod[users] *= avail[ii] / tot
            if need.sum() > WEEK_CAP and cp_notice_t is None:
                cp_notice_t = t                            # orders exceed plants: give the co-packer notice
            elif need.sum() < 0.9 * WEEK_CAP:
                cp_notice_t = None                         # demand eased: release the co-packer
            cap = WEEK_CAP * (1 + CP_SHARE) if (cp_notice_t is not None and t >= cp_notice_t + 14) else WEEK_CAP
            if prod.sum() > cap:
                prod *= cap / prod.sum()
            cp_units = max(0.0, prod.sum() - WEEK_CAP)
            fill = np.where(need > 0, prod / np.maximum(need, 1e-9), 0)
            receive = order * fill[None, :]
            cons = prod @ BOM_M
            for ii, ingn in enumerate(INGR):                  # other pulps: farms/processors top up as needed
                if ingn not in CONSTRAINED and cons[ii] > avail[ii]:
                    deliv[ii] += cons[ii] - avail[ii]; avail[ii] = cons[ii]
            ing_open[t] = pulp
            pulp = avail - cons
            cons_hist.append((t, cons.copy()))
            if record:
                rows["prod"].append((d, need.copy(), prod.copy(), cp_units))
                rows["ing"].append((d, ing_open[t].copy(), deliv.copy(), air, imp_in, cons.copy(), pulp.copy()))
            coh = np.roll(coh, 1, axis=1); coh_day = np.roll(coh_day, 1, axis=1)
            woff[t] += coh[:, 0].reshape(ND, NF)               # anything this old is long expired (normally 0)
            coh[:, 0] = receive.reshape(-1); coh_day[:, 0] = t
            rec[t] = receive
        # ---------------- daily sales (FIFO): MT/QC take stock <= 30 days old, GT takes <= 75 days
        age = t - coh_day
        dem = D[t]
        mtqc = (dem[:, iMT, :] + dem[:, iQC, :]).reshape(-1)
        gt = dem[:, iGT, :].reshape(-1)
        oi = np.argsort(-age, axis=1)
        C = np.take_along_axis(coh, oi, 1); A = np.take_along_axis(age, oi, 1)
        av = C * (A <= MTQC_MAX_AGE); cum = np.cumsum(av, 1)
        tk1 = np.clip(mtqc[:, None] - (cum - av), 0, av); C = C - tk1
        av = C * (A <= p["gtmax"]); cum = np.cumsum(av, 1)
        tk2 = np.clip(gt[:, None] - (cum - av), 0, av); C = C - tk2
        disc[t] += (tk2 * (A > MTQC_MAX_AGE)).sum(1).reshape(ND, NF)
        ex = A > p["gtmax"]
        woff[t] += (C * ex).sum(1).reshape(ND, NF)
        C = C * ~ex
        coh = np.take_along_axis(C, np.argsort(oi, 1), 1)
        s1, s2 = tk1.sum(1), tk2.sum(1)
        mt = dem[:, iMT, :].reshape(-1)
        smt = np.where(mtqc > 0, mt / np.maximum(mtqc, 1e-9), 0)
        sales[t, :, iMT, :] = (s1 * smt).reshape(ND, NF)
        sales[t, :, iQC, :] = (s1 * (1 - smt)).reshape(ND, NF)
        sales[t, :, iGT, :] = s2.reshape(ND, NF)
        lost[t] = dem - sales[t]
        onhand[t] = coh.sum(1).reshape(ND, NF)
        aged[t] = (coh * ((t - coh_day) > MTQC_MAX_AGE)).sum(1).reshape(ND, NF)
        if record and d.weekday() == 6 and d >= OUT_START:
            rows["batches"].append((t, coh.copy(), coh_day.copy()))
    # ---------------- KPIs
    s0, s1_ = DIDX[SUMMER[0]], DIDX[SUMMER[1]] + 1
    a0, a1 = DIDX[TTM[0]], DIDX[TTM[1]] + 1
    S = sales[s0:s1_]
    k = dict(ttm=sales[a0:a1].sum(), summer=S.sum(), flavor=S.sum(axis=(0, 1, 2)) / S.sum(),
             channel=S.sum(axis=(0, 1, 3)) / S.sum(), lost=lost[s0:s1_].sum())
    k["growth"] = sales[a0:a1].sum() / sales[DIDX[date(2024, 7, 1)]:DIDX[date(2025, 6, 30)] + 1].sum() - 1
    k["writeoff_inr"] = disc[s0:, :, [iMPB, iGC]].sum() * PRICE * p["disc"] + woff[s0:, :, [iMPB, iGC]].sum() * UNIT_COST
    tc = DIDX[CLOSURES[2026][0]]
    c28 = sum(c[iPF] for (tt, c) in cons_hist if tc - 28 <= tt < tc) / 28
    k["pf_cover"] = ing_open[tc, iPF] / max(c28, 1e-9)
    errs = []
    for mk_ in range(2025 * 12 + 6, 2026 * 12 + 6):
        a = sales[month_key == mk_].sum(axis=(0, 2)); b = p50[mk_]
        m_ = a > 0
        errs.append(np.abs(a[m_] - b[m_]) / a[m_])
    k["mape"] = float(np.concatenate(errs).mean())
    if record:
        k["detail"] = dict(sales=sales, lost=lost, disc=disc, woff=woff, rec=rec, xin=xin, xout=xout,
                           onhand=onhand, aged=aged, p50=p50, rows=rows)
    return k


def _supplier(ing, n):
    return {"mango": "S_MANGO", "peach": "S_PEACH", "basil": "S_BASIL", "passionfruit": "S_PASSION",
            "dragonfruit": "S_DRAGON_DOM", "guava": "S_GUAVA1" if n % 2 else "S_GUAVA2"}[ing]


def run(p, record=False):
    D_exp = build_demand(p, noise=False)
    D = build_demand(p)
    return simulate(p, D, D_exp, record), D


# ============================================================== calibration
P0 = dict(K=1.0, t0=26.0, slope=2.0, disc=0.25, gtmax=80.0, g26=0.15, m_f=np.ones(NF), m_c=np.ones(NC), lam=0.5, cannib=0.15, pf_target=21.0, sigma_m=0.20)


def score_of(k):
    sh = k["summer"] / k["ttm"]
    e = dict(ttm=k["ttm"] / TARGET["ttm_bottles"] - 1, summer_share=sh - TARGET["summer_share"],
             flavor=float(np.abs(k["flavor"] - TARGET["flavor"]).max()),
             channel=float(np.abs(k["channel"] - TARGET["channel"]).max()),
             lost=k["lost"] / TARGET["lost_bottles"] - 1, writeoff=k["writeoff_inr"] / TARGET["writeoff_inr"] - 1,
             pf_cover=k["pf_cover"] - TARGET["pf_cover_days"], mape=k["mape"] - TARGET["mape"])
    e["growth"] = k["growth"] - 0.15
    tol = dict(growth=0.005, ttm=0.002, summer_share=0.002, flavor=0.002, channel=0.002, lost=0.03, writeoff=0.05, pf_cover=0.25, mape=0.015)
    return sum(abs(e[x]) / tol[x] for x in e), e, all(abs(e[x]) <= tol[x] for x in e)


def calibrate(p, iters=60, verbose=True):
    k, _ = run(p)
    p["K"] *= TARGET["ttm_bottles"] / k["ttm"]
    gain, best, best_s, log = 1.0, copy.deepcopy(p), 1e18, []
    for it in range(iters):
        k, _ = run(p)
        vals = [k["ttm"], k["summer"], k["lost"], k["writeoff_inr"], k["pf_cover"], k["mape"], *k["flavor"]]
        if not np.all(np.isfinite(vals)):
            p, gain = copy.deepcopy(best), gain * 0.5
            continue
        s, e, ok = score_of(k)
        log.append(dict(iter=it, score=round(s, 2), gain=gain, **{x: round(float(v), 5) for x, v in e.items()}))
        if verbose:
            print(f"it {it:2d} score {s:7.1f} g {gain:.2f} | ttm {e['ttm']:+.4f} summer {e['summer_share']:+.4f} "
                  f"flav {e['flavor']:.4f} chan {e['channel']:.4f} lost {e['lost']:+.3f} wo {e['writeoff']:+.3f} "
                  f"pf {k['pf_cover']:.2f} mape {k['mape']:.3f}", flush=True)
        if s < best_s:
            best, best_s = copy.deepcopy(p), s
        elif s > 1.5 * best_s:                       # got worse: go back and take smaller steps
            p, gain = copy.deepcopy(best), gain * 0.6
            continue
        if ok:
            break
        g = gain
        p["K"] *= (TARGET["ttm_bottles"] / k["ttm"]) ** min(1.0, g)
        p["t0"] += 20.0 * g * (TARGET["summer_share"] - k["summer"] / k["ttm"])
        mf = p["m_f"].copy()
        mf *= (TARGET["flavor"] / k["flavor"]) ** (0.7 * g)
        p["m_f"] = mf
        p["m_c"] = p["m_c"] * (TARGET["channel"] / k["channel"]) ** (0.7 * g)
        p["lam"] = float(np.clip(p["lam"] + 0.5 * g * (k["lost"] / TARGET["lost_bottles"] - 1), 0.0, 3.0))
        p["cannib"] = float(np.clip(p["cannib"] * (TARGET["writeoff_inr"] / max(k["writeoff_inr"], 1)) ** (0.4 * g), 0.0, 0.6))
        p["pf_target"] += 0.7 * g * (TARGET["pf_cover_days"] - k["pf_cover"])
        p["sigma_m"] = float(np.clip(p["sigma_m"] * (TARGET["mape"] / k["mape"]) ** (0.7 * g), 0.01, 0.8))
    return best, best_s, log



# ---------------------------------------------------------------- least-squares calibration (all settings at once)
TOL = dict(growth=0.005, ttm=0.002, summer_share=0.002, flavor=0.002, channel=0.002, lost=0.03, writeoff=0.05, pf_cover=0.25, mape=0.015)


def pack(p):
    return np.concatenate([[math.log(p["K"]), p["t0"]], np.log(p["m_f"]), np.log(p["m_c"]),
                           [p["lam"], p["cannib"], p["pf_target"], math.log(p["sigma_m"]), p["slope"], p["disc"], p["g26"]]])


def unpack(x, base):
    p = copy.deepcopy(base)
    p["K"], p["t0"] = math.exp(x[0]), x[1]
    p["m_f"], p["m_c"] = np.exp(x[2:7]), np.exp(x[7:10])
    p["lam"], p["cannib"], p["pf_target"], p["sigma_m"], p["slope"], p["disc"], p["g26"] = x[10], x[11], x[12], math.exp(x[13]), x[14], x[15], x[16]
    return p


def residuals(x, base):
    k, _ = run(unpack(x, base))
    sh = k["summer"] / k["ttm"]
    r = [(k["growth"] - 0.15) / TOL["growth"], (k["ttm"] / TARGET["ttm_bottles"] - 1) / TOL["ttm"], (sh - TARGET["summer_share"]) / TOL["summer_share"]]
    r += list((k["flavor"] - TARGET["flavor"]) / TOL["flavor"]) + list((k["channel"] - TARGET["channel"]) / TOL["channel"])
    r += [(k["lost"] / TARGET["lost_bottles"] - 1) / TOL["lost"], (k["writeoff_inr"] / TARGET["writeoff_inr"] - 1) / TOL["writeoff"],
          (k["pf_cover"] - TARGET["pf_cover_days"]) / TOL["pf_cover"], (k["mape"] - TARGET["mape"]) / TOL["mape"]]
    r = np.nan_to_num(np.array(r), nan=1e4, posinf=1e4, neginf=-1e4)
    print(f"  eval: max|r| {np.abs(r).max():7.2f}  lost {k['lost']/TARGET['lost_bottles']-1:+.3f}  summer {sh:.4f}", flush=True)
    return r


def solve(p_start):
    from scipy.optimize import least_squares
    x0 = pack(p_start)
    lo = np.array([-np.inf, 18, *[-1.5] * 5, *[-1.0] * 3, 0.0, 0.0, 3.0, math.log(0.01), 0.8, 0.05, -0.05])
    hi = np.array([np.inf, 34, *[1.5] * 5, *[1.0] * 3, 2.0, 0.9, 40.0, math.log(0.8), 5.0, 0.45, 0.30])
    x0 = np.clip(x0, lo + 1e-6, hi - 1e-6)
    res = least_squares(residuals, x0, args=(p_start,), bounds=(lo, hi), diff_step=0.03, x_scale="jac", max_nfev=int(os.environ.get("NFEV", "500")))
    return unpack(res.x, p_start), res


# ---------------------------------------------------------------- one-control-per-target calibration (robust)
FIXED = dict(slope=1.5, cannib=0.08, lam=0.75, gtmax=80.0)        # kept at realistic values, not calibrated


def _metric(k, name):
    return {"mape": k["mape"], "lost": k["lost"] / TARGET["lost_bottles"] - 1,
            "writeoff": k["writeoff_inr"] / TARGET["writeoff_inr"] - 1, "pf": k["pf_cover"] - TARGET["pf_cover_days"],
            "summer": k["summer"] / k["ttm"] - TARGET["summer_share"], "dpshare": k["flavor"][iDP] - TARGET["flavor"][iDP]}[name]


def _solve1(p, key, name, target, lo, hi, tol, max_eval=12):
    """Bracket the root of (metric - target) in [lo, hi], then bisect. Robust to a bumpy simulation."""
    cache = {}
    def f(x):
        if x not in cache:
            q = dict(p); q[key] = x
            cache[x] = _metric(run(q)[0], name) - target
        return cache[x]
    x = float(np.clip(p[key], lo, hi))
    fx = f(x)
    if abs(fx) <= tol:
        return x
    step = max(abs(x) * 0.1, (hi - lo) * 0.02)
    a, fa = x, fx
    for _ in range(6):                                   # walk outwards until the sign changes
        for b in (min(hi, a + step), max(lo, a - step)):
            fb = f(b)
            if np.sign(fb) != np.sign(fx):
                lo_, hi_ = sorted([x, b])
                flo = f(lo_)
                for _ in range(max_eval):
                    m = (lo_ + hi_) / 2; fm = f(m)
                    if abs(fm) <= tol:
                        return m
                    if np.sign(fm) == np.sign(flo):
                        lo_, flo = m, fm
                    else:
                        hi_ = m
                return (lo_ + hi_) / 2
        step *= 2
    return min(cache, key=lambda z: abs(cache[z]))      # no sign change found: best point seen


def gs_calibrate(p, loops=10):
    p = dict(p, **FIXED)
    best, best_s = dict(p), float("inf")
    for it in range(loops):
        k, _ = run(p)
        p["K"] *= TARGET["ttm_bottles"] / k["ttm"]
        p["t0"] = _solve1(p, "t0", "summer", 0.0, 18.0, 34.0, 0.0007)
        p["sigma_m"] = _solve1(p, "sigma_m", "mape", 0.0 + TARGET["mape"], 0.05, 0.6, 0.004)
        p["flex"] = _solve1(p, "flex", "dpshare", 0.0, 0.1, 3.0, 0.0008)
        p["dp_demand"] = _solve1(p, "dp_demand", "lost", 0.0, 0.2, 8.0, 0.01)
        p["disc"] = _solve1(p, "disc", "writeoff", 0.0, 0.03, 0.45, 0.02)
        p["pf_target"] = _solve1(p, "pf_target", "pf", 0.0, 3.0, 40.0, 0.1)
        for _ in range(3):                                   # mix fixed points
            k, _ = run(p)
            p["K"] *= TARGET["ttm_bottles"] / k["ttm"]
            mf = p["m_f"] * np.clip(TARGET["flavor"] / np.maximum(k["flavor"], 1e-4), 0.7, 1.4)
            mf[iDP] = p["m_f"][iDP]                          # DP sales come from supply (flex), not this multiplier
            p["m_f"] = mf
            p["m_c"] = p["m_c"] * np.clip(TARGET["channel"] / np.maximum(k["channel"], 1e-4), 0.7, 1.4)
        s, e, ok = score_of(run(p)[0])
        if not np.isfinite(s):
            print(f"loop {it}: non-finite, back to best", flush=True)
            p = dict(best); continue
        if s < best_s:
            best, best_s = dict(p), s
        print(f"loop {it}: score {s:.2f} ok {ok} | " + " ".join(f"{x} {v:+.4f}" for x, v in e.items()), flush=True)
        if ok:
            break
    return best

if __name__ == "__main__":
    if os.environ.get("WARM") and (HID / "calibrated_settings.json").exists():
        p = {x: (np.array(v) if isinstance(v, list) else v) for x, v in json.load(open(HID / "calibrated_settings.json")).items()}
        print("warm start")
    else:
        p = copy.deepcopy(P0)
        p, best_s, log = calibrate(p, iters=int(os.environ.get("CAL_ITERS", "25")), verbose=False)
        print("rough start score", round(best_s, 1))
    for rnd in range(int(os.environ.get("ROUNDS", "3"))):
        p, res = solve(p)
        s, e, ok = score_of(run(p)[0])
        print(f"round {rnd}: score {s:.2f}  ok {ok}", flush=True)
        json.dump({x: (v.tolist() if isinstance(v, np.ndarray) else v) for x, v in p.items()},
                  open(HID / "calibrated_settings.json", "w"), indent=2)
        if ok:
            break
    print(f"\nfinal score {s:.2f}  all within tolerance: {ok}")
    print({x: round(float(v), 4) for x, v in e.items()})
