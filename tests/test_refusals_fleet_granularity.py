"""SPEC 3.2 at vac_version 0.2: three granularities, three key namespaces.

fleet-board-v1 recomputes per-(suite, member), per-suite, and whole-board.
Under 0.1 all three shared one key per field, and the pool comment said a
headline "may cite any honest grouping level". They are all honest, which is
the defect: a suite's 0.167 and one member's 1.0 both landed in
`detection_rate`, so a suite rate declared as 1.0 was accepted. Scope-per-check
cannot reach it, because the collision is INSIDE a single check.
"""
from __future__ import annotations

import json
import pathlib
import shutil

import pytest

from vac.verify import verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FLEET = (ROOT / "../reference-fleet/board/vac").resolve()
needs_fleet = pytest.mark.skipif(
    not (FLEET / "vac.json").is_file(),
    reason="reference-fleet checkout not present")


def _at(tmp_path, version: str, edit=None) -> pathlib.Path:
    b = tmp_path / "b"
    shutil.copytree(FLEET, b)
    p = b / "vac.json"
    m = json.loads(p.read_text())
    m["vac_version"] = version
    if edit is not None:
        edit(m["results"]["summary"])
    p.write_text(json.dumps(m, indent=1) + "\n")
    return b


@needs_fleet
def test_v01_semantics_are_untouched(tmp_path):
    """The accepted bundle keeps verifying under a verifier that implements
    the 0.2 namespaces. A compatibility change that quietly invalidated the
    entry it was protecting would be worse than the defect."""
    assert verify_bundle(_at(tmp_path, "0.1")) == []


@needs_fleet
def test_at_v01_a_member_rate_satisfies_a_suite_headline(tmp_path):
    """THE KILL-CHECK, and it must PASS.

    naive-contains has five members at 0.0, one at 1.0, and a suite rate of
    0.167. At 0.1 every one of those is in `detection_rate`, so republishing
    the suite's rate as a member's 0.0 is accepted. If this test ever fails,
    the 0.2 test below has stopped being evidence for the thing it names."""
    def cook(s):
        s["suites"]["naive-contains"]["detection_rate"] = 0.0
    assert verify_bundle(_at(tmp_path, "0.1", cook)) == []


@needs_fleet
def test_at_v02_a_member_rate_cannot_satisfy_a_suite_headline(tmp_path):
    """The same lie, refused, because suite_* and member_* are now separate
    namespaces. The declared 0.0 is a REAL number from the wrong grouping
    level, which is the whole class this fix closes."""
    def cook(s):
        s.clear()
        s["results"] = {"suite_detection_rate": 0.0}
    # Assert the STRICT-tier message, not merely that it refused. Dropping
    # the namespaces makes `suite_detection_rate` vanish from the pool, and
    # the leaf then refuses as "no check recomputes it" -- a pass for the
    # wrong reason. "recomputation gives" is what proves the key EXISTS and
    # holds only suite-level values.
    assert verify_bundle(_at(tmp_path, "0.2", cook)) == [
        "summary-outruns-checks: summary.results.suite_detection_rate: "
        "declares 0.0, recomputation gives one of [0.167, 1.0]"]


@needs_fleet
def test_at_v02_a_board_rate_cannot_satisfy_a_suite_headline(tmp_path):
    """The other direction of the same collision. 0.621 is the whole board's
    rate, honest and recomputed, and it is not any suite's."""
    def cook(s):
        s.clear()
        s["results"] = {"suite_detection_rate": 0.621}
    assert verify_bundle(_at(tmp_path, "0.2", cook)) == [
        "summary-outruns-checks: summary.results.suite_detection_rate: "
        "declares 0.621, recomputation gives one of [0.167, 1.0]"]


@needs_fleet
def test_at_v02_a_whole_board_check_still_merges_suites(tmp_path):
    """The RESIDUAL, pinned so nobody reads the profile fix as sufficient.

    This bundle has ONE check covering three suites, so `suite_detection_rate`
    still holds one value per suite: {0.167, 1.0}. Declaring naive's 0.167 as
    another suite's 1.0 is therefore still accepted. Closing that needs the
    ISSUER to emit one check per suite; the profile fix and the split are two
    halves of one repair, and this test fails the day the split lands."""
    def cook(s):
        s.clear()
        s["results"] = {"suite_detection_rate": 1.0}
    assert verify_bundle(_at(tmp_path, "0.2", cook)) == []
