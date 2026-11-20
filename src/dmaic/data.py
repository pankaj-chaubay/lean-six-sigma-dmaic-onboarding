"""Generated onboarding cases for a fictional company with three sites.

One row per new hire, one column per step, with process time (hands-on work)
and waiting time in working days. The baseline process runs the steps one after
another. The improved process starts IT work at offer acceptance, in parallel
with the contract, and uses a standard access request form.

Planted causes of delay in the baseline:
* IT equipment is ordered only after the contract is signed (one step after another)
* access requests come back for missing information (rework, about 1 in 4)
* hiring managers who send the request late (less than 10 days before start)
* site C has a longer equipment delivery time
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STEPS = [
    # name, mean process time (days), mean waiting time before the step (days)
    ("Issue contract", 0.5, 1.5),
    ("Sign contract", 0.2, 2.0),
    ("Order IT equipment", 0.3, 1.0),
    ("Deliver equipment", 0.2, 3.5),
    ("Request system access", 0.3, 0.8),
    ("Provision access", 0.4, 1.5),
    ("Book onboarding training", 0.2, 0.8),
]
SITES = {"A": 1.0, "B": 1.1, "C": 1.45}


def generate(n: int = 240, seed: int = 11, improved: bool = False, start: str = "2025-01-01", span_days: int = 364) -> pd.DataFrame:
    rng = np.random.default_rng(seed + (100 if improved else 0))
    rows = []
    for i in range(n):
        site = rng.choice(list(SITES), p=[0.45, 0.35, 0.2])
        late_request = rng.random() < (0.12 if improved else 0.3)
        rework = rng.random() < (0.08 if improved else 0.26)
        rec = {"case_id": f"{'P' if improved else 'B'}{i + 1:04d}", "site": site, "late_request": late_request, "access_rework": rework}
        pt_total = wt_total = 0.0
        step_times = {}
        for name, pt, wt in STEPS:
            p = rng.gamma(4, pt / 4)
            w = rng.gamma(2, wt / 2)
            if name == "Deliver equipment":
                w *= SITES[site]
            if name == "Provision access" and rework:
                w += rng.gamma(3, 1.2)
                p += 0.3
            if late_request and name in ("Issue contract", "Order IT equipment"):
                w += rng.gamma(2, 0.8)
            step_times[name] = (p, w)
            pt_total += p
            wt_total += w
            rec[f"pt_{name}"] = round(p, 2)
            rec[f"wt_{name}"] = round(w, 2)
        if improved:
            # IT equipment is ordered at offer acceptance, in parallel with the contract.
            # Access still needs the signed contract, so it follows the contract.
            contract = sum(sum(step_times[s]) for s in ("Issue contract", "Sign contract"))
            it = sum(sum(step_times[s]) for s in ("Order IT equipment", "Deliver equipment"))
            access = sum(sum(step_times[s]) for s in ("Request system access", "Provision access"))
            lead = max(contract + access, it) + sum(step_times["Book onboarding training"])
        else:
            lead = pt_total + wt_total
        rec["process_time_days"] = round(pt_total, 2)
        rec["lead_time_days"] = round(lead, 2)
        days_to_start = rng.normal(17, 3) if not late_request else rng.normal(10, 2)
        rec["days_offer_to_start"] = round(days_to_start, 1)
        rec["ready_on_day_one"] = bool(lead <= days_to_start)
        rec["offer_accepted"] = (pd.Timestamp(start) + pd.Timedelta(days=int(i * span_days / n))).date().isoformat()
        rows.append(rec)
    return pd.DataFrame(rows)
