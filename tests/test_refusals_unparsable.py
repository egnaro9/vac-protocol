"""Artifacts that are present and byte-honest can still carry nothing worth
verifying. A hash pins WHICH bytes were graded, never that those bytes are
the payload the profile promised — so every profile checker also has to
refuse a structurally wrong artifact BY NAME, and refuse it before it
recomputes anything from the hole where the evidence should have been.

These pin the `artifact-unparsable:` refusals of the certlab, fleet,
evalmut, and crashkit checkers. Each test asserts the exact failure list
(the specific reason, not a substring of a long one), because the whole
point of the refusal is that it names itself."""

from __future__ import annotations

import json
import pathlib
import shutil

from vac.verify import _sha256, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"


def _bundle(tmp_path: pathlib.Path) -> pathlib.Path:
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    return b


def _rehash(bundle: pathlib.Path, rel: str) -> None:
    """Re-pin an artifact's sha256 honestly, so the bundle fails on the
    STRUCTURE under test and not on a stale hash."""
    man_path = bundle / "vac.json"
    man = json.loads(man_path.read_text())
    for e in man["evidence"]:
        if e["path"] == rel:
            e["sha256"] = _sha256(bundle / rel)
    man_path.write_text(json.dumps(man, indent=1) + "\n")


def _edit(bundle: pathlib.Path, rel: str, fn) -> None:
    art = bundle / rel
    data = json.loads(art.read_text())
    fn(data)
    art.write_text(json.dumps(data, indent=1) + "\n")
    _rehash(bundle, rel)


def test_load_json_names_the_artifact_it_could_not_parse(tmp_path):
    """Bytes that are not JSON at all: the refusal must name the artifact
    and carry the decoder's own complaint, not degrade to the generic
    fail-closed 'check contributed no recomputation'."""
    b = _bundle(tmp_path)
    (b / "evidence/bundle.json").write_text("{ this is not json\n")
    _rehash(b, "evidence/bundle.json")
    out = verify_bundle(b)
    prefix = "artifact-unparsable: evidence/bundle.json: "
    assert len(out) == 1, out
    assert out[0].startswith(prefix) and out[0][len(prefix):].strip(), out


def test_certlab_refuses_a_payload_with_no_verdicts_array(tmp_path):
    """Parseable JSON carrying no verdicts[] recomputes to zeros rather
    than to nothing — the counts must not be earned from an absent list."""
    b = _bundle(tmp_path)
    _edit(b, "evidence/bundle.json", lambda d: d.pop("verdicts"))
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/bundle.json: no verdicts[] array"]


def test_fleet_refuses_unparsable_raw_lines(tmp_path):
    """The raw jsonl is the only thing the aggregate is re-earned FROM; a
    line that does not parse must stop the check by name."""
    b = _bundle(tmp_path)
    raw = b / "evidence/raw_results.jsonl"
    raw.write_text(raw.read_text() + '{"suite": "toy-suite", oops}\n')
    _rehash(b, "evidence/raw_results.jsonl")
    out = verify_bundle(b)
    prefix = "artifact-unparsable: evidence/raw_results.jsonl: "
    assert len(out) == 1, out
    assert out[0].startswith(prefix) and out[0][len(prefix):].strip(), out


def test_fleet_refuses_an_aggregate_with_no_rows_array(tmp_path):
    """No rows[] means every declared board row is unopposed; the checker
    must say so instead of iterating an empty comparison."""
    b = _bundle(tmp_path)
    _edit(b, "evidence/results.json", lambda d: d.pop("rows"))
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/results.json: no rows[] array"]


def test_evalmut_refuses_a_payload_with_no_tally_object(tmp_path):
    """Deleting the tally deletes the thing the rows are checked against.
    Absence must cost what a wrong tally costs."""
    b = _bundle(tmp_path)
    _edit(b, "evidence/evalmut_run.json", lambda d: d.pop("tally"))
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/evalmut_run.json: no tally object"]


def test_evalmut_refuses_a_payload_with_no_holes_object(tmp_path):
    """The holes ARE the finding of a mutation run; a payload that ships
    without them is refused, not scored as a run with no holes."""
    b = _bundle(tmp_path)
    _edit(b, "evidence/evalmut_run.json", lambda d: d.pop("holes"))
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/evalmut_run.json: no holes object"]


def test_evalmut_refuses_a_catalog_holding_a_non_object(tmp_path):
    """The catalog is a list of operator records. A bare scalar riding in
    the list has no id to bind a row to, so the whole catalog binding is
    refused — and `operators` then stops being recomputable at all."""
    b = _bundle(tmp_path)
    _edit(b, "evidence/operators.json", lambda d: d.append("toy-blank"))
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/operators.json: no operator array",
        "summary-mismatch: operators: not recomputable under evalmut-run-v1"]


def test_evalmut_refuses_a_catalog_entry_without_mined_provenance(tmp_path):
    """real_origin is what makes the battery MINED rather than asserted;
    an entry missing it is named with its own index."""
    b = _bundle(tmp_path)
    _edit(b, "evidence/operators.json", lambda d: d[0].pop("real_origin"))
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/operators.json: catalog entry 1 lacks "
        "a non-empty id/real_origin — the battery must be mined, not "
        "asserted",
        "summary-mismatch: operators: not recomputable under evalmut-run-v1"]


def test_evalmut_refuses_duplicate_operator_ids(tmp_path):
    """Two entries under one id make the operator count a free parameter:
    the catalog can be padded while every row still resolves. Refuse the
    ambiguity rather than picking a winner."""
    b = _bundle(tmp_path)
    _edit(b, "evidence/operators.json", lambda d: d.append(dict(d[0])))
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/operators.json: duplicate operator ids",
        "summary-mismatch: operators: not recomputable under evalmut-run-v1"]


def test_crashkit_refuses_a_payload_with_no_cases_array(tmp_path):
    """Without the per-case rows the metrics block is a declaration; the
    profile refuses it before recomputing anything."""
    b = _bundle(tmp_path)
    _edit(b, "evidence/eval_run.json", lambda d: d.pop("cases"))
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/eval_run.json: no cases[] array"]


def test_crashkit_refuses_a_payload_with_no_metrics_object(tmp_path):
    """Deleting metrics deletes every comparison the case rows would have
    lost — absence must be as loud as a cooked number."""
    b = _bundle(tmp_path)
    _edit(b, "evidence/eval_run.json", lambda d: d.pop("metrics"))
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/eval_run.json: no metrics object"]


def test_crashkit_refuses_a_payload_with_no_per_kind_object(tmp_path):
    """per_kind is the only place a single collapsed kind would show; its
    absence is refused rather than treated as 'no kinds to check'."""
    b = _bundle(tmp_path)
    _edit(b, "evidence/eval_run.json", lambda d: d.pop("per_kind"))
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/eval_run.json: no per_kind object"]


def test_crashkit_refuses_a_severity_outside_the_frozen_table(tmp_path):
    """Re-casing a graded case's severity would silently drop it to weight
    0 and divide the vulnerability score toward a clean, false number
    through the ordinary arithmetic path. The label itself is refused."""
    b = _bundle(tmp_path)

    def recase(d):
        d["cases"][0]["severity"] = "Critical"

    _edit(b, "evidence/eval_run.json", recase)
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/eval_run.json: severity 'Critical' "
        "outside the profile's frozen table (none/low/med/high/critical)"]
