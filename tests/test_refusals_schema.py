"""Schema refusals that no fixture exercised: _validate_manifest's named
lines and the per-profile check-shape guards.

A mutation sweep disabled each `f.append(...)` in vac/verify.py one at a time
and found these went unnoticed by the whole suite — a refusal nothing tests
is a refusal nobody can trust. Each test here mutates ONE field of a private
copy of the one honest bundle and pins the EXACT failure list that mutation
must produce; the baseline test below proves the copy is otherwise clean, so
every reason in those lists is caused by the edit and nothing else.
"""

from __future__ import annotations

import json
import pathlib
import shutil

from vac.verify import verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"


def _edit(tmp_path, fn):
    """A private copy of fixtures/valid with `fn` applied to its manifest.

    Only vac.json is touched, and vac.json is not itself hashed by any
    evidence entry, so no artifact sha256 needs re-pinning here.
    """
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    p = b / "vac.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    fn(m)
    p.write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")
    return b


def _check(m, profile):
    return next(c for c in m["results"]["checks"] if c["profile"] == profile)


def test_untouched_copy_is_clean(tmp_path):
    """The baseline every other test in this file rests on: copying the
    bundle changes nothing, so any reason below belongs to that test's edit."""
    assert verify_bundle(_edit(tmp_path, lambda m: None)) == []


# --------------------------------------------------------------------------
# _validate_manifest


def test_schema_violation_names_the_field_need_rejected(tmp_path):
    """The shared `need()` append, which every required-field rule routes
    through: a whitespace-only capability is no capability, and the reason
    must name WHICH field failed rather than just "schema-violation"."""
    b = _edit(tmp_path, lambda m: m["claim"].update(capability="   "))
    assert verify_bundle(b) == [
        "schema-violation: claim.capability: non-empty string required"]


def test_subject_kind_outside_the_enum_is_refused(tmp_path):
    b = _edit(tmp_path, lambda m: m["subject"].update(kind="model"))
    assert verify_bundle(b) == [
        "schema-violation: subject.kind: "
        "must be 'agent' or 'suite-archetype'"]


def test_unpinned_subject_version_is_refused(tmp_path):
    """An empty version object pins nothing: the claim would name a subject
    no one can identify later."""
    b = _edit(tmp_path, lambda m: m["subject"].update(version={}))
    assert verify_bundle(b) == [
        "schema-violation: subject.version: at least one pinned "
        "identifier required — an unpinned subject is unverifiable"]


def test_a_named_but_empty_protocol_hash_is_refused(tmp_path):
    """protocol.hashes is read BY NAME everywhere else, so an extra entry
    with an empty value trips only this rule: every named hash must carry a
    value, not just exist as a key."""
    b = _edit(tmp_path, lambda m: m["protocol"]["hashes"].update(toy_hash=""))
    assert verify_bundle(b) == [
        "schema-violation: protocol.hashes: at least one named "
        "content hash required"]


def test_empty_evidence_array_is_refused(tmp_path):
    """Emptying evidence also orphans every artifact and every check ref, so
    the list is long — but nothing outside those three families may appear,
    and the evidence rule itself must be one of them."""
    out = verify_bundle(_edit(tmp_path, lambda m: m.update(evidence=[])))
    assert out[0] == ("schema-violation: evidence: "
                      "non-empty array required"), out
    assert all(r.startswith(("schema-violation: evidence:", "unlisted-file: ",
                             "check-artifact-not-listed: "))
               for r in out), out


def test_unsafe_evidence_path_is_refused(tmp_path):
    """Inserted at index 0 so the reason's index is stable. The entry is
    dropped by every later pass (it fails _safe_relpath there too), so this
    line is the ONLY thing standing between the manifest and a path that
    reads outside the bundle."""
    b = _edit(tmp_path, lambda m: m["evidence"].insert(
        0, {"path": "../outside.json", "sha256": "0" * 64}))
    assert verify_bundle(b) == [
        "schema-violation: evidence[0].path: safe relative path required"]


def test_evidence_sha256_in_uppercase_hex_is_refused(tmp_path):
    """Uppercase is not the pinned form. It matters that this is named: the
    hash comparison in _verify_artifacts SKIPS a non-hex64 digest, so with
    this line gone the artifact's bytes would never be checked at all."""
    def upper(m):
        e = next(e for e in m["evidence"]
                 if e["path"] == "evidence/bundle.json")
        e["sha256"] = e["sha256"].upper()

    assert verify_bundle(_edit(tmp_path, upper)) == [
        "schema-violation: evidence[1].sha256: 64 "
        "lowercase hex chars required"]


def test_non_object_results_summary_is_refused(tmp_path):
    """A string summary slips past SPEC 2.5 recomputation, which only walks a
    dict — so the shape itself has to be refused here."""
    b = _edit(tmp_path, lambda m: m["results"].update(summary="all green"))
    assert verify_bundle(b) == [
        "schema-violation: results.summary: object required"]


def test_empty_results_checks_is_refused(tmp_path):
    """No checks means nothing recomputes anything; the evidence then stands
    pinned but unread, which is the second reason."""
    b = _edit(tmp_path, lambda m: m["results"].update(checks=[]))
    assert verify_bundle(b) == [
        "schema-violation: results.checks: at least one profile check "
        "required",
        "evidence-unchecked: evidence/RESULTS.md, evidence/bundle.json, "
        "evidence/eval_run.json, evidence/evalmut_run.json (+9 more): "
        "listed in evidence but read by no check"]


def test_empty_replay_commands_is_refused(tmp_path):
    """Structural PASS is explicitly not a replay, so the recipe that WOULD
    re-earn the verdicts is mandatory."""
    b = _edit(tmp_path, lambda m: m["replay"].update(commands=[]))
    assert verify_bundle(b) == [
        "schema-violation: replay.commands: non-empty list of "
        "commands required"]


def test_missing_replay_expected_is_refused(tmp_path):
    """Commands without a stated expected outcome are a script, not a test."""
    b = _edit(tmp_path, lambda m: m["replay"].pop("expected"))
    assert verify_bundle(b) == [
        "schema-violation: replay.expected: expected outcome required"]


# --------------------------------------------------------------------------
# Per-profile check shape. Dropping `expect` removes the declared numbers a
# profile is graded against; without these lines the check would recompute
# happily and compare against nothing.


def test_certlab_check_without_expect_is_refused(tmp_path):
    b = _edit(tmp_path, lambda m: _check(m, "certlab-bundle-v1").pop("expect"))
    assert verify_bundle(b) == [
        "schema-violation: results.checks[certlab-bundle-v1].expect: "
        "declared counts required"]


def test_evalmut_check_without_expect_is_refused(tmp_path):
    b = _edit(tmp_path, lambda m: _check(m, "evalmut-run-v1").pop("expect"))
    assert verify_bundle(b) == [
        "schema-violation: results.checks[evalmut-run-v1].expect: "
        "declared counts required"]


def test_crashkit_check_without_battery_hash_key_is_refused(tmp_path):
    """The key names which protocol.hashes entry pins the battery. Drop it
    and the stamp comparison below simply never happens — the issuer would
    decide whether it is bound to a battery at all."""
    b = _edit(tmp_path, lambda m: _check(
        m, "crashkit-battery-v1").pop("battery_hash_key"))
    assert verify_bundle(b) == [
        "schema-violation: results.checks[crashkit-battery-v1]"
        ".battery_hash_key: name of the protocol.hashes entry "
        "pinning this artifact's battery required"]


def test_crashkit_check_without_expect_is_refused(tmp_path):
    b = _edit(tmp_path, lambda m: _check(
        m, "crashkit-battery-v1").pop("expect"))
    assert verify_bundle(b) == [
        "schema-violation: results.checks[crashkit-battery-v1]"
        ".expect: declared numbers required"]


def test_modeldrift_check_without_expect_is_refused(tmp_path):
    b = _edit(tmp_path, lambda m: _check(
        m, "modeldrift-board-v1").pop("expect"))
    assert verify_bundle(b) == [
        "schema-violation: results.checks[modeldrift-board-v1]"
        ".expect: declared numbers required"]
