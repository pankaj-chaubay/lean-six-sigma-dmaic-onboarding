import numpy as np
import pandas as pd
import pytest

from dmaic import analysis as a
from dmaic import data
from dmaic.__main__ import main


@pytest.fixture(scope="module")
def base():
    return data.generate()


@pytest.fixture(scope="module")
def pilot():
    return data.generate(60, improved=True, start="2026-02-02", span_days=89)


def test_lead_time_is_sum_of_steps_in_baseline(base):
    cols = [c for c in base.columns if c.startswith(("pt_", "wt_"))]
    assert np.allclose(base[cols].sum(axis=1), base["lead_time_days"], atol=0.05)


def test_value_stream_matches_cases(base):
    vs = a.value_stream(base)
    assert vs["lead_time_days"].sum() == pytest.approx(base["lead_time_days"].mean(), abs=0.05)


def test_capability_on_known_numbers():
    x = pd.Series(np.r_[np.full(90, 10.0), np.full(10, 20.0)])
    c = a.capability(x, usl=15)
    assert c["share_over_usl"] == 0.1 and c["dpmo"] == 100000
    assert c["sigma_level"] == pytest.approx(1.28 + 1.5, abs=0.01)


def test_pareto_adds_up(base):
    p = a.delay_pareto(base)
    assert p["cumulative_share"].iloc[-1] == pytest.approx(1.0, abs=0.01)
    assert p.loc[0, "step"] == "Deliver equipment"


def test_planted_causes_are_found(base):
    t = a.root_cause_tests(base).set_index("hypothesis")
    assert t.loc["Cases with access rework take longer", "confirmed"]
    assert t.loc["Late requests are less often ready on day one", "confirmed"]
    r = a.regression(base).set_index("term")
    assert r.loc["access_rework", "days"] == pytest.approx(4.5, abs=1.5)


def test_pilot_is_better(base, pilot):
    c = a.compare(base, pilot)
    assert c["median_after"] < c["median_before"]
    assert float(c["lead_time_p_value"]) < 0.01


def test_imr_limits_formula():
    lim = a.imr_limits(pd.Series([10, 12, 11, 13, 12]))
    mr = np.mean([2, 1, 2, 1])
    assert lim["ucl"] == pytest.approx(11.6 + 2.66 * mr, abs=0.01)


def test_rules_find_shift_and_outlier():
    lim = {"center": 10, "ucl": 15, "lcl": 5}
    x = pd.Series([10, 9, 11, 30] + [12] * 8)
    v = a.rule_violations(x, lim)
    assert set(v["rule"]) == {"beyond control limit", "8 in a row on one side of the centre"}


def test_p_chart_limits_widen_for_small_months():
    df = pd.DataFrame({"case_id": range(40), "offer_accepted": ["2026-01-05"] * 30 + ["2026-02-05"] * 10, "ready_on_day_one": [True] * 32 + [False] * 8})
    g = a.p_chart(df).set_index("period")
    assert g.loc["2026-02", "ucl"] > g.loc["2026-01", "ucl"]


def test_cli(tmp_path):
    main(["--data", str(tmp_path / "d"), "--out", str(tmp_path / "r")])
    assert (tmp_path / "r" / "figures" / "control_chart.png").exists()
    assert "## Control" in (tmp_path / "r" / "results.md").read_text()
