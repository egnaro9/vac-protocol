#!/usr/bin/env python3
"""Score the tamper-fixture corpus ON ITS OWN, at commit f59fb62.

The paper reports the sixteen committed tamper fixtures catching 10 of 112
refusal-site mutants (score 0.089). This reproduces that number. It applies the
same deletion operator as tools/mutation_sweep.py, over the same refusal sites
of vac/verify.py as they stood at f59fb62, but scores with the unit suite out
of the picture, so that only the fixture corpus can report a catch.

WHY A SECOND SCRIPT, and not `mutation_sweep.py --detector fixtures`: that flag
exists and is the right way to ask this question of the tree as it stands, but
it cannot answer it at f59fb62. tools/mutation_sweep.py does not exist at that
commit, and HEAD's copy cannot simply be pointed at a checkout of it: its
EXCLUDE map is keyed to HEAD's source, and at f59fb62 its "{render_rel}: {e}"
fragment matches no line at all, so the declared-count guard aborts the run by
design (exit 2) rather than quietly resize the denominator. That guard is worth
more than the convenience. At f59fb62 the refusal population is 112 sites with
nothing excluded, which is the denominator the paper reports.

The exact command, which creates and removes its own detached worktree and
never touches the working tree:

  python tools/fixture_corpus_score.py

Or against a checkout you made yourself:

  git worktree add /tmp/vac-f59fb62 f59fb62
  python tools/fixture_corpus_score.py --repo /tmp/vac-f59fb62

`--detector liveness` scores the other half of the same question: whether
deleting a refusal breaks the clean-bundle control instead. Run both and the
two numbers say how the corpus's catches are actually earned.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from mutation_sweep import (REFUSAL, TOOL, _sha256,  # noqa: E402
                            site_identities, span,
                            tree_digest)     # same operator, same key

HERE = pathlib.Path(__file__).resolve().parent.parent
# The two files whose bytes decide what a run here does: this one, and the
# sweep it takes the operator and the site key from.
TOOLS = (pathlib.Path(__file__).resolve(), TOOL)
REV = "f59fb62"


def _run(repo: pathlib.Path, args: list[str], timeout: int = 300) -> int:
    return subprocess.run(args, capture_output=True, text=True,
                          cwd=repo, timeout=timeout).returncode


def observe(repo: pathlib.Path, detector: str) -> tuple[bool, str]:
    """(noticed, how) with ONLY the named detector allowed to report."""
    if detector == "liveness":
        if _run(repo, [sys.executable, "-m", "vac.verify", "fixtures/valid"]):
            return True, "control-broke"
        return False, "SURVIVED"
    for d in sorted((repo / "fixtures").glob("tamper-*")):
        if _run(repo, [sys.executable, "-m", "vac.verify", str(d)]) != 1:
            return True, f"sweep:{d.name}"
    return False, "SURVIVED"


def sweep(repo: pathlib.Path, detector: str) -> tuple[list[dict], int, dict]:
    """(rows, site count, what was measured).

    Rows carry the same position-independent site key as tools/mutation_sweep
    builds, so a row here and a row there name the same site when they are the
    same site, and a line shift between the two revisions does not say they
    are different ones.

    "measured" hashes fixtures/ as well as the source, because here the
    fixture corpus IS the detector: the same verify.py scored against a
    different corpus is a different number. It also hashes the tool bytes that
    applied the operator. It records no issuer checkouts, unlike
    tools/mutation_sweep.py: neither detector here runs a test, and
    vac/verify.py reads no VAC_*_CHECKOUT variable and imports nothing that
    does, so no checkout can change a verdict.
    """
    src = repo / "vac" / "verify.py"
    raw = src.read_bytes()
    orig = raw.decode("utf-8")
    lines = orig.splitlines(keepends=True)
    identities = site_identities(lines)
    sites = [i for i, ln in enumerate(lines) if REFUSAL.match(ln)]
    fixtures = sorted((repo / "fixtures").glob("tamper-*"))
    tests_sha, n_tests = tree_digest(repo / "tests")
    fixtures_sha, n_fixtures = tree_digest(repo / "fixtures", "**/*")
    measured = {"source": {"path": "vac/verify.py", "sha256": _sha256(raw)},
                "tests": {"path": "tests", "files": n_tests,
                          "sha256": tests_sha},
                "fixtures": {"path": "fixtures", "files": n_fixtures,
                             "sha256": fixtures_sha},
                "tool": {p.relative_to(HERE).as_posix():
                         _sha256(p.read_bytes()) for p in TOOLS}}
    print(f"{len(sites)} refusal sites, {len(fixtures)} tamper fixtures, "
          f"detector: {detector} alone")
    print(f"measured vac/verify.py sha256 {measured['source']['sha256']}; "
          f"tests ({n_tests} files) sha256 {tests_sha}; "
          f"fixtures ({n_fixtures} files) sha256 {fixtures_sha}")
    for path, sha in measured["tool"].items():
        print(f"measured {path} sha256 {sha}")

    noticed, how = observe(repo, detector)
    if noticed:
        print(f"ABORT: baseline is not clean ({how}). A mutation score "
              "against a red baseline measures nothing.", file=sys.stderr)
        raise SystemExit(2)
    print("baseline clean")

    results = []
    try:
        for n, i in enumerate(sites, 1):
            a0, b0 = span(lines, i)
            indent = lines[a0][:len(lines[a0]) - len(lines[a0].lstrip())]
            src.write_text("".join(lines[:a0]
                                   + [f"{indent}pass  # MUTANT\n"]
                                   + lines[b0 + 1:]), encoding="utf-8")
            try:
                caught, why = observe(repo, detector)
            except subprocess.TimeoutExpired:
                caught, why = True, "timeout"
            ident = identities[i]
            results.append({"key": ident["key"], "scope": ident["scope"],
                            "statement": ident["statement"],
                            "ordinal": ident["ordinal"],
                            "line": a0 + 1, "caught": caught, "how": why,
                            "reason": lines[a0].strip()[:70]})
            print(f"  [{n}/{len(sites)}] L{a0 + 1} "
                  f"{'caught: ' + why if caught else 'survived'}", flush=True)
    finally:
        src.write_text(orig, encoding="utf-8")
    return results, len(sites), measured


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=pathlib.Path,
                    help="an existing checkout of the target revision; "
                         "without it a detached worktree is made and removed")
    ap.add_argument("--rev", default=REV, help=f"target revision ({REV})")
    ap.add_argument("--detector", default="fixtures",
                    choices=("fixtures", "liveness"))
    ap.add_argument("--json", type=pathlib.Path)
    a = ap.parse_args()

    rp = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--verify",
                         "--quiet", f"{a.rev}^{{commit}}"],
                        capture_output=True, text=True)
    want = rp.stdout.strip()
    if rp.returncode or not want:
        print(f"ABORT: {a.rev} is not a commit in {HERE}", file=sys.stderr)
        return 2

    tmp = None
    try:
        if a.repo:
            repo = a.repo.resolve()
            at = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
            if at != want:
                print(f"ABORT: {repo} is at {at[:7] or '?'}, not {a.rev}. The "
                      "figure is revision-specific; measuring another commit "
                      "and calling it this one is the error this repository "
                      "exists to refuse.", file=sys.stderr)
                return 2
            dirty = subprocess.run(["git", "-C", str(repo), "status",
                                    "--porcelain"], capture_output=True,
                                   text=True).stdout.strip()
            if dirty:
                print(f"ABORT: {repo} has uncommitted changes; the mutants "
                      "would be applied on top of them.", file=sys.stderr)
                return 2
        else:
            tmp = pathlib.Path(tempfile.mkdtemp(prefix="vac-corpus-"))
            repo = tmp / "wt"
            subprocess.run(["git", "-C", str(HERE), "worktree", "add",
                            "--detach", str(repo), want], check=True,
                           capture_output=True, text=True)
        print(f"revision: {want[:7]} at {repo}")
        results, total, measured = sweep(repo, a.detector)
    finally:
        if tmp:
            subprocess.run(["git", "-C", str(HERE), "worktree", "remove",
                            "--force", str(tmp / "wt")], capture_output=True)
            subprocess.run(["rm", "-rf", str(tmp)], capture_output=True)

    k = sum(1 for r in results if r["caught"])
    score = k / total if total else 0.0
    print(f"\n{a.detector.upper()}-ONLY SCORE: {k}/{total} = {score:.3f}")
    if k:
        print("caught:")
        for r in results:
            if r["caught"]:
                print(f"  vac/verify.py:{r['line']:<5} {r['how']}")
    if a.json:
        a.json.write_text(json.dumps(
            {"rev": want, "detector": a.detector, "score": round(score, 4),
             "caught": k, "total": total, "measured": measured,
             "results": results}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
