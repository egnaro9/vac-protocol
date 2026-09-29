"""The archived CI logs must still say what the paper says they say.

GitHub Actions keeps run logs for 90 days. The arXiv v2 draft cites figures
that exist nowhere else: no post-v1 mutation sweep output is committed to this
repository, and the per-site verdicts for `a17af5c` were only ever printed by a
CI job. `paper/ci-logs/` is the copy taken while those runs were still
reachable, and `paper/ci-logs/MANIFEST.json` is its record.

An archive nobody checks rots in three ways, and each has a test below:

1. A file is dropped, renamed or truncated. Caught by the bijection between the
   manifest and the directory, and by the length and sha256 of every entry.
2. A log is filed under the wrong run or the wrong commit. Caught by requiring
   each log to name its own head commit, which every Actions log does in its
   checkout lines.
3. The manifest, or the paper, comes to claim a number the log never printed.
   Caught by reading the figures back out of the logs and comparing them with
   the values the citation rests on.

Every check here is offline. Nothing in this file contacts GitHub, so it keeps
working after the runs expire, which is the whole point of the archive.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "paper" / "ci-logs"
MANIFEST_PATH = ARCHIVE / "MANIFEST.json"

# The runs the v2 ledger cites, and the item that cites each one. Taken from
# `paper/arxiv/v2/V2_CHANGE_LEDGER.md`: V2-07's CI "MUTATION SCORE" list,
# V2-34's refusal-coverage job 95117946431, V2-46's named runs, and V2-42's
# model-drift track runs. If a citation loses its log, this list is what
# notices.
REQUIRED_RUNS = {
    31927793408: "V2-34",
    33159814662: "V2-07",
    33161590378: "V2-07",
    33163033473: "V2-07",
    33197719579: "V2-07",
    33198957969: "V2-07",
    33297411944: "V2-07",
    33369255102: "V2-07",
    34733162559: "V2-07",
    35261829754: "V2-07",
    35261829963: "V2-46",
    32695974153: "V2-46",
    33388729376: "V2-46",
    34112794528: "V2-46",
    34835695565: "V2-46",
    31249636235: "V2-42",
    31304963616: "V2-42",
    31376273128: "V2-42",
    31787685327: "V2-42",
    31937330672: "V2-42",
}

# The mutation score each run printed, keyed by run id, with the short head
# commit it was measured at. This is the sequence V2-07's "Since v1" paragraph
# walks, plus the 0.925 row V2-34 rests on. Keying by run id rather than by
# commit matters: `6a05245` and `c441011` each have more than one run archived,
# and only the `vac` workflow runs the sweep. A log swapped for another run's
# log fails here even when its sha256 is recorded correctly.
EXPECTED_SCORES = {
    31927793408: ("a17af5c", 123, 133),
    33159814662: ("3f49c14", 152, 152),
    33161590378: ("0bca936", 152, 152),
    33163033473: ("2e5734b", 157, 157),
    33197719579: ("08f995b", 161, 161),
    33198957969: ("f1511f5", 161, 161),
    33297411944: ("652e71b", 166, 166),
    33369255102: ("6a05245", 166, 166),
    34733162559: ("0b44bf2", 166, 166),
    35261829754: ("c441011", 168, 168),
}

# V2-34's per-site claim, read off the job it cites.
A17_RUN = 31927793408
A17_VERDICT_LINES = 133
A17_CAUGHT = 123
A17_SURVIVORS = [325, 362, 384, 393, 461, 466, 470, 572, 592, 1348]

SCORE_RE = re.compile(rb"MUTATION SCORE: (\d+)/(\d+) = [\d.]+")
VERDICT_RE = re.compile(rb"\[(\d+)/(\d+)\] L(\d+) (\*\*\* SURVIVED \*\*\*|caught)")


def _manifest() -> dict:
    assert MANIFEST_PATH.is_file(), (
        f"{MANIFEST_PATH.relative_to(ROOT)} is missing. The CI logs the v2 "
        "draft cites are kept for 90 days by GitHub and the earliest expires "
        "2026-11-06; without this archive those citations cannot be checked "
        "by anyone, including the author.")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return _manifest()


@pytest.fixture(scope="module")
def entries(manifest: dict) -> list:
    got = manifest["entries"]
    assert got, "the manifest lists no runs, so every check below is vacuous"
    return got


def test_every_cited_run_is_archived(entries):
    """A citation whose log is gone is a citation nobody can check."""
    have = {e["run_id"] for e in entries}
    missing = {rid: item for rid, item in REQUIRED_RUNS.items()
               if rid not in have}
    assert missing == {}, (
        "these runs are cited by the v2 ledger and have no archived log: "
        f"{missing}")


def test_the_manifest_and_the_directory_agree(entries):
    """A file added without a record, or recorded without a file, means the
    manifest is no longer the archive's index."""
    on_disk = {str(p.relative_to(ARCHIVE))
               for p in ARCHIVE.rglob("*.log") if p.is_file()}
    listed = {e["file"] for e in entries}
    assert on_disk == listed, (
        f"only on disk: {sorted(on_disk - listed)}; "
        f"only in the manifest: {sorted(listed - on_disk)}")


def test_each_log_matches_its_recorded_length_and_hash(entries):
    """Truncation and silent editing both show up here."""
    bad = []
    for e in entries:
        p = ARCHIVE / e["file"]
        if not p.is_file():
            bad.append(f"{e['file']}: missing")
            continue
        blob = p.read_bytes()
        if len(blob) != e["bytes"]:
            bad.append(f"{e['file']}: {len(blob)} bytes, recorded {e['bytes']}")
            continue
        got = hashlib.sha256(blob).hexdigest()
        if got != e["sha256"]:
            bad.append(f"{e['file']}: sha256 {got}, recorded {e['sha256']}")
    assert bad == [], bad


def test_each_log_names_its_own_head_commit(entries):
    """An Actions log prints the commit it checked out. A log filed under the
    wrong run keeps its own sha and fails here, which a hash of the stored
    bytes alone would never catch."""
    bad = []
    for e in entries:
        blob = (ARCHIVE / e["file"]).read_bytes()
        if e["head_sha"].encode() not in blob:
            bad.append(f"{e['file']}: does not contain {e['head_sha']}")
    assert bad == [], bad


def test_each_log_still_prints_the_text_its_citation_rests_on(entries):
    """`must_contain` is the quoted evidence, not a summary of it. If the
    paper's sentence and the log ever part company, one of them moved."""
    checked = 0
    bad = []
    for e in entries:
        blob = (ARCHIVE / e["file"]).read_bytes()
        for needle in e["must_contain"]:
            checked += 1
            if needle.encode() not in blob:
                bad.append(f"{e['file']}: absent: {needle!r}")
    assert bad == [], bad
    assert checked >= len(entries), (
        "at least one entry records no quoted evidence, so its log is stored "
        "without anything tying it to a claim")


def test_the_mutation_score_path_reads_back_off_the_logs(entries):
    """V2-07's population path and V2-34's 0.925 row, recomputed from the
    archived output rather than copied forward from the ledger."""
    by_run = {e["run_id"]: e for e in entries}
    bad = []
    for run_id, (short, num, den) in EXPECTED_SCORES.items():
        e = by_run.get(run_id)
        if e is None:
            bad.append(f"run {run_id}: no archived log")
            continue
        if e["head_sha"][:7] != short:
            bad.append(f"run {run_id}: archived at {e['head_sha'][:7]}, "
                       f"cited at {short}")
            continue
        blob = (ARCHIVE / e["file"]).read_bytes()
        found = {(int(m.group(1)), int(m.group(2)))
                 for m in SCORE_RE.finditer(blob)}
        if found != {(num, den)}:
            bad.append(f"run {run_id} ({short}): log prints "
                       f"{sorted(found)}, expected {(num, den)}")
    assert bad == [], bad


def test_the_a17af5c_job_still_prints_every_site_verdict():
    """V2-34 replaces a caught-count argument with the per-site record from
    this one job. The record is 133 verdict lines, 123 of them caught. Nothing
    else in the repository holds it."""
    entries = _manifest()["entries"]
    match = [e for e in entries if e["run_id"] == A17_RUN]
    assert len(match) == 1, f"expected one entry for run {A17_RUN}, got {match}"
    blob = (ARCHIVE / match[0]["file"]).read_bytes()
    verdicts = VERDICT_RE.findall(blob)
    assert len(verdicts) == A17_VERDICT_LINES, (
        f"{len(verdicts)} verdict lines, expected {A17_VERDICT_LINES}")
    caught = [v for v in verdicts if v[3] == b"caught"]
    survivors = sorted(int(v[2]) for v in verdicts if v[3] != b"caught")
    assert len(caught) == A17_CAUGHT, (
        f"{len(caught)} caught, expected {A17_CAUGHT}")
    assert survivors == A17_SURVIVORS, survivors


def test_the_recorded_expiry_follows_the_retention_policy(manifest, entries):
    """The archive exists because of a deadline, so the deadline is part of the
    record. GitHub measures retention from completion, so the estimate is a
    lower bound on the real expiry and never later than it."""
    days = manifest["retention_days"]
    assert days == 90, days
    bad = []
    for e in entries:
        created = dt.datetime.strptime(
            e["run_created_utc"], "%Y-%m-%dT%H:%M:%SZ")
        want = (created + dt.timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        if e["expires_utc_estimate"] != want:
            bad.append(f"{e['file']}: recorded {e['expires_utc_estimate']}, "
                       f"policy gives {want}")
    assert bad == [], bad


def test_the_archive_is_readable_as_stored(entries):
    """A control. If the logs were unreadable or empty the checks above would
    pass by finding nothing, so a green run has to mean real bytes were read."""
    sizes = [(ARCHIVE / e["file"]).stat().st_size for e in entries]
    assert len(sizes) >= len(REQUIRED_RUNS)
    assert min(sizes) > 1000, sizes
