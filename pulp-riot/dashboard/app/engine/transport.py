"""
transport.py - transport fragility, flags and the compare-and-choose for the fragile lane.

Fragility is judged lane by lane on explicit tests (no opaque score):
    single route (F41) · disruptions on record (b03 of 5, F42) · lead time vs plant cover (a12)
    · on-time rate, last 13 weeks (a11) · ordering frequency (F17)
Level: High if single route with disruptions on record, or lead time above plant cover;
       Medium if any other test fails; Low otherwise; "Not evaluable" where the case gives no lane (G02).
"""
from datetime import timedelta
from functools import lru_cache

from ..data import store
from .supply import _closed, balance, closures, landslide_months, normal_freight_per_kg

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


@lru_cache(maxsize=64)
def fragility(w, ctl):
    s = store()
    K = w + timedelta(7)
    base = balance(w, ctl)["planned"]["ing"]
    tr = s.transportation(w)
    by = {l["name"]: l for l in tr["lanes"]}
    wins = closures(w, ctl)
    closed_now = _closed(K, wins)
    season = landslide_months()
    in_season = K.month in season or (K + timedelta(28)).month in season

    def lane(name, key, ing, single, disrupt, lead, freq, src):
        l = by.get(key, {})
        cover = base[ing]["cover"] if ing else None
        tests = []
        tests.append(("Single route or source", single, src))
        tests.append(("Disruptions on record", disrupt, "F42 (b03)" if disrupt else "none in the case"))
        lr = (lead / cover) if (cover and lead is not None) else None
        tests.append((f"Lead time vs plant cover (flag above {ctl['a12']:.0%})", lr is not None and lr > ctl["a12"],
                      f"{lead:g} d vs {cover:.0f} d cover" if lr is not None else "–"))
        ot = l.get("on_time")
        tests.append((f"On time, last 13 weeks (flag below {ctl['a11']:.0%})", ot is not None and ot < ctl["a11"],
                      f"{ot:.0%} of {l.get('n', 0)}" if ot is not None else "no deliveries"))
        tests.append(("Infrequent ordering", freq == "quarterly", freq))
        if (single and disrupt) or (lr is not None and lr > 1):
            level = "High"
        elif any(t[1] for t in tests):
            level = "Medium"
        else:
            level = "Low"
        return dict(name=name, level=level, tests=tests, cover=cover, lead=lead, on_time=ot, late=l.get("late", 0),
                    blocked=l.get("blocked", 0))

    lanes = [
        lane("Passionfruit cooperative → plants (road)", "Passionfruit cooperative → plants", "passionfruit", True,
             ctl["b03"] > 0, ctl["a01"], "weekly", "F35, F41"),
        lane("Imported dragonfruit → plants (sea)", "Imported dragonfruit → plants", "dragonfruit", False, False,
             ctl["a03"], "quarterly", "F16, F17"),
        lane("Domestic dragonfruit → plants (road)", "Domestic dragonfruit → plants", "dragonfruit", False, False,
             ctl["a04"], "weekly", "G07"),
        lane("Mango, peach, basil → plants (road)", "Mango, peach, basil → plants", "mango", False, False,
             ctl["a04"], "weekly", "G07"),
        lane("Guava, 2 suppliers → plants (road)", "Guava (2 suppliers) → plants", "guava", False, False,
             ctl["a04"], "weekly", "F76, G07"),
    ]
    lanes.append(dict(name="Plants → depots", level="Not evaluable", tests=[("Mode, lead time and cost", None, "not in the case (G02)")],
                      cover=None, lead=None, on_time=None, late=0, blocked=0))
    lanes.append(dict(name="Depot ↔ depot transfers", level="Low", tests=[("Lead time", False, f"{ctl['a07']:g} days (F49)"),
                                                                          ("Cost", False, f"₹{ctl['a08']:g}/bottle (F50)")],
                      cover=None, lead=ctl["a07"], on_time=None, late=0, blocked=0))

    flags = []
    pf = base["passionfruit"]
    if closed_now:
        c = [x for x in wins if x["start"] <= K <= x["end"]][0]
        flags.append(dict(sev="High", text=f"Passionfruit highway closed: {c['note']}.", ref="F41, F55"))
    if in_season and pf["cover"] is not None and pf["cover"] < ctl["b02"] + ctl["g05"]:
        flags.append(dict(sev="High" if not closed_now else "Medium",
                          text=f"Landslide season ({', '.join(MONTHS[m - 1] for m in season)} on record): passionfruit cover "
                               f"{pf['cover']:.0f} days is below a {ctl['b02']:.0f}-day closure + {ctl['g05']:.0f}-day buffer.",
                          ref="F42, F43, b02, g05"))
    sea = [c for c in balance(w, ctl)["planned"]["excluded"] if "overdue" in c["why"]]
    if sea:
        flags.append(dict(sev="Medium", text=f"{len(sea)} open order(s) overdue and not counted as supply: "
                                             + "; ".join(f"{c['ing']} {c['kg']:,.0f} kg ({c['why']})" for c in sea[:3]), ref="R12"))
    ns = [c for c in balance(w, ctl)["planned"]["excluded"] if "not shipped" in c["why"]]
    if ns:
        flags.append(dict(sev="High", text=f"{len(ns)} passionfruit order(s) not shipped because the road is closed.", ref="R06"))
    for l in lanes:
        if l["on_time"] is not None and l["on_time"] < ctl["a11"]:
            flags.append(dict(sev="Medium", text=f"{l['name']}: {l['on_time']:.0%} on time over 13 weeks.", ref="a11"))
    if ctl["a09"] > 0 or ctl["a10"] > 0:
        flags.append(dict(sev="Medium", text=f"Scenario: sea orders +{ctl['a09']:.0f} days, road orders +{ctl['a10']:.0f} days.", ref="a09, a10"))
    return dict(lanes=lanes, flags=flags, season=season, in_season=in_season, closed_now=closed_now)


@lru_cache(maxsize=64)
def mitigation(w, ctl):
    """Compare and choose: protecting the passionfruit lane against a b02-day closure."""
    pf = balance(w, ctl)["planned"]["ing"]["passionfruit"]
    use = pf["avg_use"]
    need_days = ctl["b02"] + ctl["g05"]
    have = ctl["e03"]                                     # cover procurement normally holds
    gap_days = max(0.0, need_days - have)
    nf, nf_src = normal_freight_per_kg(ctl)
    K = w + timedelta(7)
    season = landslide_months()
    nxt = min([K.replace(month=m, day=1) if m >= K.month else K.replace(year=K.year + 1, month=m, day=1) for m in season],
              default=K)
    hold = max(0, (nxt - K).days) + ctl["b02"]          # oldest pre-built pulp: built now, used at the end of a closure
    ages_ok = hold <= ctl["g03"]
    air_days = max(0.0, ctl["b02"] - ctl["a05"])
    air_kg = min(ctl["c04"] * air_days, gap_days * use)
    air_cover = air_kg / use if use else 0
    opts = [
        dict(key="none", name="Rely on today's cover target", protects=have, cost=0.0, cost_txt="₹0", lead="–", feasible=True,
             evidence="Given/Derived", depends="–",
             why=f"{have:.1f} days (e03) against a {ctl['b02']:.0f}-day closure: short by {gap_days:.1f} days"),
        dict(key="prepos", name=f"Pre-position pulp before landslide season: hold {need_days:.0f} days",
             protects=need_days, cost=None, cost_txt="storage + working capital: not quantified (pulp price G33, cold-storage room G08)",
             lead="weeks before season", feasible=ctl["c05"] > 0 and ages_ok,
             evidence=f"Given: frozen pulp keeps {ctl['g03']:.0f} days (F37, g03); held up to {hold:.0f} days here",
             depends=f"cooperative must confirm ~{gap_days * use:,.0f} kg extra (c05 = {ctl['c05']:,.0f} kg/day)",
             why=("pulp would be held longer than its frozen life (g03)" if not ages_ok else
                  "" if ctl["c05"] > 0 else "conditional: the cooperative has not confirmed surge volume (c05 = 0)")),
        dict(key="air", name="Pre-agreed air-freight trigger (contract, not spot)", protects=have + air_cover,
             cost=air_kg * nf * (ctl["a06"] - 1), cost_txt=None, lead=f"{ctl['a05']:g} days after the trigger",
             feasible=ctl["c04"] > 0, evidence="Given: 5x cost (F57); capacity Assumed (c04)",
             depends=f"air capacity {ctl['c04']:,.0f} kg/day (c04, Assumed)", why=""),
        dict(key="both", name="Pre-position + air trigger as backup", protects=max(need_days, have + air_cover),
             cost=0.0, cost_txt="pre-positioning cost (not quantified); air only if a closure outlasts the stock",
             lead="weeks before season", feasible=ctl["c05"] > 0 and ctl["c04"] > 0 and ages_ok,
             evidence="F37, F57", depends="c05 and c04 confirmed",
             why="" if ctl["c05"] > 0 else "conditional on cooperative surge volume (c05 = 0)"),
        dict(key="route", name="Alternative road route", protects=None, cost=None, cost_txt="–", lead="–", feasible=False,
             evidence="Given: none exists (F41)", depends="–", why="no alternative road (F41)"),
        dict(key="supplier", name="Qualify a second passionfruit supplier in another region", protects=None, cost=None, cost_txt="–",
             lead="months", feasible=False, evidence="Given: none qualified (F35)", depends="qualification project",
             why="medium-term; start now, cannot act this season"),
    ]
    for o in opts:
        if o["cost"] is not None and o["cost_txt"] is None:
            o["cost_txt"] = f"₹{o['cost'] / 1e7:,.2f} Cr premium" + (f" ({nf_src})" if nf else "")
        o["full"] = o["protects"] is not None and o["protects"] >= need_days
    # choose: feasible options that fully protect; else the one that protects most; conditional ones kept visible
    feas = [o for o in opts if o["feasible"] and o["protects"] is not None]
    full = [o for o in feas if o["full"]]
    win = (min(full, key=lambda o: (o["cost"] if o["cost"] is not None else 0)) if full
           else (max(feas, key=lambda o: o["protects"]) if feas else None))
    # if the best option is only conditional (pre-positioning needs a confirmation), say so
    cond = next((o for o in opts if o["key"] == "both"), None)
    for o in opts:
        o["winner"] = win is not None and o["key"] == win["key"]
    rec = None
    if win and win["key"] != "none":
        rec = dict(id=f"TR-{w.isoformat()}-{win['key']}", title=f"Passionfruit lane: {win['name']}", module="Transportation",
                   owner="Procurement", detail=f"Protects {win['protects']:.0f} of {need_days:.0f} days needed. {win['cost_txt']}.")
    return dict(options=opts, winner=win, need_days=need_days, have=have, gap_days=gap_days, use=use, rec=rec,
                conditional=cond, nf=nf, nf_src=nf_src)
