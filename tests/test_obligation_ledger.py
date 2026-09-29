"""The obligation ledger held to the standard it exists to impose.

A coverage ledger nobody can fail is a worse artifact than no ledger, because it
converts an unexamined claim into a published number. Every test here mutates a
copy of obligations.json and asserts the checker REFUSES it. The positive case
is one line; the negatives are the point.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / "obligations.json"
CHECKER = ROOT / "tools" / "check_obligations.py"


def run(ledger_path) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(CHECKER), "--ledger", str(ledger_path)],
                       capture_output=True, text=True, cwd=ROOT)
    return p.returncode, p.stdout + p.stderr


@pytest.fixture
def ledger():
    return json.loads(LEDGER.read_text())


def write(tmp_path, doc):
    p = tmp_path / "obligations.json"
    p.write_text(json.dumps(doc, indent=1))
    return p


def test_the_committed_ledger_passes():
    rc, out = run(LEDGER)
    assert rc == 0, out


def test_every_normative_clause_has_an_entry(ledger):
    """C1. The count is not decorative: it is re-extracted from SPEC.md."""
    import re
    spec = (ROOT / "SPEC.md").read_text().splitlines()
    clauses = [i for i, l in enumerate(spec, 1)
               if re.search(r"\bMUST NOT\b|\bMUST\b|\bSHALL NOT\b|\bSHALL\b", l)]
    spans = {int(o["source_span"].split(":")[1]) for o in ledger["obligations"]}
    assert set(clauses) == spans


def test_a_deleted_mapping_is_refused(tmp_path, ledger):
    """C1. Dropping an entry must not quietly shrink the denominator."""
    d = copy.deepcopy(ledger)
    d["obligations"] = d["obligations"][1:]
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "C1 no ledger entry" in out


def test_a_site_that_does_not_exist_is_refused(tmp_path, ledger):
    """C2. The commonest rot: a test is renamed and the ledger still cites it."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if o["evaluation_sites"])
    m["evaluation_sites"] = ["tests/test_verify.py::test_this_was_renamed_away"]
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "does not exist" in out


def test_an_unknown_refusal_code_is_refused(tmp_path, ledger):
    """C2. A refusal_site the verifier never emits cannot be the mechanism."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if o["refusal_site"])
    m["refusal_site"] = "sounds-plausible-mismatch"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "is not a code vac/verify.py emits" in out


def test_a_misbound_token_is_refused(tmp_path, ledger):
    """C3. The named test must reference the mechanism it is claimed to exercise."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"]
             if o["refusal_site"] == "raw-aggregate-mismatch" and o["evaluation_sites"])
    m["evaluation_sites"] = ["tests/test_draft.py::" + _first_draft_test()]
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "does not reference refusal_site" in out


def _first_draft_test() -> str:
    import re
    return re.findall(r"^def (test_\w+)", (ROOT / "tests" / "test_draft.py").read_text(), re.M)[0]


def test_a_token_prefix_contradicting_its_section_is_refused(tmp_path, ledger):
    """C3. A crashkit property cannot be evidence for a modeldrift clause."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if "modeldrift" in o["section"].lower())
    m["property_token"] = "crashkit.accuracy_equals_all_four_aliases"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "contradicts section" in out


def test_unmeasured_promoted_to_mapped_is_refused(tmp_path, ledger):
    """C4. The load-bearing one. Calling something mapped is a claim that a
    mechanism fails when it is violated, and it is refused without one."""
    d = copy.deepcopy(ledger)
    u = next(o for o in d["obligations"] if o["status"] == "unmeasured")
    u["status"] = "mapped"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "status 'mapped' with no executable reference" in out


def test_unmeasured_claiming_a_site_is_refused(tmp_path, ledger):
    """C4, the other direction: unmeasured must actually be unmeasured."""
    d = copy.deepcopy(ledger)
    u = next(o for o in d["obligations"] if o["status"] == "unmeasured")
    u["refusal_site"] = "schema-violation"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "'unmeasured' but a site is claimed" in out


def test_a_vague_property_token_is_refused(tmp_path, ledger):
    """C5. 'covered' and 'works' are how a coverage table stops meaning anything."""
    d = copy.deepcopy(ledger)
    d["obligations"][0]["property_token"] = "bundle.correctness"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "vague term" in out


def test_an_undotted_property_token_is_refused(tmp_path, ledger):
    d = copy.deepcopy(ledger)
    d["obligations"][0]["property_token"] = "hashes"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "not a dotted operational property" in out


def test_a_duplicate_obligation_id_is_refused(tmp_path, ledger):
    d = copy.deepcopy(ledger)
    d["obligations"][1]["obligation_id"] = d["obligations"][0]["obligation_id"]
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "duplicate obligation_id" in out


def test_clause_text_drift_is_refused(tmp_path, ledger):
    """C6. If SPEC.md is edited under a ledger entry, the entry is stale."""
    d = copy.deepcopy(ledger)
    d["obligations"][0]["normative_text"] = "MUST do something else entirely"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "no longer matches" in out


def test_the_ledger_rebuilds_byte_identically():
    """The ledger is derived, so a stale committed copy is a real defect."""
    before = LEDGER.read_bytes()
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_obligations.py")],
                   capture_output=True, text=True, cwd=ROOT, check=True)
    after = LEDGER.read_bytes()
    if after != before:
        LEDGER.write_bytes(before)
        pytest.fail("obligations.json is not what tools/build_obligations.py emits")


def test_unmeasured_obligations_are_reported_not_hidden(ledger):
    """The finding this whole artifact exists to make sayable."""
    un = [o for o in ledger["obligations"] if o["status"] == "unmeasured"]
    assert un, "an all-mapped ledger is the outcome to distrust"
    for o in un:
        assert o["rationale"].strip(), f"{o['obligation_id']} is unmeasured with no reason given"


# ── addressee: the field that makes the structural claim artifact-derived ──
#
# The claim the paper wants to make is "the unmeasured obligations are the ones
# addressed to a human or a registry, not to the verifier". Before this field
# that sentence was an author's retrospective reading of the rationale prose.
# These tests exist so it is a property of the ledger instead.

def test_every_obligation_carries_an_allowed_addressee(ledger):
    for o in ledger["obligations"]:
        assert o["addressee"] in {"verifier", "registry", "reviewer"}, o["obligation_id"]
        assert o["addressee_basis"] in {"derived-from-token-prefix", "adjudicated"}


def test_no_verifier_addressed_obligation_is_unmeasured(ledger):
    """The structural finding, asserted rather than narrated."""
    stranded = [o["obligation_id"] for o in ledger["obligations"]
                if o["addressee"] == "verifier" and o["status"] == "unmeasured"]
    assert stranded == [], f"verifier-addressed but unmeasured: {stranded}"


def test_the_partially_mapped_verifier_obligation_is_named(ledger):
    """SPEC-40 is the one verifier obligation that is not fully mapped. If that
    stops being true the paper's sentence changes, so it fails here first. It
    was SPEC-39 until the JSON nesting clause was inserted ahead of it in
    SPEC 4, and ids are positional."""
    partial = sorted(o["obligation_id"] for o in ledger["obligations"]
                     if o["addressee"] == "verifier" and o["status"] == "partially_mapped")
    assert partial == ["SPEC-40"], partial


def test_a_missing_addressee_is_refused(tmp_path, ledger):
    d = copy.deepcopy(ledger)
    del d["obligations"][0]["addressee"]
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "C7" in out and "is not one of" in out


def test_an_invented_addressee_is_refused(tmp_path, ledger):
    d = copy.deepcopy(ledger)
    d["obligations"][0]["addressee"] = "auditor"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "C7" in out


def test_an_addressee_contradicting_its_exact_prefix_is_refused(tmp_path, ledger):
    """C8. A registry.* token cannot be relabelled as a verifier obligation to
    move an unmeasured row out of the awkward column."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if o["property_token"].startswith("registry."))
    m["addressee"] = "verifier"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "contradicts exact prefix" in out


def test_claiming_adjudication_for_an_exact_prefix_is_refused(tmp_path, ledger):
    """C8. Adjudication is for genuinely ambiguous prefixes; claiming it where
    the namespace already settles the answer hides a decision that was not made."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"]
             if o["addressee_basis"] == "derived-from-token-prefix")
    m["addressee_basis"] = "adjudicated"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "must be derived-from-token-prefix" in out


def test_deriving_an_ambiguous_prefix_is_refused(tmp_path, ledger):
    """C8, the other direction: protocol.* spans addressees, so it may not be
    silently derived."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if o["property_token"].startswith("protocol."))
    m["addressee_basis"] = "derived-from-token-prefix"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "must be adjudicated" in out


def test_an_unaccountable_prefix_is_refused(tmp_path, ledger):
    d = copy.deepcopy(ledger)
    d["obligations"][0]["property_token"] = "novelnamespace.some_property"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "unaccountable" in out


def _copy_tools(root):
    """COPIES, not symlinks: the tools resolve ROOT from __file__, and a
    symlink would resolve straight back to this repo. Every tool is copied,
    so a tool's sibling imports resolve inside the sandbox too."""
    (root / "tools").mkdir(parents=True)
    for p in sorted((ROOT / "tools").glob("*.py")):
        (root / "tools" / p.name).write_text(p.read_text(encoding="utf-8"),
                                             encoding="utf-8")


def _sandbox_repo(tmp_path, mutate):
    """A throwaway repo whose tools/ holds a MUTATED builder and whose inputs are
    symlinks to the real ones. The builder resolves ROOT from __file__, so this
    gives it a correct ROOT without ever writing to the checked-in source."""
    root = tmp_path / "repo"
    _copy_tools(root)
    for name in ("SPEC.md", "vac", "tests"):
        (root / name).symlink_to(ROOT / name)
    src = (ROOT / "tools" / "build_obligations.py").read_text()
    (root / "tools" / "build_obligations.py").write_text(mutate(src))
    return root


def _run_builder(root):
    p = subprocess.run([sys.executable, str(root / "tools" / "build_obligations.py")],
                       capture_output=True, text=True, cwd=root)
    return p.returncode, p.stdout + p.stderr


def test_the_builder_refuses_an_ambiguous_prefix_with_no_adjudication(tmp_path):
    """Dropping the adjudication must not fall back to a guess."""
    rc, out = _run_builder(_sandbox_repo(
        tmp_path,
        lambda s: re.sub(r'(109:\(None,"protocol\.grading[^\n]*?),"reviewer"\),', r'\1),', s)))
    assert rc != 0 and "no explicit addressee adjudication" in out
    assert (ROOT / "tools" / "build_obligations.py").read_text().count('"reviewer"') >= 1


def test_the_builder_refuses_an_adjudication_the_table_contradicts(tmp_path):
    """The hole this amendment closes, at the builder. A legal value and a legal
    basis are not enough; the ruling has to be the reviewed one."""
    rc, out = _run_builder(_sandbox_repo(
        tmp_path,
        lambda s: s.replace('"unmeasured","Prose obligation.', '"unmeasured","Prose obligation.', 1)
                   .replace(',"reviewer"),', ',"verifier"),', 1)))
    assert rc != 0 and "the reviewed ruling for that subfamily is" in out


def test_the_builder_refuses_a_token_no_adjudication_rule_covers(tmp_path):
    """An ambiguous-prefix token outside every ADJUDICATED rule answers to nothing."""
    rc, out = _run_builder(_sandbox_repo(
        tmp_path,
        lambda s: s.replace("protocol.grading.describes_deterministic_process",
                            "protocol.unruled.some_property", 1)))
    assert rc != 0 and "matches no ADJUDICATED rule" in out


# ── C9: the adjudication must hold the reviewed answer, checked on a ledger copy ──

def test_spec03_relabelled_as_verifier_is_refused(tmp_path, ledger):
    """The exact mutation that passed before this amendment. It kept a permitted
    addressee and an 'adjudicated' basis, and inverted the headline finding to
    'one verifier-addressed obligation is unmeasured'."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if o["property_token"].startswith("protocol.grading."))
    m["addressee"] = "verifier"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "C9" in out and "the reviewed ruling for" in out


def test_a_protocol_hashes_obligation_relabelled_as_reviewer_is_refused(tmp_path, ledger):
    """The other direction: moving a verifier obligation into the reviewer column
    would shrink the set the verifier is answerable for."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if o["property_token"].startswith("protocol.hashes."))
    m["addressee"] = "reviewer"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "C9" in out and "'verifier'" in out


def test_an_unruled_ambiguous_token_is_refused(tmp_path, ledger):
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if o["property_token"].startswith("protocol."))
    m["property_token"] = "protocol.unruled.some_property"
    rc, out = run(write(tmp_path, d))
    assert rc == 1 and "answers to nothing" in out


# ── refusal codes are read from emission sites, and tests bind by their code ──
#
# The ledger found refusal codes with the regex "([a-z][a-z0-9-]{4,40}): over
# the whole of vac/verify.py. That matched `suite` from the tail of a
# raw-aggregate-mismatch message and `usage` from a CLI constant, and missed
# every code emitted bare (`empty-limitations`, `missing-issuer-commit`) or by
# print (`unsafe-archive`). SPEC-30 was keyed to `suite` and C2 passed it.
# Tests were bound by splitting each file at `def test_`, so a comment sitting
# after one test bound that test to whatever code the comment named, which is
# how SPEC-01 came to cite a test that asserts a different code.

def _ledger_sources():
    spec = importlib.util.spec_from_file_location(
        "_ledger_sources", ROOT / "tools" / "ledger_sources.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("word", ["suite", "usage"])
def test_a_refusal_site_that_is_not_an_emitted_code_is_refused(tmp_path, ledger,
                                                               word):
    """C2. `suite` is the last word of a raw-aggregate-mismatch message and
    `usage` opens the CLI usage string. Neither is a refusal code."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if o["refusal_site"])
    m["refusal_site"] = word
    rc, out = run(write(tmp_path, d))
    assert rc == 1
    assert f"refusal_site {word!r} is not a code vac/verify.py emits" in out


@pytest.mark.parametrize("code", ["empty-limitations", "missing-issuer-commit",
                                  "unsafe-archive"])
def test_codes_emitted_bare_or_by_print_are_accepted(tmp_path, ledger, code):
    """C2, the other direction. The entry is made partially_mapped with no
    evaluation site so that C2 is the only check with anything to say."""
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if o["refusal_site"])
    m["refusal_site"] = code
    m["status"] = "partially_mapped"
    m["evaluation_sites"] = []
    rc, out = run(write(tmp_path, d))
    assert rc == 0, out


def test_the_extractor_reads_emission_sites_not_every_quoted_word():
    src = (ROOT / "vac" / "verify.py").read_text(encoding="utf-8")
    codes = _ledger_sources().refusal_codes(src)
    assert {"empty-limitations", "missing-issuer-commit",
            "unsafe-archive"} <= set(codes)
    assert "suite" not in codes
    assert "usage" not in codes


def test_the_extractor_on_every_emission_shape():
    """One of each shape vac/verify.py uses, and the three shapes that look
    like refusals and are not: a quoted word ending a message, the generic
    reporter that prints reasons already collected, and a print that does not
    open with FAIL."""
    src = (
        'USAGE = "usage: python -m vac.verify <bundle>"\n'
        "def check(f, failures, w, j, unknown, e, reason):\n"
        '    f.append(f"raw-aggregate-mismatch: {w}: "\n'
        '             f"fails_runs[{j}] names tasks outside the "\n'
        '             f"suite: {unknown}")\n'
        '    f.append("empty-limitations")\n'
        '    failures.append("missing-issuer-commit")\n'
        '    print(_printable(f"FAIL unsafe-archive: {e}"))\n'
        '    print(f"FAIL {_printable(reason)}")\n'
        '    print("dry-run: a print that is not a refusal")\n'
        '    return ["missing-manifest: no vac.json in bundle"]\n')
    codes = _ledger_sources().refusal_codes(src)
    assert sorted(codes) == ["empty-limitations", "missing-issuer-commit",
                             "missing-manifest", "raw-aggregate-mismatch",
                             "unsafe-archive"]
    assert codes["raw-aggregate-mismatch"] == [3]


def test_the_extractor_reads_every_site_the_mutation_sweep_scores():
    """The ledger's codes and the sweep's denominator come from the same
    appends. A mutant removes one site from both, so this holds inside a
    sweep as well."""
    src = (ROOT / "vac" / "verify.py").read_text(encoding="utf-8")
    swept = {i for i, ln in enumerate(src.splitlines(), 1)
             if re.match(r"^\s*(f|failures)\.append\(", ln)}
    read = {n for lines in _ledger_sources().refusal_codes(src).values()
            for n in lines}
    assert swept and swept <= read
    assert all(re.match(r"^\s*(f|failures)\.append\(|^\s*return \[|"
                        r"^\s*print\(", src.splitlines()[n - 1])
               for n in read - swept)


@pytest.mark.parametrize("line", [
    "f.append(reason)",
    'f.append(f"{kind}: computed")',
    'f.append("declared without a code")',
])
def test_the_extractor_refuses_a_refusal_whose_code_it_cannot_read(line):
    """Every f.append is a refusal site to the mutation sweep. One whose code
    cannot be read statically must stop the build, not drop out of C2."""
    src = f"def check(f, reason, kind):\n    {line}\n"
    with pytest.raises(ValueError, match="line 2"):
        _ledger_sources().refusal_codes(src)


@pytest.mark.parametrize("code,literal,binds", [
    ("unlisted-file", "unlisted-file", True),
    ("unlisted-file", "unlisted-file: evidence/extra.txt", True),
    ("unsafe-archive", "FAIL unsafe-archive: member escapes", True),
    ("unlisted-file", "sha256-mismatch: a; unlisted-file: b", True),
    ("unlisted-file", "unlisted-files", False),
    ("unlisted-file", "unlisted-file-extra: x", False),
    ("draft-incomplete", "tamper-draft-incomplete", False),
    ("unlisted-file", "xunlisted-file: y", False),
    ("unlisted-file", "the unlisted-file rule", False),
])
def test_a_reference_is_the_code_as_a_whole_token(code, literal, binds):
    """The code opens the literal as a whole token, or appears as `code:`
    anywhere, bounded on the left. A fixture directory named after a code, a
    longer code, or prose that mentions it is not a reference."""
    assert _ledger_sources().references([literal], code) is binds


def test_the_builder_refuses_a_row_keyed_to_a_code_verify_never_emits(tmp_path):
    """C2 refuses this in a written ledger. The builder refuses it before
    writing one, with `suite`, the word SPEC-30 used to be keyed to."""
    def rekey(src):
        old = '549:("raw-aggregate-mismatch",'
        assert src.count(old) == 1
        return src.replace(old, '549:("suite",')
    rc, out = _run_builder(_sandbox_repo(tmp_path, rekey))
    assert rc != 0
    assert "never emits: [(549, 'suite')]" in out


BINDING_PROBE = '''\
import pytest


def test_probe_names_the_code_in_code():
    reason = "{code}: named where the test uses it"
    assert reason.startswith("{code}")


def test_probe_names_the_code_only_after_itself():
    assert 1 + 1 == 2


# {code}: this comment sits between two tests and exercises nothing


def test_probe_names_the_code_only_in_prose():
    """Mentions {code}: in a docstring, which exercises nothing either."""
    assert True


@pytest.mark.parametrize("reason", ["{code}: from the decorator"])
def test_probe_names_the_code_in_a_decorator(reason):
    assert reason


@pytest.mark.skip(reason="{code}: never runs")
def test_probe_names_the_code_as_a_skip_reason():
    assert False


@pytest.mark.xfail(reason="{code}: expected to fail")
def test_probe_names_the_code_as_an_xfail_reason():
    assert False


def test_probe_names_the_code_as_a_runtime_skip_reason():
    pytest.skip("{code}: skipped at runtime")


def test_probe_asserts_the_code_is_absent():
    out = []
    assert "{code}" not in out
    assert out != ["{code}: never produced"]


def test_probe_names_the_code_in_a_branch_that_never_runs():
    if False:
        assert "{code}: never evaluated"


def test_probe_names_the_code_in_a_statement_that_does_nothing():
    x = 1
    "{code}: a string statement that is not the docstring"
    assert x


async def test_probe_names_the_code_in_a_coroutine():
    assert "{code}: pytest does not run this without a plugin"
'''
PROBE = "test_zz_binding_probe.py"
# A code the MAPPING keys a clause to (SPEC.md:58) both before and after the
# re-keying, so the builder test isolates the binding rule.
PROBE_CODE = "unsafe-bundle"


def _checker_sandbox(tmp_path, code):
    """The real SPEC, verifier and test files, plus one probe test file whose
    functions reference `code` in different places."""
    root = tmp_path / "repo"
    _copy_tools(root)
    for name in ("SPEC.md", "vac"):
        (root / name).symlink_to(ROOT / name)
    (root / "tests").mkdir()
    for p in sorted((ROOT / "tests").glob("test_*.py")):
        (root / "tests" / p.name).symlink_to(p)
    (root / "tests" / PROBE).write_text(
        BINDING_PROBE.replace("{code}", code), encoding="utf-8")
    return root


def _cite_probe(tmp_path, ledger, fn):
    root = _checker_sandbox(tmp_path, PROBE_CODE)
    d = copy.deepcopy(ledger)
    m = next(o for o in d["obligations"] if o["status"] == "mapped")
    m["refusal_site"] = PROBE_CODE
    m["evaluation_sites"] = [f"tests/{PROBE}::{fn}"]
    p = subprocess.run([sys.executable, str(root / "tools" / "check_obligations.py"),
                        "--ledger", str(write(tmp_path, d))],
                       capture_output=True, text=True, cwd=root)
    return p.returncode, p.stdout + p.stderr


@pytest.mark.parametrize("fn", ["test_probe_names_the_code_in_code",
                                "test_probe_names_the_code_in_a_decorator"])
def test_a_test_that_uses_the_code_binds(tmp_path, ledger, fn):
    """Liveness for the two refusals below: the sandbox is sound, and a code
    used in a test's body or decorators satisfies C3."""
    rc, out = _cite_probe(tmp_path, ledger, fn)
    assert rc == 0, out


@pytest.mark.parametrize("fn", ["test_probe_names_the_code_only_after_itself",
                                "test_probe_names_the_code_only_in_prose"])
def test_a_binding_through_a_comment_or_docstring_is_refused(tmp_path, ledger,
                                                             fn):
    """C3. A comment after the function, or prose inside it, names the code
    without the test doing anything with it."""
    rc, out = _cite_probe(tmp_path, ledger, fn)
    assert rc == 1
    assert f"does not reference refusal_site {PROBE_CODE!r}" in out


@pytest.mark.parametrize("fn", [
    "test_probe_names_the_code_as_a_skip_reason",
    "test_probe_names_the_code_as_an_xfail_reason",
    "test_probe_names_the_code_as_a_runtime_skip_reason",
    "test_probe_asserts_the_code_is_absent",
    "test_probe_names_the_code_in_a_branch_that_never_runs",
    "test_probe_names_the_code_in_a_statement_that_does_nothing",
])
def test_a_test_that_cannot_check_the_code_does_not_bind(tmp_path, ledger, fn):
    """C3. Each names the code inside the function, where the test can never
    act on it: why the test is skipped or expected to fail, a comparison that
    can only hold when the refusal is absent, a branch with a constant false
    condition, a string that is only a statement."""
    rc, out = _cite_probe(tmp_path, ledger, fn)
    assert rc == 1
    assert f"does not reference refusal_site {PROBE_CODE!r}" in out


def test_a_coroutine_is_not_a_site(tmp_path, ledger):
    """C2. pytest does not run an async test without a plugin, so it is not
    a site at all, whatever it asserts."""
    rc, out = _cite_probe(tmp_path, ledger,
                          "test_probe_names_the_code_in_a_coroutine")
    assert rc == 1
    assert "is not a module-level test function pytest runs" in out


def test_the_builder_binds_only_tests_that_use_the_code(tmp_path):
    """The builder applies the same rule as C3. The probe functions are the
    only tests in the sandbox, so every site the ledger derives for a code is
    one of them, and the ones that only mention it must not appear."""
    root = _checker_sandbox(tmp_path, PROBE_CODE)
    for p in (root / "tests").iterdir():
        if p.name != PROBE:
            p.unlink()
    rc, out = _run_builder(root)
    assert rc == 0, out
    built = json.loads((root / "obligations.json").read_text())
    sites = {s for o in built["obligations"]
             if o["refusal_site"] == PROBE_CODE
             for s in o["evaluation_sites"]}
    assert sites == {f"tests/{PROBE}::test_probe_names_the_code_in_code",
                     f"tests/{PROBE}::test_probe_names_the_code_in_a_decorator"}


def test_spec01_is_keyed_to_the_code_its_sentence_names(ledger):
    """SPEC.md:52-53: a file present but unlisted is `unlisted-file`. The entry
    was keyed to missing-artifact and cited a test about evalmut operators."""
    o = next(o for o in ledger["obligations"]
             if o["source_span"] == "SPEC.md:52")
    assert o["refusal_site"] == "unlisted-file"
    assert ("tests/test_verify.py::test_unlisted_file_breaks_closure"
            in o["evaluation_sites"])


def test_spec30_is_keyed_to_the_refusal_that_enforces_it(ledger):
    """SPEC.md:549 is the RESULTS.md byte-identity clause. vac/verify.py refuses
    a divergence as raw-aggregate-mismatch; `suite` is not a code at all."""
    o = next(o for o in ledger["obligations"]
             if o["source_span"] == "SPEC.md:549")
    assert o["refusal_site"] == "raw-aggregate-mismatch"
    assert o["property_token"] == (
        "modeldrift.results_md_byte_identical_to_rerender")
    assert o["evaluation_sites"][0] == (
        "tests/test_refusals_modeldrift_b.py::"
        "test_results_md_must_be_a_byte_identical_rerender_of_the_standings")


def test_the_json_nesting_clause_is_keyed_to_its_boundary_tests(ledger):
    """SPEC 4's nesting limit is refused as invalid-json, and the sites the
    ledger derives for it are the tests that pin the boundary."""
    [o] = [o for o in ledger["obligations"]
           if "nest deeper than 256 levels" in o["normative_text"]]
    assert o["refusal_site"] == "invalid-json"
    assert o["status"] == "mapped" and o["addressee"] == "verifier"
    assert ("tests/test_refusals_json_depth.py::"
            "test_a_manifest_one_level_past_the_limit_is_refused"
            in o["evaluation_sites"])


# ── the ledger read from the other side ─────────────────────────────────────
#
# Every check above reads forward, from a clause in SPEC.md to the refusal that
# enforces it, so none of them can see a refusal the ledger names nowhere. The
# size of that residue was a number in prose that nothing regenerated.
# tools/unkeyed_refusals.py enumerates it. These two run it against the
# COMMITTED verifier and the COMMITTED ledger, which is why they belong in this
# file: like everything else here they read vac/verify.py's emission sites, so
# a mutant turns them red without any bundle getting past the verifier, and the
# sweep deselects this file for exactly that reason.

REVERSE = ROOT / "tools" / "unkeyed_refusals.py"


def test_the_reverse_enumeration_runs_clean_on_the_committed_tree(tmp_path):
    """One run is three agreements: the sweep's EXCLUDE table matches the
    source as declared, the AST and the line pattern read the same appends,
    and the population is still the one the sweep pins. Any of the three
    failing makes every share the tool prints a figure about some other
    population."""
    out = tmp_path / "reverse.json"
    p = subprocess.run([sys.executable, str(REVERSE), "--json", str(out)],
                       capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "UNKEYED" in p.stdout
    assert json.loads(out.read_text())["scored"]["population"] > 0


def test_the_residue_is_the_emitted_codes_this_ledger_does_not_name(ledger,
                                                                    tmp_path):
    """The residue re-derived here from the same two artifacts. A tool that
    reported a smaller one would be publishing coverage the ledger does not
    have."""
    out = tmp_path / "reverse.json"
    subprocess.run([sys.executable, str(REVERSE), "--json", str(out)],
                   capture_output=True, text=True, cwd=ROOT, check=True)
    report = json.loads(out.read_text())
    emitted = _ledger_sources().refusal_codes(
        (ROOT / "vac" / "verify.py").read_text(encoding="utf-8"))
    named = {o["refusal_site"] for o in ledger["obligations"]
             if o["refusal_site"]}
    assert sorted(r["code"] for r in report["unkeyed"]["by_code"]) == sorted(
        set(emitted) - named)
    assert report["unkeyed"]["emissions"] == sum(
        len(lines) for code, lines in emitted.items() if code not in named)
    # Counted by code, and one code dominates it. The paper cannot quote the
    # residue as a count of uncovered rules while that is true.
    rows = sorted(report["unkeyed"]["by_code"], key=lambda r: -r["sites"])
    assert rows[0]["sites"] > sum(r["sites"] for r in rows[1:])
