"""The verifier must pass the one honest bundle and refuse every tamper —
each with its SPECIFIC named reason, not a generic red. A gate that cannot
name why it fired cannot be audited, and a gate that never fires cannot be
trusted, so both directions are pinned here: exact failure lists for the
committed tampered fixtures, and a repaired-tamper case proving the clean
path is reachable, not vacuous."""

from __future__ import annotations

import io
import json
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
                             "recomputed 2"],
    "tamper-empty-limitations": ["empty-limitations"],
    "tamper-missing-issuer-commit": ["missing-issuer-commit"],
    "tamper-raw-aggregate": [
        "raw-aggregate-mismatch: toy-suite/toy-defect-b: "
        "detected declared 3, recomputed 2",
        "raw-aggregate-mismatch: toy-suite/toy-defect-b: "
        "detection_rate declared 0.75, recomputed 0.5"],
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
