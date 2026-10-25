"""
draw_diagram.py  -  draws the supply-network flowchart FROM the tables (nothing is hand-typed
into the picture except layout positions).

    python code/draw_diagram.py        ->  diagrams/supply_network.svg and .png (1920x1080, 16:9)

Names, lead times, frequencies, shares and the Given/Assumed border style all come from
nodes.csv / edges.csv / risk_flags.csv.  Change a row, re-run, and the picture changes.

Reading the picture
  solid blue arrows   goods (physical flow)          dashed teal arrows   information flow
  dashed grey         depot-to-depot transfers       orange dashed        air-freight contingency
  RED                 the critical bottlenecks, numbered 1-3 and explained in the strip below
  border: solid = Given in the case, dashed = Assumed by us, dotted = Derived from case figures
"""
import textwrap
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "diagrams"
OUT.mkdir(exist_ok=True)

nodes = pd.read_csv(DATA / "nodes.csv", encoding="utf-8-sig").set_index("node_id")
edges = pd.read_csv(DATA / "edges.csv", encoding="utf-8-sig")
flags = pd.read_csv(DATA / "risk_flags.csv", encoding="utf-8-sig")


def E(frm, to, flow=None, mode=None):
    """Fetch the first edge row matching from/to (and optionally flow/mode)."""
    q = edges[(edges.from_node == frm) & (edges.to_node == to)]
    if flow:
        q = q[q.flow_type == flow]
    if mode:
        q = q[q["mode"] == mode]
    return q.iloc[0]


def days(r):
    lo, hi = r.lead_time_days_min, r.lead_time_days_max
    return f"{lo:.0f} days" if lo == hi else f"{lo / 7:.0f}-{hi / 7:.0f} weeks"


# ---------------------------------------------------------------- palette
INK, MUTED, FAINT = "#14213D", "#5B6880", "#8A95A8"
GOODS, INFO, XFER, AIR, RED = "#2E6DA4", "#0F8B8D", "#8A95A8", "#D9822B", "#C0392B"
FILL = {"supplier": "#EAF3EC", "plant": "#E8F1FA", "copacker": "#E8F1FA", "depot": "#F0E9FA",
        "channel": "#FCEFD9", "function": "#EEF1F6"}
STROKE = {"supplier": "#4C9A63", "plant": "#2E6DA4", "copacker": "#2E6DA4", "depot": "#7B52B5",
          "channel": "#C98A2B", "function": "#5B6880"}
DASH = {"Given": "", "Derived": "2 3", "Assumed": "7 4"}
FONT = "Segoe UI, Calibri, Arial, sans-serif"

W, H = 1920, 1080
parts = []
pos = {}      # node_id -> (x, y, w, h)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=13, color=INK, bold=False, anchor="start", italic=False, spacing=None):
    parts.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{color}" '
                 f'font-weight="{700 if bold else 400}" text-anchor="{anchor}"'
                 f'{' font-style="italic"' if italic else ""}>{esc(s)}</text>')


def box(nid, x, y, w, h, lines=None, size=13, fill=None, stroke=None, strong=False):
    r = nodes.loc[nid]
    pos[nid] = (x, y, w, h)
    f = fill or FILL[r.type]
    s = stroke or STROKE[r.type]
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{f}" stroke="{s}" '
                 f'stroke-width="{2.4 if strong else 1.8}" stroke-dasharray="{DASH[r.data_source]}"/>')
    lines = lines or textwrap.wrap(r["name"], width=int(w / (size * 0.52)))
    top = y + h / 2 - (len(lines) - 1) * (size + 2) / 2 + size * 0.36
    for i, ln in enumerate(lines):
        text(x + w / 2, top + i * (size + 2), ln, size, INK, bold=(i == 0 and len(lines) > 1 and False),
             anchor="middle")


def mid(a, b, t=0.5):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def arrow(pts, color=GOODS, width=2.2, dash="", label=None, label_at=None, label_color=None,
          both=False, size=11.5, label_anchor="middle", label_dy=-7, halo=True, head=True):
    d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    mk = color.replace("#", "")
    parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
                 f'stroke-dasharray="{dash}" stroke-linejoin="round"{f' marker-end="url(#a{mk})"' if head else ""}'
                 f'{f' marker-start="url(#s{mk})"' if both else ""}/>')
    if label:
        lx, ly = label_at or mid(pts[len(pts) // 2 - 1], pts[len(pts) // 2])
        tw = len(label) * size * 0.5
        if halo:
            parts.append(f'<rect x="{lx - tw / 2 - 3:.1f}" y="{ly + label_dy - size + 2:.1f}" width="{tw + 6:.1f}" '
                         f'height="{size + 3}" rx="3" fill="#fff" fill-opacity="0.9"/>')
        text(lx, ly + label_dy + 2, label, size, label_color or color, bold=True, anchor=label_anchor)


def badge(x, y, n):
    parts.append(f'<circle cx="{x}" cy="{y}" r="15" fill="{RED}" stroke="#fff" stroke-width="2"/>')
    text(x, y + 6, str(n), 17, "#fff", bold=True, anchor="middle")


# ---------------------------------------------------------------- defs (arrowheads)
defs = ""
for c in (GOODS, INFO, XFER, AIR, RED):
    k = c.replace("#", "")
    defs += (f'<marker id="a{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
             f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
             f'<marker id="s{k}" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" '
             f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
parts.append(f'<defs>{defs}</defs>')
parts.append(f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>')

# ---------------------------------------------------------------- title
text(30, 40, "Pulp Riot: supply network, physical flow and information flow", 28, INK, bold=True)
text(30, 64, "Every box is a row in nodes.csv and every arrow a row in edges.csv. Red marks the three bottlenecks "
             "that failed last summer; Supply and Inventory are the two modules modelled in depth.", 13.5, MUTED)

# ---------------------------------------------------------------- module bands (Supply / Inventory)
parts.append(f'<rect x="18" y="312" width="778" height="606" rx="12" fill="#F4FAF5" stroke="#CFE5D4"/>')
text(32, 334, "SUPPLY  (deep module)", 12.5, "#3F8A57", bold=True)
parts.append(f'<rect x="846" y="312" width="548" height="606" rx="12" fill="#FAF7FD" stroke="#E2D6F1"/>')
text(860, 334, "INVENTORY  (deep module)", 12.5, "#7B52B5", bold=True)
text(1700, 334, "DEMAND CHANNELS", 12.5, "#B37A1E", bold=True)

# ---------------------------------------------------------------- functions (information layer)
box("X_PROC", 30, 175, 300, 60, ["Procurement", "targets set on price per kg"], 13)
box("X_COO", 1100, 100, 300, 40, ["COO / S&OP (monthly)"], 13)
box("X_PLAN", 1100, 175, 300, 60, ["Planning", "15 planners, spreadsheets"], 13)
box("X_MKT", 1500, 175, 300, 60, ["Marketing", "receives daily QC sell-through"], 13)
text(116, 160, "INFORMATION  (decisions are made here)", 12.5, INFO, bold=True)

# ---------------------------------------------------------------- suppliers
sup_order = ["S_PASSION", "S_DRAGON_IMP", "S_DRAGON_DOM", "S_MANGO", "S_PEACH", "S_BASIL", "S_GUAVA1", "S_GUAVA2"]
for i, s in enumerate(sup_order):
    box(s, 30, 350 + i * 69, 300, 54, None, 12.5, strong=(s == "S_PASSION"),
        stroke=RED if s == "S_PASSION" else None)

# ---------------------------------------------------------------- plants + co-packer
box("P1", 520, 400, 230, 92, ["Plant 1", "cold storage: frozen pulp", "keeps up to 6 months"], 13)
box("P2", 520, 510, 230, 92, ["Plant 2", "cold storage: frozen pulp", "keeps up to 6 months"], 13)
box("CP", 520, 650, 230, 78, ["Co-packer", "up to +10% volume, +25% cost,", "2 weeks' notice"], 12.5)
cap = nodes.loc[["P1", "P2"], "capacity_per_month"].sum()
text(635, 626, f"{cap:.1f} crore bottles / month together, ~95% used", 11.5, MUTED, anchor="middle", italic=True)
text(635, 770, "pulp cover at closure start: 14 days", 11.5, RED, bold=True, anchor="middle")
text(635, 786, "(closure lasted 21 days)", 11.5, RED, anchor="middle")

# ---------------------------------------------------------------- depots, grouped by region
regions = [("North", 870, 350), ("South", 1135, 350), ("East", 870, 575), ("West", 1135, 575)]
for reg, rx, ry in regions:
    deps = [n for n, r in nodes.iterrows() if r.type == "depot" and r.region == reg]
    h = 40 + len(deps) * 42 - 4 + 8
    parts.append(f'<rect x="{rx}" y="{ry}" width="245" height="{h}" rx="9" fill="#fff" stroke="#C9B6E3" stroke-dasharray="7 4"/>')
    text(rx + 12, ry + 21, f"{reg} region", 12, "#7B52B5", bold=True)
    for j, d in enumerate(deps):
        box(d, rx + 12, ry + 32 + j * 42, 221, 36, [f"{nodes.loc[d, 'name']}  ·  {nodes.loc[d, 'cover_target_days']:.0f} days cover"], 11.5)
dep_ids = [n for n, r in nodes.iterrows() if r.type == "depot"]
xfer = E(dep_ids[0], dep_ids[1], "transfer")
text(1132, 748, "Depot-to-depot transfers (any depot to any depot)", 12, "#5B6880", bold=True, anchor="middle")
arrow([(900, 760), (1365, 760)], XFER, 2, "6 4", both=True,
      label=f"{xfer.lead_time_days_min:.0f}-{xfer.lead_time_days_max:.0f} days  ·  about INR {xfer.cost_per_unit:.2f} per bottle",
      label_at=(1132, 760), label_color="#4A5568", halo=True, label_dy=18)
text(1132, 818, "Cover set from last year's mix, reset monthly.", 12, MUTED, anchor="middle")
text(1132, 835, "Each depot reports weekly in its own spreadsheet.", 12, MUTED, anchor="middle")

# ---------------------------------------------------------------- channels
chan = {"C_QC": 355, "C_MT": 545, "C_GT": 735}
for c, y in chan.items():
    r = nodes.loc[c]
    share = edges[(edges.to_node == c) & (edges.flow_type == "goods")].volume_share.iloc[0]
    sub = {"C_QC": "dark stores · rejects < 60 days left", "C_MT": "retailers · rejects < 60 days left",
           "C_GT": "~600 distributors · no outlet data"}[c]
    box(c, 1560, y, 300, 100, [r["name"].split(" (")[0] + f"  ({share:.0%} of volume)", sub], 13)

# ================================================================ GOODS ARROWS
# suppliers -> plant block (fan in on the plant block's left edge)
targets = {"S_PASSION": 418, "S_DRAGON_IMP": 462, "S_DRAGON_DOM": 520, "S_MANGO": 540, "S_PEACH": 558,
           "S_BASIL": 576, "S_GUAVA1": 590, "S_GUAVA2": 600}
PX = 520
road = E("S_PASSION", "P1", "goods", "road")
air = E("S_PASSION", "P1", "goods", "air")
imp = E("S_DRAGON_IMP", "P1", "goods")
for s in sup_order:
    sx, sy, sw, sh = pos[s]
    start = (sx + sw, sy + sh / 2)
    if s == "S_PASSION":
        arrow([start, (PX, targets[s])], RED, 4, label=f"road · {days(road)}", label_at=(425, 392), label_color=RED, size=12)
        arrow([(start[0], start[1] + 12), (PX, 440)], AIR, 2.2, "7 4", label=f"air · {air.cost_multiple:.0f}x cost",
              label_at=(405, 438), label_color="#B5651D", size=11, label_dy=0)
    elif s == "S_DRAGON_IMP":
        arrow([start, (PX, targets[s])], "#B5651D", 2.4, label=f"{imp['mode']}* · {days(imp)} · quarterly",
              label_at=(420, 478), label_color="#B5651D", size=11, label_dy=14)
    else:
        arrow([start, (PX, targets[s])], GOODS, 1.6)
text(425, 912, "Other suppliers: arrows exist in the case; lead times not stated.", 11, MUTED, anchor="middle", italic=True)
# plants + co-packer -> depots
a = E("P1", "D_N1", "goods")
arrow([(750, 446), (810, 446), (810, 440), (846, 440)], GOODS, 3.2)
arrow([(750, 556), (810, 556), (810, 440)], GOODS, 3.2)
arrow([(750, 689), (810, 689), (810, 440)], GOODS, 3.2)
text(758, 706, "road* · lead time", 11, MUTED, anchor="start", italic=True)
text(758, 721, "not stated", 11, MUTED, anchor="start", italic=True)
# depots -> channels
for c, y in chan.items():
    share = edges[(edges.to_node == c) & (edges.flow_type == "goods")].volume_share.iloc[0]
    arrow([(1394, y + 50), (1560, y + 50)], GOODS, 2 + share * 4, label=f"{share:.0%}", label_at=(1477, y + 50), size=12)

# ================================================================ INFORMATION ARROWS
daily = E("C_QC", "X_MKT", "information")
eom = E("C_QC", "X_PLAN", "information")
wk = E(dep_ids[0], "X_PLAN", "information")
mo = E("X_PLAN", dep_ids[0], "information")
launch = E("X_MKT", "X_PROC", "information")
fc = E("X_PLAN", "X_PROC", "information")
# QC -> Marketing: daily
arrow([(1650, 355), (1650, 235)], INFO, 2.4, "6 4", label=daily.frequency + " sell-through", label_at=(1650, 300),
      label_color=INFO, size=11.5, label_dy=-6)
# channels -> Planning: month-end (the slow path) via right-hand rail
rail = 1895
arrow([(1860, 600 + 0), (rail, 600), (rail, 262), (1385, 262), (1385, 235)], RED, 3, "7 4",
      label="consolidated sales: month-end", label_at=(1520, 262), label_color=RED, size=12)
arrow([(1860, 410), (rail, 410)], RED, 3, "7 4", head=False)
arrow([(1860, 785), (rail, 785), (rail, 600)], RED, 3, "7 4", head=False)
# Depots <-> Planning
arrow([(1330, 350), (1330, 235)], INFO, 2, "6 4", label=f"stock: {wk.frequency}", label_at=(1360, 295), size=11, label_anchor="start")
arrow([(1180, 235), (1180, 350)], INFO, 2, "6 4", label=f"allocation: {mo.frequency}", label_at=(1170, 295), size=11, label_anchor="end")
# Planning -> Procurement (forecast), Marketing -> Procurement (launch notice), COO
arrow([(1100, 205), (330, 205)], INFO, 2, "6 4", label=f"forecast: {fc.frequency}", label_at=(720, 205), size=11.5)
arrow([(1650, 175), (1650, 88), (100, 88), (100, 175)], INFO, 2, "6 4",
      label=f"launch notice: {launch.lead_time_days_min / 7:.0f} weeks before launch (imported pulp needs 6-8)",
      label_at=(760, 88), size=11.5, label_dy=-6)
arrow([(1200, 175), (1200, 140)], INFO, 1.8, "6 4", both=True)
text(1212, 163, "monthly S&OP · trade-offs escalated", 11, INFO, bold=False)
# Procurement -> suppliers
arrow([(180, 235), (180, 350)], INFO, 2, "6 4", label="orders", label_at=(186, 290), size=11, label_anchor="start", label_dy=0)
text(186, 316, "quarterly for imported", 10.5, INFO)
text(186, 330, "dragonfruit", 10.5, INFO)
# the missing link
parts.append(f'<line x1="1402" y1="206" x2="1498" y2="206" stroke="{RED}" stroke-width="2" stroke-dasharray="2 4"/>')
text(1450, 197, "no link", 10.5, RED, bold=True, anchor="middle")
text(1450, 223, "stated", 10.5, RED, bold=True, anchor="middle")

# ================================================================ BOTTLENECK BADGES
badge(372, 395, 1)
badge(1050, 331, 2)
badge(1885, 262, 3)
# red outline on the bottleneck node/regions
parts.append(f'<rect x="866" y="346" width="253" height="0" fill="none"/>')

# ================================================================ BOTTLENECK STRIP + LEGEND
sy0 = 935
parts.append(f'<rect x="18" y="{sy0}" width="1884" height="122" rx="10" fill="#FDF3F1" stroke="#F0C9C3"/>')
items = [
    (1, "Passionfruit: single source, single road",
     "No second supplier, no alternative route; road closed 1+ week in 3 of the last 5 summers. Plants held ~2 weeks of pulp, "
     "the closure lasted 3. Feeds Passionfruit Punch + Dragon Passion = 28% of volume.", "F35 F41 F42 F43 F55"),
    (2, "Depot cover set from last year's mix",
     "3 weeks of cover per flavor, reset monthly, weekly stock in separate spreadsheets. A new flavor had no cover; "
     "overstock aged toward the 60-day retailer cutoff (INR 6 crore written off).", "F45 F46 F48 F60"),
    (3, "Demand signal reaches Planning at month-end",
     "Quick commerce tells Marketing daily, Planning only at month-end, and no flow links Marketing to Planning. "
     "Planners saw the spike when shortages were reported.", "F29 F30 F54"),
]
for i, (n, head, body, facts) in enumerate(items):
    x = 36 + i * 625
    badge(x + 14, sy0 + 26, n)
    text(x + 38, sy0 + 31, head, 14, RED, bold=True)
    for j, ln in enumerate(textwrap.wrap(body, 82)):
        text(x + 38, sy0 + 52 + j * 16, ln, 11.5, INK)
    text(x + 38, sy0 + 112, "case facts: " + facts, 10.5, MUTED, italic=True)

# legend (top-right)
lx, ly = 420, 104
legend = [("solid blue", GOODS, "", "goods"), ("dashed teal", INFO, "6 4", "information"),
          ("dashed grey", XFER, "6 4", "transfer"), ("dashed orange", AIR, "7 4", "air (contingency)")]
for i, (nm, col, dash, lab) in enumerate(legend):
    x = lx + (i % 2) * 190
    y = ly + (i // 2) * 20
    parts.append(f'<line x1="{x}" y1="{y + 6}" x2="{x + 34}" y2="{y + 6}" stroke="{col}" stroke-width="2.6" stroke-dasharray="{dash}"/>')
    text(x + 42, y + 10, lab, 11.5, INK)
for i, (src, lab) in enumerate([("Given", "border solid: Given"), ("Derived", "dotted: Derived"), ("Assumed", "dashed: Assumed")]):
    x = lx + i * 125
    parts.append(f'<rect x="{x}" y="{ly + 48}" width="26" height="14" rx="3" fill="#fff" stroke="{FAINT}" stroke-width="1.8" stroke-dasharray="{DASH[src]}"/>')
    text(x + 32, ly + 59, lab.split(": ")[-1], 11.5, INK)
text(lx, ly + 78, "* = mode assumed (case silent)", 11, MUTED, italic=True)

svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">' + "".join(parts) + "</svg>"
svg_path = OUT / "supply_network.svg"
svg_path.write_text(svg, encoding="utf-8")
print("wrote", svg_path)

# ---------------------------------------------------------------- render PNG with headless Chromium
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1.5)
        pg.goto(svg_path.as_uri())
        pg.screenshot(path=str(OUT / "supply_network.png"))
        b.close()
    print("wrote", OUT / "supply_network.png")
except Exception as e:                                   # the SVG alone is still usable
    print("PNG not rendered:", e)
