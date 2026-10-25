"""
export_prompt1_docs.py - writes the prompt-1 deliverables from the engine itself, so every number matches the dashboard.

    python code/export_prompt1_docs.py

    docs/PROMPT1_NOTES.md     change log, decision tables, risk register, assumptions and limitations, controls, prompt-2 hand-off
    docs/controls.csv         every control: id, group, label, unit, default, range, source, reference
    docs/risk_register.csv    R01-R27 with their evaluated status at the two replay weeks
"""
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

from app.engine import controls as CT          # noqa: E402
from app.engine import forecast as FC          # noqa: E402
from app.engine import risks as RK             # noqa: E402
from app.engine import supply as SUP           # noqa: E402
from app.engine import transport as TR         # noqa: E402
from app.engine import copacker as CP          # noqa: E402

DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)
CTL = CT.Ctl()
CLOSURE_W, SPIKE_W = date(2026, 5, 4), date(2026, 3, 16)

NEW_ASSUMPTIONS = [
    ("A25", "Scenario delays on open orders are levers, default 0 days", "a09, a10"),
    ("A26", "A hypothetical highway closure is off by default", "b01"),
    ("A27", "Demand-shock scenario is off by default; its size defaults to the case's 4x (F53)", "b11-b13"),
    ("A28", "Air-freight capacity about 4.7 t/day: the sample airlifted 66 t over the closure's last two weeks", "c04"),
    ("A29", "National flavor-level forecast error 15% (depot errors are not independent); test 10-20%", "f02"),
    ("A30", "Pulp planned at P80, finished goods at P50 (spec 3.2)", "f03, f04"),
    ("A31", "Baseline = last year's same week x a level blended between planned growth and the realised level", "f05, f06"),
    ("A32", "Censored weeks use units ordered as demand (orders = sold + lost in the sample)", "f07"),
    ("A33", "Detector: EWMA 0.3, alert at 1.5x or CUSUM 1.5 (slack 0.15), 2 days running, >= 500 bottles/day, 28-day "
            "baseline lagged 7 days, seasonal rise removed", "f08-f14, f26"),
    ("A34", "Alert classes: launch ramp inside 28 days of launch; viral burst if >= 60% of depots break and the rise is sudden", "f15, f16"),
    ("A35", "Depot shares: recency half-life 4 weeks, shrinkage k = 4 toward the region; DP starts from the PP + DB average", "f19, f20"),
    ("A36", "Social desk thresholds (3x velocity, 30 mentions/day, 15% macro + mega) on a simulated feed", "f24, f25, f27"),
    ("A37", "Pulp safety buffer 3 days of use (handoff 5.4)", "g05"),
    ("A38", "Planning horizon 56 days (spec: 28-56)", "g06"),
    ("A39", "No minimum service floor unless management sets one", "g07"),
    ("A40", "Planned growth 15% a year for the baseline (user decision: growth slowing to 15%)", "f23"),
    ("A41", "The two plants' pulp is pooled (which plant makes which flavor is not in the case, G01)", "-"),
    ("A42", "No-action production = forecast at the finished-goods percentile, capped pro rata by plant capacity", "f04, e01, e02"),
    ("A43", "Uniform contribution of ₹19.20 per bottle (₹60 x 32%) as the margin proxy for every flavor", "d05, d06"),
    ("A44", "Normal standing orders keep arriving at the forecast requirement after the lead time (shown as 'planned', "
            "not confirmed); passionfruit stops while the road is shut; imports count only when ordered", "-"),
    ("A45", "Share of unmet MPB / GC buyers who would switch flavor: 0 (no data; a hypothesis slider)", "d12"),
    ("A46", "The case's PP cut (F58) sized at 90% in the 'case response' option", "d13"),
    ("A47", "A lane is flagged below 90% on time, or when lead time exceeds 50% of plant cover", "a11, a12"),
]
NEW_GAPS = [
    ("G25", "Packaging (bottles, caps, labels) supply and stock"),
    ("G26", "Pulp lot quality, quarantine and cold-storage incidents"),
    ("G27", "Plant breakdown history"),
    ("G28", "Import price and currency terms for dragonfruit"),
    ("G29", "Guava supplier 2's spare capacity and ramp time"),
    ("G30", "Domestic dragonfruit suppliers' spare capacity"),
    ("G31", "Passionfruit cooperative's surge capacity before the season"),
    ("G32", "Qualified alternate mango, peach and basil processors"),
    ("G33", "Pulp price per kg (needed to cost pre-positioning)"),
    ("G34", "Promotion calendar (needed to tell a promotion from a viral burst)"),
    ("G35", "Social-listening data (the desk runs on a simulated feed)"),
]
LIMITS = [
    "All data is synthetic and calibrated to the case. No accuracy is claimed; replays show detection dates and lead times on the sample only.",
    "Planned receipts assume suppliers keep delivering the forecast requirement. Where supplier capacity itself is the problem, "
    "the engine shows it only through a scenario control (b04, b06, c01-c06), never by inventing capacity.",
    "After a disruption, standing orders replace use but do not rebuild the buffer above it (no order-up-to rebuild), so a second "
    "shock soon after the first is shown slightly worse than a planner who rebuilds would face.",
    "Plants are pooled (A41); there is no plant-to-depot lane data (G02), so plant-level and lane-level constraints are not modelled.",
    "The joint allocation maximises bottles because the margin is uniform (A43). With real per-flavor margins it would change; the "
    "service floor g07 is the guard against starving one flavor.",
    "'10% co-packer volume' is read as 10% of plant volume over the fortnight (G12).",
    "Basil cover is structurally short in the sample (5-7 days, F75 fresh basil), so R03 fires in stress runs; its 3-day lead is assumed (G07).",
    "The as-of view is weekly (the Monday after the chosen week); the detector is daily inside that window.",
    "The social desk runs on a simulated feed. It can only ask for verification; it never moves supply.",
    "Scenarios, the change log and decisions are local JSON files (dashboard/state/): a single-user prototype. Roles in the review form are "
    "self-declared; a vendor build would add sign-in and a database.",
    "Pathway A/B substitution (MPB, GC) is a hypothesis slider (d12), not an optimisation, because no substitution data exists.",
]


def md_table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("|", "/") for x in r) + " |")
    return "\n".join(out)


def b(n):
    return "–" if n is None else (f"{n / 1e5:,.1f} L" if abs(n) >= 1e5 else f"{n:,.0f}")


def inr(x):
    return "–" if x is None else (f"₹{x / 1e7:,.2f} Cr" if abs(x) >= 1e7 else f"₹{x / 1e5:,.1f} L")


def contrast(a, c):
    def lum(h):
        h = h.lstrip("#")
        v = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    l1, l2 = sorted((lum(a), lum(c)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def main():
    # controls.csv
    with open(DOCS / "controls.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "group", "label", "unit", "default", "min", "max", "source", "reference", "note"])
        for c in CT.REGISTRY:
            rng = (c["lo"], c["hi"]) if c["kind"] != "select" else ("/".join(c["options"]), "")
            w.writerow([c["id"].upper(), CT.GROUPS[c["group"]], c["label"], c["unit"], c["default"], rng[0], rng[1], c["src"], c["ref"], c["note"]])

    # risk_register.csv
    rc, rs = {r["id"]: r for r in RK.evaluate(CLOSURE_W, CTL)}, {r["id"]: r for r in RK.evaluate(SPIKE_W, CTL)}
    with open(DOCS / "risk_register.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "risk", "flavors", "evidence basis", "owner", "agreed response", "new in prompt 1",
                    "status 11 May 2026", "evidence 11 May 2026", "status 16 Mar 2026", "evidence 16 Mar 2026"])
        for m in RK.META.values():
            w.writerow([m["id"], m["name"], m["skus"], m["basis"], m["owner"], m["response"], "yes" if m["id"] >= "R19" else "",
                        rc[m["id"]]["status"], rc[m["id"]]["evidence"], rs[m["id"]]["status"], rs[m["id"]]["evidence"]])

    # numbers for the decision tables
    mit = SUP.mitigations(CLOSURE_W, CTL)
    tm = TR.mitigation(CLOSURE_W, CTL)
    mt = FC.method_test(CTL)
    sp = FC.replay_spike(CTL)
    cl = SUP.replay_closure(CTL)
    cp = CP.evaluate(date(2026, 3, 30), CTL)

    L = []
    L.append("# PulpSense · Prompt 1 (Supply) — notes and deliverables\n")
    L.append("Generated by `code/export_prompt1_docs.py` from the engine at its default settings, so every number below matches the "
             "dashboard. Acceptance checks: `code/check_prompt1.py` (results in `docs/acceptance_prompt1.csv`).\n")
    L.append("Run the dashboard: `python dashboard/run.py`, then open http://localhost:8600.\n")

    L.append("## 1. Change log\n")
    L.append("""- **New decision engine** `dashboard/app/engine/`: `controls` (Control Panel registry, scenarios, change log), `forecast`
  (baseline, quantiles, kg, daily detector, classifier, persistence, depot split, replays), `supply` (daily material balance,
  levers, lead-time gap, pathways A/B/C, joint allocation LP, closure replay), `risks` (R01–R27), `copacker` (eligibility rule),
  `transport` (lane fragility, flags, lane mitigation), `social` (simulated desk), `readme` (READ_ME), `reviews` (decision queue),
  `inventory_iface` (the Supply → Inventory hand-off, simple form).
- **New pages**: Supply risk engine, Forecast & signals, Social signal desk, Co-packer, Review queue, Control panel, READ_ME.
- **Extended pages**: Overview (the alerts placeholder is now "Needs attention", fed by READ_ME); Supply (engine summary);
  Transportation (fragility, flags, compare-and-choose); Inventory ("Inventory module: coming in prompt 2" + hand-off table);
  Inventory and Distribution now take the depot cover target (g04) and transfer cost (a08) from the Control Panel.
- **Every recommendation is a review candidate** (Approve / Reject / Defer / Escalate to COO, rationale required, append-only log).
  Nothing is executed.
- **Theme**: McKinsey palette (navy #051C2C sidebar, electric #2251FF accent, cyan #00A9F4 for fills only); contrast checked (section 6).
  Renamed to PulpSense; a page strip for phones; the dead catch-all route removed.
- **State**: `dashboard/state/` holds the active scenario, saved scenarios, the control change log and decisions (JSON).
- **Bugs found and fixed while building**: the detector read the normal seasonal warm-up as spikes (fixed with a seasonally
  adjusted ratio); stock-out days were read as zero sales in the breadth test (now unobservable); recipe shares above 100%
  crashed the risk text (now normalised); old unfilled orders from earlier closures were counted as open (now closed after 30 days).
""")

    L.append("## 2. Decision tables (compare and choose)\n")
    L.append(f"### 2.1 Pathway C — passionfruit / dragonfruit shortage, as of Monday 11 May 2026 (May closure replay)\n")
    L.append(f"Horizon {int(CTL['g06'])} days; pulp limits PP/DB/DP until {mit['end']:%d %b}; contribution proxy ₹{mit['margin']:.2f}/bottle "
             f"(d05 × d06, Given F26 × F02, uniform). Net = contribution protected − extra cost; an exposure estimate, not avoided savings.\n")
    rows = []
    for o in mit["options"]:
        verdict = "**chosen**" if o["winner"] else ("not feasible" if not o["feasible"] else ("baseline" if o["key"] == "none" else "compared"))
        rows.append([o["name"], f"{o['lead']:g} d" if o["lead"] is not None else "–", b(o.get("unmet")),
                     inr(o.get("cost")), inr(o.get("net")), verdict, o["why"] or o["note"]])
    L.append(md_table(["Option", "Lead", "Unmet PP+DB+DP", "Extra cost", "Net vs no action", "Verdict", "Why / note"], rows))
    L.append("\n**Implemented**: the joint allocation (a linear program over the horizon with dated receipts) is the recommendation and goes "
             "to review. Air + joint saves more bottles but its ₹ premium is larger than the extra contribution, so it is shown, not chosen. "
             "The case's own response (cut PP) is beaten by the joint allocation without extra cost.\n")

    L.append(f"### 2.2 Transport — protecting the passionfruit lane against a {int(CTL['b02'])}-day closure (as of 11 May 2026)\n")
    rows = [[o["name"], f"{o['protects']:.0f}" if o["protects"] is not None else "–", o["cost_txt"], o["lead"], o["depends"],
             "**chosen**" if o["winner"] else ("conditional" if o["why"].startswith("conditional") else ("not feasible" if not o["feasible"] else "compared"))]
            for o in tm["options"]]
    L.append(md_table(["Option", "Days protected", "Cost", "Lead", "Depends on", "Verdict"], rows))
    L.append(f"\nNeeded {tm['need_days']:.0f} days; procurement's target holds {tm['have']:.1f}. **Implemented**: the pre-agreed air trigger is "
             "chosen today because it is the only feasible option that protects most; **pre-positioning + air backup becomes the choice the "
             "moment the cooperative confirms surge volume (c05)** — frozen pulp keeps 6 months (F37). Its cost needs the pulp price (G33).\n")

    L.append("### 2.3 Forecasting — how to detect a demand shift\n")
    rows = [[r["method"], f"{r['caught']} / {r['spikes']}", f"{r['median_delay']:.0f} d" if r["median_delay"] is not None else "–", r["false"],
             "**chosen**" if r["key"] == "adjusted" else ""] for r in mt]
    L.append(md_table(["Method", "Injected spikes caught", "Median delay", "False alerts", "Verdict"], rows))
    L.append(f"\nInjected-scenario test (spec 8): {mt[0]['runs']} seeded synthetic series from the sample's smoothed Guava Chilli season with "
             "10% daily noise; half get a 2–4x spike. Synthetic, for choosing a method — not an accuracy figure. The raw ratio is tripped by the "
             "seasonal warm-up itself; the fixed rule is simple but has no handling of stock-outs or noise. **Implemented**: EWMA + CUSUM on the "
             f"seasonally adjusted ratio. Replay: the March spike is detected **{sp['detected']:%d %b}**, {sp['lead_planning']} days before "
             f"Planning's month-end view ({sp['planning_sees']:%d %b}).\n")

    L.append("### 2.4 Forecasting — the baseline method (\"better method if found\")\n")
    L.append(md_table(["Method", "Uses history", "Explainable to 15 planners", "Vendor-maintainable", "Verdict"], [
        ["Spec's case plan: 9.6 Cr split evenly Mar–Jun × shares", "no (spec assumed none)", "yes", "yes", "fallback only"],
        ["Plan blended with trailing run-rate (spec 3.1)", "recent weeks", "yes", "yes", "kept as the level term"],
        ["**Last year's same week × level blended between plan growth and realised level**", "two years (dataset v2)", "yes", "yes", "**chosen**"],
        ["ML / black-box model", "yes", "no", "no (no data team, F64–F65)", "rejected"],
    ]))
    L.append("\nWhy: dataset v2 has 2024–2026 history, so the seasonal shape no longer has to be assumed flat. Dragon Passion has no last year: "
             "its run-rate × the PP + DB seasonal shape, and before launch the launch allocation once Marketing has told Procurement (F36).\n")

    L.append("### 2.5 The co-packer rule (task 3) — how it reads the case\n")
    L.append(md_table(["Check", "Reading", "Source"], [
        ["Forecast above combined plant max", f"P{int(CTL['f04'])} forecast for the 2 weeks after {int(CTL['d09'])} days' notice vs e01 × e02", "F22, F32"],
        ["Ingredients available", "material balance stays above the buffer after plant use for the extra bottles", "R25"],
        ["≤ 10% cap", "volume proposed = min(excess, 10% of plant volume); the rest stays unmet", "F20, G12"],
        ["Economics shown", f"premium {CTL['d07']:.0%} × unit cost ₹{CTL['d05'] * (1 - CTL['d06']):.2f} = ₹{CTL['d07'] * CTL['d05'] * (1 - CTL['d06']):.2f} vs contribution ₹{CTL['d05'] * CTL['d06']:.2f}", "F02, F21, F26"],
    ]))
    L.append(f"\nExample: as of 30 Mar 2026 the forecast is above plant capacity but the co-packer is **not eligible** — "
             f"{' '.join(cp['reasons'])}\n")

    L.append("## 3. Risk register (R01–R27)\n")
    L.append("R01–R18 from the handoff; **R19–R27 are new in prompt 1**. Status at the two replay weeks; full evidence in `docs/risk_register.csv`.\n")
    rows = [[m["id"] + (" (new)" if m["id"] >= "R19" else ""), m["name"], m["skus"], m["basis"], rs[m["id"]]["status"], rc[m["id"]]["status"], m["owner"]]
            for m in RK.META.values()]
    L.append(md_table(["ID", "Risk", "Flavors", "Evidence basis", "16 Mar 2026", "11 May 2026", "Owner"], rows))
    L.append("\nWhy the new ones matter: packaging (R19), lot quality (R20) and cold chain (R21) can make pulp *on hand* unusable — the "
             "balance's opening stock is only as good as these; a plant breakdown (R22) at 95% utilisation has no slack; import price / FX (R23) "
             "hits the 40% imported dragonfruit; supplier concentration (R24) is the structural root of R06; the co-packer needs the same pulp "
             "(R25), so it cannot fix a pulp shortage; peach orchards and the passionfruit cooperative are both hill-region sources (R26, an "
             "inference); and pre-building finished goods ages them past the 60-day cutoff (R27, Inventory).\n")

    L.append("## 4. Replays (acceptance)\n")
    L.append(md_table(["Replay", "Detection", "Planning's month-end signal", "Lead"], [
        ["March spike (Dragon Passion quick commerce)", f"{sp['detected']:%d %b} (first breach {sp['first_hit']:%d %b})", f"{sp['planning_sees']:%d %b}", f"{sp['lead_planning']} days"],
        ["May closure (passionfruit)", f"pre-season warning {cl['pre_warning']:%d %b}; closure {cl['detected']:%d %b}", f"{cl['planning_sees']:%d %b}", f"{cl['lead']} days ({cl['pre_lead']} days of pre-season warning)"],
    ]))
    L.append(f"\nMay closure detail: {cl['cover']:.1f} days of passionfruit cover; below buffer {cl['first_unsafe']:%d %b}, runs out {cl['first_out']:%d %b}; "
             f"air had to be booked by {cl['book_by']:%d %b} — the sample booked it {cl['booked']:%d %b} ({cl['book_gap']} days late; case: 2nd week, F44). "
             "The censoring check: without the stock-out mask the detector raises a false 'demand collapse' on PP during the closure; with it, none.\n")

    L.append("## 5. Assumptions and limitations\n")
    L.append("### New assumptions (A25–A47)\n")
    L.append(md_table(["ID", "Assumption", "Control"], NEW_ASSUMPTIONS))
    L.append("\n### New gaps (G25–G35) — what the case and the sample do not give\n")
    L.append(md_table(["ID", "Gap"], NEW_GAPS))
    L.append("\n### Limitations\n")
    L.extend(f"- {x}" for x in LIMITS)
    L.append("")

    L.append("## 6. Theme tokens and contrast (WCAG)\n")
    pairs = [("--accent #2251FF on white", "#2251FF", "#FFFFFF", "text, buttons"),
             ("--accent-d #1238C7 on --al #EAF0FF", "#1238C7", "#EAF0FF", "active chips"),
             ("white on --navy #051C2C", "#FFFFFF", "#051C2C", "sidebar active"),
             ("#D5DEE6 on --navy", "#D5DEE6", "#051C2C", "sidebar links"),
             ("#8EA4B7 on --navy", "#8EA4B7", "#051C2C", "sidebar group labels"),
             ("white on --accent", "#FFFFFF", "#2251FF", "primary buttons"),
             ("--cyan #00A9F4 on white", "#00A9F4", "#FFFFFF", "fills only (fails as text)"),
             ("--cyan-d #00699A on white", "#00699A", "#FFFFFF", "cyan text when needed"),
             ("--t3 #667085 on white", "#667085", "#FFFFFF", "secondary text")]
    L.append(md_table(["Pair", "Ratio", "AA body text (4.5)", "Use"],
                      [[n, f"{contrast(a, c):.1f}:1", "pass" if contrast(a, c) >= 4.5 else "fail", u] for n, a, c, u in pairs]))
    L.append("\nRed / amber stay reserved for status. Cyan is used only as a fill (planned receipts, P10–P90 band, sidebar marker).\n")

    L.append("## 7. Controls — full list with defaults and sources\n")
    for g, name in CT.GROUPS.items():
        L.append(f"### {g}) {name}\n")
        L.append(md_table(["ID", "Control", "Default", "Unit", "Range", "Source", "Ref"],
                          [[c["id"].upper(), c["label"], c["default"], c["unit"],
                            (f"{c['lo']}–{c['hi']}" if c["kind"] != "select" else "/".join(c["options"])), c["src"], c["ref"]]
                           for c in CT.REGISTRY if c["group"] == g]))
        L.append("")
    L.append("Presets: " + "; ".join(f"**{p['name']}** — {p['note']}" for p in CT.PRESETS.values()) + "\n")

    L.append("## 8. Handoff to prompt 2 (Inventory)\n")
    L.append("""**Data model (already loaded by `app/data.py`)**: `inventory_weekly` (depot × flavor × week: opening, receipts, transfers,
sold, discounted, written off, closing, stock under 60 days left, P50/P80 week, days of cover, status, report received),
`stock_batches_weekly` (batch ages, MT/QC acceptance), `writeoffs_discounts_weekly`, `transfers`, `depots` (region, size weight,
QC tilt), `demand_weekly` (ordered / sold / lost by channel), `qc_sellthrough_daily` (with out-of-stock flags), `forecast_monthly`
(the old plan). Never read `data/v2/_hidden/`.

**Extension points (keep these signatures)**
- `engine/inventory_iface.fg_position(w, ctl)` → per flavor: on hand, MT/QC-eligible share, cover. *Replace the national pooling with depot rows.*
- `engine/inventory_iface.supply_to_fg(w, ctl, sim)` → national run-out date from pulp-limited production. *Allocate `sim["made"]` to depots.*
- `engine/forecast.depot_forecast(w, ctl, weeks)` → depot × flavor P50, finished-goods percentile (f04 with depot error f01) and P80, with shrinkage shares and the DP prior.
- `engine/supply.balance(w, ctl)["planned"]` → daily `made` (bottles by flavor) and `plan`, the supply side of any depot projection.
- `engine/reviews.record / annotate` → transfer and allocation candidates go through the same review queue.
- `engine/readme._items` → add an "Inventory" source; the "Inventory (prompt 2)" group already exists.
- Control group **g** (g01 shelf life, g02 MT/QC days left, g04 depot cover target) is in place; add transfer and allocation controls as g08+.
- Template: `templates/inventory.html` card `#handoff` is the placeholder to replace.

**Deferred to prompt 2 (not built here)**: cover targets by velocity and variability instead of a flat 21 days (spec 5.4); allocation of
scarce stock by cover gap; transfer candidates (2–4 days, ₹1.50, MT/QC 60-day rule, demand evidence at the destination); estimated stock
between weekly reports (spec 5.3); age-risk flags and age-aware pre-build (R27); the regional MPB/GC imbalance replay (A24); a
depot-level Supply → Inventory lag.

**Inventory issues noticed**
- The sample's finished-goods lag is short: PP depot stock drains within ~3 weeks of the closure start because production is cut 90% at
  once and depot cover going in is only ~11 days (a real 21-day cover would last longer).
- Dragon Passion launched with a 3% depot allocation against ~12% demand, so DP is out of stock at most depots by 9 March — before the
  viral reel (G21, F46). This is the cover-rule root cause, separate from the spike and the highway.
- `inventory_weekly.days_of_cover` is measured against the P50 forecast; measured against actual sales, North and West hold MPB/GC overstock
  (the ₹6 Cr write-off story). Prompt 2 should choose and label the basis.
- Data quality: a ×10 closing-stock reading (D_W2 MPB, week of 12 Aug 2024) breaks the ledger; one missing report (D_E1, week of 3 Feb 2025);
  one quick-commerce one-day blip (D_N1 GC, 21 Apr 2026). All are shown, not corrected.
- The depot cover target and transfer cost are now controls (g04, a08); the old constants in `data.py` remain only as defaults.
""")
    (DOCS / "PROMPT1_NOTES.md").write_text("\n".join(L), encoding="utf-8")
    print("wrote", DOCS / "PROMPT1_NOTES.md", DOCS / "controls.csv", DOCS / "risk_register.csv")


if __name__ == "__main__":
    main()
