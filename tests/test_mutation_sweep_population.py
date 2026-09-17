"""The sweep's population pins are enforced, both of them.

tools/mutation_sweep.py pins the refusal-site population as two numbers, raw
and scored, because the CI floor constrains a ratio and a denominator that
moves silently is a passing score about a different question. Only the raw
pin was ever read: the scored count was derived as raw minus the EXCLUDE hits,
so EXPECT_SCORED_SITES could hold any value at all and the run still went
ahead. These tests hold the scored pin to the same standard as the raw one.

They drive main() in-process against a SYNTHETIC source file, with the
detector stubbed out. Nothing here reads vac/verify.py, spawns a sweep, runs
pytest, or touches the sweep lock, so the file is safe to run inside a sweep's
own detector: a mutant in verify.py cannot turn it red, and it cannot hold the
lock the sweep needs. That is why it is not in DESELECT.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SWEEP = REPO / "tools" / "mutation_sweep.py"

# Five refusal-shaped lines, one of which the synthetic EXCLUDE removes, so the
# honest population is 5 raw / 4 scored.
SYNTHETIC_SRC = (
    "def check(f, failures):\n"
    '    f.append("alpha-code: one")\n'
    '    f.append("beta-code: two")\n'
    '    failures.append("gamma-code: three")\n'
    '    f.append("delta-code: SYNTHETIC-EXCLUDED four")\n'
    '    f.append("epsilon-code: five")\n'
)


def _load_sweep():
    spec = importlib.util.spec_from_file_location("_sweep_under_test", SWEEP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sweep(tmp_path, monkeypatch):
    """The sweep module pointed at the synthetic source, with a detector that
    records whether it was reached and never runs anything."""
    mod = _load_sweep()
    src = tmp_path / "verify.py"
    src.write_text(SYNTHETIC_SRC, encoding="utf-8")
    monkeypatch.setattr(mod, "SRC", src)
    monkeypatch.setattr(mod, "EXCLUDE", {
        "SYNTHETIC-EXCLUDED": (1, "excluded so raw and scored differ")})
    monkeypatch.setattr(mod, "EXPECT_RAW_SITES", 5)
    monkeypatch.setattr(mod, "EXPECT_SCORED_SITES", 4)
    calls = []

    def _detector(detector="all"):
        # Reaching the baseline means the population check passed. Report a
        # red baseline so main() stops there and never mutates anything.
        calls.append(detector)
        return True, "stubbed-detector"

    def _no_transaction(*a, **k):
        raise AssertionError("the sweep reached its mutation transaction")

    def _no_process(*a, **k):
        # observe() is replaced by name above. If main() ever reaches a real
        # detector some other way, that detector is `pytest tests/`, which
        # would collect this file and call main() again.
        raise AssertionError("the sweep launched a detector process")

    monkeypatch.setattr(mod, "observe", _detector)
    monkeypatch.setattr(mod, "_sweep_transaction", _no_transaction)
    monkeypatch.setattr(mod, "_run", _no_process)
    monkeypatch.setattr(mod.subprocess, "run", _no_process)
    mod.detector_calls = calls
    mod.synthetic_src = src
    return mod


def _main(mod, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["mutation_sweep.py", *args])
    return mod.main()


def test_a_wrong_scored_pin_aborts_before_the_baseline_runs(sweep, monkeypatch,
                                                            capsys):
    """The defect: raw matches, scored does not, and the run went ahead."""
    monkeypatch.setattr(sweep, "EXPECT_SCORED_SITES", 5)
    rc = _main(sweep, monkeypatch, "--detector", "liveness")
    err = capsys.readouterr().err
    assert rc == 2
    assert "refusal-site population is 5 raw / 4 scored; expected 5 / 5" in err
    assert sweep.detector_calls == [], (
        "the baseline ran, so the scored pin was not enforced")
    assert sweep.synthetic_src.read_text(encoding="utf-8") == SYNTHETIC_SRC


def test_the_right_scored_pin_passes_the_population_check(sweep, monkeypatch,
                                                          capsys):
    """Liveness for the test above: with both pins right, the run gets past the
    population check and reaches the (stubbed, red) baseline."""
    rc = _main(sweep, monkeypatch, "--detector", "liveness")
    err = capsys.readouterr().err
    assert rc == 2
    assert "refusal-site population" not in err
    assert "baseline is not clean (stubbed-detector)" in err
    assert sweep.detector_calls == ["liveness"]


def test_a_wrong_raw_pin_still_aborts_before_the_baseline_runs(sweep,
                                                               monkeypatch,
                                                               capsys):
    monkeypatch.setattr(sweep, "EXPECT_RAW_SITES", 6)
    rc = _main(sweep, monkeypatch, "--detector", "liveness")
    err = capsys.readouterr().err
    assert rc == 2
    assert "refusal-site population is 5 raw / 4 scored; expected 6 / 4" in err
    assert sweep.detector_calls == []


def test_expect_sites_derives_the_scored_count_for_a_one_off_run(sweep,
                                                                 monkeypatch,
                                                                 capsys):
    """--expect-sites measures another revision, whose scored count the pinned
    constant does not describe. The scored count is then raw minus the EXCLUDE
    hits, whose arity was already checked, so the pinned scored value is not
    consulted at all."""
    monkeypatch.setattr(sweep, "EXPECT_RAW_SITES", 999)
    monkeypatch.setattr(sweep, "EXPECT_SCORED_SITES", 999)
    rc = _main(sweep, monkeypatch, "--detector", "liveness",
               "--expect-sites", "5")
    err = capsys.readouterr().err
    assert rc == 2
    assert "refusal-site population" not in err
    assert sweep.detector_calls == ["liveness"]

    sweep.detector_calls.clear()
    rc = _main(sweep, monkeypatch, "--detector", "liveness",
               "--expect-sites", "4")
    err = capsys.readouterr().err
    assert rc == 2
    assert "expected 4 / 3" in err
    assert sweep.detector_calls == []


def test_the_committed_pins_agree_with_the_exclude_table():
    """Static, so it is red in the ordinary test job rather than only in the
    sweep job: the scored pin is the raw pin minus every declared exclusion.
    It reads only the sweep's own constants, never vac/verify.py."""
    mod = _load_sweep()
    excluded = sum(n for n, _ in mod.EXCLUDE.values())
    assert mod.EXPECT_SCORED_SITES == mod.EXPECT_RAW_SITES - excluded


# The ledger tools read vac/verify.py's emission sites. A test that runs them
# names these in its own source.
LEDGER_TOOLS = ("check_obligations", "build_obligations", "ledger_sources")


def test_a_test_that_reads_the_emission_sites_is_not_a_sweep_detector():
    """The sweep scores a mutant as caught when any test fails. A test that
    runs the ledger tools fails on a removed emission site because the
    extractor no longer sees it, not because a bundle got past the verifier,
    so it would score a refusal as tested when no behavioural test is."""
    mod = _load_sweep()
    readers = sorted(
        f"tests/{p.name}" for p in (REPO / "tests").glob("test_*.py")
        if p.name != pathlib.Path(__file__).name
        and any(t in p.read_text(encoding="utf-8") for t in LEDGER_TOOLS))
    assert readers, "the ledger's own tests should name the tools they run"
    assert [r for r in readers if r not in mod.DESELECT] == []
