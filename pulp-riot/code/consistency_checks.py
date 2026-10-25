"""
consistency_checks.py  -  does the case agree with itself?  (brief Phase 1)

    python code/consistency_checks.py

Reads Case_Facts.csv (so every number is the one in the register) and writes
data/Consistency_Checks.csv with a pass / flag / insight status per check.
    pass     the figures agree within tolerance
    flag     they disagree; we record why and what we did about it
    insight  not a pass/fail test; a derived number the model will use
"""
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
facts = pd.read_csv(DATA / "Case_Facts.csv").set_index("fact_id")["value"]
v = lambda fid: float(facts[fid])

rows = []
def check(cid, desc, formula, computed, expected, status, note=""):
    rows.append((cid, desc, formula, round(computed, 4), expected, status, note))

bottles_year = v("F01") / v("F26")                       # crore INR / (INR per bottle) -> crore bottles
check("C01", "Annual bottles from revenue and price", "1200 cr / INR 60", bottles_year, "20 crore", "insight",
      "Derived annual volume: 20 crore bottles")
summer = bottles_year * v("F18") / 100
check("C02", "Summer bottles = 48% of annual", "20 cr x 48%", summer, f"{v('F31')} crore (F31)",
      "pass" if abs(summer - v("F31")) < 0.05 else "flag", "Matches the stated 9.6 crore")
cap4 = 4 * v("F32")
check("C03", "Four months of plant capacity", "4 x 2.5 cr", cap4, "10 crore", "insight")
util = v("F31") / cap4 * 100
check("C04", "Utilization implied by 9.6 cr", "9.6 / 10", util, f"{v('F33')}% (F33)",
      "pass" if abs(util - v("F33")) <= 1.5 else "flag",
      "96% vs stated 95%: within rounding of 'about 9.6 crore'")
check("C05", "Flavor shares add to 100%", "38+20+16+14+12",
      sum(v(f) for f in ("F09", "F10", "F11", "F12", "F13")), "100", "pass" if sum(v(f) for f in ("F09", "F10", "F11", "F12", "F13")) == 100 else "flag")
check("C06", "Channel shares add to 100%", "55+25+20", v("F23") + v("F24") + v("F25"), "100",
      "pass" if v("F23") + v("F24") + v("F25") == 100 else "flag")
check("C07", "Dragonfruit domestic + imported", "60+40", v("F14") + v("F15"), "100",
      "pass" if v("F14") + v("F15") == 100 else "flag")
rev_summer = v("F01") * v("F18") / 100
lost_rev = rev_summer * v("F61") / 100
check("C08", "Summer revenue", "1200 x 48%", rev_summer, "576 crore", "insight")
check("C09", "Revenue lost to stock-outs", "8% x 576", lost_rev, "~46 crore", "insight",
      "The brief's own figure (~46 crore); basis assumed to be summer revenue")
lost_bottles = lost_rev / v("F26")
check("C10", "Bottles lost to stock-outs", "46.08 cr / INR 60", lost_bottles, "~0.77 crore", "insight",
      "8% of the 9.6 crore sold, so potential demand was about 10.4 crore vs 10 crore of plant capacity")
check("C11", "Contribution lost on stock-outs", "46.08 x 32%", lost_rev * v("F02") / 100, "~14.7 crore", "insight",
      "Margin view of the revenue loss")
check("C12", "Normal air-freight cost implied", "3.2 cr / 5", v("F56") / v("F57"), "0.64 crore", "insight",
      "What the same pulp would have cost by road")
check("C13", "Pulp cover vs closure length", "21 days - 14 days", 21 - 14, "7 days uncovered",
      "flag", "Cover was about 2 weeks; closure ran 3 weeks. Expected to cause a stock-out, matching F59")
check("C14", "Usable shelf life at MT/QC after production", "90 - 60", v("F38") - v("F39"), "30 days", "insight",
      "A depot holding 21 days of cover leaves only about 9 days of margin before MT/QC reject the stock")
check("C15", "Co-packer ceiling", "10% x 2.5 cr x 4 months", 0.10 * cap4, "1.0 crore", "insight",
      "Co-packer can add about 1.0 crore bottles over the summer, versus ~0.77 crore lost: tight but not impossible")
check("C16", "Imported lead time vs ordering cycle", "6-8 weeks vs quarterly", 56, "<= 91 days",
      "pass", "One quarterly order is inside a 6-month pulp life but gives no room to react to a demand jump")
check("C17", "Viral peak vs when planners see the data", "30 Mar peak vs 31 Mar month-end", 1, "after the peak",
      "flag", "Planners get consolidated data a day after the peak; trade had already reported shortages (F54)")

pd.DataFrame(rows, columns=["check_id", "description", "formula", "computed", "expected", "status", "note"]) \
    .to_csv(DATA / "Consistency_Checks.csv", index=False, encoding="utf-8-sig")
for r in rows:
    print(f"{r[0]}  {r[5]:8} {r[1]:48} {r[3]}")
