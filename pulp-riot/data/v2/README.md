# Dataset v2: weekly, 2024 – 2026

This is synthetic data, built from a day-by-day simulation of Pulp Riot and calibrated so that last summer (2026) reproduces every figure in the case.

**How to rebuild it**

```bash
python code/generate_dataset_v2.py
python code/write_dataset_v2.py
```

The first command calibrates the simulation. The second writes the tables and runs `dataset_checks.csv`.

**Visible vs hidden**

- **Model inputs:** everything in this folder.
- **Answer key and true values:** everything in `_hidden/`. **Never feed `_hidden/` to the model.**

## Period and timing

- **Weeks:** Monday to Sunday, from 1 Jan 2024 to 5 Jul 2026. "Today" is July 2026.
- **The ₹1,200 crore** is July 2025 to June 2026. Last summer is 1 Mar – 30 Jun 2026.
- **Reported dates:** every record says when the company would actually have received it.
  - `visible_to_planning`: consolidated sales at month-end (F30).
  - `visible_to_marketing`: quick commerce, the next day (F29).
  - Depot stock: the Monday after the week (F48).

  Backtests must only use rows whose reported date has passed.

## Tables

| Table | Grain | What it holds |
|---|---|---|
| `calendar_weekly` | week | ISO week, month, Jul–Jun fiscal year, days in summer, road-closed days, temperature and monsoon factor per region |
| `sku` | SKU = flavor | Price ₹60, unit cost ₹40.80, 90-day shelf life, 60-day cutoff, pulp mix |
| `depots` | depot | Region, size weight, flavor preference (all Assumed) |
| `suppliers` | supplier | Mode, lead time, order cycle, single-source flag |
| `closures_history` | year | Highway closures 2022–2026: 3 of the last 5 summers (F42) |
| `demand_weekly` | week × depot × channel × SKU | **ordered** (true demand) / **sold** / **lost** units, revenue, reported dates |
| `qc_sellthrough_daily` | day × depot × SKU | Quick-commerce units sold and out-of-stock flag, reported next day |
| `forecast_monthly` | month × depot × SKU | The company's **existing** P50 / P80 forecast (old method: last year's same month, last year's mix) |
| `inventory_weekly` | week × depot × SKU | Opening, receipts, transfers, sold, discounted, written off, **closing (current stock)**, **P50 / P80 for the week**, days of cover vs 21-day target, stock under 60 days left, status |
| `stock_batches_weekly` | week × depot × SKU × batch | Bottled date, units, age, shelf life left, accepted by MT/QC (Y/N) |
| `transfers` | transfer | Depot to depot, 3 days, ₹1.50/bottle |
| `writeoffs_discounts_weekly` | week × depot × SKU | Aged stock sold at a discount, and stock written off, in ₹ |
| `production_weekly` | week × plant × SKU | Requested vs produced, capacity, utilisation; co-packer headroom (unused) |
| `pulp_ledger_weekly` | week × plant × ingredient | Opening, road / import / air receipts, consumption, closing (kg), **days of cover**, target |
| `purchase_orders` | order | Pulp orders: promised vs received date, days late, mode, air-freight cost |
| `parameters` | – | The control sheet (case figures) plus every Assumed and Calibrated setting, with reasons |
| `dataset_checks` | – | Every case figure the data must reproduce, with pass/fail |

## How the data is made

**Demand**
- Growth falls logarithmically year by year: 45% → 32% → 25% → 19% → 15%.
- Seasonality follows each region's monthly temperature (approximate IMD normals), damped in the monsoon months.
- On top of that: region and flavor preferences, the channel mix, weekday patterns and noise.

**Depots**
- Replenished weekly by the company's old method: last year's same month, plus 3 weeks of cover.
- Stock sells oldest-first. Modern trade and quick commerce refuse stock with under 60 days of shelf life left.
- Older stock goes to general trade at a discount, or is written off.

**Plants**
- Capacity is 2.5 crore a month.
- Production is limited by pulp in cold storage.
- During the 2026 closure, Passionfruit Punch is cut to protect Dragon Passion (F58).

**Lost sales** are whatever the depots could not serve. They are produced by the simulation, not typed in. In summer 2026 they come to ₹45.7 crore:

| Flavor | Share of lost sales |
|---|---|
| Dragon Passion | 63% |
| Passionfruit Punch | 35% |
| Mango Peach Basil | 1.4% |
| Guava Chilli | 0.6% |

That matches the case: "ran out of both".

**Supply limits**
- Only **passionfruit** and **dragonfruit** can limit production:
  - passionfruit: single cooperative, single road (F35, F41);
  - dragonfruit: imports ordered quarterly (F17).
- Mango, peach, basil and guava are topped up as needed. Basil grows next to the plant (F75).

**What happens in May 2026**
- Passionfruit Punch production is cut 90% during the closure to protect Dragon Passion (F58).
- The air shipment is too small to prevent the run-out.

**Co-packer**
- It is called when weekly orders exceed plant capacity: 14 days' notice, up to +10%, +25% cost (F20–F22).
- It runs for most of the 2026 summer. `production_weekly` shows its units and extra cost.

**Transfers.** `transfers.csv` is empty on purpose. The old process moved no stock between depots, which is the case's point: "stock did not reach the depots where demand was rising". The model should recommend transfers that never happened.

**Calibration**
- These settings were tuned until 2026 reproduces the case:
  - overall level
  - season shape
  - mix multipliers
  - forecast noise
  - Dragon Passion cannibalisation
  - shortfall recognition
  - passionfruit cover target
  - aged-stock discount
  - 2026 trend growth
- Their values and reasons are in `parameters.csv`, and the run history is in `_hidden/calibration_log.csv`.
- Two values are large and worth knowing:
  - Dragon Passion takes **47% of Mango Peach Basil and Guava Chilli demand in the North and West**. This is what creates the overstock behind the ₹6 crore of write-offs.
  - The **2026 underlying trend is 20.6%**. Measured sales growth still comes out at 15%, because 2026 lost so much to stock-outs.

## Outliers

There are 14 in total, listed with the expected model response in `_hidden/outlier_log.csv`.

**Real events**
- 2024: a heatwave in the North, a 1-week highway closure, a guava supplier running late.
- 2025: a modern-trade promotion, a 10-day closure, an import arriving 14 days late.
- 2026: an early heatwave, the Dragon Passion launch, the viral spike, the 3-week closure, the air freight.

**Data errors** (true values are in `_hidden/`)
- **2024:** a spreadsheet typo with an extra zero.
- **2025:** a missing weekly depot report.
- **2026:** a one-day quick-commerce glitch that reverts. This is a false-alarm test.
