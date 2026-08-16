"""Every declared ref must BIND something, not merely be referenced.

The closure rule (`evidence-unchecked`) proves a check *references* an
artifact. It does not prove the check reads anything in it. A profile could
declare a ref, open the file, ignore its contents, and satisfy closure while
binding nothing — "artifact-read coverage" without "field-binding coverage".
Today that gap is closed only by author discipline, which is exactly the kind
of unenforced convention this repo exists to distrust.

This is the mechanical version: for every ref of every check in the valid
fixture, corrupt the referenced artifact (re-pinning its sha256 HONESTLY, so
the hash check cannot be what catches it) and require the verifier to refuse.
A ref whose artifact can be corrupted without complaint is unbound at that
field, and this test fails unless the gap is recorded in KNOWN_UNBOUND with a
reason.

What it found on first run, and the honest reading: 4 of 12 refs went clean.
Three were the `schema` version field and one non-load-bearing digit in a raw
stream — unbound FIELDS inside otherwise-bound artifacts, not decorative refs.
That is a weaker result than the raw 4/12 suggests, and it is the one worth
reporting.

Credit where due: this gap was pointed out in an external review, not found
here.
"""
from __future__ import annotations

import json
import pathlib
import shutil

import pytest

from vac.verify import _CHECK_OPT_REFS, _CHECK_REFS, _sha256, verify_bundle

FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
MANIFEST = json.loads((FIX / "valid/vac.json").read_text(encoding="utf-8"))


def _refs() -> list[tuple[int, str, str, str]]:
    """(check index, profile, ref key, artifact path) for every declared ref."""
    out = []
    for i, c in enumerate(MANIFEST["results"]["checks"]):
        prof = c.get("profile")
        keys = list(_CHECK_REFS.get(prof, ()))
        keys += [k for k in _CHECK_OPT_REFS.get(prof, ()) if k in c]
        for k in keys:
            if isinstance(c.get(k), str):
                out.append((i, prof, k, c[k]))
    return out


REFS = _refs()

# Fields a corrupting probe can change without the verifier noticing. Found by
# this test after an external reviewer pointed out that evidence closure proves
# a check READS an artifact, never that it BINDS anything in it. Each entry is
# a real gap, recorded rather than hidden; the probe mutates the first numeric
# leaf, so the named field is what it happened to reach first.
KNOWN_UNBOUND = {
    "certlab-bundle-v1:artifact":
        "`schema` (format version) is not recomputed. An issuer could declare "
        "a schema version it did not emit. Low severity, real.",
    "fleet-board-v1:aggregate":
        "`schema` again, same shape as certlab's.",
    "fleet-board-v1:raw":
        "the first digit in the raw JSONL stream is not load-bearing for the "
        "recomputation; the paired-outcome fields it does bind are pinned by "
        "test_refusals_last_five.py.",
    "modeldrift-board-v1:narrative":
        "`models` (a count inside the narrative) is not recomputed, though "
        "claims_fired is. The narrative is partly bound, not decorative.",
}


def _corrupt(p: pathlib.Path) -> bool:
    """Change one meaningful value in place. True if something changed."""
    raw = p.read_bytes()
    try:
        d = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # line-delimited or plain text: bump the first digit we find
        s = raw.decode("utf-8", "replace")
        for ch in s:
            if ch.isdigit():
                p.write_text(s.replace(ch, str((int(ch) + 5) % 10), 1),
                             encoding="utf-8")
                return True
        return False

    changed = False

    def walk(node):
        nonlocal changed
        if changed:
            return node
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, bool):
            return node
        if isinstance(node, (int, float)):
            changed = True
            return node + 7
        return node

    d2 = walk(d)
    if changed:
        p.write_text(json.dumps(d2, indent=1) + "\n", encoding="utf-8")
    return changed


@pytest.mark.parametrize(
    "profile,ref,art",
    [(p, k, a) for _, p, k, a in REFS],
    ids=[f"{p}:{k}" for _, p, k, _ in REFS])
def test_corrupting_a_referenced_artifact_is_refused(tmp_path, profile, ref,
                                                     art):
    b = tmp_path / "b"
    shutil.copytree(FIX / "valid", b)
    target = b / art
    if not _corrupt(target):
        pytest.skip(f"no corruptible value in {art}")

    # honest re-pin: the hash must NOT be what catches this, or the test proves
    # only that sha256 works — which we already know
    man_p = b / "vac.json"
    man = json.loads(man_p.read_text(encoding="utf-8"))
    for e in man["evidence"]:
        if e["path"] == art:
            e["sha256"] = _sha256(target)
    man_p.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")

    out = verify_bundle(b)
    if not out:
        key = f"{profile}:{ref}"
        assert key in KNOWN_UNBOUND, (
            f"{key} -> {art}: the artifact was corrupted and honestly "
            "re-pinned, and the verifier returned CLEAN. Either bind the "
            f"field or add {key!r} to KNOWN_UNBOUND with a reason.")
        pytest.xfail(f"{key}: {KNOWN_UNBOUND[key]}")
    assert not any(x.startswith("sha256-mismatch") for x in out), out


def test_the_ref_inventory_is_not_empty():
    """Liveness for the parametrisation itself. If _refs() ever returns [],
    every test above vanishes silently and this file reports all-green while
    checking nothing."""
    assert len(REFS) >= 8, REFS
