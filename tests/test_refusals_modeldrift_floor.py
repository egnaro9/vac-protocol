"""SPEC 3.5 at vac_version 0.2: the declared reliability floor.

A rate limit, timeout or provider outage makes a call ABSENT, not wrong.
Scoring it publishes the provider's bad morning as the model getting dumber.
The issuer learned this the expensive way: model-drift kept the floor only in
its dashboard JS, and RESULTS.md published a Google outage as three Gemini
regressions of -37.1 and -94.3 points while the chart above it correctly
showed nothing (modeldrift/board.py:32).

At 0.1 this profile took the latest point unconditionally, which is exactly
that bug. At 0.2 the bundle DECLARES its floor, bounded and pinned across
every surface that publishes standings derived with it, because an
issuer-chosen number driving a recomputation is what 3.1 calls
non-authoritative.
"""
from __future__ import annotations

import json
import pathlib
import shutil

import pytest

from vac.verify import _REL_FLOOR_RANGE, _sha256, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
BASE = FIX / "v02-twin-arms"        # a 0.2 bundle whose floor is declared
MET = "evidence/metrics.json"
STAND = "evidence/standings.json"
MD = "evidence/RESULTS.md"


def _bundle(tmp_path) -> pathlib.Path:
    b = tmp_path / "b"
    shutil.copytree(BASE, b)
    return b


def _read(b, rel):
    return json.loads((b / rel).read_text())


def _write(b, rel, obj) -> None:
    (b / rel).write_text(json.dumps(obj, indent=1) + "\n")
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    for e in man["evidence"]:
        if e["path"] == rel:
            e["sha256"] = _sha256(b / rel)
    h = man.get("protocol", {}).get("hashes", {})
    if rel == MET and "metrics_sha256" in h:
        h["metrics_sha256"] = _sha256(b / rel)
    man_path.write_text(json.dumps(man, indent=1) + "\n")


def _floor(b) -> float:
    return _read(b, MET)["rel_floor"]


def test_the_declared_floor_bundle_verifies(tmp_path):
    """The control. Every point here is reliable, so nothing is disqualified
    and the floor changes no standing: it only has to be declared, bounded
    and consistent."""
    assert verify_bundle(_bundle(tmp_path)) == []


def test_a_v01_bundle_is_untouched_by_any_of_this():
    """0.1 keeps the rule it was accepted under. No floor is required, none
    is read, and the latest point still counts unconditionally."""
    assert verify_bundle(FIX / "valid") == []
    man = json.loads((FIX / "valid" / "vac.json").read_text())
    assert man["vac_version"] == "0.1"
    assert not any("rel_floor" in c for c in man["results"]["checks"])


def test_an_undeclared_floor_is_refused(tmp_path):
    b = _bundle(tmp_path)
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    for c in man["results"]["checks"]:
        c.pop("rel_floor", None)
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(b) == [
        "schema-violation: rel_floor: a 0.2 modeldrift-board-v1 check MUST "
        "declare the reliability floor its standings were derived under"]


@pytest.mark.parametrize("bad", [True, "0.5", None, [0.5]])
def test_a_non_numeric_floor_is_refused(tmp_path, bad):
    """`True` is in here deliberately: bool is a subclass of int, so a naive
    isinstance check would accept it and then compare True >= 0.0."""
    b = _bundle(tmp_path)
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    for c in man["results"]["checks"]:
        if c.get("profile") == "modeldrift-board-v1":
            c["rel_floor"] = bad
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    out = verify_bundle(b)
    assert out and out[0].startswith("schema-violation: rel_floor:"), out
    if bad is not None:
        assert "must be a number" in out[0], out


@pytest.mark.parametrize("bad", [-0.1, 0.95, 1.0, 42])
def test_a_floor_outside_the_admissible_range_is_refused(tmp_path, bad):
    """A floor an issuer can raise without bound is a dial for disqualifying
    an inconvenient run until the standing it wants is the one that shows."""
    lo, hi = _REL_FLOOR_RANGE
    assert not (lo <= bad <= hi)
    b = _bundle(tmp_path)
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    for c in man["results"]["checks"]:
        if c.get("profile") == "modeldrift-board-v1":
            c["rel_floor"] = bad
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    out = verify_bundle(b)
    assert out == [
        f"schema-violation: rel_floor: {bad} is outside the admissible range "
        f"[{lo}, {hi}]. A floor an issuer can raise without bound is a dial "
        "for disqualifying an inconvenient run"], out


def test_the_dashboard_metrics_must_carry_the_same_floor(tmp_path):
    """The surface that drifted last time. The floor lived only in the
    dashboard's own data once, and the published table disagreed with it."""
    b = _bundle(tmp_path)
    met = _read(b, MET)
    met["rel_floor"] = 0.4
    _write(b, MET, met)
    out = verify_bundle(b)
    assert any(r.startswith("raw-aggregate-mismatch: metrics.json: rel_floor")
               for r in out), out


def test_the_published_table_must_state_the_floor(tmp_path):
    b = _bundle(tmp_path)
    md_path = b / MD
    md_path.write_text(md_path.read_text().replace(
        f"floor** is {_floor(b)}", "floor** is 0.4", 1))
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    for e in man["evidence"]:
        if e["path"] == MD:
            e["sha256"] = _sha256(md_path)
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    out = verify_bundle(b)
    assert any("RESULTS.md" in r and "reliability floor" in r
               for r in out), out


def _disqualify_latest(b) -> tuple[str, dict, dict]:
    """Drop the latest point of the first multi-point series below the floor.

    Returns (model id, the now-disqualified point, the point that becomes the
    qualifying standing)."""
    met = _read(b, MET)
    floor = met["rel_floor"]
    for mid, pts in met["series"].items():
        if len(pts) >= 2:
            pts[-1]["reliability"] = round(floor - 0.1, 4)
            _write(b, MET, met)
            return mid, pts[-1], pts[-2]
    raise AssertionError("fixture has no multi-point series")


def test_an_unconditional_latest_standing_refuses_when_it_is_below_floor(
        tmp_path):
    """THE CASE THIS EXISTS FOR. The standings still name the latest point,
    which is what 0.1 would have computed. At 0.2 that run is disqualified,
    so the declared standing is the outage rather than the model."""
    b = _bundle(tmp_path)
    mid, dead, _ = _disqualify_latest(b)
    out = verify_bundle(b)
    # The standing moves back to the last qualifying point. Asserting on
    # `acc` would be wrong here and pass only by luck elsewhere: this
    # fixture's two points share an accuracy, so the observable movement is
    # the DATE. The disqualified run is what `latest_observed` must carry.
    assert any(f"standings.json: {mid}: when declared "
               f"{dead['t'][:10]!r}, recomputed" in r for r in out), out
    assert any("latest_observed declared" in r and "'qualified': False" in r
               for r in out), out


def test_the_floored_standing_is_what_verifies(tmp_path):
    """The same bundle, with the standings recomputed the way the issuer's
    documented rule says: the latest QUALIFYING point, and a latest-observed
    block that keeps the disqualified run visible."""
    b = _bundle(tmp_path)
    mid, dead, alive = _disqualify_latest(b)
    st = _read(b, STAND)
    for row in st["rows"]:
        if row["id"] != mid:
            continue
        row["when"] = (alive.get("t") or "")[:10] or None
        row["acc"] = alive.get("acc")
        row["latest_observed"] = {
            "when": (dead.get("t") or "")[:10] or None,
            "acc": dead.get("acc"),
            "reliability": dead.get("reliability"),
            "acc_spread": dead.get("acc_spread"),
            "qualified": False,
        }
    _write(b, STAND, st)
    out = verify_bundle(b)
    # the standings row for the floored model no longer disagrees
    assert not any(f"standings.json: {mid}: acc declared" in r
                   for r in out), out


def test_the_latest_observed_block_is_required_even_when_disqualified(
        tmp_path):
    """Publishing only the qualifying standing would let a bundle erase a
    collapse, which is the same defect facing the other way: a reader could
    not tell a stable model from an unreachable one."""
    b = _bundle(tmp_path)
    st = _read(b, STAND)
    for row in st["rows"]:
        row.pop("latest_observed", None)
    _write(b, STAND, st)
    out = verify_bundle(b)
    assert any("latest_observed" in r for r in out), out
