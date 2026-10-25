"""
data.py - loads dataset v2 once and answers "what did the company know as of week W?".

As-of rule (the dashboard's foundation)
  The user picks a week W (a Monday). The view is the Monday AFTER that week, K = W + 7 days.
  Everything shown is data that existed by K:
    depot reports, demand, plant and pulp ledgers  -> weeks up to and including W
    quick-commerce daily sell-through              -> days up to W + 6
    purchase orders                                -> ordered by K; "received" only if received by K
    highway closures                               -> only closures that had started by K
  Nothing in data/v2/_hidden/ is ever read here.
"""
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]          # .../pulp-riot
DATA = ROOT / "data" / "v2"
PRICE = 60.0                                        # case F26
REGIONS = ["North", "South", "East", "West"]
SKU_NAMES = {"MPB": "Mango Peach Basil", "GC": "Guava Chilli", "PP": "Passionfruit Punch",
             "DB": "Dragonfruit Bloom", "DP": "Dragon Passion"}


def _read(name, dates=()):
    df = pd.read_csv(DATA / f"{name}.csv", encoding="utf-8-sig")
    for c in dates:
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    return df


class Store:
    def __init__(self):
        self.cal = _read("calendar_weekly", ["week_start", "week_end"])
        self.dem = _read("demand_weekly", ["week_start", "week_end"])
        self.inv = _read("inventory_weekly", ["week_start", "week_end", "reported_date"])
        self.inv = self.inv.sort_values("week_start")
        self.inv["pace"] = (self.inv.groupby(["depot_id", "sku_id"]).units_sold
                            .transform(lambda x: x.rolling(4, min_periods=2).mean() / 7))
        self.inv["cover_actual"] = self.inv.closing_stock / self.inv.pace.where(self.inv.pace > 0)
        self.qc = _read("qc_sellthrough_daily", ["date", "reported_date"])
        self.pulp = _read("pulp_ledger_weekly", ["week_start"])
        self.prod = _read("production_weekly", ["week_start"])
        self.po = _read("purchase_orders", ["order_date", "promised_date", "received_date"])
        self.closures = _read("closures_history", ["start", "end"])
        self.depots = _read("depots")
        self.sku = _read("sku")
        self.weeks = sorted(self.cal.week_start.unique())
        self._precompute()

    # ------------------------------------------------------------------ weekly series
    def _precompute(self):
        d = self.dem
        self.sales_w = d.groupby("week_start")[["units_sold", "units_lost", "units_ordered"]].sum()
        self.qc_share_w = d[d.channel_id == "C_QC"].groupby("week_start").units_sold.sum() / self.sales_w.units_sold

        inv = self.inv[self.inv.report_received]
        g = inv.groupby("week_start")
        self.inv_w = pd.DataFrame({
            "below7": g.apply(lambda x: int((x.days_of_cover < 7).sum()), include_groups=False),
            "stockouts": g.apply(lambda x: int((x.stock_status == "stock-out").sum()), include_groups=False),
            "median_cover": g.days_of_cover.median(),
            "aged_share": g.stock_under_60_days_left.sum() / g.closing_stock.sum().replace(0, np.nan),
            "pairs": g.size(),
        })
        # region cover = region stock / region daily P50
        r = inv.assign(p50d=inv.p50_week / 7).groupby(["week_start", "region"])[["closing_stock", "p50d"]].sum()
        rc = (r.closing_stock / r.p50d.replace(0, np.nan)).unstack("region")
        self.region_cover_w = rc
        self.region_spread_w = rc.max(axis=1) - rc.min(axis=1)

        pf = self.pulp[self.pulp.ingredient == "passionfruit"]
        self.pf_cover_w = pf.groupby("week_start").days_of_cover.min()
        self.pf_road_w = pf.groupby("week_start").receipts_road_kg.sum()
        self.pf_air_w = pf.groupby("week_start").receipts_air_kg.sum()

        p = self.prod
        plant = p[p.plant.isin(["P1", "P2"])].groupby("week_start").utilisation.mean()
        cp = p[p.plant == "CP"].groupby("week_start").units_produced.sum()
        self.util_w, self.cp_w = plant, cp
        self.road_closed_days_w = self.cal.set_index("week_start").road_closed_days

    # ------------------------------------------------------------------ helpers
    def clamp(self, w):
        if w is None or w not in self.weeks:
            return self.weeks[-1]
        return w

    def window(self, w, n):
        i = self.weeks.index(w)
        return self.weeks[max(0, i - n + 1): i + 1]

    def known_closures(self, w):
        k = w + timedelta(7)
        c = self.closures[(self.closures.closed == "Y") & (self.closures.start <= k)]
        return c

    # ------------------------------------------------------------------ overview
    @lru_cache(maxsize=256)
    def overview(self, w):
        k = w + timedelta(7)
        last4 = self.window(w, 4)
        ly4 = [x - timedelta(364) for x in last4]
        s4 = self.sales_w.reindex(last4)
        sold4, lost4 = float(s4.units_sold.sum()), float(s4.units_lost.sum())
        ly = self.sales_w.reindex(ly4).units_sold
        sold_ly4 = float(ly.sum()) if ly.notna().all() else None

        iw = self.inv_w.reindex([w]).iloc[0]
        inv_now = self.inv[self.inv.week_start == w]
        missing = inv_now[~inv_now.report_received].depot_id.unique().tolist()

        pf_cover = float(self.pf_cover_w.get(w, np.nan))
        kc = self.known_closures(w)
        longest = int(kc.days.max()) if len(kc) else 0
        closed_days = int(self.road_closed_days_w.get(w, 0))

        # tiles -------------------------------------------------------
        prev = self.weeks[self.weeks.index(w) - 1] if self.weeks.index(w) > 0 else None
        sold_w = float(self.sales_w.units_sold.get(w, 0))
        sold_prev = float(self.sales_w.units_sold.get(prev, np.nan)) if prev else np.nan
        po4 = self.po[(self.po.order_date >= last4[0] - timedelta(1)) & (self.po.order_date <= k)]
        not_shipped = int(po4.status.str.startswith("not shipped").sum())
        late = int(((po4.received_date.notna()) & (po4.received_date <= k) & (po4.days_late > 0)).sum())
        air_ytd = float(self.po[(self.po["mode"] == "air") & (self.po.order_date <= k) &
                                (self.po.order_date >= date(w.year, 1, 1))].freight_cost_inr.fillna(0).sum())
        rc = self.region_cover_w.reindex([w]).iloc[0]
        spark = self.window(w, 12)

        tiles = [
            dict(key="demand", name="Demand", href="/demand",
                 value=sold_w, value_kind="bottles", label="sold this week",
                 lines=[f"{_pct(sold_w / sold_prev - 1)} vs last week" if sold_prev == sold_prev and sold_prev else "first week",
                        f"Quick commerce {self.qc_share_w.get(w, 0):.0%} of sales"],
                 spark=[float(self.sales_w.units_sold.get(x, 0)) for x in spark], state="neutral"),
            dict(key="supply", name="Supply", href="/supply",
                 value=pf_cover, value_kind="days", label="passionfruit cover at plants",
                 lines=[f"Plants {self.util_w.get(w, 0):.0%} utilised",
                        "Co-packer running" if self.cp_w.get(w, 0) > 0 else "Co-packer idle"],
                 spark=[float(self.pf_cover_w.get(x, np.nan)) for x in spark],
                 state="bad" if pf_cover < 7 else "neutral", value_bad=pf_cover < 7),
            dict(key="inventory", name="Inventory", href="/inventory",
                 value=float(iw.median_cover), value_kind="days", label="median depot cover (target 21)",
                 lines=[f"{int(iw.stockouts)} depot-flavor stock-outs", f"{iw.aged_share:.0%} of stock under 60 days left"],
                 spark=[float(self.inv_w.below7.get(x, np.nan)) for x in spark],
                 state="bad" if iw.stockouts > 0 else "neutral", spark_label="pairs below 7 days"),
            dict(key="distribution", name="Distribution", href="/distribution",
                 value=float(self.region_spread_w.get(w, np.nan)), value_kind="days", label="cover gap between regions",
                 lines=[f"Highest {rc.idxmax()} {rc.max():.0f} d · lowest {rc.idxmin()} {rc.min():.0f} d",
                        "0 depot transfers in last 4 weeks"],
                 spark=[float(self.region_spread_w.get(x, np.nan)) for x in spark], state="neutral"),
            dict(key="transport", name="Transportation", href="/transportation",
                 value=None, value_text="Closed" if closed_days else "Open", label="passionfruit highway",
                 lines=[f"{not_shipped} pulp orders not shipped, {late} late (4 wks)",
                        f"Air freight {w.year}: {_inr(air_ytd)}"],
                 spark=[float(self.pf_road_w.get(x, 0)) for x in spark],
                 state="bad" if closed_days else "neutral", value_bad=bool(closed_days), spark_label="passionfruit by road (kg)"),
        ]

        trend_weeks = self.window(w, 26)
        tr = self.sales_w.reindex(trend_weeks)
        trend = dict(weeks=trend_weeks, sold=tr.units_sold.fillna(0).tolist(), lost=tr.units_lost.fillna(0).tolist())

        # network state -----------------------------------------------
        so = inv_now[inv_now.stock_status == "stock-out"]
        region_out = {r: int((so.region == r).sum()) for r in REGIONS}
        net = dict(road_closed=bool(closed_days), pf_cover=pf_cover, cp_on=bool(self.cp_w.get(w, 0) > 0),
                   region_out=region_out, region_cover={r: float(rc.get(r, np.nan)) for r in REGIONS},
                   dp_live=w >= date(2026, 3, 2))

        return dict(
            week=w, known_by=k,
            kpi=dict(sold4=sold4, sold_ly4=sold_ly4, lost4=lost4, below7=int(iw.below7), stockouts=int(iw.stockouts),
                     pairs=int(iw.pairs), missing=missing, pf_cover=pf_cover, longest_closure=longest,
                     closed_days=closed_days),
            tiles=tiles, trend=trend, net=net)


    # ------------------------------------------------------------------ supply page
    INGR_ORDER = ["passionfruit", "dragonfruit", "mango", "peach", "basil", "guava"]
    SUPPLIER_NAMES = {"S_PASSION": "Passionfruit cooperative", "S_DRAGON_DOM": "Dragonfruit, domestic",
                      "S_DRAGON_IMP": "Dragonfruit, imported", "S_MANGO": "Mango processors", "S_PEACH": "Peach orchards",
                      "S_BASIL": "Basil farms", "S_GUAVA1": "Guava supplier 1", "S_GUAVA2": "Guava supplier 2"}

    def _pulp_daily_use(self, ing, w):
        """Average daily use over the 4 weeks before week w, both plants together (kg/day)."""
        prior = [x for x in self.window(w, 5)[:-1]] or [w]          # first week: use the week itself
        p = self.pulp[(self.pulp.ingredient == ing) & (self.pulp.week_start.isin(prior))]
        return float(p.consumption_kg.sum()) / max(7 * len(prior), 1)

    @lru_cache(maxsize=256)
    def supply(self, w, po_filter="all"):
        k = w + timedelta(7)
        pw = self.pulp[self.pulp.week_start == w].copy()
        kc = self.known_closures(w)
        longest = int(kc.days.max()) if len(kc) else 0

        # --- top strip
        pf_cover = float(self.pf_cover_w.get(w, np.nan))
        df_now = pw[pw.ingredient == "dragonfruit"]
        df_close = float(df_now.closing_kg.sum())
        df_use = self._pulp_daily_use("dragonfruit", w) or np.nan
        imp = self.po[(self.po["mode"] == "sea") & (self.po.order_date <= k)]
        in_transit = imp[imp.received_date.isna() | (imp.received_date > k)]
        transit_kg = float(in_transit.qty_kg.sum())
        util = float(self.util_w.get(w, np.nan))
        cp_units = float(self.cp_w.get(w, 0))
        last4 = self.window(w, 4)
        po4 = self.po[(self.po.order_date >= last4[0] - timedelta(1)) & (self.po.order_date <= k)]
        not_shipped = int(po4.status.str.startswith("not shipped").sum())
        late = int(((po4.received_date.notna()) & (po4.received_date <= k) & (po4.days_late > 0)).sum())

        # --- ingredient cover by plant
        rows = []
        for ing in self.INGR_ORDER:
            for plant in ("P1", "P2"):
                r = pw[(pw.ingredient == ing) & (pw.plant == plant)]
                if r.empty:
                    continue
                r = r.iloc[0]
                rows.append(dict(plant=plant, ingredient=ing, opening=r.opening_kg, road=r.receipts_road_kg,
                                 imp=r.receipts_import_kg, air=r.receipts_air_kg, used=r.consumption_kg,
                                 closing=r.closing_kg, cover=r.days_of_cover, target=r.target_cover_days))

        # --- passionfruit cover chart (26 weeks)
        cw = self.window(w, 26)
        pf_series = dict(weeks=cw, values=[float(self.pf_cover_w.get(x, np.nan)) for x in cw],
                         closed=[int(self.road_closed_days_w.get(x, 0)) > 0 for x in cw], ref=longest)

        # --- single-source exposure (share of last-4-week bottles that need each supplier)
        s4 = self.dem[self.dem.week_start.isin(last4)].groupby("sku_id").units_sold.sum()
        total = float(s4.sum()) or 1.0
        mix = {r.sku_id: dict(p.rsplit(" ", 1) for p in r.pulp_mix.split("; ")) for r in self.sku.itertuples()}
        uses = lambda ing: [s for s, m in mix.items() if ing in m]
        sup = self.depots  # noqa  (keeps linters quiet; suppliers table read below)
        suppliers = pd.read_csv(DATA / "suppliers.csv", encoding="utf-8-sig")
        ing_of = {"S_PASSION": "passionfruit", "S_DRAGON_DOM": "dragonfruit", "S_DRAGON_IMP": "dragonfruit",
                  "S_MANGO": "mango", "S_PEACH": "peach", "S_BASIL": "basil", "S_GUAVA1": "guava", "S_GUAVA2": "guava"}
        exposure = []
        for r in suppliers.itertuples():
            fl = uses(ing_of[r.supplier_id])
            share = float(s4.reindex(fl).fillna(0).sum()) / total
            exposure.append(dict(supplier=self.SUPPLIER_NAMES[r.supplier_id], single=r.single_source == "Y",
                                 flavors=fl, share=share, mode=r.mode, lead=r.lead_time_days, cycle=r.order_cycle))
        exposure.sort(key=lambda x: (-x["single"], -x["share"]))

        # --- import pipeline
        pipe = []
        for r in imp.sort_values("order_date", ascending=False).head(6).itertuples():
            received = r.received_date if (r.received_date is not None and r.received_date == r.received_date and r.received_date <= k) else None
            if received:
                state = "late" if r.days_late > 0 else "on time"
            else:
                state = "overdue" if r.promised_date < k else "on the water"
            pipe.append(dict(ordered=r.order_date, qty=r.qty_kg, due=r.promised_date, received=received,
                             late=(r.days_late if received else None), state=state))

        # --- production this week
        pr = self.prod[self.prod.week_start == w]
        req = pr[pr.plant != "CP"].groupby("sku_id").units_requested.sum()
        made = pr.groupby("sku_id").units_produced.sum()
        cp_made = pr[pr.plant == "CP"].groupby("sku_id").units_produced.sum()
        production = [dict(sku=s, requested=float(req.get(s, 0)), produced=float(made.get(s, 0)),
                           copacker=float(cp_made.get(s, 0))) for s in ["MPB", "GC", "PP", "DB", "DP"] if s in made.index]
        cp_cost_week = float(pr[pr.plant == "CP"].extra_cost_inr.sum())
        cp_cost_ytd = float(self.prod[(self.prod.plant == "CP") & (self.prod.week_start <= w) &
                                      (self.prod.week_start >= date(w.year, 1, 1))].extra_cost_inr.sum())
        util_spark = [float(self.util_w.get(x, np.nan)) for x in self.window(w, 12)]

        # --- purchase-order log (last 4 weeks)
        log = po4.sort_values("order_date", ascending=False).copy()
        def state(r):
            if str(r.status).startswith("not shipped"):
                return "not shipped"
            if r["mode"] == "air":
                return "air"
            if r.received_date is None or r.received_date != r.received_date or r.received_date > k:
                return "due"
            return "late" if r.days_late > 0 else "received"
        log["state"] = log.apply(state, axis=1)
        counts = log.state.value_counts().to_dict()
        if po_filter != "all":
            log = log[log.state == po_filter]
        po_rows = [dict(ordered=r.order_date, supplier=self.SUPPLIER_NAMES.get(r.supplier, r.supplier), ingredient=r.ingredient,
                        mode=r.mode, qty=r.qty_kg, due=r.promised_date,
                        received=r.received_date if r.state in ("received", "late", "air") else None,
                        late=r.days_late if r.state == "late" else None, state=r.state, cost=r.freight_cost_inr)
                   for r in log.head(40).itertuples()]

        return dict(
            kpi=dict(pf_cover=pf_cover, longest=longest, closed_days=int(self.road_closed_days_w.get(w, 0)),
                     df_cover=df_close / df_use if df_use == df_use else np.nan, df_transit_days=transit_kg / df_use if df_use == df_use else np.nan,
                     transit_orders=len(in_transit), util=util, cp_units=cp_units, not_shipped=not_shipped, late=late),
            cover_rows=rows, pf_series=pf_series, exposure=exposure, pipeline=pipe, production=production,
            cp_cost_week=cp_cost_week, cp_cost_ytd=cp_cost_ytd, util_spark=util_spark,
            po_rows=po_rows, po_counts=counts, po_filter=po_filter, po_total=len(po4))


    # ------------------------------------------------------------------ inventory page
    TARGET = 21                                         # case F45

    def _cover_class(self, cover, status, received=True, target=None):
        T = target or self.TARGET
        if not received:
            return "missing"
        if status == "stock-out":
            return "out"
        if cover != cover:
            return "missing"
        if cover < 7:
            return "critical"
        if cover < 0.75 * T:
            return "low"
        if cover > 1.5 * T:
            return "over"
        return "ok"

    def _inv_extra(self):
        if hasattr(self, "_inv_ready"):
            return
        self.wo = _read("writeoffs_discounts_weekly", ["week_start"]).merge(self.depots[["depot_id", "region"]], on="depot_id")
        self.batches = _read("stock_batches_weekly", ["week_start", "bottled_date"])
        inv = self.inv.copy()
        inv["cls"] = [self._cover_class(c, s, r) for c, s, r in zip(inv.days_of_cover, inv.stock_status, inv.report_received)]
        self.inv_cls = inv
        self.status_w = inv.groupby(["week_start", "cls"]).size().unstack(fill_value=0)
        num = ["opening_stock", "receipts", "transfers_in", "transfers_out", "units_sold", "units_written_off", "closing_stock"]
        a = inv[num].apply(pd.to_numeric, errors="coerce")
        inv["ledger_gap"] = (a.opening_stock + a.receipts + a.transfers_in - a.transfers_out - a.units_sold
                             - a.units_written_off - a.closing_stock)
        self.ledger_breaks = inv[inv.report_received & (inv.ledger_gap.abs() > 2)]
        self._inv_ready = True

    @lru_cache(maxsize=16)
    def _status_w(self, target):
        inv = self.inv_cls
        cls = [self._cover_class(c, s, r, target) for c, s, r in zip(inv.days_of_cover, inv.stock_status, inv.report_received)]
        return inv.assign(cls=cls).groupby(["week_start", "cls"]).size().unstack(fill_value=0)

    @lru_cache(maxsize=256)
    def inventory(self, w, depot=None, basis="forecast", target=21):
        """target: depot cover target in days (Control Panel g04, case F45)."""
        self._inv_extra()
        now = self.inv_cls[self.inv_cls.week_start == w].copy()
        if basis == "sales":
            now["days_of_cover"] = now.cover_actual
        now["cls"] = [self._cover_class(c, st, r, target) for c, st, r in zip(now.days_of_cover, now.stock_status, now.report_received)]
        rec = now[now.report_received]
        dep_list = self.depots.depot_id.tolist()
        depot = depot if depot in dep_list else None

        # --- top strip
        lost_w = float(self.dem[self.dem.week_start == w].units_lost.sum())
        wo_ytd = self.wo[(self.wo.week_start <= w) & (self.wo.week_start >= date(w.year, 1, 1))]
        kpi = dict(median=float(rec.days_of_cover.median()), below7=int((rec.days_of_cover < 7).sum()), pairs=len(now),
                   stockouts=int((rec.stock_status == "stock-out").sum()), lost_w=lost_w,
                   aged=float(rec.stock_under_60_days_left.sum()), aged_share=float(rec.stock_under_60_days_left.sum() / max(rec.closing_stock.sum(), 1)),
                   wo_ytd=float(wo_ytd.total_cost_inr.sum()), disc_ytd=float(wo_ytd.discount_cost_inr.sum()),
                   woff_ytd=float(wo_ytd.writeoff_cost_inr.sum()))

        # --- heatmap
        skus = [s for s in ["MPB", "GC", "PP", "DB", "DP"] if s in now.sku_id.unique()]
        heat = []
        for d in dep_list:
            row = dict(depot=d, region=self.depots.set_index("depot_id").region[d], cells=[])
            for s in skus:
                r = now[(now.depot_id == d) & (now.sku_id == s)]
                if r.empty:
                    row["cells"].append(None); continue
                r = r.iloc[0]
                row["cells"].append(dict(sku=s, cover=r.days_of_cover, cls=r.cls, closing=r.closing_stock))
            heat.append(row)

        # --- status over 26 weeks
        sw = self.window(w, 26)
        st = self._status_w(target).reindex(sw).fillna(0)
        status = dict(weeks=sw, series={c: [int(st[c].get(x, 0)) if c in st else 0 for x in sw]
                                        for c in ["out", "critical", "low", "ok", "over", "missing"]})

        # --- stock age (batches at the end of week w)
        b = self.batches[self.batches.week_start == w]
        gtmax = 80
        bins = [("0–30 days · any channel", b.age_days <= 30), ("31–60 days · general trade only", (b.age_days > 30) & (b.age_days <= 60)),
                (f"61–{gtmax} days · last chance", (b.age_days > 60) & (b.age_days <= gtmax))]
        age = []
        for s in skus:
            bs = b[b.sku_id == s]
            tot = float(bs.units.sum()) or 1.0
            age.append(dict(sku=s, total=float(bs.units.sum()),
                            parts=[float(bs[m.loc[bs.index]].units.sum()) / tot for _, m in bins]))
        age_labels = [n for n, _ in bins]

        # --- write-offs and discounts
        wo_fl = wo_ytd.groupby("sku_id").total_cost_inr.sum()
        wo_rg = wo_ytd.groupby("region").total_cost_inr.sum()
        wo_trend_w = self.window(w, 26)
        wt = self.wo.groupby("week_start").total_cost_inr.sum()
        wo = dict(by_flavor=[(s, float(wo_fl.get(s, 0))) for s in ["MPB", "GC", "PP", "DB", "DP"]],
                  by_region=[(r, float(wo_rg.get(r, 0))) for r in REGIONS],
                  trend=[float(wt.get(x, 0)) for x in wo_trend_w])

        # --- depot detail
        worst = rec.assign(bad=rec.cls.isin(["out", "critical"])).groupby("depot_id").bad.sum().sort_values(ascending=False)
        depot = depot or (worst.index[0] if len(worst) and worst.iloc[0] > 0 else dep_list[0])
        det = now[now.depot_id == depot].sort_values("sku_id", key=lambda s: s.map({k: i for i, k in enumerate(["MPB", "GC", "PP", "DB", "DP"])}))
        detail = [dict(sku=r.sku_id, opening=r.opening_stock, receipts=r.receipts, sold=r.units_sold, disc=r.units_sold_at_discount,
                       woff=r.units_written_off, closing=r.closing_stock, p50=r.p50_week, p80=r.p80_week, cover=r.days_of_cover,
                       aged=r.stock_under_60_days_left, cls=r.cls, received=r.report_received) for r in det.itertuples()]

        # --- data quality
        missing = sorted(now[~now.report_received].depot_id.unique().tolist())
        breaks = self.ledger_breaks[self.ledger_breaks.week_start <= w].sort_values("week_start", ascending=False).head(5)
        quality = dict(missing=missing, breaks=[dict(week=r.week_start, depot=r.depot_id, sku=r.sku_id, closing=r.closing_stock,
                                                     gap=r.ledger_gap) for r in breaks.itertuples()],
                       missing_hist=self.inv[(~self.inv.report_received) & (self.inv.week_start <= w)]
                       .groupby(["week_start", "depot_id"]).size().reset_index().tail(5).to_dict("records"))

        return dict(basis=basis, target=target, kpi=kpi, skus=skus, heat=heat, status=status, age=age, age_labels=age_labels, wo=wo,
                    wo_weeks=wo_trend_w, depot=depot, depots=dep_list, detail=detail, quality=quality)


    # ------------------------------------------------------------------ demand page
    SKUS = ["MPB", "GC", "PP", "DB", "DP"]

    def _dem_extra(self):
        if hasattr(self, "_dem_ready"):
            return
        self.fc = _read("forecast_monthly")
        d = self.dem.copy()
        d["month"] = [f"{x.year}-{x.month:02d}" for x in d.week_start]
        self.dem_m = d.groupby(["month", "depot_id", "sku_id"]).units_sold.sum()
        self.band_w = self.inv.groupby(["week_start", "sku_id"])[["p50_week", "p80_week"]].sum()
        self.qc_day = self.qc.groupby(["date", "sku_id"]).units_sold.sum()
        self.qc_oos = self.qc.groupby(["date", "sku_id"]).out_of_stock.sum()
        self._dem_ready = True

    def _accuracy(self, month):
        """Old forecast vs actual for one month, depot x flavor (weeks assigned to the month they start in)."""
        f = self.fc[self.fc.month == month].set_index(["depot_id", "sku_id"]).p50_units
        if f.empty or month not in self.dem_m.index.get_level_values(0):
            return None
        a = self.dem_m.loc[month]
        j = pd.concat([a.rename("a"), f.rename("f")], axis=1).dropna()
        j = j[j.a > 0]
        if j.empty:
            return None
        out = dict(mape=float((abs(j.a - j.f) / j.a).mean()), bias=float(j.a.sum() / j.f.sum() - 1), by_sku={})
        for s, g in j.groupby(level="sku_id"):
            out["by_sku"][s] = dict(mape=float((abs(g.a - g.f) / g.a).mean()), bias=float(g.a.sum() / g.f.sum() - 1))
        return out

    @lru_cache(maxsize=256)
    def demand(self, w, flavor="all", qcf=None):
        self._dem_extra()
        last_day = w + timedelta(6)
        live = [s for s in self.SKUS if s != "DP" or w >= date(2026, 3, 2)]
        flavor = flavor if flavor in live else "all"
        qcf = qcf if qcf in live else ("DP" if "DP" in live else "MPB")

        dw = self.dem[self.dem.week_start == w]
        sold, ordered, lost = float(dw.units_sold.sum()), float(dw.units_ordered.sum()), float(dw.units_lost.sum())
        ly = self.dem[self.dem.week_start == w - timedelta(364)]
        sold_ly = float(ly.units_sold.sum()) if len(ly) else None

        # last completed months (month fully over by the end of week w)
        months = []
        m = date(last_day.year, last_day.month, 1) - timedelta(1)          # last day of previous month
        for _ in range(3):
            months.append(f"{m.year}-{m.month:02d}")
            m = date(m.year, m.month, 1) - timedelta(1)
        acc = [(mo, self._accuracy(mo)) for mo in months]
        acc = [(mo, a) for mo, a in acc if a]
        last_acc = acc[0] if acc else (None, None)

        # quick-commerce pulse: last 7 days vs previous 28-day average
        days7 = [last_day - timedelta(i) for i in range(7)]
        days28 = [last_day - timedelta(i) for i in range(7, 35)]
        pulse = []
        for s in live:
            a = float(sum(self.qc_day.get((d, s), 0) for d in days7))
            b = float(sum(self.qc_day.get((d, s), 0) for d in days28)) / 4
            oosd = sum(1 for d in days7 if self.qc_oos.get((d, s), 0) > 0)
            pulse.append(dict(sku=s, last7=a, mult=(a / b) if b > 0 else None, oos_days=oosd))
        top = max([p for p in pulse if p["mult"]], key=lambda p: p["mult"], default=None)

        # demand vs forecast, 26 weeks
        ww = self.window(w, 26)
        dd = self.dem[self.dem.week_start.isin(ww)]
        if flavor != "all":
            dd = dd[dd.sku_id == flavor]
        g = dd.groupby("week_start")[["units_sold", "units_ordered"]].sum().reindex(ww).fillna(0)
        band = self.band_w.reset_index()
        band = band[band.week_start.isin(ww)]
        if flavor != "all":
            band = band[band.sku_id == flavor]
        band = band.groupby("week_start")[["p50_week", "p80_week"]].sum().reindex(ww)
        dvf = dict(weeks=ww, sold=g.units_sold.tolist(), ordered=g.units_ordered.tolist(),
                   p50=band.p50_week.tolist(), p80=band.p80_week.tolist())

        # signal gap: QC daily, last 70 days; Planning has data only to the last month-end
        days = [last_day - timedelta(i) for i in range(69, -1, -1)]
        series = [float(self.qc_day.get((d, qcf), 0)) if (qcf != "DP" or d >= date(2026, 3, 2)) else None for d in days]
        cutoff = date(last_day.year, last_day.month, 1) - timedelta(1)
        if last_day == (date(last_day.year + last_day.month // 12, last_day.month % 12 + 1, 1) - timedelta(1)):
            cutoff = last_day
        base = [v for d, v in zip(days, series) if v and d <= cutoff][-28:]
        oos = [int(self.qc_oos.get((d, qcf), 0)) for d in days]
        gap = dict(days=days, values=series, cutoff=cutoff, sku=qcf, oos=oos,
                   seen_mkt=(sum(v for v in series[-7:] if v) / 7) if series[-7:] else 0,
                   seen_plan=(sum(base[-7:]) / max(len(base[-7:]), 1)) if base else 0,
                   lag=(last_day - cutoff).days)

        # mix, last 4 weeks
        l4 = self.window(w, 4)
        m4 = self.dem[self.dem.week_start.isin(l4)]
        tot = float(m4.units_sold.sum()) or 1.0
        by_ch = m4.groupby(["sku_id", "channel_id"]).units_sold.sum() / tot
        by_rg = m4.groupby(["sku_id", "region"]).units_sold.sum() / tot
        by_fl = m4.groupby("sku_id").units_sold.sum() / tot
        mix = dict(skus=live, ch={s: {c: float(by_ch.get((s, c), 0)) for c in ["C_GT", "C_MT", "C_QC"]} for s in live},
                   rg={s: {r: float(by_rg.get((s, r), 0)) for r in REGIONS} for s in live},
                   fl={s: float(by_fl.get(s, 0)) for s in live},
                   ch_tot={c: float(m4[m4.channel_id == c].units_sold.sum() / tot) for c in ["C_GT", "C_MT", "C_QC"]},
                   rg_tot={r: float(m4[m4.region == r].units_sold.sum() / tot) for r in REGIONS})
        lost4 = dict(fl=[(s, float(m4[m4.sku_id == s].units_lost.sum())) for s in live],
                     rg=[(r, float(m4[m4.region == r].units_lost.sum())) for r in REGIONS])

        return dict(
            kpi=dict(sold=sold, sold_ly=sold_ly, ordered=ordered, lost=lost, fill=sold / ordered if ordered else None,
                     acc_month=last_acc[0], acc=last_acc[1], top=top),
            live=live, flavor=flavor, dvf=dvf, gap=gap, pulse=pulse, mix=mix, acc=acc, lost4=lost4)


    # ------------------------------------------------------------------ distribution page
    def _dist_extra(self):
        if hasattr(self, "_dist_ready"):
            return
        self.xfer = _read("transfers", ["date"])
        self._dist_ready = True

    @lru_cache(maxsize=256)
    def distribution(self, w, target=21, xfer_cost=1.5):
        """target: depot cover target (g04, F45); xfer_cost: INR per bottle moved (a08, F50)."""
        self._dist_extra()
        self._inv_extra()
        last4 = self.window(w, 4)
        k = w + timedelta(7)
        inv_now = self.inv[(self.inv.week_start == w) & self.inv.report_received].copy()
        inv_now["p50d"] = inv_now.pace                       # actual sales per day, last 4 weeks
        inv_now["days_of_cover"] = inv_now.cover_actual
        inv_now = inv_now[inv_now.p50d > 0]
        live = [s for s in self.SKUS if s in inv_now.sku_id.unique()]

        # --- top strip
        shipped = float(self.inv[self.inv.week_start == w].receipts.sum())
        pr = self.prod[self.prod.week_start == w]
        cp_share = float(pr[pr.plant == "CP"].units_produced.sum() / max(pr.units_produced.sum(), 1))
        rc = self.region_cover_w.reindex([w]).iloc[0]
        x4 = self.xfer[(self.xfer.date >= last4[0]) & (self.xfer.date < k)]
        xall = self.xfer[self.xfer.date < k]

        # --- mismatches: surplus (> 1.5 x target) at one depot while the same flavor is under 7 days at another
        T = target
        mism, stranded = [], 0.0
        for s in live:
            g = inv_now[inv_now.sku_id == s]
            sur = [(r.depot_id, r.region, float(r.closing_stock - T * r.p50d)) for r in g.itertuples()
                   if r.days_of_cover == r.days_of_cover and r.days_of_cover > 1.5 * T]
            sho = [(r.depot_id, r.region, float((T - r.days_of_cover) * r.p50d), r.days_of_cover) for r in g.itertuples()
                   if r.days_of_cover == r.days_of_cover and r.days_of_cover < 7]
            sur.sort(key=lambda x: -x[2]); sho.sort(key=lambda x: -x[2])
            left = {d: q for d, _, q in sur}
            for d2, r2, need, cov in sho:
                for d1, r1, _ in sur:
                    q = min(need, left[d1])
                    if q < 1000:
                        continue
                    mism.append(dict(sku=s, from_d=d1, from_r=r1, to_d=d2, to_r=r2, to_cover=cov, units=q,
                                     cost=q * xfer_cost, same_region=r1 == r2))
                    left[d1] -= q; need -= q; stranded += q
                    if need < 1000:
                        break
        mism.sort(key=lambda m: -m["units"])

        # --- flows, last 4 weeks
        rec4 = self.inv[self.inv.week_start.isin(last4)].groupby("region").receipts.sum()
        pr4 = self.prod[self.prod.week_start.isin(last4)]
        cp4 = float(pr4[pr4.plant == "CP"].units_produced.sum() / max(pr4.units_produced.sum(), 1))
        d4 = self.dem[self.dem.week_start.isin(last4)]
        sold_rc = d4.groupby(["region", "channel_id"]).units_sold.sum()
        flows = dict(
            src=[("Plants 1 + 2", 1 - cp4), ("Co-packer", cp4)],
            reg=[(r, float(rec4.get(r, 0))) for r in REGIONS],
            reg_ch=[(r, c, float(sold_rc.get((r, c), 0))) for r in REGIONS for c in ["C_GT", "C_MT", "C_QC"]])

        # --- shipped vs ordered by region
        ord_r = d4.groupby("region").units_ordered.sum()
        tot_s, tot_o = float(rec4.sum()) or 1, float(ord_r.sum()) or 1
        alloc = [dict(region=r, shipped=float(rec4.get(r, 0)) / tot_s, ordered=float(ord_r.get(r, 0)) / tot_o) for r in REGIONS]

        # --- regional balance by flavor
        g = inv_now.groupby(["sku_id", "region"])[["closing_stock", "p50d"]].sum()
        bal = {s: {r: (float(g.loc[(s, r)].closing_stock / g.loc[(s, r)].p50d) if (s, r) in g.index and g.loc[(s, r)].p50d > 0 else None)
                   for r in REGIONS} for s in live}

        # --- fill by region x channel
        f = d4.groupby(["region", "channel_id"])[["units_sold", "units_ordered"]].sum()
        fill = {r: {c: (float(f.loc[(r, c)].units_sold / f.loc[(r, c)].units_ordered) if (r, c) in f.index and f.loc[(r, c)].units_ordered else None)
                    for c in ["C_GT", "C_MT", "C_QC"]} for r in REGIONS}

        return dict(target=T, kpi=dict(shipped=shipped, cp_share=cp_share, gap=float(rc.max() - rc.min()), hi=rc.idxmax(), lo=rc.idxmin(),
                             hi_v=float(rc.max()), lo_v=float(rc.min()), stranded=stranded, x4=len(x4), x4_units=float(x4.units.sum()),
                             xall=len(xall)),
                    mism=mism[:12], mism_n=len(mism), flows=flows, alloc=alloc, bal=bal, live=live, fill=fill)


    # ------------------------------------------------------------------ transportation page
    @lru_cache(maxsize=256)
    def transportation(self, w):
        self._dist_extra()
        k = w + timedelta(7)
        last13 = self.window(w, 13)
        po = self.po[self.po.order_date <= k].copy()
        po["arrived"] = po.received_date.notna() & (po.received_date <= k)
        recent = po[po.order_date >= last13[0] - timedelta(1)]

        # --- highway
        closed_days = int(self.road_closed_days_w.get(w, 0))
        kc = self.known_closures(w)
        hist = []
        for r in self.closures.sort_values("year").itertuples():
            known = r.closed == "Y" and r.start is not None and r.start == r.start and r.start <= k
            in_past_year = r.year < w.year or (r.year == w.year and r.start is not None and r.start == r.start and r.start <= k)
            if r.year <= w.year:
                hist.append(dict(year=r.year, closed=bool(known), days=int(r.days) if known else 0,
                                 start=r.start if known else None, end=r.end if known else None,
                                 ongoing=bool(known and r.end >= w and r.start <= w + timedelta(6))))
        summers = [h for h in hist if h["year"] < w.year or (h["year"] == w.year and w.month > 6)]

        # --- lanes (inbound, outbound, lateral)
        def lane(name, f, mode, lead, freq, single):
            g = recent[f(recent)]
            done = g[g.arrived]
            on_time = float((done.days_late <= 0).mean()) if len(done) else None
            return dict(name=name, mode=mode, lead=lead, freq=freq, single=single, n=len(g),
                        on_time=on_time, late=int((done.days_late > 0).sum()), blocked=int(g.status.str.startswith("not shipped").sum()),
                        avg_late=float(done[done.days_late > 0].days_late.mean()) if (done.days_late > 0).any() else 0.0)
        lanes = [
            lane("Passionfruit cooperative → plants", lambda g: (g.supplier == "S_PASSION") & (g["mode"] == "road"), "road", "3 days", "weekly", True),
            lane("Passionfruit by air (contingency)", lambda g: (g.supplier == "S_PASSION") & (g["mode"] == "air"), "air", "booked when needed", "as needed", False),
            lane("Imported dragonfruit → plants", lambda g: g["mode"] == "sea", "sea", "6–8 weeks", "quarterly", False),
            lane("Domestic dragonfruit → plants", lambda g: g.supplier == "S_DRAGON_DOM", "road", "3 days", "weekly", False),
            lane("Mango, peach, basil → plants", lambda g: g.supplier.isin(["S_MANGO", "S_PEACH", "S_BASIL"]), "road", "3 days", "weekly", False),
            lane("Guava (2 suppliers) → plants", lambda g: g.supplier.isin(["S_GUAVA1", "S_GUAVA2"]), "road", "3 days", "weekly", False),
        ]
        arrived13 = recent[recent.arrived]
        on_time_all = float((arrived13.days_late <= 0).mean()) if len(arrived13) else None

        # --- freight cost
        air = po[(po["mode"] == "air")]
        air_ytd = air[air.order_date >= date(w.year, 1, 1)]
        air_cost = float(air_ytd.freight_cost_inr.fillna(0).sum())
        air_kg = float(air_ytd.qty_kg.sum())

        # --- passionfruit arrivals, 26 weeks
        ww = self.window(w, 26)
        pf = self.pulp[self.pulp.ingredient == "passionfruit"].groupby("week_start")[["receipts_road_kg", "receipts_air_kg"]].sum()
        arrivals = dict(weeks=ww, road=[float(pf.receipts_road_kg.get(x, 0)) for x in ww],
                        air=[float(pf.receipts_air_kg.get(x, 0)) for x in ww],
                        closed=[int(self.road_closed_days_w.get(x, 0)) > 0 for x in ww])

        # --- imports on the water
        imp = po[po["mode"] == "sea"]
        water = imp[~imp.arrived]
        ships = [dict(ordered=r.order_date, qty=r.qty_kg, eta=r.promised_date, days=(k - r.order_date).days,
                      overdue=r.promised_date < k) for r in water.itertuples()]

        # --- outbound: plant -> depots by region, 26 weeks; transfers on record
        ob = self.inv[self.inv.week_start.isin(ww)].groupby(["week_start", "region"]).receipts.sum().unstack().reindex(ww).fillna(0)
        outbound = dict(weeks=ww, series={r: ob[r].tolist() if r in ob else [0] * len(ww) for r in REGIONS})
        xfer = self.xfer[self.xfer.date < k].sort_values("date", ascending=False)
        transfers = [dict(date=r.date, frm=r.from_depot, to=r.to_depot, sku=r.sku_id, units=r.units, cost=r.cost_inr, lead=r.lead_time_days)
                     for r in xfer.head(8).itertuples()]

        return dict(kpi=dict(closed_days=closed_days, n_closures=len([h for h in summers if h["closed"]]), n_summers=len(summers),
                             longest=int(kc.days.max()) if len(kc) else 0, on_time=on_time_all, n13=len(arrived13),
                             air_cost=air_cost, air_kg=air_kg, air_normal=air_cost / 5 if air_cost else 0,
                             water_n=len(water), water_kg=float(water.qty_kg.sum()), next_eta=min([s["eta"] for s in ships], default=None)),
                    hist=hist, lanes=lanes, arrivals=arrivals, ships=ships, outbound=outbound, transfers=transfers,
                    shipped_w=float(self.inv[self.inv.week_start == w].receipts.sum()))


    # ------------------------------------------------------------------ data & assumptions page
    TABLES = [  # name, grain, when the company sees it, used on
        ("demand_weekly", "week × depot × channel × flavor", "weekly depot reports (consolidated to Planning at month-end today)", "Overview, Demand, Distribution"),
        ("qc_sellthrough_daily", "day × depot × flavor", "next day, to Marketing", "Demand"),
        ("forecast_monthly", "month × depot × flavor", "set at the start of each month", "Demand"),
        ("inventory_weekly", "week × depot × flavor", "Monday after the week", "Overview, Inventory, Distribution"),
        ("stock_batches_weekly", "week × depot × flavor × batch", "Monday after the week", "Inventory"),
        ("writeoffs_discounts_weekly", "week × depot × flavor", "Monday after the week", "Inventory"),
        ("transfers", "one row per transfer", "on the day", "Distribution, Transportation"),
        ("production_weekly", "week × plant × flavor", "end of the week", "Supply, Distribution"),
        ("pulp_ledger_weekly", "week × plant × ingredient", "start of the week (opening stock)", "Overview, Supply, Transportation"),
        ("purchase_orders", "one row per pulp order", "on order; received date when it arrives", "Supply, Transportation"),
        ("closures_history", "one row per summer", "as closures happen", "Overview, Transportation"),
        ("calendar_weekly", "week", "–", "all pages"),
        ("sku", "flavor", "–", "all pages"),
        ("depots", "depot", "–", "all pages"),
        ("suppliers", "supplier", "–", "Supply"),
        ("parameters", "setting", "–", "this page"),
        ("dataset_checks", "check", "–", "this page"),
    ]

    @lru_cache(maxsize=8)
    def reference(self, w, src="all"):
        self._inv_extra()
        params = _read("parameters")
        params["group"] = params.data_source.str.split(" ").str[0].str.replace(r"[^A-Za-z]", "", regex=True)
        counts = params.group.value_counts().to_dict()
        if src != "all":
            params = params[params.group == src]
        checks = _read("dataset_checks")
        tables = []
        for name, grain, seen, used in self.TABLES:
            p = DATA / f"{name}.csv"
            n = sum(1 for _ in open(p, encoding="utf-8-sig")) - 1 if p.exists() else 0
            tables.append(dict(name=name, rows=n, grain=grain, seen=seen, used=used))
        miss = self.inv[(~self.inv.report_received) & (self.inv.week_start <= w)]
        brk = self.ledger_breaks[self.ledger_breaks.week_start <= w]
        return dict(params=params.to_dict("records"), counts=counts, src=src, checks=checks.to_dict("records"),
                    n_pass=int((checks.status == "pass").sum()), n_checks=len(checks), tables=tables,
                    missing=miss.groupby(["week_start", "depot_id"]).size().reset_index().to_dict("records"),
                    breaks=brk[["week_start", "depot_id", "sku_id", "closing_stock", "ledger_gap"]].to_dict("records"))


def _pct(x):
    if x is None or x != x:
        return "–"
    return f"{'+' if x >= 0 else '−'}{abs(x):.0%}"


def _inr(x):
    if x >= 1e7:
        return f"₹{x / 1e7:.1f} Cr"
    if x >= 1e5:
        return f"₹{x / 1e5:.1f} L"
    return f"₹{x:,.0f}"


STORE = None


def store():
    global STORE
    if STORE is None:
        STORE = Store()
    return STORE
