"""The worked example in ISSUING.md must actually verify.

A walkthrough whose example has quietly stopped working is worse than no
walkthrough: the first thing a stranger does is run it, and a refusal there
reads as "this project does not work" rather than "this doc is stale".
"""
from __future__ import annotations

import json
import pathlib

from vac.verify import PROFILES, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/outsider"


def test_the_documented_example_verifies():
    assert verify_bundle(EXAMPLE) == []


def test_the_example_is_issued_by_someone_other_than_us():
    """The example's whole job is to show a stranger's bundle. If it drifts to
    one of our own issuers it stops demonstrating the thing it exists for."""
    man = json.loads((EXAMPLE / "vac.json").read_text(encoding="utf-8"))
    assert "egnaro9" not in man["protocol"]["issuer"]


def test_the_example_uses_the_generic_profile():
    profiles = [c["profile"] for c in
                json.loads((EXAMPLE / "vac.json").read_text(
                    encoding="utf-8"))["results"]["checks"]]
    assert profiles == ["rows-aggregate-v1"], profiles


def test_the_example_reports_a_real_failure():
    """A suite with nothing failing is the less convincing demo, and ISSUING.md
    says so. Keep the example honest about that."""
    rows = json.loads((EXAMPLE / "results.json").read_text(
        encoding="utf-8"))["cases"]
    assert any(r["passed"] is False for r in rows)


def test_issuing_md_names_only_real_ops():
    """The doc lists the op set inline. If SPEC gains or loses one, this fails
    rather than letting the walkthrough teach an op that does not exist."""
    from vac.verify import _ROW_OPS
    doc = (ROOT / "ISSUING.md").read_text(encoding="utf-8")
    for op in _ROW_OPS:
        assert f"`{op}`" in doc or f"{op}," in doc or f"`op` is one of" in doc, op
    assert "rows-aggregate-v1" in PROFILES
