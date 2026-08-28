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
import re
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


# --------------------------------------------------------------------------
# registry.json is the source of truth for what a REAL issuer bundle is
# expected to do. An accepted entry must verify clean; a pending entry must be
# refused for exactly the reasons the registry records, so a bundle that starts
# failing for a NEW reason fails loudly instead of being absorbed by a blanket
# "it is expected to fail". Regenerated by `python -m vac.registry`.
_REG_PREFIX = "refused at generation: structural: "
_REG_TAIL = " \u2014 fix the committed bundle and re-run python -m vac.registry"


def _registry_expectation(name: str):
    """('accepted', None) | ('pending', [reason, ...]) | (None, None)."""
    reg = json.loads((ROOT / "registry.json").read_text())
    if any(e.get("name") == name for e in reg.get("entries", [])):
        return "accepted", None
    for pend in reg.get("pending", []):
        if pend.get("name") == name:
            body = pend.get("reason", "")
            if body.startswith(_REG_PREFIX):
                body = body[len(_REG_PREFIX):]
            if body.endswith(_REG_TAIL):
                body = body[:-len(_REG_TAIL)]
            return "pending", body.split("; structural: ")
    return None, None


def _assert_matches_registry(bundle, name) -> bool:
    """Hold the bundle to its registry status. True when the tamper leg
    should run, i.e. the bundle is accepted and verified clean."""
    status, documented = _registry_expectation(name)
    if status is None:
        pytest.skip(f"{name} has no registry.json entry")
    actual = verify_bundle(bundle)
    if status == "accepted":
        assert actual == [], (
            f"{name} is ACCEPTED in registry.json but the committed bundle "
            f"is refused: {actual}")
        return True
    assert actual == documented, (
        f"{name} is PENDING in registry.json, but for different reasons than "
        f"recorded. Re-run `python -m vac.registry` if the bundle changed.\n"
        f"  registry: {documented}\n  actual:   {actual}")
    return False


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
    if not _assert_matches_registry(b, "model-drift/vac"):
        return  # pending: refused for the documented reason, nothing to tamper
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
    if not _assert_matches_registry(b, "evalmut/vac"):
        return  # pending: refused for the documented reason, nothing to tamper
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
    if not _assert_matches_registry(b, "crashkit/vac"):
        return  # pending: refused for the documented reason, nothing to tamper
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


# ---------------------------------------------------------------------------
# Robustness: inputs that made the verifier CRASH instead of naming a
# reason, an unbounded scan on an issuer-controlled field, and a
# verdict that depended on the host rather than on the bundle.

def test_non_object_rows_are_named_not_crashed(tmp_path):
    """V-009. certlab and fleet validated the container but not its elements,
    so .get() on a string raised AttributeError out of verify_bundle, breaking
    the 'one named reason per failure' contract."""
    for rel, key in (("evidence/bundle.json", "verdicts"),
                     ("evidence/results.json", "rows")):
        b = tmp_path / ("b" + key)
        shutil.copytree(FIX / "valid", b)
        _art_edit(b, rel, lambda d, k=key: d[k].append("not-a-dict"))
        crashed, out = False, []
        try:
            out = verify_bundle(b)
        except Exception:  # noqa: BLE001 - proving ANY escape is the defect
            crashed = True
        assert not crashed, "verify_bundle raised instead of naming a reason"
        assert any("artifact-unparsable" in x for x in out)


def test_a_scalar_container_is_named_not_crashed(tmp_path):
    """V-010. `m.get("evidence") or []` guards None and [] but not a truthy
    scalar: `5 or []` is 5, and `for e in 5` raises TypeError."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    _man_edit(b, lambda m: m.update(evidence=5))
    out = verify_bundle(b)  # must not raise
    assert any("evidence" in x for x in out)


def test_a_non_string_timestamp_is_named_not_coerced(tmp_path):
    """V-012. A non-string `t` was coerced to "" with NO failure named, so the
    chronology check was silently skipped for that point, and the value then
    reached [:10] slices downstream and crashed."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)

    def f(d):
        for pts in d["series"].values():
            for i, p in enumerate(pts):
                p["t"] = 20260101 + i
    _art_edit(b, "evidence/metrics.json", f)
    out = verify_bundle(b)  # must not raise
    assert any("is not a string" in x for x in out)


def test_a_non_list_fails_vector_is_named_not_crashed(tmp_path):
    """V-013. `fails` was fed to set()/sorted() unchecked: a scalar raised
    TypeError, and a mixed str/int list raised on the sort against `ids`."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)

    def f(d):
        next(iter(d["series"].values()))[0]["fails"] = 7
    _art_edit(b, "evidence/metrics.json", f)
    out = verify_bundle(b)  # must not raise
    assert any("fails" in x for x in out)


def test_the_verdict_does_not_depend_on_the_host_locale(tmp_path):
    """V-014. read_text() with no encoding= uses the LOCALE codec, so the same
    bundle bytes verified differently on different hosts. A manifest carrying
    UTF-8 byte 0x81 (undefined in cp1252) was rejected as invalid-json on a
    Windows host and accepted under UTF-8 mode."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    p = b / "vac.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    m["claim"]["limitations"].append("Проверка не доказывает семантику.")
    p.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")
    assert b"\x81" in p.read_bytes()  # undefined in cp1252
    assert verify_bundle(b) == []


def test_a_deeply_nested_manifest_is_named_not_crashed(tmp_path):
    """V-021. verify_bundle caught only UnicodeDecodeError/JSONDecodeError, so
    a deeply nested manifest raised RecursionError with NO named reason and an
    EMPTY stdout, against SPEC 4's "one named reason per failure"."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    (b / "vac.json").write_text("[" * 200000 + "]" * 200000, encoding="utf-8")
    crashed, out = False, []
    try:
        out = verify_bundle(b)
    except BaseException:  # noqa: BLE001 - ANY escape is the defect
        crashed = True
    assert not crashed, "verify_bundle raised instead of naming a reason"
    assert out and "invalid-json" in out[0]


def test_issuer_text_cannot_repaint_the_terminal(tmp_path, capsys):
    """V-020. The replay block is echoed AFTER the verdict line and was printed
    raw, so ANSI escapes in replay.commands could clear the screen and paint a
    forged PASS banner over a failing run. Drive the real CLI and inspect what
    actually reaches stdout."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    p = b / "vac.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    esc = chr(27)
    man["replay"]["commands"] = [
        esc + "[2J" + esc + "[Hstructural verification: PASS (spoof)"]
    man["claim"]["limitations"] = []          # force a failing verdict
    p.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    main([str(b)])
    printed = capsys.readouterr().out
    assert "empty-limitations" in printed     # it really did fail
    assert esc not in printed                 # and could not repaint anything


@pytest.mark.parametrize("rel,mutate", [
    ("evidence/eval_run.json",
     lambda d: d["cases"][0].update(severity=[])),
    ("evidence/evalmut_run.json",
     lambda d: d["results"][0].update(operator_id=[])),
    ("evidence/results.json",
     lambda d: d["rows"][0].update(suite=[])),
    ("evidence/metrics.json",
     lambda d: next(iter(d["series"].values()))[0].update(
         fails_runs=[[["nested"]]])),
])
def test_unhashable_issuer_values_are_named_not_crashed(tmp_path, rel, mutate):
    """V-011 at every site, not just the one the first fix pinned.

    Issuer JSON reaches dict keys and set elements in four places, and
    `dict.get()` RAISES on an unhashable key rather than returning its
    default. The first pass hardened crashkit `severity` only; a poisoning
    sweep found the other three still reachable, one of them on a line the
    fix diff itself had just added.
    """
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    _art_edit(b, rel, mutate)
    crashed, out = False, []
    try:
        out = verify_bundle(b)
    except Exception:  # noqa: BLE001 - ANY escape is the defect
        crashed = True
    assert not crashed, "verify_bundle raised instead of naming a reason"
    assert out, "the poisoned value must be named, not silently accepted"


def test_the_cli_names_a_reason_for_a_nested_manifest(tmp_path, capsys):
    """V-021 at the CLI, not just in verify_bundle.

    `_report` re-parses vac.json for the replay echo, and its except tuple
    lacked RecursionError, so the shipped entry point printed a traceback
    beside the named reason. A stranger runs `python -m vac.verify`, not
    `verify_bundle`, so that is the level the contract has to hold at.
    """
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    (b / "vac.json").write_text("[" * 200000 + "]" * 200000, encoding="utf-8")
    rc = main([str(b)])
    printed = capsys.readouterr().out
    assert rc == 1
    assert "invalid-json" in printed
    assert "structural verification: FAIL" in printed


def test_a_nested_evidence_artifact_is_named_not_crashed(tmp_path):
    """V-021 via an evidence artifact rather than the manifest: `_load_json`
    had the same gap."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    rel = "evidence/bundle.json"
    (b / rel).write_text("[" * 200000 + "]" * 200000, encoding="utf-8")
    _rehash(b, rel)
    crashed, out = False, []
    try:
        out = verify_bundle(b)
    except Exception:  # noqa: BLE001
        crashed = True
    assert not crashed, "verify_bundle raised instead of naming a reason"
    assert any("artifact-unparsable" in x for x in out)


def test_no_text_read_in_the_verifier_relies_on_the_host_locale():
    """V-014, pinned structurally so it fails on ANY host.

    The behavioural sibling test only goes red where the preferred encoding
    is not UTF-8, so on this project's own CI (ubuntu, 3.11/3.12) it would
    pass against the unfixed code and protect nothing. This one reads the
    source instead: every text read must name its encoding.
    """
    bad = []
    for mod in sorted((pathlib.Path(__file__).resolve().parents[1]
                       / "vac").glob("*.py")):
        src = mod.read_text(encoding="utf-8")
        for m in re.findall(r"\.(?:read_text|write_text)\("
                            r"(?![^()]*encoding)[^()]*\)", src):
            bad.append(f"{mod.name}: {m}")
    assert bad == [], f"text I/O without encoding=: {bad}"


def test_the_narrative_strip_matches_the_regex_exactly():
    """V-017, half one: the replacement is the SAME transform.

    _strip_tags exists only because `<[^>]+>` is quadratic on an
    issuer-controlled field. SPEC 3.5 pins the committed narrative against
    that transform, so a divergence would flip verdicts on honest bundles
    rather than merely change performance. The corpus is drawn from a
    `<>`-dense alphabet under a fixed seed, so every host and every run sees
    the same strings.

    This half has no upstream red state: its subject does not exist on main.
    The half below is the one that fails there.
    """
    import random

    from vac.verify import _strip_tags

    cases = ["", "<", ">", "<>", "<>>", "<<>", "<a>", "<a", "a>", "a<b>c",
             "<a><b>", "<a<b>c>", "<<a>>", "< >", "x<y", "<>x<>", "<a><",
             "><a>", "<a>" * 4, "<" * 8, ">" * 8, "<\n>"]
    rng = random.Random(20260816)
    for _ in range(20000):
        cases.append("".join(rng.choice("<>ab \n")
                             for _ in range(rng.randrange(12))))
    for s in cases:
        assert _strip_tags(s) == re.sub(r"<[^>]+>", "", s), repr(s)


def test_the_narrative_strip_never_reaches_the_quadratic_regex(tmp_path,
                                                              monkeypatch):
    """V-017, half two, through the real modeldrift check.

    narrative.html is issuer-controlled and was fed to `<[^>]+>`, which
    rescans to end-of-string from every start position when no ">" follows.
    This input costs ~20s against the pre-fix code and is instant against
    _strip_tags.

    The first version of this test asserted wall clock under 4.0s. That let a
    verdict about the patch depend on how loaded the host was, which is the
    same class of defect the patch exists to remove, so the clock is gone.
    What is asserted instead is the mechanism: the quadratic pattern never
    reaches the engine at all, by either route it could take.

    A step-count bound is deliberately not attempted. The quadratic work
    happens inside the C engine, where no Python-level counter can observe
    it, so counting Python operations would assert nothing about the path
    that was slow.
    """
    seen = []
    real_sub, real_compile = re.sub, re.compile

    def _pat(pattern):
        return pattern if isinstance(pattern, str) else pattern.pattern

    def _recording_sub(pattern, repl, string, *a, **kw):
        seen.append(_pat(pattern))
        return real_sub(pattern, repl, string, *a, **kw)

    def _recording_compile(pattern, *a, **kw):
        seen.append(_pat(pattern))
        return real_compile(pattern, *a, **kw)

    # Both routes: re.sub(pattern, ...) and re.compile(pattern).sub(...).
    # Recording only the first would let the quadratic form return through
    # the compiled one without the test noticing.
    monkeypatch.setattr(re, "sub", _recording_sub)
    monkeypatch.setattr(re, "compile", _recording_compile)

    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    rel = "evidence/narrative.json"
    art = b / rel
    d = json.loads(art.read_text(encoding="utf-8"))
    d["html"] = "<" * 120000
    art.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    _rehash(b, rel)

    assert isinstance(verify_bundle(b), list)
    # A recorder that saw nothing passes the assertion below vacuously,
    # which is the defect class this whole branch is about.
    assert seen, "no pattern was recorded: the recorder proves nothing"
    assert [p for p in seen if "[^>]" in p] == []


def _set_fleet_ids(b, value):
    """Rewrite suite/member consistently in BOTH fleet artifacts."""
    agg = b / "evidence/results.json"
    d = json.loads(agg.read_text(encoding="utf-8"))
    for i, row in enumerate(d["rows"]):
        row["member"] = value(i)
    agg.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    _rehash(b, "evidence/results.json")

    raw = b / "evidence/raw_results.jsonl"
    order, out = [], []
    for ln in raw.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        o = json.loads(ln)
        if o["member"] not in order:
            order.append(o["member"])
        o["member"] = value(order.index(o["member"]))
        out.append(json.dumps(o))
    raw.write_text("\n".join(out) + "\n", encoding="utf-8")
    _rehash(b, "evidence/raw_results.jsonl")


def test_integer_fleet_member_ids_are_still_accepted(tmp_path):
    """SPEC 3.2 gives the row shape as {suite, member, ...} and types neither
    field, so a board keyed by integer member ids is legal evidence. An
    earlier version of the unhashable-key guard required strings and refused
    this, which is a wider refusal than the defect warrants."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    _set_fleet_ids(b, lambda i: i + 1)
    assert verify_bundle(b) == []


def test_integer_evalmut_operator_ids_are_still_accepted(tmp_path):
    """SPEC 3.3 types the CATALOG's `id`, and the catalog is optional; the
    row's operator_id is untyped. A catalogless bundle with integer operator
    ids is legal and must not be refused."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    p = b / "vac.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    ids = {}
    for c in man["results"]["checks"]:
        if c.get("profile") == "evalmut-run-v1":
            c.pop("catalog", None)          # catalog is optional per SPEC 3.3
    man["evidence"] = [e for e in man["evidence"]
                       if e["path"] != "evidence/operators.json"]
    man["results"]["summary"].pop("mutation_blind_spots", None)
    p.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    (b / "evidence/operators.json").unlink()

    rel = "evidence/evalmut_run.json"
    art = b / rel
    d = json.loads(art.read_text(encoding="utf-8"))
    for r in d["results"]:
        ids.setdefault(r["operator_id"], len(ids) + 1)
        r["operator_id"] = ids[r["operator_id"]]
    for lst in d.get("holes", {}).values():
        for r in lst:
            if isinstance(r, dict) and "operator_id" in r:
                r["operator_id"] = ids[r["operator_id"]]
    art.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    _rehash(b, rel)
    out = verify_bundle(b)
    assert not any("operator_id" in x for x in out), out


def test_a_clean_bundle_prints_on_a_non_utf8_console(tmp_path):
    """An honest bundle whose replay block carries non-ASCII text must still
    print a verdict on a console that is not UTF-8. The replay echo was
    written raw, so on a cp1252 stdout the CLI died with UnicodeEncodeError
    after a PASS: exit 1 and a traceback where the answer was 0."""
    import contextlib
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    p = b / "vac.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    man["replay"]["commands"].append("# note: " + chr(26085) + chr(26412))
    p.write_text(json.dumps(man, indent=1) + chr(10), encoding="utf-8")
    assert verify_bundle(b) == []          # the bundle itself is honest
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")
    with contextlib.redirect_stdout(buf):
        rc = main([str(b)])
    buf.flush()
    assert rc == 0


@pytest.mark.parametrize("codec", ["cp1252", "ascii"])
def test_a_failing_bundle_prints_its_verdict_on_any_console(tmp_path, codec):
    """The verifier's OWN verdict line carries an em dash, and it was printed
    raw. cp1252 happens to contain U+2014, so a cp1252-only test cannot see
    this; ascii cannot encode it and the CLI died after the FAIL reasons but
    before the verdict, which is the one line a reader needs.
    """
    import contextlib
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    p = b / "vac.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    man["claim"]["limitations"] = []          # force a failing verdict
    p.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    buf = io.TextIOWrapper(io.BytesIO(), encoding=codec, newline="")
    with contextlib.redirect_stdout(buf):
        rc = main([str(b)])
    buf.flush()
    printed = buf.buffer.getvalue().decode(codec)
    assert rc == 1
    assert "empty-limitations" in printed
    assert "structural verification: FAIL" in printed


def test_bidi_and_separator_controls_are_escaped(monkeypatch):
    """Escaping C0/C1 is not enough on a UTF-8 console.

    U+202E reverses the DISPLAYED order of a replay command the reader is
    explicitly invited to copy and paste, and U+2028 renders as a newline in
    many log viewers, which is enough to forge an output line of the
    verifier's own. Legitimate text must still pass through untouched.

    The offending characters are built with chr() rather than written as
    literals, so this file does not itself contain invisible reordering
    marks.
    """
    from vac.verify import _printable

    class _Utf8:
        encoding = "utf-8"

    monkeypatch.setattr(sys, "stdout", _Utf8())
    for cp in (0x202E, 0x202D, 0x200F, 0x2028, 0x2029, 0x2066):
        bad = chr(cp)
        assert bad not in _printable("x" + bad + "y")

    ok = "".join(chr(c) for c in (0x41F, 0x440, 0x43E, 0x432, 0x435, 0x440,
                                  0x43A, 0x430))          # Cyrillic
    ok += " " + "".join(chr(c) for c in (0x65E5, 0x672C))  # CJK
    ok += " " + chr(0x2014) + " " + chr(0x1F534) + " ok"   # em dash, emoji
    assert _printable(ok) == ok


def _nest(depth, leaf):
    """Build a nested dict in Python, without the JSON decoder.

    The earlier version of these tests built the fixture with
    json.loads('{"a":' * 3000), which RecursionErrors inside the DECODER on
    some interpreters before the verifier is ever reached. That made the test
    green on one host and red on another, which is the same host-dependence
    the patch exists to remove. Building the structure directly recurses in
    neither the decoder nor the test.
    """
    node = leaf
    for _ in range(depth):
        node = {"a": node}
    return node


def test_the_summary_traversal_is_iterative():
    """SPEC 2.5's walk covers results.summary, which the issuer writes and can
    nest to whatever depth the decoder on THIS host happened to allow. A
    recursive walk therefore fails at a depth that varies by interpreter. An
    explicit stack has no such limit, so the depth below is far past any
    default recursion limit and must still be handled.
    """
    from vac.verify import _summary_outruns
    deep = _nest(20000, 1)
    out = _summary_outruns(deep, [{"a": [1]}])   # must not raise
    assert isinstance(out, list)


def test_the_draft_traversal_is_iterative():
    """Same property for the TODO walk, which covers the whole manifest."""
    from vac.verify import _todo_failures
    out = _todo_failures(_nest(20000, "x"))      # must not raise
    assert isinstance(out, list)


def test_a_recursion_error_does_not_erase_the_other_reasons(tmp_path,
                                                            monkeypatch):
    """Defence in depth for the traversals that are not iterative yet.

    The backstop must APPEND. An earlier version returned a fresh list, which
    handed the issuer a switch: anything that induced a RecursionError deleted
    every other named reason, a smuggled unlisted file included, while still
    exiting 1 so nothing looked wrong. Injected rather than induced, so the
    test does not depend on where this interpreter's stack gives out.
    """
    import vac.verify as V
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    (b / "evidence" / "SECRET.txt").write_text("smuggled", encoding="utf-8")
    p = b / "vac.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    man["claim"]["limitations"] = []
    p.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")

    def _boom(*a, **k):
        raise RecursionError("injected")

    monkeypatch.setattr(V, "_coherence", _boom)
    out = V.verify_bundle(b)
    assert any("unlisted-file: evidence/SECRET.txt" in x for x in out), out
    assert any("empty-limitations" in x for x in out), out
    assert any("nesting too deep" in x for x in out), out


# --- Each refusal below is pinned by its exact reason text, not by "some
# artifact-unparsable fired". The repo's refusal-coverage job mutates each
# f.append site away and requires a test to notice; an assertion that only
# checks the list is non-empty survives that mutation via collateral damage.

def _write_raw(b, lines):
    rel = "evidence/raw_results.jsonl"
    (b / rel).write_text("\n".join(lines) + "\n", encoding="utf-8")
    _rehash(b, rel)


def test_a_raw_line_that_is_not_an_object_is_refused(tmp_path):
    """The fleet raw payload is one JSON object per line. A bare scalar line
    reached ln.get() and raised AttributeError out of verify_bundle."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    raw = (b / "evidence/raw_results.jsonl").read_text(
        encoding="utf-8").splitlines()
    _write_raw(b, raw + ["42"])
    assert ("artifact-unparsable: evidence/raw_results.jsonl: every line "
            "must be an object") in verify_bundle(b)


def test_a_raw_line_with_an_unhashable_member_is_refused(tmp_path):
    """(suite, member) becomes a dict key and a set element, and dict.get()
    RAISES on an unhashable key rather than returning its default."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    raw = (b / "evidence/raw_results.jsonl").read_text(
        encoding="utf-8").splitlines()
    first = json.loads(raw[0])
    first["member"] = []
    _write_raw(b, [json.dumps(first)] + raw[1:])
    assert ("artifact-unparsable: evidence/raw_results.jsonl: line 1 "
            "suite/member must be scalar identifiers") in verify_bundle(b)


def test_an_aggregate_row_with_an_unhashable_member_is_refused(tmp_path):
    """Same hazard on the aggregate side, where the duplicate-row check this
    branch adds is itself the line that would raise."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    rel = "evidence/results.json"
    art = b / rel
    d = json.loads(art.read_text(encoding="utf-8"))
    d["rows"][0]["member"] = []
    art.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    _rehash(b, rel)
    assert ("artifact-unparsable: evidence/results.json: row 1 "
            "suite/member must be scalar identifiers") in verify_bundle(b)


def test_an_evalmut_row_with_an_unhashable_operator_id_is_refused(tmp_path):
    """operator_id reaches a set element and the catalog dict lookup."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    rel = "evidence/evalmut_run.json"
    art = b / rel
    d = json.loads(art.read_text(encoding="utf-8"))
    d["results"][0]["operator_id"] = []
    art.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    _rehash(b, rel)
    assert ("artifact-unparsable: evidence/evalmut_run.json: row 1 "
            "operator_id must be a scalar identifier") in verify_bundle(b)


def _symlink_or_skip(link: pathlib.Path, target: pathlib.Path):
    """Symlinks need privilege on Windows. CI is ubuntu, so these run there.

    The skip is explicit rather than silent: a test that quietly vanishes on
    the maintainer's host is the same shape of problem as a test that only
    passes on mine.
    """
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"symlinks unavailable on this host: {e}")


def test_a_symlinked_artifact_is_refused(tmp_path):
    """PR #1 handed this over unresolved: directory-mode closure versus
    symlinks. Settled on a POSIX host, and the answer was yes.

    A COVERED artifact replaced by a symlink pointing out of the bundle
    verified clean, exit 0, under the banner "bundle closure". The bytes were
    hash-identical, so nothing else could notice: the evidence simply lived
    somewhere else on the verifying host. A bundle whose closure is not a
    closure cannot support the one sentence this tool prints.
    """
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    outside = tmp_path / "outside"
    outside.mkdir()
    rel = "evidence/bundle.json"
    moved = outside / "bundle.json"
    shutil.move(str(b / rel), str(moved))
    _symlink_or_skip(b / rel, moved)

    out = verify_bundle(b)
    assert f"unsafe-bundle: {rel}: symlink" in out


def test_a_symlinked_directory_cannot_smuggle_an_unlisted_file(tmp_path):
    """The other half, and the reason is_file() alone could not catch it.

    rglob does not descend a symlinked directory, and is_file() answers False
    for the link itself, so an unlisted file inside one was never seen. The
    control is test_unlisted_file_breaks_closure: the identical
    file placed directly in the bundle was always refused.
    """
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "stowaway.txt").write_text("rider\n", encoding="utf-8")
    _symlink_or_skip(b / "evidence/linked", outside)

    out = verify_bundle(b)
    assert "unsafe-bundle: evidence/linked: symlink" in out


def test_a_symlinked_artifact_does_not_leak_the_outside_digest(tmp_path):
    """The refusal must come BEFORE the read, not after it.

    Naming the symlink but still hashing through it would leave the oracle
    open: a wrong declared sha256 makes the mismatch reason print the true
    digest of whatever the link points at, which is arbitrary-read by
    confirmation. This pins the order, not just the outcome.
    """
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.json"
    secret.write_text('{"secret": true}\n', encoding="utf-8")
    digest = _sha256(secret)
    rel = "evidence/bundle.json"
    (b / rel).unlink()
    _symlink_or_skip(b / rel, secret)

    out = verify_bundle(b)
    assert f"unsafe-bundle: {rel}: symlink" in out
    assert not [x for x in out if digest in x], out
