# PulpSense | Raw-Material Supply Risk & Mitigation Playbook
_Complete context handoff for continuing the McKinsey / Pulp Riot Juice Co. hackathon discussion in a new ChatGPT account_
Status: strategic design agreed in discussion; mathematical logic is a proposed prototype, not an independently validated operational optimizer. Prepared 25 October 2026.

**READ FIRST** The official case explicitly says no dataset is provided. The supplied CSVs are sample / case-calibrated data and combine given, derived, and assumed fields. Separate case facts from prototype assumptions in every calculation and slide.


## 1  |  What we have decided
Goal: a transparent, human-approved decision-support layer for raw-material shortages, linked to Inventory Risk. PulpSense should detect supply pressure, calculate feasible alternative actions, compare no-action vs intervention, and show business trade-offs before any stakeholder approval.

| Pathway | Affected SKU(s) | Agreed mitigation |
|---|---|---|
| A — Production substitution | SKU 1  Mango Peach Basil (MPB) | If an input is unavailable, use confirmed pipeline/on-hand inventory and qualified supplier alternatives where feasible; then reallocate production to other SKUs only up to genuinely substitutable unmet demand. |
| B — Supplier-switching ladder | SKU 2  Guava Chilli (GC) | Use confirmed in-transit pipeline as a bridge; request a verified ramp-up from the second regional guava supplier; if insufficient, use partial switching + selective production reallocation; if both fail, reallocate more broadly. |
| C — Joint ingredient optimizer | SKU 3  Passionfruit Punch (PP); SKU 4  Dragonfruit Bloom (DB); SKU 5  Dragon Passion (DP) | Redistribute eligible finished stock first; then jointly allocate limited passionfruit and dragonfruit using real inventory, confirmed domestic/import arrivals, demand priorities, capacity, shelf life and approval. |

The model is not allowed to automatically execute purchases, production changes or inter-depot transfers. Its outputs are review candidates with status Pending / Approved / Rejected / Deferred and a recorded rationale.


## 2  |  Verified case facts and sample-data inputs

### 2.1  Case facts — source: McKinsey PS1, pp. 1–5
- Pulp Riot has five flavors, two plants and a co-packer, nine depots across four regions, and about 600 distribution / retail accounts. Summer volume mix: MPB 38%, GC 20%, PP 16%, DB 14%, DP 12%.
- Guava pulp comes from two regional suppliers. Passionfruit relies on a single hill-region cooperative; there is no qualified second supplier. The normal passionfruit road transit is three days, with no alternative road route.
- The passionfruit road has closed for at least a week in three of five summers; the May case closure lasted three weeks. Plants had about two weeks of pulp at closure start; the firm spent ₹3.2 crore on air freight at five times normal cost.
- Dragonfruit pulp was sourced 60% domestically and 40% internationally; imported pulp had 6–8 weeks lead time and was ordered quarterly. This 60/40 ratio is a sourcing MIX, not verified maximum domestic supplier capacity.
- Summer plant utilization reached ~95%; plants cannot add new mid-season lines. Co-packer can add up to 10% volume at a 25% cost premium and requires two weeks’ notice.
- Dragon Passion’s quick-commerce demand jumped fourfold after a viral reel. Forecasts were updated monthly and average flavor/depot forecast error was 30%; planners received consolidated sales too late.
- Frozen fruit pulp lasts up to six months in cold storage; juice bottles last 90 days; MT and quick commerce reject bottles with fewer than 60 days remaining. Depot-to-depot transfers take 2–4 days and average ₹1.50/bottle.
- Overall case impact: ₹6 crore in finished-goods write-offs/discounts, about 8% of summer revenue lost to stock-outs, and ₹3.2 crore air freight. These are system-wide outcomes, NOT amounts demonstrably avoidable by a specific proposed mitigation.


### 2.2  Prototype dataset fields — assumptions, NOT source facts
The supplied sku.csv assumes 0.06 kg of total pulp input per bottle and the recipe shares below. These quantities are convenient for a runnable model, but the case does not provide a verified bill of materials.

| SKU | Assumed ingredient requirement per bottle | Case role |
|---|---|---|
| MPB | 0.033 kg mango + 0.021 kg peach + 0.006 kg basil | Supply can fail through any one of three inputs |
| GC | 0.060 kg guava | Two-supplier recovery candidate |
| PP | 0.060 kg passionfruit | Single-source passionfruit user |
| DB | 0.060 kg dragonfruit | Domestic/import dragonfruit user |
| DP | 0.030 kg passionfruit + 0.030 kg dragonfruit | Jointly constrained by BOTH pulp supplies |

> Additional prototype assumptions: suppliers.csv assigns 3 days road lead time to mango, peach, basil, guava and domestic dragonfruit; only passionfruit’s three-day route is specifically established by the case. Dragonfruit “sea” transport mode is also a dataset assumption.


## 3  |  Raw-material risk register — all identified pathways
“Case” below means the risk is evidenced by an explicit case fact. “Conditional” means a sensible risk to monitor but its occurrence, probability and impact have not been demonstrated in the supplied evidence.

| ID | Risk / failure mode | SKUs | Evidence status / key response |
|---|---|---|---|
| R01 | Mango shortage / processor disruption | MPB | Case exposure; availability and alternate processor capacity unverified. Reallocate after material / inbound check. |
| R02 | Peach supply shortfall / hill-region disruption | MPB | Case geographic exposure. Inspect inbound dates and qualified alternate processors; then reallocate. |
| R03 | Fresh basil shortage / extraction bottleneck | MPB | Case input exposure; spoilage/extraction capacity are conditional. Verify usable output, then reallocate. |
| R04 | One of two guava suppliers stops dispatching | GC | Case two-source structure; disruption hypothetical. Use confirmed pipeline + supplier 2 ramp. |
| R05 | Both guava suppliers fail or backup cannot ramp sufficiently | GC | Conditional. Partial / full substitution-led production reallocation. |
| R06 | Passionfruit supplier interruption / highway closure | PP, DP | Case-confirmed. Project stock-outs and evaluate transport/supply contingencies. |
| R07 | Passionfruit competition between PP and DP | PP, DP | Case-confirmed production cut; joint allocation subject to demand and service floors. |
| R08 | Imported dragonfruit delay / quarterly purchase timing | DB, DP | Case-confirmed 6–8 weeks; reconcile existing stock, ETA and domestic supply. |
| R09 | Domestic dragonfruit supplier capacity gap / regional concentration | DB, DP | Conditional. Seek verified extra domestic supply; do not assume a fixed 60% cap. |
| R10 | Dragonfruit competition between DB and DP | DB, DP | Case ingredient sharing; allocation conflict inferred. Joint optimization. |
| R11 | Simultaneous passionfruit + dragonfruit shortfall | PP, DB, DP | Conditional compound disruption; combined two-ingredient optimization. |
| R12 | Pipeline visibility error / shipments not actually deliverable | All | Conditional cross-cutting. Count confirmed in-transit shipments only; recheck ETAs. |
| R13 | Demand shock exhausts raw-material cover faster than forecast | All, especially DP | Case viral spike; daily channel signals feed recalculated ingredient requirements. |
| R14 | Production bottleneck / SKU changeover infeasibility | All | Case 95% utilization and fixed lines; verify actual flexible capacity. |
| R15 | Shelf-life, quality or cold-storage unusability | All | Case shelf-life; quality loss / cold-chain failure conditional. Apply usable-stock filters. |
| R16 | Expedited freight / high spot purchase cost | All, especially PP/DP | Case expensive air freight; compare contribution exposure with premium. |
| R17 | Delayed marketing–procurement coordination / late order placement | All, especially DP | Case late launch notice and monthly forecast cycle; trigger earlier S&OP review. |
| R18 | Missing supplier capacity, recipe, route and transfer data | All | Known model limitation. Present review candidates and confidence warnings. |


## 4  |  SKU-by-SKU mitigation decisions

### SKU 1 — Mango Peach Basil | Multi-input shortage + substitution
A shortage of ANY required input (mango, peach or basil) constrains MPB. Check on-hand usable input, confirmed inbound by date, and any genuinely qualified alternate processor/farm first. Do not assume “contracted processors” guarantees unlimited backup supply. Calculate the ingredient-constrained maximum feasible MPB quantity. Then check whether excess MPB finished goods can cover priority depots before changing production.

For the remaining lost MPB volume, estimate how many customers would accept GC, PP, DB or DP as alternatives. Produce only what (a) customers might buy, (b) raw materials support, (c) plant capacity allows, and (d) can reach the right depot before the need date. The substitution fractions are NOT known from the case and must be presented as adjustable, testable hypotheses.


### SKU 2 — Guava Chilli | Three-stage supplier-switching ladder
1. Supplier 1 stops or reduces dispatch. Identify exactly which shipments were dispatched before the stoppage and which are expected to reach the plant. If a shutdown or road closure also affects transit, those shipments cannot automatically be counted.
2. Ask the existing second guava supplier for incremental capacity, earliest confirmed dispatch date, transit lead time and quoted cost. Use remaining on-hand stock + verified in-transit arrivals as a time bridge.
3. If supplier 2 can fully replace lost deliveries before projected stock falls below the minimum operating level, maintain GC output (subject to plant capacity and quality).
4. If supplier 2 can only partially replace output, combine a partial supplier ramp with selective alternative-SKU production. If neither supplier can supply, activate wider demand-substitution reallocation.
5. Reassess daily as arrivals, demand and supplier restoration plans change; approval needed for new procurement and production changes.

**CAUTION — 3-DAY BUFFER** Three-day transport time is NOT three guaranteed days of continuing inbound supply. That bridge exists only if the corresponding volume was dispatched, is not affected by the disruption and is due to arrive. Guava’s three-day lead time is a dataset assumption, unlike the case-confirmed three days for passionfruit.

Illustrative bridge calculation: if the plant consumes 1,000 kg/day guava, Supplier 1 normally dispatches 600 kg/day and Supplier 2 sends 400 kg/day, Supplier 2 must add 600 kg/day (a 150% increase over its original deliveries) to preserve the total. An uninterrupted three-day arrival pipeline works only if Supplier 1’s already-dispatched shipments are confirmed AND Supplier 2 can ramp and dispatch new material immediately for delivery as the old pipeline ends. Otherwise inventory on hand must cover the gap.


### SKU 3 — Passionfruit Punch | Shared scarce ingredient
Passionfruit Punch uses passionfruit alone under the prototype recipe, but it competes for scarce passionfruit with DP. Instead of reflexively cutting PP to favor DP, first redistribute shelf-life-eligible PP/DP finished goods and calculate residual depot/channel demand. Allocate the remaining pulp between PP and DP using an objective that considers incremental fulfillment, contribution and minimum service levels for both.

During highway closures, model on-hand stock, road shipments that can still arrive, and any approved emergency freight with genuine ETA/cost. A second supplier is NOT qualified in the case; treat alternate sourcing as a medium-term qualification project, not an immediately executable order.


### SKU 4 — Dragonfruit Bloom | Domestic flex + imported supply runway
Dragonfruit is 60% domestic / 40% imported in the case. PulpSense should forecast usable dragonfruit inventory by week through the 6–8-week import replenishment window. Prioritize already-held imported pulp and confirmed incoming shipments, and ask domestic suppliers how much EXTRA quantity they can reliably deliver. Do not impose a 60% production limit: the 60% is historical allocation, not demonstrated max production capacity.

If domestic capacity cannot fully bridge imports, jointly ration dragonfruit between DB and DP according to their actual unmet demand, remaining passionfruit, capacity and service commitments. Recover the normal sourcing mix only when shipments and inventory support it; imports do not all arrive exactly 6–8 weeks after a disruption.


### SKU 5 — Dragon Passion | Dual-ingredient constraint
DP consumes both passionfruit AND dragonfruit under the prototype mix. A proposed DP production increase is valid only if both ingredient constraints pass. If passionfruit fails, PP and DP compete. If dragonfruit fails, DB and DP compete. If both fail, optimize PP, DB and DP together, not as isolated decisions.

Because quick-commerce demand for DP rose fourfold in the case, channel demand should be updated more frequently than the monthly production plan. But the model should never equate a 4× order spike with a guaranteed 4× sell-through forecast.


## 5  |  Mathematical model another ChatGPT can implement

### 5.1  Daily material balance (preferred over a static “days of cover” guess)
For raw material k on day t: ClosingInventory[k,t] = OpeningInventory[k,t] + ConfirmedReceipts[k,t] + ApprovedIncrementalReceipts[k,t] − Sum_i(recipe[k,i] × production[i,t]). Receipts must be dated and counted once. Usable inventory excludes quarantined, expired and reserved quantities. Keep a configurable safety stock separately.

AvailableForNewProduction[k,t] = max(0, usable-on-hand + confirmed eligible arrivals up to t − safety stock − prior commitments). For a disruption, replay this balance over a rolling daily/weekly horizon and flag the first projected day inventory goes negative or below its approved buffer.


### 5.2  Joint production optimization for SKUs 3, 4 and 5
Decision variables: x_PP, x_DB, x_DP = ADDITIONAL feasible bottles produced in the chosen planning period (rather than total demand). Using ASSUMED sku.csv recipes:

- Passionfruit: 0.06 × x_PP + 0.03 × x_DP ≤ passionfruit kg allocated to incremental production.
- Dragonfruit: 0.06 × x_DB + 0.03 × x_DP ≤ dragonfruit kg allocated to incremental production.
- Demand ceilings: 0 ≤ x_i ≤ residual unmet demand_i after eligible finished goods, planned production and deliverable transfers.
- Capacity: Σ_i x_i ≤ truly available shared plant/co-packer capacity in the same time period; respect line flexibility, lead times and minimum lots.
- Optional service floor: delivered_i ≥ management-approved minimum commitment_i, if feasible; surface infeasibility rather than secretly dropping a constraint.

Suggested objective: maximize Σ_i (incremental contribution per bottle × fulfilled incremental bottles) − incremental procurement premiums − changeover cost − expedited freight − transfer costs − other attributable costs; optionally impose weighted service penalties. Casewide 32% contribution margin and ₹60/bottle imply ₹19.20/bottle as a rough, UNIFORM proxy, not a validated per-SKU incremental margin.


### 5.3  Supplier switching and demand substitution
Deficit[k,t] = max(0, required consumption[k,t] − deliverable receipts[k,t] − allowed inventory draw[k,t]). Supplier-2 ramp cannot exceed confirmed incremental production capacity, dispatch feasibility and shipment ETA. Use the daily material balance to determine whether any bridge is real.

For substitution from affected SKU i to alternative SKU j: SubstitutableDemand[i→j] ≤ LostSalesExposure_i × alpha[i,j], where alpha is an ASSUMED/validated switching probability. Enforce Σ_j alpha[i,j] ≤ 1 and never count the same customer twice. Actual extra production must also pass ingredient, plant, depot stock and delivery checks.


### 5.4  Case scenario arithmetic
Default May closure replay: closure = 21 days; initial passionfruit cover = 14 days; safety buffer = 3 days. Uncovered days = max(0, 21 − 14) = 7. Days beyond the safety buffer under the agreed prototype definition = max(0, 21 − 14 − 3) = 4. These are deterministic timing indicators, NOT unit-loss estimates or proof that ₹3.2 crore in freight could have been avoided.


### 5.5  Illustrative allocation check — not historical outcome
Suppose 3,000 kg passionfruit and 1,800 kg dragonfruit are usable; unmet PP demand is 40,000 bottles and unmet DP demand is 80,000 bottles. A PP-priority allocation (40,000 PP + 20,000 DP) uses all 3,000 kg passionfruit and 600 kg dragonfruit; it fulfills 60,000 bottles. If capacity permits, an allocation of 20,000 PP + 60,000 DP uses 3,000 kg passionfruit and 1,800 kg dragonfruit and fulfills 80,000 bottles. The increase is 20,000 bottles, but PP fulfillment falls from 100% to 50%, so the “best” choice depends on service floors and margins. Both mixes are made-up explanation scenarios.


## 6  |  End-to-end response workflow and dashboard outputs
1. DETECT: sudden change in incoming quantities, delayed PO ETA, falling ingredient cover, weather/highway alert, viral sell-through shock or unusual multi-SKU material consumption.
2. DIAGNOSE: identify affected ingredient → supplier(s) → bill-of-materials dependency → plants → SKU production → depot/channel coverage. Label incomplete links as “unverified”.
3. PRESERVE: reconcile usable on-hand material and confirmed in-transit raw material; check depot finished goods and eligible inter-depot transfers before ordering unnecessary additional production.
4. GENERATE: compare (a) no-action case, (b) supplier switching / domestic expansion, (c) partial production reallocation, (d) joint ingredient optimization, and (e) emergency freight where relevant.
5. EVALUATE: compute feasible bottles, residual shortages, days of coverage, service levels by SKU, logistics/procurement premium, stock-aging constraints and estimated contribution exposure with assumptions visible.
6. APPROVE: show recommendation, assumptions, confidence level and expiry of recommendation; COO/procurement/production approver chooses Pending, Approved, Rejected or Deferred and records rationale.
7. MONITOR: recompute upon new PO ETA, demand, inventory and approved decisions. Avoid promising real-time action from weekly CSV snapshots.

| Dashboard item | What to show / calculate |
|---|---|
| Supply dependency network | Ingredient → specific supplier → plant/co-packer → affected SKUs. Show domestic vs import branches and connection lines; do NOT treat illustrative edges as verified routes. |
| Shortage timeline | Projected daily/weekly material balance; first unsafe day; receipts from each source; risk thresholds labelled configurable. |
| SKU production comparison | Planned vs material-constrained production vs proposed reallocation; usable ingredient constraints and changeover/capacity checks. |
| Demand satisfaction | Per SKU and total: forecast unmet demand, incremental feasible fulfillment, minimum service coverage, residual unmet demand. |
| Mitigation cost / impact | Incremental procurement, freight, co-packer and transfer costs against estimated incremental contribution; avoid claims of realized savings. |
| Decision queue | Named stakeholder, action, status, recorded rationale, last refresh and whether source evidence is complete. |


## 7  |  Design guardrails, unresolved data and judge-proof cautions
- Do not label any recommendation an “optimized transfer” if historical transfers and route-specific costs are absent. transfers.csv is empty in the supplied project; inter-depot movement should be a REVIEW CANDIDATE and subject to 2–4-day transit, ~₹1.50/bottle and channel shelf-life eligibility.
- The provided data audit found an inventory ledger discrepancy of 4,149,405 bottles in one record and four rows with missing ledger values, despite dataset_checks.csv asserting a pass. Do not silently treat all inventory as reconciled.
- No measured customer SKU-to-SKU substitution matrix exists; the 20% / 15% / 5% switching example discussed earlier was illustrative only. Use scenario sliders, not “AI-predicted” rates, unless validated.
- No verified alternate supplier capacity, route ETAs for most ingredients, plant changeover costs/compatibility, real ingredient BOM or per-SKU margin is established. Require transparent input assumptions and feasible-range testing.
- Casewide losses cannot be attributed entirely to raw-material supply or claimed as avoided savings without a rigorous counterfactual. Distinguish measurable arithmetic from hypotheses.
- Supply protection can worsen Inventory Risk if increased alternative-flavor production goes to the wrong depot, arrives too late or nears expiry. Check destination-level demand, inventory age and acceptance windows.
- Budget ceiling is ₹2.5 crore for the FIRST YEAR, including build and running costs, with vendor-run IT. Do not create unsupported implementation/vendor cost figures.
- Formal approval precedes procurement, production changes, emergency freight, inter-depot transfer or co-packer reservation. No action is auto-executed.


### Recommended next development sequence
1. Build an ingredient-to-SKU dependency graph from sku.csv and supplier links from suppliers.csv, displaying source “Given” vs “Assumed”.
2. Implement a 28–56-day dated material balance with confirmed pipeline arrivals and delay sliders (different domestic and import lead times).
3. Implement supplier 2 spare-capacity input and multi-day bridge analysis for guava; include a “both suppliers down” branch.
4. Implement a small linear program for PP/DB/DP with two pulp constraints, demand ceilings, capacity and minimum service floors; expose Pareto trade-offs.
5. Add production reallocation/substitution for MPB/GC with editable, clearly hypothetical alpha coefficients; never force new sales demand.
6. Add scenario comparisons, net incremental economics and explicit Pending/Approved/Rejected/Deferred review persistence; test impossible and missing-data cases.


## 8  |  Copy-paste prompt for the next ChatGPT account
The paragraph below is designed to carry the conversation forward. Upload this document alongside the McKinsey PS1 PDF, plus the 17 CSVs or PulpSense project ZIP if model-building is required.

CONTINUATION PROMPT: I am building PulpSense, a hackathon decision-support dashboard for Pulp Riot Juice Co. Our two deep-dive modules are Supply and Inventory. Read the attached handoff in full; preserve the distinction between official case facts and assumed sample CSV fields. We have agreed on three raw-material risk mitigation pathways: (A) MPB multi-ingredient shortages → assess deliverable stock and qualified backups, then validated substitution-driven production reallocation; (B) GC two-supplier shortages → use confirmed in-transit pipeline as a bridge, verify supplier-2 ramp, partially reallocate if insufficient, fully reallocate only if both routes fail; (C) PP/DB/DP passionfruit/dragonfruit shortages → redistribute eligible finished goods first, then jointly optimize scarce pulp across the three SKUs using time-dated domestic/import receipts, on-hand stock, both shared-ingredient constraints, demand, plant capacity, service commitments and cost. Never treat the case’s 60% domestic dragonfruit SOURCING MIX as a fixed capacity ceiling, or the assumed three-day guava transit as guaranteed protection. Any recommendation needs human approval. Continue by critically examining additional failure modes and implementing clear mathematical/operational logic for the supply risk mitigation engine. Do not fabricate avoided savings, substitution rates, supplier spare capacity, shipment ETAs or optimized outcomes. Use all relevant source files if present.


## 9  |  Source record
- Primary: “TF’26 Problem Statements” PDF, Management PS1 “The Dragon Passion Problem at Pulp Riot Juice Co.”, pages 1–5.
- Sample files: sku.csv, suppliers.csv, parameters.csv, pulp_ledger_weekly.csv, purchase_orders.csv, production_weekly.csv, inventory_weekly.csv, demand_weekly.csv and related CSVs in the supplied Drive Data folder.
- Existing project audit: pulp_riot_dashboard/DATA_AUDIT.md and data_audit.json. The official PS1 explicitly allows teams to create sample data; the CSVs are not verified company transaction records.
- Discussion-derived ideas: production substitution for MPB/GC; guava confirmed-pipeline bridge and secondary-supplier ramp; joint PP/DB/DP pulp allocation; domestic supply flex during import delays; three-level fallback and human review.

END OF HANDOFF — all assumed figures require sensitivity analysis or owner validation before any operational use.

