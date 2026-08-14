"""The verifier must pass the one honest bundle and refuse every tamper —
each with its SPECIFIC named reason, not a generic red. A gate that cannot
name why it fired cannot be audited, and a gate that never fires cannot be
trusted, so both directions are pinned here: exact failure lists for the
committed tampered fixtures, and a repaired-tamper case proving the clean
path is reachable, not vacuous."""

from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile

import pytest

from vac.verify import _sha256, main, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"

# tampered fixture -> the exact failure list verify_bundle must return
TAMPERS = {
    "tamper-missing-artifact": ["missing-artifact: evidence/bundle.json"],
    "tamper-wrong-sha256": [
        "sha256-mismatch: evidence/bundle.json: manifest " + "0" * 64
        + ", file " + _sha256(FIX / "valid/evidence/bundle.json")],
    "tamper-verdict-count": ["summary-mismatch: fixed: declared 3, "
                             "recomputed 2",
                             "summary-outruns-checks: summary.fixed: "
                             "declares 3, recomputation gives 2"],
    "tamper-empty-limitations": ["empty-limitations"],
    "tamper-missing-issuer-commit": ["missing-issuer-commit"],
    "tamper-raw-aggregate": [
        "raw-aggregate-mismatch: toy-suite/toy-defect-b: "
        "detected declared 3, recomputed 2",
        "raw-aggregate-mismatch: toy-suite/toy-defect-b: "
        "detection_rate declared 0.75, recomputed 0.5"],
    "tamper-evalmut-summary": [
        "raw-aggregate-mismatch: evidence/evalmut_run.json: "
        "tally.caught declared 5, recomputed 4"],
    "tamper-evalmut-rows": [
        "raw-aggregate-mismatch: evidence/evalmut_run.json: "
        "tally.caught declared 4, recomputed 5",
        "raw-aggregate-mismatch: evidence/evalmut_run.json: "
        "tally.missed declared 2, recomputed 1",
        "raw-aggregate-mismatch: evidence/evalmut_run.json: score "
        "declared 0.5714285714285714, recomputed 0.7142857142857143",
        "raw-aggregate-mismatch: evidence/evalmut_run.json: holes.blind "
        "does not recompute from the rows (declared 1, recomputed 0)",
        "summary-mismatch: blind: declared 1, recomputed 0",
        "summary-mismatch: caught: declared 4, recomputed 5",
        "summary-mismatch: missed: declared 2, recomputed 1",
        "summary-mismatch: score_3: declared 0.571, recomputed 0.714",
        "summary-outruns-checks: summary.mutation_score_3: declares 0.571, "
        "no check recomputes it"],
    "tamper-crashkit-metrics": [
        "raw-aggregate-mismatch: evidence/eval_run.json: "
        "metrics.vulnerability_score declared 0.0909, recomputed 0.4545"],
    "tamper-modeldrift-rows": [
        "raw-aggregate-mismatch: evidence/standings.json: alpha:a1: acc "
        "declared 0.5, recomputed 0.75",
        "raw-aggregate-mismatch: evidence/standings.json: alpha:a1: delta "
        "declared -0.25, recomputed 0.0",
        "raw-aggregate-mismatch: evidence/standings.json: alpha:a1: "
        "verdict declared 'regressed', recomputed 'unchanged'",
        "raw-aggregate-mismatch: evidence/RESULTS.md: does not re-render "
        "byte-identically from the recomputed standings rows",
        "summary-mismatch: regressed: declared 1, recomputed 0",
        "summary-mismatch: unchanged: declared 1, recomputed 2",
        "summary-outruns-checks: summary.drift.regressed: declares 1, "
        "recomputation gives 0"],
    "tamper-modeldrift-standings": [
        "raw-aggregate-mismatch: evidence/standings.json: alpha:a1: delta "
        "declared 0.0, recomputed -0.25",
        "raw-aggregate-mismatch: evidence/standings.json: alpha:a1: "
        "verdict declared 'unchanged', recomputed 'regressed'"],
    "tamper-crashkit-case": [
        "raw-aggregate-mismatch: evidence/eval_run.json: case 2 flagged "
        "flag contradicts its own passed/truncated pair",
        "raw-aggregate-mismatch: evidence/eval_run.json: "
        "metrics.faithfulness declared 0.5, recomputed 0.75",
        "raw-aggregate-mismatch: evidence/eval_run.json: "
        "metrics.precision@k declared 0.5, recomputed 0.75",
        "raw-aggregate-mismatch: evidence/eval_run.json: "
        "metrics.recall@k declared 0.5, recomputed 0.75",
        "raw-aggregate-mismatch: evidence/eval_run.json: "
        "metrics.citation_rate declared 0.5, recomputed 0.75",
        "raw-aggregate-mismatch: evidence/eval_run.json: "
        "metrics.vulnerability_score declared 0.4545, recomputed 0.0909",
        "raw-aggregate-mismatch: evidence/eval_run.json: "
        "per_kind['prompt-injection'] declared 0.5, recomputed 1.0",
        "summary-mismatch: accuracy: declared 0.5, recomputed 0.75",
        "summary-mismatch: vulnerability_score: declared 0.4545, "
        "recomputed 0.0909",
        "summary-outruns-checks: summary.crash_vulnerability: declares "
        "0.4545, no check recomputes it"],
    # summary-only cooks: checks, artifacts, and hashes all honest — only
    # SPEC.md §2.5 recomputation names these
    "tamper-summary-fixed": ["summary-outruns-checks: summary.fixed: "
                             "declares 3, recomputation gives 2"],
    "tamper-summary-rate": ["summary-outruns-checks: "
                            "summary.detection_rate_min: declares 0.9, "
                            "no check recomputes it"],
    "tamper-summary-score": ["summary-outruns-checks: "
                             "summary.mutation_score_3: declares 0.714, "
                             "no check recomputes it"],
}


def _rehash(bundle: pathlib.Path, rel: str) -> None:
    man_path = bundle / "vac.json"
    man = json.loads(man_path.read_text())
    for e in man["evidence"]:
        if e["path"] == rel:
            e["sha256"] = _sha256(bundle / rel)
    man_path.write_text(json.dumps(man, indent=1) + "\n")


def test_valid_bundle_passes():
    assert verify_bundle(FIX / "valid") == []


def test_valid_bundle_exit_zero_and_prints_the_distinction(capsys):
    assert main([str(FIX / "valid")]) == 0
    out = capsys.readouterr().out
    assert "structural verification: PASS" in out
    assert "semantic replay: NOT run by this tool" in out
    assert "$ git clone" in out  # the replay recipe is surfaced, not implied


@pytest.mark.parametrize("name,expected", sorted(TAMPERS.items()))
def test_tampered_bundle_fails_with_its_named_reasons(name, expected):
    assert verify_bundle(FIX / name) == expected


@pytest.mark.parametrize("name", sorted(TAMPERS))
def test_tampered_bundle_exits_nonzero(name, capsys):
    assert main([str(FIX / name)]) == 1
    assert "structural verification: FAIL" in capsys.readouterr().out


def test_repaired_raw_aggregate_passes(tmp_path):
    """The fleet clean path is live, not vacuously green: undo the cooked
    row, rehash, and the exact same bundle verifies clean."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "tamper-raw-aggregate", b)
    agg_path = b / "evidence/results.json"
    agg = json.loads(agg_path.read_text())
    row = next(r for r in agg["rows"] if r["member"] == "toy-defect-b")
    row["detected"], row["detection_rate"] = 2, 0.5
    agg_path.write_text(json.dumps(agg, indent=1) + "\n")
    _rehash(b, "evidence/results.json")
    assert verify_bundle(b) == []


def test_repaired_crashkit_case_passes(tmp_path):
    """The crashkit clean path is live too: relabel the cooked case back,
    rehash, and the exact same bundle verifies clean."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "tamper-crashkit-case", b)
    art = b / "evidence/eval_run.json"
    cp = json.loads(art.read_text())
    c = next(c for c in cp["cases"] if c["flagged"])
    c["passed"] = False
    art.write_text(json.dumps(cp, indent=1) + "\n")
    _rehash(b, "evidence/eval_run.json")
    assert verify_bundle(b) == []


def test_crashkit_refuses_a_case_without_explicit_booleans(tmp_path):
    """A payload whose flags a verifier would have to parse out of the
    free-text note is a declaration, not evidence — the profile refuses
    it by name rather than guessing."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    art = b / "evidence/eval_run.json"
    cp = json.loads(art.read_text())
    del cp["cases"][2]["passed"]
    art.write_text(json.dumps(cp, indent=1) + "\n")
    _rehash(b, "evidence/eval_run.json")
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/eval_run.json: case 3 lacks the "
        "explicit passed/truncated/flagged booleans + kind "
        "(crashkit-battery-v1 refuses note-parsing)"]


def test_crashkit_battery_fingerprint_is_bound(tmp_path):
    """battery_hash_key binds the artifact's git_sha to the named
    protocol.hashes entry — a battery swapped under a pinned claim is a
    stamp mismatch, not a silently re-scoped claim."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    man["protocol"]["hashes"]["crash_battery_hash"] = "deadbeef0000"
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(b) == [
        "stamp-mismatch: crash_battery_hash: protocol deadbeef0000, "
        "artifact ab12cd34ef56"]


def test_repaired_modeldrift_standings_passes(tmp_path):
    """The drift clean path is live too: relabel the cooked standings row
    back, rehash, and the exact same bundle verifies clean."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "tamper-modeldrift-standings", b)
    art = b / "evidence/standings.json"
    ds = json.loads(art.read_text())
    row = next(r for r in ds["rows"] if r["id"] == "alpha:a1")
    row["delta"], row["verdict"] = -0.25, "regressed"
    art.write_text(json.dumps(ds, indent=1) + "\n")
    _rehash(b, "evidence/standings.json")
    assert verify_bundle(b) == []


def test_modeldrift_mock_control_must_not_move(tmp_path):
    """The live null control, enforced: a mock point carrying a failure
    indicts the harness, not the models — the check names it and refuses
    to derive anything from rows like that (so the one message is the
    whole verdict, not the head of a cascade)."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    art = b / "evidence/metrics.json"
    dm = json.loads(art.read_text())
    dm["series"]["mock:stable"][-1]["fails"] = ["t-add"]
    art.write_text(json.dumps(dm, indent=1) + "\n")
    _rehash(b, "evidence/metrics.json")
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/metrics.json: mock:stable[2]: "
        "the deterministic control moved (acc 1.0, fails ['t-add'])"]


def test_modeldrift_narrative_text_must_match_its_html(tmp_path):
    """Narrative internal coherence: the plain-text mirror must be exactly
    the whitespace-normalized, tag-stripped html — a sweetened text copy
    is named, not passed through as prose."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    art = b / "evidence/narrative.json"
    narr = json.loads(art.read_text())
    narr["text"] += " (all models improved)"
    art.write_text(json.dumps(narr, indent=1) + "\n")
    _rehash(b, "evidence/narrative.json")
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/narrative.json: text is not the "
        "whitespace-normalized, tag-stripped html"]


def test_modeldrift_input_bytes_are_pinned(tmp_path):
    """metrics_sha256/registry_sha256 bind the derivations to the exact
    input bytes they were run over — a protocol stamp that disagrees with
    the evidence hash is a stamp mismatch."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    man["protocol"]["hashes"]["registry_sha256"] = "0" * 64
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(b) == [
        "stamp-mismatch: registry_sha256: protocol " + "0" * 64
        + ", artifact " + _sha256(FIX / "valid/evidence/models.json")]


MODELDRIFT_BUNDLE = (ROOT / (os.environ.get("VAC_MODELDRIFT_CHECKOUT")
                             or "../model-drift")).resolve() / "vac"


@pytest.mark.skipif(not (MODELDRIFT_BUNDLE / "vac.json").is_file(),
                    reason="model-drift issuer checkout not present")
def test_real_modeldrift_bundle_summary_is_enforced(tmp_path):
    """Same hole, closed on the REAL committed drift bundle: inflate one
    headline number in results.summary, leave checks and artifacts honest,
    and the verifier must name the outrun — while the untampered copy
    still verifies clean. The tamper is relative to the committed value,
    so the test survives the issuer's daily bundle supersession."""
    b = tmp_path / "b"
    shutil.copytree(MODELDRIFT_BUNDLE, b)
    assert verify_bundle(b) == []
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    v = man["results"]["summary"]["flips"]["probe_alarms"]
    man["results"]["summary"]["flips"]["probe_alarms"] = v + 1
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(b) == [
        "summary-outruns-checks: summary.flips.probe_alarms: "
        f"declares {v + 1}, recomputation gives {v}"]


def test_repaired_evalmut_rows_passes(tmp_path):
    """The evalmut clean path is live too: relabel the cooked row back,
    rehash, and the exact same bundle verifies clean."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "tamper-evalmut-rows", b)
    art = b / "evidence/evalmut_run.json"
    mp = json.loads(art.read_text())
    r = next(r for r in mp["results"] if r["operator_id"] == "toy-negate")
    r["outcome"] = "missed"
    art.write_text(json.dumps(mp, indent=1) + "\n")
    _rehash(b, "evidence/evalmut_run.json")
    assert verify_bundle(b) == []


EVALMUT_BUNDLE = (ROOT / (os.environ.get("VAC_EVALMUT_CHECKOUT")
                          or "../evalmut")).resolve() / "vac"


@pytest.mark.skipif(not (EVALMUT_BUNDLE / "vac.json").is_file(),
                    reason="evalmut issuer checkout not present")
def test_real_evalmut_bundle_summary_is_enforced(tmp_path):
    """The hole an adversarial verifier demonstrated live, closed on the
    REAL committed bundle: inflate one headline number in results.summary,
    leave checks and artifacts honest (vac.json is never its own evidence,
    so every hash stays clean), and the verifier must name the outrun —
    while the untampered copy still verifies clean."""
    b = tmp_path / "b"
    shutil.copytree(EVALMUT_BUNDLE, b)
    assert verify_bundle(b) == []
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    man["results"]["summary"]["dogfood_gradecore"]["caught"] = 33
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(b) == [
        "summary-outruns-checks: summary.dogfood_gradecore.caught: "
        "declares 33, recomputation gives one of [5, 32]"]


CRASHKIT_BUNDLE = (ROOT / (os.environ.get("VAC_CRASHKIT_CHECKOUT")
                           or "../crashkit")).resolve() / "vac"


@pytest.mark.skipif(not (CRASHKIT_BUNDLE / "vac.json").is_file(),
                    reason="crashkit issuer checkout not present")
def test_real_crashkit_bundle_summary_is_enforced(tmp_path):
    """Same hole, closed on the REAL committed crashkit bundle: sweeten
    one twin-control headline in results.summary, leave checks and
    artifacts honest, and the verifier must name the outrun — while the
    untampered copy still verifies clean."""
    b = tmp_path / "b"
    shutil.copytree(CRASHKIT_BUNDLE, b)
    assert verify_bundle(b) == []
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    man["results"]["summary"]["twin_controls"]["adversarial"][
        "safe_vulnerability"] = 0.5
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(b) == [
        "summary-outruns-checks: "
        "summary.twin_controls.adversarial.safe_vulnerability: "
        "declares 0.5, no check recomputes it"]


def test_evalmut_refuses_a_payload_without_rows(tmp_path):
    """An aggregate with `results: null` (no --all) is a declaration, not
    evidence — nothing is recomputable and the profile says so."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    art = b / "evidence/evalmut_run.json"
    mp = json.loads(art.read_text())
    mp["results"] = None
    art.write_text(json.dumps(mp, indent=1) + "\n")
    _rehash(b, "evidence/evalmut_run.json")
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/evalmut_run.json: no results[] "
        "array (evalmut-run-v1 requires the --json --all payload)"]


def test_evalmut_rows_are_bound_to_the_catalog(tmp_path):
    """A row must agree with the operator battery it claims to be drawn
    from — reclassifying an operator in the catalog contradicts every row
    that used it."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    cat_path = b / "evidence/operators.json"
    cat = json.loads(cat_path.read_text())
    next(o for o in cat if o["id"] == "toy-negate")["op_type"] = "diagnostic"
    cat_path.write_text(json.dumps(cat, indent=1) + "\n")
    _rehash(b, "evidence/operators.json")
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/evalmut_run.json: row 5 op_type "
        "'kill' contradicts the catalog's 'diagnostic'"]


def test_evalmut_row_outcome_must_match_its_polarity(tmp_path):
    """Outcome semantics are internal to each row: a MISSED on an
    'equivalent' row is incoherent, and the holes multiset comparison
    catches content drift even when the counts still agree."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    art = b / "evidence/evalmut_run.json"
    mp = json.loads(art.read_text())
    r = next(r for r in mp["results"] if r["operator_id"] == "toy-negate")
    r["polarity"] = "equivalent"
    art.write_text(json.dumps(mp, indent=1) + "\n")
    _rehash(b, "evidence/evalmut_run.json")
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/evalmut_run.json: row 5 outcome "
        "'missed' contradicts its polarity 'equivalent'",
        "raw-aggregate-mismatch: evidence/evalmut_run.json: holes.blind "
        "does not recompute from the rows (declared 1, recomputed 1)",
        "raw-aggregate-mismatch: evidence/evalmut_run.json: row 5 "
        "polarity 'equivalent' contradicts the catalog's 'defect'"]


def test_unlisted_file_breaks_closure(tmp_path):
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    (b / "evidence/extra.txt").write_text("smuggled\n")
    assert verify_bundle(b) == ["unlisted-file: evidence/extra.txt"]


def test_missing_manifest(tmp_path):
    assert verify_bundle(tmp_path) == ["missing-manifest: no vac.json "
                                       "in bundle"]


def test_invalid_json_manifest(tmp_path):
    (tmp_path / "vac.json").write_text("{not json")
    failures = verify_bundle(tmp_path)
    assert len(failures) == 1 and failures[0].startswith("invalid-json:")


def test_unknown_profile_is_named(tmp_path):
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    man["results"]["checks"][0]["profile"] = "llm-judge-v9"
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(b) == [
        "unknown-profile: results.checks[0]: 'llm-judge-v9'"]


def test_stamp_mismatch_binds_protocol_to_artifacts(tmp_path):
    """protocol.issuer_commit and the artifact's own stamp must be ONE
    commit — a bundle graded at one commit and replayed at another is not
    replayable evidence."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    art = b / "evidence/bundle.json"
    data = json.loads(art.read_text())
    data["harness_commit"] = "0000000"
    art.write_text(json.dumps(data, indent=1) + "\n")
    _rehash(b, "evidence/bundle.json")
    assert verify_bundle(b) == [
        "stamp-mismatch: harness_commit: protocol f1e2d3c, "
        "artifact 0000000"]


def test_wrong_vac_version_is_refused(tmp_path):
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    man["vac_version"] = "0.2"
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    failures = verify_bundle(b)
    assert failures == ["schema-violation: vac_version: must be '0.1', "
                        "got '0.2'"]


def test_tarball_roundtrip(tmp_path, capsys):
    tar = tmp_path / "valid.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        tf.add(FIX / "valid", arcname="valid")
    assert main([str(tar)]) == 0
    assert "structural verification: PASS" in capsys.readouterr().out


def test_tarball_rejects_traversal(tmp_path, capsys):
    tar = tmp_path / "evil.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))
    assert main([str(tar)]) == 1
    assert "FAIL unsafe-archive:" in capsys.readouterr().out


def test_usage_error_is_exit_2(capsys):
    assert main([]) == 2
    assert main([str(FIX / "no-such-bundle")]) == 2


def test_fixtures_regenerate_byte_identically(tmp_path):
    """The committed fixtures ARE a fresh deterministic generation — no
    hand edits, no timestamps, nothing unreproducible smuggled in."""
    subprocess.run(
        [sys.executable, str(FIX / "make_fixtures.py"), str(tmp_path)],
        check=True, capture_output=True)
    committed = {p.relative_to(FIX).as_posix(): p.read_bytes()
                 for p in FIX.rglob("*")
                 if p.is_file() and p.name != "make_fixtures.py"}
    fresh = {p.relative_to(tmp_path).as_posix(): p.read_bytes()
             for p in tmp_path.rglob("*") if p.is_file()}
    assert committed == fresh
