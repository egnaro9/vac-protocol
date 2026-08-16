"""Every refusal in rows-aggregate-v1, plus the case that motivated it.

This profile exists because an outsider could not issue a bundle at all. Every
other profile hard-codes one of our own artifact shapes, so the registry was a
closed loop by construction. Walked the outsider path to confirm it: a fresh
repo, a plausible three-row results file, `vac draft`, every TODO filled in
diligently, closest-looking profile chosen. It died on `no per_kind object`.

So the tests here cover two things: that a stranger's own shape now verifies,
and that giving them that freedom did not buy it with a weaker guarantee.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from vac.verify import _check_rows_aggregate

CHECK = {
    "profile": "rows-aggregate-v1",
    "artifact": "r.json",
    "rows_key": "cases",
    "recompute": {
        "accuracy": {"op": "rate_true", "field": "passed", "round": 4},
        "n_cases": {"op": "count"},
        "worst": {"op": "min", "field": "score"},
    },
    "expect": {"accuracy": 0.6667, "n_cases": 3.0, "worst": 0.1},
}

DOC = {
    "schema": 1,
    "cases": [
        {"id": "c1", "passed": True, "score": 0.9},
        {"id": "c2", "passed": False, "score": 0.1},
        {"id": "c3", "passed": True, "score": 0.8},
    ],
}


def _run(tmp_path, doc=None, check=None) -> list[str]:
    (tmp_path / "r.json").write_text(
        json.dumps(doc if doc is not None else DOC), encoding="utf-8")
    f: list[str] = []
    _check_rows_aggregate(tmp_path, check or CHECK, {}, f)
    return f


def test_a_strangers_own_shape_verifies(tmp_path):
    """The control, and the whole point of the profile. Without this passing,
    every refusal below could be firing for the wrong reason."""
    assert _run(tmp_path) == []


def test_the_recipe_actually_recomputes(tmp_path):
    """Not just 'no failures': the pool must carry the recomputed values, or
    the summary rule downstream has nothing to hold a headline to."""
    f: list[str] = []
    (tmp_path / "r.json").write_text(json.dumps(DOC), encoding="utf-8")
    pool = _check_rows_aggregate(tmp_path, CHECK, {}, f)
    assert f == []
    assert pool == {"accuracy": [0.6667], "n_cases": [3.0], "worst": [0.1]}


def test_a_cooked_number_is_refused(tmp_path):
    check = {**CHECK, "expect": {**CHECK["expect"], "accuracy": 1.0}}
    assert _run(tmp_path, check=check) == [
        "summary-mismatch: accuracy: declared 1.0, recomputed 0.6667"]


def test_empty_rows_are_refused(tmp_path):
    """The vacuous pass this profile could most easily have shipped: every
    aggregate over an empty set is satisfiable, so an issuer with no data at
    all could otherwise declare anything."""
    assert _run(tmp_path, doc={**DOC, "cases": []}) == [
        "artifact-unparsable: r.json: rows[] is empty; no aggregate can be "
        "recomputed from nothing"]


def test_a_missing_recipe_is_refused(tmp_path):
    check = {k: v for k, v in CHECK.items() if k != "recompute"}
    out = _run(tmp_path, check=check)
    assert out and out[0].startswith(
        "schema-violation: results.checks[rows-aggregate-v1].recompute:"), out


def test_an_invented_op_is_refused_not_defaulted(tmp_path):
    """An unknown op must be named. Silently treating it as a no-op, or
    defaulting it, is how `.get(severity, 0)` handed an issuer the
    denominator elsewhere in this file."""
    check = {**CHECK, "recompute": {"accuracy": {"op": "whatever_i_want",
                                                 "field": "passed"}}}
    out = _run(tmp_path, check=check)
    assert out == ["schema-violation: recompute.accuracy.op: "
                   "'whatever_i_want' is not one of "
                   "count/sum/mean/rate_true/min/max"], out


def test_a_field_absent_from_a_row_is_named_with_its_index(tmp_path):
    doc = json.loads(json.dumps(DOC))
    del doc["cases"][1]["passed"]
    assert _run(tmp_path, doc=doc) == [
        "raw-aggregate-mismatch: r.json: recompute.accuracy reads 'passed', "
        "absent from row 1"]


@pytest.mark.parametrize("field,bad,op", [
    ("passed", "yes", "rate_true"),
    ("score", "high", "min"),
])
def test_a_field_of_the_wrong_type_is_refused_not_coerced(tmp_path, field,
                                                          bad, op):
    doc = json.loads(json.dumps(DOC))
    for c in doc["cases"]:
        c[field] = bad
    out = _run(tmp_path, doc=doc)
    assert any(f"is not the type op {op!r} requires" in x for x in out), out


def test_a_declared_number_the_recipe_ignores_is_refused(tmp_path):
    """You cannot declare a number and decline to say where it came from."""
    check = {**CHECK, "expect": {**CHECK["expect"], "invented": 42.0}}
    out = _run(tmp_path, check=check)
    assert "summary-mismatch: invented: declared but the recipe does not " \
           "recompute it" in out, out


def test_rows_at_the_top_level_need_no_rows_key(tmp_path):
    check = {k: v for k, v in CHECK.items() if k != "rows_key"}
    check = {**check, "recompute": {"n_cases": {"op": "count"}},
             "expect": {"n_cases": 3.0}}
    assert _run(tmp_path, doc=DOC["cases"], check=check) == []


def test_a_document_with_no_row_array_is_refused(tmp_path):
    out = _run(tmp_path, doc={"schema": 1, "cases": "not an array"})
    assert out == ["artifact-unparsable: r.json: no array of row objects at "
                   "'cases'"], out


# The recipe is issuer-supplied data, so every shape it can be malformed in
# needs a named refusal. The CI mutation floor caught all four of these as
# untested when the profile first landed, which is the floor doing its job on
# the person who wrote it.

def test_a_recipe_entry_that_is_not_an_object_is_refused(tmp_path):
    check = {**CHECK, "recompute": {"accuracy": "rate_true"}}
    assert _run(tmp_path, check=check) == [
        "schema-violation: recompute.accuracy: object required"]


def test_an_op_needing_a_field_without_one_is_refused(tmp_path):
    """`count` is the only op that reads no field. Any other op with no field
    would otherwise read None off every row."""
    check = {**CHECK, "recompute": {"accuracy": {"op": "mean"}}}
    assert _run(tmp_path, check=check) == [
        "schema-violation: recompute.accuracy.field: required for op 'mean'"]


def test_a_non_integer_round_is_refused(tmp_path):
    check = {**CHECK, "recompute": {"accuracy": {"op": "rate_true",
                                                 "field": "passed",
                                                 "round": "two"}}}
    assert _run(tmp_path, check=check) == [
        "schema-violation: recompute.accuracy.round: integer required"]


def test_a_missing_expect_is_refused(tmp_path):
    """A recipe with nothing declared against it recomputes numbers no one
    claimed, which is a check that cannot fail."""
    check = {k: v for k, v in CHECK.items() if k != "expect"}
    assert _run(tmp_path, check=check) == [
        "schema-violation: results.checks[rows-aggregate-v1].expect: "
        "declared numbers required"]
