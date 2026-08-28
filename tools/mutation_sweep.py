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

  python tools/mutation_sweep.py [--floor 0.99] [--json out.json]

`--detector` chooses which of the three may report. The default `all` is the
scored path and the one the CI floor is set against: it is first-detector-wins
in the order tests, liveness, fixtures, so a mutant the unit suite catches
never reaches the fixture corpus. That makes `all` a measurement of what the
corpus adds ON TOP of the suite, which for a suite that pins every fixture's
exact verdict is zero by construction. To ask what a detector catches BY
ITSELF, name it; a mutant then counts as caught only if that one fires:

  python tools/mutation_sweep.py --detector fixtures

For the same standalone-corpus measurement at commit f59fb62, where this file
does not yet exist, see tools/fixture_corpus_score.py.
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
# Each value is (how many source lines this fragment is EXPECTED to match,
# why the refusal cannot be reached). The count is explicit so that a fragment
# silently matching more or fewer lines than intended aborts the run instead of
# quietly resizing the denominator in either direction.
# The expected size of the refusal-site population, pinned for the same reason
# EXCLUDE pins its arity. `--floor` constrains a RATIO, so a behaviour-preserving
# refactor that merges refusal sites into a helper leaves the suite green, does
# not trip the EXCLUDE arity check, and shrinks the denominator underneath the
# floor. Moving four stamp-mismatch appends into one helper takes the raw count
# from 146 to 143 and the scored population from 143 to 140, and nothing in the
# run would say so. Update this deliberately, in the commit that changes the
# population, or pass --expect-sites to override it for a one-off measurement.
EXPECT_RAW_SITES = 155      # lines matching REFUSAL in vac/verify.py at 93fa8d1
EXPECT_SCORED_SITES = 152   # the above minus EXCLUDE

EXCLUDE: dict[str, tuple[int, str]] = {
    "{md_rel}: {e}": (1,
        "OSError wrapper on reading RESULTS.md. To reach the check at all the "
        "artifact must already be in `trusted`, which required is_file() plus a "
        "full _sha256() read of the same bytes. Only a filesystem race between "
        "the hash pass and this read could fire it -- a real guard, and "
        "unreachable from any input a test can construct."),
    "{render_rel}: {e}": (2,
        "OSError wrappers in BOTH render comparators. `render` is a declared "
        "ref: a render not listed in evidence is refused earlier as "
        "check-artifact-not-listed, and one that IS listed was already opened "
        "and sha256'd by _verify_artifacts before the check runs. Probed both "
        "ways -- listing a directory yields missing-artifact."),
}


def _run(args: list[str], timeout: int = 300) -> int:
    return subprocess.run(args, capture_output=True, text=True,
                          cwd=REPO, timeout=timeout).returncode


def observe(detector: str = "all") -> tuple[bool, str]:
    """(noticed, how) for the tree as it currently stands.

    `detector` restricts which disjuncts may report. "all" preserves the
    historical first-detector-wins order below and is the scored path. Naming
    a single detector runs only that one, so a mutant counts as caught only
    if that detector fires: the marginal-vs-standalone distinction the score
    otherwise hides.
    """
    if detector in ("all", "tests"):
        deselect = [x for t in DESELECT for x in ("--deselect", t)]
        if _run([sys.executable, "-m", "pytest", "tests/", "-q", "-x",
                 "--no-header", "-p", "no:cacheprovider"] + deselect):
            return True, "tests"
    if detector in ("all", "liveness"):
        if _run([sys.executable, "-m", "vac.verify", "fixtures/valid"]):
            return True, "control-broke"
    if detector in ("all", "fixtures"):
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
    ap.add_argument("--expect-sites", type=int, metavar="RAW",
                    help="expected count of REFUSAL-matching lines; overrides "
                         "EXPECT_RAW_SITES for a measurement at another "
                         "revision. The scored population is this minus the "
                         "EXCLUDE hits.")
    ap.add_argument("--json", type=pathlib.Path)
    ap.add_argument("--detector", default="all",
                    choices=("all", "tests", "fixtures", "liveness"),
                    help="which detector may report a catch. 'all' (default) "
                         "is first-detector-wins and is the scored path; a "
                         "single name scores that detector on its own")
    a = ap.parse_args()

    orig = SRC.read_text(encoding="utf-8")
    lines = orig.splitlines(keepends=True)
    sites = [i for i, ln in enumerate(lines) if REFUSAL.match(ln)]
    excluded, bad = [], []
    for k, (want_n, _) in EXCLUDE.items():
        hits = [i for i in sites if k in lines[i]]
        if len(hits) != want_n:
            bad.append(f"{k!r} expected {want_n} line(s), matched {len(hits)}")
        excluded += hits
    if bad:
        print("ABORT: EXCLUDE does not match the source as declared:\n  "
              + "\n  ".join(bad)
              + "\nAn exclusion matching fewer lines than declared inflates "
                "the denominator; one matching more shrinks it. Either is a "
                "silently wrong score.", file=sys.stderr)
        return 2
    raw_n = len(sites)
    sites = [i for i in sites if i not in excluded]

    want_raw = a.expect_sites if a.expect_sites is not None else EXPECT_RAW_SITES
    want_scored = want_raw - len(excluded)
    if (raw_n, len(sites)) != (want_raw, want_scored):
        print(f"ABORT: refusal-site population is {raw_n} raw / {len(sites)} "
              f"scored; expected {want_raw} / {want_scored}. The floor "
              "constrains a ratio, so a population that moves without anyone "
              "deciding it should is a denominator change wearing a passing "
              "score. Update EXPECT_RAW_SITES in the same commit that changes "
              "the population, or pass --expect-sites for a one-off run at "
              "another revision.", file=sys.stderr)
        return 2

    if a.detector != "all":
        print(f"detector: {a.detector} alone. A mutant counts as caught only "
              "if this detector fires; the others are not run. This is not "
              "the scored path and the CI floor does not apply to it.")
    noticed, how = observe(a.detector)
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
                caught, why = observe(a.detector)
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
        payload = {"score": round(score, 4), "caught": k,
                   "total": len(results), "results": results}
        if a.detector != "all":
            payload["detector"] = a.detector
        a.json.write_text(json.dumps(payload, indent=1))
    if a.floor is not None and score < a.floor:
        print(f"\nFAIL: {score:.3f} is below the floor {a.floor:.3f}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
