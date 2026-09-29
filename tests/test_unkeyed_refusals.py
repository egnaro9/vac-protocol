"""The reverse enumeration held to what it claims to measure.

tools/unkeyed_refusals.py reads from the verifier's emission sites back to the
obligation entries that name them, and prints the residue: the codes no entry
names. The residue is a published figure, so the ways it can be quietly wrong
are the tests worth having. A code silently leaving the residue because
something other than an entry named it, an append counted as an emission but
never as an append, a scored share taken over a population the sweep does not
score: each of those reads as a smaller gap than there is.

Every test here drives the tool against a SYNTHETIC source and a SYNTHETIC
ledger. Nothing in this file reads vac/verify.py, obligations.json, SPEC.md or
the tests directory, so a mutant in the verifier cannot turn it red and it is
safe to run inside the mutation sweep's own detector. That is why it is not in
the sweep's DESELECT. A test that runs this tool over the COMMITTED verifier
does not have that property and belongs beside the other ledger tests, which
the sweep deselects for exactly this reason.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "unkeyed_refusals.py"

# Invented codes, so this file cannot bind a real refusal code to an obligation
# by naming it: the codes below are emitted by nothing the ledger reads.
# Five appends, one early return, one CLI print, over five codes.
SRC = (
    "def check(f, failures, e):\n"
    '    f.append("alpha-code: one")\n'
    '    f.append("beta-code: two")\n'
    '    failures.append("beta-code: two again")\n'
    '    f.append("beta-code: SYNTHETIC-EXCLUDED three")\n'
    '    f.append("gamma-code: four")\n'
    '    print(f"FAIL delta-code: {e}")\n'
    '    return ["epsilon-code: five"]\n'
)
# One append of the five carries the fragment, so the honest synthetic
# population is 5 raw / 4 scored.
SYNTHETIC_EXCLUDE = {"SYNTHETIC-EXCLUDED": (1, "synthetic, for these tests")}


def _tool():
    spec = importlib.util.spec_from_file_location("_unkeyed_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ledger(*pairs):
    """A ledger naming one refusal code per pair. `None` is an entry with no
    refusal site, which is how the ledger records an unmeasured obligation."""
    return {"obligations": [{"obligation_id": f"SPEC-{n:02d}",
                             "refusal_site": code}
                            for n, code in enumerate(pairs, 1)]}


def _measure(src=SRC, ledger=None, scored=True, exclude=None):
    mod = _tool()
    led = _ledger() if ledger is None else ledger
    if not scored:
        return mod.measure(src, led)
    keep, dropped = mod.scored_lines(
        src, SYNTHETIC_EXCLUDE if exclude is None else exclude)
    return mod.measure(src, led, keep, dropped)


def _codes(report):
    return sorted(r["code"] for r in report["unkeyed"]["by_code"])


# ── the residue itself ──────────────────────────────────────────────────────

def test_a_code_no_entry_names_is_in_the_residue():
    """The liveness case for the refusal below: with a ledger that names
    nothing, every emitted code is residue."""
    r = _measure()
    assert _codes(r) == ["alpha-code", "beta-code", "delta-code",
                         "epsilon-code", "gamma-code"]
    assert r["unkeyed"]["codes"] == 5
    assert r["unkeyed"]["emissions"] == 7


def test_naming_a_code_takes_it_out_of_the_residue():
    """The same source against a ledger that names two of its codes. If the
    residue does not shrink by exactly those two, it is not reading the
    ledger."""
    r = _measure(ledger=_ledger("alpha-code", "delta-code"))
    assert _codes(r) == ["beta-code", "epsilon-code", "gamma-code"]
    assert r["unkeyed"]["codes"] == 3
    # The three beta-code emissions and the one gamma-code and epsilon-code.
    assert r["unkeyed"]["emissions"] == 5


def test_an_entry_with_no_refusal_site_names_no_code():
    """An unmeasured obligation is the ledger disclosing a gap. Counting it as
    naming something would turn the disclosure into coverage."""
    r = _measure(ledger=_ledger(None, None, "alpha-code"))
    assert _codes(r) == ["beta-code", "delta-code", "epsilon-code",
                         "gamma-code"]
    assert r["ledger"]["entries"] == 3
    assert r["ledger"]["entries_naming_a_code"] == 1


def test_the_residue_is_counted_by_code_and_by_emission():
    """beta-code is emitted three times. One code, three emissions: a report
    that gave only one of those numbers would be quoted as the other."""
    r = _measure()
    beta = next(x for x in r["unkeyed"]["by_code"] if x["code"] == "beta-code")
    assert beta["sites"] == 3 and beta["appends"] == 3
    assert beta["lines"] == [3, 4, 5]


def test_a_code_an_entry_names_that_nothing_emits_is_reported():
    """The mismatch in the other direction. The checker refuses it as C2; a
    reverse enumeration that stayed silent about it would report a residue
    against a ledger it had already found wrong."""
    r = _measure(ledger=_ledger("alpha-code", "code-that-is-emitted-nowhere"))
    assert r["ledger"]["codes_named_but_never_emitted"] == [
        "code-that-is-emitted-nowhere"]


# ── the populations: emissions, appends, scored ─────────────────────────────

def test_the_return_and_the_print_are_emissions_and_not_appends():
    """Three populations, and the appends are the smallest. Merging them is
    how a figure taken over one gets quoted as the other."""
    r = _measure()
    assert r["population"]["by_kind"] == {"append": 5, "return": 1, "print": 1}
    assert r["population"]["emissions"] == 7
    assert r["unkeyed"]["emissions"] == 7
    assert r["unkeyed"]["appends"] == 5
    assert r["unkeyed"]["append_codes"] == 3


def test_the_scored_population_is_the_appends_minus_the_exclusions():
    """The sweep does not score the sites it declares unreachable, so a share
    over the raw appends would not be a share of anything it measures."""
    r = _measure()
    assert r["scored"] == {"population": 4, "excluded": 1, "unkeyed": 4,
                           "share": 1.0, "unkeyed_and_excluded": 1}


def test_the_scored_share_is_taken_over_the_scored_population():
    r = _measure(ledger=_ledger("beta-code"))
    # beta-code holds two of the four scored appends; alpha and gamma remain.
    assert r["scored"]["unkeyed"] == 2 and r["scored"]["share"] == 0.5


def test_an_exclusion_that_does_not_match_as_declared_is_refused():
    """Straight from the sweep: an exclusion matching fewer lines than
    declared inflates the denominator, one matching more shrinks it, and the
    share is silently wrong either way."""
    mod = _tool()
    with pytest.raises(ValueError, match="EXCLUDE does not match"):
        mod.scored_lines(SRC, {"SYNTHETIC-EXCLUDED": (2, "wrong arity")})


def test_the_two_readers_of_the_append_population_must_agree():
    """The emission sites are read from the AST and the scored population by
    line. A refusal only one of them can see makes both counts unsafe, so the
    report stops instead of printing a share over a population it cannot
    account for."""
    mod = _tool()
    keep, dropped = mod.scored_lines(SRC, SYNTHETIC_EXCLUDE)
    with pytest.raises(ValueError, match="do not agree"):
        mod.measure(SRC, _ledger(), {next(iter(keep))}, dropped)


def test_a_refusal_whose_code_cannot_be_read_stops_the_report():
    """Inherited from the extractor, and asserted here because this tool is
    the one that publishes a count: a site it cannot read must not simply be
    missing from the denominator."""
    mod = _tool()
    with pytest.raises(ValueError, match="line 2"):
        mod.measure('def check(f, reason):\n    f.append(reason)\n', _ledger())


# ── what the residue does not bound ─────────────────────────────────────────

def test_a_named_code_carrying_more_sites_than_entries_is_reported():
    """The deflation side. Those sites are outside the residue whatever they
    enforce, so a residue printed without them reads as a coverage bound."""
    r = _measure(ledger=_ledger("beta-code"))
    assert [(x["code"], x["sites"], x["entries"]) for x in r["shared"]] == [
        ("beta-code", 3, 1)]


def test_a_named_code_with_one_site_each_is_not_reported_as_shared():
    """The negative, so the row above is not simply every named code."""
    r = _measure(ledger=_ledger("alpha-code"))
    assert r["shared"] == []


def test_the_report_does_not_classify_the_residue():
    """Whether a residue code is an alias for a named rule, enforces a
    sentence carrying no MUST, or has no basis at all, is a reading of the
    specification. A tool that guessed would publish the guess as a
    measurement."""
    text = _tool().render(_measure())
    assert "is not derived here" in text
    for word in ("alias", "MUST"):
        assert word in text


# ── the command line ────────────────────────────────────────────────────────

def _write_tree(tmp_path, src=SRC, ledger=None):
    (tmp_path / "verify.py").write_text(src, encoding="utf-8")
    (tmp_path / "obligations.json").write_text(
        json.dumps(_ledger() if ledger is None else ledger), encoding="utf-8")
    return tmp_path / "verify.py", tmp_path / "obligations.json"


def _run(args):
    p = subprocess.run([sys.executable, str(TOOL)] + [str(a) for a in args],
                       capture_output=True, text=True, cwd=REPO)
    return p.returncode, p.stdout + p.stderr


def test_the_cli_leaves_out_a_share_it_cannot_support(tmp_path):
    """Another revision may not be the tree the sweep's EXCLUDE table
    describes. The emission counts still stand, so the run says which figure
    it is leaving out rather than printing a share it cannot support."""
    verify, ledger = _write_tree(tmp_path)
    rc, out = _run(["--verify", verify, "--ledger", ledger])
    assert rc == 0, out
    assert "scored population: not established" in out
    assert "5 codes over 7 of the 7 emissions" in out


def test_the_cli_writes_the_same_report_it_prints(tmp_path):
    verify, ledger = _write_tree(tmp_path, ledger=_ledger("alpha-code"))
    out_json = tmp_path / "report.json"
    rc, out = _run(["--verify", verify, "--ledger", ledger,
                    "--json", out_json])
    assert rc == 0, out
    doc = json.loads(out_json.read_text())
    assert doc["unkeyed"]["codes"] == 4
    assert f"{doc['unkeyed']['codes']} codes over" in out


def test_the_cli_refuses_a_source_it_cannot_read(tmp_path):
    verify, ledger = _write_tree(
        tmp_path, src="def check(f, reason):\n    f.append(reason)\n")
    rc, out = _run(["--verify", verify, "--ledger", ledger])
    assert rc == 2 and "ABORT" in out and "cannot be read" in out


# ── the pin, driven in process against the synthetic tree ───────────────────

def _pinned_main(tmp_path, raw, scored, ledger=None):
    """main() with the synthetic tree standing in for this one, so the pin
    check runs without reading the committed verifier."""
    mod = _tool()
    verify, led = _write_tree(tmp_path, ledger=ledger)
    mod.DEFAULT_VERIFY, mod.DEFAULT_LEDGER = verify, led
    mod.EXCLUDE = SYNTHETIC_EXCLUDE
    mod.EXPECT_RAW_SITES, mod.EXPECT_SCORED_SITES = raw, scored
    return mod.main([])


def test_the_pin_passes_when_the_population_is_the_pinned_one(tmp_path,
                                                              capsys):
    """Liveness for the refusal below."""
    assert _pinned_main(tmp_path, 5, 4) == 0
    assert "5 appends" in capsys.readouterr().out


def test_a_population_that_left_the_sweeps_pin_is_refused(tmp_path, capsys):
    """Every share in the report is taken over the sweep's population. If the
    population moved without anyone deciding it should, the report would print
    figures the mutation score does not share."""
    assert _pinned_main(tmp_path, 4, 3) == 2
    assert "the mutation sweep pins 4 / 3" in capsys.readouterr().err


def test_the_pin_is_not_applied_to_another_tree(tmp_path, capsys):
    """Pointing the tool at another revision must not measure it against this
    revision's pinned population."""
    mod = _tool()
    verify, led = _write_tree(tmp_path)
    mod.EXCLUDE = SYNTHETIC_EXCLUDE
    mod.EXPECT_RAW_SITES, mod.EXPECT_SCORED_SITES = 999, 999
    assert mod.main(["--verify", str(verify), "--ledger", str(led)]) == 0
