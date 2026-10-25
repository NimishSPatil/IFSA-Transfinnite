"""
check_prompt2.py - the prompt-2 (Inventory integration) acceptance checks, rerunnable.

    python code/check_prompt2.py          (about 1 minute)

Writes docs/acceptance_prompt2.csv. Checks run on the engine and on the rendered pages (FastAPI TestClient).
"""
import csv
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

from fastapi.testclient import TestClient            # noqa: E402

from app.engine import controls as CT                # noqa: E402
from app.engine import copacker as CP                # noqa: E402
from app.engine import inventory as INV              # noqa: E402
from app.engine import readme as RM                  # noqa: E402
from app.main import app                             # noqa: E402

DOCS = ROOT / "docs"
results = []
client = TestClient(app)


def text(path):
    r = client.get(path)
    return r.status_code, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text)), r.text


def check(n, name, ok, detail):
    results.append(dict(n=n, check=name, result="pass" if ok else "FAIL", detail=detail))
    print(f"[{'pass' if ok else 'FAIL'}] {n}. {name}: {detail}")


if __name__ == "__main__":
    ctl = CT.Ctl()
    rc = INV.reconcile()
    ex = rc["exceptions"]
    y2025 = next(y for y in INV.summary("all", ctl)["years"] if y["year"] == 2025)["before"]
    check(1, "Headline figures reconcile; exceptions explained", rc["all_ok"] and len(ex) == 4 and abs(rc["exc_loss"] - y2025) < 1,
          "; ".join(f"{r['name']} {r['handoff']}" for r in rc["rows"]) + f" | exceptions: {len(ex)} unreported rows "
          f"({ex[0]['depot']}, week of {ex[0]['week']}) carry ₹{rc['exc_loss'] / 1e7:.4f} Cr = all of 2025's loss")

    code, t, html = text("/rebalance?asof=2026-05-04")
    years = {y["year"]: round(y["net"] / 1e7, 2) for y in INV.summary("all", ctl)["years"]}
    default_on = 'class="chip on" href="/rebalance?asof=2026-05-04&win=summer26"' in html
    check(2, "Default window is Mar–Jun 2026; net-by-year view present", code == 200 and default_on and years == {2024: -0.09, 2025: -0.23, 2026: 2.28},
          f"default chip on: {default_on}; net by year {years}")

    sm = INV.summary("summer26", ctl)
    note = "is Passionfruit Punch and Dragon Passion" in t and "supply problem" in t
    check(3, "Next to the saving, PP and DP residual is called a supply problem", note,
          f"PP + DP = {100 * sm['pp_dp_share']:.2f}% of the loss left after rebalancing (Mar–Jun 2026); {100 * INV.summary('all', ctl)['pp_dp_share']:.1f}% over the whole file")

    moved = {}
    for k, v in (("h01", 20), ("h02", 0), ("a08", 3), ("h03", 50)):
        c = CT.Ctl({k: v})
        s2, o2 = INV.summary("summer26", c), INV.overstock("all", c)
        moved[k] = (s2["before"], s2["after_total"], o2["before"]["n"]) != (sm["before"], sm["after_total"], INV.overstock("all", ctl)["before"]["n"])
    locked = [c["id"] for c in CT.REGISTRY if c["locked"]]
    ignored = all(CT.Ctl({k: 1234})[k] == CT.BY_ID[k]["default"] for k in locked)
    _, tc, hc = text("/controls?asof=2026-05-04")
    disabled = all(re.search(rf'id="{k}"[\s\S]{{0,900}}?disabled', hc) for k in locked)
    rep = INV.replicate()
    check(4, "Financial controls recalculate; optimiser controls disabled with a match rate", all(moved.values()) and ignored and disabled,
          f"recalc {moved}; locked {locked} ignored={ignored} disabled in UI={disabled}; greedy replica reproduces "
          f"{rep['exact'][0]}/{rep['exact'][1]} transfers (receivers {rep['receivers'][0]}/{rep['receivers'][1]}) < {rep['tolerance']:.0%} tolerance")

    code, t, _ = text("/overstock?asof=2026-05-04&win=all")
    o = INV.overstock("all", ctl)
    check(5, "Overstock exposure view without an invented write-off", code == 200 and "not claimed" in t and o["writeoff"] is None
          and (o["before"]["status_n"], o["after"]["status_n"]) == (321, 337),
          f"over-35 depot-weeks {o['before']['status_n']} → {o['after']['status_n']}; write-off shown only if h05 > 0 (now 0)")

    claims = []
    for p in ("rebalance", "link", "overstock", "fcsource"):
        _, tt, _ = text(f"/{p}?asof=2026-05-04")
        for m in re.finditer(r"[^.]*\b(accuracy|MAPE|accurate)\b[^.]*\.", tt, re.I):
            if not re.search(r"\b(no|not|never|neither|cannot)\b", m.group(0), re.I):
                claims.append(f"{p}: {m.group(0).strip()[:80]}")
    check(6, "No accuracy claim from sample or file data", not claims, claims[0] if claims else "every mention is a disclaimer")

    quiet = [w for w in (date(2026, 1, 5), date(2025, 12, 1))]
    cp_ok = all(not CP.evaluate(w, ctl)["eligible"] and not CP.evaluate(w, ctl)["checks"][0]["ok"] for w in quiet)
    dep = any(x["title"].startswith("Departs from case") for x in RM.items(date(2026, 5, 4), CT.Ctl({"a01": 4})))
    presets = len([s for s in CT.list_scenarios() if s["preset"]]) == 5
    css = (ROOT / "dashboard" / "app" / "static" / "app.css").read_text(encoding="utf-8")
    theme = all(x in css for x in ("#051C2C", "#2251FF", "#00A9F4"))
    pages = ["/", "/supply", "/inventory", "/demand", "/distribution", "/transportation", "/data", "/risk", "/forecast", "/social",
             "/copacker", "/readme", "/reviews", "/controls", "/rebalance", "/link", "/overstock", "/fcsource"]
    bad = [p for p in pages if client.get(p + "?asof=2026-05-04").status_code != 200]
    check(7, "Prompt 1 behaviour still works", cp_ok and dep and presets and theme and not bad,
          f"co-packer blocked below threshold: {cp_ok}; Given departure on READ_ME: {dep}; 5 presets: {presets}; theme tokens: {theme}; "
          f"{len(pages) - len(bad)}/{len(pages)} pages render")

    rows = RM.items(date(2026, 5, 4), ctl)
    want = ["unreported rows", "Stock not conserved", "senders below", "lost money", "shortage-only", "lower bound",
            "PP depot stock reaches zero", "Two inventory sources", "Optimiser logic is offline"]
    found = [w for w in want if any(w.lower() in (x["title"] + x["detail"]).lower() for x in rows)]
    qs = [x for x in rows if x["group"] == "Open questions (teammate)"]
    check(8, "READ_ME carries the inventory items and the teammate questions", len(found) == len(want) and len(qs) == 5,
          f"{len(found)}/{len(want)} required items; {len(qs)} open questions; groups {sorted({x['group'] for x in rows})}")

    with open(DOCS / "acceptance_prompt2.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["n", "check", "result", "detail"])
        wr.writeheader()
        wr.writerows(results)
    print(f"\n{sum(r['result'] == 'pass' for r in results)} of {len(results)} checks pass")
