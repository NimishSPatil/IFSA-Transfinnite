"""
load_db.py  -  loads every CSV in /data into one SQLite file (pulp_riot.db) and runs sanity SQL.

    python code/load_db.py

SQLite = a whole database in a single file, no server, free; real SQL; can move to Postgres later.
Each CSV becomes one table with the same name.  Re-running rebuilds the file from the CSVs, so the
CSVs stay the source of truth.  Exits with a non-zero code if any check fails.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA, DB = ROOT / "data", ROOT / "pulp_riot.db"

if DB.exists():
    DB.unlink()
con = sqlite3.connect(DB)
for csv in sorted(DATA.glob("*.csv")):
    df = pd.read_csv(csv, encoding="utf-8-sig")
    df.to_sql(csv.stem, con, index=False)
    print(f"loaded {csv.stem:22} {len(df):>7,} rows")

failures = 0


def check(name, sql, expect_zero=True, expected=None, tol=0.0):
    """Run one query. expect_zero: the query lists violations and must return 0 rows/0.
    expected: the query returns a number that must equal `expected` within `tol`."""
    global failures
    rows = con.execute(sql).fetchall()
    if expected is not None:
        got = rows[0][0]
        ok = abs(got - expected) <= tol
        detail = f"got {got:,.4f}, expected {expected:,}"
    else:
        ok = len(rows) == 0
        detail = "ok" if ok else f"{len(rows)} violation(s): {rows[:5]}"
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name:58} {detail if not ok or expected is not None else ''}")


# ---- shares ---------------------------------------------------------------
check("flavor shares sum to 100%", "SELECT SUM(summer_share) FROM products", expected=1.0, tol=1e-9)
check("channel shares sum to 100%", "SELECT SUM(summer_share) FROM channels", expected=1.0, tol=1e-9)
check("each depot's channel edges sum to 100%",
      """SELECT from_node, SUM(volume_share) s FROM edges
         WHERE to_node LIKE 'C\\_%' ESCAPE '\\' AND from_node LIKE 'D\\_%' ESCAPE '\\'
         GROUP BY from_node HAVING ABS(s - 1) > 1e-9""")

# ---- keys -----------------------------------------------------------------
check("no duplicate node_id", "SELECT node_id FROM nodes GROUP BY node_id HAVING COUNT(*) > 1")
check("no duplicate edge_id", "SELECT edge_id FROM edges GROUP BY edge_id HAVING COUNT(*) > 1")
check("every edge starts at an existing node",
      "SELECT edge_id FROM edges WHERE from_node NOT IN (SELECT node_id FROM nodes)")
check("every edge ends at an existing node",
      "SELECT edge_id FROM edges WHERE to_node NOT IN (SELECT node_id FROM nodes)")
check("no self-loop edges", "SELECT edge_id FROM edges WHERE from_node = to_node")
check("no duplicate edge (same from, to, flow, mode)",
      "SELECT from_node, to_node, flow_type, mode FROM edges GROUP BY 1,2,3,4 HAVING COUNT(*) > 1")
check("every BOM source node exists",
      """SELECT flavor_id FROM bom WHERE source_node NOT IN (SELECT node_id FROM nodes)
         AND source_node NOT LIKE '%;%'""")

# ---- values ---------------------------------------------------------------
check("no negative lead times", "SELECT edge_id FROM edges WHERE lead_time_days_min < 0 OR lead_time_days_max < 0")
check("lead time min <= max", "SELECT edge_id FROM edges WHERE lead_time_days_min > lead_time_days_max")
check("no negative stock or sales",
      "SELECT 1 FROM demand_daily WHERE units < 0 UNION ALL SELECT 1 FROM inventory_snapshot WHERE units_on_hand < 0")
for tbl in ("nodes", "edges", "inventory_snapshot"):
    check(f"{tbl}.data_source is Given/Derived/Assumed",
          f"SELECT 1 FROM {tbl} WHERE data_source NOT IN ('Given','Derived','Assumed') OR data_source IS NULL")

# ---- traceability: every tag points to a real fact / gap ------------------
facts = {r[0] for r in con.execute("SELECT fact_id FROM Case_Facts")}
gaps = {r[0] for r in con.execute("SELECT gap_id FROM Gaps")}
bad = []
for tbl in ("nodes", "edges", "products", "bom", "channels", "events", "loss_ledger"):
    for (cell,) in con.execute(f"SELECT case_fact_id FROM {tbl}"):
        bad += [(tbl, f) for f in str(cell).split(";") if f not in ("", "nan", "None") and f not in facts]
for tbl in ("edges", "bom"):
    for (cell,) in con.execute(f"SELECT gap_id FROM {tbl}"):
        bad += [(tbl, g) for g in str(cell).split(";") if g not in ("", "nan", "None") and g not in gaps]
failures += bool(bad)
print(f"{'FAIL' if bad else 'PASS'}  every case_fact_id / gap_id points to a real row {bad[:5] if bad else ''}")
check("every Assumption points to a Gap", "SELECT assumption_id FROM Assumptions WHERE gap_id NOT IN (SELECT gap_id FROM Gaps)")
check("every Gap points to an Assumption",
      "SELECT gap_id FROM Gaps WHERE assumption_id NOT IN (SELECT assumption_id FROM Assumptions)")

# ---- the generated sales reconcile to the case ----------------------------
check("summer sales total = 9.6 crore bottles", "SELECT SUM(units) FROM demand_daily", expected=96_000_000, tol=0)
for _, fl in pd.read_sql("SELECT flavor_id, summer_share FROM products", con).iterrows():
    check(f"sales share of {fl.flavor_id} = {fl.summer_share:.0%}",
          f"SELECT 1.0*SUM(units)/(SELECT SUM(units) FROM demand_daily) FROM demand_daily WHERE flavor_id='{fl.flavor_id}'",
          expected=fl.summer_share, tol=1e-6)
for _, ch in pd.read_sql("SELECT channel_id, summer_share FROM channels", con).iterrows():
    check(f"sales share of {ch.channel_id} = {ch.summer_share:.0%}",
          f"SELECT 1.0*SUM(units)/(SELECT SUM(units) FROM demand_daily) FROM demand_daily WHERE channel_id='{ch.channel_id}'",
          expected=ch.summer_share, tol=1e-6)
check("demand dates fall inside 1 Mar - 30 Jun",
      "SELECT 1 FROM demand_daily WHERE date < '2026-03-01' OR date > '2026-06-30' LIMIT 1")
check("Dragon Passion has no sales before launch (2 Mar)",
      "SELECT 1 FROM demand_daily WHERE flavor_id='DP' AND date < '2026-03-02' AND units > 0 LIMIT 1")

con.commit()
con.close()
print(f"\n{'ALL CHECKS PASSED' if not failures else str(failures) + ' CHECK(S) FAILED'}  ->  {DB}")
sys.exit(1 if failures else 0)
