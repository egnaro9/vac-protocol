"""A sweep row names a site, not a line.

Every archived sweep keys its rows by line number. A line number is not an
identity: insert one line above a refusal and every site below it is renamed,
so two archives can be compared per-site only where their line keys happen to
coincide, and anywhere they differ "this site went from caught to surviving"
is undecidable rather than false. The 17 to 14 figure behind the 239e1ba
correction, read over 39 shared line keys, is a line-shift artifact of exactly
that kind.

These tests hold the key to the property the line number lacks. The site key
is the innermost enclosing def or class, the refusal statement with its
whitespace normalised, and an ordinal among identical statements in that same
scope. It must not move when lines are inserted above it, when the block is
reindented, when two sites are reordered, when a site is dropped from the
denominator, or when the verdict changes. Revert any of those to a position
and a test here goes red.

Known and deliberate: rewrapping one statement across different line breaks
DOES change its key, because the normalised text keeps the structural space a
line break becomes. Canonicalising through ast.unparse would survive that, at
the price of a key whose value depends on the CPython version that produced
it, which is a worse trade for an archive meant to be compared across years.

These tests drive the sweep in-process against a SYNTHETIC source, with the
detector stubbed and the lock redirected into tmp_path. Nothing here reads
vac/verify.py, spawns a sweep, runs pytest, or touches the repository lock, so
the file is safe to run inside a sweep's own detector and does not belong in
DESELECT. The only processes started are git, by the issuer-record tests near
the end, in repositories they make under tmp_path.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SWEEP = REPO / "tools" / "mutation_sweep.py"
CORPUS = REPO / "tools" / "fixture_corpus_score.py"

_CHECKOUT_VAR = re.compile(r"VAC_[A-Z0-9_]+_CHECKOUT")
BUNDLE_JSON = '{"vac_version": "0.2"}\n'


def _clear_checkout_env(monkeypatch) -> None:
    """Unset every VAC_*_CHECKOUT for this test.

    main() checks the issuer checkouts before it reads the source. With a
    doubled value exported in the shell that runs pytest, every test that
    drives main() would abort on that gate and fail on its message instead of
    its own. A test that is about those variables sets them itself.
    """
    for name in list(os.environ):
        if _CHECKOUT_VAR.fullmatch(name):
            monkeypatch.delenv(name, raising=False)


def _hermetic_issuers(mod, tmp_path, monkeypatch) -> list[dict]:
    """The real issuer table, with each fallback moved into tmp_path.

    An unset variable falls back to a sibling of the repository, and on a
    developer's machine those siblings exist. Left alone, the measured record
    would ask git about them, and what these tests see would depend on which
    machine runs them.
    """
    siblings = tmp_path / "siblings"
    redirected = [
        dict(cfg, default_checkout=str(
            siblings / pathlib.Path(cfg["default_checkout"]).name))
        for cfg in mod._issuers()]
    monkeypatch.setattr(mod, "_issuers", lambda: redirected)
    return redirected


# Six refusal-shaped lines, one of which the synthetic EXCLUDE removes, so the
# honest population is 6 raw / 5 scored. The shape is chosen to break a weaker
# key: `dup-code: repeated` appears three times, twice in one scope and once
# in another, and one statement is wrapped across three lines.
SYNTHETIC_SRC = (
    "def alpha(f, failures):\n"
    '    f.append("alpha-code: first")\n'
    '    f.append("dup-code: repeated")\n'
    '    f.append("dup-code: repeated")\n'
    "\n"
    "\n"
    "def beta(f, failures):\n"
    '    f.append("dup-code: repeated")\n'
    '    failures.append("beta-code: SYNTHETIC-EXCLUDED last")\n'
    "\n"
    "\n"
    "def gamma(f, failures):\n"
    "    f.append(\n"
    '        "gamma-code: "\n'
    '        "wrapped")\n'
)


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_sweep():
    return _load(SWEEP, "_sweep_under_test")


def _keys(mod, source: str) -> list[str]:
    ids = mod.site_identities(source.splitlines(keepends=True))
    return [ids[i]["key"] for i in sorted(ids)]


# --------------------------------------------------------------------------
# The key itself, with no sweep running.

def test_the_key_does_not_move_when_lines_are_inserted_above_it():
    """The defect in one line: a key that is a position is renamed by an edit
    somewhere else entirely."""
    mod = _load_sweep()
    shifted = "# a new comment\n" * 7 + SYNTHETIC_SRC
    before = mod.site_identities(SYNTHETIC_SRC.splitlines(keepends=True))
    after = mod.site_identities(shifted.splitlines(keepends=True))

    assert [before[i]["key"] for i in sorted(before)] == \
           [after[i]["key"] for i in sorted(after)]
    assert sorted(before) != sorted(after), (
        "the insertion did not move any line, so this proves nothing")
    assert all(a - b == 7 for a, b in zip(sorted(after), sorted(before)))


def test_the_key_does_not_move_when_the_block_is_reindented():
    """Indentation is whitespace, and the key normalises whitespace. A
    reformat that moves no statement must not rename any site."""
    mod = _load_sweep()
    reindented = "if True:\n" + "".join(
        ("    " + ln if ln.strip() else ln)
        for ln in SYNTHETIC_SRC.splitlines(keepends=True))
    assert _keys(mod, reindented) == _keys(mod, SYNTHETIC_SRC)


def test_a_source_that_does_not_parse_is_refused_not_keyed_to_module():
    """The quiet failure this avoids: swallow the SyntaxError, return an empty
    scope map, and every site keys to <module>. The keys stay unique and
    plausible, the duplicated statements collapse, and the archive says
    nothing about it."""
    mod = _load_sweep()
    broken = 'def alpha(f):\n    f.append("a-code: x")\n  bad indent\n'
    with pytest.raises(SyntaxError):
        mod.site_identities(broken.splitlines(keepends=True))


def test_the_key_does_not_move_when_two_sites_are_reordered():
    """Reordering rearranges positions and nothing else. Each key must follow
    its statement, not the slot the statement happens to occupy, so comparing
    key sets is not enough: a line key survives that comparison and still
    hands site L2's name to a different refusal."""
    mod = _load_sweep()
    lines = SYNTHETIC_SRC.splitlines(keepends=True)
    lines[1], lines[2] = lines[2], lines[1]
    swapped = "".join(lines)
    assert swapped != SYNTHETIC_SRC

    def named(source: str) -> dict[str, str]:
        ids = mod.site_identities(source.splitlines(keepends=True))
        return {v["key"]: v["statement"] for v in ids.values()}

    assert named(swapped) == named(SYNTHETIC_SRC)


def test_the_same_statement_in_two_scopes_gets_two_keys():
    """`dup-code: repeated` is written three times, twice in alpha and once in
    beta. Drop the enclosing scope from the key and beta's copy becomes
    alpha's third, which is the misattribution the scope exists to stop."""
    mod = _load_sweep()
    ids = mod.site_identities(SYNTHETIC_SRC.splitlines(keepends=True))
    dup = [v for v in ids.values() if "dup-code" in v["statement"]]
    assert len(dup) == 3
    assert [v["scope"] for v in dup] == ["alpha", "alpha", "beta"]
    assert [v["ordinal"] for v in dup] == [0, 1, 0], (
        "beta's copy was numbered as if it continued alpha's run")
    assert len({v["key"] for v in dup}) == 3


def test_identical_statements_in_one_scope_are_separated_by_an_ordinal():
    mod = _load_sweep()
    ids = mod.site_identities(SYNTHETIC_SRC.splitlines(keepends=True))
    alpha_dup = [v for v in ids.values()
                 if v["scope"] == "alpha" and "dup-code" in v["statement"]]
    assert [v["ordinal"] for v in alpha_dup] == [0, 1]
    assert alpha_dup[0]["key"] != alpha_dup[1]["key"]
    assert alpha_dup[0]["statement"] == alpha_dup[1]["statement"]


def test_a_statement_wrapped_over_three_lines_keys_as_one_statement():
    mod = _load_sweep()
    ids = mod.site_identities(SYNTHETIC_SRC.splitlines(keepends=True))
    wrapped = [v for v in ids.values() if v["scope"] == "gamma"]
    assert len(wrapped) == 1
    assert "\n" not in wrapped[0]["statement"]
    assert wrapped[0]["statement"] == 'f.append( "gamma-code: " "wrapped")'


def test_a_method_keys_under_its_class():
    """Two classes can hold the same method with the same refusal. The
    innermost scope wins and the qualname keeps them apart."""
    mod = _load_sweep()
    src = ("class A:\n"
           "    def check(self, f):\n"
           '        f.append("same-code: text")\n'
           "\n"
           "\n"
           "class B:\n"
           "    def check(self, f):\n"
           '        f.append("same-code: text")\n')
    ids = mod.site_identities(src.splitlines(keepends=True))
    assert [v["scope"] for v in ids.values()] == ["A.check", "B.check"]
    assert len({v["key"] for v in ids.values()}) == 2


def test_a_refusal_outside_any_scope_is_named_not_left_blank():
    mod = _load_sweep()
    ids = mod.site_identities(['f.append("top-code: text")\n'])
    assert [v["scope"] for v in ids.values()] == ["<module>"]


# --------------------------------------------------------------------------
# The sweep's own output.

@pytest.fixture
def sweep(tmp_path, monkeypatch):
    """The sweep module pointed at the synthetic source, with a clean stubbed
    baseline, a lock inside tmp_path, no VAC_*_CHECKOUT set, every issuer's
    fallback inside tmp_path, and no process anywhere."""
    _clear_checkout_env(monkeypatch)
    mod = _load_sweep()
    src = tmp_path / "verify.py"
    src.write_text(SYNTHETIC_SRC, encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_one.py").write_text("def test_one():\n    pass\n")
    (tests_dir / "test_two.py").write_text("def test_two():\n    pass\n")
    # Not .py on purpose: the detectors read every file in fixtures/, and a
    # digest over *.py alone would record none of these.
    fixtures_dir = tmp_path / "fixtures"
    for name in ("valid", "tamper-one"):
        (fixtures_dir / name).mkdir(parents=True)
        (fixtures_dir / name / "vac.json").write_text(BUNDLE_JSON)

    monkeypatch.setattr(mod, "SRC", src)
    monkeypatch.setattr(mod, "TESTS", tests_dir)
    monkeypatch.setattr(mod, "FIXTURES", fixtures_dir)
    mod.issuer_configs = _hermetic_issuers(mod, tmp_path, monkeypatch)
    mod.synthetic_fixtures = fixtures_dir
    monkeypatch.setattr(mod, "LOCK", tmp_path / ".mutation_sweep.lock")
    monkeypatch.setattr(mod, "EXCLUDE", {
        "SYNTHETIC-EXCLUDED": (1, "excluded so raw and scored differ")})
    monkeypatch.setattr(mod, "EXPECT_RAW_SITES", 6)
    monkeypatch.setattr(mod, "EXPECT_SCORED_SITES", 5)

    state = {"calls": 0, "mutant": (False, "SURVIVED")}

    def _detector(detector="all"):
        state["calls"] += 1
        if state["calls"] == 1:
            return False, "SURVIVED"       # a clean baseline, so main proceeds
        return state["mutant"]

    def _no_process(*a, **k):
        raise AssertionError("the sweep launched a detector process")

    monkeypatch.setattr(mod, "observe", _detector)
    monkeypatch.setattr(mod, "_run", _no_process)
    monkeypatch.setattr(mod.subprocess, "run", _no_process)
    mod.state = state
    mod.synthetic_src = src
    mod.synthetic_tests = tests_dir
    return mod


def _run_main(mod, monkeypatch, tmp_path, name="out.json", *args):
    out = tmp_path / name
    before = mod.synthetic_src.read_bytes()
    monkeypatch.setattr(sys, "argv",
                        ["mutation_sweep.py", "--json", str(out), *args])
    rc = mod.main()
    assert rc == 0, "the sweep did not complete"
    assert mod.synthetic_src.read_bytes() == before, (
        "the sweep left a mutant behind")
    return rc, json.loads(out.read_text())


def test_every_row_carries_a_key(sweep, monkeypatch, tmp_path):
    _, payload = _run_main(sweep, monkeypatch, tmp_path)
    assert len(payload["results"]) == 5
    assert all(r["key"] for r in payload["results"])
    assert len({r["key"] for r in payload["results"]}) == 5


def test_the_row_key_is_the_whole_file_identity_not_the_scored_position(
        sweep, monkeypatch, tmp_path):
    """The exclusion removes one site from the denominator. The sites that
    stay must keep the identity they had before it was removed: number the
    ordinal over the SCORED list instead and the EXCLUDE table is back inside
    the key, which is the same defect in a different place."""
    _, payload = _run_main(sweep, monkeypatch, tmp_path)
    whole_file = sweep.site_identities(SYNTHETIC_SRC.splitlines(keepends=True))
    # Five scored sites: six raw minus the one excluded. The loop below and
    # the absence after it both hold for an empty result list, so the count
    # is what makes either of them evidence.
    assert len(payload["results"]) == 5, payload["results"]
    for r in payload["results"]:
        assert r["key"] == whole_file[r["line"] - 1]["key"]
        assert r["scope"] == whole_file[r["line"] - 1]["scope"]
        assert r["ordinal"] == whole_file[r["line"] - 1]["ordinal"]
    assert "SYNTHETIC-EXCLUDED" not in json.dumps(payload["results"])


# An excluded statement with an identical twin in the same scope. EXCLUDE
# matches a fragment on a refusal's FIRST line, while the key normalises the
# whole statement, so the one-line copy is excluded, the wrapped copy is
# scored, and both normalise to the same text. Neither real excluded site has
# a twin today, which is why the test above cannot see the defect below.
TWIN_SRC = (
    "def delta(f):\n"
    '    f.append("delta-code: kept")\n'
    '    f.append("twin-code: " "TWIN-EXCLUDED")\n'
    '    f.append("twin-code: "\n'
    '             "TWIN-EXCLUDED")\n'
)
TWIN_STATEMENT = 'f.append("twin-code: " "TWIN-EXCLUDED")'


def test_an_excluded_twin_keeps_its_ordinal_so_the_scored_twin_keeps_its_own(
        sweep, monkeypatch, tmp_path):
    """Ordinals are counted before EXCLUDE. Count them after it and the
    scored twin takes #0, which is the name its excluded twin has in every
    sweep that does not exclude it, so two archives would pair different
    statements under one key.

    The expected keys are written out rather than derived from
    site_identities. A mutant that skips excluded lines inside site_identities
    would move a derived expectation along with the answer, which is how the
    test above passes it."""
    sweep.synthetic_src.write_text(TWIN_SRC, encoding="utf-8")
    monkeypatch.setattr(sweep, "EXCLUDE", {
        "TWIN-EXCLUDED": (1, "one of two identical statements excluded")})
    monkeypatch.setattr(sweep, "EXPECT_RAW_SITES", 3)
    monkeypatch.setattr(sweep, "EXPECT_SCORED_SITES", 2)

    ids = sweep.site_identities(TWIN_SRC.splitlines(keepends=True))
    assert [ids[i]["key"] for i in sorted(ids)] == [
        'delta::f.append("delta-code: kept")#0',
        f"delta::{TWIN_STATEMENT}#0",
        f"delta::{TWIN_STATEMENT}#1"]

    _, payload = _run_main(sweep, monkeypatch, tmp_path)
    assert [(r["line"], r["key"]) for r in payload["results"]] == [
        (2, 'delta::f.append("delta-code: kept")#0'),
        (4, f"delta::{TWIN_STATEMENT}#1")]


def test_the_key_does_not_depend_on_the_outcome(sweep, monkeypatch, tmp_path):
    """The reviewer's point: no field in the archive identified a site
    independently of the verdict. Two runs that disagree on every site must
    still name the same sites."""
    sweep.state["mutant"] = (True, "tests")
    _, caught = _run_main(sweep, monkeypatch, tmp_path, "caught.json")
    sweep.state["calls"] = 0
    sweep.state["mutant"] = (False, "SURVIVED")
    _, survived = _run_main(sweep, monkeypatch, tmp_path, "survived.json")

    assert [r["key"] for r in caught["results"]] == \
           [r["key"] for r in survived["results"]]
    assert [r["caught"] for r in caught["results"]] != \
           [r["caught"] for r in survived["results"]]
    assert caught["score"] == 1.0 and survived["score"] == 0.0


def test_the_row_still_carries_its_line_number(sweep, monkeypatch, tmp_path):
    """The twelve archived sweeps are keyed by line, and the tool that reads
    them joins on that field. The key is added beside it, not instead of it."""
    _, payload = _run_main(sweep, monkeypatch, tmp_path)
    assert [r["line"] for r in payload["results"]] == [2, 3, 4, 8, 13]


def test_the_output_records_the_bytes_it_measured(sweep, monkeypatch,
                                                  tmp_path):
    """Not a commit id. In 7 of the 12 archives the verify.py the run measured
    was not committed until the archive itself was, so no commit existing at
    run time named the tree."""
    _, payload = _run_main(sweep, monkeypatch, tmp_path)
    want = hashlib.sha256(SYNTHETIC_SRC.encode("utf-8")).hexdigest()
    assert payload["measured"]["source"]["sha256"] == want
    assert payload["measured"]["source"]["path"] == "verify.py"


def test_editing_the_source_changes_the_recorded_source_hash(
        sweep, monkeypatch, tmp_path):
    _, first = _run_main(sweep, monkeypatch, tmp_path, "a.json")
    sweep.synthetic_src.write_text(
        SYNTHETIC_SRC.replace("alpha-code: first", "alpha-code: firsT"),
        encoding="utf-8")
    sweep.state["calls"] = 0
    _, second = _run_main(sweep, monkeypatch, tmp_path, "b.json")
    assert first["measured"]["source"]["sha256"] != \
        second["measured"]["source"]["sha256"]


def test_the_output_records_a_digest_of_the_tests_that_could_report(
        sweep, monkeypatch, tmp_path):
    """Two archived runs measured the same verify.py and disagree on one site.
    Only a change on the detector side explains that, so a source hash alone
    would still not say what was measured."""
    _, first = _run_main(sweep, monkeypatch, tmp_path, "a.json")
    assert first["measured"]["tests"]["files"] == 2
    assert len(first["measured"]["tests"]["sha256"]) == 64

    (sweep.synthetic_tests / "test_one.py").write_text(
        "def test_one():\n    assert True\n")
    sweep.state["calls"] = 0
    _, second = _run_main(sweep, monkeypatch, tmp_path, "b.json")
    assert first["measured"]["source"]["sha256"] == \
        second["measured"]["source"]["sha256"]
    assert first["measured"]["tests"]["sha256"] != \
        second["measured"]["tests"]["sha256"], (
            "the same source with different tests recorded the same thing")


def test_adding_a_test_file_changes_the_digest(sweep, monkeypatch, tmp_path):
    _, first = _run_main(sweep, monkeypatch, tmp_path, "a.json")
    (sweep.synthetic_tests / "test_three.py").write_text("def test_c():\n"
                                                         "    pass\n")
    sweep.state["calls"] = 0
    _, second = _run_main(sweep, monkeypatch, tmp_path, "b.json")
    assert second["measured"]["tests"]["files"] == 3
    assert first["measured"]["tests"]["sha256"] != \
        second["measured"]["tests"]["sha256"]


def test_renaming_a_test_file_changes_the_digest(sweep, monkeypatch, tmp_path):
    """The digest covers paths as well as bytes, so a rename is a change."""
    _, first = _run_main(sweep, monkeypatch, tmp_path, "a.json")
    (sweep.synthetic_tests / "test_one.py").rename(
        sweep.synthetic_tests / "test_renamed.py")
    sweep.state["calls"] = 0
    _, second = _run_main(sweep, monkeypatch, tmp_path, "b.json")
    assert second["measured"]["tests"]["files"] == 2
    assert first["measured"]["tests"]["sha256"] != \
        second["measured"]["tests"]["sha256"]


def test_the_digest_ignores_compiled_caches(sweep, monkeypatch, tmp_path):
    """A __pycache__ left by an earlier run must not make two measurements of
    the same tests look different."""
    _, first = _run_main(sweep, monkeypatch, tmp_path, "a.json")
    cache = sweep.synthetic_tests / "__pycache__"
    cache.mkdir()
    (cache / "test_one.cpython-312.py").write_text("# not source\n")
    sweep.state["calls"] = 0
    _, second = _run_main(sweep, monkeypatch, tmp_path, "b.json")
    assert first["measured"]["tests"] == second["measured"]["tests"]


def test_the_output_records_which_detector_ran(sweep, monkeypatch, tmp_path):
    """`all` and a single detector answer different questions over the same
    sites. An archive that does not say which one it asked cannot be read."""
    _, payload = _run_main(sweep, monkeypatch, tmp_path, "out.json",
                           "--detector", "fixtures")
    assert payload["detector"] == "fixtures"


def test_the_default_detector_is_recorded_too(sweep, monkeypatch, tmp_path):
    """The scored path is the one an archive is most often read for, and it is
    the one the old payload left out: it named the detector only when it was
    not `all`, so a reader had to know that silence meant `all`. The test
    above passes against that, because it asks for a named detector."""
    _, payload = _run_main(sweep, monkeypatch, tmp_path)
    assert payload["detector"] == "all"


def test_the_output_records_the_fixtures_the_detectors_read(
        sweep, monkeypatch, tmp_path):
    """The liveness and fixtures detectors run each mutant against fixtures/.
    Edit a fixture and a verdict can change with the source and the tests
    byte-identical, so a record without it does not name the measurement."""
    _, first = _run_main(sweep, monkeypatch, tmp_path, "a.json")
    assert first["measured"]["fixtures"]["files"] == 2
    assert len(first["measured"]["fixtures"]["sha256"]) == 64

    (sweep.synthetic_fixtures / "tamper-one" / "vac.json").write_text(
        '{"vac_version": "0.1"}\n')
    sweep.state["calls"] = 0
    _, second = _run_main(sweep, monkeypatch, tmp_path, "b.json")
    assert first["measured"]["source"] == second["measured"]["source"]
    assert first["measured"]["tests"] == second["measured"]["tests"]
    assert first["measured"]["fixtures"]["sha256"] != \
        second["measured"]["fixtures"]["sha256"], (
            "the same source and tests over different fixtures recorded the "
            "same thing")


def test_the_output_records_the_sweep_tools_own_bytes(sweep, monkeypatch,
                                                      tmp_path):
    """DESELECT, EXCLUDE, the operator and the detector order live in the
    tool. A path added to DESELECT drops a test from the detector with tests/
    unchanged, so the tool is part of what was measured."""
    _, payload = _run_main(sweep, monkeypatch, tmp_path)
    assert payload["measured"]["tool"] == {
        "tools/mutation_sweep.py":
            hashlib.sha256(SWEEP.read_bytes()).hexdigest()}


def test_the_output_records_every_issuer_checkout_even_unset(
        sweep, monkeypatch, tmp_path):
    """Unset is not absent: each consumer falls back to a sibling checkout and
    runs against it when it is there. So every configured variable is
    recorded, and an unset one names the fallback it read and whether a
    bundle was there."""
    _, payload = _run_main(sweep, monkeypatch, tmp_path)
    issuers = payload["measured"]["issuers"]
    ci_set = {"VAC_CRASHKIT_CHECKOUT", "VAC_EVALMUT_CHECKOUT",
              "VAC_MODELDRIFT_CHECKOUT"}
    assert ci_set <= set(issuers), "the three CI sets are not recorded"
    assert set(issuers) == {c["checkout_env"] for c in sweep.issuer_configs}
    for cfg in sweep.issuer_configs:
        assert issuers[cfg["checkout_env"]] == {
            "value": "unset", "checkout": cfg["default_checkout"],
            "commit": "absent"}


def test_a_set_issuer_checkout_is_recorded_with_what_it_resolved_to(
        sweep, monkeypatch, tmp_path):
    """A variable set to a directory that holds the bundle. This one has no
    .git of its own, so no commit can be named for it and the record says
    so. It says so without starting git (the fixture forbids any process):
    git would answer for whatever repository encloses the directory."""
    co = tmp_path / "copied-crashkit"
    (co / "vac").mkdir(parents=True)
    (co / "vac" / "vac.json").write_text(BUNDLE_JSON)
    monkeypatch.setenv("VAC_CRASHKIT_CHECKOUT", str(co))
    _, payload = _run_main(sweep, monkeypatch, tmp_path)
    issuers = payload["measured"]["issuers"]
    assert issuers["VAC_CRASHKIT_CHECKOUT"] == {
        "value": str(co), "checkout": str(co),
        "commit": "not a git checkout"}
    assert issuers["VAC_EVALMUT_CHECKOUT"]["value"] == "unset"


def test_the_measured_record_is_printed_for_a_run_that_writes_no_json(
        sweep, monkeypatch, capsys):
    """CI runs the sweep without --json, so the log is the only record a CI
    run leaves. Every digest and every issuer has to be in it."""
    monkeypatch.setattr(sys, "argv", ["mutation_sweep.py"])
    assert sweep.main() == 0
    out = capsys.readouterr().out
    fixtures_sha, _ = sweep.tree_digest(sweep.synthetic_fixtures, "**/*")
    for want in (
            hashlib.sha256(SYNTHETIC_SRC.encode("utf-8")).hexdigest(),
            sweep.tree_digest(sweep.synthetic_tests)[0],
            f"fixtures (2 files) sha256 {fixtures_sha}",
            "measured tools/mutation_sweep.py sha256 "
            + hashlib.sha256(SWEEP.read_bytes()).hexdigest()):
        assert want in out, f"{want!r} is not in the log"
    for cfg in sweep.issuer_configs:
        line = (f"issuer {cfg['checkout_env']} unset: reads "
                f"{cfg['default_checkout']}, commit absent")
        assert line in out, f"{line!r} is not in the log"


# --------------------------------------------------------------------------
# The issuer record against real git repositories. These start git, in
# repositories made under tmp_path, and nothing else.

def _git(cwd: pathlib.Path, *args: str) -> str:
    """git with no user or system config and no inherited GIT_* variables, so
    a developer's hooks, signing or GIT_DIR cannot reach these repositories."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=sweep-test",
         "-c", "user.email=sweep-test@example.invalid",
         "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={os.devnull}",
         *args], check=True, capture_output=True, text=True, env=env).stdout


def _issuer_repo(path: pathlib.Path) -> str:
    """A one-commit repository holding a vac/ bundle. Returns its HEAD.

    The commit message is the directory name. Two repositories with the same
    tree, author and second would otherwise share a commit id, and a test that
    tells them apart by commit would prove nothing."""
    (path / "vac").mkdir(parents=True)
    (path / "vac" / "vac.json").write_text(BUNDLE_JSON)
    _git(path, "init", "-q")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", f"bundle in {path.name}")
    return _git(path, "rev-parse", "HEAD").strip()


@pytest.fixture
def issuers(tmp_path, monkeypatch):
    """The sweep module with no VAC_*_CHECKOUT set and every issuer's
    fallback inside tmp_path. git may run."""
    _clear_checkout_env(monkeypatch)
    mod = _load_sweep()
    _hermetic_issuers(mod, tmp_path, monkeypatch)
    return mod


def _crashkit(mod, env: dict) -> dict:
    return mod.issuer_checkouts(env)["VAC_CRASHKIT_CHECKOUT"]


def test_a_git_checkout_is_recorded_at_the_commit_git_names_there(issuers,
                                                                  tmp_path):
    """The commit, and whether the tree the tests read still matches it. A
    commit id alone is the claim measured_revision refuses for verify.py: it
    names what was committed, not what was read."""
    co = tmp_path / "crashkit"
    head = _issuer_repo(co)
    assert _crashkit(issuers, {"VAC_CRASHKIT_CHECKOUT": str(co)}) == {
        "value": str(co), "checkout": str(co), "commit": head,
        "dirty": False}

    (co / "vac" / "vac.json").write_text('{"vac_version": "0.1"}\n')
    rec = _crashkit(issuers, {"VAC_CRASHKIT_CHECKOUT": str(co)})
    assert (rec["commit"], rec["dirty"]) == (head, True)


def test_an_unset_variable_records_the_sibling_it_falls_back_to(issuers):
    """Unset, with the sibling present: the tests run against the sibling, so
    the record names it and its commit rather than stopping at "unset"."""
    cfg = next(c for c in issuers._issuers()
               if c["checkout_env"] == "VAC_CRASHKIT_CHECKOUT")
    head = _issuer_repo(pathlib.Path(cfg["default_checkout"]))
    assert _crashkit(issuers, {}) == {
        "value": "unset", "checkout": cfg["default_checkout"],
        "commit": head, "dirty": False}


def test_a_bundle_inside_another_repository_is_not_given_its_head(issuers,
                                                                  tmp_path):
    """git answers for the nearest enclosing repository, and an empty .git
    directory does not stop it climbing. A copied bundle sitting inside some
    other checkout would otherwise be recorded at that checkout's HEAD: a
    real commit id, for bytes it does not describe."""
    outer = tmp_path / "outer"
    outer_head = _issuer_repo(outer)
    inner = outer / "copied-crashkit"
    (inner / "vac").mkdir(parents=True)
    (inner / "vac" / "vac.json").write_text(BUNDLE_JSON)
    (inner / ".git").mkdir()
    assert _git(inner, "rev-parse", "HEAD").strip() == outer_head, (
        "git did not climb to the outer repository, so this proves nothing")
    assert _crashkit(issuers, {"VAC_CRASHKIT_CHECKOUT": str(inner)}) == {
        "value": str(inner), "checkout": str(inner),
        "commit": "not a git checkout"}


def test_an_exported_git_dir_does_not_redirect_the_record(issuers, tmp_path,
                                                          monkeypatch):
    """A git hook exports GIT_DIR, and git then answers every query for the
    repository that ran the hook, taking the directory it was started in as
    that repository's top level. A sweep started from a hook would record the
    hook's HEAD for every issuer, and the top-level guard would not see it."""
    hook_repo = tmp_path / "hook-repo"
    hook_head = _issuer_repo(hook_repo)
    co = tmp_path / "crashkit"
    head = _issuer_repo(co)
    assert head != hook_head
    monkeypatch.setenv("GIT_DIR", str(hook_repo / ".git"))
    assert _crashkit(issuers, {"VAC_CRASHKIT_CHECKOUT": str(co)})["commit"] \
        == head


# --------------------------------------------------------------------------
# The other sweep over the same operator.

def _corpus_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A checkout-shaped tree: the synthetic source, one test, one fixture."""
    repo = tmp_path / "repo"
    (repo / "vac").mkdir(parents=True)
    (repo / "fixtures" / "tamper-one").mkdir(parents=True)
    (repo / "fixtures" / "tamper-one" / "vac.json").write_text(BUNDLE_JSON)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_one.py").write_text("def test_one():\n    pass\n")
    (repo / "vac" / "verify.py").write_text(SYNTHETIC_SRC, encoding="utf-8")
    return repo


def test_the_corpus_score_keys_its_rows_the_same_way(tmp_path, monkeypatch):
    """tools/fixture_corpus_score.py applies the same deletion operator to the
    same refusal sites. A second key would make the two archives
    unreconcilable for no reason."""
    mod = _load(CORPUS, "_corpus_under_test")
    repo = _corpus_repo(tmp_path)
    src = repo / "vac" / "verify.py"

    monkeypatch.setattr(mod, "observe", lambda repo, detector: (False,
                                                                "SURVIVED"))
    results, total, measured = mod.sweep(repo, "fixtures")

    assert total == 6, "the corpus score excludes nothing, so all six count"
    whole_file = mod.site_identities(SYNTHETIC_SRC.splitlines(keepends=True))
    for r in results:
        assert r["key"] == whole_file[r["line"] - 1]["key"]
    assert len({r["key"] for r in results}) == 6
    assert measured["source"]["sha256"] == \
        hashlib.sha256(SYNTHETIC_SRC.encode("utf-8")).hexdigest()
    assert measured["tests"]["files"] == 1
    assert src.read_text(encoding="utf-8") == SYNTHETIC_SRC


def test_the_corpus_score_records_the_fixtures_and_tools_it_ran(tmp_path,
                                                                monkeypatch):
    """Here the fixture corpus IS the detector, so the same verify.py scored
    against a different corpus is a different number. The two files that
    applied the operator are recorded beside it: this tool, and the sweep it
    takes the operator and the key from."""
    mod = _load(CORPUS, "_corpus_under_test")
    repo = _corpus_repo(tmp_path)
    monkeypatch.setattr(mod, "observe", lambda repo, detector: (False,
                                                                "SURVIVED"))
    _, _, first = mod.sweep(repo, "fixtures")
    assert first["fixtures"]["files"] == 1
    assert first["tool"] == {
        "tools/fixture_corpus_score.py":
            hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        "tools/mutation_sweep.py":
            hashlib.sha256(SWEEP.read_bytes()).hexdigest()}

    (repo / "fixtures" / "tamper-one" / "vac.json").write_text(
        '{"vac_version": "0.1"}\n')
    _, _, second = mod.sweep(repo, "fixtures")
    assert first["source"] == second["source"]
    assert first["fixtures"]["sha256"] != second["fixtures"]["sha256"]


def test_recording_a_checkout_does_not_write_to_it(issuers, tmp_path):
    """A plain `git status` refreshes a stale index and writes it back. The
    record runs against the issuer checkouts the tests are about to read, and
    in CI and on a developer's machine those are real repositories, so it must
    leave them byte-identical. A file whose timestamp moved and whose bytes
    did not is the case that makes git want to rewrite the index."""
    co = tmp_path / "crashkit"
    head = _issuer_repo(co)
    bundle = co / "vac" / "vac.json"
    st = bundle.stat()
    os.utime(bundle, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    index = (co / ".git" / "index").read_bytes()

    rec = _crashkit(issuers, {"VAC_CRASHKIT_CHECKOUT": str(co)})
    assert (rec["commit"], rec["dirty"]) == (head, False)
    assert (co / ".git" / "index").read_bytes() == index, (
        "recording the checkout rewrote its index")
