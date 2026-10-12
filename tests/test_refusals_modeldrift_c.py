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


# --- the reliability floor applies to flips, not only to standings ---------------
#
# Found 2026-10-12 by verifying model-drift's committed bundle: 9 refusals, all one
# cause. model-drift has filtered outage points (reliability below rel_floor) out of
# its flip analysis since 2026-10-05, because 268 of 895 recorded flips were
# manufactured by 19 outage points. This profile already read the floor and applied
# it to the standings, then recomputed flips over the raw series and refused every
# bundle the issuer had cut since. A recompute that applies the floor to one derived
# view and not the other is not a recompute of the board; it is a second board.

def _cook_v02_metrics(tmp_path: pathlib.Path, mutate) -> pathlib.Path:
    """Copy the 0.2 fixture, add one stored point to alpha:a1, and re-pin
    everything an honest issuer would have re-pinned with it: the evidence
    sha256, the protocol's metrics_sha256 stamp, and the declared raw point
    count. Nothing derived (standings, flips) is touched, which is the point."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "v02-twin-arms", b)
    rel = "evidence/metrics.json"
    art = b / rel
    data = json.loads(art.read_text())
    mutate(data)
    art.write_text(json.dumps(data, indent=1) + "\n")
    _rehash(b, rel)
    man_path = b / "vac.json"
    man = json.loads(man_path.read_text())
    man["protocol"]["hashes"]["metrics_sha256"] = _sha256(art)
    for c in man["results"]["checks"]:
        if c.get("profile") == "modeldrift-board-v1" and "points" in c.get("expect", {}):
            c["expect"]["points"] += 1
    for v in man["results"].get("summary", {}).values():
        if isinstance(v, dict) and "points" in v:
            v["points"] += 1
    man_path.write_text(json.dumps(man, indent=1) + "\n")
    return b


def _outage_point(reliability: float) -> dict:
    """A point between alpha:a1's first and second runs whose fails set differs
    from both neighbours, so it would manufacture two flips if counted. It is
    not the newest point, so the standings never see it either way."""
    return {"t": "2026-01-01T12:00:00Z", "acc": 0.0, "latency_ms": 120.0,
            "reliability": reliability, "refusal_rate": 0.0,
            "fails": ["t-add", "t-sub", "t-mul", "t-div"]}


def test_a_point_below_the_floor_manufactures_no_flip(tmp_path):
    """Under rel_floor 0.5 an outage point is excluded from the flip
    recomputation exactly as it is from the standings, so the committed flips
    artifact, derived without it, still verifies."""
    def add_outage(m):
        m["series"]["alpha:a1"].insert(1, _outage_point(0.1))
    b = _cook_v02_metrics(tmp_path, add_outage)
    assert verify_bundle(b) == []


def test_the_same_point_at_full_reliability_is_a_real_flip(tmp_path):
    """The negative case the fix needs: the floor is why the point is ignored,
    not that the recompute stopped looking. Raise its reliability and the
    committed flips artifact is refused for not containing what the vectors
    now show."""
    def add_measured(m):
        m["series"]["alpha:a1"].insert(1, _outage_point(1.0))
    b = _cook_v02_metrics(tmp_path, add_measured)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/flips.json: repeat_offenders does "
        "not recompute from the fails vectors: declared 1 rows, recomputed 3",
        "summary-mismatch: repeat_offenders: declared 1, recomputed 3"]
