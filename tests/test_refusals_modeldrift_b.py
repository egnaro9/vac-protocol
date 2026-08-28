"""The modeldrift point-arithmetic and standings-recomputation refusals that
the committed fixtures never exercise. Each test cooks ONE field of the valid
bundle so exactly one named reason can fire, and asserts the whole failure
list — a substring search over a cascade would pass against the very defect
this verifier exists to refuse.

Every bundle here is cooked the way a motivated publisher would cook one: the
edited artifact's sha256 is honestly re-pinned in evidence[] AND in the
protocol.hashes stamp that covers it, so no mechanical inconsistency is left
for a hash check to trip over. The only thing wrong with these bundles is the
arithmetic, which is the sole thing these refusals are here to catch."""

from __future__ import annotations

import json
import pathlib
import shutil

from vac.verify import _sha256, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"

MET = "evidence/metrics.json"
STAND = "evidence/standings.json"
RESULTS_MD = "evidence/RESULTS.md"
# protocol.hashes stamps that pin an artifact's bytes independently of
# evidence[] — re-pinned too, or they mask the refusal under test
STAMPS = {"metrics_sha256": MET, "registry_sha256": "evidence/models.json"}


def _repin(bundle: pathlib.Path, rel: str) -> None:
    man_path = bundle / "vac.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    for e in man["evidence"]:
        if e["path"] == rel:
            e["sha256"] = _sha256(bundle / rel)
    for key, covered in STAMPS.items():
        if covered == rel:
            man["protocol"]["hashes"][key] = _sha256(bundle / covered)
    man_path.write_text(json.dumps(man, indent=1) + "\n",
                        encoding="utf-8", newline="")


def _cook_all(tmp_path: pathlib.Path, edits: dict) -> pathlib.Path:
    """Copy the valid bundle and apply one mutator per artifact, honestly
    re-pinning every hash that covers the bytes each one changed. A JSON
    mutator is handed the parsed object and edits in place; a text mutator
    is handed the text and returns its replacement."""
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    for rel, edit in edits.items():
        art = b / rel
        if rel.endswith(".json"):
            doc = json.loads(art.read_text(encoding="utf-8"))
            edit(doc)
            art.write_text(json.dumps(doc, indent=1) + "\n",
                           encoding="utf-8", newline="")
        else:
            art.write_text(edit(art.read_text(encoding="utf-8")),
                           encoding="utf-8", newline="")
        _repin(b, rel)
    return b


def _cook(tmp_path: pathlib.Path, rel: str, edit) -> pathlib.Path:
    return _cook_all(tmp_path, {rel: edit})


# ------------------------------------------------------------- the instrument


def test_cooking_harness_alone_produces_a_clean_bundle(tmp_path):
    """Prove the instrument before the finding: copy, re-serialize and re-pin
    both artifacts with a no-op edit and the bundle must still verify clean.
    Without this, every refusal below could be firing on damage the harness
    itself did, and the exact-list assertions would be measuring nothing."""
    assert verify_bundle(_cook(tmp_path, MET, lambda doc: None)) == []
    assert verify_bundle(_cook(tmp_path / "s", STAND, lambda doc: None)) == []


# ---------------------------------------------------------------- per-point


def test_acc_spread_must_not_be_negative(tmp_path):
    """Spread is a width, and a negative width would shrink any confidence
    band derived from it — the direction that manufactures significance."""
    def edit(dm):
        dm["series"]["alpha:a1"][2]["acc_spread"] = -0.25
    assert verify_bundle(_cook(tmp_path, MET, edit)) == [
        f"raw-aggregate-mismatch: {MET}: alpha:a1[2]: acc_spread -0.25 < 0"]


def test_fails_must_name_tasks_inside_the_suite(tmp_path):
    """A fails vector naming a task the fingerprint does not list is either a
    stale suite or an invented failure; either way nothing downstream (flips,
    probe alarms) is recomputable from it. gamma:g1 carries no fails_runs, so
    this refusal fires alone."""
    def edit(dm):
        dm["series"]["gamma:g1"][0]["fails"].append("t-ghost")
    assert verify_bundle(_cook(tmp_path, MET, edit)) == [
        f"raw-aggregate-mismatch: {MET}: gamma:g1[0]: fails name tasks "
        "outside the suite: ['t-ghost']"]


def test_graded_must_lie_within_the_suite_size(tmp_path):
    """graded is the accuracy denominator AND the per-model floor (100/graded),
    so claiming more graded calls than the suite has tasks shrinks the floor a
    delta must clear — how a movement smaller than the instrument gets sold
    as a regression. Cooked CONSISTENTLY: the standings row and the rendered
    table are both re-derived from graded 9, so nothing downstream disagrees
    and this bounds check is the only thing left that can refuse it."""
    def metrics(dm):
        dm["series"]["alpha:a1"][2]["graded"] = 9

    def standings(ds):
        row = next(r for r in ds["rows"] if r["id"] == "alpha:a1")
        row["graded"] = 9
        row["min_detectable_pts"] = 11.111  # round(100 / 9, 3)

    def table(text):
        # Alpha's floor cell; Beta's reads "±33.3 ⚠ below floor", so unique
        assert text.count("| ±25.0 |") == 1, text
        return text.replace("| ±25.0 |", "| ±11.1 |")

    b = _cook_all(tmp_path, {MET: metrics, STAND: standings,
                             RESULTS_MD: table})
    assert verify_bundle(b) == [
        f"raw-aggregate-mismatch: {MET}: alpha:a1[2]: graded 9 "
        "outside 1..4"]


def test_point_suite_version_must_match_the_fingerprint(tmp_path):
    """A point stamped with a different suite version is a comparison across
    two different tests — the drift it shows is the suite moving."""
    def edit(dm):
        dm["series"]["alpha:a1"][2]["suite"] = "toy-suite-v2"
    assert verify_bundle(_cook(tmp_path, MET, edit)) == [
        f"raw-aggregate-mismatch: {MET}: alpha:a1[2]: suite 'toy-suite-v2' "
        "is not 'toy-suite-v1'"]


def test_point_suite_hash_must_match_the_fingerprint(tmp_path):
    """Same version string, different suite bytes: the hash is the half of the
    stamp that catches an edited task under an unchanged version label."""
    def edit(dm):
        dm["series"]["alpha:a1"][2]["suite_hash"] = "0" * 16
    assert verify_bundle(_cook(tmp_path, MET, edit)) == [
        f"raw-aggregate-mismatch: {MET}: alpha:a1[2]: suite_hash "
        "'0000000000000000' is not 'ffeeddcc99887766'"]


def test_fails_runs_must_be_a_list_of_samples(tmp_path):
    """A flat list of task ids where per-run samples belong would be read as
    N one-task runs; the shape is refused rather than coerced."""
    def edit(dm):
        dm["series"]["alpha:a1"][2]["fails_runs"] = ["t-add", "t-sub"]
    assert verify_bundle(_cook(tmp_path, MET, edit)) == [
        f"raw-aggregate-mismatch: {MET}: alpha:a1[2]: fails_runs "
        "['t-add', 't-sub'] is not a list of samples"]


def test_fails_runs_samples_must_name_tasks_inside_the_suite(tmp_path):
    """Per-sample task binding, not just the aggregated vector — the stored
    `fails` stays a genuine member of fails_runs here, so only the sample-level
    refusal can account for the failure."""
    def edit(dm):
        dm["series"]["alpha:a1"][2]["fails_runs"][1] = ["t-add", "t-ghost"]
    assert verify_bundle(_cook(tmp_path, MET, edit)) == [
        f"raw-aggregate-mismatch: {MET}: alpha:a1[2]: fails_runs[1] names "
        "tasks outside the suite: ['t-ghost']"]


def test_fails_must_be_one_of_its_own_runs(tmp_path):
    """The published vector has to be a run that actually happened, not a
    summary of several. Every sample here is well-formed and in-suite, so the
    only thing wrong is that `fails` is not among them."""
    def edit(dm):
        dm["series"]["alpha:a1"][2]["fails_runs"] = [["t-add"]] * 3
    assert verify_bundle(_cook(tmp_path, MET, edit)) == [
        f"raw-aggregate-mismatch: {MET}: alpha:a1[2]: fails is not one of "
        "its own fails_runs samples"]


# ---------------------------------------------------------------- standings


def test_standings_full_grade_floor_is_recomputed(tmp_path):
    """The board-wide floor is 100/tasks, not a number the publisher gets to
    declare — understating it is how a movement smaller than the instrument
    can be printed as a finding."""
    def edit(ds):
        ds["min_detectable_pts_full_grade"] = 20.0
    assert verify_bundle(_cook(tmp_path, STAND, edit)) == [
        f"raw-aggregate-mismatch: {STAND}: min_detectable_pts_full_grade "
        "declared 20.0, recomputed 25.0"]


def test_standings_rejects_unrecomputed_top_level_keys(tmp_path):
    """Recomputation is exact-shape: a key nobody re-earns is a claim riding
    along inside a verified artifact."""
    def edit(ds):
        ds["headline_regression_pts"] = 42.0
    assert verify_bundle(_cook(tmp_path, STAND, edit)) == [
        f"raw-aggregate-mismatch: {STAND}: unexpected keys "
        "['headline_regression_pts']"]


def test_standings_rows_must_follow_registry_order(tmp_path):
    """Rows are matched to the registry positionally, so a reordering (same
    count, same ids) would silently pair every row with the wrong model's
    recomputation. Order is pinned before any field is compared."""
    def edit(ds):
        ds["rows"][1], ds["rows"][2] = ds["rows"][2], ds["rows"][1]
    assert verify_bundle(_cook(tmp_path, STAND, edit)) == [
        f"raw-aggregate-mismatch: {STAND}: rows do not cover the registry in "
        "registry order (declared 5, recomputed 5)"]
