"""The obligation ledger held to the standard it exists to impose.

A coverage ledger nobody can fail is a worse artifact than no ledger, because it
converts an unexamined claim into a published number. Every test here mutates a
copy of obligations.json and asserts the checker REFUSES it. The positive case
is one line; the negatives are the point.
"""
from __future__ import annotations

import copy
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
    """SPEC-39 is the one verifier obligation that is not fully mapped. If that
    stops being true the paper's sentence changes, so it fails here first."""
    partial = sorted(o["obligation_id"] for o in ledger["obligations"]
                     if o["addressee"] == "verifier" and o["status"] == "partially_mapped")
    assert partial == ["SPEC-39"], partial


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


def test_the_builder_refuses_an_ambiguous_prefix_with_no_adjudication():
    """Builder-side guard: dropping the adjudication must not fall back to a guess."""
    src = ROOT / "tools" / "build_obligations.py"
    original = src.read_text()
    mutated = original.replace('109:(None,"protocol.grading.describes_deterministic_process","unmeasured"',
                               '109:(None,"protocol.grading.describes_deterministic_process","unmeasured"', 1)
    # remove the trailing adjudication on the SPEC-03 row
    mutated = re.sub(r'(109:\(None,"protocol\.grading[^\n]*?),"reviewer"\),', r'\1),', mutated)
    assert mutated != original, "could not locate the SPEC-03 adjudication to remove"
    ledger_before = LEDGER.read_bytes()
    try:
        src.write_text(mutated)
        p = subprocess.run([sys.executable, str(src)], capture_output=True, text=True, cwd=ROOT)
        assert p.returncode != 0, "builder accepted an ambiguous prefix with no adjudication"
        assert "no explicit addressee adjudication" in (p.stdout + p.stderr)
    finally:
        src.write_text(original)
        LEDGER.write_bytes(ledger_before)
    assert src.read_text() == original
    assert LEDGER.read_bytes() == ledger_before
