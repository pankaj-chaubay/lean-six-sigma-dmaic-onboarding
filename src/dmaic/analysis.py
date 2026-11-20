"""Measure, Analyze, Improve and Control calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .data import STEPS

USL_DAYS = 15.0  # CTQ: equipment, access and training ready within 15 working days of offer acceptance

# ---- Measure -------------------------------------------------------------------


def value_stream(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, _, _ in STEPS:
        rows.append({"step": name, "process_time_days": round(df[f"pt_{name}"].mean(), 2), "waiting_time_days": round(df[f"wt_{name}"].mean(), 2)})
    vs = pd.DataFrame(rows)
    vs["lead_time_days"] = vs["process_time_days"] + vs["waiting_time_days"]
    return vs


def process_cycle_efficiency(df: pd.DataFrame) -> float:
    """Share of the lead time spent on actual work."""
    return round(float(df["process_time_days"].mean() / df["lead_time_days"].mean()), 3)


def capability(x: pd.Series, usl: float = USL_DAYS) -> dict:
    """Upper-limit capability. Ppk from the normal fit, and a percentile version
    because lead times are right-skewed."""
    x = np.asarray(x, float)
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    ppk = (usl - mu) / (3 * sd)
    p99865 = np.percentile(x, 99.865)
    ppk_pct = (usl - np.median(x)) / (p99865 - np.median(x))
    defects = float((x > usl).mean())
    dpmo = defects * 1_000_000
    sigma = stats.norm.ppf(1 - defects) + 1.5 if 0 < defects < 1 else float("inf")
    shapiro_p = stats.shapiro(x).pvalue if len(x) <= 5000 else np.nan
    return {
        "mean": round(mu, 2),
        "median": round(float(np.median(x)), 2),
        "std": round(sd, 2),
        "ppk_normal": round(ppk, 2),
        "ppk_percentile": round(float(ppk_pct), 2),
        "share_over_usl": round(defects, 3),
        "dpmo": int(round(dpmo)),
        "sigma_level": round(float(sigma), 2),
        "normality_p": round(float(shapiro_p), 4),
    }


# ---- Analyze -------------------------------------------------------------------


def delay_pareto(df: pd.DataFrame) -> pd.DataFrame:
    """Waiting time by step, sorted, with cumulative share."""
    w = pd.Series({name: df[f"wt_{name}"].sum() for name, _, _ in STEPS}).sort_values(ascending=False)
    out = pd.DataFrame({"step": w.index, "waiting_days_total": w.round(0).astype(int).values})
    out["share"] = (out["waiting_days_total"] / out["waiting_days_total"].sum()).round(3)
    out["cumulative_share"] = out["share"].cumsum().round(3)
    return out


def root_cause_tests(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    a = df.loc[df["access_rework"], "lead_time_days"]
    b = df.loc[~df["access_rework"], "lead_time_days"]
    u = stats.mannwhitneyu(a, b, alternative="greater")
    rows.append({"hypothesis": "Cases with access rework take longer", "test": "Mann-Whitney U", "effect": f"median {a.median():.1f} vs {b.median():.1f} days", "p_value": u.pvalue})

    a = df.loc[df["late_request"], "lead_time_days"]
    b = df.loc[~df["late_request"], "lead_time_days"]
    u = stats.mannwhitneyu(a, b, alternative="greater")
    rows.append({"hypothesis": "Late requests from hiring managers take longer", "test": "Mann-Whitney U", "effect": f"median {a.median():.1f} vs {b.median():.1f} days", "p_value": u.pvalue})

    table = pd.crosstab(df["late_request"], df["ready_on_day_one"])
    chi = stats.chi2_contingency(table)
    ready = df.groupby("late_request")["ready_on_day_one"].mean()
    rows.append({"hypothesis": "Late requests are less often ready on day one", "test": "Chi-square", "effect": f"{ready.get(True, 0):.0%} vs {ready.get(False, 0):.0%} ready", "p_value": chi.pvalue})

    groups = [g["lead_time_days"].to_numpy() for _, g in df.groupby("site")]
    k = stats.kruskal(*groups)
    med = df.groupby("site")["lead_time_days"].median()
    rows.append({"hypothesis": "Lead time differs by site", "test": "Kruskal-Wallis", "effect": ", ".join(f"{s} {m:.1f}" for s, m in med.items()), "p_value": k.pvalue})

    w = df.groupby("site")["wt_Deliver equipment"].median()
    k2 = stats.kruskal(*[g["wt_Deliver equipment"].to_numpy() for _, g in df.groupby("site")])
    rows.append({"hypothesis": "Equipment delivery wait differs by site", "test": "Kruskal-Wallis", "effect": ", ".join(f"{s} {m:.1f}" for s, m in w.items()), "p_value": k2.pvalue})

    out = pd.DataFrame(rows)
    out["confirmed"] = out["p_value"] < 0.05
    out["p_value"] = out["p_value"].map(lambda v: f"{v:.1e}")
    return out


def regression(df: pd.DataFrame) -> pd.DataFrame:
    """Lead time on all causes at once, so each effect is shown with the others held fixed."""
    X = pd.DataFrame(
        {
            "intercept": 1.0,
            "access_rework": df["access_rework"].astype(float),
            "late_request": df["late_request"].astype(float),
            "site_B": (df["site"] == "B").astype(float),
            "site_C": (df["site"] == "C").astype(float),
        }
    )
    y = df["lead_time_days"].to_numpy()
    beta, *_ = np.linalg.lstsq(X.to_numpy(), y, rcond=None)
    resid = y - X.to_numpy() @ beta
    dof = len(y) - X.shape[1]
    se = np.sqrt(np.diag(resid @ resid / dof * np.linalg.inv(X.T.to_numpy() @ X.to_numpy())))
    p = 2 * stats.t.sf(np.abs(beta / se), dof)
    r2 = 1 - resid @ resid / ((y - y.mean()) @ (y - y.mean()))
    out = pd.DataFrame({"term": X.columns, "days": beta.round(2), "std_error": se.round(2), "p_value": [f"{v:.1e}" for v in p]})
    out.attrs["r2"] = round(float(r2), 3)
    return out


# ---- Improve -------------------------------------------------------------------


def compare(before: pd.DataFrame, after: pd.DataFrame) -> dict:
    u = stats.mannwhitneyu(before["lead_time_days"], after["lead_time_days"], alternative="greater")
    both = pd.concat([before.assign(g="before"), after.assign(g="after")], ignore_index=True)
    t = pd.crosstab(both["g"], both["ready_on_day_one"])
    chi = stats.chi2_contingency(t)
    lv = stats.levene(before["lead_time_days"], after["lead_time_days"])
    return {
        "median_before": round(float(before["lead_time_days"].median()), 1),
        "median_after": round(float(after["lead_time_days"].median()), 1),
        "median_reduction_pct": round(float(100 * (1 - after["lead_time_days"].median() / before["lead_time_days"].median())), 1),
        "lead_time_p_value": f"{u.pvalue:.1e}",
        "std_before": round(float(before["lead_time_days"].std()), 1),
        "std_after": round(float(after["lead_time_days"].std()), 1),
        "variance_p_value": f"{lv.pvalue:.1e}",
        "ready_day_one_before": round(float(before["ready_on_day_one"].mean()), 3),
        "ready_day_one_after": round(float(after["ready_on_day_one"].mean()), 3),
        "ready_p_value": f"{chi.pvalue:.1e}",
        "pce_before": process_cycle_efficiency(before),
        "pce_after": process_cycle_efficiency(after),
    }


# ---- Control -------------------------------------------------------------------


def imr_limits(x: pd.Series) -> dict:
    x = np.asarray(x, float)
    mr = np.abs(np.diff(x))
    mrbar = mr.mean()
    center = x.mean()
    return {k: round(float(v), 2) for k, v in {"center": center, "ucl": center + 2.66 * mrbar, "lcl": max(center - 2.66 * mrbar, 0.0), "mr_bar": mrbar, "mr_ucl": 3.267 * mrbar}.items()}


def rule_violations(x: pd.Series, limits: dict) -> pd.DataFrame:
    """Western Electric rule 1 (a point beyond a limit) and rule 4 (eight points in a row on one side)."""
    x = np.asarray(x, float)
    hits = []
    for i, v in enumerate(x):
        if v > limits["ucl"] or v < limits["lcl"]:
            hits.append({"point": i + 1, "value": round(v, 1), "rule": "beyond control limit"})
    side = np.sign(x - limits["center"])
    run = 1
    for i in range(1, len(x)):
        run = run + 1 if side[i] == side[i - 1] and side[i] != 0 else 1
        if run == 8:
            hits.append({"point": i + 1, "value": round(x[i], 1), "rule": "8 in a row on one side of the centre"})
    return pd.DataFrame(hits, columns=["point", "value", "rule"])


def p_chart(df: pd.DataFrame, freq: str = "M") -> pd.DataFrame:
    """Share not ready on day one per month, with limits that depend on the month's sample size."""
    d = df.copy()
    d["period"] = pd.to_datetime(d["offer_accepted"]).dt.to_period(freq).astype(str)
    g = d.groupby("period").agg(n=("case_id", "count"), not_ready=("ready_on_day_one", lambda s: int((~s).sum()))).reset_index()
    pbar = g["not_ready"].sum() / g["n"].sum()
    g["p"] = (g["not_ready"] / g["n"]).round(3)
    se = np.sqrt(pbar * (1 - pbar) / g["n"])
    g["ucl"] = (pbar + 3 * se).clip(upper=1).round(3)
    g["lcl"] = (pbar - 3 * se).clip(lower=0).round(3)
    g["center"] = round(pbar, 3)
    g["out_of_control"] = (g["p"] > g["ucl"]) | (g["p"] < g["lcl"])
    return g
