"""The archived sweeps, reconciled by what each site is, not where it sat.

paper/reconcile_sweeps.py joins every archived mutation sweep to the
vac/verify.py blob its rows match, keys each row with the sweep's own
site_identities(), and reports every transition between adjacent files. Its
first version got four things wrong, and the tests here are aimed at them:

  * ORDER was a hand-typed list, and it paired files that were never
    adjacent. The order must come from each file's introducing commit, with
    files from one commit in name order. The same twelve archive names are
    introduced here in different orders, and edited after their add, so no
    list of names and no last-commit order can pass.
  * It compared {line: caught}, so two files that differ in three rows
    looked identical, and it printed "the same run under two names" for
    them. Rows are compared in full, every line the tool prints must be one
    of the sentences listed in KNOWN_LINES below, and none of those says
    two files are one run.
  * A line key cannot follow a site across an edit. The key must be the
    sweep's, scope included, looked up on tools/mutation_sweep.py when it is
    used: change that function and this tool's output must change with it.
  * A caught site that stops being caught must be reported wherever it sits,
    including across a line shift that a line key cannot see.

Two kinds of test. The SYNTHETIC ones build small repositories under tmp_path
and run anywhere git does. The HISTORY ones read this repository's own history
and archives and pin the ledger's numbers (V2-35, V2-36). They need the full
history, so they skip, and say why, where it is absent: outside a git checkout
(a git-archive export, which is how a sweep's scratch tree is made) and in a
shallow clone (the default actions/checkout). Set VAC_REQUIRE_GIT_HISTORY=1
and a missing history fails test_history_is_present_when_required instead.

Nothing here writes to this repository, runs a sweep, or reads the working
tree's vac/verify.py, so the file is safe inside a sweep's own detector.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "paper" / "reconcile_sweeps.py"
SWEEP = REPO / "tools" / "mutation_sweep.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rec = _load(TOOL, "_reconcile_under_test")
# Loaded separately from the tool's own copy, so a tool that stopped using
# the sweep's function would be compared against the real one.
sweep = _load(SWEEP, "_reconcile_test_sweep")

# Typed out, not read from the tool, so a tool that emptied its constant
# would not pass by printing the empty string.
ASSUMPTION_TEXT = (
    "ASSUMPTION: every keying below assumes each archive file measured a "
    "tree whose vac/verify.py equals the blob it is matched to. The row set "
    "and the reason codes are evidence for that, not proof of it.")


# --------------------------------------------------------------------------
# every sentence the tool may print

_SHA = r"[0-9a-f]{7}"
_DATE = r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4}"
_FIELD = r"(reason|the detector \(how\))"
# The tool's whole vocabulary, one pattern per kind of line, each matched
# against a whole line. A sentence the tool starts to print that is not here
# fails every test that reads its output, so no new phrasing, a synonym for
# "the same run" included, can arrive without this list being changed on
# purpose. None of these says that two files are one run.
KNOWN_LINES = [re.compile(p) for p in (
    r"",
    r"Reconciling \d+ archived sweeps against the history of HEAD " + _SHA
    + r" \(\d+ commits\)\.",
    r"Site key: site_identities\(\) imported from tools/mutation_sweep\.py "
    r"\(enclosing scope, normalised statement, ordinal\)\.",
    r"REFUSAL: '.+', (the same in every committed version of the sweep that "
    r"defines it|and no committed version of the sweep is in this history|"
    r"BUT committed versions of the sweep use .+)",
    re.escape(ASSUMPTION_TEXT),
    r"== Order: introducing commit \(git log --diff-filter=A --no-renames\), "
    r"then name order within one commit ==",
    r"  [ \d]\d  \S+ +\S+ +" + _SHA + "  " + _DATE + r"  \((equals HEAD|not "
    r"at HEAD|DIFFERS FROM HEAD)(; re-added at " + _SHA + "(, " + _SHA
    + r")*)?\)",
    r"  NOTE: " + _SHA + " is not an ancestor of " + _SHA + r"; \S+ -> \S+ "
    r"is ordered by topology, not by descent",
    r"== Each file's vac/verify\.py blob: the commits whose refusal sites "
    r"minus that commit's EXCLUDE equal the rows ==",
    r"  \S+ +\d+/\d+ \((no header|header \d+/\d+( DISAGREES WITH ROWS)?), "
    r"(bare list|dict with header)\): (blob " + _SHA + r", \d+ raw sites, "
    r"\d+ excluded|matches NO committed blob; left unkeyed|matches SEVERAL "
    r"blobs: " + _SHA + "(, " + _SHA + r")+; left unkeyed)",
    r"          rows equal the scored sites at (" + _SHA + r"|\d+ commits, "
    r"first " + _SHA + ", last " + _SHA + r"); (its introducing commit is "
    r"one of them|NOT its introducing commit " + _SHA + ")",
    r"          reasons that differ from the source line: L\d+ row .+, "
    r"source .+",
    r"          RECORDED SITE KEY DIFFERS at L\d+(, L\d+)*",
    r"          MEASURED SHA256 DIFFERS from the matched blob",
    r"          measured\.source\.sha256 equals the matched blob",
    r"== Transitions, in introduction order \(\d+\) ==",
    r"\S+ -> \S+: NOT KEYED \(a file has no unique blob\)",
    r"\S+ -> \S+   \[\S+\.json -> \S+\.json\]   blob " + _SHA + " -> " + _SHA,
    r"  order: both files were introduced by " + _SHA + r"; name order puts "
    r"\S+ first",
    r"  content keys: \d+ paired \(caught \d+ -> \d+\), \d+ arrive \(\d+ "
    r"caught\), \d+ depart \(\d+ survivors\); key sets (identical|differ)",
    r"  verdict flips: \d+ caught -> surviving, \d+ surviving -> caught",
    r"  same key set and verdicts; (1 row differs|\d+ rows differ): \d+ in "
    + _FIELD + r"(, \d+ in " + _FIELD + r")*",
    r"  same key set and verdicts; every row identical in verdict, detector "
    r"and reason",
    r"    CAUGHT -> SURVIVING  L\d+ \S+ .+ -> L\d+",
    r"    row differs  L\d+ -> L\d+ \S+: (how|reason) .+ -> .+",
    r"    arrive  L\d+ \S+ .+  (caught|SURVIVED)  \((new in the source|was "
    r"excluded in \S+)\)",
    r"    depart  L\d+ \S+ .+  (caught|SURVIVED)  \((excluded in \S+|not in "
    r"\S+'s source: deleted, or its statement or scope changed)\)",
    r"  line keys: \d+ shared \(caught \d+ -> \d+ among them; \d+ caught -> "
    r"surviving and \d+ surviving -> caught by line\); line key sets "
    r"(identical|differ); (same blob, so line keys are valid here|different "
    r"blobs, so a line key need not name one site)",
    r"TOTAL over \d+ transitions: \d+ arrive, \d+ caught on arrival; \d+ "
    r"depart, \d+ of them survivors; \d+ caught -> surviving; \d+ surviving "
    r"-> caught\.",
    r"That \d+ caught -> surviving holds for the name-order tiebreak; \d+ of "
    r"the \d+ within-commit orders gives? 0 \(see the tiebreak section\)\.",
    r"That \d+ caught -> surviving is over the keyed transitions only, in "
    r"the name order; the tiebreak check needs every file keyed and was not "
    r"run\.",
    r"That \d+ caught -> surviving is in the name order; the tiebreak check "
    r"was not computed\.",
    r"Adjacent pairs with identical key sets: \d+ of \d+ by content key, \d+ "
    r"of \d+ by line key\.",
    r"Transitions between two files on one blob, the only ones where a line "
    r"key names one site: \d+ of \d+\.",
    r"Transitions whose order rests on the name tiebreak: \d+\.",
    r"Transitions not keyed: \d+\.",
    r"== Sensitivity to the same-commit tiebreak: every order of the files "
    r"within each introducing commit ==",
    r"  \d+ orders, more than \d+; not computed",
    r"  \d+ orders; \d+ show no site going from caught to surviving(, the "
    r"name order among them)?",
    r"  \S+ -> \S+: \d+ caught -> surviving, (in the only order there is|in "
    r"every one of the \d+ orders, since \S+ always follows \S+, so it does "
    r"not rest on the tiebreak|only in the \d+ of \d+ orders that place \S+ "
    r"right after \S+); (one blob|DIFFERENT BLOBS)",
    r"  falls between different blobs, under any order: (none|\S+ -> \S+(, "
    r"\S+ -> \S+)*)",
    r"  No order shows a site going from caught to surviving, so that count "
    r"does not rest on the tiebreak\.",
    r"  THE ZERO RESTS ON THE TIEBREAK\. The name order gives 0 caught -> "
    r"surviving over \d+ transitions, and \d+ of the \d+ orders gives? 0\. "
    r"It puts \S+ (before|not right after) \S+((, | and )\S+ (before|not "
    r"right after) \S+)*; an order that places \S+ right after \S+ shows \d+ "
    r"falls?(, and one that places \S+ right after \S+ shows \d+ falls?)*\.",
    r"  The name order gives \d+ caught -> surviving over \d+ transitions; "
    r"\d+ of the \d+ orders gives? 0\.",
    r"  Evidence for the order within each commit, from outside the rows:",
    r"    " + _SHA + r" \([^)]+\): its message quotes (no score that any of "
    r"these files has|\S+ \([^)]+\)(; \S+ \([^)]+\))*)",
    r'      ".*"',
    r"    " + _SHA + r" file mtimes, earliest first: [^;]+ " + _DATE + "(; "
    r"[^;]+ " + _DATE + ")*",
    r"  \(Messages are read from git\. Mtimes are read from the files read "
    r"here: they say when a sweep wrote its file only in the tree it wrote "
    r"it in, and a checkout stamps its own\.\)",
    r"== Files that match the same blob, compared row for row ==",
    r"  \S+ vs \S+ \(blob " + _SHA + r"\): \d+ shared keys = \d+ identical "
    r"\+ \d+ verdict flips \(\d+ up, \d+ down\) \+ \d+ other; \d+ keys in "
    r"one only",
    r"== Statements with more than one site, per matched blob ==",
    r"  blob " + _SHA + r" \([^)]+\): \d+ of \d+ sites share their text, in "
    r"\d+ groups?",
    r"    x\d+ .+",
    r"       L\d+ \S+#\d+ \[[CSx,]+\](; L\d+ \S+#\d+ \[[CSx,]+\])*",
    r"  \(C caught, S survived, x not scored, one letter per file in the "
    r"order listed\)",
    r"== Ablation: statement text plus a file-wide ordinal, no scope ==",
    r"  \S+ -> \S+: \S+ L\d+ \(\S+\) pairs with (L\d+ \(\S+\)|nothing \(it "
    r"departs\)) under the site key and with L\d+ \(\S+\) without the scope",
    r"  misattributed pairings: \d+\. Totals without the scope: \d+ arrive, "
    r"\d+ caught on arrival, \d+ depart, \d+ caught -> surviving, \d+ "
    r"surviving -> caught\.",
    # --pair
    r"  \S+'s \d+ survivors, by scope: caught in \S+ / still surviving / not "
    r"in \S+",
    r"    \S+ +\d+: \d+ / \d+ / \d+",
    r"  still surviving: L\d+->L\d+(, L\d+->L\d+)*",
)]

# Phrasings that would say two files are one run. KNOWN_LINES already keeps
# them out of the tool's own sentences; this also covers the free text the
# tool quotes (statements, reasons, commit message lines).
ONE_RUN = re.compile(r"same run|one run|same sweep|one sweep|recorded twice|"
                     r"two names|duplicate (run|sweep)|identical (run|sweep)|"
                     r"same measurement", re.IGNORECASE)


def _assert_known_sentences(text: str) -> None:
    unknown = [ln for ln in text.split("\n")
               if not any(p.fullmatch(ln) for p in KNOWN_LINES)]
    assert unknown == [], f"lines the tool is not known to print: {unknown}"
    assert not ONE_RUN.search(text), ONE_RUN.search(text).group(0)


# --------------------------------------------------------------------------
# synthetic repositories

_T0 = 1_700_000_000


def _git(cwd: pathlib.Path, *args: str, stdin: bytes | None = None) -> str:
    """git with no user or system config and no inherited GIT_* variables,
    so a developer's hooks, signing or GIT_DIR cannot reach these
    repositories."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(["git", "-C", str(cwd), *args], input=stdin,
                          capture_output=True, env=env,
                          check=True).stdout.decode()


class Repo:
    """A small repository for one test.

    Commits are written with one `git fast-import` per batch rather than
    three git processes per commit: this file runs inside every mutant's
    test run of the sweep, and the histories here reach thirteen commits.
    Each file is also written to the working tree, where the tool reads the
    archives. Pending commits are imported when `root` or `sha()` is read,
    so a test always runs the tool on the full history. Commit n is dated
    _T0 + 60 n, so commit order and date order agree and neither can hide
    behind a one-second tie."""

    def __init__(self, root: pathlib.Path):
        self._root = root
        self._pending: list[tuple[dict, str]] = []
        self._shas: list[str] = []
        root.mkdir(parents=True, exist_ok=True)
        _git(root, "init", "-q")
        # The branch HEAD names, whatever this git calls its default.
        self._ref = (root / ".git" / "HEAD").read_text().split(": ")[1].strip()

    def commit(self, files: dict[str, str | None], msg: str = "c") -> int:
        """Write each file, or delete it where its text is None, and queue
        a commit of those changes. Returns the commit's index for sha()."""
        for rel, text in files.items():
            p = self._root / rel
            if text is None:
                p.unlink()
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        self._pending.append((files, msg))
        return len(self._shas) + len(self._pending) - 1

    def _import(self) -> None:
        if not self._pending:
            return
        out, n0 = [], len(self._shas)
        who = b"reconcile-test <reconcile-test@example.invalid>"
        for k, (files, msg) in enumerate(self._pending):
            n = n0 + k + 1
            m = msg.encode()
            out += [b"commit %s\nmark :%d\n" % (self._ref.encode(), n),
                    b"author %s %d +0000\n" % (who, _T0 + 60 * n),
                    b"committer %s %d +0000\n" % (who, _T0 + 60 * n),
                    b"data %d\n%s\n" % (len(m), m)]
            if n > 1:
                out.append(b"from %s\n" % (b":%d" % (n - 1) if k else
                                           self._shas[-1].encode()))
            for rel, text in sorted(files.items()):
                if text is None:
                    out.append(b"D %s\n" % rel.encode())
                else:
                    d = text.encode()
                    out.append(b"M 100644 inline %s\ndata %d\n%s\n"
                               % (rel.encode(), len(d), d))
            out.append(b"\n")
        marks = self._root / ".git" / "reconcile-test.marks"
        _git(self._root, "fast-import", "--quiet",
             f"--export-marks={marks}", stdin=b"".join(out))
        ids = dict(ln.split() for ln in marks.read_text().splitlines())
        self._shas += [ids[f":{n}"] for n in
                       range(n0 + 1, n0 + len(self._pending) + 1)]
        self._pending = []

    @property
    def root(self) -> pathlib.Path:
        self._import()
        return self._root

    def sha(self, i: int) -> str:
        self._import()
        return self._shas[i]


# Two functions hold the same refusal statement. The copy in alpha is
# caught; the copy in beta survives.
V1 = '''def alpha(f):
    f.append("dup-code: the same words")
    f.append("alpha-code: one")


def beta(f):
    f.append("dup-code: the same words")
    f.append("beta-code: two")
'''

# alpha's copy is deleted and two lines are inserted above everything, so
# every surviving site moves: a line key names none of them any more.
V2 = '''# one line
# and another
def alpha(f):
    f.append("alpha-code: one")


def beta(f):
    f.append("dup-code: the same words")
    f.append("beta-code: two")
'''

# V1 with one message edited: the same lines, a different blob.
V1_EDITED = V1.replace("beta-code: two", "beta-code: two, reworded")

SWEEP_NONE = 'REFUSAL = re.compile(r"^\\s*(f|failures)\\.append\\(")\n'
SWEEP_EXCLUDING_BETA = SWEEP_NONE + (
    'EXCLUDE: dict[str, tuple[int, str]] = {\n'
    '    "beta-code": (1, "why it cannot be reached"),\n'
    '}\n')


def _line(src: str, text: str, nth: int = 0) -> int:
    hits = [i + 1 for i, ln in enumerate(src.splitlines())
            if sweep.REFUSAL.match(ln) and text in ln]
    return hits[nth]


def _rows(src: str, verdicts: dict[tuple[str, int], object],
          skip: tuple[tuple[str, int], ...] = ()) -> list[dict]:
    """One row per refusal site in `src`, in line order. `verdicts` maps
    (text, nth copy) to caught (a bool) or to a full {caught, how, reason}
    override; any site not named is caught by tests."""
    out, seen = [], {}
    for i, ln in enumerate(src.splitlines()):
        if not sweep.REFUSAL.match(ln):
            continue
        code = re.search(r'"([a-z-]+):', ln).group(1)
        nth = seen.get(code, 0)
        seen[code] = nth + 1
        if (code, nth) in skip:
            continue
        v = verdicts.get((code, nth), True)
        row = {"line": i + 1, "caught": True, "how": "tests", "reason": code}
        if isinstance(v, dict):
            row.update(v)
        else:
            row.update(caught=v, how="tests" if v else "SURVIVED")
        out.append(row)
    return out


def _archive(rows: list[dict], header: bool = True, **extra) -> str:
    if not header:
        return json.dumps(rows)
    k = sum(1 for r in rows if r["caught"])
    return json.dumps({"score": round(k / len(rows), 4), "caught": k,
                       "total": len(rows), **extra, "results": rows})


def _run(repo: pathlib.Path, *extra: str, capsys=None):
    code = rec.main(["--repo", str(repo), *extra])
    text = capsys.readouterr().out if capsys else ""
    _assert_known_sentences(text)
    return code, text


def _reconciled(repo: pathlib.Path):
    hist, archives = rec.reconcile(repo, repo / "paper", "paper")
    lines, summary = rec.report(hist, archives)
    text = "\n".join(lines)
    _assert_known_sentences(text)
    return archives, text, summary


def _file_blocks(text: str) -> dict[str, str]:
    """label -> that file's lines in the blob section of the report."""
    section = text.split("\n== Each file's", 1)[1].split("\n== ", 1)[0]
    blocks: dict[str, list[str]] = {}
    for ln in section.splitlines()[1:]:
        m = re.match(r"  (\S+) +\d+/\d+ \(", ln)
        if m:
            label = m.group(1)
            blocks[label] = []
        if ln:
            blocks[label].append(ln)
    return {k: "\n".join(v) for k, v in blocks.items()}


# --------------------------------------------------------------------------
# ORDER comes from history, never from a list


@pytest.mark.parametrize("first,second", [("zeta", "able"), ("able", "zeta")])
def test_order_follows_the_introducing_commit_not_the_name(tmp_path, first,
                                                           second):
    """The same four files, introduced in two different orders, must come
    out in those two orders. A hand-typed ORDER cannot pass both, and
    neither can a sort by name."""
    r = Repo(tmp_path / "r")
    rows = _archive(_rows(V1, {}))
    r.commit({"vac/verify.py": V1, "tools/mutation_sweep.py": SWEEP_NONE,
              f"paper/mutation_{first}.json": rows})
    r.commit({"paper/mutation_beta.json": rows,
              "paper/mutation_alpha.json": rows})
    r.commit({f"paper/mutation_{second}.json": rows})
    archives, text, summary = _reconciled(r.root)
    assert [a.label for a in archives] == [first, "alpha", "beta", second]
    # alpha and beta share a commit; history cannot order them, and the
    # output must say that transition rests on the name tiebreak.
    assert summary["name_order_ties"] == 1
    assert "both files were introduced by" in text


# The twelve names this repository's archives carry, in the order their
# commits introduced them (EXPECTED below pins that order against history).
REAL_NAMES = ["mutation.json", "mutation_after.json", "mutation_gated.json",
              "mutation_covered.json", "mutation_final.json",
              "mutation_v2.json", "mutation_v3.json", "mutation_final2.json",
              "mutation_v5.json", "mutation_v6.json", "mutation_v7.json",
              "mutation_v8.json"]
ORDERS = {"as committed": REAL_NAMES, "reversed": REAL_NAMES[::-1]}


@pytest.mark.parametrize("how", sorted(ORDERS))
def test_the_real_archive_names_are_ordered_by_their_history(tmp_path, how):
    """Requirement 2: the order is derived from the data, and demonstrably.

    The twelve real archive names are introduced in two different orders,
    the order this repository committed them in and its reverse, one file
    per commit, and then the first file introduced is edited, so that its
    last commit comes after every other file's. Everything a hand-maintained
    order could key on is the same in both histories (the names, the rows,
    the blob), so any fixed list of names, however right for this
    repository, gives the same order twice and fails at least one of these.
    Taking each file's last touching commit instead of its introducing one
    moves the edited file to the end, and fails both. Only the introducing
    commit passes, and the transitions, and where the one fall is reported,
    follow it."""
    intro = ORDERS[how]
    r = Repo(tmp_path / "r")
    for i, name in enumerate(intro):
        # The second file introduced is the one where beta-code survives, so
        # the fall sits on the first transition of the introduction order.
        rows = _rows(V1, {("beta-code", 0): False} if i == 1 else {})
        extra = ({"vac/verify.py": V1, "tools/mutation_sweep.py": SWEEP_NONE}
                 if i == 0 else {})
        r.commit({**extra, f"paper/{name}": _archive(rows)})
    first = r.commit({f"paper/{intro[0]}": json.dumps(
        json.loads(_archive(_rows(V1, {}))), indent=1)},
        msg="edit the first archive after the others were added")

    # The history really does separate the three candidate orders: each
    # file's last commit, newest first, puts the edited file at the end.
    last = {}
    log = _git(r.root, "log", "--format=%x00%H", "--name-only", "--",
               "paper").split("\0")[1:]
    for chunk in log:
        sha, *paths = chunk.split()
        for p in paths:
            last.setdefault(pathlib.Path(p).name, sha)
    assert last[intro[0]] == r.sha(first)
    shas = [r.sha(i) for i in range(len(intro) + 1)]
    order_by_last = sorted(intro, key=lambda n: shas.index(last[n]))
    assert order_by_last == intro[1:] + intro[:1] != intro
    assert sorted(intro) != intro

    archives, text, summary = _reconciled(r.root)
    assert [a.name for a in archives] == intro
    assert [(t["from"], t["to"]) for t in summary["transitions"]] == \
        list(zip(intro, intro[1:]))
    falls = [(t["from"], t["to"]) for t in summary["transitions"]
             if t["caught_to_surviving"]]
    assert falls == [(intro[0], intro[1])]
    assert summary["name_order_ties"] == 0
    assert text.count("equals HEAD") == 12
    assert "re-added" not in text


def test_an_archive_edited_or_readded_later_keeps_its_introducing_place(
        tmp_path):
    """a is added first, then b, then c; then a is edited, and b is deleted
    and added again. Placed by the introducing commit, the order is a, b, c,
    and only b is reported as re-added. Placed by the last commit that
    touched each file it would be c, a, b; placed by the last add, a, c, b;
    and counting a mere edit as an add would call a re-added."""
    rows = _archive(_rows(V1, {}))
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1, "paper/mutation_a.json": rows})
    r.commit({"paper/mutation_b.json": rows})
    r.commit({"paper/mutation_c.json": rows})
    r.commit({"paper/mutation_a.json": json.dumps(json.loads(rows),
                                                  indent=1)})
    r.commit({"paper/mutation_b.json": None})
    readd = r.sha(r.commit({"paper/mutation_b.json": rows}))
    archives, text, _ = _reconciled(r.root)
    assert [a.label for a in archives] == ["a", "b", "c"]
    assert [a.readded for a in archives] == [[], [readd], []]
    lines = {a.label: ln for a in archives for ln in text.splitlines()
             if f" {a.name} " in ln}
    assert f"re-added at {readd[:7]})" in lines["b"]
    assert "re-added" not in lines["a"] and "re-added" not in lines["c"]


def test_the_tool_holds_no_archive_name_outside_its_docstrings():
    """No list of archive names, and no single name, sits in the tool's code.
    The names in its docstrings are usage and history, not data."""
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if (isinstance(node, (ast.Module, ast.FunctionDef,
                              ast.AsyncFunctionDef, ast.ClassDef))
                and node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)):
            docs.add(id(node.body[0].value))
    named = [n.value for n in ast.walk(tree)
             if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and id(n) not in docs
             and re.search(r"mutation(_\w+)?\.json", n.value)]
    assert named == []


def test_a_file_git_never_saw_has_no_place_in_the_order(tmp_path, capsys):
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(_rows(V1, {}))})
    (r.root / "paper" / "mutation_b.json").write_text(
        _archive(_rows(V1, {})))
    code = rec.main(["--repo", str(r.root)])
    err = capsys.readouterr().err
    assert code == 2 and "mutation_b.json" in err and "never added" in err


def test_a_shallow_clone_is_refused_not_half_read(tmp_path, capsys):
    """In a shallow clone the first file's introducing commit is missing,
    and read anyway it would look like a file git never saw, or like one
    that matches no blob. The tool must name the real cause."""
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(_rows(V1, {}))})
    r.commit({"paper/mutation_b.json": _archive(_rows(V1, {}))})
    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", r.root.as_uri(),
         str(shallow))
    code = rec.main(["--repo", str(shallow)])
    err = capsys.readouterr().err
    assert code == 2 and "shallow clone" in err


def test_a_directory_inside_a_checkout_is_not_read_as_it(tmp_path, capsys):
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(_rows(V1, {}))})
    code = rec.main(["--repo", str(r.root / "paper")])
    err = capsys.readouterr().err
    assert code == 2 and "not the top of a git checkout" in err


def test_inherited_git_variables_do_not_redirect_the_tool(tmp_path,
                                                          monkeypatch,
                                                          capsys):
    """A hook or a shell that exports GIT_DIR would make every git query
    answer for another repository. The tool must drop inherited GIT_*
    variables and read the repository it was given."""
    r = Repo(tmp_path / "r")
    head = r.sha(r.commit({"vac/verify.py": V1,
                           "paper/mutation_a.json": _archive(_rows(V1, {})),
                           "paper/mutation_b.json": _archive(_rows(V1, {}))}))
    decoy = Repo(tmp_path / "decoy")
    decoy.commit({"README": "another repository\n"})
    monkeypatch.setenv("GIT_DIR", str(decoy.root / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy.root))
    assert not any(k.startswith("GIT_") and k != "GIT_OPTIONAL_LOCKS"
                   for k in rec._git_env())
    code = rec.main(["--repo", str(r.root)])
    out, err = capsys.readouterr()
    assert code == 0, err
    _assert_known_sentences(out)
    assert f"history of HEAD {head[:7]} (1 commits)" in out


# --------------------------------------------------------------------------
# MATCH: one blob, or say so


def test_exclude_is_read_from_the_commit_that_carries_it(tmp_path):
    """final's rows lack beta-code, and only the second commit's EXCLUDE
    explains that. The departure must be reported as an exclusion, not as a
    deletion from the source."""
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1, "tools/mutation_sweep.py": SWEEP_NONE,
              "paper/mutation_a.json": _archive(_rows(V1, {}))})
    c2 = r.commit({"tools/mutation_sweep.py": SWEEP_EXCLUDING_BETA,
                   "paper/mutation_b.json": _archive(
                       _rows(V1, {}, skip=(("beta-code", 0),)))})
    archives, text, summary = _reconciled(r.root)
    b = archives[1]
    assert b.match_commits == [r.sha(c2)]
    assert summary["depart"] == 1
    assert summary["transitions"][0]["depart_excluded"] == 1
    assert "(excluded in b)" in text


def test_a_readmitted_site_is_not_called_new(tmp_path):
    """The mirror of the test above: beta-code was excluded when a was
    written and scored again when b was. Its arrival is a re-admission,
    and must not be reported as a site new in the source."""
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "tools/mutation_sweep.py": SWEEP_EXCLUDING_BETA,
              "paper/mutation_a.json": _archive(
                  _rows(V1, {}, skip=(("beta-code", 0),)))})
    r.commit({"tools/mutation_sweep.py": SWEEP_NONE,
              "paper/mutation_b.json": _archive(_rows(V1, {}))})
    _, text, summary = _reconciled(r.root)
    t = summary["transitions"][0]
    assert (t["arrive"], t["arrive_readmitted"]) == (1, 1)
    assert (f"    arrive  L{_line(V1, 'beta-code')} beta beta-code  caught  "
            "(was excluded in a)") in text.splitlines()
    assert "new in the source" not in text


def test_a_file_that_matches_no_blob_is_left_unkeyed(tmp_path, capsys):
    r = Repo(tmp_path / "r")
    rows = _rows(V1, {})
    rows[0]["line"] = 4     # a blank line: no blob has a refusal there
    r.commit({"vac/verify.py": V1, "paper/mutation_a.json": _archive(rows),
              "paper/mutation_b.json": _archive(_rows(V1, {}))})
    code, text = _run(r.root, capsys=capsys)
    assert code == 1
    assert "matches NO committed blob" in text
    assert "NOT KEYED" in text


def test_the_json_summary_keeps_the_unkeyed_file_names(tmp_path, capsys):
    """The --json summary lists the unkeyed files by name. The count of
    transitions that could not be keyed is a separate number and must not
    overwrite the list."""
    r = Repo(tmp_path / "r")
    rows = _rows(V1, {})
    rows[0]["line"] = 4
    r.commit({"vac/verify.py": V1, "paper/mutation_a.json": _archive(rows),
              "paper/mutation_b.json": _archive(_rows(V1, {})),
              "paper/mutation_c.json": _archive(_rows(V1, {}))})
    out = tmp_path / "summary.json"
    code, text = _run(r.root, "--json", str(out), capsys=capsys)
    summary = json.loads(out.read_text())
    assert code == 1
    assert summary["unkeyed"] == ["mutation_a.json"]
    assert summary["unkeyed_transitions"] == 1
    assert [(t["from"], t["to"]) for t in summary["transitions"]] == \
        [("mutation_b.json", "mutation_c.json")]
    assert "Transitions not keyed: 1." in text
    assert "tiebreak" not in summary
    assert ("That 0 caught -> surviving is over the keyed transitions only, "
            "in the name order; the tiebreak check needs every file keyed "
            "and was not run.") in text.splitlines()


def test_a_file_that_matches_two_blobs_is_not_guessed(tmp_path, capsys):
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1})
    r.commit({"vac/verify.py": V1_EDITED,
              "paper/mutation_a.json": _archive(_rows(V1, {})),
              "paper/mutation_b.json": _archive(_rows(V1, {}))})
    code, text = _run(r.root, capsys=capsys)
    assert code == 1
    assert "matches SEVERAL blobs" in text
    # Reported is not enough: a file keyed to either blob would be a guess,
    # so neither file may be keyed and their transition must say so.
    archives, _, _ = _reconciled(r.root)
    assert [a.keyed for a in archives] == [None, None]
    assert "a -> b: NOT KEYED" in text


def test_a_recorded_site_key_and_measured_hash_are_checked(tmp_path, capsys):
    """Sweeps from V2-55 on record a site key per row and the sha256 of the
    verify.py they measured. Where an archive carries them, the match must
    agree with them, and a disagreement must be printed, listed and make the
    exit code 1: a (both agree), b (a key differs), c (the hash differs)."""
    ids = sweep.site_identities(V1.splitlines(keepends=True))
    good = _rows(V1, {})
    for row in good:
        row["key"] = ids[row["line"] - 1]["key"]
    bad = [dict(row) for row in good]
    bad[1]["key"] = "alpha::something else#0"

    def measured(text):
        digest = hashlib.sha256(text.encode()).hexdigest()
        return {"source": {"path": "vac/verify.py", "sha256": digest}}

    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(good, measured=measured(V1)),
              "paper/mutation_b.json": _archive(bad),
              "paper/mutation_c.json": _archive(
                  good, measured=measured(V1_EDITED))})
    out = tmp_path / "summary.json"
    code, text = _run(r.root, "--json", str(out), capsys=capsys)
    summary = json.loads(out.read_text())
    blocks = _file_blocks(text)
    assert "measured.source.sha256 equals the matched blob" in blocks["a"]
    assert f"RECORDED SITE KEY DIFFERS at L{bad[1]['line']}" in blocks["b"]
    assert "MEASURED SHA256 DIFFERS from the matched blob" in blocks["c"]
    assert "MEASURED SHA256 DIFFERS" not in blocks["a"] + blocks["b"]
    assert summary["recorded_key_differs"] == ["mutation_b.json"]
    assert summary["measured_sha256_differs"] == ["mutation_c.json"]
    assert summary["unkeyed"] == []
    assert code == 1


def test_a_header_that_disagrees_with_its_rows_is_flagged(tmp_path, capsys):
    """A header is the archive's own claim about its rows. One that says 4/4
    over rows that count 3/4 must be printed, listed and make the exit code
    1; the same file with a true header must not."""
    rows = _rows(V1, {("beta-code", 0): False})
    lying = json.loads(_archive(rows))
    lying.update(caught=4, score=1.0)
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": json.dumps(lying),
              "paper/mutation_b.json": _archive(rows)})
    out = tmp_path / "summary.json"
    code, text = _run(r.root, "--json", str(out), capsys=capsys)
    summary = json.loads(out.read_text())
    lines = text.splitlines()
    assert any(ln.startswith("  a       3/4 (header 4/4 DISAGREES WITH ROWS, "
                             "dict with header): blob ") for ln in lines)
    assert any(ln.startswith("  b       3/4 (header 3/4, dict with header): "
                             "blob ") for ln in lines)
    assert summary["header_disagrees"] == ["mutation_a.json"]
    assert code == 1


# --------------------------------------------------------------------------
# KEY: the sweep's own key, scope included


def test_rows_are_keyed_by_the_sweeps_own_site_identities(tmp_path):
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(_rows(V1, {}))})
    archives, _, _ = _reconciled(r.root)
    ids = sweep.site_identities(V1.splitlines(keepends=True))
    want = {ids[r_["line"] - 1]["key"] for r_ in _rows(V1, {})}
    assert set(archives[0].keyed) == want
    # The scope is in the key: the two copies of the duplicated statement
    # are told apart by the function that holds them.
    assert {k.split("::")[0] for k in want if "dup-code" in k} == {"alpha",
                                                                  "beta"}


def test_the_key_function_is_the_sweeps_own_looked_up_when_used(tmp_path,
                                                                monkeypatch):
    """Requirement 4: the tool consumes tools/mutation_sweep.py's
    site_identities(), not a copy.

    Three checks, each of which a copy fails. The module the tool loaded is
    that file, and the function's code was compiled from it. The tool
    defines no key function of its own. And replacing the function on the
    sweep module the tool loaded replaces the keys the tool reports, so the
    function the tool calls is the sweep's, at the time it keys the rows."""
    assert pathlib.Path(rec._sweep.__file__).resolve() == SWEEP
    code = rec._sweep.site_identities.__code__
    assert pathlib.Path(code.co_filename).resolve() == SWEEP
    assert rec.REFUSAL is rec._sweep.REFUSAL
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    defined = {n.name for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not defined & {"site_identities", "_qualname_map", "span"}

    real_fn = rec._sweep.site_identities
    calls = []

    def marked(lines):
        calls.append(len(lines))
        return {i: dict(v, key="marked:" + v["key"])
                for i, v in real_fn(lines).items()}

    monkeypatch.setattr(rec._sweep, "site_identities", marked)
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(_rows(V1, {}))})
    archives, _, _ = _reconciled(r.root)
    assert calls == [len(V1.splitlines())]
    assert sorted(archives[0].keyed) == sorted(
        "marked:" + v["key"] for v in
        sweep.site_identities(V1.splitlines(keepends=True)).values())


def _scopeless_sweep(tmp_path: pathlib.Path) -> pathlib.Path:
    """The working tree's tools/mutation_sweep.py with one mutation: the
    site key's scope is always <module>. Its ordinal is then counted over
    the whole file, which is the ablation's key."""
    src = SWEEP.read_text(encoding="utf-8")
    anchor = 'scope = qual.get(a0 + 1, "<module>")'
    assert src.count(anchor) == 1, "the sweep's scope line has moved"
    p = tmp_path / "scopeless" / "tools" / "mutation_sweep.py"
    p.parent.mkdir(parents=True)
    p.write_text(src.replace(anchor, 'scope = "<module>"'), encoding="utf-8")
    return p


def _dup_repo(root: pathlib.Path) -> Repo:
    """alpha's copy of the duplicated statement (caught) is deleted; beta's
    copy (surviving) stays and moves."""
    r = Repo(root)
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(
                  _rows(V1, {("dup-code", 1): False}))})
    r.commit({"vac/verify.py": V2,
              "paper/mutation_b.json": _archive(
                  _rows(V2, {("dup-code", 0): False}))})
    return r


def test_a_duplicated_statement_is_not_paired_across_functions(tmp_path):
    """Keyed by text and ordinal alone, beta's copy would inherit alpha's
    ordinal, and the report would show a caught site falling to surviving
    that never fell. Keyed with the scope, alpha's copy departs and beta's
    copy stays a survivor. By line, the one shared line (8) is beta-code in
    V1 and beta's copy in V2, so the line view shows a fall that the
    content key does not: the 239e1ba artifact in miniature."""
    r = _dup_repo(tmp_path / "r")
    archives, text, summary = _reconciled(r.root)
    t = summary["transitions"][0]
    assert (t["caught_to_surviving"], t["depart"], t["paired"]) == (0, 1, 3)
    assert f"depart  L{_line(V1, 'dup-code', 0)} alpha dup-code  caught" \
        in text
    assert "CAUGHT -> SURVIVING" not in text
    assert (t["line_keys_shared"], t["line_down"]) == (1, 1)
    assert ("  line keys: 1 shared (caught 1 -> 0 among them; 1 caught -> "
            "surviving and 0 surviving -> caught by line); line key sets "
            "differ; different blobs, so a line key need not name one site"
            ) in text.splitlines()
    # The ablation shows what the scope decided here.
    assert summary["ablation_misattributed"] == 1
    assert summary["ablation_totals"]["down"] == 1


def test_a_scope_dropping_change_to_the_sweeps_key_changes_the_output(
        tmp_path, monkeypatch):
    """Requirement 5, where it runs anywhere: mutate the sweep's
    site_identities() so that it drops the enclosing scope, and the
    reconciliation must change as the ablation predicts. beta's copy takes
    alpha's ordinal, so a caught -> surviving fall appears that never
    happened, beta's old key departs as a survivor, and the ablation, now
    comparing the key with itself, finds nothing to misattribute."""
    r = _dup_repo(tmp_path / "r")
    _, _, before = _reconciled(r.root)
    mutant = _load(_scopeless_sweep(tmp_path), "_reconcile_scopeless_sweep")
    monkeypatch.setattr(rec._sweep, "site_identities",
                        mutant.site_identities)
    _, text, after = _reconciled(r.root)
    tb, ta = before["transitions"][0], after["transitions"][0]
    assert (tb["caught_to_surviving"], tb["depart_survivors"]) == (0, 0)
    assert (ta["caught_to_surviving"], ta["depart_survivors"]) == (1, 1)
    assert (f"    CAUGHT -> SURVIVING  L{_line(V1, 'dup-code', 0)} <module> "
            f"dup-code -> L{_line(V2, 'dup-code', 0)}") in text.splitlines()
    assert (before["ablation_misattributed"],
            after["ablation_misattributed"]) == (1, 0)


# --------------------------------------------------------------------------
# FULL ROWS, and no "same run"


def test_rows_are_compared_in_full_not_as_line_to_caught(tmp_path):
    """Two files on one blob with the same verdicts, differing in one
    detector and one reason. {line: caught}, the old script's criterion for
    "the same run under two names", sees two equal files; the report must
    name both rows and both fields, and nothing it prints may call them one
    run (checked by _reconciled)."""
    r = Repo(tmp_path / "r")
    base = _rows(V1, {})
    other = _rows(V1, {("alpha-code", 0): {"how": "sweep:tamper-x"},
                       ("beta-code", 0): {"reason": 'f.append("beta-code")'}})
    assert {x["line"]: x["caught"] for x in base} == \
        {x["line"]: x["caught"] for x in other}
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(base),
              "paper/mutation_b.json": _archive(other, header=False)})
    archives, text, summary = _reconciled(r.root)
    t = summary["transitions"][0]
    assert t["same_key_set"] and t["caught_to_surviving"] == 0
    assert t["rows_differ_same_verdict"] == 2
    assert ("same key set and verdicts; 2 rows differ: "
            "1 in the detector (how), 1 in reason") in text
    assert f"L{_line(V1, 'alpha-code')}" in text and "'sweep:tamper-x'" in text
    assert "= 2 identical + 0 verdict flips (0 up, 0 down) + 2 other" in text


def test_identical_files_are_still_not_called_the_same_run(tmp_path):
    r = Repo(tmp_path / "r")
    rows = _archive(_rows(V1, {}))
    r.commit({"vac/verify.py": V1, "paper/mutation_a.json": rows,
              "paper/mutation_b.json": rows})
    _, text, _ = _reconciled(r.root)
    assert "same run" not in text
    assert "every row identical in verdict, detector and reason" in text


def test_the_one_run_check_is_live():
    """The sentence check itself must fail on what it is there to stop: the
    old label, and a synonym for it."""
    for bad in ("  mutation_a.json and mutation_b.json are the same run under "
                "two names",
                "  mutation_a.json and mutation_b.json are one sweep recorded "
                "twice"):
        with pytest.raises(AssertionError):
            _assert_known_sentences(bad)


def test_the_assumption_is_printed_first_and_last(tmp_path, capsys):
    """Requirement: the assumption is stated in the output, not only in the
    docstring. It opens and closes the full report and opens --pair."""
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(_rows(V1, {})),
              "paper/mutation_b.json": _archive(_rows(V1, {}))})
    _, text = _run(r.root, capsys=capsys)
    lines = text.splitlines()
    assert lines[3] == ASSUMPTION_TEXT and lines[-1] == ASSUMPTION_TEXT
    _, text = _run(r.root, "--pair", "a", "b", capsys=capsys)
    assert text.splitlines()[0] == ASSUMPTION_TEXT
    assert "THE ASSUMPTION every keying here rests on" in rec.__doc__


def test_the_pair_option_joins_the_files_in_the_order_given(tmp_path,
                                                            capsys):
    """a has one survivor that b catches. --pair a b must report it as
    surviving -> caught and count a's survivors; --pair b a, the reverse.
    Names and labels are both accepted."""
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(
                  _rows(V1, {("beta-code", 0): False})),
              "paper/mutation_b.json": _archive(_rows(V1, {}))})
    code, text = _run(r.root, "--pair", "mutation_a.json", "b",
                      capsys=capsys)
    lines = text.splitlines()
    assert code == 0
    assert re.fullmatch(r"a -> b   \[mutation_a\.json -> mutation_b\.json\]"
                        r"   blob \w{7} -> \w{7}", lines[2])
    assert "  verdict flips: 0 caught -> surviving, 1 surviving -> caught" \
        in lines
    assert ("  a's 1 survivors, by scope: caught in b / still surviving / not "
            "in b") in lines
    code, text = _run(r.root, "--pair", "b", "a", capsys=capsys)
    assert code == 0
    assert "  verdict flips: 1 caught -> surviving, 0 surviving -> caught" \
        in text.splitlines()
    assert text.splitlines()[2].startswith("b -> a   ")


def test_a_copy_of_the_archives_is_ordered_by_the_repository(tmp_path,
                                                              capsys):
    """--archives names a directory outside the repository, as a copy for an
    injected defect would be. Each file is still placed by where its name was
    added in the repository, and the copy's difference from HEAD is shown."""
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_b.json": _archive(_rows(V1, {}))})
    r.commit({"paper/mutation_a.json": _archive(_rows(V1, {}))})
    copy = tmp_path / "copy"
    shutil.copytree(r.root / "paper", copy)
    (copy / "mutation_a.json").write_text(
        _archive(_rows(V1, {("beta-code", 0): False})))
    code, text = _run(r.root, "--archives", str(copy), "--json",
                      str(tmp_path / "s.json"), capsys=capsys)
    summary = json.loads((tmp_path / "s.json").read_text())
    assert code == 0
    assert [(t["from"], t["to"]) for t in summary["transitions"]] == \
        [("mutation_b.json", "mutation_a.json")]
    assert summary["down"] == 1
    assert re.search(r"mutation_a\.json\s+\w{7} .*DIFFERS FROM HEAD", text)


# --------------------------------------------------------------------------
# a fall is reported wherever the site went


def test_a_caught_site_that_stops_being_caught_is_reported(tmp_path):
    """beta-code moves from one line to another and stops being caught. The
    line key shares no line with it; the content key must find it."""
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1,
              "paper/mutation_a.json": _archive(_rows(V1, {}))})
    r.commit({"vac/verify.py": V2,
              "paper/mutation_b.json": _archive(
                  _rows(V2, {("beta-code", 0): False}))})
    _, text, summary = _reconciled(r.root)
    assert summary["down"] == 1
    assert summary["transitions"][0]["caught_to_surviving"] == 1
    assert (f"CAUGHT -> SURVIVING  L{_line(V1, 'beta-code')} beta beta-code "
            f"-> L{_line(V2, 'beta-code')}") in text


# --------------------------------------------------------------------------
# the tiebreak: what rests on it, and what does not


def test_a_fall_that_needs_no_tiebreak_is_not_called_order_dependent(
        tmp_path):
    """a (V1) -> b (V2) loses beta-code, across an edit of verify.py; c1 and
    c2 share a commit. b follows a in both within-commit orders, so that
    fall must be reported as in every order and not resting on the
    tiebreak, and listed as a fall between different blobs. The falls among
    b, c1 and c2 appear in one order each, and must say so."""
    r = Repo(tmp_path / "r")
    r.commit({"vac/verify.py": V1, "tools/mutation_sweep.py": SWEEP_NONE,
              "paper/mutation_a.json": _archive(_rows(V1, {}))})
    r.commit({"vac/verify.py": V2,
              "paper/mutation_b.json": _archive(
                  _rows(V2, {("beta-code", 0): False}))})
    r.commit({"paper/mutation_c1.json": _archive(
                  _rows(V2, {("beta-code", 0): False})),
              "paper/mutation_c2.json": _archive(
                  _rows(V2, {("alpha-code", 0): False,
                             ("dup-code", 0): False}))})
    _, text, summary = _reconciled(r.root)
    lines = text.splitlines()
    tb = summary["tiebreak"]
    assert (tb["orders"], tb["no_fall_orders"], tb["name_order_falls"]) == \
        (2, 0, 3)
    assert tb["cross_blob_falls"] == ["a -> b"]
    assert tb["fall_orders"] == {"a -> b": 2, "b -> c2": 1, "c1 -> c2": 1,
                                 "c2 -> c1": 1}
    assert ("  a -> b: 1 caught -> surviving, in every one of the 2 orders, "
            "since b always follows a, so it does not rest on the tiebreak; "
            "DIFFERENT BLOBS") in lines
    assert ("  c1 -> c2: 2 caught -> surviving, only in the 1 of 2 orders "
            "that place c2 right after c1; one blob") in lines
    assert "  falls between different blobs, under any order: a -> b" in lines
    assert not any("only" in ln and "a -> b" in ln for ln in lines)
    assert ("  The name order gives 3 caught -> surviving over 3 transitions; "
            "0 of the 2 orders give 0.") in lines
    assert ("That 3 caught -> surviving holds for the name-order tiebreak; 0 "
            "of the 2 within-commit orders give 0 (see the tiebreak "
            "section).") in lines


def test_a_zero_that_rests_on_the_tiebreak_says_so_with_its_evidence(
        tmp_path):
    """p and q share a commit; q catches the site p missed. The name order
    (p, q) gives no fall, and the other order gives one, so the output must
    say the zero rests on the tiebreak, which order the name order is, and
    what outside the rows bears on it: the scores the commit message quotes
    that equal a file's own, and the files' mtimes, earliest first."""
    msg = ("Two sweeps\n\nThe first came back 0.750 against the floor.\n"
           "Covered, now 4/4 = 1.000.\n")
    r = Repo(tmp_path / "r")
    c = r.sha(r.commit({
        "vac/verify.py": V1, "tools/mutation_sweep.py": SWEEP_NONE,
        "paper/mutation_p.json": _archive(
            _rows(V1, {("beta-code", 0): False})),
        "paper/mutation_q.json": _archive(_rows(V1, {}))}, msg=msg))
    # q's file is older than p's here, so the mtime line must put q first.
    os.utime(r.root / "paper" / "mutation_p.json", (_T0 + 7200, _T0 + 7200))
    os.utime(r.root / "paper" / "mutation_q.json", (_T0 + 3600, _T0 + 3600))
    _, text, summary = _reconciled(r.root)
    lines = text.splitlines()

    def stamp(t):
        return time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(t))

    assert ("That 0 caught -> surviving holds for the name-order tiebreak; 1 "
            "of the 2 within-commit orders gives 0 (see the tiebreak "
            "section).") in lines
    assert ("  q -> p: 1 caught -> surviving, only in the 1 of 2 orders that "
            "place p right after q; one blob") in lines
    assert ("  THE ZERO RESTS ON THE TIEBREAK. The name order gives 0 caught "
            "-> surviving over 1 transitions, and 1 of the 2 orders gives 0. "
            "It puts p before q; an order that places p right after q shows 1 "
            "fall.") in lines
    assert (f"    {c[:7]} (p, q): its message quotes 0.750 (p 3/4); 4/4 (q); "
            "1.000 (q 4/4)") in lines
    assert '      "The first came back 0.750 against the floor."' in lines
    assert '      "Covered, now 4/4 = 1.000."' in lines
    assert (f"    {c[:7]} file mtimes, earliest first: q {stamp(_T0 + 3600)}; "
            f"p {stamp(_T0 + 7200)}") in lines
    assert summary["tiebreak"]["evidence"][c[:7]]["quoted"] == \
        [["0.750", ["p"]], ["4/4", ["q"]], ["1.000", ["q"]]]


def test_the_docstring_states_what_the_zero_rests_on():
    doc = " ".join(rec.__doc__.split())
    for claim in ("THE HEADLINE ZERO RESTS ON THE TIEBREAK",
                  "the name order gives 0 caught -> surviving in 11 "
                  "transitions",
                  "puts v5 before v6 (both introduced by f6e32fd) and v7 "
                  "before v8 (both introduced by ba14203)",
                  "Of the 24 orders of the files within their introducing "
                  "commits, 6 give 0",
                  "mutation_v5.json's mtime is 2026-08-16 01:57:04 and "
                  "mutation_v6.json's is 02:03:38",
                  '"came back 0.972"', "0.972 is v7's 139/143"):
        assert claim in doc, claim


# --------------------------------------------------------------------------
# this repository's own history and archives


def _why_no_history() -> str | None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    r = subprocess.run(["git", "--no-optional-locks", "-C", str(REPO),
                        "rev-parse", "--show-toplevel",
                        "--is-shallow-repository"],
                       capture_output=True, text=True, env=env)
    out = r.stdout.split("\n")
    # git -C walks upward: a tree that is not a checkout but sits inside one
    # would otherwise be answered for by the enclosing repository.
    if r.returncode or pathlib.Path(out[0]).resolve() != REPO:
        return "not a git checkout, so the archives' history is not here"
    if out[1].strip() == "true":
        return ("a shallow clone: the archives' introducing commits and the "
                "verify.py blobs they match are not here")
    return None


_NO_HISTORY = _why_no_history()
history = pytest.mark.skipif(_NO_HISTORY is not None,
                             reason=_NO_HISTORY or "")


def test_history_is_present_when_required():
    """The history tests skip without the full history. Where a job means
    to run them (CI's test job, with fetch-depth: 0), it sets
    VAC_REQUIRE_GIT_HISTORY=1, and a missing history is then a failure
    here rather than eleven quiet skips."""
    if os.environ.get("VAC_REQUIRE_GIT_HISTORY") == "1":
        assert _NO_HISTORY is None, _NO_HISTORY


@pytest.fixture(scope="module")
def real():
    hist, archives = rec.reconcile(REPO, REPO / "paper", "paper")
    lines, summary = rec.report(hist, archives)
    return hist, archives, "\n".join(lines), summary


# V2-36's table of introducing commits, and V2-33's table of blobs.
EXPECTED = [
    ("mutation.json", "6b6f96f", "e99745d"),
    ("mutation_after.json", "6b6f96f", "168bb37"),
    ("mutation_gated.json", "6b6f96f", "168bb37"),
    ("mutation_covered.json", "6c3a2c8", "168bb37"),
    ("mutation_final.json", "5c2e049", "80a28ca"),
    ("mutation_v2.json", "2484484", "9fcb82d"),
    ("mutation_v3.json", "bfc9642", "f595841"),
    ("mutation_final2.json", "1674f4c", "df110fc"),
    ("mutation_v5.json", "f6e32fd", "df110fc"),
    ("mutation_v6.json", "f6e32fd", "df110fc"),
    ("mutation_v7.json", "ba14203", "efedc37"),
    ("mutation_v8.json", "ba14203", "efedc37"),
]
assert [n for n, _, _ in EXPECTED] == REAL_NAMES

# V2-35's table: (paired, caught before, caught after among paired, arrive,
# caught on arrival, depart, departing survivors, caught -> surviving,
# surviving -> caught, same-verdict rows that differ).
TRANSITIONS = {
    ("base", "after"): (112, 37, 37, 7, 2, 0, 0, 0, 0, 0),
    ("after", "gated"): (119, 39, 39, 0, 0, 0, 0, 0, 0, 3),
    ("gated", "covered"): (119, 39, 112, 0, 0, 0, 0, 0, 73, 0),
    ("covered", "final"): (117, 112, 112, 0, 0, 2, 2, 0, 0, 0),
    ("final", "v2"): (117, 112, 112, 8, 8, 0, 0, 0, 0, 0),
    ("v2", "v3"): (125, 120, 120, 4, 3, 0, 0, 0, 0, 0),
    ("v3", "final2"): (129, 123, 123, 4, 3, 0, 0, 0, 0, 0),
    ("final2", "v5"): (131, 126, 130, 0, 0, 2, 2, 0, 4, 0),
    ("v5", "v6"): (131, 130, 131, 0, 0, 0, 0, 0, 1, 0),
    ("v6", "v7"): (131, 131, 131, 12, 8, 0, 0, 0, 0, 0),
    ("v7", "v8"): (143, 139, 143, 0, 0, 0, 0, 0, 4, 0),
}


def _t(summary, a, b):
    for t in summary["transitions"]:
        if (rec.label(t["from"]), rec.label(t["to"])) == (a, b):
            return t
    raise AssertionError(f"no transition {a} -> {b}")


@history
def test_real_order_is_introduction_order(real):
    _, archives, _, _ = real
    assert [(a.name, a.commit[:7]) for a in archives] == \
        [(n, c) for n, c, _ in EXPECTED]


@history
def test_real_files_each_match_exactly_one_blob(real):
    _, archives, _, summary = real
    assert summary["unkeyed"] == []
    assert (summary["header_disagrees"], summary["recorded_key_differs"],
            summary["measured_sha256_differs"]) == ([], [], [])
    assert [(a.name, a.blob.oid[:7]) for a in archives] == \
        [(n, b) for n, _, b in EXPECTED]
    # Each row's reason matches its source line, except two bare codes in
    # the two files an earlier, colon-less sweep wrote.
    mism = {a.label: [n for n, _, _ in a.reason_mismatch] for a in archives
            if a.reason_mismatch}
    assert mism == {"base": [124, 185], "after": [124, 185]}


@history
def test_real_transitions_reproduce_the_ledger(real):
    _, _, _, summary = real
    got = {}
    for t in summary["transitions"]:
        got[(rec.label(t["from"]), rec.label(t["to"]))] = (
            t["paired"], t["caught_before"], t["caught_after"], t["arrive"],
            t["arrive_caught"], t["depart"], t["depart_survivors"],
            t["caught_to_surviving"], t["surviving_to_caught"],
            t["rows_differ_same_verdict"])
    assert got == TRANSITIONS
    assert (summary["arrive"], summary["arrive_caught"], summary["depart"],
            summary["depart_survivors"], summary["down"]) == (35, 24, 4, 4, 0)


# after -> gated as the tool prints it, whole. The two files are named
# apart, and the three rows in which they differ are each printed.
AFTER_GATED = """\
after -> gated   [mutation_after.json -> mutation_gated.json]   blob 168bb37 -> 168bb37
  order: both files were introduced by 6b6f96f; name order puts after first
  content keys: 119 paired (caught 39 -> 39), 0 arrive (0 caught), 0 depart (0 survivors); key sets identical
  verdict flips: 0 caught -> surviving, 0 surviving -> caught
  same key set and verdicts; 3 rows differ: 2 in reason, 1 in the detector (how)
    row differs  L124 -> L124 _validate_manifest: reason 'empty-limitations' -> 'f.append("empty-limitations")'
    row differs  L185 -> L185 _validate_manifest: reason 'missing-issuer-commit' -> 'f.append("missing-issuer-commit")'
    row differs  L1192 -> L1192 _coherence: how 'sweep:tamper-check-deleted' -> 'tests'
  line keys: 119 shared (caught 39 -> 39 among them; 0 caught -> surviving and 0 surviving -> caught by line); line key sets identical; same blob, so line keys are valid here
"""  # noqa: E501


@history
def test_real_after_and_gated_differ_in_three_named_rows(real):
    """Requirement 3, the corrected output: after -> gated is printed whole,
    as above, and every line the tool prints is a known sentence, none of
    which says that two files are one run."""
    _, _, text, _ = real
    block = text.split("\nafter -> gated", 1)[1].split("\ngated -> covered")[0]
    assert "after -> gated" + block + "\n" == AFTER_GATED
    assert ("  after vs gated (blob 168bb37): 119 shared keys = 116 identical "
            "+ 0 verdict flips (0 up, 0 down) + 3 other; 0 keys in one only"
            ) in text.splitlines()
    _assert_known_sentences(text)


@history
def test_real_the_former_same_run_label_was_false(tmp_path, real):
    """Requirement 3, the regression: the committed script (fe4f1c8) says
    mutation_after.json and mutation_gated.json are the same run under two
    names. Read straight from the two files, with neither script, they
    differ in three rows: L124 and L185 in reason and L1192 in the
    detector. The label was false, and the new output names those rows."""
    old = tmp_path / "reconcile_fe4f1c8.py"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    old.write_bytes(subprocess.run(
        ["git", "--no-optional-locks", "-C", str(REPO), "show",
         "fe4f1c8:paper/reconcile_sweeps.py"],
        capture_output=True, env=env, check=True).stdout)
    said = subprocess.run([sys.executable, str(old), str(REPO / "paper")],
                          capture_output=True, text=True, check=True,
                          env=dict(env, PYTHONDONTWRITEBYTECODE="1")).stdout
    assert ("  mutation_after.json and mutation_gated.json are the same run "
            "under two names") in said.splitlines()

    def rows(name):
        d = json.loads((REPO / "paper" / name).read_text())
        return {r["line"]: r for r in (d["results"] if isinstance(d, dict)
                                       else d)}

    after, gated = rows("mutation_after.json"), rows("mutation_gated.json")
    assert set(after) == set(gated)
    assert all(after[n]["caught"] == gated[n]["caught"] for n in after)
    differ = sorted((n, f) for n in after for f in ("caught", "how", "reason")
                    if after[n][f] != gated[n][f])
    assert differ == [(124, "reason"), (185, "reason"), (1192, "how")]

    _, _, text, _ = real
    for n, f in differ:
        assert re.search(rf"^    row differs  L{n} -> L{n} \S+: {f} ", text,
                         re.M)


@history
def test_real_identical_key_sets_and_line_key_figures(real):
    _, _, text, summary = real
    same = [(rec.label(t["from"]), rec.label(t["to"]))
            for t in summary["transitions"] if t["same_key_set"]]
    assert same == [("after", "gated"), ("gated", "covered"), ("v5", "v6"),
                    ("v7", "v8")]
    assert (summary["identical_content"], summary["identical_lines"]) == (4, 4)
    assert summary["same_blob"] == 5
    # The 239e1ba figure: 17 -> 14 over 39 shared line keys, 3 of them down
    # by line, while the content key pairs all 112 and finds the same 37
    # caught.
    t = _t(summary, "base", "after")
    assert (t["line_keys_shared"], t["line_caught_before"],
            t["line_caught_after"], t["line_down"]) == (39, 17, 14, 3)
    assert (t["paired"], t["caught_before"], t["caught_after"]) == (112, 37, 37)
    assert ("  line keys: 39 shared (caught 17 -> 14 among them; 3 caught -> "
            "surviving and 0 surviving -> caught by line); line key sets "
            "differ; different blobs, so a line key need not name one site"
            ) in text.splitlines()
    # V2-34: one more line-key fall, 1 among 44 at v3 -> final2, and none
    # by content.
    t = _t(summary, "v3", "final2")
    assert (t["line_keys_shared"], t["line_down"],
            t["caught_to_surviving"]) == (44, 1, 0)
    assert sum(t["line_down"] for t in summary["transitions"]) == 4
    # V2-36: in introduction order covered -> final shares 87 line keys and
    # final -> v2 shares 3.
    assert _t(summary, "covered", "final")["line_keys_shared"] == 87
    assert _t(summary, "final", "v2")["line_keys_shared"] == 3


@history
def test_real_departures_say_deleted_or_excluded(real):
    _, _, text, _ = real
    assert "depart  L863 _check_modeldrift artifact-unparsable  SURVIVED  " \
           "(not in final's source" in text
    assert "depart  L990 _check_modeldrift artifact-unparsable  SURVIVED  " \
           "(excluded in final)" in text
    assert "depart  L325 _check_certlab artifact-unparsable  SURVIVED  " \
           "(excluded in v5)" in text
    assert "depart  L592 _check_evalmut artifact-unparsable  SURVIVED  " \
           "(excluded in v5)" in text


@history
def test_real_ablation_without_the_scope(real):
    """Without the scope, two sites pair with a twin in another function;
    the totals happen not to move. The ledger says one site; the committed
    blobs give two, one in each of two duplicated statements."""
    _, _, text, summary = real
    assert summary["ablation_misattributed"] == 2
    assert "v3 L554 (_check_evalmut) pairs with L592 (_check_evalmut) under " \
        "the site key and with L325 (_check_certlab)" in text
    assert "v6 L1235 (_check_modeldrift) pairs with L1364 " \
        "(_check_modeldrift) under the site key and with L1116 " \
        "(_check_rows_aggregate)" in text
    abl = summary["ablation_totals"]
    assert (abl["arrived"], abl["arrive_caught"], abl["departed"],
            abl["down"]) == (35, 24, 4, 0)


@history
def test_real_a_scope_dropping_sweep_key_misattributes_the_two_sites(
        tmp_path, real):
    """Requirement 5 on the real archives: put the tool beside a copy of
    tools/mutation_sweep.py whose site_identities() drops the enclosing
    scope, and reconcile this repository's history with it. The ledger
    (V2-35, as corrected) predicts two misattributions, and exactly those
    two pairings move: v3 L554 pairs with final2 L325 (certlab) instead of
    L592 (evalmut), and v6 L1235 with v7 L1116 (rows_aggregate) instead of
    L1364 (modeldrift). The totals do not move, and the mutant tool's own
    ablation finds nothing left to misattribute."""
    mutated = _scopeless_sweep(tmp_path)
    paper = mutated.parent.parent / "paper"
    paper.mkdir()
    shutil.copy2(TOOL, paper / TOOL.name)
    mut = _load(paper / TOOL.name, "_reconcile_with_scopeless_sweep")
    assert pathlib.Path(mut._sweep.__file__).resolve() == mutated.resolve()
    hist, archives = mut.reconcile(REPO, REPO / "paper", "paper")
    lines, summary = mut.report(hist, archives)

    _, real_archives, _, real_summary = real
    moved = []
    for (a, b), (ra, rb) in zip(zip(archives, archives[1:]),
                                zip(real_archives, real_archives[1:])):
        got = mut.compare(a, b)["partner"]
        want = rec.compare(ra, rb)["partner"]
        moved += [(a.label, b.label, n, want.get(n), got.get(n))
                  for n in sorted(set(got) | set(want))
                  if got.get(n) != want.get(n)]
    assert moved == [("v3", "final2", 554, 592, 325),
                     ("v6", "v7", 1235, 1364, 1116)]
    keys = ("arrive", "arrive_caught", "depart", "depart_survivors", "down",
            "up")
    assert [summary[k] for k in keys] == [real_summary[k] for k in keys] == \
        [35, 24, 4, 4, 0, 82]
    assert summary["ablation_misattributed"] == 0
    assert real_summary["ablation_misattributed"] == 2


@history
def test_real_tiebreak_sensitivity(real):
    """Name order within a commit is a convention. Under every order of the
    files within each introducing commit, a fall appears only between two
    files on one blob, when v6 is put before v5 or v8 before v7. No order
    shows a fall across an edit of verify.py."""
    _, _, _, summary = real
    t = summary["tiebreak"]
    assert (t["orders"], t["no_fall_orders"], t["name_order_no_fall"]) == \
        (24, 6, True)
    assert t["falls"] == ["v6 -> v5: 1", "v8 -> v7: 4"]
    assert t["fall_orders"] == {"v6 -> v5": 12, "v8 -> v7": 12}
    assert t["cross_blob_falls"] == []


@history
def test_real_headline_zero_names_its_tiebreak_and_its_evidence(real):
    """Where the output gives 0 caught -> surviving, it says that the zero
    holds for the name order (v5 before v6, v7 before v8), that 6 of the 24
    orders give it, and what outside the rows supports the name order. The
    commit messages are read from git and pinned here. The mtimes are the
    files' own, so only their form is pinned: in the tree the sweeps wrote
    they are 01:57:04 and 02:03:38 for v5 and v6, and in a checkout they are
    the checkout's."""
    _, _, text, _ = real
    lines = text.splitlines()
    for want in (
        "TOTAL over 11 transitions: 35 arrive, 24 caught on arrival; 4 "
        "depart, 4 of them survivors; 0 caught -> surviving; 82 surviving -> "
        "caught.",
        "That 0 caught -> surviving holds for the name-order tiebreak; 6 of "
        "the 24 within-commit orders give 0 (see the tiebreak section).",
        "  24 orders; 6 show no site going from caught to surviving, the "
        "name order among them",
        "  v6 -> v5: 1 caught -> surviving, only in the 12 of 24 orders that "
        "place v5 right after v6; one blob",
        "  v8 -> v7: 4 caught -> surviving, only in the 12 of 24 orders that "
        "place v7 right after v8; one blob",
        "  falls between different blobs, under any order: none",
        "  THE ZERO RESTS ON THE TIEBREAK. The name order gives 0 caught -> "
        "surviving over 11 transitions, and 6 of the 24 orders give 0. It "
        "puts v5 before v6 and v7 before v8; an order that places v5 right "
        "after v6 shows 1 fall, and one that places v7 right after v8 shows "
        "4 falls.",
        "    ba14203 (v7, v8): its message quotes 0.972 (v7 139/143); 143/143 "
        "(v8); 1.000 (v8 143/143)",
        '      "schema-violations and the run came back 0.972 against the '
        '0.990 floor. Covered,"',
        "    f6e32fd (v5, v6): its message quotes 1.000 (v6 131/131); 131/131 "
        "(v6); 1.000 (v6 131/131)",
    ):
        assert want in lines, want
    assert re.search(r"^    f6e32fd file mtimes, earliest first: \S", text,
                     re.M)


@history
def test_real_keys_are_the_sweeps_keys(real):
    hist, archives, _, _ = real
    v8 = archives[-1]
    ids = sweep.site_identities(v8.blob.lines)
    assert set(v8.keyed) == {ids[r["line"] - 1]["key"] for r in v8.rows}


@history
def test_an_injected_fall_across_a_line_shift_is_reported(tmp_path, real):
    """Copy the twelve archives and make v7's _check_modeldrift
    summary-mismatch copy (L1364) a survivor. In v6 that site sits at L1235,
    and neither line appears in the other file, so no line key can see the
    fall. It is also a duplicated statement, so a key without the scope
    pairs it with the wrong copy and misses the fall too."""
    copy = tmp_path / "paper"
    copy.mkdir()
    for p in sorted((REPO / "paper").glob("mutation*.json")):
        shutil.copy2(p, copy / p.name)
    v7 = json.loads((copy / "mutation_v7.json").read_text())
    for row in v7["results"]:
        if row["line"] == 1364:
            assert row["caught"] and row["reason"] == "summary-mismatch"
            row.update(caught=False, how="SURVIVED")
    # Keep the header true to the rows, so the only change is the fall.
    v7["caught"] -= 1
    v7["score"] = round(v7["caught"] / v7["total"], 4)
    (copy / "mutation_v7.json").write_text(json.dumps(v7, indent=1))

    # The history is the module's; only the archives are the copy.
    hist = real[0]
    archives = rec.order(hist, rec.load_archives(copy, "paper"))
    rec.match(hist, archives)
    lines, summary = rec.report(hist, archives)
    text = "\n".join(lines)
    _assert_known_sentences(text)
    assert summary["unkeyed"] == []
    assert _t(summary, "v6", "v7")["caught_to_surviving"] == 1
    assert _t(summary, "v6", "v7")["line_down"] == 0
    assert summary["down"] == 1
    assert ("CAUGHT -> SURVIVING  L1235 _check_modeldrift summary-mismatch "
            "-> L1364") in text
    assert re.search(r"mutation_v7\.json\s+ba14203 .*DIFFERS FROM HEAD", text)
    assert text.count("DIFFERS FROM HEAD") == 1
    assert "DISAGREES WITH ROWS" not in text


@history
def test_real_pair_base_to_covered(real):
    """V2-32's join: with the verifier unchanged from 6b6f96f to 6c3a2c8,
    68 of the 75 baseline survivors are caught at covered and 7 remain."""
    _, archives, _, _ = real
    by = {a.label: a for a in archives}
    text = "\n".join(rec.pair_report(by["base"], by["covered"]))
    assert "verdict flips: 0 caught -> surviving, 68 surviving -> caught" \
        in text
    assert ("still surviving: L340->L351, L362->L373, L371->L382, "
            "L515->L533, L833->L863, L960->L990, L1127->L1179") in text
    _assert_known_sentences(text)
