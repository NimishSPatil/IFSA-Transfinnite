"""
seed_tables.py  -  writes the hand-authored master tables to /data as CSV.

Run ONCE to create the starting tables:      python code/seed_tables.py
After that the CSVs are the source of truth: edit them in Excel, not here.
(Re-running would overwrite your edits, so it refuses unless you pass --force.)

Every value is tagged with where it came from:
    Given    stated in the case (PDF pages 1-3)
    Derived  calculated from case figures
    Assumed  our judgement, with a one-line reason; each one is listed in
             Assumptions.csv and, where the case is silent, in Gaps.csv

PDF page numbers: p1 = Background, p2 = Key operating data + what happened,
p3 = CEO quote, Problem Statement, Task, p4 = Objectives, p5 = Deliverables.
"""
import csv
import itertools
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)
FORCE = "--force" in sys.argv


def write(name, header, rows):
    path = DATA / name
    if path.exists() and not FORCE:
        print(f"skip  {name} (exists; use --force to overwrite)")
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {name:24} {len(rows):4} rows")


# --------------------------------------------------------------------------
# 1. CASE FACTS  (fact_id, fact, value, unit, page, module)
# --------------------------------------------------------------------------
FACTS = [
    ("F01", "Annual revenue", "1200", "INR crore", 1, "General"),
    ("F02", "Contribution margin", "32", "%", 1, "General"),
    ("F03", "Number of plants", "2", "count", 1, "Supply"),
    ("F04", "Number of co-packers", "1", "count", 1, "Supply"),
    ("F05", "Number of depots", "9", "count", 1, "Distribution"),
    ("F06", "Depots sit in this many regions", "4", "count", 2, "Distribution"),
    ("F07", "About 600 general-trade distributors, plus modern-trade retailers and quick-commerce dark stores, are served by the depots", "600", "distributors", 1, "Distribution"),
    ("F08", "Number of flavors", "5", "count", 1, "General"),
    ("F09", "Mango Peach Basil share of summer volume", "38", "%", 1, "Demand"),
    ("F10", "Guava Chilli share of summer volume", "20", "%", 1, "Demand"),
    ("F11", "Passionfruit Punch share of summer volume", "16", "%", 1, "Demand"),
    ("F12", "Dragonfruit Bloom share of summer volume", "14", "%", 1, "Demand"),
    ("F13", "Dragon Passion share of summer volume (new blend of dragonfruit + passionfruit pulp)", "12", "%", 1, "Demand"),
    ("F14", "Dragonfruit pulp that is domestic", "60", "%", 1, "Supply"),
    ("F15", "Dragonfruit pulp that is imported", "40", "%", 1, "Supply"),
    ("F16", "Imported dragonfruit pulp lead time", "6-8", "weeks", 1, "Supply"),
    ("F17", "Imported dragonfruit pulp is ordered once a quarter", "quarterly", "frequency", 2, "Supply"),
    ("F18", "Peak summer (March-June) share of annual revenue", "48", "%", 1, "Demand"),
    ("F19", "Plants cannot add mid-season lines (summer capacity is fixed)", "fixed", "constraint", 1, "Supply"),
    ("F20", "Co-packer can add up to this much extra volume", "10", "%", 2, "Supply"),
    ("F21", "Co-packer cost premium per bottle vs in-house", "25", "%", 2, "Supply"),
    ("F22", "Co-packer needs this much notice", "2", "weeks", 2, "Supply"),
    ("F23", "General trade share of summer volume", "55", "%", 1, "Demand"),
    ("F24", "Modern trade share of summer volume", "25", "%", 1, "Demand"),
    ("F25", "Quick commerce share of summer volume", "20", "%", 1, "Demand"),
    ("F26", "Average realized price", "60", "INR/bottle", 1, "General"),
    ("F27", "Forecasts are updated", "monthly", "frequency", 1, "Demand"),
    ("F28", "Average forecast error at flavor and depot level", "30", "%", 1, "Demand"),
    ("F29", "Quick-commerce platforms send sell-through reports to marketing", "daily", "frequency", 1, "Demand"),
    ("F30", "Planners receive consolidated sales data", "month-end", "frequency", 1, "Demand"),
    ("F31", "Summer volume", "9.6", "crore bottles", 2, "General"),
    ("F32", "Two plants can make together", "2.5", "crore bottles/month", 2, "Supply"),
    ("F33", "Plant utilization through the summer", "95", "%", 2, "Supply"),
    ("F34", "Procurement targets are set on price per kilogram", "price/kg", "rule", 2, "Supply"),
    ("F35", "No second passionfruit supplier has been qualified", "0", "suppliers", 2, "Supply"),
    ("F36", "Marketing informed procurement of Dragon Passion launch this long before launch", "2", "weeks", 2, "Supply"),
    ("F37", "Frozen pulp keeps up to this long in plant cold storage", "6", "months", 2, "Inventory"),
    ("F38", "Bottled juice shelf life", "90", "days", 2, "Inventory"),
    ("F39", "Modern trade and quick commerce reject stock with less than this many days left", "60", "days", 2, "Inventory"),
    ("F40", "Passionfruit pulp normally reaches plants by road in", "3", "days", 2, "Transportation"),
    ("F41", "No alternative road route from the passionfruit cooperative", "none", "constraint", 2, "Transportation"),
    ("F42", "Highway closed for at least a week in this many of the last 5 summers", "3", "of 5 summers", 2, "Transportation"),
    ("F43", "Plants held about this much passionfruit pulp when the May closure began", "2", "weeks", 2, "Inventory"),
    ("F44", "Air freight was booked in the closure's", "2nd", "week", 2, "Transportation"),
    ("F45", "Each depot holds about this much cover for every flavor", "3", "weeks", 2, "Inventory"),
    ("F46", "Depot cover is based on the previous year's flavor mix", "prior-year mix", "rule", 2, "Inventory"),
    ("F47", "Depot allocations are reset", "monthly", "frequency", 2, "Distribution"),
    ("F48", "Each depot reports stock in its own spreadsheet", "weekly", "frequency", 2, "Inventory"),
    ("F49", "Depot-to-depot transfer takes", "2-4", "days", 2, "Distribution"),
    ("F50", "Depot-to-depot transfer cost", "1.50", "INR/bottle", 2, "Distribution"),
    ("F51", "Dragon Passion launched", "early March", "date", 2, "Demand"),
    ("F52", "Influencer reel went viral this long after launch", "2", "weeks", 2, "Demand"),
    ("F53", "Quick-commerce orders rose this many times over the next two weeks", "4", "x", 2, "Demand"),
    ("F54", "Planners saw the spike only when distributors and retailers reported shortages", "late", "signal", 2, "Demand"),
    ("F55", "Landslides closed the only highway from the passionfruit cooperative in May for", "3", "weeks", 2, "Transportation"),
    ("F56", "Air-freight spend", "3.2", "INR crore", 2, "Transportation"),
    ("F57", "Air freight cost vs normal", "5", "x", 2, "Transportation"),
    ("F58", "Passionfruit Punch production was cut to protect Dragon Passion", "cut", "action", 2, "Supply"),
    ("F59", "Company still ran out of both Passionfruit Punch and Dragon Passion", "stock-out", "outcome", 2, "Inventory"),
    ("F60", "Write-offs and discounts from Mango Peach Basil and Guava Chilli overstock", "6", "INR crore", 2, "Inventory"),
    ("F61", "Share of summer revenue lost to stock-outs", "8", "%", 2, "Inventory"),
    ("F62", "Rival launched a dragonfruit-passionfruit drink within this long of the stock-outs", "6", "weeks", 2, "Demand"),
    ("F63", "Planners working in spreadsheets", "15", "planners", 3, "General"),
    ("F64", "No data or AI team", "0", "team", 3, "General"),
    ("F65", "IT is run by vendors", "vendor", "constraint", 3, "General"),
    ("F66", "Earlier digital pilots that stalled after go-live", "2", "pilots", 3, "General"),
    ("F67", "Peak-season trade-offs are escalated to the", "COO", "role", 3, "General"),
    ("F68", "S&OP meeting is held", "monthly", "frequency", 3, "General"),
    ("F69", "Total first-year budget (one-time build + first-year running)", "2.5", "INR crore", 3, "General"),
    ("F70", "No general-trade outlet data", "none", "constraint", 3, "Demand"),
    ("F71", "A stakeholder approves every recommendation the model makes", "human", "constraint", 3, "General"),
    ("F72", "Next summer is this far away", "8", "months", 3, "General"),
    ("F73", "Mango pulp comes from contracted processors", "contracted", "source", 1, "Supply"),
    ("F74", "Peach pulp comes from hill-state orchards", "hill-state", "source", 1, "Supply"),
    ("F75", "Fresh basil from contract farms near the plant, pressed into extract on site", "on-site", "source", 1, "Supply"),
    ("F76", "Guava pulp comes from two regional suppliers", "2", "suppliers", 1, "Supply"),
    ("F77", "Passionfruit Punch depends on a single hill-region cooperative", "1", "supplier", 1, "Supply"),
    ("F78", "Dragon Passion uses both dragonfruit and passionfruit pulp", "both", "ingredients", 1, "Supply"),
    ("F79", "Deck limit (including opening and closing slides)", "10", "slides", 5, "Competition"),
    ("F80", "Time to submit", "42", "hours", 5, "Competition"),
]
write("Case_Facts.csv", ["fact_id", "fact", "value", "unit", "page", "module"], FACTS)

# --------------------------------------------------------------------------
# 2. GAPS  (what the case does not say; each becomes a labelled assumption)
# --------------------------------------------------------------------------
GAPS = [
    ("G01", "Which plant makes which flavor", "Supply", "A01"),
    ("G02", "Which plants ship to which depots; transport mode, lead time and cost plant-to-depot", "Distribution", "A02"),
    ("G03", "Depot names, which depot sits in which region, and each depot's volume", "Distribution", "A03"),
    ("G04", "Import mode and route for dragonfruit; whether the 6-8 week lead time applies to the imported 40% only", "Transportation", "A04"),
    ("G05", "Passionfruit and dragonfruit share inside Dragon Passion, and its domestic/imported dragonfruit split", "Supply", "A05"),
    ("G06", "Ingredient shares in Mango Peach Basil, and the split between the two guava suppliers", "Supply", "A06"),
    ("G07", "Lead time and mode from the mango, peach, basil, guava and domestic dragonfruit suppliers to the plants", "Transportation", "A07"),
    ("G08", "Passionfruit pulp volume per month (kg) and plant cold-storage capacity", "Inventory", "A08"),
    ("G09", "Exact dates: May closure start, air-freight arrival, stock-out start/end", "Transportation", "A09"),
    ("G10", "Monthly split of the 9.6 crore summer bottles (March to June)", "Demand", "A10"),
    ("G11", "Flavor x channel x depot split of volume", "Demand", "A11"),
    ("G12", "Co-packer location, flavors it can make, and what 'up to 10% volume' is 10% of", "Supply", "A12"),
    ("G13", "No stated flow carrying the daily quick-commerce signal from Marketing to Planning (information gap)", "Demand", "A13"),
    ("G14", "Which functions attend the monthly S&OP meeting", "General", "A14"),
    ("G15", "Calendar year of 'last summer'", "General", "A15"),
    ("G16", "Air-freight transit time and the delay from booking to arrival", "Transportation", "A16"),
    ("G17", "How the 8% lost revenue and the INR 3.2 crore / INR 6 crore costs split across flavors and channels", "General", "A17"),
    ("G18", "Whether '600 distributors' includes modern-trade and quick-commerce accounts", "Distribution", "A18"),
    ("G19", "Whether the co-packer was used last summer", "Supply", "A19"),
    ("G20", "How long the quick-commerce 4x level lasted after the two-week rise", "Demand", "A20"),
    ("G21", "What depot plan share Dragon Passion got, given depot cover follows the previous year's mix", "Inventory", "A22"),
    ("G22", "Passionfruit pulp cover outside the closure window, and how fast it rebuilt after", "Inventory", "A23"),
    ("G23", "How daily sales moved during the stock-out windows, and how pulp running out at the plants on 25 May translated into empty depots given ~3 weeks of finished cover at depots", "Demand", "A21"),
    ("G24", "Which regions or depots were overstocked with Mango Peach Basil and Guava Chilli, and which were short", "Inventory", "A24"),
]
write("Gaps.csv", ["gap_id", "what_the_case_does_not_say", "module", "assumption_id"], GAPS)

# --------------------------------------------------------------------------
# 3. ASSUMPTIONS  (kept short; each justified from the case)
# --------------------------------------------------------------------------
ASSUMPTIONS = [
    ("A01", "G01", "Both plants and the co-packer can make all five flavors", "Case never limits a flavor to a plant; 'two plants make 2.5 crore bottles a month' is stated as one pool"),
    ("A02", "G02", "Both plants and the co-packer can ship to every depot, by road; lead time and cost left blank", "Case says it 'ships to nine depots' without restricting origin; blank rather than invented"),
    ("A03", "G03", "Regions are North, South, East, West; depots split 2/2/2/3 (West has 3). Generic names, no real cities", "Case gives 9 depots in 4 regions and nothing else; generic names avoid outside facts"),
    ("A04", "G04", "Imported dragonfruit travels by sea; the 6-8 week lead time applies to the imported share", "Brief calls it 'import shipping'; the case attaches the lead time to the imported pulp"),
    ("A05", "G05", "Dragon Passion pulp split is left blank until modelled; needed before the passionfruit cover calculation", "Case says 'both' only"),
    ("A06", "G06", "Guava split between the two suppliers assumed 50/50; Mango Peach Basil ingredient shares left blank", "No figure in case; equal split is the neutral choice"),
    ("A07", "G07", "Those supply edges exist (case names the sources) but lead time and mode are left blank", "Not stated; blank rather than invented"),
    ("A08", "G08", "Passionfruit cover is tracked in days of cover (14 days at closure start), not kilograms", "Case gives cover in weeks only"),
    ("A09", "G09", "Closure assumed to run 11 May to 31 May 2026 (21 days); pulp cover reaches zero on 25 May", "Case says 'May', three weeks, ~2 weeks of cover; 11 May is our pick within May"),
    ("A10", "G10", "Summer volume split evenly, 2.4 crore bottles a month (March to June)", "9.6 / 4 months; also 96% of the 2.5 crore plant capacity, close to the stated 95%"),
    ("A11", "G11", "Channel and flavor mixes are the same at every depot; all depots equal weight (1/9) before the spike is overlaid", "No depot-level data in the case"),
    ("A12", "G12", "Co-packer capacity = 10% of plant capacity = 0.25 crore bottles/month, all flavors", "Case says 'up to 10% volume'; we read it as 10% of plant volume"),
    ("A13", "G13", "No Marketing-to-Planning edge is created; the missing flow is itself a risk flag", "Case says only that QC reports go to marketing and that planners see data at month-end"),
    ("A14", "G14", "Only Planning and the COO are drawn at S&OP", "Case names the meeting and the COO escalation; other attendees not stated"),
    ("A15", "G15", "'Last summer' is calendar year 2026, used only to order dates", "Case gives months, not a year"),
    ("A16", "G16", "Air-freight lead time left blank; the 2nd-week booking delay is stored as a note", "Case gives booking week and cost multiple, not transit time"),
    ("A17", "G17", "Loss ledger holds only the three given figures; attribution to causes is a later step", "Avoids baking an unproven split into the data"),
    ("A18", "G18", "600 is treated as the approximate downstream account count and not used in calculations", "Wording is ambiguous"),
    ("A19", "G19", "Co-packer shown as available capacity, not as last summer's actual flow", "Case does not say it was used"),
    ("A20", "G20", "The 4x quick-commerce level for Dragon Passion is held until 30 June in the sample data", "Case gives the rise, not the decay; holding keeps the stress case visible"),
    ("A21", "G23", "Sample sales of Passionfruit Punch and Dragon Passion run at 30% of normal from 25 May to 14 Jun, with depot stock at zero for both (pulp gone until supply rebuilt)", "Case says both ran out; the size of the dip is ours. Flavor and channel totals are still held to the Given shares"),
    ("A22", "G21", "Depot plan mix gives Dragon Passion 5% and scales the other four flavors up to 95%", "Case says cover follows the previous year's mix, which predates the launch; any non-zero share is our assumption"),
    ("A23", "G22", "Plant passionfruit cover is 14 days before the closure, falls 1 day per day to 0 on 25 May, stays 0 to 31 May, and rebuilds linearly to 14 days by 14 Jun", "Case gives only the 2 weeks at closure start; the rest follows from it"),
    ("A24", "G24", "The baseline keeps depots equal, so it shows the Dragon Passion shortage but NOT the regional overstock/shortage of Mango Peach Basil and Guava Chilli; that imbalance is introduced as a scenario parameter in the replay", "Case says it happened (F60) but gives no depot detail; inventing a split here would bake an unproven pattern into the data"),
]
write("Assumptions.csv", ["assumption_id", "gap_id", "assumption", "reason"], ASSUMPTIONS)

# --------------------------------------------------------------------------
# 4. NODES
#    node_id, name, type, region, capacity_per_month, capacity_unit,
#    storage_type, cover_target_days, pulp_on_hand_days, single_source,
#    data_source, case_fact_id, notes
# --------------------------------------------------------------------------
N = []
def node(*row): N.append(row)

# Suppliers (type = supplier)
node("S_MANGO", "Mango pulp processors (contracted)", "supplier", "", "", "", "", "", "", "N", "Given", "F73", "Plural, contracted")
node("S_PEACH", "Peach orchards (hill-state)", "supplier", "Hill", "", "", "", "", "", "N", "Given", "F74", "Plural orchards")
node("S_BASIL", "Basil contract farms (near plant)", "supplier", "", "", "", "", "", "", "N", "Given", "F75", "Fresh basil pressed into extract on site")
node("S_GUAVA1", "Guava pulp supplier 1 (regional)", "supplier", "", "", "", "", "", "", "N", "Given", "F76", "One of two")
node("S_GUAVA2", "Guava pulp supplier 2 (regional)", "supplier", "", "", "", "", "", "", "N", "Given", "F76", "One of two")
node("S_PASSION", "Passionfruit cooperative (hill region)", "supplier", "Hill", "", "", "", "", "", "Y", "Given", "F77;F35", "Single source, no second supplier qualified")
node("S_DRAGON_DOM", "Dragonfruit pulp - domestic (60%)", "supplier", "", "", "", "", "", "", "N", "Given", "F14", "")
node("S_DRAGON_IMP", "Dragonfruit pulp - imported (40%)", "supplier", "Overseas", "", "", "", "", "", "N", "Given", "F15", "Ordered once a quarter")

# Plants / co-packer. 2.5 crore/month is for both plants together -> 1.25 each (Assumed equal)
node("P1", "Plant 1", "plant", "", 1.25, "crore bottles", "cold storage (frozen pulp, up to 6 months)", "", 14, "N", "Assumed", "F32;F37;F43", "Capacity split equally (A01); 14 days passionfruit pulp at closure start is Given (F43)")
node("P2", "Plant 2", "plant", "", 1.25, "crore bottles", "cold storage (frozen pulp, up to 6 months)", "", 14, "N", "Assumed", "F32;F37;F43", "Capacity split equally (A01)")
node("CP", "Co-packer", "copacker", "", 0.25, "crore bottles", "", "", "", "N", "Derived", "F20", "10% of plant capacity (A12); +25% cost, 2 weeks' notice")

# Depots: 9 depots in 4 regions (Assumed split 2/2/2/3)
for rid, region, n in [("N", "North", 2), ("S", "South", 2), ("E", "East", 2), ("W", "West", 3)]:
    for i in range(1, n + 1):
        node(f"D_{rid}{i}", f"{region} depot {i}", "depot", region, "", "", "ambient", 21, "", "N", "Assumed", "F05;F06;F45", "Region/name assumed (A03); 3 weeks cover is Given")

# Channels
node("C_GT", "General trade (distributors)", "channel", "", "", "", "", "", "", "N", "Given", "F23", "55% of summer volume; no outlet data (F70)")
node("C_MT", "Modern trade (retailers)", "channel", "", "", "", "", "", "", "N", "Given", "F24", "25%; rejects stock under 60 days left")
node("C_QC", "Quick commerce (dark stores)", "channel", "", "", "", "", "", "", "N", "Given", "F25", "20%; rejects stock under 60 days left; daily sell-through reports")

# Functions
node("X_MKT", "Marketing", "function", "", "", "", "", "", "", "N", "Given", "F29;F36", "")
node("X_PLAN", "Planning (15 planners, spreadsheets)", "function", "", "", "", "", "", "", "N", "Given", "F63", "")
node("X_PROC", "Procurement", "function", "", "", "", "", "", "", "N", "Given", "F34", "Targets set on price per kg")
node("X_COO", "COO / S&OP", "function", "", "", "", "", "", "", "N", "Given", "F67;F68", "Approves peak-season trade-offs")

write("nodes.csv",
      ["node_id", "name", "type", "region", "capacity_per_month", "capacity_unit",
       "storage_type", "cover_target_days", "pulp_on_hand_days", "single_source",
       "data_source", "case_fact_id", "notes"], N)

PLANTS = ["P1", "P2"]
DEPOTS = [r[0] for r in N if r[2] == "depot"]
CHANNELS = ["C_GT", "C_MT", "C_QC"]
SUPPLIERS = [r[0] for r in N if r[2] == "supplier"]

# --------------------------------------------------------------------------
# 5. EDGES
#    edge_id, from_node, to_node, flow_type, mode, lead_time_days_min,
#    lead_time_days_max, cost_per_unit, cost_multiple, volume_share,
#    alternative_route_exists, frequency, reporting_lag_days,
#    disruption_history, data_source, case_fact_id, gap_id, notes
# --------------------------------------------------------------------------
E = []
def edge(frm, to, flow, mode, lmin="", lmax="", cost="", mult="", share="", alt="",
         freq="", lag="", hist="", src="", fact="", gap="", notes=""):
    E.append((f"E{len(E) + 1:03d}", frm, to, flow, mode, lmin, lmax, cost, mult, share,
              alt, freq, lag, hist, src, fact, gap, notes))

# --- Inbound goods: suppliers -> plants
for p in PLANTS:
    edge("S_PASSION", p, "goods", "road", 3, 3, mult=1, alt="N", freq="",
         hist="closed >=1 week in 3 of last 5 summers", src="Given",
         fact="F40;F41;F42", notes="Only highway; no alternative road route")
for p in PLANTS:
    edge("S_PASSION", p, "goods", "air", "", "", mult=5, alt="Y", freq="contingency",
         src="Given", fact="F44;F56;F57", gap="G16",
         notes="Contingency only. 5x normal cost; booked in 2nd week of closure; transit time not stated")
for p in PLANTS:
    edge("S_DRAGON_IMP", p, "goods", "sea", 42, 56, alt="unknown", freq="quarterly",
         src="Assumed", fact="F15;F16;F17", gap="G04",
         notes="Lead time 6-8 weeks and quarterly ordering are Given; sea mode is Assumed")
for sup, fid, gap in [("S_MANGO", "F73", "G07"), ("S_PEACH", "F74", "G07"),
                      ("S_BASIL", "F75", "G07"), ("S_GUAVA1", "F76", "G07"),
                      ("S_GUAVA2", "F76", "G07"), ("S_DRAGON_DOM", "F14", "G07")]:
    for p in PLANTS:
        edge(sup, p, "goods", "road", alt="unknown", src="Assumed", fact=fid, gap=gap,
             notes="Edge exists per case; mode and lead time not stated")

# --- Production -> depots (both plants and the co-packer ship to every depot, Assumed)
for src_node in PLANTS + ["CP"]:
    for d in DEPOTS:
        edge(src_node, d, "goods", "road", alt="Y", src="Assumed", fact="F05", gap="G02",
             notes="Plant-to-depot allocation, mode and lead time not stated")

# --- Depots -> channels (volume share is Given at channel level, same at every depot, Assumed)
for d in DEPOTS:
    for c, share, fid in [("C_GT", 0.55, "F23"), ("C_MT", 0.25, "F24"), ("C_QC", 0.20, "F25")]:
        edge(d, c, "goods", "road", share=share, alt="unknown", src="Assumed", fact=fid, gap="G11",
             notes="Channel share is Given overall; applied equally at each depot")

# --- Lateral: depot <-> depot transfers (every ordered pair)
for a, b in itertools.permutations(DEPOTS, 2):
    edge(a, b, "transfer", "road", 2, 4, cost=1.50, alt="Y", src="Given", fact="F49;F50",
         notes="2-4 days, about INR 1.50 per bottle")

# --- Information flows
edge("C_QC", "X_MKT", "information", "digital", freq="daily", lag=1, src="Given", fact="F29",
     notes="Daily sell-through reports. Lag of 1 day is Derived from 'daily'")
for c in CHANNELS:
    edge(c, "X_PLAN", "information", "manual", freq="monthly", lag=30, src="Derived", fact="F30",
         notes="Consolidated sales reach planners at month-end; up to ~30 days old (Derived)")
for d in DEPOTS:
    edge(d, "X_PLAN", "information", "manual", freq="weekly", lag=7, src="Given", fact="F48",
         notes="Each depot's own spreadsheet; up to 7 days old (Derived from 'weekly')")
for d in DEPOTS:
    edge("X_PLAN", d, "information", "manual", freq="monthly", src="Given", fact="F47;F46",
         notes="Allocation reset monthly using the previous year's flavor mix")
edge("X_MKT", "X_PROC", "information", "manual", freq="one-off", lmin=14, lmax=14,
     src="Given", fact="F36", notes="Dragon Passion launch notice: 2 weeks before launch")
edge("X_PLAN", "X_PROC", "information", "manual", freq="monthly", src="Assumed", fact="F27",
     notes="Monthly forecast assumed to reach procurement; case does not state the link")
for sup in SUPPLIERS:
    edge("X_PROC", sup, "information", "manual",
         freq="quarterly" if sup == "S_DRAGON_IMP" else "", src="Given" if sup == "S_DRAGON_IMP" else "Assumed",
         fact="F17" if sup == "S_DRAGON_IMP" else "F34", gap="" if sup == "S_DRAGON_IMP" else "G07",
         notes="Orders. Imported dragonfruit ordered once a quarter; other order cycles not stated")
edge("X_PLAN", "CP", "information", "manual", freq="as needed", lmin=14, lmax=14,
     src="Given", fact="F22", notes="Co-packer needs 2 weeks' notice")
edge("X_PLAN", "X_COO", "information", "manual", freq="monthly", src="Given", fact="F67;F68",
     notes="Monthly S&OP; peak-season trade-offs escalated to the COO")
edge("X_COO", "X_PLAN", "information", "manual", freq="as needed", src="Given", fact="F67",
     notes="COO decisions on escalated trade-offs")

write("edges.csv",
      ["edge_id", "from_node", "to_node", "flow_type", "mode", "lead_time_days_min",
       "lead_time_days_max", "cost_per_unit", "cost_multiple", "volume_share",
       "alternative_route_exists", "frequency", "reporting_lag_days", "disruption_history",
       "data_source", "case_fact_id", "gap_id", "notes"], E)

# --------------------------------------------------------------------------
# 6. PRODUCTS, BOM, CHANNELS, EVENTS, LOSS LEDGER
# --------------------------------------------------------------------------
write("products.csv", ["flavor_id", "name", "summer_share", "shelf_life_days", "is_new", "data_source", "case_fact_id"], [
    ("MPB", "Mango Peach Basil", 0.38, 90, "N", "Given", "F09;F38"),
    ("GC", "Guava Chilli", 0.20, 90, "N", "Given", "F10;F38"),
    ("PP", "Passionfruit Punch", 0.16, 90, "N", "Given", "F11;F38"),
    ("DB", "Dragonfruit Bloom", 0.14, 90, "N", "Given", "F12;F38"),
    ("DP", "Dragon Passion", 0.12, 90, "Y", "Given", "F13;F38"),
])

write("bom.csv", ["flavor_id", "ingredient", "source_node", "share_of_input", "data_source", "case_fact_id", "gap_id"], [
    ("MPB", "mango pulp", "S_MANGO", "", "Given", "F73", "G06"),
    ("MPB", "peach pulp", "S_PEACH", "", "Given", "F74", "G06"),
    ("MPB", "fresh basil (extract pressed on site)", "S_BASIL", "", "Given", "F75", "G06"),
    ("GC", "guava pulp", "S_GUAVA1", 0.5, "Assumed", "F76", "G06"),
    ("GC", "guava pulp", "S_GUAVA2", 0.5, "Assumed", "F76", "G06"),
    ("PP", "passionfruit pulp", "S_PASSION", 1.0, "Given", "F77", ""),
    ("DB", "dragonfruit pulp - domestic", "S_DRAGON_DOM", 0.6, "Given", "F14", ""),
    ("DB", "dragonfruit pulp - imported", "S_DRAGON_IMP", 0.4, "Given", "F15", ""),
    ("DP", "dragonfruit pulp", "S_DRAGON_DOM;S_DRAGON_IMP", "", "Given", "F78", "G05"),
    ("DP", "passionfruit pulp", "S_PASSION", "", "Given", "F78", "G05"),
])

write("channels.csv", ["channel_id", "name", "summer_share", "reporting_frequency", "min_shelf_life_days", "data_source", "case_fact_id"], [
    ("C_GT", "General trade", 0.55, "month-end (consolidated)", "", "Given", "F23;F30"),
    ("C_MT", "Modern trade", 0.25, "month-end (consolidated)", 60, "Given", "F24;F39"),
    ("C_QC", "Quick commerce", 0.20, "daily to marketing; month-end to planners", 60, "Given", "F25;F29;F39"),
])

write("events.csv", ["event_id", "date", "event_type", "description", "affected_nodes", "data_source", "case_fact_id"], [
    ("EV1", "2026-03-02", "launch", "Dragon Passion launched (early March; exact day Assumed)", "X_MKT;X_PROC;C_QC", "Assumed", "F51"),
    ("EV2", "2026-03-16", "demand_spike_start", "Influencer reel goes viral, 2 weeks after launch (Derived)", "C_QC", "Derived", "F52"),
    ("EV3", "2026-03-30", "demand_spike_peak", "Quick-commerce orders reach 4x, two weeks after the reel (Derived)", "C_QC;D_N1;D_N2;D_S1;D_S2;D_E1;D_E2;D_W1;D_W2;D_W3", "Derived", "F53"),
    ("EV4", "2026-03-31", "signal_reaches_planners", "Month-end consolidated sales reach planners; shortages already reported by trade (Derived)", "X_PLAN", "Derived", "F30;F54"),
    ("EV5", "2026-05-11", "highway_closure_start", "Landslides close the only highway from the passionfruit cooperative (day Assumed within May)", "S_PASSION;P1;P2", "Assumed", "F55"),
    ("EV6", "2026-05-18", "air_freight_booked", "Air freight booked in the 2nd week of closure (Derived from start date)", "S_PASSION;P1;P2", "Derived", "F44"),
    ("EV7", "2026-05-25", "passionfruit_pulp_exhausted", "About 2 weeks of pulp cover used up (Derived: 14 days after start)", "P1;P2", "Derived", "F43"),
    ("EV8", "2026-05-31", "highway_closure_end", "Closure ends after 3 weeks (Derived)", "S_PASSION", "Derived", "F55"),
])

write("loss_ledger.csv", ["item", "value", "unit", "data_source", "case_fact_id", "notes"], [
    ("Air freight of passionfruit pulp", 3.2, "INR crore", "Given", "F56", "At 5x normal cost"),
    ("Write-offs and discounts (Mango Peach Basil, Guava Chilli overstock)", 6.0, "INR crore", "Given", "F60", ""),
    ("Revenue lost to stock-outs", 46.08, "INR crore", "Derived", "F61;F01;F18", "8% x (48% x 1200) = 8% x 576; attribution to causes is a later step (A17)"),
])
