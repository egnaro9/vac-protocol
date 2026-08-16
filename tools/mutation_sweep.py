#!/usr/bin/env python3
"""Mutation-test the verifier's own refusals.

The verifier is a grader, and an ungraded grader is a claim. This disables one
refusal at a time -- each `failures.append("<reason>: ...")` becomes `pass` --
and asks whether anything notices: the unit suite, the liveness control, or the
committed tamper fixtures. A mutant nothing notices is a refusal nothing tests.

THE LIVENESS GATE IS THE POINT. Run against a baseline that is already red and
`pytest -x` exits nonzero for every mutant, every one scores "caught", and the
score reads 1.000 while nothing was measured. That is not hypothetical -- it is
exactly what this script did on its first hardened run, and it is the same
vacuous-pass class the verifier exists to refuse. So: prove the instrument can
report BOTH outcomes before believing either.

  python tools/mutation_sweep.py [--floor 0.328] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "vac" / "verify.py"
REFUSAL = re.compile(r"^\s*(f|failures)\.append\(")

# Deselect tests that are red for a KNOWN, accepted reason, so the gate below
# measures the instrument rather than an open work item. Anything listed here
# must be justified; an empty list is the healthy state.
DESELECT: list[str] = []

# Refusals deliberately excluded from the denominator, each with the reason it
# cannot be reached by any bundle-shaped input. This list is a liability, not a
# convenience: an entry here is a permanent survivor that would otherwise make
# the score lie. Deleting a real guard to flatter a metric is worse than
# excluding it and saying why.
# Keyed by a distinctive SOURCE fragment of the refusal line, so a rename that
# changes the line is a miss (loud) rather than a silent over-match.
EXCLUDE: dict[str, str] = {
    '{md_rel}: {e}':
        "OSError wrapper on reading RESULTS.md. To reach the check at all the "
        "artifact must already be in `trusted`, which required is_file() plus a "
        "full _sha256() read of the same bytes. Only a filesystem race between "
        "the hash pass and this read could fire it -- a real guard, and "
        "unreachable from any input a test can construct.",
}


def _run(args: list[str], timeout: int = 300) -> int:
    return subprocess.run(args, capture_output=True, text=True,
                          cwd=REPO, timeout=timeout).returncode


def observe() -> tuple[bool, str]:
    """(noticed, how) for the tree as it currently stands."""
    deselect = [x for t in DESELECT for x in ("--deselect", t)]
    if _run([sys.executable, "-m", "pytest", "tests/", "-q", "-x",
             "--no-header", "-p", "no:cacheprovider"] + deselect):
        return True, "tests"
    if _run([sys.executable, "-m", "vac.verify", "fixtures/valid"]):
        return True, "control-broke"
    for d in sorted((REPO / "fixtures").glob("tamper-*")):
        if _run([sys.executable, "-m", "vac.verify", str(d)]) != 1:
            return True, f"sweep:{d.name}"
    return False, "SURVIVED"


def span(lines: list[str], i: int) -> tuple[int, int]:
    """The full (possibly multi-line) statement starting at line i."""
    depth = lines[i].count("(") - lines[i].count(")")
    j = i
    while depth > 0 and j + 1 < len(lines):
        j += 1
        depth += lines[j].count("(") - lines[j].count(")")
    return i, j


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=float, default=None,
                    help="fail if the score drops below this")
    ap.add_argument("--json", type=pathlib.Path)
    a = ap.parse_args()

    orig = SRC.read_text(encoding="utf-8")
    lines = orig.splitlines(keepends=True)
    sites = [i for i, ln in enumerate(lines) if REFUSAL.match(ln)]
    excluded = [i for i in sites if any(k in lines[i] for k in EXCLUDE)]
    sites = [i for i in sites if i not in excluded]
    if len(excluded) != len(EXCLUDE):
        print(f"ABORT: EXCLUDE has {len(EXCLUDE)} entries but matched "
              f"{len(excluded)} source lines. An exclusion that matches "
              "nothing silently inflates the denominator; one that matches "
              "twice silently shrinks it.", file=sys.stderr)
        return 2

    noticed, how = observe()
    if noticed:
        print(f"ABORT: baseline is not clean ({how}). A mutation score against "
              "a red baseline measures nothing.", file=sys.stderr)
        return 2
    print(f"baseline clean; {len(sites)} refusal sites"
          + (f" ({len(excluded)} excluded, see EXCLUDE)" if excluded else ""))

    results = []
    try:
        for n, i in enumerate(sites, 1):
            a0, b0 = span(lines, i)
            indent = re.match(r"^(\s*)", lines[a0]).group(1)
            SRC.write_text("".join(lines[:a0]
                                   + [f"{indent}pass  # MUTANT\n"]
                                   + lines[b0 + 1:]), encoding="utf-8")
            try:
                caught, why = observe()
            except subprocess.TimeoutExpired:
                caught, why = True, "timeout"
            m = re.search(r'"([a-z-]+):', lines[a0])
            results.append({"line": a0 + 1, "caught": caught, "how": why,
                            "reason": m.group(1) if m
                            else lines[a0].strip()[:60]})
            print(f"  [{n}/{len(sites)}] L{a0 + 1} "
                  f"{'caught: ' + why if caught else '*** SURVIVED ***'}",
                  flush=True)
    finally:
        SRC.write_text(orig, encoding="utf-8")

    k = sum(1 for r in results if r["caught"])
    score = k / len(results) if results else 0.0
    print(f"\nMUTATION SCORE: {k}/{len(results)} = {score:.3f}")
    surv = [r for r in results if not r["caught"]]
    if surv:
        print(f"SURVIVORS ({len(surv)}) — refusals nothing tests:")
        for r in surv:
            print(f"  vac/verify.py:{r['line']}  {r['reason']}")
    if a.json:
        a.json.write_text(json.dumps(
            {"score": round(score, 4), "caught": k, "total": len(results),
             "results": results}, indent=1))
    if a.floor is not None and score < a.floor:
        print(f"\nFAIL: {score:.3f} is below the floor {a.floor:.3f}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
