"""Refusals nothing exercised: stamp bindings, the per-profile "not
recomputable" summary bar, duplicate evidence entries, the replay/protocol
commit agreement, and a check pointing at evidence the manifest never listed.

A mutation sweep over vac/verify.py neutralised each `f.append(...)` in turn
and found these fired for no test — a gate that never fires cannot be
trusted. Each test below builds a bundle that must trip ONE named reason and
asserts the EXACT failure list, so the reason cannot be reached by accident
(a substring search over a long list would pass on the wrong root cause) and
so disabling the refusal fails the test rather than shortening a list nobody
reads.
"""

from __future__ import annotations

import json
import pathlib
import shutil

from vac.verify import _sha256, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"


def _copy_valid(tmp_path: pathlib.Path) -> pathlib.Path:
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)  # fixtures/ itself is never touched
    return b


def _rehash(bundle: pathlib.Path, rel: str) -> None:
    """Re-pin an artifact's sha256 honestly, so a tamper is tested on the
    reason it targets and not on the hash it happened to break."""
    man_path = bundle / "vac.json"
    man = json.loads(man_path.read_text())
    for e in man["evidence"]:
        if e["path"] == rel:
            e["sha256"] = _sha256(bundle / rel)
    man_path.write_text(json.dumps(man, indent=1) + "\n")


def _edit_manifest(bundle: pathlib.Path, fn) -> None:
    p = bundle / "vac.json"
    man = json.loads(p.read_text())
    fn(man)
    p.write_text(json.dumps(man, indent=1) + "\n")


def _edit_artifact(bundle: pathlib.Path, rel: str, fn) -> None:
    p = bundle / rel
    data = json.loads(p.read_text())
    fn(data)
    p.write_text(json.dumps(data, indent=1) + "\n")
    _rehash(bundle, rel)


def _check(man: dict, profile: str) -> dict:
    return next(c for c in man["results"]["checks"]
                if c["profile"] == profile)


# --------------------------------------------------------------------------
# manifest-level: duplicate evidence, replay/protocol commit agreement
def test_duplicate_evidence_entry_is_named(tmp_path):
    """Two entries for one path let a bundle carry two sha256 pins for the
    same bytes — one of them decorative, whichever the reader trusts."""
    b = _copy_valid(tmp_path)
    _edit_manifest(b, lambda m: m["evidence"].append(
        dict(next(e for e in m["evidence"]
                  if e["path"] == "evidence/bundle.json"))))
    assert verify_bundle(b) == ["duplicate-artifact: evidence/bundle.json"]


def test_replay_commit_must_equal_protocol_commit(tmp_path):
    """The replay recipe is the bundle's own re-earn instructions: if it
    checks out a different commit than the protocol pins, the recipe does
    not reproduce the claim it is printed under."""
    b = _copy_valid(tmp_path)
    _edit_manifest(b,
                   lambda m: m["replay"].update(issuer_commit="0000000"))
    assert verify_bundle(b) == [
        "issuer-commit-mismatch: replay 0000000 != protocol f1e2d3c"]


# --------------------------------------------------------------------------
# certlab stamps: deleting a stamp must cost exactly what faking it costs
def test_certlab_stamp_named_by_hashes_must_be_present(tmp_path):
    """protocol.hashes names taskset_hash, so the artifact must carry it:
    dropping the key is how an issuer opts out of the comparison."""
    b = _copy_valid(tmp_path)
    _edit_artifact(b, "evidence/bundle.json",
                   lambda d: d.pop("taskset_hash"))
    assert verify_bundle(b) == [
        "stamp-mismatch: taskset_hash: named by protocol.hashes but absent "
        "from evidence/bundle.json"]


def test_certlab_stamp_value_must_equal_the_protocol_pin(tmp_path):
    """Same stamp, faked instead of deleted: the run was graded over a
    different task set than the claim is scoped to."""
    b = _copy_valid(tmp_path)
    _edit_manifest(b, lambda m: m["protocol"]["hashes"].update(
        taskset_hash="ffffffffffffffff"))
    assert verify_bundle(b) == [
        "stamp-mismatch: taskset_hash: protocol ffffffffffffffff, "
        "artifact 00112233445566aa"]


def test_certlab_artifact_must_carry_a_harness_commit(tmp_path):
    """A pinned issuer_commit with no harness_commit in the payload leaves
    the verdicts unattributable to the code that produced them."""
    b = _copy_valid(tmp_path)
    _edit_artifact(b, "evidence/bundle.json",
                   lambda d: d.pop("harness_commit"))
    assert verify_bundle(b) == [
        "stamp-mismatch: harness_commit: protocol declares issuer_commit "
        "but evidence/bundle.json carries no harness_commit"]


# --------------------------------------------------------------------------
# fleet stamps: both the issuer_commit binding and the protocol.hashes one
def test_fleet_aggregate_must_carry_a_fleet_commit(tmp_path):
    """Deleting fleet_commit from the aggregate silences BOTH bindings —
    the issuer_commit one and the protocol.hashes one — so both are named
    here; either going quiet is the sweep's finding."""
    b = _copy_valid(tmp_path)
    _edit_artifact(b, "evidence/results.json",
                   lambda d: d.pop("fleet_commit"))
    assert verify_bundle(b) == [
        "stamp-mismatch: fleet_commit: protocol declares issuer_commit but "
        "the aggregate row carries no fleet_commit",
        "stamp-mismatch: hashes.fleet_commit: named by protocol.hashes but "
        "absent from the aggregate row"]


def test_fleet_commit_value_must_equal_the_protocol_pins(tmp_path):
    """The board was run at some other fleet commit than the one the claim
    is stamped with — named against protocol.issuer_commit AND against the
    protocol.hashes entry that pins the same identity."""
    b = _copy_valid(tmp_path)
    _edit_artifact(b, "evidence/results.json",
                   lambda d: d.update(fleet_commit="0000000"))
    assert verify_bundle(b) == [
        "stamp-mismatch: fleet_commit: protocol f1e2d3c, artifact 0000000",
        "stamp-mismatch: hashes.fleet_commit: protocol f1e2d3c, "
        "artifact 0000000"]


# --------------------------------------------------------------------------
# crashkit: the check names which protocol.hashes entry pins its battery
def test_crashkit_battery_hash_key_must_name_a_real_pin(tmp_path):
    """battery_hash_key pointing at a key protocol.hashes does not have is
    an unpinned battery wearing a pin's name — deleting the entry must not
    be cheaper than faking it (which test_verify already covers)."""
    b = _copy_valid(tmp_path)
    _edit_manifest(b,
                   lambda m: m["protocol"]["hashes"].pop("crash_battery_hash"))
    assert verify_bundle(b) == [
        "stamp-mismatch: crash_battery_hash: named by the check but absent "
        "from protocol.hashes"]


# --------------------------------------------------------------------------
# the per-profile summary bar: a declared number this profile cannot
# recompute is a free-floating claim, not evidence — one test per profile,
# since each profile appends its own reason
def test_certlab_expect_key_must_be_recomputable(tmp_path):
    b = _copy_valid(tmp_path)
    _edit_manifest(b, lambda m: _check(m, "certlab-bundle-v1")["expect"]
                   .update(unfixed=1))
    assert verify_bundle(b) == [
        "summary-mismatch: unfixed: not recomputable under "
        "certlab-bundle-v1"]


def test_fleet_expect_key_must_be_recomputable(tmp_path):
    """fleet-board-v1 recomputes exactly `rows` from the aggregate; a rate
    declared here would be checked against nothing."""
    b = _copy_valid(tmp_path)
    _edit_manifest(b, lambda m: _check(m, "fleet-board-v1")["expect"]
                   .update(detection_rate=0.75))
    assert verify_bundle(b) == [
        "summary-mismatch: detection_rate: not recomputable under "
        "fleet-board-v1"]


def test_fleet_expect_rows_must_match_the_aggregate(tmp_path):
    """The one number fleet-board-v1 does recompute, declared wrong."""
    b = _copy_valid(tmp_path)
    _edit_manifest(b, lambda m: _check(m, "fleet-board-v1")["expect"]
                   .update(rows=3))
    assert verify_bundle(b) == [
        "summary-mismatch: rows: declared 3, recomputed 2"]


def test_evalmut_expect_key_must_be_recomputable(tmp_path):
    b = _copy_valid(tmp_path)
    _edit_manifest(b, lambda m: _check(m, "evalmut-run-v1")["expect"]
                   .update(survivors=3))
    assert verify_bundle(b) == [
        "summary-mismatch: survivors: not recomputable under "
        "evalmut-run-v1"]


def test_crashkit_expect_key_must_be_recomputable(tmp_path):
    b = _copy_valid(tmp_path)
    _edit_manifest(b, lambda m: _check(m, "crashkit-battery-v1")["expect"]
                   .update(refusals=2))
    assert verify_bundle(b) == [
        "summary-mismatch: refusals: not recomputable under "
        "crashkit-battery-v1"]


def test_modeldrift_expect_key_must_be_recomputable(tmp_path):
    b = _copy_valid(tmp_path)
    _edit_manifest(b, lambda m: _check(m, "modeldrift-board-v1")["expect"]
                   .update(flaky=2))
    assert verify_bundle(b) == [
        "summary-mismatch: flaky: not recomputable under "
        "modeldrift-board-v1"]


# --------------------------------------------------------------------------
# a check must read evidence the manifest actually pins
def test_check_artifact_must_be_listed_in_evidence(tmp_path):
    """A check reading an unlisted path recomputes from bytes no sha256
    covers. The evidence-unchecked line is the orphaned artifact the check
    stopped reading — asserted exactly so neither reason can go quiet."""
    b = _copy_valid(tmp_path)
    _edit_manifest(b, lambda m: _check(m, "certlab-bundle-v1")
                   .update(artifact="evidence/nope.json"))
    assert verify_bundle(b) == [
        "check-artifact-not-listed: 'evidence/nope.json'",
        "evidence-unchecked: evidence/bundle.json: listed in evidence but "
        "read by no check"]


def test_optional_check_ref_is_held_to_the_same_bar(tmp_path):
    """evalmut's `catalog` is optional, but once named it is a reference
    like any other: pointing it off the manifest must not be a way to keep
    a ref in the JSON while dropping it from verification."""
    b = _copy_valid(tmp_path)
    _edit_manifest(b, lambda m: _check(m, "evalmut-run-v1")
                   .update(catalog="evidence/nope.json"))
    assert verify_bundle(b) == [
        "check-artifact-not-listed: 'evidence/nope.json'",
        "evidence-unchecked: evidence/operators.json: listed in evidence "
        "but read by no check"]
