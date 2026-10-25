# Pulp Riot model: one-page spec (v1, for sign-off)

Based on `FINAL WORKFLOW.pdf`, built in **Python + Streamlit** instead of Excel.

## Purpose and user

- **Purpose:** an early-warning and decision-support model for Pulp Riot's next summer. It is deep on **Supply** and **Inventory**, and links the two in both directions. Demand, Distribution and Transportation are covered at a high level.
- **User:** a planner who reviews flags and approves or rejects each recommendation. The COO approves escalated trade-offs.

## Inputs (all in `data/`, each value tagged Given / Derived / Assumed)

- **Network:** `nodes`, `edges`, `bom`, `products`, `channels`, `events`, `loss_ledger`, `Case_Facts`.
- **Demand:** `demand_daily`, rebuilt in layer 1 with both realized sales and unconstrained demand.
- **Inventory:** `inventory_snapshot` (weekly depot stock), plus daily passionfruit pulp at the plants, derived from consumption.
- **New `parameters.csv`:** the control sheet plus every threshold. Nothing is hard-coded in the logic.
- **New `launch_calendar.csv`:** empty for next summer by default.
- **New `approvals.csv`:** append-only, written only by a person through the app.

## Calculations (one Python module per layer, in `model/`)

| # | Layer | Output |
|---|---|---|
| 1 | Data fixes | Daily demand (realized + lost = unconstrained); pulp cover from consumption, anchored to the Given 14 days on 11 May; regional overstock scenario switch, calibrated to the ₹6 cr |
| 2 | Forecast | P50 by flavor × month from *unconstrained* demand; P80 = P50 × (1 + 0.84 × 30% ÷ 0.8) ≈ ×1.32 (Assumed); demand-shift alert when QC sales are ≥ 2× baseline for 3 days |
| 3 | Supply depth | Pulp days of cover against closure risk (3 of 5 summers, ≥ 1 week); import lead time against launch notice; shared-ingredient exposure |
| 4 | Inventory depth | Depot cover against the 21-day target, by flavor; shelf-life margin to the 60-day cutoff; transfer options at ₹1.50/bottle, 2–4 days |
| 5 | Link layer | **Supply → Inventory:** pulp run-out date becomes depot stock-out dates by flavor. **Inventory → Supply:** depot draw on Dragon Passion becomes passionfruit consumption, and the allocation trade-off between Passionfruit Punch and Dragon Passion |
| 6 | Risk engine | Flags with severity, evidence (row + case fact), recommended action and approver role |
| 7 | Approval queue | Every flag starts as **pending**; a named person approves or rejects, and the decision and reason are logged |
| 8 | Dashboard | Streamlit: all five areas, depth on Supply and Inventory |
| 9 | Scenario replay | The engine runs **as of each date** using only data known then; first flag date vs the real date |
| 10 | Loss and impact | ₹46.08 cr, ₹3.2 cr and ₹6 cr tied to the flags that would have prevented them, under stated assumptions |

## Rules

1. **Totals stay equal to the control sheet:**
   - 9.6 cr bottles
   - Flavor shares 38/20/16/14/12
   - Channel shares 55/25/20
   - ₹46.08 cr lost revenue, ₹3.2 cr air freight, ₹6 cr write-offs
2. **No hindsight:** a replay rule may use only facts knowable on that date.
3. **Hard caps on recommendations:**
   - Never exceed plant capacity of 2.5 cr/month.
   - Co-packer adds at most 0.25 cr/month and needs 14 days' notice.
4. **Nothing is ever auto-approved.**
5. **v1 data stays frozen:** layer 1 writes new tables and never edits the originals.

## Definition of done (run by `checks.py`, reported at each gate)

**Totals and integrity**
- No errors on a full run.
- Control totals tie.
- Original v1 tables are unchanged (hash check).

**Logic**
- Changing closure length (21 → 10 days), forecast error or cover target changes the dependent flags.
- Three numbers worked out by hand match the model's output.
- Every flag traces to a source row and a case fact.
- No output breaks the capacity or co-packer caps.
- Every approval is pending until a person decides.

**Replay**
- The demand-shift flag fires before **31 March**.
- The pre-season pulp flag fires before **11 May**.
- An operational pulp flag fires on closure day 1, recommending air freight in week 1, well before the **25 May** run-out.

**Scale**
- Adding a 6th flavor and a 10th depot in a test copy works without code edits.

## Handover to teammates

- `outputs/` holds the flags table, replay timeline, loss and impact, and the assumptions list, as CSV and one Excel export.
- The README gives the run order and colour legend.
- A change log and a frozen `v-final` copy.

## Review gates

| Gate | Layers |
|---|---|
| **A** | 1–4 (data, forecast, supply, inventory) |
| **B** | 5–7 (link, risk engine, approval queue) |
| **C** | 8–10 (dashboard, replay, loss and impact) |

## Defaults (say if you want them changed)

- Approvers are roles ("Head of Planning", "COO").
- The launch calendar for next summer is empty.
- Lost sales are spread across flavors by Assumed rules, shown as a separate table.
- The existing network, Sankey and timeline tabs are kept in the app.
