"""
controls.py - the Control Panel: every setting the decision engine uses, in one registry.

Rules
  * No engine number is hard-coded. Engine code reads settings only through Ctl (ctl["a01"]).
  * Each control carries: id, group (a-g), label, unit, default, range, source tag (Given/Derived/Assumed)
    and a reference (F## case fact, G## gap, A## assumption, or a new A/G number added in prompt 1).
  * The active scenario lives in dashboard/state/active.json. Saved scenarios in state/scenarios/.
  * Every change is appended to state/change_log.jsonl. A Given control moved away from its default
    is "departs from case" and shows on READ_ME.
"""
import json
import re
from datetime import date, datetime
from pathlib import Path

STATE = Path(__file__).resolve().parents[2] / "state"
SCEN = STATE / "scenarios"

GROUPS = {
    "a": "Transit and lead times",
    "b": "Disruptions (scenario inputs)",
    "c": "Supplier capacity",
    "d": "Recipe and cost",
    "e": "Production",
    "f": "Demand, forecast and signals",
    "g": "Inventory, shelf life and buffers",
    "h": "Inventory rebalancing and loss (teammate feed)",
}


def C(id, label, unit, default, lo=None, hi=None, step=None, src="Assumed", ref="", note="", kind="num", options=None,
      locked=False, anchor=False):
    """locked: shown but not editable (needs an optimiser re-run). anchor: default comes from the case or the
    teammate's file, so moving it 'departs from case' even when the source tag is Derived/Assumed."""
    return dict(id=id, group=id[0], label=label, unit=unit, default=default, lo=lo, hi=hi, step=step,
                src=src, ref=ref, note=note, kind=kind, options=options, locked=locked, anchor=anchor)


# --------------------------------------------------------------------------------------------- registry
# New gaps/assumptions introduced in prompt 1 are numbered from G25 / A25 (see docs/PROMPT1_NOTES.md).
REGISTRY = [
    # a) transit
    C("a01", "Passionfruit road transit", "days", 3, 1, 10, 1, "Given", "F40"),
    C("a02", "Imported dragonfruit lead time, shortest", "days", 42, 28, 90, 1, "Given", "F16", "6 weeks"),
    C("a03", "Imported dragonfruit lead time, longest", "days", 56, 28, 120, 1, "Given", "F16", "8 weeks"),
    C("a04", "Domestic road transit (mango, peach, basil, guava, domestic dragonfruit)", "days", 3, 1, 10, 1, "Assumed", "G07 / A07"),
    C("a05", "Air freight, booking to arrival", "days", 10, 1, 21, 1, "Derived", "G16 / sample",
      "case gives no air transit time (G16); the sample's airlift was booked 18 May, landed 28 May (F44: 2nd week)"),
    C("a06", "Air freight cost vs normal", "x", 5, 1, 10, 0.5, "Given", "F57"),
    C("a07", "Depot-to-depot transfer time", "days", 3, 2, 4, 1, "Given", "F49", "case range 2-4 days"),
    C("a08", "Depot-to-depot transfer cost", "INR/bottle", 1.5, 0, 10, 0.1, "Given", "F50"),
    C("a09", "Extra delay on open sea orders", "days", 0, 0, 60, 1, "Assumed", "A25", "scenario lever; 0 = as promised"),
    C("a10", "Extra delay on open road orders", "days", 0, 0, 30, 1, "Assumed", "A25", "scenario lever; 0 = as promised"),
    C("a11", "Flag a lane when on-time deliveries fall below", "share", 0.9, 0.5, 1, 0.01, "Assumed", "A47"),
    C("a12", "Flag a lane when lead time exceeds this share of plant cover", "share", 0.5, 0.1, 2, 0.05, "Assumed", "A47"),

    # b) disruptions
    C("b01", "Hypothetical highway closure starts", "days after as-of", -1, -1, 120, 1, "Assumed", "A26",
      "-1 = no hypothetical closure. A closure already under way in the data is always used."),
    C("b02", "Length of a closure (planning stress case)", "days", 21, 0, 60, 1, "Given", "F55",
      "Used for any closure whose end is not yet known, and for the hypothetical one."),
    C("b03", "Summers with a closure of a week or more", "of 5", 3, 0, 5, 1, "Given", "F42"),
    C("b04", "Guava supplier 1 stops dispatching", "days", 0, 0, 60, 1, "Assumed", "R04 scenario"),
    C("b05", "Guava supplier 1 share of guava", "share", 0.6, 0, 1, 0.05, "Assumed", "G06 / A06",
      "split between the two guava suppliers is not in the case"),
    C("b06", "Mango / peach / basil outage (one input, all three tested)", "days", 0, 0, 60, 1, "Assumed", "R01-R03 scenario"),
    C("b07", "Plant breakdown: capacity lost", "share", 0.0, 0, 1, 0.05, "Assumed", "R22 / G27"),
    C("b08", "Plant breakdown: duration", "days", 0, 0, 60, 1, "Assumed", "R22 / G27"),
    C("b09", "Pulp lost to cold-chain or quality hold", "share of on-hand", 0.0, 0, 1, 0.05, "Assumed", "R20, R21 / G26"),
    C("b10", "Packaging (bottles, caps, labels) short", "share of capacity", 0.0, 0, 1, 0.05, "Assumed", "R19 / G25"),
    C("b11", "Demand shock flavor", "flavor", "none", kind="select", options=["none", "MPB", "GC", "PP", "DB", "DP"],
      src="Assumed", ref="A27", note="scenario lever for the viral-spike replay"),
    C("b12", "Demand shock size (quick commerce)", "x", 4.0, 1, 10, 0.5, "Given", "F53", "case: orders rose 4x"),
    C("b13", "Demand shock starts", "days after as-of", 0, 0, 120, 1, "Assumed", "A27"),
    C("b14", "Import price / FX change", "share", 0.0, -0.5, 1, 0.05, "Assumed", "R23 / G28"),

    # c) supplier capacity (0 = not confirmed; the engine never invents spare capacity)
    C("c01", "Guava supplier 2 confirmed extra capacity", "kg/day", 0, 0, 20000, 100, "Assumed", "G29",
      "0 until the supplier confirms a figure"),
    C("c02", "Guava supplier 2 earliest extra dispatch", "days after request", 3, 0, 30, 1, "Assumed", "G29"),
    C("c03", "Domestic dragonfruit confirmed extra capacity", "kg/day", 0, 0, 20000, 100, "Assumed", "G30",
      "60% is a sourcing mix (F14), not a capacity ceiling; 0 until confirmed"),
    C("c04", "Air freight capacity", "kg/day", 4700, 0, 20000, 100, "Assumed", "G16 / A28",
      "not in the case; the sample airlifted 66 t over the closure's last two weeks, about 4.7 t/day"),
    C("c05", "Passionfruit cooperative confirmed surge capacity", "kg/day", 0, 0, 20000, 100, "Assumed", "G31",
      "pre-season surge for pre-building; 0 until confirmed"),
    C("c06", "Alternate mango/peach/basil processor confirmed capacity", "share of need", 0.0, 0, 1, 0.05, "Assumed", "G32"),

    # d) recipe and cost
    C("d01", "Pulp per bottle", "kg", 0.06, 0.02, 0.2, 0.005, "Assumed", "A05 / A06", "sku.csv"),
    C("d02", "Mango share in Mango Peach Basil", "share", 0.55, 0, 1, 0.05, "Assumed", "G06 / A06"),
    C("d03", "Peach share in Mango Peach Basil", "share", 0.35, 0, 1, 0.05, "Assumed", "G06 / A06"),
    C("d04", "Passionfruit share in Dragon Passion", "share", 0.5, 0, 1, 0.05, "Assumed", "G05 / A05",
      "basil = 1 - mango - peach; dragonfruit = 1 - passionfruit"),
    C("d05", "Average price", "INR/bottle", 60, 30, 120, 1, "Given", "F26"),
    C("d06", "Contribution margin", "share", 0.32, 0, 0.8, 0.01, "Given", "F02",
      "uniform proxy across flavors; not a validated per-flavor margin"),
    C("d07", "Co-packer cost premium", "share of unit cost", 0.25, 0, 1, 0.01, "Given", "F21"),
    C("d08", "Co-packer volume cap", "share of plant volume", 0.10, 0, 0.5, 0.01, "Given", "F20"),
    C("d09", "Co-packer notice", "days", 14, 0, 60, 1, "Given", "F22"),
    C("d10", "Normal freight cost of passionfruit", "INR/kg", 0, 0, 500, 1, "Derived", "F56, F57 + sample",
      "0 = derive from the sample's 2026 air spend / 5x / kg airlifted"),
    C("d11", "Dragonfruit domestic share of supply (sourcing mix)", "share", 0.6, 0, 1, 0.05, "Given", "F14"),
    C("d12", "Share of unmet MPB / GC buyers who would take another flavor", "share", 0.0, 0, 1, 0.05, "Assumed", "A45",
      "hypothesis only: no substitution data exists. 0 = no switching assumed"),
    C("d13", "Passionfruit Punch cut in the 'case response' option", "share", 0.9, 0, 1, 0.05, "Assumed", "F58 / A46",
      "the case says PP was cut (F58); the size is the sample's assumption"),

    # e) production
    C("e01", "Combined plant capacity", "crore bottles/month", 2.5, 1, 5, 0.1, "Given", "F32"),
    C("e02", "Usable share of plant capacity", "share", 1.0, 0.5, 1, 0.01, "Assumed", "F33",
      "case reports ~95% utilisation; 100% = theoretical max"),
    C("e03", "Plant pulp cover target (procurement)", "days", 15.6, 5, 60, 0.5, "Derived", "F43 + sample",
      "the sample's calibrated target; gives 14 days on 11 May (F43)"),

    # f) demand, forecast, signals
    C("f01", "Forecast error, flavor x depot", "MAPE", 0.30, 0.05, 0.8, 0.01, "Given", "F28"),
    C("f02", "Forecast error, national flavor", "MAPE", 0.15, 0.03, 0.6, 0.01, "Assumed", "A29",
      "depot errors are not independent; test 10/15/20%"),
    C("f03", "Percentile for pulp (long lead)", "P", 80, 50, 95, 5, "Assumed", "A30", "spec: P80-P90"),
    C("f04", "Percentile for finished goods", "P", 50, 50, 95, 5, "Assumed", "A30", "spec: P50-P60"),
    C("f05", "Weight on recent run-rate vs last year's shape", "share", 0.6, 0, 1, 0.05, "Assumed", "A31"),
    C("f06", "Weeks of run-rate used for the level", "weeks", 6, 2, 13, 1, "Assumed", "A31"),
    C("f07", "Censored weeks", "method", "orders", kind="select", options=["orders", "impute", "exclude"],
      src="Assumed", ref="A32", note="orders = use units ordered; impute = pre-stock-out run-rate; exclude = drop"),
    C("f08", "Detector: EWMA weight", "lambda", 0.3, 0.05, 1, 0.05, "Assumed", "A33"),
    C("f09", "Detector: alert when EWMA ratio above", "x baseline", 1.5, 1.05, 4, 0.05, "Assumed", "A33"),
    C("f10", "Detector: CUSUM slack", "ratio", 0.15, 0, 1, 0.05, "Assumed", "A33"),
    C("f11", "Detector: CUSUM alarm level", "ratio-days", 1.5, 0.2, 10, 0.1, "Assumed", "A33"),
    C("f12", "Detector: consecutive days needed", "days", 2, 1, 7, 1, "Assumed", "A33", "spec starts at 2"),
    C("f13", "Detector: minimum baseline volume", "bottles/day", 500, 0, 20000, 100, "Assumed", "A33"),
    C("f14", "Detector: baseline window", "days", 28, 7, 56, 1, "Assumed", "A33"),
    C("f15", "Launch-ramp window", "days", 28, 0, 90, 1, "Assumed", "A34"),
    C("f16", "Breadth for a viral burst", "share of depots", 0.6, 0.1, 1, 0.05, "Assumed", "A34"),
    C("f17", "Persistence: decay half-life", "days", 21, 3, 120, 1, "Assumed", "G20 / A20"),
    C("f18", "Persistence: fade half-life", "days", 7, 1, 60, 1, "Assumed", "G20 / A20"),
    C("f19", "Depot share: recency half-life", "weeks", 4, 1, 26, 1, "Assumed", "A35"),
    C("f20", "Depot share: shrinkage k", "weeks", 4, 0, 26, 1, "Assumed", "A35", "pulls thin depots to their region"),
    C("f21", "Dragon Passion launch allocation (before data)", "share of volume", 0.03, 0, 0.3, 0.005, "Assumed", "G21 / A22"),
    C("f22", "Marketing notice of launches to procurement", "days", 14, 0, 90, 1, "Given", "F36"),
    C("f23", "Year-on-year growth for the baseline", "share", 0.15, -0.2, 0.6, 0.01, "Assumed", "A40",
      "user decision: growth slowing to 15%"),
    C("f26", "Detector: remove last year's seasonal rise", "method", "yes", kind="select", options=["yes", "no"],
      src="Assumed", ref="A33", note="compares each day's rise with the same day last year; see decision table"),
    C("f24", "Social: velocity alert", "x baseline", 3.0, 1.2, 10, 0.1, "Assumed", "A36", "simulated feed only"),
    C("f25", "Social: minimum mentions per day", "mentions", 30, 1, 1000, 1, "Assumed", "A36"),
    C("f27", "Social: macro + mega share for an influencer burst", "share", 0.15, 0.01, 1, 0.01, "Assumed", "A36"),

    # g) inventory, shelf life, buffers
    C("g01", "Bottle shelf life", "days", 90, 30, 365, 1, "Given", "F38"),
    C("g02", "MT / QC minimum days left", "days", 60, 0, 120, 1, "Given", "F39"),
    C("g03", "Frozen pulp shelf life", "days", 180, 30, 365, 1, "Given", "F37"),
    C("g04", "Depot cover target", "days", 21, 3, 60, 1, "Given", "F45"),
    C("g05", "Pulp safety buffer", "days of use", 3, 0, 21, 1, "Assumed", "A37", "handoff 5.4"),
    C("g06", "Planning horizon for the material balance", "days", 56, 14, 112, 7, "Assumed", "A38", "spec: 28-56 days"),
    C("g07", "Minimum service level for any flavor in an allocation", "share", 0.0, 0, 1, 0.05, "Assumed", "A39",
      "management floor; 0 = none"),
    C("g08", "Finished-goods lag, plant to depot shelf", "days", 7, 0, 28, 1, "Assumed", "G02 / A48",
      "plant-to-depot lane not in the case; drives the Supply -> Inventory projection and the MT/QC gate"),

    # f) forecast source (prompt 2)
    C("f28", "Forecast for inventory views", "source", "file", kind="select", options=["file", "dashboard"],
      src="Assumed", ref="A49", note="file = teammate's static P50/P80; dashboard = prompt-1 one-week-ahead forecast"),
    C("f29", "Flag a forecast difference above", "share", 0.25, 0.05, 1, 0.05, "Assumed", "A49"),

    # h) inventory rebalancing and loss (teammate feed). h04, h06, h07 need the offline optimiser: locked.
    C("h01", "Loss per bottle below P50", "INR/bottle", 15.36, 0, 60, 0.01, "Derived", "file; 15.36 + 3.84 = F26 × F02",
      "with h02 a bottle below P50 costs ₹19.20 (₹60 × 32%)", anchor=True),
    C("h02", "Extra loss per bottle below P80", "INR/bottle", 3.84, 0, 60, 0.01, "Derived", "file; F26 × F02 × 20%", anchor=True),
    C("h03", "Overstock threshold", "days of cover", 35, 14, 90, 1, "Assumed", "file / A50", anchor=True),
    C("h04", "Minimum transfer", "bottles", 10000, 1000, 100000, 1000, "Assumed", "file", "needs an optimiser re-run",
      locked=True, anchor=True),
    C("h05", "Write-off rate on bottles past the saleable window", "INR/bottle", 0, 0, 60, 0.5, "Assumed", "A51",
      "0 = no rupee write-off is claimed; the case's ₹6 Cr (F60) is not reproduced by this view"),
    C("h06", "Sender floor (cover kept after a transfer)", "days", 16.25, 5, 40, 0.25, "Assumed", "inferred from file",
      "needs an optimiser re-run", locked=True, anchor=True),
    C("h07", "Receiver trigger / top-up", "days", 16.0, 5, 30, 0.25, "Assumed", "inferred from file",
      "needs an optimiser re-run; top-up 16.2 days", locked=True, anchor=True),
]
BY_ID = {c["id"]: c for c in REGISTRY}


# --------------------------------------------------------------------------------------------- presets
PRESETS = {
    "base": dict(name="Base", asof=None, note="All controls at their defaults. No hypothetical disruption.", values={}),
    "may_closure": dict(name="May closure replay", asof="2026-05-04",
                        note="As of Monday 11 May 2026: the highway has just closed (case F55). Closure length "
                             "planned at 21 days (b02, the case's length). The engine starts from that morning's pulp.",
                        values={}),
    "viral_spike": dict(name="Viral spike replay", asof="2026-03-09",
                        note="As of Monday 16 March 2026: Dragon Passion quick-commerce demand rises 4x (case F53).",
                        values={"b11": "DP", "b12": 4.0, "b13": 0}),
    "import_delay": dict(name="Import delay", asof="2026-04-13",
                         note="Open sea orders of dragonfruit arrive 21 days late.", values={"a09": 21}),
    "compound": dict(name="Compound shock", asof="2026-04-27",
                     note="A 21-day highway closure from day 3, imports 21 days late and a 4x Dragon Passion spike.",
                     values={"b01": 3, "b02": 21, "a09": 21, "b11": "DP", "b12": 4.0, "b13": 0}),
}


# --------------------------------------------------------------------------------------------- state
def _coerce(c, v):
    if c["kind"] == "select":
        return v if v in c["options"] else c["default"]
    try:
        x = float(v)
    except (TypeError, ValueError):
        return c["default"]
    if c["lo"] is not None:
        x = max(c["lo"], x)
    if c["hi"] is not None:
        x = min(c["hi"], x)
    if isinstance(c["default"], int) and float(c["step"] or 1).is_integer():
        x = int(round(x))
    return x


class Ctl:
    """Read-only, hashable view of one scenario's control values (so engine results can be cached)."""

    def __init__(self, values=None):
        v = {c["id"]: c["default"] for c in REGISTRY}
        for k, x in (values or {}).items():
            if k in BY_ID and not BY_ID[k]["locked"]:
                v[k] = _coerce(BY_ID[k], x)
        self._v = v
        self.key = tuple(sorted(v.items(), key=lambda t: t[0]))

    def __getitem__(self, k):
        return self._v[k]

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, o):
        return isinstance(o, Ctl) and self.key == o.key

    def values(self):
        return dict(self._v)

    def changed(self):
        return {k: v for k, v in self._v.items() if v != BY_ID[k]["default"]}

    def departures(self):
        """Given values (or case / file-anchored defaults) moved away from the case or the file."""
        return [dict(BY_ID[k], value=v) for k, v in self.changed().items() if BY_ID[k]["src"] == "Given" or BY_ID[k]["anchor"]]

    def tag(self, *ids):
        """Source tag for a figure computed from these controls: Given only if all inputs are Given and unchanged."""
        srcs = {BY_ID[i]["src"] for i in ids}
        moved = [i for i in ids if self._v[i] != BY_ID[i]["default"]]
        kind = "Given" if srcs == {"Given"} and not moved else ("Assumed" if "Assumed" in srcs or moved else "Derived")
        return dict(src=kind, refs=", ".join(f"{i.upper()} ({BY_ID[i]['ref']})" for i in ids))


def _ensure():
    STATE.mkdir(exist_ok=True)
    SCEN.mkdir(exist_ok=True)


def load_active():
    _ensure()
    p = STATE / "active.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return Ctl(d.get("values", {})), d.get("name", "Custom")
        except (ValueError, OSError):
            pass
    return Ctl(), "Base"


def _log(entries):
    with open(STATE / "change_log.jsonl", "a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, default=str) + "\n")


def save_active(new_values, name="Custom", who="planner", reason=""):
    """Write the active scenario and log every control that changed."""
    _ensure()
    old, _ = load_active()
    ctl = Ctl(new_values)
    ts = datetime.now().isoformat(timespec="seconds")
    entries = []
    for k in BY_ID:
        if old[k] != ctl[k]:
            c = BY_ID[k]
            entries.append(dict(ts=ts, id=k, label=c["label"], old=old[k], new=ctl[k], default=c["default"],
                                src=c["src"], ref=c["ref"], departs=(c["src"] == "Given" or c["anchor"]) and ctl[k] != c["default"],
                                scenario=name, who=who, reason=reason))
    (STATE / "active.json").write_text(json.dumps(dict(name=name, values=ctl.changed()), indent=1, default=str), encoding="utf-8")
    if entries:
        _log(entries)
    return ctl, entries


def change_log(n=200):
    p = STATE / "change_log.jsonl"
    if not p.exists():
        return []
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return rows[::-1][:n]


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "scenario"


def save_scenario(name, ctl, asof=None):
    _ensure()
    p = SCEN / f"{_slug(name)}.json"
    p.write_text(json.dumps(dict(name=name, asof=asof, saved=datetime.now().isoformat(timespec="seconds"),
                                 values=ctl.changed()), indent=1, default=str), encoding="utf-8")
    return _slug(name)


def list_scenarios():
    _ensure()
    out = [dict(slug=k, name=p["name"], asof=p["asof"], saved=None, values=p["values"], preset=True, note=p["note"])
           for k, p in PRESETS.items()]
    for p in sorted(SCEN.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append(dict(slug=p.stem, name=d["name"], asof=d.get("asof"), saved=d.get("saved"),
                            values=d.get("values", {}), preset=False, note=""))
        except (ValueError, OSError, KeyError):
            continue
    return out


def get_scenario(slug):
    for s in list_scenarios():
        if s["slug"] == slug:
            return s
    return None


def fmt_value(c, v):
    if c["kind"] == "select":
        return str(v)
    if isinstance(v, float) and not float(v).is_integer():
        return f"{v:g}"
    return f"{int(v)}" if float(v).is_integer() else f"{v:g}"


def asof_date(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None
