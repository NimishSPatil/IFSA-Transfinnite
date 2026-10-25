# IFSA TransfiNITTe 2026 — PS1: The Dragon Passion Problem (Pulp Riot Juice Co.)

**PulpSense**, a human-approved decision-support dashboard for Pulp Riot's supply and inventory, built on a case-calibrated synthetic dataset.

- **The project:** [`pulp-riot/`](pulp-riot/README.md): dashboard, data, code and notes.
- **Run locally:** `pip install -r pulp-riot/dashboard/requirements.txt`, then `python pulp-riot/dashboard/run.py`, then open http://localhost:8600.
- **Deploy:** `render.yaml` (Render → New → Blueprint).
- **Notes:** `pulp-riot/docs/PROMPT1_NOTES.md` (Supply) and `pulp-riot/docs/PROMPT2_NOTES.md` (Inventory).
- **Inputs in this folder:** the problem statement, workflow PDFs, briefs, the teammate's inventory feed and the sales-reporting sheet.

All data is synthetic, built from the case figures. Nothing on the dashboard executes an action: every recommendation needs a named approver.
