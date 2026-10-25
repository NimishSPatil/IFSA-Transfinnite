"""
trace_facts.py  -  follows three case facts through every layer and checks nothing changed.

    python code/trace_facts.py

Layers: Case_Facts.csv -> nodes/edges CSV -> SQLite -> NetworkX graph -> the drawn SVG text.
"""
import sqlite3
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
con = sqlite3.connect(ROOT / "pulp_riot.db")
svg = (ROOT / "diagrams" / "supply_network.svg").read_text(encoding="utf-8")
facts = pd.read_csv(DATA / "Case_Facts.csv", encoding="utf-8-sig").set_index("fact_id")
edges = pd.read_csv(DATA / "edges.csv", encoding="utf-8-sig")
G = nx.MultiDiGraph()
for r in edges.to_dict("records"):
    G.add_edge(r["from_node"], r["to_node"], key=r["edge_id"], **r)

ok = True
def show(layer, value, expect):
    global ok
    good = str(value) == str(expect)
    ok &= good
    print(f"  {'OK ' if good else 'BAD'} {layer:12} {value}")

print("Fact F40: passionfruit pulp reaches plants by road in 3 days")
show("case fact", facts.loc["F40", "value"], 3)
row = edges[(edges.from_node == "S_PASSION") & (edges.to_node == "P1") & (edges["mode"] == "road")].iloc[0]
show("edges.csv", int(row.lead_time_days_min), 3)
show("SQLite", con.execute("SELECT lead_time_days_max FROM edges WHERE from_node='S_PASSION' AND to_node='P1' AND mode='road'").fetchone()[0], 3.0)
show("graph", G["S_PASSION"]["P1"]["E001"]["lead_time_days_max"], 3.0)
show("diagram", "road · 3 days" in svg, True)

print("Fact F38/F39: 90-day shelf life, retailers reject under 60 days")
show("case fact", f"{facts.loc['F38', 'value']}/{facts.loc['F39', 'value']}", "90/60")
show("products.csv", int(pd.read_csv(DATA / "products.csv").shelf_life_days.unique()[0]), 90)
show("SQLite", con.execute("SELECT MIN(min_shelf_life_days) FROM channels").fetchone()[0], 60.0)
show("risk flag", "has only 9 days of margin" in con.execute("SELECT reason FROM risk_flags WHERE risk_type='shelf_life_margin'").fetchone()[0], True)
show("diagram", "rejects &lt; 60 days left" in svg, True)

print("Fact F49/F50: depot transfer 2-4 days, INR 1.50 per bottle")
show("case fact", f"{facts.loc['F49', 'value']}/{facts.loc['F50', 'value']}", "2-4/1.50")
tr = edges[edges.flow_type == "transfer"]
show("edges.csv", f"{tr.lead_time_days_min.unique()[0]:.0f}-{tr.lead_time_days_max.unique()[0]:.0f}/{tr.cost_per_unit.unique()[0]:.2f}", "2-4/1.50")
show("SQLite", con.execute("SELECT MIN(cost_per_unit), COUNT(*) FROM edges WHERE flow_type='transfer'").fetchone(), (1.5, 72))
e0 = tr.iloc[0]
show("graph",G[e0.from_node][e0.to_node][e0.edge_id]["cost_per_unit"], 1.5)
show("diagram", "2-4 days  ·  about INR 1.50 per bottle" in svg, True)
print("\nALL TRACES MATCH" if ok else "\nMISMATCH FOUND")
