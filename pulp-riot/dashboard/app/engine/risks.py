"""
risks.py - the raw-material risk register, evaluated as of a week.

R01-R18 come from the handoff (PulpSense_Raw_Material_Supply_Risks_Handoff.md, section 3).
R19-R27 are added in prompt 1 (failure modes the handoff did not list).
Each rule returns: status (Triggered / Watch / Structural / Clear / Not evaluable), the evidence with numbers,
first unsafe day, fastest lever and the lead-time gap, a severity and a time bucket for READ_ME.
"""
from datetime import timedelta
from functools import lru_cache

from ..data import store
from . import forecast as F
from .copacker import evaluate as copacker
from .inventory_iface import fg_position
from .supply import balance, closures, lead_gap, _closed

REGISTER = [
    # id, name, flavors, evidence basis, owner, agreed response
    ("R01", "Mango shortage / processor disruption", "MPB", "Case exposure (F73)", "Procurement", "Check inbound, qualified alternates; then reallocate (pathway A)"),
    ("R02", "Peach supply shortfall / hill-region disruption", "MPB", "Case exposure (F74)", "Procurement", "Inspect inbound dates and alternates; then reallocate"),
    ("R03", "Fresh basil shortage / extraction bottleneck", "MPB", "Case input (F75); conditional", "Production", "Verify usable output, then reallocate"),
    ("R04", "One of two guava suppliers stops dispatching", "GC", "Case structure (F76); disruption hypothetical", "Procurement", "Confirmed pipeline + supplier-2 ramp (pathway B)"),
    ("R05", "Both guava suppliers fail or backup cannot ramp", "GC", "Conditional", "Procurement", "Partial / full substitution-led reallocation"),
    ("R06", "Passionfruit supply interruption / highway closure", "PP, DP", "Case-confirmed (F41, F42, F55)", "Procurement", "Project stock-outs; transport and supply contingencies"),
    ("R07", "Passionfruit competition between PP and DP", "PP, DP", "Case-confirmed (F58, F78)", "Production", "Joint allocation with service floors (pathway C)"),
    ("R08", "Imported dragonfruit delay / quarterly timing", "DB, DP", "Case-confirmed (F16, F17)", "Procurement", "Reconcile stock, ETA, domestic supply"),
    ("R09", "Domestic dragonfruit capacity gap", "DB, DP", "Conditional (F14 is a mix, not a cap)", "Procurement", "Ask for verified extra domestic supply"),
    ("R10", "Dragonfruit competition between DB and DP", "DB, DP", "Inferred from shared ingredient (F78)", "Production", "Joint allocation"),
    ("R11", "Passionfruit and dragonfruit short together", "PP, DB, DP", "Conditional compound", "COO", "Two-ingredient joint allocation"),
    ("R12", "Pipeline visibility: shipments not really deliverable", "All", "Conditional", "Procurement", "Count confirmed in-transit only; recheck ETAs"),
    ("R13", "Demand shock exhausts pulp faster than forecast", "All, esp. DP", "Case viral spike (F53)", "Planning", "Daily channel signal recalculates requirements"),
    ("R14", "Production bottleneck / capacity", "All", "Case 95% utilisation, fixed lines (F19, F33)", "Production", "Verify flexible capacity; co-packer rule"),
    ("R15", "Shelf-life, quality or cold-storage unusability", "All", "Case shelf life (F37-F39)", "Production", "Usable-stock filters"),
    ("R16", "Expedited freight / spot purchase cost", "All, esp. PP/DP", "Case air freight (F56, F57)", "COO", "Compare contribution exposure with premium"),
    ("R17", "Late marketing-procurement coordination", "All, esp. DP", "Case 2-week notice (F36), monthly cycle (F27)", "Planning", "Earlier S&OP trigger"),
    ("R18", "Missing supplier capacity, recipe, route, transfer data", "All", "Known model limitation", "Planning", "Show review candidates with confidence warnings"),
    # new in prompt 1
    ("R19", "Packaging shortage (bottles, caps, labels)", "All", "New, conditional (G25)", "Procurement", "Packaging cover alongside pulp cover"),
    ("R20", "Pulp lot fails quality and is quarantined", "All", "New, conditional (G26)", "Production", "Usable stock excludes quarantined lots"),
    ("R21", "Cold-chain or power failure in plant cold storage", "All", "New, conditional (G26)", "Production", "Backup power; split stock across rooms"),
    ("R22", "Plant breakdown at peak", "All", "New, conditional (G27)", "Production", "Capacity loss scenario; co-packer rule"),
    ("R23", "Import price / FX spike on dragonfruit", "DB, DP", "New, conditional (G28)", "Procurement", "Price exposure on open import orders"),
    ("R24", "Supplier concentration", "PP, DP", "Derived from supplier table (F35, F76, F14)", "Procurement", "Second-source programme"),
    ("R25", "Co-packer volume needs the same scarce pulp", "All", "New, inferred (F20-F22, G12)", "Production", "Co-packer rule checks pulp before capacity"),
    ("R26", "One monsoon event hits peach and passionfruit together", "MPB, PP, DP", "New, conditional (F74, F77)", "Procurement", "Check peach cover whenever the passionfruit road closes"),
    ("R27", "Pre-built finished goods age past the 60-day cutoff", "All", "New, interface to Inventory (F38, F39)", "Planning", "Prompt 2: age-aware pre-build"),
    # new in prompt 2 (inventory module)
    ("R28", "Transfers drain senders below the depot cover target", "All", "Teammate feed (F45)", "Supply chain manager",
     "Flag below-target senders on every transfer; review before approval"),
    ("R29", "Rebalancing leaves receivers overstocked once the shortage passes", "MPB, GC, PP", "Teammate feed", "Planning",
     "Overstock & aging view; age risk vs 30 saleable days"),
    ("R30", "Inventory feed integrity (stock not conserved, unreported rows)", "DP, PP, all", "Teammate feed", "Planning",
     "Shown, not corrected; questions to the teammate"),
    ("R31", "Rebalancing optimiser is offline and cannot be re-run", "All", "Teammate feed", "Planning",
     "Precomputed transfers; optimiser controls locked; greedy replica as evidence"),
]
META = {r[0]: dict(id=r[0], name=r[1], skus=r[2], basis=r[3], owner=r[4], response=r[5]) for r in REGISTER}


def _bucket(days):
    if days is None:
        return "Later"
    return "Immediate" if days <= 7 else ("Soon" if days <= 28 else "Later")


def _sev(status, days, gap=None):
    if status == "Triggered":
        return "High" if (days is not None and days <= 14) or (gap is not None and gap < 0) else "Medium"
    if status in ("Watch", "Structural"):
        return "Medium" if days is not None and days <= 28 else ("Medium" if status == "Structural" else "Low")
    return "Low"


@lru_cache(maxsize=64)
def evaluate(w, ctl):
    s = store()
    K = w + timedelta(7)
    B = balance(w, ctl)
    sim, stress, conf_only = B["planned"], B["stress"], B["confirmed_only"]
    ing = sim["ing"]
    out = []

    def add(rid, status, evidence, days=None, ingredient=None, link="/risk", extra=None):
        r = dict(META[rid])
        gap, lever = (None, None)
        if ingredient:
            gap, lever = lead_gap(w, ctl, ingredient, ing[ingredient])
        r.update(status=status, evidence=evidence, days=days, gap=gap, lever=lever, ingredient=ingredient, link=link,
                 first_unsafe=ing[ingredient]["first_unsafe"] if ingredient else None)
        r["severity"] = _sev(status, days, gap)
        r["bucket"] = _bucket(days) if status in ("Triggered", "Watch") else "Later"
        r.update(extra or {})
        out.append(r)

    def unsafe_rule(rid, i, extra_txt=""):
        r, st = ing[i], stress["ing"][i]
        if r["first_unsafe"]:
            out_ = f" (runs out {r['first_out']:%d %b})" if r["first_out"] else ""
            add(rid, "Triggered", f"{i.capitalize()} falls below its {ctl['g05']:.0f}-day buffer on {r['first_unsafe']:%d %b}"
                                  f"{out_}." + extra_txt, r["days_to_unsafe"], i)
        elif st["first_unsafe"]:
            add(rid, "Watch", f"At P{int(ctl['f03'])} demand {i} falls below its buffer on {st['first_unsafe']:%d %b}; "
                              f"fine at P{int(ctl['f04'])}. Cover {r['cover'] or 0:.1f} days." + extra_txt, st["days_to_unsafe"], i)
        elif r["cover"] is None:
            add(rid, "Clear", f"No {i} in the current recipe (d02-d04)." + extra_txt, None, i)
        else:
            add(rid, "Clear", f"{i.capitalize()} cover {r['cover']:.1f} days; above its buffer for {int(ctl['g06'])} days." + extra_txt, None, i)

    # --- pathway A
    out_txt = f" Outage scenario b06 = {ctl['b06']:.0f} days." if ctl["b06"] > 0 else ""
    unsafe_rule("R01", "mango", out_txt)
    unsafe_rule("R02", "peach", out_txt)
    unsafe_rule("R03", "basil", out_txt)

    # --- pathway B
    g = ing["guava"]
    if ctl["b04"] > 0:
        st = "Triggered" if g["first_unsafe"] else "Watch"
        add("R04", st, f"Supplier 1 stops for {ctl['b04']:.0f} days (scenario b04). "
                       + (f"Guava below buffer on {g['first_unsafe']:%d %b}." if g["first_unsafe"] else "Stock + pipeline bridge the gap."),
            g["days_to_unsafe"], "guava", link="/risk#ladder")
        need = ctl["b05"] * g["avg_use"]
        if ctl["c01"] < need:
            add("R05", "Triggered" if g["first_unsafe"] else "Watch",
                f"Supplier 2 confirmed extra {ctl['c01']:,.0f} kg/day vs {need:,.0f} kg/day lost.", g["days_to_unsafe"], "guava", link="/risk#ladder")
        else:
            add("R05", "Clear", f"Supplier 2 confirmed {ctl['c01']:,.0f} kg/day covers the {need:,.0f} kg/day lost.", None, "guava")
    else:
        add("R04", "Clear", "No supplier stoppage reported. Split between suppliers unknown (G06).", None, "guava")
        add("R05", "Not evaluable", "Supplier-2 spare capacity not known (G29).", None, "guava")

    # --- pathway C
    pf, df = ing["passionfruit"], ing["dragonfruit"]
    wins = closures(w, ctl)
    closed_now = _closed(K, wins)
    hyp = [c for c in wins if c["kind"] == "hypothetical"]
    if closed_now or hyp or pf["first_unsafe"]:
        txt = []
        for c in wins:
            txt.append(f"Closure {c['start']:%d %b}–{c['end']:%d %b} ({c['note']}).")
        if pf["first_unsafe"]:
            txt.append(f"Passionfruit below buffer {pf['first_unsafe']:%d %b}, runs out {pf['first_out']:%d %b}." if pf["first_out"]
                       else f"Passionfruit below buffer {pf['first_unsafe']:%d %b}.")
        add("R06", "Triggered", " ".join(txt), 0 if closed_now else (pf["days_to_unsafe"] if pf["first_unsafe"] else 0), "passionfruit")
    else:
        add("R06", "Watch" if pf["cover"] and pf["cover"] < ctl["b02"] + ctl["g05"] else "Clear",
            f"Road open. Cover {pf['cover']:.1f} days vs a {ctl['b02']:.0f}-day closure + {ctl['g05']:.0f}-day buffer; "
            f"closures in {ctl['b03']:.0f} of the last 5 summers (F42).", None, "passionfruit")
    pp_short, dp_short = sim["short"]["PP"], sim["short"]["DP"]
    db_short = sim["short"]["DB"]
    if pf["first_out"] and (pp_short > 0 or dp_short > 0):
        add("R07", "Triggered", f"Pulp-limited shortfall over {int(ctl['g06'])} days: PP {pp_short:,.0f}, DP {dp_short:,.0f} bottles. "
                                "See the allocation comparison.", pf["days_to_out"], "passionfruit", link="/risk#options")
    else:
        add("R07", "Clear", "Passionfruit covers both PP and DP over the horizon.", None, "passionfruit")
    imp_over = [e for e in sim["excluded"] if e["ing"] == "dragonfruit" and "overdue" in e["why"]]
    imp_open = [c for c in sim["conf"] if c["ing"] == "dragonfruit" and c["mode"] == "sea"]
    if imp_over or (ctl["a09"] > 0 and df["first_unsafe"]):
        add("R08", "Triggered", (f"{len(imp_over)} import order(s) overdue and not counted. " if imp_over else "")
            + (f"Sea orders delayed {ctl['a09']:.0f} days (scenario). " if ctl["a09"] > 0 else "")
            + (f"Dragonfruit below buffer {df['first_unsafe']:%d %b}." if df["first_unsafe"] else ""), df["days_to_unsafe"], "dragonfruit")
    elif df["first_unsafe"]:
        add("R08", "Watch", f"Dragonfruit below buffer {df['first_unsafe']:%d %b}; {len(imp_open)} import order(s) on the water. "
                            f"A new order takes {ctl['a02']:.0f}–{ctl['a03']:.0f} days.", df["days_to_unsafe"], "dragonfruit")
    else:
        add("R08", "Clear", f"Dragonfruit covered for {int(ctl['g06'])} days; {len(imp_open)} import order(s) on the water.", None, "dragonfruit")
    add("R09", "Not evaluable" if ctl["c03"] <= 0 else ("Watch" if df["first_unsafe"] else "Clear"),
        "Domestic spare capacity not confirmed (G30). The 60% domestic share is a sourcing mix (F14), not a ceiling."
        if ctl["c03"] <= 0 else f"Confirmed extra domestic dragonfruit {ctl['c03']:,.0f} kg/day.", df["days_to_unsafe"], "dragonfruit")
    if df["first_out"] and (db_short > 0 or dp_short > 0):
        add("R10", "Triggered", f"Dragonfruit-limited shortfall: DB {db_short:,.0f}, DP {dp_short:,.0f} bottles.", df["days_to_out"],
            "dragonfruit", link="/risk#options")
    else:
        add("R10", "Clear", "Dragonfruit covers both DB and DP over the horizon.", None, "dragonfruit")
    both = pf["first_out"] and df["first_out"]
    add("R11", "Triggered" if both else ("Watch" if (pf["first_unsafe"] and df["first_unsafe"]) else "Clear"),
        "Both pulps short inside the horizon: allocate PP, DB and DP together." if both else
        ("Both below buffer inside the horizon." if pf["first_unsafe"] and df["first_unsafe"] else "Not both at once."),
        min([d for d in (pf["days_to_unsafe"], df["days_to_unsafe"]) if d is not None], default=None), None)

    # --- cross-cutting
    excl = sim["excluded"]
    add("R12", "Watch" if excl else "Clear",
        (f"{len(excl)} open order(s) not counted as supply: " + "; ".join(f"{e['ing']} {e['kg']:,.0f} kg ({e['why']})" for e in excl[:3]))
        if excl else f"All {len(sim['conf'])} open orders have a future ETA and are counted.", None, None, link="/risk#pipeline")
    al = [a for a in F.alerts(w, ctl) if a["active"]]
    if al or ctl["b11"] != "none":
        add("R13", "Triggered", "; ".join(f"{a['sku']} quick commerce {a['ratio']:.1f}x baseline since {a['start']:%d %b} ({a['cls']})" for a in al)
            + (f" Scenario shock: {ctl['b11']} x{ctl['b12']:g} (b11-b13)." if ctl["b11"] != "none" else ""), 0, None, link="/forecast")
    else:
        add("R13", "Clear", "No active quick-commerce alert.", None, None, link="/forecast")
    cs = sim["cap_short"]
    over = next((d for d, t, c in zip(sim["days"], sim["tot"], sim["cap"]) if t > c), None)
    util = float(s.util_w.get(w, 0) or 0)
    if cs > 0:
        add("R14", "Triggered", f"Forecast (P{int(ctl['f04'])}) above plant capacity from {over:%d %b}: {cs / 1e5:,.1f} L bottles over "
                                f"{int(ctl['g06'])} days. Plants {util:.0%} utilised last week.", (over - K).days, None, link="/copacker")
    else:
        add("R14", "Watch" if util >= 0.95 else "Clear", f"Plants {util:.0%} utilised last week; forecast within capacity.", None, None)
    inv = s.inv[(s.inv.week_start == w) & s.inv.report_received]
    aged = float(inv.stock_under_60_days_left.sum()) / max(float(inv.closing_stock.sum()), 1)
    add("R15", "Watch" if aged > 0.2 else "Clear",
        f"{aged:.0%} of depot stock has under {ctl['g02']:.0f} days of shelf life left. Pulp lot ages are not in the data, so "
        "pulp usability is not tested (G26).", None, None, link="/inventory")
    air = s.po[(s.po["mode"] == "air") & (s.po.order_date <= K) & (s.po.order_date >= K - timedelta(28))]
    add("R16", "Triggered" if len(air) else "Clear",
        f"Air freight booked in the last 4 weeks: ₹{air.freight_cost_inr.fillna(0).sum() / 1e7:.1f} Cr." if len(air)
        else "No emergency freight in the last 4 weeks.", 0 if len(air) else None, None, link="/transportation")
    add("R17", "Structural", f"Launch notice to procurement is {ctl['f22']:.0f} days (F36) but imported dragonfruit takes "
                             f"{ctl['a02']:.0f}–{ctl['a03']:.0f} days (F16): a launch that needs imports cannot be supplied on time.",
        None, None)
    add("R18", "Watch", "No verified supplier spare capacity (G29-G32), recipe (G05, G06), plant-to-depot lanes (G02), pulp "
                        "price (G33) or substitution data. Recommendations carry these as assumptions.", None, None, link="/data")

    # --- new risks
    add("R19", "Triggered" if ctl["b10"] > 0 else "Not evaluable",
        f"Scenario: packaging short by {ctl['b10']:.0%} of capacity (b10)." if ctl["b10"] > 0 else
        "No packaging stock or supplier data (G25). Use b10 to test.", 0 if ctl["b10"] > 0 else None, None)
    add("R20", "Triggered" if ctl["b09"] > 0 else "Not evaluable",
        f"Scenario: {ctl['b09']:.0%} of pulp on hand held (b09)." if ctl["b09"] > 0 else
        "No lot-quality or quarantine records (G26). Use b09 to test.", 0 if ctl["b09"] > 0 else None, None)
    add("R21", "Triggered" if ctl["b09"] > 0 else "Not evaluable",
        f"Scenario: {ctl['b09']:.0%} of pulp on hand lost (b09)." if ctl["b09"] > 0 else
        "No cold-storage incident or capacity data (G08, G26). Use b09 to test.", 0 if ctl["b09"] > 0 else None, None)
    add("R22", "Triggered" if ctl["b07"] > 0 and ctl["b08"] > 0 else "Not evaluable",
        f"Scenario: {ctl['b07']:.0%} of capacity lost for {ctl['b08']:.0f} days (b07, b08)." if ctl["b07"] > 0 and ctl["b08"] > 0 else
        "No breakdown history (G27). Use b07 and b08 to test.", 0 if ctl["b07"] > 0 and ctl["b08"] > 0 else None, None)
    open_kg = sum(c["kg"] for c in imp_open)
    add("R23", "Watch" if ctl["b14"] != 0 else "Not evaluable",
        f"Scenario: import price {ctl['b14']:+.0%} on {open_kg:,.0f} kg on the water; ₹ impact needs the import price (G28)."
        if ctl["b14"] != 0 else f"{open_kg:,.0f} kg of imported dragonfruit on the water; price and currency terms not in the case (G28).",
        None, None)
    add("R24", "Structural", "Passionfruit: 1 cooperative, 1 road (F35, F41) feeding PP and half of DP; dragonfruit: 40% from one "
                             "import lane at 6-8 weeks (F15, F16); guava: 2 suppliers (F76).", None, "passionfruit")
    cp = copacker(w, ctl)
    a_ok = cp["checks"][0]["ok"]
    b_ok = cp["checks"][1]["ok"]
    add("R25", "Triggered" if a_ok and b_ok is False else "Clear",
        "Demand is above plant capacity, but the co-packer would need pulp that is not there: " + "; ".join(cp["reasons"][-1:])
        if a_ok and b_ok is False else "The co-packer rule checks pulp before capacity.", 0 if a_ok and b_ok is False else None, None,
        link="/copacker")
    pe = ing["peach"]
    if closed_now or hyp:
        add("R26", "Watch", f"Passionfruit road closure in play; peach (hill-state orchards, F74) cover {pe['cover']:.0f} days vs a "
                            f"{ctl['b02']:.0f}-day closure. Same-region exposure is an inference: the case does not say they share a road.",
            None, "peach")
    else:
        add("R26", "Clear", "No passionfruit closure in play.", None, "peach")
    fg = fg_position(w, ctl)
    win = ctl["g01"] - ctl["g02"]
    long_ = [f"{k} {v['cover']:.0f} d" for k, v in fg.items() if v["cover"] and v["cover"] > win]
    add("R27", "Watch" if long_ else "Clear",
        (f"National stock above the {win:.0f}-day MT/QC window: {', '.join(long_)}. Pre-building more would age. Prompt 2." if long_
         else f"No flavor holds more than {win:.0f} days nationally."), None, None, link="/inventory")
    # --- prompt 2: inventory module (the feed is a retrospective replay; counts cover transfers recommended so far)
    from . import inventory as INV
    _, tf = INV.frame(ctl)
    tk = tf[tf.ws <= w]
    below = int((tk.cover_days_sender < ctl["g04"]).sum())
    add("R28", "Watch" if below else "Clear",
        f"{below} of {len(tk)} transfers so far take stock from senders below the {ctl['g04']:.0f}-day target (g04)." if len(tk)
        else "No transfers recommended yet.", None, None, link="/rebalance#transfers")
    ov = INV.overstock("all", ctl)
    add("R29", "Watch" if ov["after"]["n"] > ov["before"]["n"] else "Clear",
        f"Depot-weeks over {ctl['h03']:.0f} days: {ov['before']['n']} before, {ov['after']['n']} after rebalancing (whole file).",
        None, None, link="/overstock")
    con, rc = INV.conservation(), INV.reconcile()
    add("R30", "Triggered", f"Replay creates {con['total']:,.0f} bottles (DP +{con['dp_mode']:,.0f} a week from {con['dp_from']:%d %b %Y}); "
                            f"{len(rc['exceptions'])} unreported rows keep ₹{rc['exc_loss'] / 1e7:.3f} Cr of loss.", None, None, link="/rebalance#check")
    rp = INV.replicate()
    add("R31", "Structural", f"A transparent greedy rule reproduces {rp['exact'][0]} of {rp['exact'][1]} transfers (receivers "
                             f"{rp['receivers'][0]}/{rp['receivers'][1]}, senders {rp['senders'][0]}/{rp['senders'][1]}); below the "
                             f"{rp['tolerance']:.0%} tolerance, so optimiser controls are locked.", None, None, link="/rebalance#replication")
    return out


def summary(rs):
    c = {}
    for r in rs:
        c[r["status"]] = c.get(r["status"], 0) + 1
    return c
