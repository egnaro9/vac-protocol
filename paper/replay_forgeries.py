#!/usr/bin/env python3
"""Replay the four hand-found forgeries against vac/verify.py at f59fb62, line by line.

v1's RQ4 said the refusal-deletion operator "anticipated three of four" hand-found
forgeries. That is a claim about specific lines: whether the refusal that would have
named each forgery's lie was one the sweep marked as surviving. A verdict cannot settle
it, because an accepted bundle looks the same whether the refusal was skipped, was
reached and found nothing, or does not exist. A line trace can. This script runs each
forgery through the pre-fix verifier with a line tracer on that one file, and says which
of the named lines executed and which did not.

What it reads:

  * vac/verify.py as it stood at f59fb62. By default it is read from this repository's
    git objects by blob id with `git cat-file` (read-only). A copy made some other way,
    for example from `git archive f59fb62`, can be passed with --verify-py, so a clone
    without that history, or an export with no .git at all, can still run it. Either way
    the bytes must hash to PIN_SHA256 below or the run stops with exit 2: the table is
    revision-specific, and a trace of other bytes is a trace of another verifier.
  * The fixtures under fixtures/. Three rows are controls that no fixture
    carries: two wrong-value stamp bundles and one summary edit. Each is built in a
    temporary directory from a committed fixture by the one edit its row names, with
    an edited artifact re-pinned honestly, the same way
    tests/test_refusals_stamps_summary.py builds its stamp controls. Nothing under
    fixtures/ is written.

What it reports, per row: the refusals verify_bundle returned, the exit code main()
returns, whether each named line executed, and which refusal sites executed. A refusal
site is a line tools/mutation_sweep.py's REFUSAL pattern matches, so "site" means what
it means in the sweep's 112-site population at f59fb62. The expected values come from
V2-02 in paper/arxiv/v2/V2_CHANGE_LEDGER.md. Four rows are additions to that table:
fixtures/valid, and three controls (tamper-summary-fixed, the certlab stamps set to a
wrong value, and tamper-check-deleted with a headline no check recomputes) that show
the lines a forgery skips do fire when the input reaches them.

Then Table 1: for each forgery, the refusals that would have named its lie had its
defect been absent (V2-02's criterion, written out in NAMES_THE_LIE), and whether each
one was caught or survived in paper/mutation.json, the baseline sweep of this revision.
That archive keys rows by line number alone, so it is joined only after its line set
and every row's refusal code are checked against the pinned source. Table 1 is then
held to V2-02 line by line (EXPECT_BASELINE), not only by count, because two rows that
swap caught and survived keep every count.

The printed table is read back and compared with the measurements before the script
exits, so a table whose words say the opposite of what was traced fails the run.

Line events, not line counts: CPython reports a line more than once for one execution of
a statement that spans several lines, so only whether a line executed is reported.

  python paper/replay_forgeries.py
  python paper/replay_forgeries.py --verify-py /tmp/f59/vac/verify.py --json out.json

Exit 0 when every row, every printed status, every Table 1 count and every line of
the archive V2-02 names as caught or survived matches its expected value, 1 when any
differs, 2 when the pinned verifier cannot be read or the sweep does not fit it.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from mutation_sweep import REFUSAL  # noqa: E402  the sweep's own site pattern

REV = "f59fb6262eafc86db393294ceca530ed21396846"
# `git show f59fb62:vac/verify.py | shasum -a 256`, and its git blob id. The blob id is
# what `git ls-tree f59fb62 vac/verify.py` prints, so a reader can check the pin
# without this script.
PIN_SHA256 = "7c74677491b894fad3fb4e8e29795e255b65cf982edf0f25609f549bfb4c1259"
PIN_BLOB = "e99745dd8c065be032f8cd8782395ee9a8036122"
# The sweep's population at this revision, as the paper reports it (112 sites, nothing
# excluded). A different count means REFUSAL no longer means what the paper's
# denominator meant, and the "site" column below would silently change meaning.
EXPECT_SITES = 112

# The baseline sweep the paper reports for f59fb62 (37 of 112 caught), committed at
# 6b6f96f. That it fits the pinned source is checked, not assumed: see baseline().
SWEEP = REPO / "paper" / "mutation.json"

# The refusals that would have named each forgery's lie had its defect been absent,
# which is V2-02's test for "anticipated": a forgery counts only if one of these is a
# survivor. V2-02 names none for forgery 2: at f59fb62 no rule required a listed
# artifact to be read by some check, and deleting the check skips every certlab
# refusal, none of which says "unchecked". The forgery 2 control row shows that :1088
# would have refused the orphaned headline had no other check echoed its values;
# whether that counts as naming this lie is the ledger's call. :1088 was caught at
# baseline, so forgery 2 is not anticipated under either reading.
NAMES_THE_LIE = [
    (1, "summary value typed as a string", (1085, 1088)),
    (2, "the certlab check deleted", ()),
    (3, "severity re-cased", (618, 655, 1088)),
    (4, "stamps deleted, certlab and fleet halves", (285, 290, 376, 385)),
]
# (survived, of) for each forgery, the counts V2-02 proposes Table 1 print
EXPECT_TABLE1 = {1: (0, 2), 2: (0, 0), 3: (0, 3), 4: (2, 4)}
# Which lines paper/mutation.json has caught and which survived, as V2-02's Evidence
# names them, and its total ("Of the 75 survivors", so 37 of 112 caught). A count
# alone is not enough: two rows that swap caught and survived keep every count, and
# when both carry the same refusal code the join's checks pass too (:376 and :385
# are both stamp-mismatch). So Table 1 is checked line by line against this, and so
# is the archive, and either one differing fails the run.
EXPECT_BASELINE = {
    1085: "caught", 1088: "caught", 613: "caught", 618: "caught", 655: "caught",
    290: "caught", 385: "caught",
    285: "survived", 376: "survived", 276: "survived", 347: "survived",
    350: "survived", 534: "survived", 652: "survived", 1036: "survived",
}
EXPECT_CAUGHT = 37

# The lines this replay names, with what each one is at f59fb62. The text is checked
# against the pinned source before anything runs.
LINES = {
    255: ("guard", "_check_certlab's first statement: the checker was entered"),
    284: ("guard", "certlab taskset_hash/prompt_hash comparison, guarded on the key"),
    285: ("site", "stamp-mismatch: taskset_hash or prompt_hash"),
    288: ("guard", "certlab harness_commit comparison, guarded on the key"),
    290: ("site", "stamp-mismatch: harness_commit"),
    374: ("guard", "fleet_commit vs issuer_commit, guarded on the key"),
    376: ("site", "stamp-mismatch: fleet_commit"),
    383: ("guard", "fleet_commit vs protocol.hashes, guarded on the key"),
    385: ("site", "stamp-mismatch: hashes.fleet_commit"),
    617: ("guard", "crashkit metrics comparison, recomputed vs declared"),
    618: ("site", "raw-aggregate-mismatch: crashkit metrics"),
    655: ("site", "summary-mismatch: crashkit expect block"),
    1080: ("guard", "summary walk: return on a leaf that is not a number"),
    1085: ("site", "summary-outruns-checks: field recomputed, value differs"),
    1088: ("site", "summary-outruns-checks: no check recomputes it"),
}
LINE_TEXT = {
    255: 'art = check["artifact"]',
    284: "if k in hashes and k in data and hashes[k] != data[k]:",
    285: 'f.append(f"stamp-mismatch: {k}: protocol {hashes[k]}, "',
    288: 'if _nonempty_str(ic) and "harness_commit" in data \\',
    290: 'f.append(f"stamp-mismatch: harness_commit: protocol {ic}, "',
    374: 'if _nonempty_str(ic) and "fleet_commit" in agg \\',
    376: 'f.append(f"stamp-mismatch: fleet_commit: protocol {ic}, "',
    383: 'if ("fleet_commit" in hashes and "fleet_commit" in agg',
    385: 'f.append(f"stamp-mismatch: hashes.fleet_commit: protocol "',
    617: "if metrics.get(k) != recomputed[k]:",
    618: 'f.append(f"raw-aggregate-mismatch: {art}: metrics.{k} "',
    655: 'f.append(f"summary-mismatch: {k}: declared {expect[k]}, "',
    1080: "return",
    1085: 'f.append(f"summary-outruns-checks: {path}: declares {node}, "',
    1088: 'f.append(f"summary-outruns-checks: {path}: declares {node}, "',
}


def _set(path: str, **values):
    """A derived control: fixtures/valid with `values` written into the JSON artifact
    at `path`, and that artifact re-pinned honestly, so the only thing wrong with the
    bundle is the value under test."""
    def build(fixtures: pathlib.Path, dest: pathlib.Path) -> pathlib.Path:
        shutil.copytree(fixtures / "valid", dest)
        art = dest / path
        data = json.loads(art.read_text(encoding="utf-8"))
        data.update(values)
        art.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        man = json.loads((dest / "vac.json").read_text(encoding="utf-8"))
        for e in man["evidence"]:
            if e["path"] == path:
                e["sha256"] = hashlib.sha256(art.read_bytes()).hexdigest()
        (dest / "vac.json").write_text(json.dumps(man, indent=1) + "\n",
                                       encoding="utf-8")
        return dest
    build.edit = (f"fixtures/valid with {path} "
                  + ", ".join(f"{k}={v}" for k, v in values.items())
                  + ", re-pinned")
    return build


def _summary(fixture: str, **values):
    """A derived control: the committed `fixture` with `values` written into
    results.summary. vac.json is never its own evidence, so nothing is re-pinned."""
    def build(fixtures: pathlib.Path, dest: pathlib.Path) -> pathlib.Path:
        shutil.copytree(fixtures / fixture, dest)
        man = json.loads((dest / "vac.json").read_text(encoding="utf-8"))
        man["results"]["summary"].update(values)
        (dest / "vac.json").write_text(json.dumps(man, indent=1) + "\n",
                                       encoding="utf-8")
        return dest
    build.edit = (f"fixtures/{fixture} with results.summary "
                  + ", ".join(f"{k}={v}" for k, v in values.items()))
    return build


@dataclass
class Row:
    label: str
    forgery: str
    fixture: str | None = None          # a fixture directory under fixtures/
    derive: object = None               # or a derived control
    exit_code: int = 0
    refusals: list[str] = field(default_factory=list)
    ran: tuple[int, ...] = ()           # named lines that must execute
    not_ran: tuple[int, ...] = ()       # named lines that must not
    in_ledger: bool = True              # a row of V2-02's replay table


FLEET_WRONG = [
    "stamp-mismatch: fleet_commit: protocol f1e2d3c, artifact DEADBEEF",
    "stamp-mismatch: hashes.fleet_commit: protocol f1e2d3c, artifact DEADBEEF"]
CERTLAB_WRONG = [
    "stamp-mismatch: taskset_hash: protocol 00112233445566aa, artifact DEADBEEF",
    "stamp-mismatch: prompt_hash: protocol aabbccdd00112233, artifact DEADBEEF",
    "stamp-mismatch: harness_commit: protocol f1e2d3c, artifact DEADBEEF"]
SEVERITY_PARTIAL = [
    "raw-aggregate-mismatch: evidence/eval_run.json: metrics.vulnerability_score "
    "declared 0.4545, recomputed 0.0",
    "summary-mismatch: vulnerability_score: declared 0.4545, recomputed 0.0",
    "summary-outruns-checks: summary.crash_vulnerability: declares 0.4545, "
    "no check recomputes it"]

# Every refused row lists its refusals exactly, so "refused by exactly those three"
# is checked on the messages as well as on the executed sites.
ROWS = [
    Row("valid", "control: the honest bundle", fixture="valid",
        ran=(255, 284, 288, 374, 383, 617), not_ran=(1080,), in_ledger=False),
    Row("tamper-summary-string", "forgery 1: summary value typed as a string",
        fixture="tamper-summary-string", ran=(1080,), not_ran=(1085, 1088)),
    Row("tamper-summary-fixed", "control for forgery 1: the same field, a number",
        fixture="tamper-summary-fixed", exit_code=1,
        refusals=["summary-outruns-checks: summary.fixed: declares 3, "
                  "recomputation gives 2"],
        not_ran=(1080,), in_ledger=False),
    Row("tamper-check-deleted", "forgery 2: the certlab check deleted",
        fixture="tamper-check-deleted", not_ran=(255, 284, 288)),
    # Not a V2-02 row. With the check gone, nothing recomputes summary.fixed (2) or
    # summary.verdicts (3), yet :1088 stays quiet, because its fallback matches by bare
    # value and other checks recompute a 2 and a 3 under other names. The same bundle
    # with a headline no check recomputes is refused by :1088 at this revision.
    Row("tamper-check-deleted, summary.fixed 7777",
        "control for forgery 2: an orphaned headline no other check echoes",
        derive=_summary("tamper-check-deleted", fixed=7777), exit_code=1,
        refusals=["summary-outruns-checks: summary.fixed: declares 7777, no check "
                  "recomputes it"], not_ran=(255, 284, 288), in_ledger=False),
    Row("attack-crashkit-severity", "forgery 3: severity re-cased, carried through",
        fixture="attack-crashkit-severity", ran=(617,),
        not_ran=(618, 655, 1088)),
    Row("tamper-crashkit-severity", "forgery 3, partial: re-cased, score left honest",
        fixture="tamper-crashkit-severity", exit_code=1,
        refusals=SEVERITY_PARTIAL),
    Row("tamper-stamp-deleted", "forgery 4, certlab half: stamps deleted, re-pinned",
        fixture="tamper-stamp-deleted", ran=(284, 288), not_ran=(285, 290)),
    Row("certlab stamps DEADBEEF", "control for forgery 4, certlab: wrong values",
        derive=_set("evidence/bundle.json", harness_commit="DEADBEEF",
                    taskset_hash="DEADBEEF", prompt_hash="DEADBEEF"),
        exit_code=1, refusals=CERTLAB_WRONG, in_ledger=False),
    Row("attack-fleet-stamp-deleted", "forgery 4, fleet half: fleet_commit deleted, "
        "re-pinned", fixture="attack-fleet-stamp-deleted", ran=(374, 383),
        not_ran=(376, 385)),
    Row("fleet_commit DEADBEEF", "control for forgery 4, fleet: wrong value",
        derive=_set("evidence/results.json", fleet_commit="DEADBEEF"),
        exit_code=1, refusals=FLEET_WRONG),
]


def read_pinned(verify_py: pathlib.Path | None) -> bytes:
    """The f59fb62 verifier's bytes, or SystemExit(2) with the reason."""
    if verify_py is not None:
        data = verify_py.read_bytes()
        where = str(verify_py)
    else:
        env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
        r = subprocess.run(["git", "--no-optional-locks", "-C", str(REPO), "cat-file",
                            "blob", PIN_BLOB], capture_output=True, env=env)
        if r.returncode:
            raise SystemExit(
                f"ABORT: blob {PIN_BLOB[:12]} (vac/verify.py at f59fb62) is not in "
                f"{REPO}'s git objects: {r.stderr.decode(errors='replace').strip()}. "
                "A shallow clone lacks it: fetch the history, or pass --verify-py with "
                "a copy exported from f59fb62.")
        data = r.stdout
        where = f"git blob {PIN_BLOB[:12]}"
    got = hashlib.sha256(data).hexdigest()
    if got != PIN_SHA256:
        raise SystemExit(f"ABORT: {where} has sha256 {got}, not the f59fb62 pin "
                         f"{PIN_SHA256}. This table describes one revision.")
    return data


def load(data: bytes, where: pathlib.Path):
    """Write the pinned bytes to `where` and import them as a standalone module.

    At f59fb62 vac/verify.py imports only the standard library, so it loads without
    the rest of that tree, and loading it under its own name keeps it apart from the
    vac package this interpreter may already have imported."""
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_bytes(data)
    spec = importlib.util.spec_from_file_location("vac_verify_f59fb62", where)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # a module that is not registered cannot resolve
    spec.loader.exec_module(mod)  # its own string annotations
    return mod


def check_source(text: str) -> list[str]:
    """Named lines whose text is not what LINES describes. Empty when the pin holds;
    it exists so a hand edit to LINES cannot point a label at the wrong line."""
    src = text.splitlines()
    return [f":{n} is {src[n - 1].strip()!r}, expected {want!r}"
            for n, want in LINE_TEXT.items() if src[n - 1].strip() != want]


def trace(mod, bundle: pathlib.Path) -> tuple[list[str], set[int]]:
    """(verify_bundle's refusals, the lines of the pinned file that executed).

    Only frames whose code lives in the pinned file are traced, so a line number here
    is always a line of that file and never of a helper in another module."""
    filename = mod.verify_bundle.__code__.co_filename
    hit: set[int] = set()

    def local(frame, event, arg):
        if event == "line":
            hit.add(frame.f_lineno)
        return local

    def call(frame, event, arg):
        return local if frame.f_code.co_filename == filename else None

    previous = sys.gettrace()
    sys.settrace(call)
    try:
        refusals = mod.verify_bundle(bundle)
    finally:
        sys.settrace(previous)
    return refusals, hit


def exit_code(mod, bundle: pathlib.Path) -> tuple[int, list[str]]:
    """What `python -m vac.verify <bundle>` returns at f59fb62, and its FAIL lines."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = mod.main([str(bundle)])
    fails = [ln[len("FAIL "):] for ln in out.getvalue().splitlines()
             if ln.startswith("FAIL ")]
    return rc, fails


def bundle_digest(bundle: pathlib.Path) -> str:
    """sha256 over each file's relative path and bytes, in sorted order, so a result
    names the exact bytes it was measured on."""
    h = hashlib.sha256()
    for p in sorted(bundle.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(bundle).as_posix().encode() + b"\0")
            h.update(hashlib.sha256(p.read_bytes()).hexdigest().encode() + b"\n")
    return h.hexdigest()


def replay(mod, sites: list[int], fixtures: pathlib.Path, work: pathlib.Path,
           rows=ROWS) -> list[dict]:
    """One result per row, each carrying its own list of differences from the
    expected values. An empty `diffs` is a reproduced row."""
    out = []
    for i, row in enumerate(rows):
        if row.fixture is not None:
            bundle = fixtures / row.fixture
            source = f"fixtures/{row.fixture}"
        else:
            bundle = row.derive(fixtures, work / f"derived{i}")
            source = row.derive.edit
        refusals, hit = trace(mod, bundle)
        rc, fails = exit_code(mod, bundle)
        executed = sorted(s for s in sites if s in hit)
        named = {n: n in hit for n in sorted(set(row.ran) | set(row.not_ran)
                                             | set(executed))}
        diffs = []
        if rc != row.exit_code:
            diffs.append(f"exit {rc}, expected {row.exit_code}")
        if refusals != row.refusals:
            diffs.append(f"refusals {refusals}, expected {row.refusals}")
        if fails != refusals:
            diffs.append(f"main() printed {fails}, verify_bundle returned "
                         f"{refusals}")
        diffs += [f":{n} did not execute, expected it to" for n in row.ran
                  if n not in hit]
        diffs += [f":{n} executed, expected it not to" for n in row.not_ran
                  if n in hit]
        # A refused row must be refused by the sites that name its refusals and no
        # others; an accepted row must execute no refusal site at all.
        expected_sites = sorted({_site_for(msg) for msg in row.refusals})
        if executed != expected_sites:
            diffs.append(f"refusal sites executed {executed}, expected "
                         f"{expected_sites}")
        out.append({"label": row.label, "forgery": row.forgery,
                    "source": source, "in_ledger_table": row.in_ledger,
                    "bundle_sha256": bundle_digest(bundle), "exit": rc,
                    "refusals": refusals, "named_lines": named,
                    "refusal_sites_executed": executed, "diffs": diffs})
    return out


# Which f59fb62 site emits a message, for the messages this table expects, so a row's
# expected sites follow from its expected messages instead of being typed twice. A
# wrong entry here cannot hide: the sites a row actually executed are compared with
# the sites these patterns give.
_SITE_PATTERN = [
    (285, r"stamp-mismatch: (taskset_hash|prompt_hash): protocol .*, artifact "),
    (290, r"stamp-mismatch: harness_commit: protocol .*, artifact "),
    (376, r"stamp-mismatch: fleet_commit: protocol .*, artifact "),
    (385, r"stamp-mismatch: hashes\.fleet_commit: protocol .*, artifact "),
    (618, r"raw-aggregate-mismatch: \S+: metrics\.(vulnerability_score|flagged_cases"
          r"|n_cases|truncations|reliability) declared "),
    (655, r"summary-mismatch: vulnerability_score: declared .*, recomputed "),
    (1085, r"summary-outruns-checks: \S+: declares .*, recomputation gives "),
    (1088, r"summary-outruns-checks: \S+: declares .*, no check recomputes it$"),
]


def _site_for(message: str) -> int:
    hits = [line for line, pat in _SITE_PATTERN if re.match(pat, message)]
    if len(hits) != 1:
        raise KeyError(f"{message!r} maps to f59fb62 sites {hits}, not exactly one")
    return hits[0]


def baseline(sweep: pathlib.Path, text: str, sites: list[int]) -> dict[int, bool]:
    """Caught at baseline, by f59fb62 line, from the archived sweep.

    The archive keys each row by bare line number, and a line number names a
    statement only in the bytes it was measured on (V2-55). So the join is made only
    after two checks against the pinned source: the archive's line set is exactly the
    REFUSAL lines, and every row's refusal code appears on its own line. Either one
    failing means the archive measured other bytes, and the join would pair a
    survival with the wrong statement."""
    rows = json.loads(sweep.read_text(encoding="utf-8"))
    rows = rows["results"] if isinstance(rows, dict) else rows
    by_line = {r["line"]: r for r in rows}
    if len(rows) != len(by_line) or sorted(by_line) != sites:
        raise ValueError(f"{sweep.name}: {len(rows)} rows on {len(by_line)} lines, "
                         f"not the {len(sites)} refusal lines of the pinned source")
    src = text.splitlines()
    off = sorted(n for n, r in by_line.items() if r["reason"] not in src[n - 1])
    if off:
        raise ValueError(f"{sweep.name}: rows whose refusal code is not on their "
                         f"line in the pinned source: {off[:10]}")
    return {n: bool(r["caught"]) for n, r in by_line.items()}


def table1(caught: dict[int, bool], results: list[dict]) -> list[dict]:
    """Survivors among the refusals that name each forgery's lie.

    Each such refusal must also have executed in some row of the replay, which is
    what the wrong-value controls are for: a count of survivors among lines nothing
    can reach would be a count of dead code."""
    live = {s for r in results for s in r["refusal_sites_executed"]}
    out = []
    for n, what, lines in NAMES_THE_LIE:
        status = {ln: "caught" if caught[ln] else "survived" for ln in lines}
        survived = sum(1 for v in status.values() if v == "survived")
        diffs = []
        if (survived, len(lines)) != EXPECT_TABLE1[n]:
            diffs.append(f"{survived} of {len(lines)} survived, expected "
                         "{} of {}".format(*EXPECT_TABLE1[n]))
        # which lines, not only how many: the count can hold while the wrong
        # line survives
        wrong = [f":{ln} {status[ln]}, expected {EXPECT_BASELINE.get(ln, 'no value')}"
                 for ln in lines if status[ln] != EXPECT_BASELINE.get(ln)]
        if wrong:
            diffs.append("survivors differ from V2-02: " + ", ".join(wrong))
        dead = [ln for ln in lines if ln not in live]
        if dead:
            diffs.append(f"{dead} executed in no row of the replay")
        out.append({"forgery": n, "what": what, "names_the_lie": status,
                    "survived": survived, "of": len(lines), "diffs": diffs})
    return out


def baseline_diffs(caught: dict[int, bool]) -> list[str]:
    """Where the archive disagrees with V2-02's Evidence: a line it names as caught
    or survived that the archive records the other way, or a different total."""
    diffs = [f":{n} {'caught' if caught.get(n) else 'survived'} in the sweep, "
             f"V2-02 says {want}"
             for n, want in sorted(EXPECT_BASELINE.items())
             if n not in caught or ("caught" if caught[n] else "survived") != want]
    total = sum(caught.values())
    if total != EXPECT_CAUGHT:
        diffs.append(f"{total} of {len(caught)} caught, V2-02 says {EXPECT_CAUGHT}")
    return diffs


# The printed words for a named line, by kind. read_back() maps them to True/False
# again, so a printed table that says the opposite of what was measured is caught.
STATUS = {"site": ("fired", "did not fire"), "guard": ("ran", "did not run")}
_STATUS_LINE = re.compile(r"  :(\d+) +(fired|did not fire|ran|did not run)(?: |$)")
_SITES_LINE = "  refusal sites executed: "


def render(r: dict) -> list[str]:
    """One row of the printed table, as lines. The first is blank."""
    verdict = "PASS" if r["exit"] == 0 else "FAIL"
    mark = "reproduced" if not r["diffs"] else "DIFFERS"
    extra = "" if r["in_ledger_table"] else " (control, not in V2-02's table)"
    out = ["", f"{r['label']}  [{r['forgery']}]{extra}",
           f"  bundle: {r['source']}  sha256 {r['bundle_sha256'][:16]}",
           f"  verdict: {verdict}, exit {r['exit']}, {len(r['refusals'])} refusal(s)"]
    out += [f"    {msg}" for msg in r["refusals"]]
    for n, ran in r["named_lines"].items():
        kind, what = LINES.get(n, ("site", "refusal site"))
        yes, no = STATUS[kind]
        out.append(f"  :{n:<5} {yes if ran else no:<13} {what}")
    sites = ", ".join(f":{s}" for s in r["refusal_sites_executed"]) or "none"
    out.append(f"{_SITES_LINE}{sites}")
    out.append(f"  {mark}")
    out += [f"    - {d}" for d in r["diffs"]]
    return out


def read_back(block: list[str]) -> tuple[dict[int, bool | None], list[int] | None]:
    """What a printed row says: each named line's status, and the refusal sites it
    lists as executed. A status word of the wrong kind for its line reads as None."""
    named: dict[int, bool | None] = {}
    executed = None
    for ln in block:
        m = _STATUS_LINE.match(ln)
        if m:
            n, word = int(m.group(1)), m.group(2)
            yes, no = STATUS[LINES.get(n, ("site",))[0]]
            named[n] = True if word == yes else False if word == no else None
        elif ln.startswith(_SITES_LINE):
            rest = ln[len(_SITES_LINE):]
            executed = ([] if rest == "none"
                        else [int(s.strip().lstrip(":")) for s in rest.split(",")])
    return named, executed


def report(results: list[dict]) -> list[str]:
    """Print the table, then read each printed row back and compare it with what was
    measured. The rows' own checks compare measurements with the ledger; this one
    compares the words a reader sees with the measurements, so a table that prints
    "did not fire" for a line that fired fails the run instead of passing it."""
    diffs = []
    for r in results:
        block = render(r)
        print("\n".join(block))
        named, executed = read_back(block)
        if named != r["named_lines"]:
            diffs.append(f"{r['label']}: printed {named}, measured {r['named_lines']}")
        if executed != r["refusal_sites_executed"]:
            diffs.append(f"{r['label']}: printed sites {executed}, measured "
                         f"{r['refusal_sites_executed']}")
        fired = sorted(n for n, v in named.items()
                       if v and LINES.get(n, ("site",))[0] == "site")
        if fired != (executed or []):
            diffs.append(f"{r['label']}: printed as fired {fired}, listed as "
                         f"executed {executed}")
    return diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--verify-py", type=pathlib.Path,
                    help="a copy of vac/verify.py at f59fb62 (default: read it from "
                         "this repository's git objects)")
    ap.add_argument("--fixtures", type=pathlib.Path, default=REPO / "fixtures",
                    help="the fixture directory to replay (default: fixtures/)")
    ap.add_argument("--sweep", type=pathlib.Path, default=SWEEP,
                    help="the f59fb62 baseline sweep (default: paper/mutation.json)")
    ap.add_argument("--json", type=pathlib.Path, help="write the results here")
    a = ap.parse_args(argv)

    try:
        data = read_pinned(a.verify_py)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2
    text = data.decode("utf-8")
    bad = check_source(text)
    if bad:  # unreachable while the pin holds; kept so LINES cannot drift
        print("ABORT: named lines do not match the pinned source:\n  "
              + "\n  ".join(bad), file=sys.stderr)
        return 2
    sites = [n for n, ln in enumerate(text.splitlines(), 1) if REFUSAL.match(ln)]
    if len(sites) != EXPECT_SITES:
        print(f"ABORT: REFUSAL matches {len(sites)} lines at f59fb62, not "
              f"{EXPECT_SITES}. The site pattern changed meaning.", file=sys.stderr)
        return 2

    try:
        caught = baseline(a.sweep, text, sites)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"ABORT: the baseline sweep does not fit f59fb62: {e}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="vac-replay-") as td:
        work = pathlib.Path(td)
        mod = load(data, work / "f59fb62" / "vac" / "verify.py")
        results = replay(mod, sites, a.fixtures.resolve(), work)

    print(f"vac/verify.py at f59fb62: sha256 {PIN_SHA256}, blob {PIN_BLOB[:12]}, "
          f"{len(sites)} refusal sites")
    print(f"interpreter: {platform.python_implementation()} "
          f"{platform.python_version()}")
    print(f"fixtures: {a.fixtures}")
    misprinted = report(results)
    failed = [r["label"] for r in results if r["diffs"]]
    print(f"\n{len(results) - len(failed)} of {len(results)} rows reproduced"
          + (f"; differing: {', '.join(failed)}" if failed else ""))
    if misprinted:
        print("the printed table disagrees with the measurements:")
        for d in misprinted:
            print(f"  - DIFFERS: {d}")
        failed.append("printed table")

    t1 = table1(caught, results)
    off = baseline_diffs(caught)
    sweep_sha = hashlib.sha256(a.sweep.read_bytes()).hexdigest()
    print(f"\nTable 1, joined with {a.sweep.name} (sha256 {sweep_sha[:16]}; "
          f"{sum(caught.values())} of {len(caught)} caught; its line set and refusal "
          "codes match the pinned source):")
    for d in off:
        print(f"  - DIFFERS from V2-02's Evidence: {d}")
    if off:
        failed.append(f"{a.sweep.name} against V2-02")
    for t in t1:
        cells = ", ".join(f":{ln} {v}" for ln, v in t["names_the_lie"].items())
        tail = (f"; {t['survived']} of {t['of']} survived" if t["of"]
                else "V2-02 names no refusal for this lie")
        print(f"  forgery {t['forgery']}, {t['what']}: {cells}{tail}")
        for d in t["diffs"]:
            print(f"    - DIFFERS: {d}")
    failed += [f"Table 1 forgery {t['forgery']}" for t in t1 if t["diffs"]]
    print("\nresult: " + ("everything reproduced" if not failed
                          else "DIFFERS: " + ", ".join(failed)))

    if a.json:
        a.json.write_text(json.dumps(
            {"rev": REV, "verify_py_sha256": PIN_SHA256, "verify_py_blob": PIN_BLOB,
             "sites": len(sites), "python": platform.python_version(),
             "sweep": {"path": a.sweep.name, "sha256": sweep_sha,
                       "caught": sum(caught.values()), "diffs": off},
             "results": results, "printed_table_diffs": misprinted,
             "table1": t1}, indent=1) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
