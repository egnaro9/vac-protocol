"""The tail of modeldrift-board-v1, pinned refusal by refusal: the flip
analysis, the narrative's own claim count, and the suite stamp that binds the
protocol to the fingerprint the derivations were run over.

These are the refusals a mutation sweep found nothing noticed. Each test cooks
exactly one field of one artifact, honestly re-pins that artifact's sha256, and
asserts the WHOLE failure list — a substring search over a long list would pass
for a bundle that is broken somewhere else entirely, which is the defect this
repo exists to refuse."""

from __future__ import annotations

import json
import pathlib
import shutil

from vac.verify import _sha256, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"


def _rehash(bundle: pathlib.Path, rel: str) -> None:
    man_path = bundle / "vac.json"
    man = json.loads(man_path.read_text())
    for e in man["evidence"]:
        if e["path"] == rel:
            e["sha256"] = _sha256(bundle / rel)
    man_path.write_text(json.dumps(man, indent=1) + "\n")


def _cook(tmp_path: pathlib.Path, rel: str, mutate) -> pathlib.Path:
    """Copy the valid bundle, mutate one JSON artifact in place, re-pin it."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    art = b / rel
    data = json.loads(art.read_text())
    mutate(data)
    art.write_text(json.dumps(data, indent=1) + "\n")
    _rehash(b, rel)
    return b


def test_standings_row_refuses_an_unexpected_key(tmp_path):
    """A standings row is compared key-for-key BOTH ways: a row carrying a
    field the recomputation never produced is an unaudited channel into the
    published table, so the extra key is named rather than ignored."""
    def add_key(ds):
        row = next(r for r in ds["rows"] if r["id"] == "alpha:a1")
        row["notes"] = "temporary blip, see incident log"

    b = _cook(tmp_path, "evidence/standings.json", add_key)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/standings.json: alpha:a1: "
        "unexpected keys ['notes']"]


def test_flips_models_with_enough_history_must_recompute(tmp_path):
    """The denominator of the whole flip analysis: inflating how many series
    have >= 2 fails-bearing points makes every flip rate look better-founded
    than it is, and the artifact alone cannot be trusted to declare it."""
    def inflate(fl):
        fl["models_with_enough_history"] = 4  # metrics.json supports 3

    b = _cook(tmp_path, "evidence/flips.json", inflate)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/flips.json: "
        "models_with_enough_history declared 4, recomputed 3"]


def test_flips_one_offs_must_recompute_from_the_fails_vectors(tmp_path):
    """Deleting an inconvenient flip is the cheapest tamper on this artifact —
    the stored fails vectors still contain it, so the emptied list is named."""
    def hide(fl):
        fl["one_offs"] = []  # beta:b1 recovered on t-mul; the row is real

    b = _cook(tmp_path, "evidence/flips.json", hide)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/flips.json: one_offs does not "
        "recompute from the fails vectors: declared 0 rows, recomputed 1"]


def test_flips_equal_length_lists_name_the_differing_row(tmp_path):
    """The reason a length-only comparison could not give.

    Rewriting a flip row rather than deleting it leaves the list the same
    length, and the refusal used to read "declared 1, recomputed 1": a named
    reason that tells the reader nothing about what is wrong. SPEC §3.5."""
    def rewrite(fl):
        fl["one_offs"][0]["task"] = "t-not-the-real-task"

    b = _cook(tmp_path, "evidence/flips.json", rewrite)
    out = verify_bundle(b)
    assert len(out) == 1, out
    assert out[0].startswith(
        "raw-aggregate-mismatch: evidence/flips.json: one_offs does not "
        "recompute from the fails vectors: row 0 declared "), out[0]
    assert "t-not-the-real-task" in out[0]


def test_flips_refuses_an_unexpected_key(tmp_path):
    """Closure on the flip object: a key nothing recomputes could carry any
    claim at all past a verifier that only checked the keys it knew about."""
    def smuggle(fl):
        fl["all_clear"] = True

    b = _cook(tmp_path, "evidence/flips.json", smuggle)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/flips.json: unexpected keys "
        "['all_clear']"]


def test_narrative_claims_fired_must_equal_its_sentences(tmp_path):
    """claims_fired is the published count of generated claims; it must be
    the number of sentences actually present, not a number the issuer picks.
    (The bundle's summary still declares the honest 2, so a lie here is a
    lone, precisely named failure rather than a cascade.)"""
    def inflate(narr):
        narr["claims_fired"] = 5  # sentences[] holds 2

    b = _cook(tmp_path, "evidence/narrative.json", inflate)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/narrative.json: claims_fired "
        "declared 5, recomputed 2 (one per sentence)"]


def test_suite_hash_stamp_binds_the_protocol_to_the_fingerprint(tmp_path):
    """SPEC.md 2.3: the protocol pins the suite the board was run under. If
    that stamp may drift from the fingerprint the standings were recomputed
    against, the claim silently re-scopes itself to a different suite."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    man["protocol"]["hashes"]["suite_hash"] = "0011223344556677"
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(b) == [
        "stamp-mismatch: suite_hash: protocol 0011223344556677, "
        "artifact ffeeddcc99887766"]
