#!/usr/bin/env python3
"""Mutation-test the verifier's own refusals.

The verifier is a grader, and an ungraded grader is a claim. This disables one
refusal at a time (each `failures.append("<reason>: ...")` becomes `pass`)
and asks whether anything notices: the unit suite, the liveness control, or the
committed tamper fixtures. A mutant nothing notices is a refusal nothing tests.

THE LIVENESS GATE IS THE POINT. Run against a baseline that is already red and
`pytest -x` exits nonzero for every mutant, every one scores "caught", and the
score reads 1.000 while nothing was measured. That is not hypothetical: it is
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
import ast
import contextlib
import hashlib
import json
import os
import pathlib
import re
import signal
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "vac" / "verify.py"
TESTS = REPO / "tests"
FIXTURES = REPO / "fixtures"
TOOL = pathlib.Path(__file__).resolve()
REFUSAL = re.compile(r"^\s*(f|failures)\.append\(")

# Deselect tests that are red for a KNOWN, accepted reason, so the gate below
# measures the instrument rather than an open work item. Anything listed here
# must be justified; an empty list is the healthy state.
# These tests spawn a sweep and assert on its lock. Run inside this sweep's own
# detector they would see the lock this run holds and fail, and a red baseline
# makes the score meaningless. They guard the sweep, so the sweep cannot be
# their runner. CI runs them in the `test` job, which is where they belong.
# The obligation-ledger tests read vac/verify.py's emission sites through
# tools/ledger_sources.py. A mutant removes a site, the ledger stops seeing its
# code, and those tests fail whether or not any bundle gets past the verifier,
# so they would score a refusal as caught with no behavioural test behind it.
# They check the ledger, not the refusals; the `test` job runs them too. A
# sweep without them measured the same 168/168, so this costs no catch today.
DESELECT: list[str] = [
    "tests/test_mutation_sweep_restores.py",
    "tests/test_obligation_ledger.py",
]

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
# An entry here has been wrong once. Both render read wrappers sat in this
# table as unreachable OSError wrappers while their handler was
# `except (OSError, UnicodeDecodeError)`. The hash pass the rationale leans on
# reads BYTES, so it says nothing about a decode: a listed, correctly hashed
# artifact that is not valid UTF-8 reaches the line and it fires. Two
# reachable, untested refusals were scored as though they did not exist, and
# the sweep reported 1.000 over what was left. A rationale here must cover
# every exception its handler names, and
# tests/test_mutation_sweep_exclusions.py holds it to that.
# The expected size of the refusal-site population, pinned for the same reason
# EXCLUDE pins its arity. `--floor` constrains a RATIO, so a behaviour-preserving
# refactor that merges refusal sites into a helper leaves the suite green, does
# not trip the EXCLUDE arity check, and shrinks the denominator underneath the
# floor. Moving four stamp-mismatch appends into one helper takes the raw count
# from 146 to 143 and the scored population from 143 to 140, and nothing in the
# run would say so. Update this deliberately, in the commit that changes the
# population, or pass --expect-sites to override it for a one-off measurement.
# Both numbers are enforced. The scored one used to be derived as raw minus the
# EXCLUDE hits and never read, so it could say anything and the run went ahead.
# --expect-sites overrides only the raw count, because a one-off run at another
# revision has no pinned scored count to compare against; the scored count is
# then derived, which is safe because the EXCLUDE arity check has already fixed
# how many lines are excluded.
# 170/166 became 172/168 with the JSON nesting limit: an over-deep evidence
# artifact and an over-deep JSON Lines line are each refused by a new append,
# and both are reachable from a bundle, so neither is excluded.
# 172/168 became 172/170 when both render read wrappers left EXCLUDE. They are
# reachable through a render that is listed, correctly hashed and not valid
# UTF-8, they had no test, and they were the only survivors of a sweep with
# that entry removed. tests/test_refusals_render.py covers them now.
EXPECT_RAW_SITES = 172      # lines matching REFUSAL in vac/verify.py
EXPECT_SCORED_SITES = 170   # the above minus EXCLUDE

EXCLUDE: dict[str, tuple[int, str]] = {
    "{md_rel}: {e}": (1,
        "OSError wrapper on reading RESULTS.md. To reach the check at all the "
        "artifact must already be in `trusted`, which required is_file() plus a "
        "full _sha256() read of the same bytes. Only a filesystem race between "
        "the hash pass and this read could fire it: a real guard, and "
        "unreachable from any input a test can construct."),
    "unreadable while checking ": (1,
        "Read wrapper on the SECOND read of RESULTS.md, the one that confirms "
        "the published table states the declared reliability floor. NOT "
        "unreachable, and this entry used to claim it was, in the same words "
        "as the render entry that has now left the table: the handler is "
        "`except (OSError, UnicodeDecodeError)`, and a 0.2 bundle whose "
        "RESULTS.md is correctly hashed and not valid UTF-8 reaches the "
        "decode. Measured 2026-09-17. Only the OSError half of the old "
        "argument survives: `results_md` is a declared ref, so the check runs "
        "once the artifact is in `trusted`, which required is_file() plus a "
        "full _sha256() read of those bytes. It keeps its exclusion only "
        "until that is decided deliberately, and it is covered end to end by "
        "tests/test_refusals_modeldrift_floor.py, so the exclusion "
        "understates the score by one rather than hiding a survivor. It is a "
        "separate line from the entry above only because sharing the wording "
        "would have made a single EXCLUDE key match two sites and silently "
        "shrink the denominator."),
}


# A configured issuer checkout that does not resolve is a silently smaller
# suite, and this tool reports a RATIO over that suite.
#
# tests/test_verify.py and tests/test_registry.py gate their real-issuer tests
# on `<bundle>/vac.json`.is_file() and skip when it is absent. Skipped is not
# failed: the baseline stays clean, the score stays whatever it was, and
# nothing in this tool's output says how many tests ran. So a workflow that
# checks the issuers out and then points VAC_*_CHECKOUT somewhere else loses
# those tests and reports the same number as a run that had them.
#
# That is not hypothetical. From 1674f4c (2026-08-16), the commit that first
# checked the issuers out in CI, .github/workflows/ci.yml set each variable to
# _issuers/<repo>/vac while every consumer appends the bundle sub-path itself,
# so all three resolved to _issuers/<repo>/vac/vac, which no issuer repository
# has. The consumers appended it at 1674f4c already, so the values never
# worked. By c441011 that was seven tests skipped inside the one job that
# checks the issuers out, and CI stayed green while
# test_real_modeldrift_bundle_summary_is_enforced named a summary scope
# model-drift's v0.2 re-emission had removed.
#
# An UNSET variable falls back to the sibling checkout vac/registry.py names
# (`default_checkout`), and a sibling that is not there is an honest "not on
# this machine", so it is left alone here. The measured record below says
# which checkout each run actually read. A SET variable that resolves to no
# bundle is a configuration that lies, and the run stops instead of scoring
# the smaller suite.
def checkout_failures(env=None) -> list[str]:
    """One line per issuer whose VAC_*_CHECKOUT is set but whose bundle the
    tests would not find.

    The predicate here is deliberately the same one the skipif decorators
    use, `<bundle>/vac.json`.is_file(), and the resolution is the same one
    vac/registry.py uses, so this gate cannot drift away from the skip it
    exists to catch.
    """
    env = os.environ if env is None else env
    bad = []
    for cfg in _issuers():
        raw = env.get(cfg["checkout_env"])
        if not raw:
            continue
        checkout = (REPO / raw).resolve()
        pattern = cfg["bundles"]
        if not _has_bundle(checkout, pattern):
            bad.append(f"{cfg['checkout_env']}={raw} resolves to {checkout}, "
                       f"which has no {pattern}/vac.json. The tests gated on "
                       f"this variable would SKIP rather than run.")
    return bad


def _issuers() -> list[dict]:
    """vac/registry.py's issuer table, the one every consumer resolves.

    Imported inside the call, not at module scope: this tool REWRITES
    vac/verify.py, and vac.registry imports it. Both callers run before any
    mutation is applied, and a local import keeps them unable to run after.
    """
    from vac.registry import ISSUERS
    return ISSUERS


def _has_bundle(checkout: pathlib.Path, pattern: str) -> bool:
    """The skipif predicate: does `checkout` hold a bundle the tests would
    run against? Shared by the gate and the measured record, so the two
    cannot disagree about which checkouts count as present."""
    found = (sorted(checkout.glob(pattern)) if "*" in pattern
             else [checkout / pattern])
    return any((d / "vac.json").is_file() for d in found)


# The value recorded for an issuer whose checkout holds a bundle but whose
# commit cannot be named: no .git of its own, or a git that answers for some
# other repository. Recording that repository's HEAD instead would be a
# plausible commit id for bytes it does not describe.
NOT_A_CHECKOUT = "not a git checkout"


def _checkout_commit(checkout: pathlib.Path) -> dict:
    """{"commit", "dirty"} for a checkout that is the root of its own git
    repository, else {"commit": NOT_A_CHECKOUT}.

    Three guards, because git will answer for a repository other than the
    one asked about. A directory with no .git entry is not a checkout root,
    so git is not asked at all. One whose .git is an empty directory still
    gets an answer, about the repository above it, so the answer is only
    kept when git's own top level is this directory. And GIT_* variables are
    dropped: GIT_DIR, which a git hook exports, redirects every query to the
    repository that ran the hook, and makes the directory git was started in
    look like that repository's top level, which the second guard accepts.

    `dirty` is True when git reports any change, untracked files included,
    and also when it cannot report: in both cases the commit alone does not
    name the bytes the tests read. The status call passes
    --no-optional-locks because a plain `git status` may rewrite the
    checkout's index, and recording a checkout must not write to it.
    """
    if not (checkout / ".git").exists():
        return {"commit": NOT_A_CHECKOUT}
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    rp = subprocess.run(["git", "-C", str(checkout), "rev-parse",
                         "--show-toplevel", "HEAD"],
                        capture_output=True, text=True, env=env)
    out = rp.stdout.splitlines()
    if (rp.returncode or len(out) != 2
            or pathlib.Path(out[0]).resolve() != checkout.resolve()):
        return {"commit": NOT_A_CHECKOUT}
    st = subprocess.run(["git", "--no-optional-locks", "-C", str(checkout),
                         "status", "--porcelain"],
                        capture_output=True, text=True, env=env)
    return {"commit": out[1], "dirty": bool(st.returncode or st.stdout)}


def issuer_checkouts(env=None) -> dict[str, dict]:
    """VAC_*_CHECKOUT name -> the issuer checkout the tests read on this run.

    Which checkouts the tests find decides which tests run: at c441011 the
    doubled CI path skipped seven of them with every other byte the same. So
    a record of the source and the tests does not name the measurement until
    it also names these.

    Every configured variable is recorded, set or not, because unset does not
    mean absent: each consumer falls back to `default_checkout`, a sibling
    directory, and runs against it when it is there.

    "value" is the variable as set, or "unset". "checkout" is what the
    consumers resolve against the repository root: the variable, or the
    default when it is unset. It is the configured string, not the resolved
    path, so the record carries no machine's home directory unless the
    variable itself does. "commit" is git's HEAD in that checkout, "absent"
    when it holds no bundle and the gated tests skip, or NOT_A_CHECKOUT when
    it holds one that no commit can be named for.
    """
    env = os.environ if env is None else env
    out: dict[str, dict] = {}
    for cfg in _issuers():
        raw = env.get(cfg["checkout_env"])
        where = raw or cfg["default_checkout"]
        checkout = (REPO / where).resolve()
        rec = {"value": raw or "unset", "checkout": where}
        if _has_bundle(checkout, cfg["bundles"]):
            rec.update(_checkout_commit(checkout))
        else:
            rec["commit"] = "absent"
        out[cfg["checkout_env"]] = rec
    return out


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


# --------------------------------------------------------------------------
# SITE IDENTITY. A line number is not an identity. Insert one line above a
# refusal and every site below it is renamed, so two archived sweeps can only
# be compared per-site where their line keys happen to coincide, and anywhere
# they differ a reading of "this site went from caught to surviving" is
# undecidable rather than false. That is not hypothetical: the 17 to 14 figure
# behind the 239e1ba correction, read over 39 shared line keys, is a line-shift
# artifact of exactly this kind.
#
# The key below names what a site IS, not where it sits: the innermost
# enclosing def or class, the refusal statement with its whitespace
# normalised, and an ordinal among identical statements in that same scope. It
# does not move when lines are inserted above it, when sites are reordered,
# when another site is renamed, or when a site is dropped from the denominator.
# Editing this refusal's own message DOES change it, which is the point: a
# different message is a different refusal, and silently carrying the old
# identity across that edit is the error this key exists to refuse.
#
# Statement text alone is not enough, and neither is the scope alone. In the
# verify.py measured by the v5 archive, 8 of the 134 refusal statements share
# their full text with another, and the duplicated summary-mismatch statement
# has four copies in one file. Scope plus text plus ordinal separates them;
# scope plus text would collide, and text plus ordinal misattributes one of the
# duplicated statements.


def _qualname_map(source: str) -> dict[int, str]:
    """1-based line number -> innermost enclosing def/class qualname.

    Lines outside any def or class are absent, and the caller names them.

    A SyntaxError is raised, not swallowed. Returning an empty map for a
    source that does not parse would key every site to <module>: still a
    plausible-looking key, still unique per statement, and silently missing
    the scope that separates the duplicated statements. A sweep that cannot
    identify its sites must say so rather than archive a weaker key under the
    same name.
    """
    out: dict[int, str] = {}
    tree = ast.parse(source)

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                name = f"{prefix}.{child.name}" if prefix else child.name
                # The outer span is written first and the recursion overwrites
                # the part of it a nested scope covers, so the innermost wins.
                for ln in range(child.lineno, (child.end_lineno
                                               or child.lineno) + 1):
                    out[ln] = name
                walk(child, name)
            else:
                walk(child, prefix)

    walk(tree, "")
    return out


def site_identities(lines: list[str]) -> dict[int, dict]:
    """0-based line index -> the identity of the refusal starting there, for
    EVERY line matching REFUSAL.

    Ordinals are counted over the whole file, before any exclusion and before
    any --detector choice, so that dropping a site from the denominator cannot
    renumber a site that stays in it. Keying the ordinal to a position in the
    SCORED list would put the EXCLUDE table back inside the identity, which is
    the same defect wearing different clothes.
    """
    qual = _qualname_map("".join(lines))
    out: dict[int, dict] = {}
    seen: dict[tuple[str, str], int] = {}
    for i, ln in enumerate(lines):
        if not REFUSAL.match(ln):
            continue
        a0, b0 = span(lines, i)
        statement = " ".join("".join(lines[a0:b0 + 1]).split())
        scope = qual.get(a0 + 1, "<module>")
        ordinal = seen.get((scope, statement), 0)
        seen[(scope, statement)] = ordinal + 1
        out[i] = {"key": f"{scope}::{statement}#{ordinal}", "scope": scope,
                  "statement": statement, "ordinal": ordinal}
    return out


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rel(path: pathlib.Path) -> str:
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return path.name


def tree_digest(root: pathlib.Path,
                pattern: str = "**/*.py") -> tuple[str, int]:
    """(digest, file count) over a directory of source.

    The digest covers each file's path relative to `root` AND the sha256 of
    its bytes, in sorted path order, so a rename is a change and the value
    does not depend on the order the filesystem happens to hand back.
    """
    h = hashlib.sha256()
    n = 0
    for p in sorted(root.glob(pattern)):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(_sha256(p.read_bytes()).encode("ascii"))
        h.update(b"\n")
        n += 1
    return h.hexdigest(), n


def measured_revision(source_bytes: bytes, src: pathlib.Path,
                      tests: pathlib.Path, fixtures: pathlib.Path,
                      tool: pathlib.Path, issuers: dict) -> dict:
    """What this run actually measured, recorded as bytes and not as a commit.

    A commit id would not name it. In 7 of the 12 archived sweeps the
    verify.py the run measured was not committed until the archive itself was,
    so at the moment of measurement no commit described the tree, and a HEAD
    recorded then would name a different file. A hash of the bytes read names
    it whether or not they were ever committed.

    The tests are hashed too, and for a reason the source hash cannot cover:
    two archived runs measured the same verify.py and disagree on one site.
    Only a change on the detector side explains that, so an output that
    identified the source alone would still not say what was measured.

    The same argument reaches three more inputs, each of which can change a
    verdict with the source and the tests byte-identical:
      * fixtures/, every file. The liveness and fixtures detectors run the
        mutant against it, and a test that reads a fixture reads it too.
      * this tool's own bytes. The operator, EXCLUDE, DESELECT and the
        detector order all live here. Adding a path to DESELECT takes a test
        out of the detector without touching tests/, and an EXCLUDE edit
        moves the denominator.
      * the issuer checkouts, as issuer_checkouts() resolves them. They decide
        which tests run at all.

    It is still not every input. The tests also read registry.json,
    examples/, SPEC.md, obligations.json and the rest of vac/, and none of
    those is hashed here, so two identical records do not by themselves
    prove two identical measurements.
    """
    tests_sha, n = tree_digest(tests)
    fixtures_sha, n_fixtures = tree_digest(fixtures, "**/*")
    return {
        "source": {"path": _rel(src), "sha256": _sha256(source_bytes)},
        "tests": {"path": _rel(tests), "files": n, "sha256": tests_sha},
        "fixtures": {"path": _rel(fixtures), "files": n_fixtures,
                     "sha256": fixtures_sha},
        "tool": {_rel(tool): _sha256(tool.read_bytes())},
        "issuers": issuers,
    }


def measured_lines(measured: dict) -> list[str]:
    """The measured record as log lines. CI runs the sweep without --json, so
    for a CI run these lines are the only place the record exists."""
    s, t, fx = measured["source"], measured["tests"], measured["fixtures"]
    out = [f"measured {s['path']} sha256 {s['sha256']}; "
           f"{t['path']} ({t['files']} files) sha256 {t['sha256']}; "
           f"{fx['path']} ({fx['files']} files) sha256 {fx['sha256']}"]
    out += [f"measured {path} sha256 {sha}"
            for path, sha in measured["tool"].items()]
    for var, rec in measured["issuers"].items():
        state = ("" if "dirty" not in rec
                 else " (dirty)" if rec["dirty"] else " (clean)")
        out.append(f"issuer {var} {rec['value']}: reads {rec['checkout']}, "
                   f"commit {rec['commit']}{state}")
    return out


# --------------------------------------------------------------------------
# This tool EDITS tracked source to measure it, so it is a transaction, not an
# observer. A plain try/finally is not enough: SIGTERM (what a timeout sends,
# exit 143) terminates CPython without running finally, which on 2026-08-28
# left `pass  # MUTANT` in vac/verify.py where a refusal belongs. The lifecycle
# is: acquire isolation, snapshot, apply, measure, restore in finally, verify
# the restore BYTE-FOR-BYTE, release. See issue #11.
LOCK = REPO / ".mutation_sweep.lock"


@contextlib.contextmanager
def _sweep_transaction(src: pathlib.Path):
    """Hold the lock, snapshot `src`, and guarantee byte-identical restore on
    normal exit, exception, SIGINT and SIGTERM."""
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print(f"ABORT: {LOCK.name} exists. Another sweep is mutating this tree, "
              "or one died without releasing. A concurrent test run would read "
              "a mutated file and report a phantom failure. Remove the lock "
              "only after confirming no sweep is running.", file=sys.stderr)
        raise SystemExit(2)
    os.write(fd, f"pid={os.getpid()}\n".encode())
    os.close(fd)

    snapshot = src.read_bytes()
    restored = False

    def _restore() -> None:
        nonlocal restored
        if not restored:
            src.write_bytes(snapshot)
            restored = True
        # Restoring is not the same as having restored.
        assert src.read_bytes() == snapshot, (
            f"{src} was NOT restored byte-for-byte. Snapshot is "
            f"{len(snapshot)} bytes, file is {len(src.read_bytes())}.")
        LOCK.unlink(missing_ok=True)

    def _on_signal(signum, _frame):
        _restore()
        print(f"\ninterrupted by signal {signum}; {src} restored, lock released",
              file=sys.stderr, flush=True)
        raise SystemExit(128 + signum)

    prev = {sig: signal.signal(sig, _on_signal)
            for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        _restore()
        for sig, handler in prev.items():
            signal.signal(sig, handler)


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

    broken = checkout_failures()
    if broken:
        print("ABORT: a configured issuer checkout does not resolve:\n  "
              + "\n  ".join(broken)
              + "\nSkipped is not failed, so scoring from here would measure "
                "a smaller suite than the floor was set against and print the "
                "same number for it. Point each variable at the issuer's "
                "REPOSITORY root (the consumer appends the bundle sub-path "
                "itself), or unset it if the checkout is genuinely absent.",
              file=sys.stderr)
        return 2

    # One read, decoded rather than re-read, so the bytes recorded under
    # "measured" are the same bytes these lines were parsed from. Hashing a
    # second read would be a claim about a file, not about this measurement.
    raw = SRC.read_bytes()
    orig = raw.decode("utf-8")
    lines = orig.splitlines(keepends=True)
    identities = site_identities(lines)
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

    if a.expect_sites is None:
        want_raw, want_scored = EXPECT_RAW_SITES, EXPECT_SCORED_SITES
    else:
        want_raw = a.expect_sites
        want_scored = want_raw - len(excluded)
    if (raw_n, len(sites)) != (want_raw, want_scored):
        print(f"ABORT: refusal-site population is {raw_n} raw / {len(sites)} "
              f"scored; expected {want_raw} / {want_scored}. The floor "
              "constrains a ratio, so a population that moves without anyone "
              "deciding it should is a denominator change wearing a passing "
              "score. Update EXPECT_RAW_SITES and EXPECT_SCORED_SITES in the "
              "same commit that changes the population, or pass "
              "--expect-sites for a one-off run at another revision.",
              file=sys.stderr)
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
    measured = measured_revision(raw, SRC, TESTS, FIXTURES, TOOL,
                                 issuer_checkouts())
    print("\n".join(measured_lines(measured)))

    results = []
    with _sweep_transaction(SRC):
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
            ident = identities[i]
            results.append({"key": ident["key"], "scope": ident["scope"],
                            "statement": ident["statement"],
                            "ordinal": ident["ordinal"],
                            "line": a0 + 1, "caught": caught, "how": why,
                            "reason": m.group(1) if m
                            else lines[a0].strip()[:60]})
            print(f"  [{n}/{len(sites)}] L{a0 + 1} "
                  f"{'caught: ' + why if caught else '*** SURVIVED ***'}",
                  flush=True)

    k = sum(1 for r in results if r["caught"])
    score = k / len(results) if results else 0.0
    print(f"\nMUTATION SCORE: {k}/{len(results)} = {score:.3f}")
    surv = [r for r in results if not r["caught"]]
    if surv:
        print(f"SURVIVORS ({len(surv)}), refusals nothing tests:")
        for r in surv:
            print(f"  vac/verify.py:{r['line']}  {r['reason']}  "
                  f"in {r['scope']}")
    if a.json:
        payload = {"score": round(score, 4), "caught": k,
                   "total": len(results), "detector": a.detector,
                   "measured": measured, "results": results}
        a.json.write_text(json.dumps(payload, indent=1))
    if a.floor is not None and score < a.floor:
        print(f"\nFAIL: {score:.3f} is below the floor {a.floor:.3f}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
