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

import pytest

from vac.verify import _check_evalmut_render

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
