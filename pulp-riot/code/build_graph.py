"""
build_graph.py  -  turns nodes + edges into a NetworkX graph, validates it, and writes risk flags.

    python code/build_graph.py

Terms: a NODE is a box (supplier, plant, depot...). An EDGE is an arrow between two nodes; every
arrow in the final diagram is one row of edges.csv.  NetworkX is a Python library for graphs.
We use a MultiDiGraph: directed (arrows have a direction) and "multi" so two arrows may join the
same pair of nodes (the passionfruit road AND the air-freight contingency).

Reads  : data/nodes.csv, edges.csv, bom.csv, events.csv, inventory_snapshot.csv, products.csv
Writes : data/risk_flags.csv  (and a risk_flags table in pulp_riot.db if it exists)

Every flag cites the case fact it comes from, so a judge can follow it back.  Severity rules:
  high    a case-stated constraint left no alternative, AND it already failed last summer
  medium  a stated or derived gap that slowed the response
  low     a margin that is thin but did not fail on its own
Recommended actions are suggestions only; a human stakeholder approves every one (F71).
"""
import sqlite3
from datetime import date
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

nodes = pd.read_csv(DATA / "nodes.csv", encoding="utf-8-sig")
edges = pd.read_csv(DATA / "edges.csv", encoding="utf-8-sig")
bom = pd.read_csv(DATA / "bom.csv", encoding="utf-8-sig")
events = pd.read_csv(DATA / "events.csv", encoding="utf-8-sig").set_index("event_id")
inv = pd.read_csv(DATA / "inventory_snapshot.csv", encoding="utf-8-sig")
products = pd.read_csv(DATA / "products.csv", encoding="utf-8-sig").set_index("flavor_id")

# ------------------------------------------------------------------ build the graph
G = nx.MultiDiGraph()
for r in nodes.to_dict("records"):
    G.add_node(r["node_id"], **r)
for r in edges.to_dict("records"):
    G.add_edge(r["from_node"], r["to_node"], key=r["edge_id"], **r)
print(f"graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")


def layer(flow, include_contingency=True):
    """A copy of the graph holding only one kind of arrow (goods / transfer / information)."""
    H = nx.MultiDiGraph()
    H.add_nodes_from(G.nodes(data=True))
    for u, v, k, d in G.edges(keys=True, data=True):
        if d["flow_type"] == flow and (include_contingency or d["mode"] != "air"):
            H.add_edge(u, v, key=k, **d)
    return H


goods = layer("goods")
goods_normal = layer("goods", include_contingency=False)
info = layer("information")

# ------------------------------------------------------------------ validation
problems = []
type_of = nx.get_node_attributes(G, "type")
plants = [n for n, t in type_of.items() if t in ("plant", "copacker")]
suppliers = [n for n, t in type_of.items() if t == "supplier"]
depots = [n for n, t in type_of.items() if t == "depot"]
for d in depots:
    if not any(nx.has_path(goods, p, d) for p in plants):
        problems.append(f"depot {d} cannot be reached from any plant or co-packer")
for p in [n for n, t in type_of.items() if t == "plant"]:
    if not any(nx.has_path(goods, s, p) for s in suppliers):
        problems.append(f"plant {p} cannot be reached from any supplier")
for n in G.nodes:
    if G.degree(n) == 0:
        problems.append(f"node {n} is isolated")
print("validation:", "OK - every depot reachable from a plant, every plant from a supplier, no isolated nodes"
      if not problems else problems)

# ------------------------------------------------------------------ risk flags
flags = []


def flag(where, rtype, sev, reason, action, check, facts, when=""):
    flags.append((f"RF{len(flags) + 1:02d}", when, where, rtype, sev, reason, action,
                  "pending - human approval required", check, facts))


closure_days = 21  # F55 states three weeks; use the case figure, not the date difference

# 1. Single points of failure -------------------------------------------------
for n, d in G.nodes(data=True):
    if d.get("single_source") == "Y":
        alts = [(u, v) for u, v, dd in goods_normal.out_edges(n, data=True) if dd["alternative_route_exists"] == "Y"]
        flows = sorted({b for b in bom.loc[bom.source_node.str.contains(n), "flavor_id"]})
        share = products.loc[flows, "summer_share"].sum()
        flag(n, "single_point_of_failure", "high",
             f"{d['name']} is the only passionfruit source (no second supplier qualified) and "
             f"feeds {', '.join(flows)} = {share:.0%} of summer volume.",
             "Qualify a second passionfruit source before next summer; decide a safety-stock level in days, not weeks.",
             "single_source flag on node + BOM fan-out", "F35;F77;F78")
for u, v, k, dd in goods_normal.edges(keys=True, data=True):
    if dd["alternative_route_exists"] == "N":
        flag(f"{u}->{v} ({k})", "single_point_of_failure", "high",
             f"Road is the only route ({dd['lead_time_days_min']:.0f} days) and has closed for at least a week in "
             f"3 of the last 5 summers.",
             "Treat a closure as likely, not rare: pre-position pulp ahead of peak and pre-agree the air-freight trigger.",
             "alternative_route_exists = N", "F40;F41;F42")

# 2. Longest-lead inbound path per flavor -------------------------------------
lead_by_source = {}
for u, v, dd in goods_normal.edges(data=True):
    if type_of.get(u) == "supplier" and pd.notna(dd["lead_time_days_max"]):
        lead_by_source[u] = max(lead_by_source.get(u, 0), dd["lead_time_days_max"])
long_lead = {}   # supplier -> flavors that depend on it (one flag per supplier, not per flavor)
for fl, grp in bom.groupby("flavor_id"):
    for src in grp.source_node:
        for s in str(src).split(";"):
            if lead_by_source.get(s, 0) >= 28:
                long_lead.setdefault(s, []).append(fl)
for s, fls in long_lead.items():
    days = lead_by_source[s]
    notice = float(edges[(edges.from_node == "X_MKT") & (edges.to_node == "X_PROC")].lead_time_days_min.iloc[0])
    flag(s, "long_lead_time", "high" if days >= 42 else "low",
         f"{nodes.set_index('node_id').loc[s, 'name']} has a {days:.0f}-day maximum lead and is ordered once a quarter; it "
         f"feeds {' and '.join(sorted(fls))}. Marketing's launch notice to procurement was {notice:.0f} days, shorter than this lead. "
         f"(Dragon Passion's domestic/imported split is not stated, G05.)",
         "Give procurement a launch calendar at least one full lead time ahead; size each quarterly order from the forecast.",
         "max lead_time_days_max over supplier->plant goods edges, per BOM", "F16;F17;F36")

# 3. Shared ingredients --------------------------------------------------------
for src, grp in bom.assign(src=bom.source_node.str.split(";")).explode("src").groupby("src"):
    flavors = sorted(set(grp.flavor_id))
    if len(flavors) > 1 and src in nodes.node_id.values:
        share = products.loc[flavors, "summer_share"].sum()
        both = {"S_PASSION": ("high", "F78;F58;F59",
                              "Last May the shortage forced a trade-off: Passionfruit Punch production was cut to protect Dragon Passion, and both ran out.",
                              "Set a pre-agreed allocation rule between these flavors, decided before the shortage and approved by the COO."),
                "S_DRAGON_IMP": ("medium", "F78;F15", "Dragonfruit Bloom and Dragon Passion draw on the same imported order.", "Plan the quarterly import against the combined forecast of both flavors."),
                "S_DRAGON_DOM": ("low", "F78;F14", "Dragonfruit Bloom and Dragon Passion share the domestic supply.", "Track domestic dragonfruit cover across both flavors."),
                }.get(src)
        if both:
            sev, facts, why, act = both
            flag(src, "shared_ingredient", sev,
                 f"{nodes.set_index('node_id').loc[src, 'name']} feeds {' and '.join(flavors)} ({share:.0%} of summer volume). {why}",
                 act, "BOM: one source node used by more than one flavor", facts)

# 4. Information lag -----------------------------------------------------------
sig = edges[(edges.from_node == "C_QC") & (edges.to_node == "X_MKT")].iloc[0]
late = edges[(edges.from_node == "C_QC") & (edges.to_node == "X_PLAN")].iloc[0]
mkt_to_plan = info.has_edge("X_MKT", "X_PLAN")
path_ok = nx.has_path(info, "X_MKT", "X_PLAN")
flag("C_QC->X_MKT vs C_QC->X_PLAN", "information_lag", "high",
     f"The quick-commerce signal reaches Marketing in {sig.reporting_lag_days:.0f} day but reaches Planning up to "
     f"{late.reporting_lag_days:.0f} days later (month-end). Information path Marketing -> Planning exists: {path_ok}.",
     "Route the daily quick-commerce sell-through to Planning and set a threshold that triggers an alert.",
     "info-layer edge lags + path search", "F29;F30;F54")
flag("X_MKT->X_PROC", "information_lag", "medium",
     "Procurement heard of the Dragon Passion launch 2 weeks ahead; the co-packer needs 2 weeks' notice and imported "
     "dragonfruit takes 6-8 weeks.",
     "Share the launch calendar with Procurement and Planning together, 8+ weeks ahead.",
     "edge X_MKT->X_PROC lead time vs supplier lead times", "F36;F16;F22")
for d in depots[:1]:  # one representative flag; the weekly spreadsheet applies to all depots
    w = edges[(edges.from_node == d) & (edges.to_node == "X_PLAN")].iloc[0]
    flag("depots -> X_PLAN (9 edges)", "information_lag", "medium",
         f"Each depot reports stock weekly in its own spreadsheet (up to {w.reporting_lag_days:.0f} days old); "
         "allocations reset monthly. Imbalances between regions can build for weeks before anyone sees them.",
         "Standardise one weekly stock template first, then move to daily for fast-moving flavors.",
         "info-layer edge frequency", "F47;F48;F60")

# Decision latency: when could extra volume have arrived? -----------------------
viral = date.fromisoformat(events.loc["EV2", "date"])
seen = date.fromisoformat(events.loc["EV4", "date"])
notice = 14
flag("X_PLAN->CP", "decision_latency", "medium",
     f"Viral spike began {viral:%d %b}. Planners saw consolidated data {seen:%d %b}; the co-packer then needs "
     f"{notice} days' notice, so extra volume arrives no earlier than {(seen - viral).days + notice} days after the spike "
     f"began. With the daily signal (1 day) it could arrive after {1 + notice} days. Co-packer ceiling is 10% of plant volume.",
     "Pre-agree a trigger for calling the co-packer on a daily sell-through threshold.",
     "event dates + edge X_PLAN->CP notice", "F22;F29;F30;F52;F53;F20", when=str(viral))

# 5. Cover vs disruption -------------------------------------------------------
for p in ("P1", "P2"):
    cover = nodes.set_index("node_id").loc[p, "pulp_on_hand_days"]
    if cover < closure_days:
        flag(p, "cover_below_disruption", "high",
             f"Passionfruit pulp cover was {cover:.0f} days when the closure began; the closure lasted {closure_days} days "
             f"({closure_days - cover:.0f} days uncovered).",
             "Hold passionfruit pulp cover above the closure length seen in recent summers "
             "(frozen pulp keeps up to 6 months), and review it monthly during peak.",
             "pulp_on_hand_days < closure length", "F43;F55;F37", when=events.loc["EV5", "date"])

# 6. Inventory: depot cover policy vs the new flavor, and shelf-life margin ----
dep = inv[inv.node_id.str.startswith("D_")]
for fl, g in dep.groupby("flavor_id"):
    out = (g.stock_status == "stock-out").sum()
    if out:
        flag(f"depots x {fl}", "inventory_stock_out", "high" if out / len(g) > 0.3 else "medium",
             f"{fl}: {out} of {len(g)} depot-weeks at zero stock in the sample data. Depot cover is set from the previous "
             f"year's flavor mix, which had no room for a new flavor.",
             "Set depot cover for a new flavor from a launch forecast, and review it weekly in the first weeks.",
             "inventory_snapshot.stock_status = stock-out", "F45;F46;F59")
margin = float(products.loc["MPB", "shelf_life_days"]) - 60 - 21
flag("depots -> C_MT / C_QC", "shelf_life_margin", "low",
     f"Modern trade and quick commerce reject stock with under 60 days left; a 90-day bottle that waits 21 days at a depot "
     f"has only {margin:.0f} days of margin before it becomes unsellable there. Overstock does not stay saleable.",
     "Rebalance by depot transfers (2-4 days, about INR 1.50 a bottle) before stock ages, instead of discounting later.",
     "shelf life - retailer cutoff - depot cover", "F38;F39;F45;F49;F50;F60")

risk = pd.DataFrame(flags, columns=["flag_id", "date", "node_or_edge", "risk_type", "severity", "reason",
                                    "recommended_action", "approver", "check", "case_fact_id"])
risk.to_csv(DATA / "risk_flags.csv", index=False, encoding="utf-8-sig")
db = ROOT / "pulp_riot.db"
if db.exists():
    con = sqlite3.connect(db)
    risk.to_sql("risk_flags", con, index=False, if_exists="replace")
    con.close()
print(f"\n{len(risk)} risk flags -> data/risk_flags.csv")
print(risk[["flag_id", "node_or_edge", "risk_type", "severity"]].to_string(index=False))

# summary figures the diagram and README reuse
print("\nSingle-source nodes   :", [n for n, d in G.nodes(data=True) if d.get("single_source") == "Y"])
print("Edges with no alternative (normal goods):",
      [k for u, v, k, d in goods_normal.edges(keys=True, data=True) if d["alternative_route_exists"] == "N"])
