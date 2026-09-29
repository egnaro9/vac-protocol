"""The render comparator's refusals, pinned.

`evalmut-run-v1` may declare a `render`: the human-readable .txt a payload was
rendered into. Both of evalmut's renders were pinned as evidence and read by no
check, so the bundle shipped headline numbers nothing verified. This comparator
closes that — and its own refusals are tested here, because shipping a
closure-check with untested refusals would repeat the original mistake.

Deliberately NOT a byte-identity re-render: reimplementing evalmut's layout in
the verifier would couple it to formatting and break on a cosmetic change. What
must be impossible is a render showing numbers the payload does not support.
"""
from __future__ import annotations

import json
import pathlib
import shutil

import pytest

from vac.verify import _check_evalmut_render, _sha256, verify_bundle

WANT = {"caught": 32, "applied": 35, "na": 150, "score_3": 0.914,
        "results": 185}

HONEST = ("────────\n  evalmut — does your eval actually check anything?\n"
          "  mutation score    91.4%   (32 caught / 35 applied; 150 n/a)\n"
          "  holes            3  (1 blind, 2 coverage-gap)\n")


def _run(text: str, want: dict | None = None) -> list[str]:
    f: list[str] = []
    _check_evalmut_render("r.txt", text, dict(want or WANT), f)
    return f


def test_an_agreeing_render_is_clean():
    """The control. Without it, a comparator that refuses everything would
    look identical to one that works."""
    assert _run(HONEST) == []


def test_a_render_with_no_headline_is_refused():
    """The load-bearing one. A comparator that shrugs at an unparseable
    render passes every doctored file that omits the line it looks for —
    the exact defect this whole profile family exists to refuse."""
    assert _run("  a report with no mutation score line at all\n") == [
        "artifact-unparsable: r.txt: no 'mutation score' headline to "
        "compare against the payload"]


@pytest.mark.parametrize("frm,to,field,shown,real", [
    ("32 caught", "99 caught", "caught", 99, 32),
    ("35 applied", "40 applied", "applied", 40, 35),
    ("150 n/a", "7 n/a", "na", 7, 150),
])
def test_a_render_that_outruns_its_payload_is_refused(frm, to, field, shown,
                                                      real):
    assert _run(HONEST.replace(frm, to)) == [
        f"raw-aggregate-mismatch: r.txt: render shows {field} {shown}, "
        f"payload recomputes {real}"]


def test_a_sweetened_score_is_refused():
    assert _run(HONEST.replace("91.4%", "99.9%")) == [
        "raw-aggregate-mismatch: r.txt: render shows score_3 0.999, "
        "payload recomputes 0.914"]


def test_a_field_the_payload_cannot_recompute_is_refused():
    """If the profile stops recomputing a field the render names, the
    comparator must say so rather than quietly compare the remaining keys."""
    want = {k: v for k, v in WANT.items() if k != "na"}
    assert _run(HONEST, want) == [
        "artifact-unparsable: r.txt: render headline names na, which this "
        "profile does not recompute"]


def test_rounding_to_one_decimal_is_not_a_mismatch():
    """The render prints 0.1% precision; holding it to full float equality
    would make every honest bundle fail — a gate that cries wolf gets
    disabled, which is its own kind of vacuous."""
    assert _run(HONEST, {**WANT, "score_3": 0.914}) == []


# ── certlab: the capability contract ────────────────────────────────────────
# Same shape, same reason: CONTRACT.md is the artifact a human reads, so it is
# the one worth doctoring. Added with tests because shipping the evalmut
# comparator's twin untested is how the score quietly rots.

from vac.verify import _check_certlab_render  # noqa: E402

CWANT = {"verdicts": 6, "fixed": 6, "policy_ok": 6, "tests_ok": 6}
CONTRACT = ("# Capability contract — claude-code-headless\n\n"
            "**6/6 seeded defects fixed** under policy "
            "(test suite untouched).\n")


def _crun(text: str, want: dict | None = None) -> list[str]:
    f: list[str] = []
    _check_certlab_render("CONTRACT.md", text, dict(want or CWANT), f)
    return f


def test_an_agreeing_contract_is_clean():
    assert _crun(CONTRACT) == []


def test_a_contract_with_no_headline_is_refused():
    assert _crun("# a contract that states no counts at all\n") == [
        "artifact-unparsable: CONTRACT.md: no 'N/M seeded defects fixed' "
        "headline to compare against the verdicts"]


def test_a_contract_claiming_more_fixes_than_the_verdicts_is_refused():
    assert _crun(CONTRACT.replace("**6/6", "**9/6")) == [
        "raw-aggregate-mismatch: CONTRACT.md: contract shows fixed 9, "
        "verdicts recompute 6"]


def test_a_contract_claiming_more_tasks_than_the_verdicts_is_refused():
    assert _crun(CONTRACT.replace("6/6 seeded", "6/9 seeded")) == [
        "raw-aggregate-mismatch: CONTRACT.md: contract shows verdicts 9, "
        "verdicts recompute 6"]


def test_a_field_the_profile_cannot_recompute_is_refused():
    want = {k: v for k, v in CWANT.items() if k != "fixed"}
    assert _crun(CONTRACT, want) == [
        "artifact-unparsable: CONTRACT.md: contract names fixed, which this "
        "profile does not recompute"]


# ── the read wrapper, end to end ────────────────────────────────────────────
# Both comparators reach their render through read_text(encoding="utf-8")
# inside `except (OSError, UnicodeDecodeError)`. The mutation sweep excluded
# both appends as unreachable OSError wrappers, on the ground that a declared
# render has already been opened and sha256'd by _verify_artifacts before the
# check runs. That argument is about OSError. The hash pass reads BYTES, so a
# render that is listed, correctly hashed and not valid UTF-8 reaches the
# decode and the line fires. Deleting either append makes such a bundle verify
# clean, and nothing noticed: not the suite, not the liveness control, not the
# tamper corpus. The tests above call the comparators directly and cannot see
# the wrapper at all, which is why these two go through verify_bundle().

FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
NOT_UTF8 = b"x \xff\xfe not utf-8\n"

# (profile, render path, a render that agrees with fixtures/valid)
WRAPPED = [
    ("certlab-bundle-v1", "evidence/CONTRACT.md",
     "# Capability contract\n\n**2/3 seeded defects fixed** under policy.\n"),
    ("evalmut-run-v1", "evidence/evalmut_report.txt",
     "  mutation score    57.1%   (4 caught / 7 applied; 1 n/a)\n"),
]


def _bundle_with_render(tmp_path, profile: str, rel: str,
                        data: bytes) -> pathlib.Path:
    """fixtures/valid with `data` written at `rel`, listed in evidence under
    its REAL sha256, and declared as `profile`'s render.

    The hash is honest on purpose. A stale one is refused by the artifact
    pass, the check never runs, and a test leaning on that would pass without
    reaching the line it claims to cover.
    """
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    (b / rel).write_bytes(data)
    p = b / "vac.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    man["evidence"].append({"path": rel, "sha256": _sha256(b / rel)})
    man["evidence"].sort(key=lambda e: e["path"])
    for c in man["results"]["checks"]:
        if c["profile"] == profile:
            c["render"] = rel
    p.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    return b


@pytest.mark.parametrize("profile,rel", [(p, r) for p, r, _ in WRAPPED])
def test_a_declared_render_that_is_not_utf8_is_refused(tmp_path, profile, rel):
    """The wrapper, reached the only way a bundle can reach it. The message
    text below the prefix is CPython's, so it is not pinned here; what is
    pinned is that exactly one refusal fires, that it names the render, and
    that it says the decode failed."""
    out = verify_bundle(_bundle_with_render(tmp_path, profile, rel, NOT_UTF8))
    assert len(out) == 1, out
    assert out[0].startswith(f"artifact-unparsable: {rel}: "), out
    assert "codec can't decode" in out[0], out


@pytest.mark.parametrize("profile,rel,honest", WRAPPED)
def test_a_decodable_agreeing_render_leaves_the_bundle_clean(tmp_path, profile,
                                                             rel, honest):
    """Liveness for the test above. Without it, a bundle broken by the
    scaffolding, an unlisted file or a stale hash, would be refused for a
    reason that has nothing to do with the encoding, and the test above would
    pass while the wrapper was never reached."""
    b = _bundle_with_render(tmp_path, profile, rel, honest.encode("utf-8"))
    assert verify_bundle(b) == []
