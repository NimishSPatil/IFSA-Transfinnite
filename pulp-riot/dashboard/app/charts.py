"""
charts.py - small server-rendered SVG charts. No JavaScript libraries, no CDN:
the dashboard must render with the wifi off, like the CRM.
"""
import math

ACCENT = "#2251FF"
DANGER = "#b91c1c"
MUTED = "#94a3b8"
GRID = "#eef0f6"


def _ok(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def sparkline(values, w=132, h=34, color=ACCENT):
    pts = [(i, v) for i, v in enumerate(values) if _ok(v)]
    if len(pts) < 2:
        return f'<svg width="{w}" height="{h}"></svg>'
    lo = min(v for _, v in pts); hi = max(v for _, v in pts)
    span = (hi - lo) or 1
    n = len(values) - 1 or 1
    xy = [(2 + i / n * (w - 4), h - 3 - (v - lo) / span * (h - 6)) for i, v in pts]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    lx, ly = xy[-1]
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/></svg>')


def trend_bars(weeks, sold, lost, w=720, h=230):
    """Weekly units sold (blue) with lost sales stacked on top (red). Values in lakh bottles."""
    left, right, top, bottom = 44, 10, 12, 30
    pw, ph = w - left - right, h - top - bottom
    tot = [s + l for s, l in zip(sold, lost)]
    ymax = max(tot + [1]) / 1e5
    step = _nice(ymax / 4)
    ymax = step * math.ceil(ymax / step)
    n = len(weeks)
    bw = pw / n
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Weekly sales and lost sales">']
    for i in range(0, int(ymax / step) + 1):
        y = top + ph - i * step / ymax * ph
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="10.5" fill="#667085" text-anchor="end">{i * step:g}</text>')
    last_month = None
    for i, (wk, s, l) in enumerate(zip(weeks, sold, lost)):
        x = left + i * bw + bw * 0.14
        bwi = bw * 0.72
        hs = s / 1e5 / ymax * ph
        hl = l / 1e5 / ymax * ph
        y0 = top + ph
        cur = i == n - 1
        out.append(f'<rect x="{x:.1f}" y="{y0 - hs:.1f}" width="{bwi:.1f}" height="{hs:.1f}" rx="2" '
                   f'fill="{ACCENT}" opacity="{1 if cur else .78}"><title>Week of {wk:%d %b %Y}: '
                   f'{s / 1e5:.1f} L sold, {l / 1e5:.1f} L lost</title></rect>')
        if hl > 0.4:
            out.append(f'<rect x="{x:.1f}" y="{y0 - hs - hl:.1f}" width="{bwi:.1f}" height="{hl:.1f}" rx="2" fill="{DANGER}" opacity=".85"/>')
        if wk.month != last_month:
            out.append(f'<text x="{x:.1f}" y="{h - 10}" font-size="10.5" fill="#667085">{wk:%b %y}</text>')
            last_month = wk.month
    out.append('</svg>')
    return "".join(out)


def cover_line(weeks, values, closed, ref=None, w=720, h=210, label="days"):
    """Days-of-cover line; weeks with the highway closed shaded red; dashed line at the reference (longest closure)."""
    left, right, top, bottom = 40, 12, 14, 28
    pw, ph = w - left - right, h - top - bottom
    vals = [v for v in values if _ok(v)] + ([ref] if ref else [])
    ymax = max(vals + [7]) * 1.1
    step = _nice(ymax / 4)
    ymax = step * math.ceil(ymax / step)
    n = len(weeks)
    xw = pw / max(n - 1, 1)
    X = lambda i: left + i * xw
    Y = lambda v: top + ph - v / ymax * ph
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Cover over time">']
    for i, c in enumerate(closed):
        if c:
            out.append(f'<rect x="{X(i) - xw / 2:.1f}" y="{top}" width="{xw:.1f}" height="{ph}" fill="#fee2e2"/>')
    for i in range(0, int(ymax / step) + 1):
        y = Y(i * step)
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="10.5" fill="#667085" text-anchor="end">{i * step:g}</text>')
    y7 = Y(7)
    out.append(f'<line x1="{left}" x2="{w - right}" y1="{y7:.1f}" y2="{y7:.1f}" stroke="#b45309" stroke-dasharray="2 3"/>'
               f'<text x="{w - right - 2}" y="{y7 - 4:.1f}" font-size="10" fill="#b45309" text-anchor="end">7 days</text>')
    if ref:
        yr = Y(ref)
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{yr:.1f}" y2="{yr:.1f}" stroke="{DANGER}" stroke-dasharray="6 4"/>'
                   f'<text x="{w - right - 2}" y="{yr - 4:.1f}" font-size="10" fill="{DANGER}" text-anchor="end">longest closure so far: {ref} days</text>')
    pts = [(X(i), Y(v)) for i, v in enumerate(values) if _ok(v)]
    if pts:
        out.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) +
                   f'" fill="none" stroke="{ACCENT}" stroke-width="2.2" stroke-linejoin="round"/>')
        out.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.5" fill="{ACCENT}"/>')
    last_month = None
    for i, wk in enumerate(weeks):
        if wk.month != last_month:
            out.append(f'<text x="{X(i):.1f}" y="{h - 9}" font-size="10.5" fill="#667085">{wk:%b %y}</text>')
            last_month = wk.month
    out.append(f'<text x="{left - 34}" y="{top - 3}" font-size="10" fill="#667085">{label}</text></svg>')
    return "".join(out)


STATUS_COLORS = {"out": "#7f1d1d", "critical": "#b91c1c", "low": "#d97706", "ok": "#2251FF", "over": "#7c3aed", "missing": "#cbd5e1"}


def stacked_status(weeks, series, order=("out", "critical", "low", "ok", "over", "missing"), w=720, h=200):
    """Stacked bars of depot-flavor counts by status, one bar per week."""
    left, right, top, bottom = 34, 10, 10, 28
    pw, ph = w - left - right, h - top - bottom
    n = len(weeks)
    tot = max([sum(series[k][i] for k in order) for i in range(n)] + [1])
    bw = pw / n
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Depot-flavor status by week">']
    for frac in (0, .5, 1):
        y = top + ph - frac * ph
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="10.5" fill="#667085" text-anchor="end">{round(frac * tot)}</text>')
    last_month = None
    for i, wk in enumerate(weeks):
        x = left + i * bw + bw * .12
        y = top + ph
        for k in order:
            v = series[k][i]
            if not v:
                continue
            hh = v / tot * ph
            y -= hh
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * .76:.1f}" height="{hh:.1f}" fill="{STATUS_COLORS[k]}">'
                       f'<title>Week of {wk:%d %b %Y}: {v} {k}</title></rect>')
        if wk.month != last_month:
            out.append(f'<text x="{x:.1f}" y="{h - 9}" font-size="10.5" fill="#667085">{wk:%b %y}</text>')
            last_month = wk.month
    return "".join(out) + "</svg>"


def money_bars(weeks, values, w=720, h=150, color="#7c3aed"):
    left, right, top, bottom = 50, 10, 10, 26
    pw, ph = w - left - right, h - top - bottom
    vmax = max(values + [1])
    n = len(weeks); bw = pw / n
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Weekly write-offs and discounts">']
    for frac in (0, .5, 1):
        y = top + ph - frac * ph
        lab = vmax * frac / 1e5
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="10.5" fill="#667085" text-anchor="end">₹{lab:.0f}L</text>')
    last_month = None
    for i, (wk, v) in enumerate(zip(weeks, values)):
        hh = v / vmax * ph
        x = left + i * bw + bw * .14
        out.append(f'<rect x="{x:.1f}" y="{top + ph - hh:.1f}" width="{bw * .72:.1f}" height="{hh:.1f}" rx="2" fill="{color}" opacity=".85">'
                   f'<title>Week of {wk:%d %b %Y}: ₹{v / 1e5:.1f} L</title></rect>')
        if wk.month != last_month:
            out.append(f'<text x="{x:.1f}" y="{h - 8}" font-size="10.5" fill="#667085">{wk:%b %y}</text>')
            last_month = wk.month
    return "".join(out) + "</svg>"


def demand_forecast(weeks, sold, ordered, p50, p80, w=720, h=230):
    """Bars = sold, line = ordered (true demand), shaded band = old forecast P50..P80."""
    left, right, top, bottom = 44, 10, 12, 28
    pw, ph = w - left - right, h - top - bottom
    vals = [v for v in ordered + sold + p80 if _ok(v)]
    ymax = max(vals + [1]) / 1e5
    step = _nice(ymax / 4); ymax = step * math.ceil(ymax / step)
    n = len(weeks); bw = pw / n
    X = lambda i: left + i * bw + bw / 2
    Y = lambda v: top + ph - v / 1e5 / ymax * ph
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Demand against forecast">']
    for i in range(0, int(ymax / step) + 1):
        y = top + ph - i * step / ymax * ph
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="10.5" fill="#667085" text-anchor="end">{i * step:g}</text>')
    up = [(X(i), Y(v)) for i, v in enumerate(p80) if _ok(v)]
    lo = [(X(i), Y(v)) for i, v in enumerate(p50) if _ok(v)]
    if up and lo:
        poly = up + lo[::-1]
        out.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in poly) + '" fill="#cbd5e1" opacity=".55"/>')
        out.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in lo) + '" fill="none" stroke="#64748b" stroke-width="1.2" stroke-dasharray="3 3"/>')
    for i, (wk, s) in enumerate(zip(weeks, sold)):
        hh = s / 1e5 / ymax * ph
        out.append(f'<rect x="{left + i * bw + bw * .2:.1f}" y="{top + ph - hh:.1f}" width="{bw * .6:.1f}" height="{hh:.1f}" rx="2" fill="{ACCENT}" opacity=".8">'
                   f'<title>Week of {wk:%d %b %Y}: sold {s / 1e5:.1f} L, ordered {ordered[i] / 1e5:.1f} L, P50 {(p50[i] or 0) / 1e5:.1f} L</title></rect>')
    pts = [(X(i), Y(v)) for i, v in enumerate(ordered)]
    out.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f'" fill="none" stroke="{DANGER}" stroke-width="2"/>')
    last_month = None
    for i, wk in enumerate(weeks):
        if wk.month != last_month:
            out.append(f'<text x="{left + i * bw:.1f}" y="{h - 9}" font-size="10.5" fill="#667085">{wk:%b %y}</text>')
            last_month = wk.month
    out.append('</svg>')
    return "".join(out)


def signal_gap(days, values, cutoff, oos=None, w=1100, h=230):
    """Daily quick-commerce sales: solid = what Marketing sees daily; dashed stops at the month-end Planning has."""
    left, right, top, bottom = 48, 10, 14, 28
    pw, ph = w - left - right, h - top - bottom
    vals = [v for v in values if _ok(v)]
    ymax = max(vals + [1]) / 1e3
    step = _nice(ymax / 4); ymax = step * math.ceil(ymax / step)
    n = len(days); xw = pw / max(n - 1, 1)
    X = lambda i: left + i * xw
    Y = lambda v: top + ph - v / 1e3 / ymax * ph
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Quick-commerce daily sales">']
    for i in range(0, int(ymax / step) + 1):
        y = top + ph - i * step / ymax * ph
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="10.5" fill="#667085" text-anchor="end">{i * step:g}k</text>')
    ci = max([i for i, d in enumerate(days) if d <= cutoff], default=None)
    if ci is not None and ci < n - 1:
        x0 = X(ci)
        out.append(f'<rect x="{x0:.1f}" y="{top}" width="{w - right - x0:.1f}" height="{ph}" fill="#fef3c7" opacity=".6"/>'
                   f'<text x="{w - right - 6:.1f}" y="{top + 14}" font-size="11" fill="#b45309" font-weight="700" text-anchor="end">Planning has not seen this yet</text>')
    pts = [(X(i), Y(v)) for i, v in enumerate(values) if _ok(v)]
    if pts:
        out.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f'" fill="none" stroke="{ACCENT}" stroke-width="2"/>')
        plan = [(X(i), Y(v)) for i, v in enumerate(values) if _ok(v) and days[i] <= cutoff]
        if len(plan) > 1:
            out.append('<polyline points="' + " ".join(f"{x:.1f},{y + 0:.1f}" for x, y in plan) + '" fill="none" stroke="#b45309" stroke-width="2.4" stroke-dasharray="6 4"/>')
    last_month = None
    for i, d in enumerate(days):
        if d.month != last_month and d.day <= 7:
            out.append(f'<text x="{X(i):.1f}" y="{h - 9}" font-size="10.5" fill="#667085">{d:%d %b}</text>')
            last_month = d.month
    for i, n_out in enumerate(oos or []):
        if n_out:
            out.append(f'<circle cx="{X(i):.1f}" cy="{top + ph + 7:.1f}" r="{2 + min(n_out, 9) * .35:.1f}" fill="{DANGER}"><title>{days[i]:%d %b}: {n_out} depot(s) out of stock</title></circle>')
    out.append('</svg>')
    return "".join(out)


def flow(src, reg, reg_ch, w=620, h=320):
    """Three-column flow: sources (share) -> regions (bottles received) -> channels (bottles sold)."""
    CH = {"C_GT": "General trade", "C_MT": "Modern trade", "C_QC": "Quick commerce"}
    top, gap, nw = 10, 10, 14
    total = sum(v for _, v in reg) or 1
    avail = h - top * 2 - gap * 3
    xs, xr, xc = 128, 300, 470
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Flow from plants to regions to channels">']
    # regions column
    ry, y = {}, top
    for r, v in reg:
        hh = v / total * avail
        ry[r] = [y, hh, y]                         # top, height, running offset for outgoing
        y += hh + gap
    # source column (single stacked bar split by share)
    sy = top
    full = sum(hh for _, hh, _ in ry.values())
    for name, share in src:
        hh = full * share
        if hh < 0.5:
            continue
        out.append(f'<rect x="{xs - nw}" y="{sy:.1f}" width="{nw}" height="{hh:.1f}" fill="{ACCENT if name.startswith("Plants") else "#7c3aed"}"/>'
                   f'<text x="{xs - nw - 6}" y="{sy + hh / 2 + 4:.1f}" font-size="13" text-anchor="end" fill="#0f172a">{name} · {share:.0%}</text>')
        sy += hh
    # links source -> regions (proportional)
    off = top
    for r, v in reg:
        y0, hh, _ = ry[r]
        out.append(f'<path d="M{xs},{off:.1f} C{(xs + xr) / 2},{off:.1f} {(xs + xr) / 2},{y0:.1f} {xr},{y0:.1f} '
                   f'L{xr},{y0 + hh:.1f} C{(xs + xr) / 2},{y0 + hh:.1f} {(xs + xr) / 2},{off + hh:.1f} {xs},{off + hh:.1f} Z" '
                   f'fill="{ACCENT}" opacity=".18"/>')
        off += hh
    # channels column
    ch_tot = {c: sum(v for rr, cc, v in reg_ch if cc == c) for c in CH}
    sold_tot = sum(ch_tot.values()) or 1
    cy, y = {}, top
    for c in CH:
        hh = ch_tot[c] / sold_tot * (avail + gap)
        cy[c] = [y, hh, y]
        y += hh + gap
    for r, v in reg:
        y0, hh, _ = ry[r]
        rsold = sum(vv for rr, cc, vv in reg_ch if rr == r) or 1
        o = y0
        for c in CH:
            vv = next(x for rr, cc, x in reg_ch if rr == r and cc == c)
            hr = vv / rsold * hh
            hc = vv / sold_tot * (avail + gap)
            c0 = cy[c][2]
            out.append(f'<path d="M{xr + nw},{o:.1f} C{(xr + xc) / 2},{o:.1f} {(xr + xc) / 2},{c0:.1f} {xc},{c0:.1f} '
                       f'L{xc},{c0 + hc:.1f} C{(xr + xc) / 2},{c0 + hc:.1f} {(xr + xc) / 2},{o + hr:.1f} {xr + nw},{o + hr:.1f} Z" '
                       f'fill="#64748b" opacity=".16"><title>{r} → {CH[c]}: {vv / 1e5:.1f} L sold</title></path>')
            o += hr
            cy[c][2] += hc
    for r, v in reg:
        y0, hh, _ = ry[r]
        out.append(f'<rect x="{xr}" y="{y0:.1f}" width="{nw}" height="{hh:.1f}" fill="#051C2C"/>'
                   f'<text x="{xr + nw + 6}" y="{y0 + hh / 2 + 4:.1f}" font-size="13" fill="#0f172a" font-weight="700">{r}</text>'
                   f'<text x="{xr + nw + 6}" y="{y0 + hh / 2 + 19:.1f}" font-size="12" fill="#667085">{v / 1e5:.0f} L in</text>')
    for c in CH:
        y0, hh, _ = cy[c]
        out.append(f'<rect x="{xc}" y="{y0:.1f}" width="{nw}" height="{hh:.1f}" fill="#64748b"/>'
                   f'<text x="{xc + nw + 6}" y="{y0 + hh / 2 + 4:.1f}" font-size="13" fill="#0f172a" font-weight="700">{CH[c]}</text>'
                   f'<text x="{xc + nw + 6}" y="{y0 + hh / 2 + 19:.1f}" font-size="12" fill="#667085">{ch_tot[c] / 1e5:.0f} L sold</text>')
    return "".join(out) + "</svg>"


def stacked_weeks(weeks, series, colors, closed=None, unit=1e5, w=720, h=210, fmt="{:g}"):
    """Generic stacked weekly bars; optional red shading for weeks with the highway closed."""
    left, right, top, bottom = 48, 10, 12, 28
    pw, ph = w - left - right, h - top - bottom
    keys = list(series)
    n = len(weeks); bw = pw / n
    tot = [sum(series[k][i] for k in keys) for i in range(n)]
    ymax = max(tot + [1]) / unit
    step = _nice(ymax / 4); ymax = step * math.ceil(ymax / step)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    for i, c in enumerate(closed or []):
        if c:
            out.append(f'<rect x="{left + i * bw:.1f}" y="{top}" width="{bw:.1f}" height="{ph}" fill="#fee2e2"/>')
    for i in range(0, int(ymax / step) + 1):
        y = top + ph - i * step / ymax * ph
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="10.5" fill="#667085" text-anchor="end">{fmt.format(i * step)}</text>')
    last_month = None
    for i, wk in enumerate(weeks):
        x = left + i * bw + bw * .14
        y = top + ph
        for k in keys:
            v = series[k][i] / unit
            if v <= 0:
                continue
            hh = v / ymax * ph
            y -= hh
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * .72:.1f}" height="{hh:.1f}" fill="{colors[k]}">'
                       f'<title>Week of {wk:%d %b %Y} · {k}: {fmt.format(round(v, 1))}</title></rect>')
        if wk.month != last_month:
            out.append(f'<text x="{x:.1f}" y="{h - 9}" font-size="10.5" fill="#667085">{wk:%b %y}</text>')
            last_month = wk.month
    return "".join(out) + "</svg>"


def _nice(x):
    if x <= 0:
        return 1
    p = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 2.5, 5, 10):
        if m * p >= x:
            return m * p
    return 10 * p


def network(net, w=620, h=222):
    """Simplified network: suppliers -> plants -> regions -> channels, coloured by this week's state."""
    BAD, WARN, OK, IDLE = "#fee2e2", "#fef3c7", "#EAF0FF", "#f1f3f8"
    BADS, WARNS, OKS, IDLES = DANGER, "#b45309", ACCENT, "#ccd2e0"
    nodes, edges = {}, []

    def node(k, x, y, label, sub, fill, stroke, wd=118):
        nodes[k] = (x, y, wd)
        return (f'<g><rect x="{x}" y="{y}" width="{wd}" height="34" rx="7" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
                f'<text x="{x + 8}" y="{y + 14}" font-size="11" font-weight="700" fill="#0f172a">{label}</text>'
                f'<text x="{x + 8}" y="{y + 27}" font-size="10" fill="#4a5568">{sub}</text></g>')

    pf = net["pf_cover"]
    road = net["road_closed"]
    parts = []
    parts.append(node("pf", 4, 10, "Passionfruit coop", "road CLOSED" if road else "road open",
                      BAD if road else OK, BADS if road else OKS, wd=150))
    parts.append(node("df", 4, 58, "Dragonfruit", "60% domestic · 40% import", OK, OKS, wd=150))
    parts.append(node("mpb", 4, 106, "Mango · peach · basil", "contract suppliers", OK, OKS, wd=150))
    parts.append(node("gu", 4, 154, "Guava (2 suppliers)", "regional", OK, OKS, wd=150))
    pst = BAD if pf < 7 else (WARN if pf < 14 else OK)
    pss = BADS if pf < 7 else (WARNS if pf < 14 else OKS)
    parts.append(node("pl", 196, 58, "Plants 1 + 2", f"passionfruit {pf:.0f} days", pst, pss, wd=132))
    parts.append(node("cp", 196, 130, "Co-packer", "running" if net["cp_on"] else "idle",
                      OK if net["cp_on"] else IDLE, OKS if net["cp_on"] else IDLES, wd=132))
    for i, r in enumerate(["North", "South", "East", "West"]):
        so = net["region_out"][r]
        cov = net["region_cover"][r]
        f, s = (BAD, BADS) if so else (OK, OKS)
        sub = f"{cov:.0f} d cover" + (f" · {so} out" if so else "")
        parts.append(node(r, 372, 10 + i * 48, f"{r} depots", sub, f, s, wd=124))
    for i, (c, nm) in enumerate([("gt", "General trade"), ("mt", "Modern trade"), ("qc", "Quick commerce")]):
        parts.append(node(c, 518, 34 + i * 52, nm, ("55%" if c == "gt" else ("25%" if c == "mt" else "20%")) + " of volume", IDLE, IDLES, wd=100))

    def link(a, b, color="#ccd2e0", dash=""):
        ax, ay, aw = nodes[a]; bx, by, _ = nodes[b]
        x1, y1, x2, y2 = ax + aw, ay + 17, bx, by + 17
        mx = (x1 + x2) / 2
        edges.append(f'<path d="M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}" fill="none" stroke="{color}" '
                     f'stroke-width="1.4" {"stroke-dasharray=" + chr(34) + dash + chr(34) if dash else ""}/>')
    link("pf", "pl", DANGER if road else "#ccd2e0", "4 3" if road else "")
    for s in ("df", "mpb", "gu"):
        link(s, "pl")
    for r in ("North", "South", "East", "West"):
        link("pl", r); link("cp", r)
        for c in ("gt", "mt", "qc"):
            link(r, c)
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Network state this week">'
            + "".join(edges) + "".join(parts) + "</svg>")


# ============================================================ decision-engine charts (prompt 1)
NAVY = "#051C2C"
CYAN = "#00A9F4"


def _yaxis(out, left, right, w, top, ph, ymax, step, fmt="{:g}"):
    for i in range(0, int(round(ymax / step)) + 1):
        y = top + ph - i * step / ymax * ph
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="10.5" fill="#667085" text-anchor="end">{fmt.format(i * step)}</text>')


def _days_axis(out, days, X, h):
    for i, d in enumerate(days):
        if d.weekday() == 0 and (i == 0 or (d.day <= 7) or i % 14 == 0):
            out.append(f'<text x="{X(i):.1f}" y="{h - 9}" font-size="10.5" fill="#667085">{d:%d %b}</text>')


def balance_chart(days, closing, closing_conf, safety, rc, rp, extra, closures, unsafe=None, unc=None, w=760, h=250):
    """Daily pulp balance in tonnes: stock with standing orders (solid; cannot go below zero), confirmed orders only
    (grey dashed), the shortfall if production ran to plan (red dashed, below zero), safety buffer, receipts as
    bars (confirmed navy, planned cyan, approved extra amber); closure days shaded."""
    unc = list(unc) if unc is not None else list(closing)
    left, right, top, bottom = 44, 12, 16, 30
    pw, ph = w - left - right, h - top - bottom
    t = lambda v: v / 1e3
    lo = min(0.0, min(t(v) for v in list(closing) + list(closing_conf) + unc))
    hi = max([t(v) for v in list(closing) + list(closing_conf)] + [t(safety) * 1.5, 1])
    step = _nice((hi - lo) / 4)
    lo = step * math.floor(lo / step); hi = step * math.ceil(hi / step)
    n = len(days); xw = pw / max(n, 1)
    X = lambda i: left + (i + 0.5) * xw
    Y = lambda v: top + ph - (t(v) - lo) / (hi - lo) * ph
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Daily pulp balance">']
    for i, d in enumerate(days):
        if any(c["start"] <= d <= c["end"] for c in closures):
            out.append(f'<rect x="{left + i * xw:.1f}" y="{top}" width="{xw + .3:.1f}" height="{ph}" fill="#fee2e2"/>')
    for i in range(0, int(round((hi - lo) / step)) + 1):
        v = lo + i * step
        y = top + ph - (v - lo) / (hi - lo) * ph
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>'
                   f'<text x="{left - 6}" y="{y + 4:.1f}" font-size="10.5" fill="#667085" text-anchor="end">{v:g}t</text>')
    y0 = Y(0)
    rmax = max([a + b + c for a, b, c in zip(rc, rp, extra)] + [1])
    bscale = ph * 0.35 / rmax
    for i in range(n):
        yb = top + ph
        for v, col in ((rc[i], NAVY), (rp[i], CYAN), (extra[i], "#d97706")):
            if v > 0:
                hb = v * bscale
                out.append(f'<rect x="{left + i * xw + xw * .18:.1f}" y="{yb - hb:.1f}" width="{xw * .64:.1f}" height="{hb:.1f}" '
                           f'fill="{col}" opacity=".55"><title>{days[i]:%d %b}: {v:,.0f} kg</title></rect>')
                yb -= hb
    ys = Y(safety)
    out.append(f'<line x1="{left}" x2="{w - right}" y1="{ys:.1f}" y2="{ys:.1f}" stroke="#b45309" stroke-dasharray="3 3"/>'
               f'<text x="{w - right - 2}" y="{ys - 4:.1f}" font-size="10" fill="#b45309" text-anchor="end">safety buffer</text>')
    if lo < 0:
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{y0:.1f}" y2="{y0:.1f}" stroke="{DANGER}" stroke-width="1"/>')
    short = [min(v, 0.0) for v in unc]
    series = [(closing_conf, "#64748b", "5 4", 1.8), (closing, ACCENT, "", 2.4)]
    if any(v < 0 for v in short):
        series.insert(0, (short, DANGER, "4 3", 1.6))
    for vals, col, dash, wd in series:
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="{wd}" stroke-dasharray="{dash}" stroke-linejoin="round"/>')
    if any(v < 0 for v in short):
        j = min(range(len(short)), key=lambda i: short[i])
        out.append(f'<text x="{X(j):.1f}" y="{Y(short[j]) + 14:.1f}" font-size="10.5" fill="{DANGER}" text-anchor="middle">'
                   f'pulp missing if production ran to plan: {-short[j] / 1e3:,.0f}t</text>')
    if unsafe is not None and unsafe in days:
        i = days.index(unsafe)
        out.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{top}" y2="{top + ph}" stroke="{DANGER}" stroke-width="1.5"/>'
                   f'<text x="{X(i) + 4:.1f}" y="{top + 11}" font-size="10.5" fill="{DANGER}" font-weight="700">first unsafe day {unsafe:%d %b}</text>')
    _days_axis(out, days, X, h)
    out.append("</svg>")
    return "".join(out)


def detector_chart(rows, thr, detected=None, marks=(), w=1100, h=240):
    """Daily quick-commerce sales (bars) with the lagged baseline, and the smoothed ratio on a second band.
    Censored (stock-out) days hatched grey; alert days outlined."""
    left, right, top, bottom = 48, 12, 14, 30
    pw, ph = w - left - right, h - top - bottom
    ph1 = ph * 0.62; ph2 = ph * 0.30; gap = ph * 0.08
    n = len(rows); xw = pw / max(n, 1)
    X = lambda i: left + (i + .5) * xw
    xs = [r["x"] for r in rows if _ok(r["x"])]
    ymax = max(xs + [1]) / 1e3
    step = _nice(ymax / 3); ymax = step * math.ceil(ymax / step)
    Y1 = lambda v: top + ph1 - v / 1e3 / ymax * ph1
    rs = [r["ewma"] for r in rows if _ok(r.get("ewma"))] + [thr]
    rmax = max(rs) * 1.1
    Y2 = lambda v: top + ph1 + gap + ph2 - v / rmax * ph2
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Quick-commerce detector">']
    _yaxis(out, left, right, w, top, ph1, ymax, step, "{:g}k")
    for i, r in enumerate(rows):
        x0 = left + i * xw
        if r["censored"]:
            out.append(f'<rect x="{x0:.1f}" y="{top}" width="{xw:.1f}" height="{ph}" fill="#e2e8f0"><title>{r["date"]:%d %b}: stock-outs, demand unobservable</title></rect>')
        if _ok(r["x"]):
            hb = r["x"] / 1e3 / ymax * ph1
            col = DANGER if r["alert"] else ACCENT
            out.append(f'<rect x="{x0 + xw * .15:.1f}" y="{top + ph1 - hb:.1f}" width="{xw * .7:.1f}" height="{hb:.1f}" fill="{col}" opacity=".75">'
                       f'<title>{r["date"]:%d %b}: {r["x"]:,.0f} bottles</title></rect>')
    pts = [(X(i), Y1(r["base"])) for i, r in enumerate(rows) if _ok(r.get("base"))]
    if len(pts) > 1:
        out.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f'" fill="none" stroke="{NAVY}" stroke-width="1.8" stroke-dasharray="5 3"/>')
    yt = Y2(thr)
    out.append(f'<line x1="{left}" x2="{w - right}" y1="{Y2(1):.1f}" y2="{Y2(1):.1f}" stroke="{GRID}"/>'
               f'<line x1="{left}" x2="{w - right}" y1="{yt:.1f}" y2="{yt:.1f}" stroke="#b45309" stroke-dasharray="3 3"/>'
               f'<text x="{left - 6}" y="{yt + 4:.1f}" font-size="10" fill="#b45309" text-anchor="end">{thr:g}x</text>'
               f'<text x="{left - 6}" y="{Y2(1) + 4:.1f}" font-size="10" fill="#667085" text-anchor="end">1x</text>')
    pr = [(X(i), Y2(r["ewma"])) for i, r in enumerate(rows) if _ok(r.get("ewma"))]
    if len(pr) > 1:
        out.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pr) + f'" fill="none" stroke="{ACCENT}" stroke-width="2"/>')
    for d, label, col in marks:
        for i, r in enumerate(rows):
            if r["date"] == d:
                out.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{top}" y2="{top + ph}" stroke="{col}" stroke-width="1.6"/>'
                           f'<text x="{X(i) + 4:.1f}" y="{top + 11}" font-size="10.5" fill="{col}" font-weight="700">{label}</text>')
    days = [r["date"] for r in rows]
    _days_axis(out, days, X, h)
    out.append("</svg>")
    return "".join(out)


def fan_chart(hist_weeks, hist, weeks, p10, p50, p80, p90, w=760, h=230):
    """Weekly history (bars) and the forecast fan: P10-P90 light, P50 line."""
    left, right, top, bottom = 48, 12, 14, 30
    pw, ph = w - left - right, h - top - bottom
    allw = list(hist_weeks) + list(weeks)
    n = len(allw); xw = pw / max(n, 1)
    X = lambda i: left + (i + .5) * xw
    ymax = max(list(hist) + list(p90) + [1]) / 1e5
    step = _nice(ymax / 4); ymax = step * math.ceil(ymax / step)
    Y = lambda v: top + ph - v / 1e5 / ymax * ph
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Forecast fan">']
    _yaxis(out, left, right, w, top, ph, ymax, step, "{:g}L")
    for i, v in enumerate(hist):
        hb = v / 1e5 / ymax * ph
        out.append(f'<rect x="{left + i * xw + xw * .15:.1f}" y="{top + ph - hb:.1f}" width="{xw * .7:.1f}" height="{hb:.1f}" fill="{NAVY}" opacity=".55"/>')
    k = len(hist)
    up = [(X(k + i), Y(v)) for i, v in enumerate(p90)]
    dn = [(X(k + i), Y(v)) for i, v in enumerate(p10)][::-1]
    out.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in up + dn) + f'" fill="{CYAN}" opacity=".18"/>')
    up = [(X(k + i), Y(v)) for i, v in enumerate(p80)]
    out.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in up) + f'" fill="none" stroke="{CYAN}" stroke-width="1.5" stroke-dasharray="4 3"/>')
    pts = [(X(k + i), Y(v)) for i, v in enumerate(p50)]
    out.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f'" fill="none" stroke="{ACCENT}" stroke-width="2.4"/>')
    last = None
    for i, wk in enumerate(allw):
        if wk.month != last:
            out.append(f'<text x="{X(i) - xw / 2:.1f}" y="{h - 9}" font-size="10.5" fill="#667085">{wk:%b}</text>')
            last = wk.month
    x0 = left + k * xw
    out.append(f'<line x1="{x0:.1f}" x2="{x0:.1f}" y1="{top}" y2="{top + ph}" stroke="#667085" stroke-dasharray="2 3"/>'
               f'<text x="{x0 + 4:.1f}" y="{top + 10}" font-size="10" fill="#667085">forecast</text></svg>')
    return "".join(out)


# ============================================================ inventory-module charts (prompt 2)
def paired_bars(labels, before, after_loss, after_tr, w=760, h=240, unit=1e7, fmt="{:g}"):
    """Per month: 'before' bar (loss) beside an 'after' bar stacked as remaining loss + transport. Values in crore."""
    left, right, top, bottom = 44, 10, 14, 30
    pw, ph = w - left - right, h - top - bottom
    vals = [b / unit for b in before] + [(a + t) / unit for a, t in zip(after_loss, after_tr)]
    ymax = max(vals + [0.01])
    step = _nice(ymax / 4); ymax = step * math.ceil(ymax / step)
    n = max(len(labels), 1); gw = pw / n; bw = gw * 0.34
    Y = lambda v: top + ph - v / ymax * ph
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Loss before and after, by month">']
    _yaxis(out, left, right, w, top, ph, ymax, step, fmt)
    for i, lab in enumerate(labels):
        x0 = left + i * gw + gw * 0.12
        b, a, t = before[i] / unit, after_loss[i] / unit, after_tr[i] / unit
        out.append(f'<rect x="{x0:.1f}" y="{Y(b):.1f}" width="{bw:.1f}" height="{top + ph - Y(b):.1f}" fill="{NAVY}" opacity=".75">'
                   f'<title>{lab}: before ₹{b:.2f} Cr</title></rect>')
        x1 = x0 + bw + gw * 0.06
        out.append(f'<rect x="{x1:.1f}" y="{Y(a):.1f}" width="{bw:.1f}" height="{top + ph - Y(a):.1f}" fill="{ACCENT}">'
                   f'<title>{lab}: remaining loss ₹{a:.2f} Cr</title></rect>')
        if t > 0:
            out.append(f'<rect x="{x1:.1f}" y="{Y(a + t):.1f}" width="{bw:.1f}" height="{Y(a) - Y(a + t):.1f}" fill="#d97706">'
                       f'<title>{lab}: transport ₹{t:.3f} Cr</title></rect>')
        if n <= 14 or i % 3 == 0:
            out.append(f'<text x="{x0:.1f}" y="{h - 10}" font-size="10.5" fill="#667085">{lab}</text>')
    out.append("</svg>")
    return "".join(out)


def lines(xs, series, colors, w=760, h=230, unit=1.0, fmt="{:g}", zero=False, hlines=(), dashed=(), shade=None, xfmt="%d %b"):
    """Generic multi-line chart. series: {name: [values]} (None for gaps). hlines: [(value, label, colour)]."""
    left, right, top, bottom = 48, 12, 14, 30
    pw, ph = w - left - right, h - top - bottom
    allv = [v / unit for s in series.values() for v in s if _ok(v)] + [hv / unit for hv, _, _ in hlines]
    lo = min(allv + [0]) if zero or not allv else min(allv)
    hi = max(allv + [lo + 1e-9])
    lo = min(lo, 0) if zero else lo
    step = _nice((hi - lo) / 4 or 1); hi = step * math.ceil(hi / step); lo = step * math.floor(lo / step)
    n = len(xs); X = lambda i: left + (i / max(n - 1, 1)) * pw
    Y = lambda v: top + ph - (v - lo) / ((hi - lo) or 1) * ph
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Line chart">']
    if shade:
        for i, s in enumerate(shade):
            if s:
                out.append(f'<rect x="{X(i) - pw / max(n - 1, 1) / 2:.1f}" y="{top}" width="{pw / max(n - 1, 1):.1f}" height="{ph}" fill="#fee2e2"/>')
    for i in range(0, int(round((hi - lo) / step)) + 1):
        v = lo + i * step
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{GRID}"/>'
                   f'<text x="{left - 6}" y="{Y(v) + 4:.1f}" font-size="10.5" fill="#667085" text-anchor="end">{fmt.format(v)}</text>')
    for hv, lab, col in hlines:
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{Y(hv / unit):.1f}" y2="{Y(hv / unit):.1f}" stroke="{col}" stroke-dasharray="4 3"/>'
                   f'<text x="{w - right - 2}" y="{Y(hv / unit) - 4:.1f}" font-size="10" fill="{col}" text-anchor="end">{lab}</text>')
    for name, vals in series.items():
        segs, cur = [], []
        for i, v in enumerate(vals):
            if _ok(v):
                cur.append(f"{X(i):.1f},{Y(v / unit):.1f}")
            elif cur:
                segs.append(cur); cur = []
        if cur:
            segs.append(cur)
        for sg in segs:
            out.append(f'<polyline points="{" ".join(sg)}" fill="none" stroke="{colors.get(name, ACCENT)}" stroke-width="2.2" '
                       f'stroke-dasharray="{"5 4" if name in dashed else ""}" stroke-linejoin="round"><title>{name}</title></polyline>')
    last = None
    for i, x in enumerate(xs):
        lab = x.strftime("%b %y") if xfmt == "month" else x.strftime(xfmt)
        key = (x.year, x.month) if xfmt == "month" else None
        if (xfmt == "month" and key != last) or (xfmt != "month" and (i % max(1, n // 8) == 0)):
            out.append(f'<text x="{X(i):.1f}" y="{h - 9}" font-size="10.5" fill="#667085">{lab}</text>')
            last = key
    out.append("</svg>")
    return "".join(out)
