"""The forgery replay and the fleet-half stamp fixture it traces.

paper/replay_forgeries.py is the source for V2-02's replay table: which
refusal lines of vac/verify.py at f59fb62 each hand-found forgery skipped, and for its
Table 1 counts. These tests hold five things to it.

  * The instrument. A line tracer that reports the wrong lines produces a table that
    reads correctly and means nothing, so the tracer is first run on a module whose
    executed lines are known.
  * The table. The expected rows are written out here, from the ledger, and compared
    with fresh traces rather than with the script's own ROWS, so editing an expectation
    in the script to match a changed result does not keep this file green. The printed
    table is read too, word by word, since that is what a reader quotes.
  * Table 1. The survivor counts come from paper/mutation.json through a join that
    must refuse a sweep measured on other bytes, and are held to values written here,
    line by line. The script's own exit code must also fail when the wrong lines
    survive, not only this file.
  * The fixture. fixtures/attack-fleet-stamp-deleted must be exactly what the generator
    makes, must differ from fixtures/valid by the one deleted key and its honest re-pin,
    and must be refused by the current verifier for the reason it exists to show.
    README.md's count of fixtures/ is checked against the directory.
  * Requirement 6 of the Packet 2 review. The generated fleet-half fixture, the same
    bundle with a wrong stamp (DEADBEEF, refused) and with the right one (the positive
    control), each replayed at f59fb62 and run through the current verifier.

The rows that trace f59fb62 need that revision's vac/verify.py, which this file reads
from the repository's git objects. A shallow clone does not have it, and those tests
skip with that reason; everything else here runs anywhere.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from vac.verify import verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
NEW = "attack-fleet-stamp-deleted"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    # registered first: the script's dataclass resolves its string annotations
    # through sys.modules, and an unregistered module is not there
    sys.modules[name] = mod
    # and with bytecode writing off. Importing fixtures/make_fixtures.py this way
    # otherwise leaves fixtures/__pycache__/ behind, and
    # tests/test_verify.py::test_fixtures_regenerate_byte_identically, which
    # compares every file under fixtures/ with a fresh generation, then fails on
    # the .pyc. CI runs pytest without PYTHONDONTWRITEBYTECODE.
    was, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = was
    return mod


rf = _load("replay_forgeries", ROOT / "paper" / "replay_forgeries.py")


def _pinned() -> bytes:
    try:
        return rf.read_pinned(None)
    except SystemExit as e:
        pytest.skip(f"vac/verify.py at f59fb62 is not readable here: {e}")


@pytest.fixture(scope="module")
def f59(tmp_path_factory):
    """The pinned verifier, loaded once, and its refusal sites."""
    data = _pinned()
    mod = rf.load(data, tmp_path_factory.mktemp("f59") / "vac" / "verify.py")
    text = data.decode("utf-8")
    sites = [n for n, ln in enumerate(text.splitlines(), 1) if rf.REFUSAL.match(ln)]
    return mod, sites, text


# --------------------------------------------------------------------------
# the instrument
PROBE = '''\
def verify_bundle(bundle):
    f = []
    if bundle == "a":
        f.append("took a")
    else:
        f.append(
            "took b")
    for k in ("x", "y"):
        if k in bundle:
            f.append(k)
    return f
'''


def test_the_tracer_reports_exactly_the_lines_that_ran(tmp_path):
    """Lines of a known module: the taken branch is reported, the untaken one is not,
    a multi-line statement is reported at its first line, and a condition that is
    evaluated but false is reported while its body is not. Every row of the replay
    table is one of those four shapes.

    Line 7 is the second line of a two-line call. CPython 3.12 to 3.14 report it too,
    because an instruction of the call sits on it; whether an interpreter does is not
    what the replay relies on, since it names statements by their first line, so it is
    allowed here and not required."""
    p = tmp_path / "probe.py"
    p.write_text(PROBE)
    mod = _load("probe_mod", p)
    out, hit = rf.trace(mod, "a")
    assert out == ["took a"]
    assert hit == {2, 3, 4, 8, 9, 11}, sorted(hit)
    out, hit = rf.trace(mod, "bx")
    assert out == ["took b", "x"]
    assert hit - {7} == {2, 3, 6, 8, 9, 10, 11}, sorted(hit)


def test_the_tracer_ignores_frames_of_other_files(tmp_path):
    """Only the pinned file's lines are recorded, so a helper called from another
    module cannot put its line numbers into the table under the pinned file's name."""
    helper = tmp_path / "helper.py"
    helper.write_text("def go():\n    x = 1\n    y = 2\n    return []\n")
    main = tmp_path / "main_mod.py"
    main.write_text("import helper\n\ndef verify_bundle(b):\n    return helper.go()\n")
    sys.path.insert(0, str(tmp_path))
    try:
        mod = _load("main_mod", main)
        _, hit = rf.trace(mod, None)
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("helper", None)
    assert hit == {4}, sorted(hit)


def test_the_tracer_restores_whatever_trace_was_installed(tmp_path):
    """A coverage tool or debugger installs its own trace function. The replay must
    hand it back, or everything after the replay runs untraced by the tool."""
    p = tmp_path / "probe.py"
    p.write_text(PROBE)
    mod = _load("probe_mod2", p)

    def other(frame, event, arg):
        return None

    previous = sys.gettrace()
    sys.settrace(other)
    try:
        rf.trace(mod, "a")
        assert sys.gettrace() is other
    finally:
        sys.settrace(previous)


# --------------------------------------------------------------------------
# the pin
def test_a_copy_that_is_not_the_pin_is_refused(tmp_path, capsys):
    """--verify-py exists so an export can run the replay; it must not become the way
    to run it on some other revision's bytes."""
    p = tmp_path / "verify.py"
    p.write_text("def verify_bundle(b):\n    return []\n")
    assert rf.main(["--verify-py", str(p)]) == 2
    assert "not the f59fb62 pin" in capsys.readouterr().err


def test_the_pin_names_f59fb62s_verify_py():
    """PIN_BLOB is read by id, so check here that it is the blob f59fb62 records for
    vac/verify.py, and that PIN_SHA256 is those bytes."""
    data = _pinned()
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    blob = subprocess.run(["git", "--no-optional-locks", "-C", str(ROOT), "rev-parse",
                           f"{rf.REV}:vac/verify.py"], capture_output=True, text=True,
                          env=env)
    if blob.returncode:
        pytest.skip(f"commit {rf.REV[:7]} is not in this clone: {blob.stderr.strip()}")
    assert blob.stdout.strip() == rf.PIN_BLOB
    assert hashlib.sha256(data).hexdigest() == rf.PIN_SHA256


def test_the_named_lines_and_the_population_are_f59fb62s(f59):
    _, sites, text = f59
    assert rf.check_source(text) == []
    assert len(sites) == 112


# --------------------------------------------------------------------------
# the table, written out from V2-02 and compared with fresh traces
DEADBEEF_FLEET = rf._set("evidence/results.json", fleet_commit="DEADBEEF")

# bundle -> (exit, refusal sites that must execute, lines that must, lines that must not).
# The ledger's rows name the refusal lines. The guards added to the three deletion
# rows (284 and 288, 374 and 383, and 255 not running) are this file's: they are what
# separates "the comparison was skipped by its guard" (forgery 4) from "the checker was
# never entered" (forgery 2).
LEDGER = {
    "tamper-summary-string": (0, set(), {1080}, {1085}),
    "attack-crashkit-severity": (0, set(), {617}, {618, 655, 1088}),
    "tamper-crashkit-severity": (1, {618, 655, 1088}, set(), set()),
    "tamper-stamp-deleted": (0, set(), {284, 288}, {285, 290}),
    NEW: (0, set(), {374, 383}, {376, 385}),
    "fleet_commit DEADBEEF": (1, {376, 385}, set(), set()),
    "tamper-check-deleted": (0, set(), set(), {255, 284, 288}),
}


@pytest.mark.parametrize("name", sorted(LEDGER))
def test_each_ledger_row_reproduces_at_f59fb62(name, f59, tmp_path):
    """One test per row of V2-02's replay table. An accepted forgery must execute no
    refusal site at all; a refused bundle must execute exactly the sites the ledger
    names, and nothing else."""
    mod, sites, _ = f59
    rc_want, fired_want, ran, not_ran = LEDGER[name]
    bundle = (DEADBEEF_FLEET(FIX, tmp_path / "b") if name == "fleet_commit DEADBEEF"
              else FIX / name)
    refusals, hit = rf.trace(mod, bundle)
    rc, _ = rf.exit_code(mod, bundle)
    assert rc == rc_want, refusals
    assert (refusals == []) == (rc == 0)
    assert {s for s in sites if s in hit} == fired_want
    assert ran <= hit, sorted(ran - hit)
    assert not (not_ran & hit), sorted(not_ran & hit)


def test_the_script_reproduces_every_row_and_says_so(f59, tmp_path, capsys):
    """The script's own comparison, end to end: every ledger row is one of its rows,
    and the command a reader runs exits 0 with no row differing."""
    labels = {r.label for r in rf.ROWS}
    assert set(LEDGER) <= labels, set(LEDGER) - labels
    assert {r.label for r in rf.ROWS if r.in_ledger} == set(LEDGER)
    assert rf.main(["--json", str(tmp_path / "out.json")]) == 0
    out = capsys.readouterr().out
    assert f"{len(rf.ROWS)} of {len(rf.ROWS)} rows reproduced" in out
    payload = json.loads((tmp_path / "out.json").read_text())
    assert payload["verify_py_sha256"] == rf.PIN_SHA256
    assert all(r["diffs"] == [] for r in payload["results"])
    assert payload["printed_table_diffs"] == []
    assert payload["sweep"]["diffs"] == [] and payload["sweep"]["caught"] == 37


# The printed status of a named line, as it appears in the table. The test reads
# the words itself, with its own pattern, so a table that prints the opposite of
# what the trace measured fails here even if the script's own read-back is gone.
STATUS_LINE = re.compile(r"  :(\d+) +(fired|did not fire|ran|did not run) ")


def _printed_rows(out: str) -> dict[str, list[str]]:
    """label -> that row's printed lines, from the script's stdout."""
    rows = {}
    for chunk in out.split("\n\n"):
        lines = chunk.split("\n")
        if "  [" in lines[0] and len(lines) > 1 and lines[1].startswith("  bundle: "):
            rows[lines[0].split("  [", 1)[0]] = lines
    return rows


def test_the_printed_table_says_what_the_ledger_says(f59, capsys):
    """V2-02's rows, read from the human-readable table section 2 quotes, not from
    the JSON. Every named line prints the status the ledger gives it, in the word for
    its kind (a refusal site fires, a guard runs), and the sites a row prints as fired
    are the sites it lists as executed. A report() that says "did not fire" for a line
    that fired passed every other test here."""
    _, sites, _ = f59
    assert rf.main([]) == 0
    out = capsys.readouterr().out
    rows = _printed_rows(out)
    assert set(LEDGER) <= set(rows), set(LEDGER) - set(rows)
    for name, (rc_want, fired_want, ran, not_ran) in LEDGER.items():
        block = rows[name]
        verdict = "PASS" if rc_want == 0 else "FAIL"
        assert any(ln.startswith(f"  verdict: {verdict}, exit {rc_want},")
                   for ln in block), (name, block)
        printed = {}
        for ln in block:
            m = STATUS_LINE.match(ln)
            if m:
                assert int(m.group(1)) not in printed, (name, ln)
                printed[int(m.group(1))] = m.group(2)
        want = {n: "fired" for n in fired_want}
        want.update({n: "fired" if n in sites else "ran" for n in ran})
        want.update({n: "did not fire" if n in sites else "did not run"
                     for n in not_ran})
        assert {n: printed.get(n) for n in want} == want, (name, block)
        listed = [ln for ln in block if ln.startswith("  refusal sites executed: ")]
        assert len(listed) == 1, (name, block)
        executed = listed[0].split(": ", 1)[1]
        assert executed == (", ".join(f":{s}" for s in sorted(fired_want))
                            or "none"), (name, executed)
        assert {n for n, w in printed.items() if w == "fired"} == fired_want, name
    # Table 1 as printed: each cell's word and each row's count
    for n, _, lines in rf.NAMES_THE_LIE:
        row = [ln for ln in out.split("\n") if ln.startswith(f"  forgery {n}, ")]
        assert len(row) == 1, (n, row)
        cells = {int(a): b for a, b in re.findall(r":(\d+) (caught|survived)", row[0])}
        assert cells == {ln: ("caught" if BASELINE[ln] else "survived")
                         for ln in lines}, row[0]
        if lines:
            assert row[0].endswith("; {} of {} survived".format(*TABLE1[n])), row[0]


def test_a_misprinted_table_fails_the_script(f59, monkeypatch, capsys):
    """The script's own read-back of its printed table can say "differs": swap the
    two status words of every refusal site in the rendered rows, exactly the defect
    that went unnoticed, and the run fails instead of printing "everything
    reproduced"."""
    real = rf.render
    swap = {"fired": "did not fire", "did not fire": "fired"}

    def misprinted(r):
        out = []
        for ln in real(r):
            m = STATUS_LINE.match(ln)
            if m and m.group(2) in swap:
                ln = ln[:9] + f"{swap[m.group(2)]:<13}" + ln[22:]
            out.append(ln)
        return out

    monkeypatch.setattr(rf, "render", misprinted)
    assert rf.main([]) == 1
    out = capsys.readouterr().out
    assert "the printed table disagrees with the measurements" in out
    head = "result: DIFFERS: "
    result = [ln[len(head):] for ln in out.split("\n") if ln.startswith(head)]
    assert len(result) == 1 and "printed table" in result[0].split(", "), result


# Expected messages from f59fb62 live at module level, not in the test bodies. The
# obligation ledger's extractor binds a test to an obligation when a refusal code is
# a literal in the test's own body, and these tests exercise the f59fb62 verifier,
# not the current one: they are no evidence that the current verifier enforces
# anything, so they must not bind. (This file does not run the ledger tools, and
# does not name them, so the sweep need not deselect it.)
F2_CONTROL = ["summary-outruns-checks: summary.fixed: declares 7777, "
              "no check recomputes it"]


def test_forgery_2s_headline_passes_only_because_other_checks_echo_it(f59, tmp_path):
    """Not a ledger row, but it bears on Table 1's row 2. With the certlab check
    deleted nothing recomputes summary.fixed, and :1088 still says nothing, because
    its fallback matches by bare value and other checks recompute a 2. Give the same
    bundle a headline no check echoes and :1088 refuses it at f59fb62."""
    mod, sites, _ = f59
    refusals, hit = rf.trace(mod, FIX / "tamper-check-deleted")
    assert refusals == [] and 1088 not in hit
    b = rf._summary("tamper-check-deleted", fixed=7777)(FIX, tmp_path / "b")
    refusals, hit = rf.trace(mod, b)
    assert refusals == F2_CONTROL
    assert {s for s in sites if s in hit} == {1088}


# Table 1, from the ledger: each refusal that names a forgery's lie, and whether the
# f59fb62 baseline sweep caught it
BASELINE = {1085: True, 1088: True, 618: True, 655: True,
            285: False, 290: True, 376: False, 385: True}
TABLE1 = {1: (0, 2), 2: (0, 0), 3: (0, 3), 4: (2, 4)}


def test_table1_counts_come_from_the_baseline_sweep(f59):
    """The survivor counts V2-02 proposes for Table 1, recomputed from
    paper/mutation.json through the script's join, and held to values written here."""
    _, sites, text = f59
    caught = rf.baseline(rf.SWEEP, text, sites)
    assert sum(caught.values()) == 37 and len(caught) == 112
    assert {n: caught[n] for n in BASELINE} == BASELINE
    got = {n: (sum(1 for ln in lines if not caught[ln]), len(lines))
           for n, _, lines in rf.NAMES_THE_LIE}
    assert got == TABLE1


def test_the_join_refuses_a_sweep_measured_on_other_bytes(f59, tmp_path):
    """Line keys name statements only in the bytes they were measured on. A sweep
    whose lines are shifted by one, or whose refusal codes sit on the wrong lines, must
    be refused rather than joined."""
    _, sites, text = f59
    rows = json.loads(rf.SWEEP.read_text())
    shifted = tmp_path / "shifted.json"
    shifted.write_text(json.dumps([{**r, "line": r["line"] + 1} for r in rows]))
    with pytest.raises(ValueError, match="refusal lines"):
        rf.baseline(shifted, text, sites)
    swapped = [dict(r) for r in rows]
    a = next(r for r in swapped if r["line"] == 285)
    b = next(r for r in swapped if r["line"] == 1085)
    assert a["reason"] != b["reason"]
    a["reason"], b["reason"] = b["reason"], a["reason"]
    codes = tmp_path / "codes.json"
    codes.write_text(json.dumps(swapped))
    with pytest.raises(ValueError, match="refusal code is not on their line"):
        rf.baseline(codes, text, sites)


def _run_on_sweep(rows, tmp_path, name):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(rows))
    rc = rf.main(["--sweep", str(path), "--json", str(tmp_path / f"{name}.out.json")])
    return rc, json.loads((tmp_path / f"{name}.out.json").read_text())


def test_the_script_fails_when_the_wrong_lines_survive(f59, tmp_path, capsys):
    """The script's own exit code, not only this file, must notice an archive in
    which the wrong lines survived. Two archives that keep every Table 1 count and
    pass the join: :376 and :385 swapping results (both rows carry the same refusal
    code, so the join cannot tell them apart), and every row inverted (forgery 4
    stays at 2 of 4). Each must exit 1 with forgery 4's row marked as differing."""
    rows = json.loads(rf.SWEEP.read_text())
    a = next(r for r in rows if r["line"] == 376)
    b = next(r for r in rows if r["line"] == 385)
    assert a["reason"] == b["reason"]
    assert (a["caught"], b["caught"]) == (False, True)
    for k in ("caught", "how"):
        a[k], b[k] = b[k], a[k]
    inverted = [{**r, "caught": not r["caught"]}
                for r in json.loads(rf.SWEEP.read_text())]
    for name, bad in (("swapped", rows), ("inverted", inverted)):
        rc, payload = _run_on_sweep(bad, tmp_path, name)
        out = capsys.readouterr().out
        assert rc == 1, (name, out)
        f4 = payload["table1"][3]
        assert f4["forgery"] == 4 and (f4["survived"], f4["of"]) == (2, 4), f4
        assert any("survivors differ from V2-02" in d for d in f4["diffs"]), f4
        assert payload["sweep"]["diffs"], name
        assert "result: DIFFERS" in out, name


def test_the_comparison_can_report_a_difference(tmp_path):
    """A comparator that has never said "differs" is not known to work. Drive it with
    a stand-in verifier that accepts everything: the rows that expect a refusal, or a
    line that must run, must each come back with a named difference."""
    stub = tmp_path / "stub.py"
    stub.write_text("def verify_bundle(b):\n    return []\n\n"
                    "def main(argv):\n    return 0\n")
    mod = _load("stub_verify", stub)
    results = rf.replay(mod, [], FIX, tmp_path)
    by = {r["label"]: r["diffs"] for r in results}
    assert by["tamper-crashkit-severity"], by
    assert by["fleet_commit DEADBEEF"], by
    assert any(":1080 did not execute" in d for d in by["tamper-summary-string"])
    assert any(":374 did not execute" in d for d in by[NEW])


# --------------------------------------------------------------------------
# the fixture
def _files(d: pathlib.Path) -> dict[str, bytes]:
    return {p.relative_to(d).as_posix(): p.read_bytes()
            for p in sorted(d.rglob("*")) if p.is_file()}


def test_the_fleet_half_fixture_is_what_the_generator_makes():
    """Byte for byte, from the generator's own functions. The whole-tree regeneration
    test in test_verify.py covers this too; this one fails with the fixture's name."""
    gen = _load("make_fixtures_for_replay", FIX / "make_fixtures.py")
    valid = gen.valid_bundle()
    want = {k: v.encode("utf-8") for k, v in gen.tampered_variants(valid)[NEW].items()}
    assert _files(FIX / NEW) == want


def test_the_fleet_half_fixture_differs_from_valid_by_one_key_and_its_repin():
    """What makes it the fleet half of the stamp forgery and nothing else: the
    aggregate lost fleet_commit, the manifest re-pinned that artifact honestly, and
    every other byte is fixtures/valid's."""
    new, valid = _files(FIX / NEW), _files(FIX / "valid")
    assert set(new) == set(valid)
    changed = {k for k in new if new[k] != valid[k]}
    assert changed == {"evidence/results.json", "vac.json"}
    agg_new = json.loads(new["evidence/results.json"])
    agg_valid = json.loads(valid["evidence/results.json"])
    assert "fleet_commit" not in agg_new
    agg_valid.pop("fleet_commit")
    assert agg_new == agg_valid
    man_new, man_valid = json.loads(new["vac.json"]), json.loads(valid["vac.json"])
    pin = {e["path"]: e["sha256"] for e in man_new["evidence"]}
    assert pin["evidence/results.json"] == hashlib.sha256(
        new["evidence/results.json"]).hexdigest()
    for e in man_valid["evidence"]:
        if e["path"] == "evidence/results.json":
            e["sha256"] = pin["evidence/results.json"]
    assert man_new == man_valid


def test_the_fleet_half_fixture_stays_outside_the_tamper_glob():
    """Named attack- so the fixture detector's population is unchanged: the sweep and
    tools/fixture_corpus_score.py read fixtures/tamper-* only. Checked by content, not
    by name: a check on the name is true by the constant NEW, and a copy of this
    forgery under any tamper-* name would pass it. What makes a bundle this forgery is
    an aggregate row with no fleet_commit, so no tamper-* bundle may carry one."""
    assert "fleet_commit" not in json.loads(
        (FIX / NEW / "evidence/results.json").read_text())
    stampless = []
    for d in sorted(FIX.glob("tamper-*")):
        agg = d / "evidence/results.json"
        try:
            row = json.loads(agg.read_text())
        except (OSError, ValueError):
            continue  # no aggregate to carry the forgery
        if isinstance(row, dict) and "fleet_commit" not in row:
            stampless.append(d.name)
    assert stampless == []
    assert (FIX / NEW / "vac.json").is_file()


# README.md's sentence that counts fixtures/, read with the counts left as groups
README_COUNTS = re.compile(
    r"`fixtures/` is the verifier's own evidence: (\S+) bundles, namely (\S+) "
    r"valid synthetic bundle \(one check per profile\), (\S+) clean v0\.2 "
    r"twin-arms control, (\S+) tampered variants \(`tamper-\*`\) and (\S+) "
    r"forgeries an earlier verifier accepted \(`attack-\*`")
SMALL = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9}


def test_the_readme_counts_the_fixtures_it_has():
    """The README once said "sixteen tampered variants" while fixtures/ held 23, and
    nothing noticed. Here every count in that sentence is compared with the
    directory: a bundle is a directory with a vac.json, and each kind is named by its
    directory. Every bundle must be of a kind the sentence names, so a new kind of
    fixture fails this until the sentence covers it."""
    text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    m = README_COUNTS.search(text)
    assert m, "README.md's fixture-count sentence is gone or reworded"
    said = [SMALL[g.lower()] if g.lower() in SMALL else int(g) for g in m.groups()]
    bundles = sorted(d.name for d in FIX.iterdir() if (d / "vac.json").is_file())
    kinds = {
        "valid": [n for n in bundles if n == "valid"],
        "twin": [n for n in bundles if n == "v02-twin-arms"],
        "tamper": [n for n in bundles if n.startswith("tamper-")],
        "attack": [n for n in bundles if n.startswith("attack-")],
    }
    named = sorted(n for group in kinds.values() for n in group)
    assert named == bundles, sorted(set(bundles) - set(named))
    have = [len(bundles)] + [len(kinds[k]) for k in ("valid", "twin", "tamper",
                                                     "attack")]
    assert said == have, dict(zip(("bundles", "valid", "twin", "tamper", "attack"),
                                  zip(said, have)))


# the current verifier, on every forgery the replay uses: each one must stay refused,
# for the reason its fix added
NOW = {
    "tamper-summary-string": [
        "summary-outruns-checks: summary.fixed: declares '9999' as a string; a "
        "numeric headline must be a JSON number so it can be recomputed"],
    "tamper-check-deleted": [
        "evidence-unchecked: evidence/bundle.json: listed in evidence but read by "
        "no check"],
    "attack-crashkit-severity": [
        "artifact-unparsable: evidence/eval_run.json: severity 'Critical', 'Med' "
        "outside the profile's frozen table (none/low/med/high/critical)"],
    "tamper-crashkit-severity": [
        "artifact-unparsable: evidence/eval_run.json: severity 'Critical', 'Med' "
        "outside the profile's frozen table (none/low/med/high/critical)"],
    "tamper-stamp-deleted": [
        "stamp-mismatch: taskset_hash: named by protocol.hashes but absent from "
        "evidence/bundle.json",
        "stamp-mismatch: prompt_hash: named by protocol.hashes but absent from "
        "evidence/bundle.json",
        "stamp-mismatch: harness_commit: protocol declares issuer_commit but "
        "evidence/bundle.json carries no harness_commit"],
    NEW: [
        "stamp-mismatch: fleet_commit: protocol declares issuer_commit but the "
        "aggregate row carries no fleet_commit",
        "stamp-mismatch: hashes.fleet_commit: named by protocol.hashes but absent "
        "from the aggregate row"],
}


@pytest.mark.parametrize("name", sorted(NOW))
def test_the_current_verifier_refuses_each_forgery_by_name(name):
    """CI's liveness loop checks exit codes over tamper-* only, so it neither sees the
    attack- fixtures nor notices a refusal that changed its reason."""
    assert verify_bundle(FIX / name) == NOW[name]


# --------------------------------------------------------------------------
# requirement 6 of the Packet 2 review: the replay on the new fleet-half
# fixture, a negative case that is refused because its stamp is wrong, and a
# positive control that carries the right one. All three start from the generated
# bytes of fixtures/attack-fleet-stamp-deleted; the two derived states put
# fleet_commit back at one value and re-pin evidence/results.json honestly.
FLEET_DEADBEEF = [  # worded the same at f59fb62 and now
    "stamp-mismatch: fleet_commit: protocol f1e2d3c, artifact DEADBEEF",
    "stamp-mismatch: hashes.fleet_commit: protocol f1e2d3c, artifact DEADBEEF"]
# state -> (fleet_commit written, exit at f59fb62, refusals at f59fb62, refusal
# sites that fire at f59fb62, refusals from the current verifier)
STAMP_STATES = {
    "absent, the fixture as generated": (None, 0, [], set(), NOW[NEW]),
    "wrong, DEADBEEF": ("DEADBEEF", 1, FLEET_DEADBEEF, {376, 385}, FLEET_DEADBEEF),
    "right, f1e2d3c": ("f1e2d3c", 0, [], set(), []),
}


def _fleet_stamp(value, dest: pathlib.Path) -> pathlib.Path:
    """The generated fleet-half fixture itself for None; otherwise a copy of it with
    fleet_commit set to `value` and its artifact re-pinned."""
    if value is None:
        return FIX / NEW
    shutil.copytree(FIX / NEW, dest)
    art = dest / "evidence/results.json"
    agg = json.loads(art.read_text())
    agg["fleet_commit"] = value
    art.write_text(json.dumps(agg, indent=1) + "\n")
    man = json.loads((dest / "vac.json").read_text())
    for e in man["evidence"]:
        if e["path"] == "evidence/results.json":
            e["sha256"] = hashlib.sha256(art.read_bytes()).hexdigest()
    (dest / "vac.json").write_text(json.dumps(man, indent=1) + "\n")
    return dest


# The value half of each fleet stamp guard at f59fb62: the second line of :374's
# and of :383's condition, evaluated only when the key exists
VALUE_COMPARISONS = {375: 'and agg["fleet_commit"] != ic:',
                     384: 'and hashes["fleet_commit"] != agg["fleet_commit"]):'}


@pytest.mark.parametrize("state", sorted(STAMP_STATES))
def test_the_fleet_half_fixture_replays_by_stamp_at_f59fb62(state, f59, tmp_path):
    """The replay's own trace and exit code on the new fixture and its two
    stamped variants. Both guards (:374, :383) are reached in all three states. The
    wrong stamp is refused by exactly :376 and :385. The right one passes with
    neither firing, and its value comparisons (:375, :384) ran, so it passed by
    comparing. The new fixture, with no stamp, passes too, and its value
    comparisons never ran: the guard's key test stopped them. That is the forgery. At
    f59fb62 a deleted stamp and a correct one get the same verdict, and only the trace
    tells them apart.

    :375 and :384 are continuation lines of a two-line condition. CPython 3.12.12,
    3.13.15 and 3.14.6 all report them when the second operand runs (measured)."""
    mod, sites, text = f59
    value, rc_want, then, fired_want, _ = STAMP_STATES[state]
    src = text.splitlines()
    assert {n: src[n - 1].strip() for n in VALUE_COMPARISONS} == VALUE_COMPARISONS
    bundle = _fleet_stamp(value, tmp_path / "b")
    if value is None:
        assert bundle == FIX / NEW  # the fixture's own bytes, not a copy
    refusals, hit = rf.trace(mod, bundle)
    rc, printed = rf.exit_code(mod, bundle)
    assert (rc, refusals, printed) == (rc_want, then, then)
    assert {s for s in sites if s in hit} == fired_want
    assert {374, 383} <= hit, sorted({374, 383} - hit)
    compared = {n for n in VALUE_COMPARISONS if n in hit}
    assert compared == (set() if value is None else set(VALUE_COMPARISONS)), compared


@pytest.mark.parametrize("state", sorted(STAMP_STATES))
def test_the_fleet_half_fixture_by_stamp_now(state, tmp_path):
    """The same three states at the current verifier, which needs no git history and
    so also runs in a shallow clone: the missing stamp and the wrong one are refused,
    each for its own reason, and only the right one verifies clean."""
    value, _, _, _, now = STAMP_STATES[state]
    assert verify_bundle(_fleet_stamp(value, tmp_path / "b")) == now


def test_the_fleet_half_fixture_passes_once_its_stamp_is_restored(tmp_path):
    """The refusal above is the missing stamp and nothing else: put fleet_commit back
    at the pinned value, re-pin, and the same bundle verifies clean."""
    b = tmp_path / "b"
    shutil.copytree(FIX / NEW, b)
    art = b / "evidence/results.json"
    agg = json.loads(art.read_text())
    agg["fleet_commit"] = "f1e2d3c"
    art.write_text(json.dumps(agg, indent=1) + "\n")
    man = json.loads((b / "vac.json").read_text())
    for e in man["evidence"]:
        if e["path"] == "evidence/results.json":
            e["sha256"] = hashlib.sha256(art.read_bytes()).hexdigest()
    (b / "vac.json").write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(b) == []
