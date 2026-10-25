"""
check_prompt1.py - the prompt-1 acceptance checks, rerunnable.

    python code/check_prompt1.py            (about 3-5 minutes: every control is perturbed)

Writes docs/acceptance_prompt1.csv and docs/control_sensitivity.csv and prints a summary.
Checks
  1 every control and every risk carries a source tag and a reference
  2 no parameter is hard-coded: perturbing each control changes at least one engine output
  3 the co-packer rule blocks use below the combined-plant threshold
  4 the March spike and May closure replays report detection dates and a lead over the month-end signal
  5 moving a Given value adds a READ_ME entry
  6 READ_ME shows known data issues and the new risks (R19-R27)
  7 inventory logic is separate (inventory_iface) and the prompt-2 placeholder is shown
  8 no accuracy claim from the sample data on the new pages
"""
import csv
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

from app.engine import controls as CT                     # noqa: E402
from app.engine import copacker as CP                     # noqa: E402
from app.engine import forecast as FC                     # noqa: E402
from app.engine import readme as RM                       # noqa: E402
from app.engine import risks as RK                        # noqa: E402
from app.engine import social as SO                       # noqa: E402
from app.engine import supply as SUP                      # noqa: E402
from app.engine import transport as TR                    # noqa: E402

DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)
results = []


def check(n, name, ok, detail):
    results.append(dict(n=n, check=name, result="pass" if ok else "FAIL", detail=detail))
    print(f"[{'pass' if ok else 'FAIL'}] {n}. {name}: {detail}")


def fingerprint(ctl, weeks):
    """A text summary of every engine output that a control could move."""
    out = []
    for w in weeks:
        B = SUP.balance(w, ctl)
        for k in ("planned", "stress", "confirmed_only"):
            for i, r in B[k]["ing"].items():
                out.append(f"{k}{i}{r['first_unsafe']}{r['first_out']}{r['open']:.0f}{r['closing'].sum():.0f}{r['planned'].sum():.0f}{r['safety']:.0f}")
            out.append(f"{k}{sum(B[k]['unmet'].values()):.0f}{B[k]['cap_short']:.0f}")
        m = SUP.mitigations(w, ctl)
        out += [f"{o['key']}{o.get('unmet')}{o.get('cost')}{o['why']}{o['note']}{o['feasible']}{o.get('winner')}" for o in m["options"]]
        g = SUP.guava_ladder(w, ctl)
        out += [g["verdict"]] + [s["d"] for s in g["steps"]]
        mp = SUP.mpb_check(w, ctl)
        out.append(f"{mp['limiting']}{mp['short']:.0f}{mp['switch']:.0f}")
        cp = CP.evaluate(w, ctl)
        out += [f"{c['ok']}{c['detail']}" for c in cp["checks"]] + [f"{cp['econ']['net_total']:.0f}"]
        fr = TR.fragility(w, ctl)
        out += [l["level"] + str(l["tests"]) for l in fr["lanes"]] + [f["text"] for f in fr["flags"]]
        tm = TR.mitigation(w, ctl)
        out += [f"{o['key']}{o['protects']}{o['cost']}{o['feasible']}{o['winner']}{o['why']}{o['evidence']}" for o in tm["options"]]
        nat = FC.national(w, ctl)
        out.append(f"{nat.p50.sum():.0f}{nat.p10.sum():.0f}{nat.p_raw.sum():.0f}{nat.p_fg.sum():.0f}")
        for a in FC.alerts(w, ctl):
            out.append(f"{a['sku']}{a['start']}{a['cls']}")
            if a["active"] and a["base"]:
                out += [f"{x['name']}{x['extra']:.0f}{x['warning']}" for x in SUP.demand_scenarios(w, ctl, a["sku"], float(a["base"]), float(a["ratio"]))]
        df = FC.depot_forecast(w, ctl)
        out.append(f"{df.p50.sum():.0f}{df.p_fg.sum():.0f}{df.p80.sum():.0f}")
        from app.data import store
        iv = store().inventory(w, None, "forecast", int(ctl["g04"]))
        out.append(str(iv["status"]["series"]) + str([c["cls"] for r in iv["heat"] for c in r["cells"] if c]))
        dv = store().distribution(w, int(ctl["g04"]), float(ctl["a08"]))
        out.append(f"{dv['kpi']['stranded']:.0f}{sum(m['cost'] for m in dv['mism']):.0f}")
        sh = FC.depot_shares(w, ctl)
        out += [f"{k}{v['share'].round(4).tolist()}" for k, v in sh.items() if v]
        d = SO.desk(w, ctl)
        out += [f"{r['sku']}{r['cls']}" for r in d["table"]] + [a["id"] + a["verdict"] for a in d["alerts"]]
        out += [r["status"] + r["evidence"] for r in RK.evaluate(w, ctl)]
        out += [x["title"] for x in RM.items(w, ctl)
                if not x["title"].startswith(("Departs from case", "Assumption changed"))]   # those list the change itself
        fg = SUP.balance(w, ctl)["planned"]
        from app.engine.inventory_iface import fg_position
        out += [f"{k}{v['mtqc_ok']:.0f}{v['cover']}" for k, v in fg_position(w, ctl).items()]
        out.append(str(len(fg["days"])))
    from app.engine import inventory as INV                      # prompt 2: the inventory module
    s = INV.summary("summer26", ctl)
    out.append(f"inv{s['before']:.0f}{s['after']:.0f}{s['transport']:.0f}")
    o = INV.overstock("all", ctl)
    out.append(f"ovs{o['before']['n']}{o['after']['n']}{o['writeoff']}")
    lk = INV.link("summer26", ctl)
    out.append(f"link{lk['proj']['PP']['runs_out']}{lk['proj']['DP']['runs_out']}{lk['gate']}{[x['unmet'] for x in lk['scen']]}")
    out.append(f"fc{len(INV.forecast_compare('summer26', ctl)['big'])}")
    out.append(str(FC.replay_spike(ctl)))
    out.append(str(FC.replay_censoring(ctl)))
    out.append(str(SUP.replay_closure(ctl)))
    out.append(str(FC.method_test(ctl)))
    return "\n".join(out)


def perturb(c):
    if c["id"] in TEST_VALUE:
        return TEST_VALUE[c["id"]]
    if c["kind"] == "select":
        return next(o for o in c["options"] if o != c["default"])
    d, lo, hi, st = c["default"], c["lo"], c["hi"], c["step"] or 1
    for cand in (d * 1.5 if d else st * 3, d * 0.5, d + 3 * st, d - 3 * st, hi, lo):
        cand = max(lo, min(hi, cand))
        if isinstance(d, int):
            cand = int(round(cand))
        if cand != d:
            return cand
    return hi


# contexts in which a control matters (some only bite under a scenario)
CONTEXT = {"b05": {"b04": 10}, "c01": {"b04": 10}, "c02": {"b04": 10, "c01": 3000}, "b13": {"b11": "DP"},
           "b12": {"b11": "DP"}, "b08": {"b07": 0.3}, "b07": {"b08": 10}, "d12": {"b06": 20}, "c06": {"b06": 20},
           "f09": {"f11": 10}}                                   # CUSUM off, so the EWMA line decides
# test values where the default step would not cross a threshold the sample actually reaches
TEST_VALUE = {"f13": 20000, "f15": 7, "f16": 0.1, "f24": 8.0, "f25": 400, "f17": 90, "f18": 2, "g03": 14, "f29": 0.5}
# weeks: the closure, the spike, before the closure, the DP launch fortnight, the spike's peak
WEEKS = (date(2026, 5, 4), date(2026, 3, 16), date(2026, 4, 27), date(2026, 2, 23), date(2026, 3, 30))

if __name__ == "__main__":
    # 1 tags
    bad = [c["id"] for c in CT.REGISTRY if c["src"] not in ("Given", "Derived", "Assumed") or not c["ref"]]
    bad_r = [r for r in RK.META.values() if not r["basis"]]
    check(1, "Every control and risk tagged and referenced", not bad and not bad_r,
          f"{len(CT.REGISTRY)} controls, {len(RK.META)} risks; untagged: {bad or 'none'}")

    # 2 sensitivity
    rows, dead = [], []
    for c in CT.REGISTRY:
        if c["locked"]:                                          # needs the offline optimiser: must NOT be changeable
            ok = CT.Ctl({c["id"]: perturb(c)})[c["id"]] == c["default"]
            rows.append(dict(id=c["id"], label=c["label"], default=c["default"], tested="locked", context="",
                             outputs_changed="locked" if ok else "NOT LOCKED"))
            if not ok:
                dead.append(c["id"])
            print(f"   {c['id']}: locked ({'ok' if ok else 'NOT LOCKED'})")
            continue
        ctx = CONTEXT.get(c["id"], {})
        base = CT.Ctl(ctx)
        alt = CT.Ctl({**ctx, c["id"]: perturb(c)})
        fa, fb = fingerprint(base, WEEKS), fingerprint(alt, WEEKS)
        ca, cb = Counter(fa.splitlines()), Counter(fb.splitlines())
        changed = sum(((ca - cb) + (cb - ca)).values()) // 2 or (1 if ca != cb else 0)
        rows.append(dict(id=c["id"], label=c["label"], default=c["default"], tested=alt[c["id"]], context=str(ctx or ""),
                         outputs_changed=changed))
        if changed == 0:
            dead.append(c["id"])
        print(f"   {c['id']}: {c['default']} -> {alt[c['id']]}  {changed} outputs changed")
    with open(DOCS / "control_sensitivity.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    nl = sum(1 for c in CT.REGISTRY if c["locked"])
    check(2, "No hard-coded parameter: each control moves the outputs", not dead,
          f"{len(rows) - len(dead) - nl} of {len(rows) - nl} live controls change at least one output; {nl} optimiser controls locked; "
          f"problems: {dead or 'none'}")

    # 3 co-packer
    ctl = CT.Ctl()
    below = [w for w in (date(2026, 1, 5), date(2025, 10, 6), date(2025, 12, 1)) if not CP.evaluate(w, ctl)["checks"][0]["ok"]]
    blocked = all(not CP.evaluate(w, ctl)["eligible"] for w in below)
    big = CT.Ctl({"e01": 5.0})
    peak_blocked = not CP.evaluate(date(2026, 4, 27), big)["eligible"]
    check(3, "Co-packer blocked below the combined-plant threshold", blocked and bool(below) and peak_blocked,
          f"{len(below)} quiet weeks below threshold, all blocked; peak week with 5 Cr/month plants blocked: {peak_blocked}")

    # 4 replays
    sp, cl = FC.replay_spike(ctl), SUP.replay_closure(ctl)
    ok4 = sp.get("detected") is not None and (sp.get("lead_planning") or 0) > 0 and cl["detected"] is not None and (cl["lead"] or 0) > 0
    check(4, "Replays report detection date and lead over month-end", ok4,
          f"March spike detected {sp.get('detected')}, {sp.get('lead_planning')} days before Planning sees it on {sp.get('planning_sees')}; "
          f"May closure detected {cl['detected']} (pre-season warning {cl['pre_warning']}), {cl['lead']} days before {cl['planning_sees']}")

    # 5 Given departure -> READ_ME
    dep = CT.Ctl({"a01": 4})
    hit = [x for x in RM.items(date(2026, 5, 4), dep) if x["title"].startswith("Departs from case")]
    check(5, "Moving a Given value adds a READ_ME entry", bool(hit), hit[0]["title"] if hit else "no entry")

    # 6 READ_ME contents
    rows6 = RM.items(date(2026, 5, 4), ctl)
    known = [x for x in rows6 if x["source"] == "Known data issue"]
    new_r = {x["title"][:3] for x in rows6 if re.match(r"R(19|2[0-7]) ", x["title"])}
    check(6, "READ_ME shows known data issues and new risks", len(known) >= 4 and len(new_r) >= 5,
          f"{len(known)} known data issues; new risks listed: {sorted(new_r)}")

    # 7 inventory separation
    tpl = (ROOT / "dashboard" / "app" / "templates")
    inv = (tpl / "inventory.html").read_text(encoding="utf-8")
    eng = ROOT / "dashboard" / "app" / "engine"
    sep = (eng / "inventory_iface.py").exists() and (eng / "inventory.py").exists() and "/rebalance" in inv
    check(7, "Inventory logic separated (prompt 2 built on the hand-off hooks)", sep,
          "engine/inventory_iface.py (prompt-1 hooks) + engine/inventory.py (prompt 2); descriptive page links to the module")

    # 8 no accuracy claims on the new pages
    claims = []
    for p in ("risk.html", "forecast.html", "social.html", "copacker.html", "readme.html", "controls.html", "reviews.html",
              "rebalance.html", "link.html", "overstock.html", "fcsource.html"):
        t = (tpl / p).read_text(encoding="utf-8")
        for m in re.finditer(r"[^.]*\b(accuracy|MAPE|accurate)\b[^.]*\.", t, re.I):
            s = m.group(0)
            if not re.search(r"\b(no|not|never|neither|cannot)\b", s, re.I):
                claims.append(f"{p}: {s.strip()[:90]}")
    check(8, "No accuracy claim from the sample data", not claims, claims[0] if claims else "every mention is a disclaimer")

    with open(DOCS / "acceptance_prompt1.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["n", "check", "result", "detail"])
        wr.writeheader()
        wr.writerows(results)
    print(f"\n{sum(r['result'] == 'pass' for r in results)} of {len(results)} checks pass")
