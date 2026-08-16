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

from vac.registry import ISSUERS
from vac.verify import _sha256, _todo_failures, main, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"

# The 16 reasons a fresh draft carries — vac.draft's own output over the
# valid bundle's artifacts, every judgment field an unauthored marker.
DRAFT_REASONS = [
    f"draft-incomplete: {p} is an unauthored TODO" for p in (
        "claim.capability", "claim.limitations[0]", "claim.scope",
        "protocol.control_policy", "protocol.grading",
        "protocol.hashes.TODO", "protocol.task",
        "replay.commands[2]", "replay.commands[3]", "replay.expected",
        "results.checks[0].TODO", "results.checks[0].profile",
        "results.summary.TODO",
        "subject.id", "subject.kind", "subject.version.TODO")]

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
    # the drafted-but-unfinished bundle: mechanical fields honest (every
    # hash real, issuer and commit derived), judgment unauthored — refused
    # wholesale, one named reason per marker
    "tamper-draft-incomplete": DRAFT_REASONS,
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
    # KNOWN GAP, surfaced by the evidence-unchecked rule when it was added:
    # this bundle pins two artifacts no check reads. Assert the gap EXACTLY
    # rather than relaxing the rule, so the day the emitter covers them this
    # line fails loudly instead of the baseline quietly drifting.
    assert verify_bundle(b) == [EVALMUT_UNCHECKED]
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    man["results"]["summary"]["dogfood_gradecore"]["caught"] = 33
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(b) == [
        EVALMUT_UNCHECKED,
        "summary-outruns-checks: summary.dogfood_gradecore.caught: "
        "declares 33, recomputation gives one of [5, 32]"]


CRASHKIT_BUNDLE = (ROOT / (os.environ.get("VAC_CRASHKIT_CHECKOUT")
                           or "../crashkit")).resolve() / "vac"

# The two live bundles each pin evidence no check reads. These constants name
# that gap so the tests assert the TRUE current state; delete them (and the
# assertions that use them) once the issuers cover the artifacts.
EVALMUT_UNCHECKED = ("evidence-unchecked: dogfood_gradecore.txt, "
                     "promptfoo_findings.txt: listed in evidence but read by "
                     "no check")



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


def test_draft_refusal_preempts_every_other_check(tmp_path):
    """A draft is a workpiece, not a claim: even with an artifact tampered
    under it, the verifier names ONLY the unauthored markers — nothing
    else about a draft is worth naming until it is authored (and the
    refusal is a refusal either way, so nothing is hidden by it)."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "tamper-draft-incomplete", b)
    (b / "evidence/bundle.json").write_text("{\"cooked\": true}\n")
    assert verify_bundle(b) == DRAFT_REASONS


def test_todo_scan_liveness():
    """The absence assertion below is only meaningful if the scan can
    fire: on the committed draft fixture it names all 16 markers."""
    man = json.loads(
        (FIX / "tamper-draft-incomplete/vac.json").read_text())
    assert _todo_failures(man) == DRAFT_REASONS


def _real_bundles() -> list:
    """(name, bundle-dir) for every accepted registry entry, resolved
    through the same checkout configuration the registry generator uses."""
    checkouts = {}
    for cfg in ISSUERS:
        issuer = "/".join(cfg["repo"].rstrip("/").split("/")[-2:])
        checkouts[issuer] = (ROOT / (os.environ.get(cfg["checkout_env"])
                                     or cfg["default_checkout"])).resolve()
    doc = json.loads((ROOT / "registry.json").read_text())
    return [pytest.param(e["name"],
                         checkouts[e["issuer"]] / e["bundle_path"],
                         id=e["name"])
            for e in doc["entries"]]


@pytest.mark.parametrize("name,bundle", _real_bundles())
def test_real_bundles_carry_no_todo_markers(name, bundle):
    """The draft gate must be unable to fire on any accepted real bundle:
    none contains a TODO( marker anywhere in its manifest (liveness for
    this absence assertion is test_todo_scan_liveness above)."""
    if not (bundle / "vac.json").is_file():
        pytest.skip(f"issuer checkout not present for {name}")
    man = json.loads((bundle / "vac.json").read_text())
    assert _todo_failures(man) == []


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


# ---------------------------------------------------------------------------
# Adversarial audit: each test below reproduces a bundle that the
# verifier accepted while its declared numbers were false, or a
# path that escaped the bundle. Every one FAILS against the
# pre-fix verifier.

BS = chr(92)


def _man_edit(b, fn):
    p = b / "vac.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    fn(m)
    p.write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")


def _art_edit(b, rel, fn):
    p = b / rel
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    _rehash(b, rel)


def test_a_check_that_is_not_an_object_is_refused(tmp_path):
    """V-001. A bare profile-name STRING satisfied the schema pass, then
    _coherence skipped it as 'already named as unknown-profile' having named
    nothing. No profile ran, the pool stayed empty, and `if complete and pools`
    switched off the SPEC 2.5 outrun rule with it: a total bypass."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    _man_edit(b, lambda m: m["results"].update(
        checks=["certlab-bundle-v1"], summary={"verdicts": 9999}))
    out = verify_bundle(b)
    assert "schema-violation: results.checks[0]: object required" in out


def test_a_null_artifact_is_named_not_silently_skipped(tmp_path):
    """V-002. _load_json returned None for both "parse failed" and "the content
    is the literal null", and only the first named a reason. The silent path
    set `complete = False` with nothing to show for it.

    Note what this does NOT claim: SPEC 2.5 enforcement is still gated on
    `complete and pools`, so the planted summary number below is still not
    named. That gate is V-034, a separate protocol question left to the
    maintainer. What is fixed here is only the silent skip."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    (b / "evidence/bundle.json").write_bytes(b"null")
    _rehash(b, "evidence/bundle.json")
    _man_edit(b, lambda m: m["results"]["summary"].update(verdicts=99999))
    out = verify_bundle(b)
    assert any("artifact-unparsable: evidence/bundle.json" in x for x in out)
    assert out != []


def test_fleet_commit_hash_stamp_must_match_the_aggregate(tmp_path):
    """V-004. SPEC 3.2 binds the aggregate's fleet_commit to BOTH
    protocol.issuer_commit AND protocol.hashes.fleet_commit; 2.3 makes every
    hash named in protocol.hashes equal its counterpart. Only the first
    existed, so protocol.hashes.fleet_commit was a pin nothing read."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    _man_edit(b, lambda m: m["protocol"]["hashes"].update(
        fleet_commit="0000000"))
    assert verify_bundle(b) == [
        ("stamp-mismatch: hashes.fleet_commit: protocol 0000000, "
         "artifact f1e2d3c")]


def test_failure_mode_cannot_widen_the_summary_pool(tmp_path):
    """V-005. failure_mode is issuer free text and became a summary-pool key
    directly, letting the issuer redefine what a headline of that name is held
    to. Setting it to 'fixed' on every verdict made summary.fixed = 3 verify
    clean while the honest recomputation is 2."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    def _tag(d):
        for v in d["verdicts"]:
            v["failure_mode"] = "fixed"

    _art_edit(b, "evidence/bundle.json", _tag)
    _man_edit(b, lambda m: m["results"]["summary"].update(fixed=3))
    assert any("summary" in x and "fixed" in x for x in verify_bundle(b))


def test_a_drive_anchored_evidence_path_is_refused(tmp_path):
    """V-006. _safe_relpath vetted with PurePosixPath, for which 'C:/Windows/
    win.ini' is not absolute; but `bundle / that` on Windows DISCARDS the
    bundle root, so the verifier hashed a file outside the bundle and printed
    its sha256: an arbitrary-read and content-confirmation oracle."""
    from vac.verify import _safe_relpath
    assert not _safe_relpath("C:/Windows/win.ini")
    assert not _safe_relpath("C:evil")
    assert not _safe_relpath("evidence/\x1b[2Kspoof.json")
    assert _safe_relpath("evidence/bundle.json")


def test_duplicate_aggregate_rows_are_refused(tmp_path):
    """V-023. Coverage was checked with a SET, so duplicate (suite, member)
    rows were each validated against the same raw group and never named, while
    expect.rows compares against len(rows). SPEC 3.2 requires exact cover."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    _art_edit(b, "evidence/results.json",
              lambda d: d["rows"].extend(json.loads(json.dumps(d["rows"]))))
    assert any("duplicate aggregate row" in x for x in verify_bundle(b))


def _tar_with_raw_member(tar_path, raw_name, payload=b"OWNED"):
    """Write a tar whose member NAME is exactly raw_name.

    tarfile.add(arcname=...) normalizes the name (it strips a drive and folds
    backslashes), so a test built with add() silently exercises the POSIX
    shape that was already rejected. A real attacker writes the header
    directly, which is what TarInfo + addfile does.
    """
    with tarfile.open(tar_path, "w:gz") as tf:
        ti = tarfile.TarInfo(name=raw_name)
        ti.size = len(payload)
        tf.addfile(ti, io.BytesIO(payload))


def test_a_tar_cannot_smuggle_files_beside_the_bundle_root(tmp_path):
    """V-007. _bundle_root counted only DIRECTORIES, so an archive holding
    my-claim/ plus a top-level sibling FILE still resolved the root to
    my-claim/ and the closure scan never saw the sibling."""
    tar = tmp_path / "b.tar.gz"
    smuggled = tmp_path / "SMUGGLED.json"
    smuggled.write_text('{"payload": "never listed, never hashed"}')
    with tarfile.open(tar, "w:gz") as tf:
        tf.add(FIX / "valid", arcname="my-claim")
        tf.add(smuggled, arcname="SMUGGLED.json")
    from vac.verify import _extract_tar
    td = tmp_path / "x"
    td.mkdir()
    with pytest.raises(ValueError, match="beside the bundle root"):
        _extract_tar(tar, td)


def test_a_windows_separator_tar_member_is_refused(tmp_path):
    """V-018. _extract_tar vetted only with PurePosixPath, for which the
    single-component name r"..\\..\\evil.txt" has no ".." part, so the
    member was accepted. On pythons inside the project's declared
    requires-python window that lack tarfile's filter= kwarg, the fallback
    then extracts it UNFILTERED and it lands outside the destination: an
    arbitrary file write from verifying an untrusted bundle."""
    from vac.verify import _extract_tar
    tar = tmp_path / "evil.tar.gz"
    _tar_with_raw_member(tar, ".." + BS + ".." + BS + "evil.txt")
    with tarfile.open(tar) as tf:  # the raw name survived into the header
        assert BS in tf.getmembers()[0].name
    dest = tmp_path / "d"
    dest.mkdir()
    with pytest.raises(ValueError):
        _extract_tar(tar, dest)


def test_a_drive_letter_tar_member_is_refused(tmp_path):
    """V-018, second accepted shape: a drive-anchored member name."""
    from vac.verify import _extract_tar
    tar = tmp_path / "evil2.tar.gz"
    _tar_with_raw_member(tar, "C:/evil.txt")
    dest = tmp_path / "d2"
    dest.mkdir()
    with pytest.raises(ValueError):
        _extract_tar(tar, dest)


def test_an_empty_tar_member_name_is_refused(tmp_path):
    """A member named "" or "." passed the vetting loop (no ".." part, not
    absolute) and then raised an OSError out of extractall, which main did
    not catch."""
    from vac.verify import _extract_tar
    for name in ("", "."):
        tar = tmp_path / f"m{len(name)}.tar.gz"
        _tar_with_raw_member(tar, name)
        dest = tmp_path / f"d{len(name)}"
        dest.mkdir()
        with pytest.raises(ValueError):
            _extract_tar(tar, dest)


def test_a_dot_rooted_archive_is_still_accepted(tmp_path):
    """The honest counterpart to the empty-member-name guard.

    `tar -czf b.tar.gz .` writes the archive's own root as a member literally
    named "." , whose PurePosixPath has no parts at all. An earlier version of
    the guard conflated that with the empty name and refused it, which is a
    false reject against a mainstream tar invocation on a bundle that passes
    today. Only an empty-named or dot-named FILE is the crash vector.
    """
    tar = tmp_path / "dot.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        tf.add(FIX / "valid", arcname=".")
    assert main([str(tar)]) == 0


@pytest.mark.parametrize("rel", [
    "evidence/bundle.json", "evidence/results.json",
    "evidence/evalmut_run.json", "evidence/eval_run.json",
])
def test_a_top_level_array_artifact_is_named_not_crashed(tmp_path, rel):
    """The other half of V-002. A scalar carries no evidence, and so does a
    bare array, but four of the five profile checks call .get() on the loaded
    artifact immediately, so `[]` raised AttributeError out of verify_bundle
    with no named reason and no verdict line at all."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    (b / rel).write_text("[]", encoding="utf-8")
    _rehash(b, rel)
    crashed, out = False, []
    try:
        out = verify_bundle(b)
    except Exception:  # noqa: BLE001 - ANY escape is the defect
        crashed = True
    assert not crashed, "verify_bundle raised instead of naming a reason"
    assert any("artifact-unparsable" in x for x in out)


def test_a_root_anchored_tar_member_is_refused(tmp_path):
    """V-018, third accepted shape. A Windows path needs BOTH a drive and a
    root to be absolute, so a member named "\\evil.txt" has drive='',
    is_absolute()=False and a single component with no "..": it passed a
    check that tested only drive and is_absolute. On a python whose
    extractall has no filter= kwarg it lands at C:\\evil.txt."""
    from vac.verify import _extract_tar
    for name in (BS + "evil.txt", BS, BS + "srv" + BS + "share" + BS + "e"):
        tar = tmp_path / f"r{len(name)}.tar.gz"
        _tar_with_raw_member(tar, name)
        dest = tmp_path / f"rd{len(name)}"
        dest.mkdir()
        with pytest.raises(ValueError):
            _extract_tar(tar, dest)
