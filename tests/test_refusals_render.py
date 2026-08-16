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
