"""
readme.py - the READ_ME panel: everything a planner should look at, auto-populated, in three time buckets.

    Immediate  impact within 7 days, happening now, or a control that departs from the case
    Soon       impact within 28 days
    Later      beyond 28 days, structural exposures, data gaps and the prompt-2 (Inventory) items
Sources: risk engine, mitigation and co-packer decisions, transport flags, demand alerts, the simulated social
desk, the control panel, data-quality checks and a fixed list of known data issues.
"""
from datetime import timedelta
from functools import lru_cache

import numpy as np

from ..data import store
from . import forecast as F
from . import reviews
from .copacker import evaluate as copacker
from .risks import evaluate as risks
from .social import desk
from .supply import guava_ladder, mitigations
from .transport import fragility, mitigation as tr_mitigation
from . import inventory as INV

ORDER = {"Immediate": 0, "Soon": 1, "Later": 2}
SEV = {"High": 0, "Medium": 1, "Low": 2}

KNOWN_ISSUES = [
    ("Finished-goods lag looks short in the sample",
     "PP depot stock drains within about 2 weeks of the PP production cut (week of 11 May) because depot cover going into "
     "the closure was only ~11 days. The Supply → Inventory lag is shorter than a real 21-day depot cover would give; "
     "the lag is a control (g08) on Supply ↔ Inventory.", "Inventory (prompt 2)", "/link"),
    ("Dragon Passion launched with a 3% depot allocation against ~12% demand",
     "DP is out of stock at most depots by 9 March, before the viral reel. This is a cover-rule root cause (G21, F46), "
     "separate from the spike and the highway. The teammate's static P50 inherits it (see Forecast source).", "Inventory (prompt 2)", "/link"),
    ("Quick-commerce daily feed has sell-through only",
     "No retailer order series, so the pantry-loading test (orders rising faster than sell-through) cannot run on daily "
     "data (spec 4.2).", "Data", "/forecast"),
    ("Recipe and kilograms are assumptions",
     "0.06 kg per bottle and the MPB / DP mixes are sample assumptions (G05, G06). Every kg figure is Assumed.", "Data", "/controls"),
    ("v1 network tables are older than dataset v2",
     "data/*.csv (v1) still carries the old BOM blanks and a 25 May forced depot zero; the dashboard reads v2 only.", "Data", "/data"),
    ("Plant pulp is pooled across the two plants",
     "The material balance pools P1 and P2 (A41): the case does not say which plant makes which flavor (G01).", "Data", "/risk"),
]


def _item(bucket, sev, title, detail, source, owner, link, group, status="Open", rid=None, simulated=False):
    return dict(bucket=bucket, severity=sev, title=title, detail=detail, source=source, owner=owner, link=link,
                group=group, status=status, rec_id=rid, simulated=simulated)


def _rec_item(rec, bucket, sev, group, link):
    st = reviews.status_of(rec["id"])
    return _item(bucket, sev, f"Decision needed: {rec['title']}", rec["detail"], f"{rec['module']} engine · review candidate",
                 rec["owner"], link, group, status=st, rid=rec["id"])


def items(w, ctl):
    """READ_ME rows with the CURRENT review status (decisions are not cached)."""
    lt = reviews.latest()
    rows = [dict(x) for x in _items(w, ctl)]
    for x in rows:
        if x["rec_id"]:
            d = lt.get(x["rec_id"])
            x["status"] = d["status"] if d else "Pending"
    # transfer recommendations waiting for the supply chain manager (Mar-Jun 2026 window)
    _, t = INV.frame(ctl)
    t = t[INV.in_window(t.ws, "summer26")]
    pend = [i for i in t.id if i not in lt]
    if pend:
        rows.append(_item("Soon", "Medium", f"Decision needed: {len(pend)} of {len(t)} transfer recommendations (Mar–Jun 2026) not reviewed",
                          "Each is a review candidate for the supply chain manager; approving records the decision and moves nothing.",
                          "Inventory module · transfers", "Supply chain manager", "/rebalance#transfers", "Inventory (prompt 2)"))
        rows.sort(key=lambda x: (ORDER[x["bucket"]], SEV[x["severity"]]))
    return rows


@lru_cache(maxsize=64)
def _items(w, ctl):
    s = store()
    K = w + timedelta(7)
    out = []

    # 1. control departures (acceptance: moving a Given value adds a READ_ME entry)
    for c in ctl.departures():
        out.append(_item("Immediate", "Medium", f"Departs from case: {c['label']} = {c['value']} {c['unit']}",
                         f"The {'case' if c['src'] == 'Given' else 'case / file'} value is {c['default']} {c['unit']} ({c['ref']}). Every output on this dashboard now "
                         "uses the changed value.", "Control panel · " + c["id"].upper(), "Planning", "/controls#" + c["id"], "Controls"))
    for k, v in ctl.changed().items():
        from .controls import BY_ID
        c = BY_ID[k]
        if c["src"] != "Given" and not c["anchor"]:
            out.append(_item("Later", "Low", f"Assumption changed: {c['label']} = {v} {c['unit']}",
                             f"Default {c['default']} ({c['src']}, {c['ref']}).", "Control panel · " + k.upper(), "Planning",
                             "/controls#" + k, "Controls"))

    # 2. risk engine
    for r in risks(w, ctl):
        if r["status"] in ("Clear",):
            continue
        if r["status"] == "Not evaluable":
            out.append(_item("Later", "Low", f"{r['id']} {r['name']}: not evaluable", r["evidence"], f"Risk register · {r['id']}",
                             r["owner"], r["link"], "Supply"))
            continue
        bucket = r["bucket"] if r["status"] != "Structural" else "Later"
        gap = f" Lead-time gap {r['gap']:+.0f} days ({r['lever']['name']})." if r["gap"] is not None and r["lever"] else ""
        out.append(_item(bucket, r["severity"], f"{r['id']} {r['name']}", r["evidence"] + gap, f"Risk register · {r['id']} · {r['status']}",
                         r["owner"], r["link"], "Supply"))

    # 3. decisions
    m = mitigations(w, ctl)
    if m["rec"]:
        days = (m["first_out"] - K).days if m["first_out"] else None
        out.append(_rec_item(m["rec"], "Immediate" if days is not None and days <= 7 else "Soon", "High", "Supply", "/risk#options"))
    gl = guava_ladder(w, ctl)
    if gl["rec"]:
        out.append(_rec_item(gl["rec"], "Immediate", "High", "Supply", "/risk#ladder"))
    cp = copacker(w, ctl)
    if cp["rec"]:
        out.append(_rec_item(cp["rec"], "Soon", "Medium", "Supply", "/copacker"))
    elif cp["checks"][0]["ok"]:
        out.append(_item("Soon", "Medium", "Co-packer: demand above plant capacity but not eligible",
                         " ".join(cp["reasons"]), "Co-packer rule", "Production", "/copacker", "Supply"))
    tm = tr_mitigation(w, ctl)
    fr = fragility(w, ctl)
    for f in fr["flags"]:
        out.append(_item("Immediate" if f["sev"] == "High" else "Soon", f["sev"], "Transport: " + f["text"], f"Reference {f['ref']}.",
                         "Transport flags", "Logistics", "/transportation#fragility", "Transport"))
    if tm["rec"] and fr["in_season"]:
        out.append(_rec_item(tm["rec"], "Soon", "Medium", "Transport", "/transportation#fragility"))

    # 4. demand alerts
    for a in F.alerts(w, ctl):
        if not a["active"]:
            continue
        out.append(_item("Immediate", "High" if a["ratio"] >= 2 else "Medium",
                         f"Demand alert: {a['sku']} quick commerce {a['ratio']:.1f}x baseline ({a['cls']})",
                         f"Since {a['start']:%d %b}. " + "; ".join(a["evidence"][:2]), "Forecast · daily detector", "Planning",
                         "/forecast", "Demand", status=reviews.status_of(a["id"]), rid=a["id"]))

    # 5. social desk (simulated)
    for c in desk(w, ctl)["alerts"]:
        out.append(_item("Soon" if not c["confirmed"] else "Immediate", "Medium" if c["confirmed"] else "Low",
                         f"Social (simulated): {c['sku']} {c['cls'].lower()}", f"{c['verdict']}. Action: {c['action']}.",
                         "Social signal desk · simulated feed", "Marketing", "/social", "Social (simulated)",
                         status=reviews.status_of(c["id"]), rid=c["id"], simulated=True))

    # 6. data quality to date + known issues
    miss = s.inv[(~s.inv.report_received) & (s.inv.week_start <= w)].groupby(["week_start", "depot_id"]).size().reset_index()
    for r in miss.tail(3).itertuples():
        out.append(_item("Later", "Low", f"Depot report missing: {r.depot_id}, week of {r.week_start:%d %b %Y}",
                         "Excluded from totals; not imputed.", "Data check", "Planning", "/data", "Data"))
    s._inv_extra()
    br = s.ledger_breaks[s.ledger_breaks.week_start <= w]
    for r in br.tail(3).itertuples():
        out.append(_item("Later", "Medium", f"Stock ledger break: {r.depot_id} {r.sku_id}, week of {r.week_start:%d %b %Y}",
                         f"Closing {r.closing_stock:,.0f} is {-r.ledger_gap:,.0f} more than opening + receipts − sales allows. "
                         "Shown, not corrected.", "Data check", "Planning", "/data", "Data"))
    for b in qc_blips(w):
        out.append(_item("Later", "Low", f"Quick-commerce reading looks wrong: {b['depot']} {b['sku']} on {b['date']:%d %b %Y}",
                         f"{b['x']:,.0f} bottles vs a typical {b['med']:,.0f} around it ({b['x'] / b['med']:.1f}x) for one day only.",
                         "Data check", "Planning", "/forecast", "Data"))
    for t, d, g, link in KNOWN_ISSUES:
        out.append(_item("Later", "Medium" if g.startswith("Inventory") else "Low", t, d, "Known data issue", "Planning", link, g))

    # 7. inventory module (prompt 2): data issues, questions for the teammate, forecast-source differences
    for x in INV.readme_items(ctl):
        out.append(_item(x["bucket"], x["severity"], x["title"], x["detail"], x["source"], x["owner"], x["link"], x["group"]))
    fc = INV.forecast_compare("summer26", ctl)
    if fc["big"]:
        worst = sorted([r for r in fc["by_sku"] if r["diff"] is not None], key=lambda r: -abs(r["diff"]))
        out.append(_item("Soon", "Medium", f"Forecast sources differ by more than {ctl['f29']:.0%} in {len(fc['big'])} flavor-weeks (summer 2026)",
                         "Summer totals, dashboard vs file: " + "; ".join(f"{r['sku']} {r['diff']:+.0%}" for r in worst[:3]) +
                         ". The file's static P50 inherits the 3% DP launch allocation.", "Forecast source", "Planning", "/fcsource",
                         "Inventory (prompt 2)"))

    out.sort(key=lambda x: (ORDER[x["bucket"]], SEV[x["severity"]]))
    for i, x in enumerate(out):
        x["n"] = i + 1
    return out


PROMPT2_ITEMS = [
    ("Inventory module: coming in prompt 2", "Depot-level cover, allocation by cover gap, transfers and ageing. Supply hands over "
     "through engine/inventory_iface.py (fg_position, supply_to_fg) and forecast.depot_forecast."),
    ("Depot forecast hook is ready", "forecast.depot_forecast(w, ctl, weeks) gives depot x flavor P50 and the finished-goods "
     "percentile, with shrinkage shares and the DP prior."),
    ("Depot transfers stay review candidates", "2-4 days, ₹1.50 a bottle (F49, F50), MT/QC 60-day rule; no 'optimised transfer' "
     "label without route costs."),
]


@lru_cache(maxsize=64)
def qc_blips(w):
    """One-day readings far above the depot's own surrounding days (likely data errors)."""
    s = store()
    q = s.qc[s.qc.date <= w + timedelta(6)]
    out = []
    for (d, sku), g in q.groupby(["depot_id", "sku_id"]):
        g = g.set_index("date")
        x = g.units_sold.astype(float).where(g.out_of_stock == 0)           # stock-out days are not readings
        med = x.rolling(15, center=True, min_periods=5).median()
        r = x / med.replace(0, np.nan)
        nb = (r.shift(1) < 1.6) & (r.shift(-1) < 1.6)                     # neighbours in stock and normal
        for day in r[(r > 2.5) & nb & (med > 200)].index:
            out.append(dict(depot=d, sku=sku, date=day, x=float(x[day]), med=float(med[day])))
    return sorted(out, key=lambda b: b["date"])[-3:]


def counts(rows):
    c = {"Immediate": 0, "Soon": 0, "Later": 0}
    for r in rows:
        c[r["bucket"]] += 1
    return c
