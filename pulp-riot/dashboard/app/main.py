"""
main.py - PulpSense: Pulp Riot control tower + decision support (FastAPI + server-rendered HTML, as the myMFD CRM).

    python run.py      ->  http://localhost:8600

Every page takes ?asof=YYYY-MM-DD (a Monday). The sidebar and the week picker carry it along,
so moving between pages keeps the same point in time. The active scenario (Control Panel) applies
to every page; nothing the engine recommends is executed - it goes to the review queue.
"""
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import charts
from .data import SKU_NAMES, store
from .engine import controls as CT
from .engine import copacker as CP
from .engine import forecast as FC
from .engine import inventory as INV
from .engine import inventory_iface as II
from .engine import readme as RM
from .engine import reviews as RV
from .engine import risks as RK
from .engine import social as SO
from .engine import supply as SUP
from .engine import transport as TR

HERE = Path(__file__).resolve().parent
app = FastAPI(title="PulpSense")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
T = Jinja2Templates(directory=HERE / "templates")

# key weeks from the case, for one-click jumps (these are case events, not hidden test data)
JUMPS = [("Dragon Passion launch", date(2026, 3, 2)), ("Viral spike", date(2026, 3, 30)),
         ("Highway closes", date(2026, 5, 11)), ("Pulp runs low", date(2026, 5, 25))]


def bottles(n):
    if n is None:
        return "–"
    if abs(n) >= 1e7:
        return f"{n / 1e7:.2f} Cr"
    if abs(n) >= 1e5:
        return f"{n / 1e5:.1f} L"
    return f"{n:,.0f}"


def inr(x):
    if x is None:
        return "–"
    sign = "−" if x < 0 else ""
    x = abs(x)
    if x >= 1e7:
        return f"{sign}₹{x / 1e7:.1f} Cr"
    if x >= 1e5:
        return f"{sign}₹{x / 1e5:.1f} L"
    return f"{sign}₹{x:,.0f}"


def pct(x):
    if x is None or x != x:
        return "–"
    if abs(x) < 0.005:
        return "flat"
    return f"{'+' if x >= 0 else '−'}{abs(x):.0%}"


def day(d):
    return d.strftime("%d %b") if d else "–"


T.env.filters.update(bottles=bottles, inr=inr, pct=pct, day=day)
T.env.globals.update(charts=charts, SKU_NAMES=SKU_NAMES, JUMPS=JUMPS, asset_v="4", GROUPS=CT.GROUPS,
                     CH_NAMES=FC.CH_NAMES, STATUSES=RV.STATUSES, ROLES=RV.ROLES, WINDOWS=INV.WINDOWS, INV_DEPOTS=INV.DEPOTS,
                     INV_SKUS=INV.SKUS)


def _week(asof):
    s = store()
    try:
        d = datetime.strptime(asof, "%Y-%m-%d").date() if asof else None
    except ValueError:
        d = None
    if d is not None:
        d = d - timedelta(d.weekday())
    return s.clamp(d)


def ctx(request, nav, w, **kw):
    s = store()
    i = s.weeks.index(w)
    ctl, scen = CT.load_active()
    rm = RM.counts(RM.items(w, ctl))
    return dict(request=request, nav=nav, week=w, known_by=w + timedelta(7),
                weeks=s.weeks, prev_w=s.weeks[i - 1] if i else None,
                next_w=s.weeks[i + 1] if i + 1 < len(s.weeks) else None, latest=s.weeks[-1],
                ctl=ctl, scen=scen, n_changed=len(ctl.changed()), departures=ctl.departures(), rm_counts=rm,
                msg=request.query_params.get("msg"), err=request.query_params.get("err"), **kw)


async def _form(request):
    body = (await request.body()).decode("utf-8")
    return {k: v[-1] for k, v in parse_qs(body, keep_blank_values=True).items()}


def _back(url, **q):
    sep = "&" if "?" in url else "?"
    return RedirectResponse(url + sep + "&".join(f"{k}={quote(str(v))}" for k, v in q.items()), status_code=303)


# ------------------------------------------------------------------------------ descriptive pages
@app.get("/", response_class=HTMLResponse)
def overview(request: Request, asof: str | None = None):
    w = _week(asof)
    o = store().overview(w)
    ctl, _ = CT.load_active()
    top = [x for x in RM.items(w, ctl) if x["bucket"] in ("Immediate", "Soon")][:6]
    return T.TemplateResponse(request, "overview.html", ctx(request, "overview", w, o=o, top=top))


@app.get("/supply", response_class=HTMLResponse)
def supply(request: Request, asof: str | None = None, po: str = "all"):
    w = _week(asof)
    po = po if po in ("all", "received", "late", "due", "not shipped", "air") else "all"
    s = store().supply(w, po)
    ctl, _ = CT.load_active()
    B = SUP.balance(w, ctl)["planned"]
    rk = RK.evaluate(w, ctl)
    return T.TemplateResponse(request, "supply.html", ctx(request, "supply", w, s=s, eng=B, rk=RK.summary(rk),
                                                          trig=[r for r in rk if r["status"] == "Triggered"]))


@app.get("/inventory", response_class=HTMLResponse)
def inventory(request: Request, asof: str | None = None, depot: str | None = None, basis: str = "forecast"):
    w = _week(asof)
    ctl, _ = CT.load_active()
    v = store().inventory(w, depot, basis if basis in ("forecast", "sales") else "forecast", int(ctl["g04"]))
    fg = II.fg_position(w, ctl)
    s2f = II.supply_to_fg(w, ctl, SUP.balance(w, ctl)["planned"])
    return T.TemplateResponse(request, "inventory.html", ctx(request, "inventory", w, v=v, STATUS_COLORS=charts.STATUS_COLORS,
                                                             fg=fg, s2f=s2f, PROMPT2=II.PROMPT2))


@app.get("/demand", response_class=HTMLResponse)
def demand(request: Request, asof: str | None = None, flavor: str = "all", qcf: str | None = None):
    w = _week(asof)
    v = store().demand(w, flavor, qcf)
    return T.TemplateResponse(request, "demand.html", ctx(request, "demand", w, v=v))


@app.get("/distribution", response_class=HTMLResponse)
def distribution(request: Request, asof: str | None = None):
    w = _week(asof)
    ctl, _ = CT.load_active()
    v = store().distribution(w, int(ctl["g04"]), float(ctl["a08"]))
    return T.TemplateResponse(request, "distribution.html", ctx(request, "distribution", w, v=v))


@app.get("/transportation", response_class=HTMLResponse)
def transportation(request: Request, asof: str | None = None):
    w = _week(asof)
    v = store().transportation(w)
    ctl, _ = CT.load_active()
    fr = TR.fragility(w, ctl)
    tm = TR.mitigation(w, ctl)
    if tm["rec"]:
        RV.annotate([tm["rec"]])
    return T.TemplateResponse(request, "transportation.html", ctx(request, "transportation", w, v=v, fr=fr, tm=tm))


@app.get("/data", response_class=HTMLResponse)
def reference(request: Request, asof: str | None = None, src: str = "all"):
    w = _week(asof)
    v = store().reference(w, src if src in ("all", "Given", "Derived", "Assumed", "Calibrated") else "all")
    return T.TemplateResponse(request, "data.html", ctx(request, "data", w, v=v))


# ------------------------------------------------------------------------------ decision support
ING_LIST = ["passionfruit", "dragonfruit", "mango", "peach", "basil", "guava"]


@app.get("/risk", response_class=HTMLResponse)
def risk(request: Request, asof: str | None = None, ing: str = "passionfruit", st: str = "open"):
    w = _week(asof)
    ctl, _ = CT.load_active()
    ing = ing if ing in ING_LIST else "passionfruit"
    B = SUP.balance(w, ctl)
    rk = RK.evaluate(w, ctl)
    rows = []
    for i in ING_LIST:
        r = B["planned"]["ing"][i]
        gap, lever = SUP.lead_gap(w, ctl, i, r)
        rows.append(dict(ing=i, r=r, stress=B["stress"]["ing"][i], conf=B["confirmed_only"]["ing"][i], gap=gap, lever=lever,
                         levers=SUP.levers(w, ctl, i)))
    m = SUP.mitigations(w, ctl)
    if m["rec"]:
        RV.annotate([m["rec"]])
    gl = SUP.guava_ladder(w, ctl)
    if gl["rec"]:
        RV.annotate([gl["rec"]])
    mpb = SUP.mpb_check(w, ctl)
    shown = rk if st == "all" else [r for r in rk if r["status"] not in ("Clear",)]
    s2f = II.supply_to_fg(w, ctl, B["planned"])
    fg = II.fg_position(w, ctl)
    return T.TemplateResponse(request, "risk.html", ctx(
        request, "risk", w, B=B, rows=rows, ing=ing, rk=shown, rk_all=rk, rk_sum=RK.summary(rk), st=st, m=m, gl=gl, mpb=mpb,
        illus=SUP.illustrative_allocation(ctl), s2f=s2f, fg=fg, cp_m=SUP.contribution(ctl), replay=SUP.replay_closure(ctl)))


@app.get("/forecast", response_class=HTMLResponse)
def forecast(request: Request, asof: str | None = None, sku: str = "DP"):
    w = _week(asof)
    ctl, _ = CT.load_active()
    sku = sku if sku in FC.SKUS else "DP"
    s = store()
    nat = FC.national(w, ctl)
    wk = nat.groupby(["week", "sku"])[["p10", "p50", "p80", "p90"]].sum().reset_index()
    hist_w = s.window(w, 12)
    e = FC.estimated(ctl["f07"]).reset_index()
    hist = e[e.week_start.isin(hist_w) & (e.sku_id == sku)].groupby("week_start").est.sum().reindex(hist_w).fillna(0).tolist()
    f1 = wk[wk.sku == sku].sort_values("week")
    fan = dict(hist_w=hist_w, hist=hist, weeks=f1.week.tolist()[:12], p10=f1.p10.tolist()[:12], p50=f1.p50.tolist()[:12],
               p80=f1.p80.tolist()[:12], p90=f1.p90.tolist()[:12])
    table = wk.pivot(index="week", columns="sku", values="p50").reindex(columns=FC.SKUS).head(8)
    methods = nat[nat.week == nat.week.min()].groupby("sku").method.first().to_dict()
    kg = FC.pulp_requirement(w, ctl)
    kg8 = kg.pivot(index="week", columns="ingredient", values="kg_plan").head(8)
    st, eps = FC.detect(w, ctl, sku)
    rows = [x for x in st if x["date"] > w + timedelta(6) - timedelta(70)]
    al = FC.alerts(w, ctl)
    RV.annotate(al)
    for a in al:
        a["scen"] = SUP.demand_scenarios(w, ctl, a["sku"], float(a["base"] or 0), float(a["ratio"])) if a["active"] and a["base"] else None
    rep = FC.replay_spike(ctl)
    cens = FC.replay_censoring(ctl)
    mt = FC.method_test(ctl)
    sh = FC.depot_shares(w, ctl)
    plan = {k: FC.plan_share(w, k) for k in FC.SKUS}
    return T.TemplateResponse(request, "forecast.html", ctx(
        request, "forecast", w, sku=sku, fan=fan, table=table, methods=methods, kg8=kg8, rows=rows, al=al, rep=rep, cens=cens,
        mt=mt, sh=sh, plan=plan, depots=store().depots.depot_id.tolist(), K=w + timedelta(7)))


@app.get("/social", response_class=HTMLResponse)
def social(request: Request, asof: str | None = None):
    w = _week(asof)
    ctl, _ = CT.load_active()
    d = SO.desk(w, ctl)
    RV.annotate(d["alerts"])
    return T.TemplateResponse(request, "social.html", ctx(request, "social", w, d=d, TIERS=SO.TIERS, TIER_REACH=SO.TIER_REACH))


@app.get("/copacker", response_class=HTMLResponse)
def copacker(request: Request, asof: str | None = None):
    w = _week(asof)
    ctl, _ = CT.load_active()
    cp = CP.evaluate(w, ctl)
    if cp["rec"]:
        RV.annotate([cp["rec"]])
    s = store()
    hist_w = s.window(w, 26)
    use = [float(s.cp_w.get(x, 0)) for x in hist_w]
    return T.TemplateResponse(request, "copacker.html", ctx(request, "copacker", w, cp=cp, hist_w=hist_w, use=use))


@app.get("/readme", response_class=HTMLResponse)
def readme(request: Request, asof: str | None = None, grp: str = "all"):
    w = _week(asof)
    ctl, _ = CT.load_active()
    rows = RM.items(w, ctl)
    groups = sorted({r["group"] for r in rows})
    shown = rows if grp == "all" else [r for r in rows if r["group"] == grp]
    return T.TemplateResponse(request, "readme.html", ctx(request, "readme", w, rows=shown, all_rows=rows, groups=groups, grp=grp))


@app.get("/reviews", response_class=HTMLResponse)
def review_queue(request: Request, asof: str | None = None):
    w = _week(asof)
    ctl, _ = CT.load_active()
    recs = []
    m = SUP.mitigations(w, ctl)
    for r, link in ((m["rec"], "/risk#options"), (SUP.guava_ladder(w, ctl)["rec"], "/risk#ladder"),
                    (CP.evaluate(w, ctl)["rec"], "/copacker"), (TR.mitigation(w, ctl)["rec"], "/transportation#fragility")):
        if r:
            recs.append(dict(r, link=link))
    for a in FC.alerts(w, ctl):
        if a["active"]:
            recs.append(dict(id=a["id"], title=f"Demand alert: {a['sku']} quick commerce {a['ratio']:.1f}x ({a['cls']})",
                             module="Forecast", owner="Planning", detail="Verify, then choose a persistence scenario.", link="/forecast"))
    for c in SO.desk(w, ctl)["alerts"]:
        recs.append(dict(id=c["id"], title=f"Social (simulated): {c['sku']} {c['cls'].lower()}", module="Social desk",
                         owner="Marketing", detail=c["action"], link="/social"))
    RV.annotate(recs)
    hist = RV.history()[::-1][:60]
    return T.TemplateResponse(request, "reviews.html", ctx(request, "reviews", w, recs=recs, hist=hist))


@app.post("/review")
async def review_post(request: Request):
    f = await _form(request)
    back = f.get("back") or "/reviews"
    try:
        ctl, scen = CT.load_active()
        RV.record(f.get("rec_id", ""), f.get("status", ""), f.get("rationale", ""), f.get("role", ""), f.get("title", ""), scen)
    except ValueError as e:
        return _back(back.split("#")[0], err=str(e))
    return _back(back.split("#")[0], msg=f"Recorded: {f.get('status')} by {f.get('role')}. Nothing has been executed.")


# ------------------------------------------------------------------------------ control panel
def _outputs(w, ctl):
    """Key outputs for comparing scenarios."""
    B = SUP.balance(w, ctl)["planned"]["ing"]
    m = SUP.mitigations(w, ctl)
    cp = CP.evaluate(w, ctl)
    rk = RK.summary(RK.evaluate(w, ctl))
    rep = FC.replay_spike(ctl)
    rm = RM.counts(RM.items(w, ctl))
    return [
        ("Passionfruit first unsafe day", day(B["passionfruit"]["first_unsafe"])),
        ("Dragonfruit first unsafe day", day(B["dragonfruit"]["first_unsafe"])),
        ("PP / DB / DP unmet, no action", bottles(m["unmet0"])),
        ("Recommended option (pathway C)", m["winner"]["name"] if m["winner"] else "none needed"),
        ("Unmet with that option", bottles(m["winner"]["unmet"]) if m["winner"] else "–"),
        ("Co-packer eligible", "yes" if cp["eligible"] else "no"),
        ("Risks triggered", str(rk.get("Triggered", 0))),
        ("DP spike detected (replay)", day(rep.get("detected"))),
        ("READ_ME immediate items", str(rm["Immediate"])),
    ]


@app.get("/controls", response_class=HTMLResponse)
def controls(request: Request, asof: str | None = None, a: str | None = None, b: str | None = None):
    w = _week(asof)
    ctl, scen = CT.load_active()
    groups = {g: [dict(c, value=ctl[c["id"]], moved=ctl[c["id"]] != c["default"]) for c in CT.REGISTRY if c["group"] == g]
              for g in CT.GROUPS}
    scens = CT.list_scenarios()
    cmp = None
    if a and b:
        sa, sb = CT.get_scenario(a), CT.get_scenario(b)
        if sa and sb:
            wa = _week(sa["asof"]) if sa["asof"] else w
            wb = _week(sb["asof"]) if sb["asof"] else w
            oa, ob = _outputs(wa, CT.Ctl(sa["values"])), _outputs(wb, CT.Ctl(sb["values"]))
            cmp = dict(a=sa, b=sb, wa=wa, wb=wb, rows=[(k, va, vb) for (k, va), (_, vb) in zip(oa, ob)])
    return T.TemplateResponse(request, "controls.html", ctx(request, "controls", w, groups=groups, scens=scens, cmp=cmp,
                                                            log=CT.change_log(40), a=a, b=b, fmt=CT.fmt_value))


@app.post("/controls")
async def controls_post(request: Request):
    f = await _form(request)
    w = f.get("asof", "")
    ctl, scen = CT.load_active()
    vals = ctl.values()
    for c in CT.REGISTRY:
        if c["id"] in f and f[c["id"]] != "":
            vals[c["id"]] = f[c["id"]]
    new, entries = CT.save_active(vals, name="Custom" if scen in CT.PRESETS or scen == "Base" else scen,
                                  reason=f.get("reason", ""))
    dep = sum(1 for e in entries if e["departs"])
    msg = f"{len(entries)} control(s) changed" + (f"; {dep} departs from the case (see READ_ME)" if dep else "") + ". Every page now uses them."
    return _back(f"/controls?asof={w}", msg=msg)


@app.post("/controls/reset")
async def controls_reset(request: Request):
    f = await _form(request)
    CT.save_active({}, name="Base", reason="reset")
    return _back(f"/controls?asof={f.get('asof', '')}", msg="All controls back to their defaults (Base).")


@app.post("/controls/load")
async def controls_load(request: Request):
    f = await _form(request)
    sc = CT.get_scenario(f.get("slug", ""))
    if not sc:
        return _back(f"/controls?asof={f.get('asof', '')}", err="Scenario not found")
    CT.save_active(sc["values"], name=sc["name"], reason=f"loaded scenario {sc['name']}")
    asof = sc["asof"] or f.get("asof", "")
    return _back(f"/controls?asof={asof}", msg=f"Loaded '{sc['name']}'" + (f", as of week {asof}" if sc["asof"] else "") + ".")


@app.post("/controls/save")
async def controls_save(request: Request):
    f = await _form(request)
    name = (f.get("name") or "").strip()
    if not name:
        return _back(f"/controls?asof={f.get('asof', '')}", err="Give the scenario a name")
    ctl, _ = CT.load_active()
    CT.save_scenario(name, ctl, f.get("asof") if f.get("keep_week") else None)
    CT.save_active(ctl.values(), name=name)
    return _back(f"/controls?asof={f.get('asof', '')}", msg=f"Saved scenario '{name}'.")


# ------------------------------------------------------------------------------ inventory module (prompt 2)
def _win(win):
    return win if win in INV.WINDOWS else "summer26"


def _inv_week(w, win, wk):
    """Week for the heatmap / transfers: ?wk if valid, else the as-of week if it is in the window, else the window's last week."""
    sm_weeks = [x for x, ok in zip(INV.weeks(), INV.in_window(INV.weeks(), win)) if ok]
    d = None
    try:
        d = datetime.strptime(wk, "%Y-%m-%d").date() if wk else None
    except ValueError:
        d = None
    if d in sm_weeks:
        return d, sm_weeks
    return (w if w in sm_weeks else (sm_weeks[-1] if sm_weeks else INV.weeks()[-1])), sm_weeks


@app.get("/rebalance", response_class=HTMLResponse)
def rebalance(request: Request, asof: str | None = None, win: str = "summer26", wk: str | None = None, side: str = "before"):
    w = _week(asof)
    ctl, _ = CT.load_active()
    win = _win(win)
    side = side if side in ("before", "after") else "before"
    sm = INV.summary(win, ctl)
    week, wks = _inv_week(w, win, wk)
    tr = INV.week_transfers(week, ctl)
    RV.annotate(tr)
    wk_with = sorted({x for x in INV.frame(ctl)[1].ws if x in wks})
    return T.TemplateResponse(request, "rebalance.html", ctx(
        request, "rebalance", w, win=win, sm=sm, rc=INV.reconcile(), heat=INV.heat(week, side, ctl), side=side, iweek=week,
        iweeks=wks, wk_with=wk_with, tr=tr, rep=INV.replicate(), con=INV.conservation(), meta=INV.feed()["meta"],
        questions=INV.QUESTIONS, locked=[c for c in CT.REGISTRY if c["locked"]] + [CT.BY_ID["a07"]]))


@app.get("/link", response_class=HTMLResponse)
def inv_link(request: Request, asof: str | None = None, win: str = "summer26"):
    w = _week(asof)
    ctl, _ = CT.load_active()
    win = _win(win)
    return T.TemplateResponse(request, "link.html", ctx(request, "link", w, win=win, L=INV.link(win, ctl)))


@app.get("/overstock", response_class=HTMLResponse)
def inv_overstock(request: Request, asof: str | None = None, win: str = "summer26"):
    w = _week(asof)
    ctl, _ = CT.load_active()
    win = _win(win)
    return T.TemplateResponse(request, "overstock.html", ctx(request, "overstock", w, win=win, o=INV.overstock(win, ctl),
                                                             o_all=INV.overstock("all", ctl)))


@app.get("/fcsource", response_class=HTMLResponse)
def inv_fcsource(request: Request, asof: str | None = None, win: str = "summer26"):
    w = _week(asof)
    ctl, _ = CT.load_active()
    win = win if win in ("summer26", "summer25") else "summer26"
    return T.TemplateResponse(request, "fcsource.html", ctx(request, "fcsource", w, win=win, fc=INV.forecast_compare(win, ctl)))
