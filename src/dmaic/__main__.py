"""python -m dmaic  ->  data/, reports/results.md and charts"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import analysis as a  # noqa: E402
from . import data  # noqa: E402

BLUE, GREY, INK, INK2, SURFACE, RED = "#2a78d6", "#b9b8b2", "#0b0b0b", "#52514e", "#fcfcfb", "#d1453b"


def md(df: pd.DataFrame) -> str:
    if df.empty:
        return "None."
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(map(str, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=9)


def vsm_chart(vs: pd.DataFrame, path: Path) -> None:
    d = vs.iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor=SURFACE)
    ax.barh(d["step"], d["process_time_days"], color=BLUE, height=0.6, label="Process time (work)")
    ax.barh(d["step"], d["waiting_time_days"], left=d["process_time_days"], color=GREY, height=0.6, label="Waiting time")
    ax.set_xlabel("Average working days per case", color=INK2, fontsize=9)
    ax.set_title("Baseline value stream: most of the lead time is waiting", loc="left", fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def before_after_chart(b: pd.DataFrame, p: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.2), facecolor=SURFACE)
    bins = range(0, 36, 1)
    ax.hist(b["lead_time_days"], bins=bins, color=GREY, label=f"Baseline (n={len(b)})", density=True)
    ax.hist(p["lead_time_days"], bins=bins, color=BLUE, alpha=0.75, label=f"Pilot (n={len(p)})", density=True)
    ax.axvline(a.USL_DAYS, color=INK, lw=1.5, ls="--")
    ax.text(a.USL_DAYS + 0.3, ax.get_ylim()[1] * 0.9, "Upper limit 15 days", fontsize=8, color=INK)
    ax.set_xlabel("Lead time, offer accepted to ready (working days)", color=INK2, fontsize=9)
    ax.set_yticks([])
    ax.set_title("Lead time before and after", loc="left", fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=8)
    style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def control_chart(pilot: pd.DataFrame, ctrl: pd.DataFrame, limits: dict, path: Path) -> None:
    x = list(pilot["lead_time_days"]) + list(ctrl["lead_time_days"])
    fig, ax = plt.subplots(figsize=(7, 3.2), facecolor=SURFACE)
    ax.plot(range(1, len(x) + 1), x, color=BLUE, lw=1.5, marker="o", ms=3)
    for k, ls in (("center", "-"), ("ucl", "--"), ("lcl", "--")):
        ax.axhline(limits[k], color=INK2, lw=1, ls=ls)
        ax.text(len(x) + 1, limits[k], f"{k.upper()} {limits[k]:.1f}", fontsize=8, color=INK2, va="center")
    out = [(i + 1, v) for i, v in enumerate(x) if v > limits["ucl"] or v < limits["lcl"]]
    if out:
        ax.scatter(*zip(*out), color=RED, zorder=3, s=25)
    ax.axvline(len(pilot) + 0.5, color=GREY, lw=1)
    ax.text(len(pilot) / 2, max(x) * 1.02, "Pilot (limits set here)", ha="center", fontsize=8, color=INK2)
    ax.text(len(pilot) + len(ctrl) / 2, max(x) * 1.02, "Control phase", ha="center", fontsize=8, color=INK2)
    ax.set_ylabel("Lead time (days)", color=INK2, fontsize=9)
    ax.set_xlabel("Case", color=INK2, fontsize=9)
    ax.set_title("Individuals chart: lead time per new hire", loc="left", fontsize=11, color=INK, pad=14)
    style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="dmaic")
    p.add_argument("--data", default="data")
    p.add_argument("--out", default="reports")
    args = p.parse_args(argv)
    dd, out = Path(args.data), Path(args.out)
    dd.mkdir(parents=True, exist_ok=True)
    (out / "figures").mkdir(parents=True, exist_ok=True)

    base = data.generate()
    pilot = data.generate(60, improved=True, start="2026-02-02", span_days=89)
    ctrl = data.generate(60, seed=23, improved=True, start="2026-05-04", span_days=89)
    base.to_csv(dd / "baseline_cases.csv", index=False)
    pilot.to_csv(dd / "pilot_cases.csv", index=False)
    ctrl.to_csv(dd / "control_cases.csv", index=False)

    vs = a.value_stream(base)
    cap_b, cap_p = a.capability(base["lead_time_days"]), a.capability(pilot["lead_time_days"])
    pareto = a.delay_pareto(base)
    tests = a.root_cause_tests(base)
    reg = a.regression(base)
    cmp_ = a.compare(base, pilot)
    limits = a.imr_limits(pilot["lead_time_days"])
    viol_ctrl = a.rule_violations(ctrl["lead_time_days"], limits)
    pch = a.p_chart(pd.concat([pilot, ctrl]))
    cap_c = a.capability(ctrl["lead_time_days"])

    vsm_chart(vs, out / "figures" / "value_stream.png")
    before_after_chart(base, pilot, out / "figures" / "before_after.png")
    control_chart(pilot, ctrl, limits, out / "figures" / "control_chart.png")

    summary = {"capability_baseline": cap_b, "capability_pilot": cap_p, "capability_control": cap_c, "comparison": cmp_, "imr_limits": limits,
               "pce_baseline": a.process_cycle_efficiency(base), "regression_r2": reg.attrs["r2"]}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    cap = pd.DataFrame([{"phase": "baseline", **cap_b}, {"phase": "pilot", **cap_p}, {"phase": "control", **cap_c}])

    rep = [
        "# DMAIC results",
        "",
        "Generated by `python -m dmaic`. All data is generated (see `src/dmaic/data.py`).",
        "",
        "## Measure",
        "",
        f"Baseline: {len(base)} new hires in 2025. Process cycle efficiency {a.process_cycle_efficiency(base):.0%}: the rest of the lead time is waiting.",
        "",
        md(vs),
        "",
        "![value stream](figures/value_stream.png)",
        "",
        "Capability against the 15-day upper limit:",
        "",
        md(cap),
        "",
        "## Analyze",
        "",
        "Where the waiting happens:",
        "",
        md(pareto),
        "",
        "Root cause hypotheses:",
        "",
        md(tests),
        "",
        f"All causes in one regression (R² = {reg.attrs['r2']}):",
        "",
        md(reg),
        "",
        "## Improve",
        "",
        f"Pilot: {len(pilot)} new hires, February to April 2026.",
        "",
        md(pd.DataFrame([{"measure": k, "value": v} for k, v in cmp_.items()])),
        "",
        "![before and after](figures/before_after.png)",
        "",
        "## Control",
        "",
        f"Individuals chart limits from the pilot: centre {limits['center']}, UCL {limits['ucl']}, LCL {limits['lcl']}. "
        f"Control phase: {len(ctrl)} new hires, May to July 2026.",
        "",
        "Rule violations in the control phase:",
        "",
        md(viol_ctrl),
        "",
        "![control chart](figures/control_chart.png)",
        "",
        "Monthly share not ready on day one (p-chart):",
        "",
        md(pch),
        "",
    ]
    (out / "results.md").write_text("\n".join(rep), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(viol_ctrl.to_string(index=False))


if __name__ == "__main__":
    main()
