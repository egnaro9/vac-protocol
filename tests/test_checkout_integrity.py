"""Every sha256-pinned file must survive the checkout that delivered it.

git's autocrlf rewrites text files on checkout. It is ON by default in the
Git for Windows installer, so a default Windows clone of this repository
receives CRLF artifacts, and the committed valid bundle then fails with a
sha256-mismatch on every text artifact at once: twenty reasons, none of which
names the actual cause. CI is ubuntu-only, so nothing upstream sees it.

`.gitattributes` (`* -text`) stops the conversion for future clones. This
test is the named reason for the clones that already happened, and the guard
against the attribute being dropped later.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PINNED = sorted((ROOT / "fixtures").rglob("*"))


def test_a_gitattributes_disables_text_conversion():
    """Without this, the fix is one `git config` away from being undone on
    somebody else's machine, and the failure it produces names hashes rather
    than causes."""
    ga = ROOT / ".gitattributes"
    assert ga.is_file(), "no .gitattributes: a Windows clone will rewrite " \
                         "every sha256-pinned artifact on checkout"
    rules = [ln.strip() for ln in
             ga.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    assert "* -text" in rules, rules


def test_no_pinned_artifact_carries_crlf():
    """The named reason a broken checkout otherwise never gets."""
    bad = [str(p.relative_to(ROOT)) for p in PINNED
           if p.is_file() and b"\r\n" in p.read_bytes()]
    assert bad == [], (
        "CRLF in sha256-pinned files: this checkout converted line endings, "
        "so every hash below will mismatch for a reason the verifier cannot "
        "name. Re-checkout with conversion off:\n"
        "    git config core.autocrlf false\n"
        "    git rm --cached -r . && git reset --hard\n"
        f"affected: {bad[:5]}")


@pytest.mark.parametrize("rel", ["fixtures/valid/vac.json"])
def test_the_pinned_bundle_is_readable_as_shipped(rel):
    """A control: the file the other two tests are about exists and parses,
    so a green run means the checks ran rather than found nothing."""
    p = ROOT / rel
    assert p.is_file() and p.read_bytes()
