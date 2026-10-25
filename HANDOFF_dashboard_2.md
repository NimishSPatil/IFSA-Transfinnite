# Inventory rebalancing: handoff for the dashboard

## Files
- `dashboard_data.json` and `dashboard_data.js` hold the same data (1.7 MB).
  - Use the `.js` file if you open the HTML straight from disk: `<script src="dashboard_data.js"></script>` gives you `window.DASHBOARD_DATA`.
  - Use the `.json` file if you serve the page: `fetch("dashboard_data.json")`.
- `inventory_weekly_with_loss_and_rebalancing.xlsx` is the same numbers with live formulas, for checking figures.

No Python is needed to run the dashboard. The data is already computed.

## What the data contains
`totals`, `monthly[]`, `by_sku[]`, `transfers[]`, `weekly[]`, and `meta` (assumptions and units). All money is in rupees. Divide by 10,000,000 for crore.

| Key | What it is |
|---|---|
| `totals` | Headline: loss before, loss after, transport, after_total, saving, number of transfers, bottles moved |
| `monthly[]` | Loss before, loss after and transport for each month (month = month the week ends in) |
| `by_sku[]` | Same, by SKU |
| `transfers[]` | One recommended transfer: week, SKU, from, to, bottles, transport cost, cover at sender and receiver (days), reasons, approver |
| `weekly[]` | One row per depot, SKU and week (4,878 rows): receipts, sales, P50, P80, closing stock and cover days **before** and **after** rebalancing, status before and after, loss before and after |

Headline numbers the dashboard should reproduce: loss before Rs 21.79 cr, loss after Rs 19.08 cr, transport Rs 0.76 cr, after total Rs 19.84 cr, saving Rs 1.96 cr (9%), 113 transfers, 50.75 lakh bottles moved.

## Definitions to show on the page
- **P50 / P80:** the file's weekly demand forecasts. P80 is a higher, safer estimate.
- **Loss (my rule):** Rs 15.36 per bottle by which closing stock is below P50, plus Rs 3.84 per bottle below P80. A bottle below P50 therefore costs Rs 19.20 (Rs 60 x 32% contribution).
- **Before:** the week as it happened, no transfers.
- **After:** the same week replayed with the transfers in `transfers[]`.
- **Status:** stock-out (closing 0), below P50, below P80, ok, over 35d (more than 35 days of stock).
- **Cover days** = closing stock / (P50 / 7).
- **Reasons on transfers:** LOW_COVER, DEMAND_SHIFT, OVERSTOCK, SHELF_LIFE, IMBALANCE.
- **Approver:** every transfer is a recommendation that needs the supply chain manager to approve.

## Suggested views
1. Headline cards: loss before, after (incl. transport), saving.
2. Monthly bars: before versus after (stacked: remaining loss + transport).
3. Heatmap: depot x SKU, cover days for a chosen week, with a before/after toggle.
4. Transfers table for a chosen week: from, to, bottles, cost, reasons, approver.
5. SKU split showing which SKUs are fixed by moving stock and which are not.
6. A line chart of weekly loss before and after.

## Be honest on the page
- About Rs 19.9 cr of the Rs 21.8 cr loss is Passionfruit Punch and Dragon Passion. Those weeks were short across the whole network (road closure and viral spike), so moving stock between depots cannot fix them. Say that next to the headline saving.
- A few small months and SKUs (for example Guava Chilli) cost more in transport than they save. Show this and don't hide it.
- The original file's flat-rule loss (Rs 25.97 cr) is a different definition. If you show it, label it.

## Assumptions to display (all in `meta.assumptions`)
Transport Rs 1.50 per bottle, 3-day transit, minimum transfer 10,000 bottles, loss Rs 15.36 and Rs 3.84 per bottle, overstock above 35 days.

## Limits of the data
- Demand in stock-out weeks is a lower bound, so shortages are understated.
- The transfers were chosen by an optimiser run offline. A rate change on the dashboard would not re-run it.
- Four unreported rows (East depot 1, week of 2025-02-03) keep their original loss.
