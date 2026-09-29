"""SPEC 3.2 at vac_version 0.2: three granularities, three key namespaces.

fleet-board-v1 recomputes per-(suite, member), per-suite, and whole-board.
Under 0.1 all three shared one key per field, and the pool comment said a
headline "may cite any honest grouping level". They are all honest, which is
the defect: a suite's 0.167 and one member's 1.0 both landed in
`detection_rate`, so a suite rate declared as 1.0 was accepted.

Two repairs were needed and neither sufficed alone. The PROFILE separates the
granularities inside a check; the ISSUER emits one check per suite, because
scope is derived per check and a whole-board check leaves every suite's
values in one pool.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil

import pytest

from vac.registry import ISSUERS
from vac.verify import _summary_outruns, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"

# The fleet's own row in the table the registry generator reads, so the
# variable name, the sibling default and the bundle sub-path cannot drift from
# what vac/registry.py advertises.
_FLEET_CFG = next(c for c in ISSUERS
                  if c["repo"].rstrip("/").endswith("/reference-fleet"))


def _fleet_bundle(env) -> pathlib.Path:
    """`<VAC_FLEET_CHECKOUT or ../reference-fleet>/board/vac`, resolved the
    way vac/registry.py scan_issuer and the real-bundle tests in
    tests/test_verify.py resolve every issuer.

    This used to be a hardcoded ROOT/"../reference-fleet/board/vac". The
    registry advertises VAC_FLEET_CHECKOUT, and the checkout gate in
    tools/mutation_sweep.py accepts it when it names a real clone, so a run
    that set it passed the gate while the four tests below skipped. That is
    the silently smaller suite the gate exists to stop.
    """
    return ((ROOT / (env.get(_FLEET_CFG["checkout_env"])
                     or _FLEET_CFG["default_checkout"])).resolve()
            / _FLEET_CFG["bundles"])


FLEET = _fleet_bundle(os.environ)
needs_fleet = pytest.mark.skipif(
    not (FLEET / "vac.json").is_file(),
    reason=f"reference-fleet bundle not present at {FLEET}: clone "
           f"{_FLEET_CFG['repo']} to {_FLEET_CFG['default_checkout']} or set "
           f"{_FLEET_CFG['checkout_env']}")


def test_the_fleet_bundle_follows_its_checkout_variable(tmp_path,
                                                        monkeypatch):
    """The four fleet tests skip on every machine without the fleet, CI
    included, so none of them goes red if FLEET is hardcoded again. This
    re-executes the module under a set and an unset variable and reads the
    FLEET it computes, which does. The source is compiled and executed
    directly rather than imported, so the run leaves no bytecode behind."""
    var = _FLEET_CFG["checkout_env"]
    src = pathlib.Path(__file__)

    def fleet_under(value):
        if value is None:
            monkeypatch.delenv(var, raising=False)
        else:
            monkeypatch.setenv(var, value)
        ns = {"__name__": "_fleet_granularity_reexec", "__file__": str(src)}
        exec(compile(src.read_text(encoding="utf-8"), str(src), "exec"), ns)
        return ns["FLEET"]

    assert fleet_under(str(tmp_path)) == tmp_path.resolve() / "board" / "vac"
    assert fleet_under(None) == (
        ROOT / "../reference-fleet/board/vac").resolve()


def _pools(bundle: pathlib.Path) -> dict[str, set]:
    """The merged pool the summary is actually held to."""
    cap: list = []
    real = _summary_outruns
    import vac.verify as V
    V._summary_outruns = lambda s, p, v="0.1": (
        cap.append([dict(x) for x in p]), real(s, p, v))[1]
    try:
        verify_bundle(bundle)
    finally:
        V._summary_outruns = real
    by: dict[str, set] = {}
    for pool in cap[0]:
        for k, vs in pool.items():
            by.setdefault(k, set()).update(vs)
    return by


def _cooked(tmp_path, scope: str, field: str, value) -> pathlib.Path:
    b = tmp_path / "b"
    shutil.copytree(FLEET, b)
    p = b / "vac.json"
    m = json.loads(p.read_text())
    m["results"]["summary"][scope][field] = value
    p.write_text(json.dumps(m, indent=1) + "\n")
    return b


def test_at_v01_one_key_still_holds_every_grouping_level():
    """The kill-check, and it must PASS. fixtures/valid is a v0.1 bundle with
    a fleet check, and its `detection_rate` still merges member, suite and
    board values into {0.5, 0.75, 1.0}. If this ever fails, the 0.2 tests
    below have stopped being evidence for the thing they name."""
    pool = _pools(FIX / "valid")
    assert sorted(pool["detection_rate"]) == [0.5, 0.75, 1.0]
    assert not any(k.startswith(("member_", "suite_", "board_"))
                   for k in pool), "0.1 must keep the merged namespace"
    assert verify_bundle(FIX / "valid") == []


@needs_fleet
def test_at_v02_every_suite_rate_binds_to_exactly_one_value():
    """The POSITIVE evidence this replaces the old residual test with.

    That test asserted the hole was still open with one whole-board check.
    The issuer has since split, so the same property is now asserted from
    the other side: every published suite_* key is a SINGLETON, which is
    what makes the 0.2 badge mean something for this board."""
    pool = _pools(FLEET)
    suite_keys = {k: v for k, v in pool.items() if ".suite_" in k}
    assert suite_keys, "no suite-level pool keys at all"
    wide = {k: sorted(v) for k, v in suite_keys.items() if len(v) > 1}
    assert not wide, f"a suite claim can still be satisfied by another: {wide}"
    # and the member values are genuinely elsewhere, not merely absent
    assert sorted(pool["naive_contains.member_detection_rate"]) == [0.0, 1.0]
    assert sorted(pool["naive_contains.suite_detection_rate"]) == [0.167]


@needs_fleet
def test_at_v02_a_member_rate_cannot_satisfy_a_suite_headline(tmp_path):
    """naive-contains publishes 0.167 over five members at 0.0 and one at
    1.0. Declaring 1.0 is a REAL number from the wrong grouping level, which
    is the whole class this closes. The assertion is the strict-tier message:
    dropping the namespaces makes the key vanish and the leaf refuses as
    "no check recomputes it" instead, a pass for the wrong reason."""
    b = _cooked(tmp_path, "naive_contains", "suite_detection_rate", 1.0)
    assert verify_bundle(b) == [
        "summary-outruns-checks: summary.naive_contains.suite_detection_rate:"
        " declares 1.0, recomputation gives 0.167"]


@needs_fleet
def test_at_v02_another_suites_rate_cannot_satisfy_this_one(tmp_path):
    """Cross-CHECK separation, which only became testable once the issuer
    split. gradecore genuinely scores 1.0; naive-contains does not, and one
    suite's honest number must not satisfy another's claim."""
    b = _cooked(tmp_path, "naive_contains", "suite_detected", 1200)
    out = verify_bundle(b)
    assert out == [
        "summary-outruns-checks: summary.naive_contains.suite_detected: "
        "declares 1200, recomputation gives 200"], out


@needs_fleet
def test_at_v02_the_board_rate_cannot_satisfy_a_suite_headline(tmp_path):
    """The third granularity. Each split's board_* equals its own suite's
    value now, so this uses a cross-suite board number: 1.0 is gradecore's
    board rate, not naive-contains'."""
    b = _cooked(tmp_path, "naive_contains", "suite_false_alarm_rate", 0.5)
    out = verify_bundle(b)
    assert out and out[0].startswith(
        "summary-outruns-checks: summary.naive_contains"
        ".suite_false_alarm_rate:"), out
