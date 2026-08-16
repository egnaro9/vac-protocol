"""Every refusal in the crashkit-variance-v1 profile, pinned.

This profile exists because the evidence-closure rule caught a live bundle
pinning a variance report that no check read. Shipping it with untested
refusals would repeat the original mistake one level down, so each one is
mutation-checked: disabling the target `f.append(...)` must make the
corresponding test fail.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from vac.verify import _check_crashkit_variance

CHECK = {"profile": "crashkit-variance-v1", "artifact": "v.json"}

# Honest miniature: 4 tasks, one flaky, one hard-failing, one clean, one clean.
# tot_w = 8+4+2+1 = 15; mean = (8*0 + 4*0.5 + 2*1.0 + 1*0)/15 = 4/15 = 0.2667;
# ever-failed weight = 4+2 = 6 -> 0.4; flaky = 1 -> stability 0.75
HONEST = {
    "run": "mock:flaky", "n": 10,
    "per_task": [
        {"id": "a", "severity": "critical", "runs": 10, "passes": 10,
         "pass_rate": 1.0, "flaky": False, "ever_failed": False},
        {"id": "b", "severity": "high", "runs": 10, "passes": 5,
         "pass_rate": 0.5, "flaky": True, "ever_failed": True},
        {"id": "c", "severity": "med", "runs": 10, "passes": 0,
         "pass_rate": 0.0, "flaky": False, "ever_failed": True},
        {"id": "d", "severity": "low", "runs": 10, "passes": 10,
         "pass_rate": 1.0, "flaky": False, "ever_failed": False},
    ],
    "metrics": {"n_tasks": 4.0, "flaky_cases": 1.0, "stability": 0.75,
                "mean_vulnerability": 0.2667,
                "worst_case_vulnerability": 0.4},
}


def _run(tmp_path, mutate=None) -> list[str]:
    d = json.loads(json.dumps(HONEST))
    if mutate:
        mutate(d)
    (tmp_path / "v.json").write_text(json.dumps(d), encoding="utf-8")
    f: list[str] = []
    _check_crashkit_variance(tmp_path, CHECK, {}, f)
    return f


def test_the_honest_report_is_clean(tmp_path):
    """The control. Without it every refusal below could be firing for the
    wrong reason and the whole file would still look green."""
    assert _run(tmp_path) == []


def test_a_report_without_rows_is_refused(tmp_path):
    assert _run(tmp_path, lambda d: d.update(per_task=[])) == [
        "artifact-unparsable: v.json: no per_task[] array"]


def test_non_integer_counts_are_refused(tmp_path):
    assert _run(tmp_path, lambda d: d["per_task"][1].update(passes="5")) == [
        "artifact-unparsable: v.json: row 1: passes must be an integer"]


def test_passes_outside_the_run_count_is_refused(tmp_path):
    assert _run(tmp_path, lambda d: d["per_task"][1].update(passes=11)) == [
        "artifact-unparsable: v.json: row 1: passes 11 outside 0..runs 10"]


def test_a_severity_outside_the_frozen_table_is_refused(tmp_path):
    """The §4.3 forgery, one level down: re-casing the label on the failing
    rows drops their weight to 0 and the score divides to a false 0.0."""
    def recase(d):
        for r in d["per_task"]:
            if r["ever_failed"]:
                r["severity"] = r["severity"].capitalize()
    out = _run(tmp_path, recase)
    assert out == ["artifact-unparsable: v.json: severity 'High', 'Med' "
                   "outside the profile's frozen table "
                   "(none/low/med/high/critical)"]


@pytest.mark.parametrize("field,value,recomputed", [
    ("pass_rate", 0.9, 0.5),
    ("flaky", False, True),
    ("ever_failed", False, True),
])
def test_a_row_that_contradicts_its_own_counts_is_refused(
        tmp_path, field, value, recomputed):
    """A row's flags must follow from that row's own numbers. Taking them on
    faith is how a self-consistent-looking artifact carries a lie."""
    out = _run(tmp_path, lambda d: d["per_task"][1].update({field: value}))
    assert out == [f"raw-aggregate-mismatch: v.json: row 1: {field} "
                   f"declared {value!r}, recomputed {recomputed!r}"]


@pytest.mark.parametrize("metric,cooked,honest", [
    ("n_tasks", 9.0, 4.0),
    ("flaky_cases", 0.0, 1.0),
    ("stability", 1.0, 0.75),
    ("mean_vulnerability", 0.0, 0.2667),
    ("worst_case_vulnerability", 0.0, 0.4),
])
def test_each_headline_metric_must_recompute(tmp_path, metric, cooked,
                                             honest):
    out = _run(tmp_path, lambda d: d["metrics"].update({metric: cooked}))
    assert out == [f"raw-aggregate-mismatch: v.json: metrics.{metric} "
                   f"declared {cooked}, recomputed {honest}"]


def test_a_missing_metrics_object_is_refused(tmp_path):
    assert _run(tmp_path, lambda d: d.pop("metrics")) == [
        "artifact-unparsable: v.json: no metrics object"]


def test_a_declared_run_count_cannot_outrun_the_rows(tmp_path):
    assert _run(tmp_path, lambda d: d.update(n=99)) == [
        "raw-aggregate-mismatch: v.json: n declared 99, rows do not all "
        "carry that many runs"]
