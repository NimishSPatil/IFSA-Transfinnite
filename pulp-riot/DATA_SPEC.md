# Pulp Riot dataset v2: spec (agreed in discussion; built, see data/v2/README.md)

## Changes made while building (the case's own numbers forced these)

1. **Demand saturates with heat.**
   - **Why:** plants make 2.5 cr/month and the summer averages 2.4 cr, so demand from March to June must be nearly flat.
   - **Change:** the temperature response is logistic: it rises through spring and plateaus in the hot months, instead of rising without limit.
2. **Pre-build.** In the last two weeks of a month, depots order against next month's forecast if it is higher. The 30-day freshness limit for modern trade and quick commerce still applies.
3. **Dragon Passion adds new demand, and takes share from Mango Peach Basil and Guava Chilli in the North and West.** The share it takes is calibrated to the ₹6 cr of write-offs.
4. **Measured growth hits the path exactly.**
   - Measured sales growth from Jul 2024–Jun 2025 to Jul 2025–Jun 2026 is 15% (±0.5 points).
   - The 2026 underlying trend is calibrated to make that true. It comes out at 20.6%, because 2026 lost so much to stock-outs.
   - Earlier years follow 45 → 32 → 25 → 19%.
5. **Only passionfruit and dragonfruit can limit production.**
   - These are the only supply constraints the case names: a single cooperative and road (F35, F41), and quarterly imports (F17).
   - Other pulps are topped up as needed; basil grows next to the plant (F75).
   - Pulp deliveries follow recent plant usage.
6. **The co-packer is called when orders exceed capacity:** 14 days' notice, up to +10% (F20–F22).
7. **The viral spike is defined as observed.**
   - Quick-commerce orders for Dragon Passion rise exactly 4× in two weeks (F53).
   - They hold for four weeks, then ease to 2× by end of June, as the rival takes the shelf space (case p2).
8. **Calibration checks use the case's own "about".** Summer share must be within ±0.2 points of 48%, and summer bottles within ±0.5% of 9.6 crore.

## Fixed decisions

| Topic | Decision |
|---|---|
| SKU | Flavor: MPB, GC, PP, DB, DP (DP exists only from 2 Mar 2026) |
| Period | Weekly, Mon 1 Jan 2024 to Sun 28 Jun 2026; "today" is July 2026 |
| Revenue basis | ₹1,200 cr = Jul 2025 to Jun 2026 (trailing 12 months, ending with last summer) |
| Growth | Logarithmic decline in the yearly rate, 2022 → 2026: 45%, 32%, 25%, 19%, 15% (Assumed). Revenue about ₹875 cr (2024 basis), ₹1,043 cr (2025), ₹1,200 cr (2026). 2022–23 are only used to shape the curve and the closure history |
| Seasonality | Indian monthly temperature (IMD climate averages; Assumed, external reference), damped during monsoon (Jul–Sep); one curve per region; scaled so Mar–Jun = 48% of the year |
| Grain | Weekly for everything. Quick-commerce sell-through is **also daily**, because the platforms send it daily (F29) |
| Visibility | Every record has `reported_date`: QC +1 day, depots weekly, consolidated sales month-end (F29, F30, F48) |
| Outliers | In 2024, 2025 and 2026; both real events and data errors; a hidden `outlier_log` is the answer key |

## Tables

**Master**

| Table | Contents |
|---|---|
| `calendar` | week start/end, month, season, year, region temperature index, monsoon flag |
| `sku` | flavor, launch date, price ₹60 average, shelf life 90 days |
| `depots` | 9 depots, region, size weight (Assumed), regional flavor tilt |
| `suppliers` | lead time min/max/spread, mode, single-source flag |
| `parameters` | control sheet (case figures) + every Assumed setting, tagged |
| `closures_history` | 2022–2026 summers: closed or not, length. 3 of 5 closed: 2024 (≥1 week), 2025 (≥1 week), 2026 (3 weeks, F55) |

**Demand**

| Table | Contents |
|---|---|
| `demand_weekly` | depot × channel × SKU: ordered, fulfilled, lost (fulfilled = sales; lost from stock-outs) |
| `qc_sellthrough_daily` | depot × SKU, quick commerce only, with report date |

**Supply**

| Table | Contents |
|---|---|
| `production_weekly` | plant × SKU planned vs actual, capacity 1.25 cr/month each, ~95% utilisation; co-packer use |
| `pulp_ledger_weekly` | plant × ingredient: opening, receipts, consumption, closing (kg, Assumed kg per bottle), days of cover. Anchored to 14 days on 11 May 2026 (F43) |
| `purchase_orders` | supplier, ingredient, quantity, order / promised / received date, mode, cost multiple. Imported dragonfruit ordered quarterly, 6–8 weeks' lead time |

**Inventory (weekly, depot × SKU)**

| Table | Contents |
|---|---|
| `inventory_weekly` | **opening, receipts, sales, transfers in/out, write-offs, closing (current stock)**, **P50 and P80** (the company's existing forecast: monthly, last year's mix, ~30% error), days of cover vs 21-day target, stock under the 60-day cutoff |
| `stock_batches` | bottling week, quantity left, days of shelf life left |
| `transfers` | from/to depot, quantity, 2–4 days, ₹1.50/bottle |
| `writeoffs_discounts` | quantity and ₹ value; total ≈ ₹6 cr in 2026 (F60) |

**Hidden answer key**

| Table | Contents |
|---|---|
| `outlier_log` | id, week, table, rows affected, type (real event / data error), expected model response. Never shown to the model |

## Outliers

| Year | Real events | Data errors |
|---|---|---|
| 2024 | Heatwave week in the North; 1-week highway closure; guava supplier delay | Depot spreadsheet typo (extra zero) |
| 2025 | 1-week highway closure; modern-trade promotion spike; 2-week import delay | A missing depot week |
| 2026 | Dragon Passion launch, then 4× quick-commerce spike (F51–F53); 3-week closure (F55); early heatwave | A one-off quick-commerce blip that reverts (false-alarm test) |

## KPIs the data must support

- **Supply:**
  - pulp days of cover per ingredient and plant
  - cover gap vs closure risk
  - import pipeline cover
  - supplier on-time rate and lead-time spread
  - single-source share of volume
  - launch notice vs lead time
  - air-freight ₹ and ₹/bottle
  - co-packer headroom
  - plant utilisation
- **Inventory:**
  - days of cover vs target per SKU
  - fill rate, stock-out weeks
  - lost units and ₹
  - share of stock under the 60-day cutoff
  - write-offs ₹
  - cover spread across depots
  - transfer opportunities
  - stock turns
  - P50/P80 vs actual
- **Link:**
  - passionfruit used by Dragon Passion vs Passionfruit Punch
  - delay from plant pulp run-out to depot stock-out
  - Passionfruit Punch / Dragon Passion allocation split

## Must still tie to the case (2026 summer)

- **Volume and mix:**
  - 9.6 cr bottles
  - flavor shares 38/20/16/14/12
  - channel shares 55/25/20
  - Mar–Jun = 48% of ₹1,200 cr
- **Production:** 2.5 cr/month at ~95%
- **Forecasting:** ~30% error at flavor × depot
- **Cover:**
  - ~3 weeks at depots
  - 14 days of pulp on the day the closure starts
- **Events:**
  - 3-week closure
  - Dragon Passion quick commerce rising 4×
- **Losses:**
  - ₹3.2 cr air freight
  - ₹6 cr write-offs
  - ₹46.08 cr lost revenue (≈ 0.77 cr bottles)
