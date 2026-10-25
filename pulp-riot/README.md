# Pulp Riot (PS1): data, network model and PulpSense

**Deep modules:** Supply and Inventory. Demand, Distribution and Transportation are covered at a high level.

## 0. PulpSense decision support (prompt 1: Supply)

The dashboard below now carries a decision engine (`dashboard/app/engine/`). It covers a daily pulp material balance, 27 risk rules,
compare-and-choose tables for each shortage, the co-packer rule, a daily quick-commerce detector with replays, a simulated
Social Signal Desk, a Control Panel (82 controls with sources, scenarios and presets), READ_ME and a review queue.
Nothing is executed: every recommendation needs a named approver and a rationale.

- **Notes and deliverables:** `docs/PROMPT1_NOTES.md` (change log, decision tables, risk register, assumptions, controls, hand-off to prompt 2).
- **Acceptance checks:** `python code/check_prompt1.py` (8 checks, writes `docs/acceptance_prompt1.csv`).
- **Regenerate the notes:** `python code/export_prompt1_docs.py`.
- **Inventory (prompt 2):** the teammate's rebalancing feed (`data/inventory_feed/`) drives the Inventory module: Rebalancing (with a
  reconciliation strip), Supply ↔ Inventory, Overstock & aging and Forecast source. Notes: `docs/PROMPT2_NOTES.md`;
  checks: `python code/check_prompt2.py`; regenerate notes: `python code/export_prompt2_docs.py`.

## 1. Control tower dashboard

```bash
python dashboard/run.py
```

Then open http://localhost:8600. It needs `fastapi uvicorn jinja2 pandas numpy` (see `dashboard/requirements.txt`). It runs offline: no CDN and no web fonts.

There is one control on every page: the **As of week**. The dashboard shows only what the company could have known on the Monday after that week, so last summer can be replayed week by week without hindsight. Quick jumps take you to the Dragon Passion launch, the viral spike, the highway closing and the pulp running low.

| Page | What it shows |
|---|---|
| **Overview** | Sales and lost sales over the last 4 weeks, depot × flavor pairs under 7 days, and passionfruit cover against the longest closure. Five area tiles with sparklines, a 26-week sales / lost-sales chart, a network map coloured by this week's state, and a placeholder for model alerts. |
| **Demand** | Fill rate and the old forecast's error. Demand vs the P50–P80 forecast. The **signal gap**: what Marketing sees daily against what Planning has at month-end, with stock-out days marked. The quick-commerce pulse, the mix and lost sales. |
| **Supply** | Passionfruit and dragonfruit cover. Plant utilisation and the co-packer. Pulp orders in trouble. Who each flavor depends on (single source), pulp cover by plant and ingredient, the import pipeline, production, and the order log. |
| **Inventory** | A depot × flavor cover heatmap, measured **against the forecast or against actual sales** (the gap between them is the overstock story). 26-week status, stock age against the 60-day cutoff, write-offs and discounts, a depot ledger, and data quality. |
| **Distribution** | Flow from plants to regions to channels. Shipped vs ordered by region. Regional balance against actual sales. **Mismatches** (surplus at one depot, shortage at another), presented as facts. Fill rate by region × channel. |
| **Transportation** | Highway status and closure record. Inbound lanes with on-time rates. Passionfruit arrivals by road and air, air-freight cost, imports on the water, outbound shipments, and transfers. |
| **Data & assumptions** | The 23 case-figure checks, every setting tagged Given / Derived / Assumed / Calibrated, the tables behind each page, how "As of" works, and data quality. |

The dashboard is descriptive. Alerts and recommended actions arrive with the risk model, which is the next step.

## 2. Dataset v2 (what the dashboard reads)

Weekly data from January 2024 to July 2026, plus daily quick-commerce data. It is simulated and calibrated so that 2026 reproduces every case figure. See `data/v2/README.md` and `DATA_SPEC.md`.

```bash
python code/generate_dataset_v2.py
python code/write_dataset_v2.py
```

The first command calibrates; the second writes the tables and runs `data/v2/dataset_checks.csv`.

- **The answer key:** `data/v2/_hidden/` lists the planted events and data errors, with their true values. Neither the dashboard nor the model may read it.

## 3. Network model and flowchart (v1)

The network itself (nodes, edges, bill of materials, case facts, gaps, assumptions) lives in `data/*.csv`. The flowchart `diagrams/supply_network.png`, the SQLite file and the Excel workbook are generated from it:

```bash
python code/consistency_checks.py
python code/generate_sample_data.py
python code/load_db.py
python code/build_graph.py
python code/load_db.py
python code/draw_diagram.py
python code/export_excel.py
python code/trace_facts.py
```

`code/seed_tables.py` created the starting tables and will not overwrite them without `--force`.

## What is where

| Path | What it is |
|---|---|
| `dashboard/` | The control tower (FastAPI + server-rendered HTML, CRM visual style in blue) |
| `data/v2/` | Dataset v2: weekly demand, stock, batches, production, pulp, orders, forecasts, parameters, checks |
| `data/*.csv` | Network tables (v1): case facts, gaps, assumptions, nodes, edges, BOM, events, risk flags |
| `code/` | Generators and builders for both |
| `diagrams/supply_network.png` | The flowchart, generated from the network tables |
| `MODEL_SPEC.md`, `DATA_SPEC.md` | What the model and the data are meant to do |

## Known limits (worth saying out loud)

- **All data is synthetic.** The case provides none. Every case figure is reproduced, but daily shapes, regional splits and depot sizes are assumptions, each listed with its reason in `data/v2/parameters.csv`.
- **Weekly reporting is assumed.** The dashboard assumes depot reports reach Planning weekly. Today, per the case, Planning sees consolidated sales only at month-end. The Demand page shows that gap rather than hiding it.
- **Plant-to-depot transport is simplified:** road, delivered within the week. The case gives no lead time.
- **Lost revenue is not yet attributed** to causes. That's the model's job.
