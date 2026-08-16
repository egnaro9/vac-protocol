"""The last surviving refusals, pinned.

After the coverage sweep these five were the only reachable refusals nothing
tested. They are the tail, which is exactly where a mutation score stops being
flattering and starts being work: none of them was found by an audit, and none
would have been found by fixing a reported bug.

Every test asserts the EXACT failure list, and each was checked by neutralising
its target refusal and confirming the test goes red.
"""
from __future__ import annotations

import json
import pathlib
import shutil

from vac.verify import _sha256, verify_bundle

FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures"


def _bundle(tmp_path: pathlib.Path) -> pathlib.Path:
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    return b


def _repin(b: pathlib.Path, rel: str) -> None:
    """Honest re-pin: the forger owns vac.json too, so a test that leans on a
    stale hash is testing the hash, not the arithmetic it claims to pin."""
    p = b / "vac.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    for e in man["evidence"]:
        if e["path"] == rel:
            e["sha256"] = _sha256(b / rel)
    p.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")


def _raw(b: pathlib.Path) -> tuple[pathlib.Path, list[dict]]:
    p = b / "evidence/raw_results.jsonl"
    return p, [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()
               if x.strip()]


def _write_raw(b: pathlib.Path, p: pathlib.Path, lines: list[dict]) -> None:
    p.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    _repin(b, "evidence/raw_results.jsonl")


def test_a_raw_line_whose_detected_flag_contradicts_its_own_pair(tmp_path):
    """`detected` must follow from (defective_failed AND clean_passed) on that
    same line. Taking it on faith lets an issuer flip the headline finding
    while both underlying booleans stay honest."""
    b = _bundle(tmp_path)
    p, lines = _raw(b)
    lines[0]["detected"] = not lines[0]["detected"]
    _write_raw(b, p, lines)
    key = f"{lines[0]['suite']}/{lines[0]['member']}"
    assert any(x == f"raw-aggregate-mismatch: {key}: raw line 1 detected flag "
               "contradicts its own pair" for x in verify_bundle(b)), \
        verify_bundle(b)


def test_an_aggregate_row_with_no_raw_lines(tmp_path):
    """A board row summarising nothing. Without this the aggregate can invent
    a member that never ran."""
    b = _bundle(tmp_path)
    agg = b / "evidence/results.json"
    d = json.loads(agg.read_text(encoding="utf-8"))
    ghost = dict(d["rows"][0])
    ghost["member"] = "ghost-member"
    d["rows"].append(ghost)
    agg.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    _repin(b, "evidence/results.json")
    out = verify_bundle(b)
    assert any("ghost-member: aggregate row has no raw lines" in x
               for x in out), out


def test_raw_lines_with_no_aggregate_row(tmp_path):
    """The other direction: drop a member from the board and its raw lines
    become unreported. Silent omission is the cheapest way to improve an
    average."""
    b = _bundle(tmp_path)
    agg = b / "evidence/results.json"
    d = json.loads(agg.read_text(encoding="utf-8"))
    dropped = d["rows"].pop()
    agg.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    _repin(b, "evidence/results.json")
    out = verify_bundle(b)
    assert any(f"{dropped['suite']}/{dropped['member']}: raw lines with no "
               "aggregate row" in x for x in out), out


def test_an_evalmut_row_naming_an_operator_outside_the_catalog(tmp_path):
    """The catalog is the provenance gate: every row must trace to a mined
    operator. A row citing an unknown id is an operator with no documented
    defect behind it."""
    b = _bundle(tmp_path)
    art = "evidence/evalmut_run.json"
    p = b / art
    d = json.loads(p.read_text(encoding="utf-8"))
    d["results"][0]["operator_id"] = "not-a-real-operator"
    p.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")
    _repin(b, art)
    out = verify_bundle(b)
    assert any(f"raw-aggregate-mismatch: {art}: row 1 operator "
               "'not-a-real-operator' is not in the catalog" == x
               for x in out), out


# NOT TESTED, and deliberately: the OSError branches in both render
# comparators (vac/verify.py, "artifact-unparsable: {render_rel}: {e}") are
# unreachable. `render` is a declared ref, so a render not listed in evidence is
# refused earlier as check-artifact-not-listed, and one that IS listed has
# already been opened and sha256'd by _verify_artifacts before the check runs.
# Probed both ways rather than assumed: listing a directory yields
# "missing-artifact: evidence". They are in the sweep's EXCLUDE with that
# reason, not covered by a test that would only pretend to reach them.


def test_a_checker_that_returns_none_silently_is_still_named(monkeypatch):
    """The fail-closed backstop (vac/verify.py: "check contributed no
    recomputation").

    No bundle can trigger this: every profile checker appends a reason before
    returning None, which is precisely what the backstop is insurance against.
    So the reachable defect is a BUGGY CHECKER, and that is what this
    simulates. Without it, a future checker that returns None on some path
    would make its whole check vanish from the verdict while the bundle still
    exited 0 -- a check that ran, found nothing, and said nothing.
    """
    from vac import verify as V

    profile = "certlab-bundle-v1"
    monkeypatch.setitem(V._CHECK_FNS, profile,
                        lambda bundle_dir, check, proto, f: None)
    out = V.verify_bundle(FIX / "valid")
    assert f"artifact-unparsable: {profile}: check contributed no " \
           "recomputation" in out, out


def test_the_backstop_stays_quiet_when_the_checker_names_its_own_reason():
    """The control for the test above. A backstop that fires even when the
    checker DID report is a backstop that doubles every real reason -- so pin
    both directions, not just the one that fires."""
    from vac import verify as V

    assert V.verify_bundle(FIX / "valid") == []
