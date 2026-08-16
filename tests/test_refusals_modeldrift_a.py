"""The modeldrift raw-row gate, pinned one refusal at a time.

Every claim the drift board publishes — standings, flips, the rendered
table — is derived from the stored per-run rows in metrics.json. A row the
verifier cannot trust makes everything downstream of it unrecomputable, so
the check refuses the ROW rather than deriving from it. Each test here
cooks exactly one row-level invariant and pins the EXACT failure list, so a
refusal that stops firing shows up as a changed list, not as a still-red
bundle that is red for some other reason.

Measured, by disabling each f.append and re-running its test — what the
forged bundle returns with that one refusal gone:

  t-ordering, refusal_rate, latency_ms, runs   -> [] , a CLEAN PASS
  acc                                          -> a standings cascade that
      names gamma:g1's recomputed acc as 1.5, i.e. the symptom, never the
      out-of-range row that caused it
  the six shape/count gates                    -> the generic fail-closed
      "check contributed no recomputation", red but unnamed

So four of these refusals are the only thing between the forgery and a
green verdict, and the rest are the difference between an auditable reason
and a shrug. Both are worth a test: a gate that cannot say why it fired
cannot be audited, which is the whole point of this verifier.
"""

from __future__ import annotations

import json
import pathlib
import shutil

from vac.verify import _sha256, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"


# protocol.hashes stamps that pin the exact input bytes a derivation ran
# over. A forger who cooks an artifact owns vac.json too, so these move with
# it — see _cook.
_STAMPED = {"evidence/metrics.json": "metrics_sha256",
            "evidence/models.json": "registry_sha256"}


def _rehash(bundle: pathlib.Path, rel: str) -> None:
    man_path = bundle / "vac.json"
    man = json.loads(man_path.read_text())
    for e in man["evidence"]:
        if e["path"] == rel:
            e["sha256"] = _sha256(bundle / rel)
    if rel in _STAMPED:
        man["protocol"]["hashes"][_STAMPED[rel]] = _sha256(bundle / rel)
    man_path.write_text(json.dumps(man, indent=1) + "\n")


def _cook(tmp_path: pathlib.Path, rel: str, mutate) -> pathlib.Path:
    """Copy the honest bundle, mutate one artifact, re-pin every hash over it.

    Re-pinning is what makes these tests mean anything. Leave the manifest
    stale and the bundle goes red on sha256-mismatch (or stamp-mismatch) no
    matter what the row check does — a green test proving only that hashing
    works. With both pins moved, the bundle is internally consistent
    everywhere EXCEPT the one row invariant under test, so the refusal named
    below is the only thing standing between the forgery and a clean pass.
    """
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    art = b / rel
    data = json.loads(art.read_text())
    mutate(data)
    art.write_text(json.dumps(data, indent=1) + "\n")
    _rehash(b, rel)
    return b


# --------------------------------------------------------------------------
# shape gates: the artifact is not the thing SPEC 3 says it is


def test_metrics_series_must_be_lists_of_point_objects(tmp_path):
    def mutate(dm):
        dm["series"]["gamma:g1"] = ["2026-01-03,0.25"]  # a row, not a point

    b = _cook(tmp_path, "evidence/metrics.json", mutate)
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/metrics.json: no series object of "
        "point lists"]


def test_registry_entries_must_carry_nonempty_ids(tmp_path):
    """An id-less registry entry has no row to be held to — the standings
    recomputation keys off id, so it is refused before it is used."""
    def mutate(reg):
        reg[3]["id"] = ""

    b = _cook(tmp_path, "evidence/models.json", mutate)
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/models.json: no model registry array "
        "with ids"]


def test_fingerprint_must_declare_suite_hash(tmp_path):
    """The fingerprint is what binds every row to a suite; missing any of
    its three fields means the rows name nothing."""
    def mutate(fp):
        del fp["suite_hash"]

    b = _cook(tmp_path, "evidence/suite-fingerprint.json", mutate)
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/suite-fingerprint.json: "
        "suite_version, suite_hash, and task_ids[] required"]


def test_standings_must_be_an_object_with_rows(tmp_path):
    def mutate(stand):
        stand["rows"] = {r["id"]: r for r in stand["rows"]}  # keyed, not a list

    b = _cook(tmp_path, "evidence/standings.json", mutate)
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/standings.json: no rows[] array"]


def test_narrative_must_carry_sentences_html_and_text(tmp_path):
    """Without the plain-text mirror there is nothing to hold the html to,
    so the coherence check further down would be vacuous."""
    def mutate(narr):
        del narr["text"]

    b = _cook(tmp_path, "evidence/narrative.json", mutate)
    assert verify_bundle(b) == [
        "artifact-unparsable: evidence/narrative.json: sentences[], html, "
        "and text required"]


# --------------------------------------------------------------------------
# task count: the denominator every accuracy is over


def test_fingerprint_task_count_must_match_its_task_ids(tmp_path):
    """tasks is the denominator behind acc and the detectability floor; a
    declared count that outruns task_ids inflates nothing visibly, so it is
    recomputed rather than trusted."""
    def mutate(fp):
        fp["tasks"] = 5

    b = _cook(tmp_path, "evidence/suite-fingerprint.json", mutate)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/suite-fingerprint.json: tasks "
        "declared 5, recomputed 4 (len of task_ids)"]


# --------------------------------------------------------------------------
# per-point coherence: one cooked field per test, so the named reason is
# the whole verdict rather than the head of a cascade


def test_series_points_must_not_travel_backwards_in_time(tmp_path):
    """Ordering is load-bearing: "last two stored runs" is positional, so a
    series sorted by anything but time silently re-picks the delta pair."""
    def mutate(dm):
        dm["series"]["alpha:a1"][1]["t"] = "2025-12-31T00:00:00Z"

    b = _cook(tmp_path, "evidence/metrics.json", mutate)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/metrics.json: alpha:a1[1]: "
        "t '2025-12-31T00:00:00Z' precedes '2026-01-01T00:00:00Z'"]


def test_point_acc_must_be_a_unit_fraction(tmp_path):
    """acc above 1 would publish an above-100% board row."""
    def mutate(dm):
        dm["series"]["gamma:g1"][0]["acc"] = 1.5

    b = _cook(tmp_path, "evidence/metrics.json", mutate)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/metrics.json: gamma:g1[0]: "
        "acc 1.5 outside [0,1]"]


def test_point_refusal_rate_must_be_a_unit_fraction(tmp_path):
    """refusal_rate is optional, but once present it is held to [0,1] —
    optional must not mean unchecked."""
    def mutate(dm):
        dm["series"]["gamma:g1"][0]["refusal_rate"] = 1.5

    b = _cook(tmp_path, "evidence/metrics.json", mutate)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/metrics.json: gamma:g1[0]: "
        "refusal_rate 1.5 outside [0,1]"]


def test_point_latency_must_be_a_nonnegative_number(tmp_path):
    def mutate(dm):
        dm["series"]["gamma:g1"][0]["latency_ms"] = -1.0

    b = _cook(tmp_path, "evidence/metrics.json", mutate)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/metrics.json: gamma:g1[0]: "
        "latency_ms -1.0 not a number >= 0"]


def test_point_runs_must_be_at_least_one(tmp_path):
    """runs is the sample count acc_spread is over; zero runs would make a
    spread claim describe no measurement at all."""
    def mutate(dm):
        dm["series"]["gamma:g1"][0]["runs"] = 0

    b = _cook(tmp_path, "evidence/metrics.json", mutate)
    assert verify_bundle(b) == [
        "raw-aggregate-mismatch: evidence/metrics.json: gamma:g1[0]: "
        "runs 0 < 1"]
