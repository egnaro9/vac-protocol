#!/usr/bin/env python3
"""Reconcile the archived mutation sweeps site by site, keyed by content.

Every archived sweep in paper/ keys its rows by line number, and a line number
is not an identity: insert one line above a refusal and every site below it is
renamed. Compared by line, two archives agree only where their line keys
happen to coincide, and across an edit that shifts lines they show falls that
never happened. The 17 to 14 over 39 shared line keys behind the 239e1ba
correction is that kind of artifact.

This tool recovers identity after the fact, in three steps.

1. ORDER. Each archive file is placed by the commit that introduced it
   (`git log --diff-filter=A --no-renames` on its path, in HEAD's history),
   commits in topological order. A later edit of the file does not move it,
   and neither does a delete and re-add: the first add places it. Several
   files share one introducing commit (6b6f96f introduced three), and history
   cannot order those, so files from one commit are taken in name order. That
   tiebreak is a convention, not a measurement, so the output says which
   transitions rest on it and re-runs them under every order within each
   commit, to show where a result depends on it. The order used to be a
   hand-typed list. It paired files that were never adjacent, and nothing
   checked it. This file holds no archive name outside its docstrings.

2. MATCH. For every commit in HEAD's history, the vac/verify.py blob gives
   its refusal sites (lines matching the sweep's REFUSAL pattern), and that
   commit's tools/mutation_sweep.py gives the EXCLUDE fragments that were
   dropped from the denominator (none before the sweep existed). A file
   matches a blob when some commit's scored line set equals the file's row
   set exactly. A file that matches no blob, or more than one, is reported
   and left unkeyed rather than guessed at.

3. KEY. Each row is keyed by tools/mutation_sweep.py site_identities(), the
   same function the sweep now records in every row: innermost enclosing def
   or class, the statement with its whitespace normalised, and an ordinal
   among identical statements in that scope. It is imported, not copied, and
   looked up on the sweep module at each call, so the paper and the sweep
   cannot drift onto two definitions: change the sweep's key and this tool's
   output changes with it. Rows are then compared in full (verdict, detector
   and reason), not as {line: caught}.

THE ASSUMPTION every keying here rests on: each archive file measured a tree
whose vac/verify.py equals the blob it is matched to. The row set and the
reason codes are evidence for that. They do not prove it, and nothing in an
archive written before the sweep recorded the bytes it measured can. Where an
archive does carry that record (measured.source.sha256), or carries the site
key in its rows, the tool checks the match against it.

An archive's own record can contradict its rows or its match: a header whose
caught/total disagrees with the rows, a recorded site key that differs from
the recomputed one, a measured.source.sha256 that differs from the matched
blob. Each is printed, listed in the --json summary, and makes the exit code
1, as a file that matches no blob, or several, does.

Two files with the same key set and the same verdicts are not "the same run
under two names". The earlier version of this script printed that for
mutation_after.json and mutation_gated.json, which differ in three rows. The
rows that differ are printed instead.

THE HEADLINE ZERO RESTS ON THE TIEBREAK. Over the twelve archives this
repository holds, the name order gives 0 caught -> surviving in 11
transitions. That zero holds for the name-order tiebreak, which puts v5
before v6 (both introduced by f6e32fd) and v7 before v8 (both introduced by
ba14203). Of the 24 orders of the files within their introducing commits, 6
give 0: an order that places v5 right after v6 shows 1 fall (L1348), and one
that places v7 right after v8 shows 4. No order shows a fall between two
different verify.py blobs. The evidence for the name order is outside the
rows. In the tree the sweeps were written in, mutation_v5.json's mtime is
2026-08-16 01:57:04 and mutation_v6.json's is 02:03:38 (America/New_York).
ba14203's message says the run "came back 0.972" before four more tests
landed, and 0.972 is v7's 139/143; v8 is 143/143. The output prints the
count, the orders and this evidence, reading it from the data: each
introducing commit's message from git (the scores it quotes that equal a
file's own), and the mtimes from the files it reads. Git keeps no mtimes, so
in a checkout they are the checkout's, and say nothing about the order.

  python paper/reconcile_sweeps.py
  python paper/reconcile_sweeps.py --pair mutation.json mutation_covered.json
  python paper/reconcile_sweeps.py --archives DIR   # a copy of the archives

Exit 0 when every file is keyed and nothing contradicts it, 1 when a file is
unkeyed or contradicted, 2 when the run cannot start.

Read-only: it runs git rev-parse, rev-list, log, show, cat-file and
merge-base with optional locks off, and writes nothing. It needs the full
history; a shallow clone is refused rather than half-read.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import itertools
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
TOOL_REPO = HERE.parent
SWEEP = TOOL_REPO / "tools" / "mutation_sweep.py"
VERIFY_PATH = "vac/verify.py"
SWEEP_PATH = "tools/mutation_sweep.py"
ARCHIVE_GLOB = "mutation*.json"

ASSUMPTION = (
    "ASSUMPTION: every keying below assumes each archive file measured a "
    "tree whose vac/verify.py equals the blob it is matched to. The row set "
    "and the reason codes are evidence for that, not proof of it.")


def _load_sweep():
    """tools/mutation_sweep.py, loaded by path. It is not a package, and the
    point is to use its site_identities() and REFUSAL, not a copy of them."""
    spec = importlib.util.spec_from_file_location("_reconcile_sweep_key",
                                                  SWEEP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_sweep = _load_sweep()
if not hasattr(_sweep, "site_identities"):
    # A tree whose sweep predates the site key (V2-55) cannot run this tool,
    # and a copy of the key here would be the second definition it exists to
    # avoid.
    raise SystemExit(f"{SWEEP} has no site_identities(); this tool keys rows "
                     "with the sweep's own site key and needs a sweep that "
                     "defines it.")
# The key function is not bound to a name here. Blob.ids looks it up on the
# sweep module at each call, so the function that keys the rows is whatever
# the sweep defines, and a test that changes the sweep's function changes
# this tool's output.
REFUSAL = _sweep.REFUSAL

# The sweep derives a row's reason inline in its main(): the first
# `"code:` on the site's first line, else that line stripped and cut to 60.
# Mirrored here only to check each archived reason against its matched blob.
REASON = re.compile(r'"([a-z-]+):')

FIELDS = ("caught", "how", "reason")

# Summary keys that each list files whose keying is missing or contradicted
# by the file's own record. Any of them non-empty makes the exit code 1.
PROBLEMS = ("unkeyed", "header_disagrees", "recorded_key_differs",
            "measured_sha256_differs")


class ReconcileError(Exception):
    pass


# --------------------------------------------------------------------------
# git, read-only


def _git_env() -> dict[str, str]:
    # Inherited GIT_* variables are dropped: a hook that exports GIT_DIR would
    # otherwise answer every query below about a different repository.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def _git(repo: pathlib.Path, *args: str, stdin: bytes | None = None) -> bytes:
    r = subprocess.run(["git", "--no-optional-locks", "-C", str(repo),
                        "-c", "core.quotepath=off", *args],
                       input=stdin, capture_output=True, env=_git_env())
    if r.returncode:
        raise ReconcileError(f"git {' '.join(args)} failed in {repo}: "
                             + r.stderr.decode("utf-8", "replace").strip())
    return r.stdout


def _batch_check(repo: pathlib.Path, names: list[str]) -> list[str | None]:
    """Object id for each `rev:path` name, None where it does not exist."""
    if not names:
        return []
    out = _git(repo, "cat-file", "--batch-check",
               stdin=("\n".join(names) + "\n").encode()).decode().splitlines()
    ids = []
    for line in out:
        parts = line.split()
        ids.append(parts[0] if len(parts) == 3 and parts[1] == "blob"
                   else None)
    if len(ids) != len(names):
        raise ReconcileError("git cat-file --batch-check answered "
                             f"{len(ids)} of {len(names)} names")
    return ids


def _read_blobs(repo: pathlib.Path, oids: list[str]) -> dict[str, bytes]:
    if not oids:
        return {}
    data = _git(repo, "cat-file", "--batch",
                stdin=("\n".join(oids) + "\n").encode())
    out, pos = {}, 0
    for oid in oids:
        nl = data.index(b"\n", pos)
        header = data[pos:nl].split()
        if len(header) != 3:
            raise ReconcileError(f"cannot read blob {oid}")
        size = int(header[2])
        out[oid] = data[nl + 1:nl + 1 + size]
        pos = nl + 1 + size + 1
    return out


def blob_id(data: bytes) -> str:
    """The id git gives these bytes as a blob."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# --------------------------------------------------------------------------
# history: order, blobs, EXCLUDE


def exclude_fragments(sweep_source: str | None) -> tuple[str, ...]:
    """The EXCLUDE keys of one version of tools/mutation_sweep.py.

    Absent file or absent table means nothing was excluded. The table has
    been a dict of fragment -> reason and of fragment -> (count, reason);
    only the keys matter, because every version matched a fragment as a
    substring of the site's first line.
    """
    if sweep_source is None:
        return ()
    for node in ast.parse(sweep_source).body:
        target = value = None
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        if isinstance(target, ast.Name) and target.id == "EXCLUDE":
            table = ast.literal_eval(value)
            return tuple(table.keys() if isinstance(table, dict) else table)
    return ()


def refusal_pattern(sweep_source: str | None) -> str | None:
    """The REFUSAL regex source in one version of the sweep, if any."""
    if sweep_source is None:
        return None
    for node in ast.parse(sweep_source).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "REFUSAL"
                and isinstance(node.value, ast.Call) and node.value.args
                and isinstance(node.value.args[0], ast.Constant)):
            return node.value.args[0].value
    return None


class Blob:
    """One vac/verify.py blob: its refusal sites and their keys."""

    def __init__(self, oid: str, data: bytes):
        self.oid = oid
        self.sha256 = hashlib.sha256(data).hexdigest()
        self.lines = data.decode("utf-8").splitlines(keepends=True)
        self.raw = [i + 1 for i, ln in enumerate(self.lines)
                    if REFUSAL.match(ln)]
        self._ids = None

    def scored(self, fragments: tuple[str, ...]) -> frozenset[int]:
        return frozenset(n for n in self.raw
                         if not any(k in self.lines[n - 1] for k in fragments))

    @property
    def ids(self) -> dict[int, dict]:
        """1-based line -> site identity, from the sweep's own function."""
        if self._ids is None:
            ids = _sweep.site_identities(self.lines)
            self._ids = {i + 1: v for i, v in ids.items()}
        return self._ids

    def reason(self, line: int) -> str:
        text = self.lines[line - 1]
        m = REASON.search(text)
        return m.group(1) if m else text.strip()[:60]


class History:
    def __init__(self, repo: pathlib.Path):
        self.repo = repo
        top = _git(repo, "rev-parse", "--show-toplevel").decode().strip()
        if pathlib.Path(top).resolve() != pathlib.Path(repo).resolve():
            # git -C walks upward, so a directory that is not itself a
            # checkout would silently read whichever repository encloses it.
            raise ReconcileError(f"{repo} is not the top of a git checkout "
                                 f"(git answers for {top})")
        if _git(repo, "rev-parse",
                "--is-shallow-repository").decode().strip() == "true":
            raise ReconcileError(
                f"{repo} is a shallow clone. The introducing commits and the "
                "verify.py blobs this tool reads may not be here, and a "
                "missing one would look like a file that matches nothing. "
                "Fetch the full history first (git fetch --unshallow).")
        self.head = _git(repo, "rev-parse", "HEAD").decode().strip()
        self.commits = _git(repo, "rev-list", "--topo-order", "--reverse",
                            "HEAD").decode().split()
        self.position = {c: i for i, c in enumerate(self.commits)}
        names = [f"{c}:{p}" for c in self.commits
                 for p in (VERIFY_PATH, SWEEP_PATH)]
        ids = _batch_check(repo, names)
        self.verify_at = dict(zip(self.commits, ids[0::2]))
        self.sweep_at = dict(zip(self.commits, ids[1::2]))
        wanted = sorted({o for o in ids if o})
        raw = _read_blobs(repo, wanted)
        self.blobs = {o: Blob(o, raw[o]) for o in set(self.verify_at.values())
                      if o}
        sweeps = {o: raw[o].decode("utf-8")
                  for o in set(self.sweep_at.values()) if o}
        self.fragments = {o: exclude_fragments(src)
                          for o, src in sweeps.items()}
        self.patterns = {o: refusal_pattern(src) for o, src in sweeps.items()}

    def states(self):
        """(commit, verify blob, EXCLUDE fragments) for every commit that
        has a verify.py."""
        for c in self.commits:
            v = self.verify_at[c]
            if v:
                s = self.sweep_at[c]
                yield c, v, (self.fragments[s] if s else ())

    def introduced(self, paths: list[str]) -> dict[str, list[str]]:
        """path -> every commit in HEAD's history that added it, earliest
        first. One git log for all paths; --no-renames so that an add is an
        add whatever a user's diff.renames says."""
        out = _git(self.repo, "log", "--diff-filter=A", "--no-renames",
                   "--name-only", "--format=%x00%H", "HEAD", "--",
                   *paths).decode()
        added = defaultdict(list)
        for chunk in out.split("\0")[1:]:
            commit, *names = [ln for ln in chunk.split("\n") if ln]
            for name in names:
                added[name].append(commit)
        return {p: sorted(added.get(p, []), key=self.position.__getitem__)
                for p in paths}

    def is_ancestor(self, a: str, b: str) -> bool:
        r = subprocess.run(["git", "--no-optional-locks", "-C",
                            str(self.repo), "merge-base", "--is-ancestor",
                            a, b], capture_output=True, env=_git_env())
        return r.returncode == 0

    def dates(self, commits: list[str]) -> dict[str, str]:
        if not commits:
            return {}
        out = _git(self.repo, "show", "-s", "--format=%H %ci",
                   *commits).decode().splitlines()
        return {ln.split(" ", 1)[0]: ln.split(" ", 1)[1] for ln in out if ln}

    def message(self, commit: str) -> str:
        return _git(self.repo, "show", "-s", "--format=%B",
                    commit).decode("utf-8", "replace")


# --------------------------------------------------------------------------
# archives


def label(name: str) -> str:
    stem = name[:-5] if name.endswith(".json") else name
    stem = stem[len("mutation"):] if stem.startswith("mutation") else stem
    return stem.lstrip("_") or "base"


class Archive:
    def __init__(self, path: pathlib.Path, repo_path: str):
        self.path = path
        self.name = path.name
        self.label = label(path.name)
        self.repo_path = repo_path
        self.data = path.read_bytes()
        payload = json.loads(self.data)
        if isinstance(payload, dict):
            self.header = (payload.get("score"), payload.get("caught"),
                           payload.get("total"))
            self.rows = payload["results"]
            self.measured = payload.get("measured")
            self.format = "dict with header"
        else:
            self.header = None
            self.rows = payload
            self.measured = None
            self.format = "bare list"
        lines = [r["line"] for r in self.rows]
        if len(set(lines)) != len(lines):
            raise ReconcileError(f"{self.name}: a line appears in two rows")
        self.lineset = frozenset(lines)
        self.caught = sum(1 for r in self.rows if r["caught"])
        self.header_disagrees = (self.header is not None and
                                 (self.header[1], self.header[2]) !=
                                 (self.caught, len(self.rows)))
        # Filled by order() and match():
        self.commit = None
        self.readded = []
        self.candidates = {}
        self.blob = None
        self.match_commits = []
        self.keyed = None
        self.reason_mismatch = []
        self.recorded_key_mismatch = []
        self.measured_ok = None


def load_archives(archives: pathlib.Path, repo_dir: str) -> list[Archive]:
    files = sorted(archives.glob(ARCHIVE_GLOB))
    if not files:
        raise ReconcileError(f"no {ARCHIVE_GLOB} in {archives}")
    return [Archive(p, f"{repo_dir}/{p.name}" if repo_dir else p.name)
            for p in files]


def order(hist: History, archives: list[Archive]) -> list[Archive]:
    """Introduction order: the commit that added each file's path, then name
    order among files one commit added."""
    intros = hist.introduced([a.repo_path for a in archives])
    for a in archives:
        intro = intros[a.repo_path]
        if not intro:
            raise ReconcileError(
                f"{a.name}: {a.repo_path} was never added in HEAD's history, "
                "so it has no place in the order. Commit it first, or point "
                "--repo-dir at where it lives.")
        a.commit = intro[0]
        a.readded = intro[1:]
    return sorted(archives, key=lambda a: (hist.position[a.commit], a.name))


def match(hist: History, archives: list[Archive]) -> None:
    """Attach to each file the one blob whose scored sites equal its rows."""
    scored_memo = {}
    by_set = defaultdict(lambda: defaultdict(list))
    for c, v, frags in hist.states():
        key = (v, frags)
        if key not in scored_memo:
            scored_memo[key] = hist.blobs[v].scored(frags)
        by_set[scored_memo[key]][v].append(c)
    for a in archives:
        hits = by_set.get(a.lineset, {})
        a.candidates = dict(hits)
        if len(hits) == 1:
            (a.blob, a.match_commits), = ((hist.blobs[v], cs)
                                         for v, cs in hits.items())
            a.keyed = {}
            for r in a.rows:
                ident = a.blob.ids[r["line"]]
                a.keyed[ident["key"]] = dict(r, scope=ident["scope"],
                                             key=ident["key"])
            a.recorded_key_mismatch = [
                r["line"] for r in a.rows
                if "key" in r and r["key"] != a.blob.ids[r["line"]]["key"]]
            a.reason_mismatch = [
                (r["line"], r["reason"], a.blob.reason(r["line"]))
                for r in a.rows if r["reason"] != a.blob.reason(r["line"])]
            src = (a.measured or {}).get("source") or {}
            want = src.get("sha256")
            a.measured_ok = None if want is None else want == a.blob.sha256


# --------------------------------------------------------------------------
# comparison


def row_diff(ra: dict, rb: dict) -> list[str]:
    return [f for f in FIELDS if ra.get(f) != rb.get(f)]


def compare(a: Archive, b: Archive, keyfn=None) -> dict:
    """Join two keyed archives. keyfn, if given, re-keys each row from its
    blob and line (used only for the ablation); by default the rows are
    joined on site_identities() keys."""
    if keyfn is None:
        A, B = a.keyed, b.keyed
    else:
        ka, kb = keyfn(a.blob), keyfn(b.blob)
        A = {ka[r["line"]]: r for r in a.rows}
        B = {kb[r["line"]]: r for r in b.rows}
    paired = sorted(set(A) & set(B), key=lambda k: A[k]["line"])
    arrived = sorted(set(B) - set(A), key=lambda k: B[k]["line"])
    departed = sorted(set(A) - set(B), key=lambda k: A[k]["line"])
    down = [k for k in paired if A[k]["caught"] and not B[k]["caught"]]
    up = [k for k in paired if not A[k]["caught"] and B[k]["caught"]]
    other = [(k, row_diff(A[k], B[k])) for k in paired
             if A[k]["caught"] == B[k]["caught"] and row_diff(A[k], B[k])]
    b_raw = set(b.blob.ids[n]["key"] for n in b.blob.raw) \
        if keyfn is None else set(keyfn(b.blob).values())
    a_raw = set(a.blob.ids[n]["key"] for n in a.blob.raw) \
        if keyfn is None else set(keyfn(a.blob).values())
    return {
        "A": A, "B": B, "paired": paired, "arrived": arrived,
        "departed": departed, "down": down, "up": up, "other": other,
        "caught_a": sum(1 for k in paired if A[k]["caught"]),
        "caught_b": sum(1 for k in paired if B[k]["caught"]),
        "arrived_caught": sum(1 for k in arrived if B[k]["caught"]),
        "departed_survivors": sum(1 for k in departed
                                  if not A[k]["caught"]),
        # A departing key still among b's raw sites was excluded, not
        # deleted; an arriving key among a's raw sites was excluded in a and
        # is re-admitted, not new.
        "departed_excluded": {k for k in departed if k in b_raw},
        "arrived_unexcluded": {k for k in arrived if k in a_raw},
        "partner": {A[k]["line"]: B[k]["line"] for k in paired},
    }


def line_view(a: Archive, b: Archive) -> dict:
    A = {r["line"]: r for r in a.rows}
    B = {r["line"]: r for r in b.rows}
    shared = set(A) & set(B)
    return {
        "shared": len(shared),
        "caught_a": sum(1 for n in shared if A[n]["caught"]),
        "caught_b": sum(1 for n in shared if B[n]["caught"]),
        "down": sum(1 for n in shared if A[n]["caught"] and not B[n]["caught"]),
        "up": sum(1 for n in shared if not A[n]["caught"] and B[n]["caught"]),
        "identical": set(A) == set(B),
    }


def text_ordinal_key(blob: Blob) -> dict[int, str]:
    """ABLATION ONLY: statement text plus an ordinal over the whole file, no
    scope. Kept to show what the scope in the real key buys."""
    seen, out = defaultdict(int), {}
    for n in blob.raw:
        st = blob.ids[n]["statement"]
        out[n] = f"{st}#{seen[st]}"
        seen[st] += 1
    return out


def _v(row: dict) -> str:
    return "caught" if row["caught"] else "SURVIVED"


def _site(row: dict) -> str:
    return f"L{row['line']} {row.get('scope', '?')} {row['reason']}"


# --------------------------------------------------------------------------
# report


def describe(a: Archive, b: Archive, out: list[str], tie: bool = False) -> dict:
    j = compare(a, b)
    lv = line_view(a, b)
    head = (f"{a.label} -> {b.label}   [{a.name} -> {b.name}]   blob "
            f"{a.blob.oid[:7]} -> {b.blob.oid[:7]}")
    out.append(head)
    if tie:
        out.append("  order: both files were introduced by "
                   f"{a.commit[:7]}; name order puts {a.label} first")
    same_keys = set(j["A"]) == set(j["B"])
    out.append(f"  content keys: {len(j['paired'])} paired (caught "
               f"{j['caught_a']} -> {j['caught_b']}), {len(j['arrived'])} "
               f"arrive ({j['arrived_caught']} caught), {len(j['departed'])} "
               f"depart ({j['departed_survivors']} survivors); key sets "
               f"{'identical' if same_keys else 'differ'}")
    out.append(f"  verdict flips: {len(j['down'])} caught -> surviving, "
               f"{len(j['up'])} surviving -> caught")
    # Two files that agree on every key and verdict are still two files. The
    # earlier script called such a pair "the same run under two names" after
    # comparing {line: caught} alone, and the pair it named differs in three
    # rows. Say what agrees, and print what does not.
    if same_keys and not j["down"] and not j["up"]:
        n = len(j["other"])
        by_field = defaultdict(int)
        for _, fields in j["other"]:
            for f in fields:
                by_field[f] += 1
        what = ", ".join(
            f"{c} in {'the detector (how)' if f == 'how' else f}"
            for f, c in sorted(by_field.items(), key=lambda fc: -fc[1]))
        out.append(f"  same key set and verdicts; {n} row"
                   f"{' differs' if n == 1 else 's differ'}: {what}" if n else
                   "  same key set and verdicts; every row identical in "
                   "verdict, detector and reason")
    for k in j["down"]:
        ra, rb = j["A"][k], j["B"][k]
        out.append(f"    CAUGHT -> SURVIVING  {_site(ra)} -> L{rb['line']}")
    for k, fields in j["other"]:
        ra, rb = j["A"][k], j["B"][k]
        diffs = "; ".join(f"{f} {ra.get(f)!r} -> {rb.get(f)!r}"
                          for f in fields)
        out.append(f"    row differs  L{ra['line']} -> L{rb['line']} "
                   f"{ra['scope']}: {diffs}")
    for k in j["arrived"]:
        rb = j["B"][k]
        how = ("was excluded in " + a.label
               if k in j["arrived_unexcluded"] else "new in the source")
        out.append(f"    arrive  {_site(rb)}  {_v(rb)}  ({how})")
    for k in j["departed"]:
        ra = j["A"][k]
        how = ("excluded in " + b.label if k in j["departed_excluded"]
               else "not in " + b.label + "'s source: deleted, or its "
               "statement or scope changed")
        out.append(f"    depart  {_site(ra)}  {_v(ra)}  ({how})")
    # Line keys name the same site only when both files measured one blob.
    # Across blobs they are printed for comparison with the old figures, and
    # any fall they show is a candidate artifact, not a finding.
    same_blob = a.blob.oid == b.blob.oid
    out.append(f"  line keys: {lv['shared']} shared (caught {lv['caught_a']}"
               f" -> {lv['caught_b']} among them; {lv['down']} caught -> "
               f"surviving and {lv['up']} surviving -> caught by line); line "
               f"key sets {'identical' if lv['identical'] else 'differ'}; "
               + ("same blob, so line keys are valid here" if same_blob else
                  "different blobs, so a line key need not name one site"))
    j["line_view"] = lv
    j["same_keys"] = same_keys
    j["same_blob"] = same_blob
    return j


# A score as the sweep and its commit messages print one: a fraction
# (139/143) or three decimals (0.972).
SCORE_TOKEN = re.compile(r"\b(?:(?P<num>\d+)/(?P<den>\d+)|\d\.\d{3})\b")


def quoted_scores(message: str,
                  files: list[Archive]) -> list[tuple[str, list[Archive],
                                                      str]]:
    """The scores a commit message quotes that equal one of `files`' own
    score (caught/total, or that ratio to three places), in message order,
    each with the files it equals and the message line it is on. A number
    that equals no file's score is not reported."""
    found = []
    for line in message.splitlines():
        for m in SCORE_TOKEN.finditer(line):
            if m.group("num") is not None:
                want = (int(m.group("num")), int(m.group("den")))
                hit = [f for f in files if (f.caught, len(f.rows)) == want]
            else:
                hit = [f for f in files if f.rows and
                       f"{f.caught / len(f.rows):.3f}" == m.group(0)]
            if hit:
                found.append((m.group(0), hit, line.strip()))
    return found


def _mtimes(files: list[Archive]) -> list[tuple[str, list[Archive]]]:
    """The files' mtimes to the second, earliest first, files that share
    one grouped together."""
    by = defaultdict(list)
    for f in files:
        by[int(f.path.stat().st_mtime)].append(f)
    return [(time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(t)), fs)
            for t, fs in sorted(by.items())]


def _give(k: int) -> str:
    return "gives" if k == 1 else "give"


def _and(parts: list[str]) -> str:
    return (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1
            else "".join(parts))


def tiebreak_sensitivity(hist: History, archives: list[Archive],
                         out: list[str], cap: int = 5040) -> dict:
    """Re-run every transition under every order of the files within each
    introducing commit. Report each pair that shows a fall, in how many of
    the orders that pair is adjacent, and so whether the fall rests on the
    tiebreak at all; then what the count under the name order rests on, and
    the evidence for the name order that the data outside the rows holds."""
    groups = [list(g) for _, g in itertools.groupby(archives,
                                                     key=lambda x: x.commit)]
    n = 1
    for g in groups:
        for k in range(2, len(g) + 1):
            n *= k
    out.append("")
    out.append("== Sensitivity to the same-commit tiebreak: every order of the "
               "files within each introducing commit ==")
    if n > cap:
        out.append(f"  {n} orders, more than {cap}; not computed")
        return {"orders": n, "computed": False}
    by_name = {a.name: a for a in archives}
    pos = {a.name: i for i, a in enumerate(archives)}
    down, adjacent = {}, defaultdict(int)
    zero, name_down = 0, None
    for perms in itertools.product(*(itertools.permutations(g)
                                     for g in groups)):
        order = [x for p in perms for x in p]
        total = 0
        for a, b in zip(order, order[1:]):
            pair = (a.name, b.name)
            if pair not in down:
                down[pair] = len(compare(a, b)["down"])
            adjacent[pair] += 1
            total += down[pair]
        zero += total == 0
        if order == archives:
            name_down = total
    falls = sorted((p for p in adjacent if down[p]),
                   key=lambda p: (pos[p[0]], pos[p[1]]))
    T = len(archives) - 1
    out.append(f"  {n} orders; {zero} show no site going from caught to "
               "surviving" + (", the name order among them" if
                              name_down == 0 else ""))

    def lab(p):
        return by_name[p[0]].label, by_name[p[1]].label

    cross = []
    for p in falls:
        x, y = lab(p)
        one = by_name[p[0]].blob.oid == by_name[p[1]].blob.oid
        if not one:
            cross.append(f"{x} -> {y}")
        where = ("in the only order there is" if n == 1 else
                 f"in every one of the {n} orders, since {y} always follows "
                 f"{x}, so it does not rest on the tiebreak"
                 if adjacent[p] == n else
                 f"only in the {adjacent[p]} of {n} orders that place {y} "
                 f"right after {x}")
        out.append(f"  {x} -> {y}: {down[p]} caught -> surviving, {where}; "
                   + ("one blob" if one else "DIFFERENT BLOBS"))
    out.append("  falls between different blobs, under any order: "
               + (", ".join(sorted(cross)) if cross else "none"))

    # What the count under the name order rests on, said where it is read.
    if not falls:
        out.append("  No order shows a site going from caught to surviving, "
                   "so that count does not rest on the tiebreak.")
    elif name_down == 0:
        needs, shows = [], []
        for p in falls:
            x, y = lab(p)
            needs.append(f"{y} before {x}" if pos[p[1]] < pos[p[0]] else
                         f"{y} not right after {x}")
            shows.append(f"places {y} right after {x} shows {down[p]} "
                         + ("fall" if down[p] == 1 else "falls"))
        out.append(f"  THE ZERO RESTS ON THE TIEBREAK. The name order gives 0 "
                   f"caught -> surviving over {T} transitions, and {zero} of "
                   f"the {n} orders {_give(zero)} 0. It puts "
                   f"{_and(needs)}; an order that "
                   + ", and one that ".join(shows) + ".")
    else:
        out.append(f"  The name order gives {name_down} caught -> surviving "
                   f"over {T} transitions; {zero} of the {n} orders "
                   f"{_give(zero)} 0.")

    # The name order is a convention; say what outside the rows bears on it.
    evidence = {}
    ties = [g for g in groups if len(g) > 1]
    if ties:
        out.append("  Evidence for the order within each commit, from outside "
                   "the rows:")
    for g in ties:
        c = g[0].commit[:7]
        labels = ", ".join(f.label for f in g)
        q = quoted_scores(hist.message(g[0].commit), g)
        if q:
            out.append(f"    {c} ({labels}): its message quotes " + "; ".join(
                f"{tok} (" + ", ".join(
                    f.label if "/" in tok else
                    f"{f.label} {f.caught}/{len(f.rows)}" for f in hit) + ")"
                for tok, hit, _ in q))
            seen = []
            for _, _, line in q:
                if line not in seen:
                    seen.append(line)
                    out.append(f'      "{line}"')
        else:
            out.append(f"    {c} ({labels}): its message quotes no score "
                       "that any of these files has")
        mt = _mtimes(g)
        out.append(f"    {c} file mtimes, earliest first: " + "; ".join(
            f"{', '.join(f.label for f in fs)} {t}" for t, fs in mt))
        evidence[c] = {
            "quoted": [[tok, [f.label for f in hit]] for tok, hit, _ in q],
            "mtimes": [[t, [f.label for f in fs]] for t, fs in mt]}
    if ties:
        out.append("  (Messages are read from git. Mtimes are read from the "
                   "files read here: they say when a sweep wrote its file "
                   "only in the tree it wrote it in, and a checkout stamps "
                   "its own.)")
    return {"orders": n, "computed": True, "no_fall_orders": zero,
            "name_order_no_fall": name_down == 0,
            "name_order_falls": name_down,
            "falls": sorted(f"{x} -> {y}: {down[p]}"
                            for p in falls for x, y in [lab(p)]),
            "fall_orders": {"{} -> {}".format(*lab(p)): adjacent[p]
                            for p in falls},
            "cross_blob_falls": sorted(cross),
            "evidence": evidence}


def reconcile(repo: pathlib.Path, archives_dir: pathlib.Path,
              repo_dir: str) -> tuple[History, list[Archive]]:
    hist = History(repo)
    archives = order(hist, load_archives(archives_dir, repo_dir))
    match(hist, archives)
    return hist, archives


def report(hist: History, archives: list[Archive]) -> tuple[list[str], dict]:
    out: list[str] = []
    out.append(f"Reconciling {len(archives)} archived sweeps against the "
               f"history of HEAD {hist.head[:7]} ({len(hist.commits)} "
               "commits).")
    out.append("Site key: site_identities() imported from "
               "tools/mutation_sweep.py (enclosing scope, normalised "
               "statement, ordinal).")
    # The site population is defined by the sweep's REFUSAL today. If a
    # committed version of the sweep had used another pattern, the files it
    # wrote would have a different population, and this says so.
    pats = sorted({p for p in hist.patterns.values() if p is not None})
    out.append(f"REFUSAL: {REFUSAL.pattern!r}, " + (
        "and no committed version of the sweep is in this history"
        if not pats else
        "the same in every committed version of the sweep that defines it"
        if pats == [REFUSAL.pattern] else
        f"BUT committed versions of the sweep use {pats}"))
    out.append(ASSUMPTION)

    out.append("")
    out.append("== Order: introducing commit (git log --diff-filter=A "
               "--no-renames), then name order within one commit ==")
    dates = hist.dates(sorted({a.commit for a in archives}))
    at_head_ids = _batch_check(hist.repo,
                               [f"HEAD:{a.repo_path}" for a in archives])
    for i, (a, head) in enumerate(zip(archives, at_head_ids), 1):
        at_head = ("equals HEAD" if head == blob_id(a.data) else
                   "not at HEAD" if head is None else "DIFFERS FROM HEAD")
        extra = (f"; re-added at {', '.join(c[:7] for c in a.readded)}"
                 if a.readded else "")
        out.append(f"  {i:2d}  {a.label:7s} {a.name:24s} {a.commit[:7]}  "
                   f"{dates[a.commit]}  ({at_head}{extra})")
    for a, b in zip(archives, archives[1:]):
        if a.commit != b.commit and not hist.is_ancestor(a.commit, b.commit):
            out.append(f"  NOTE: {a.commit[:7]} is not an ancestor of "
                       f"{b.commit[:7]}; {a.label} -> {b.label} is ordered "
                       "by topology, not by descent")

    out.append("")
    out.append("== Each file's vac/verify.py blob: the commits whose "
               "refusal sites minus that commit's EXCLUDE equal the rows ==")
    unkeyed = []
    for a in archives:
        hdr = ("no header" if a.header is None else
               f"header {a.header[1]}/{a.header[2]}"
               + (" DISAGREES WITH ROWS" if a.header_disagrees else ""))
        base = (f"  {a.label:7s} {a.caught}/{len(a.rows)} ({hdr}, "
                f"{a.format})")
        if len(a.candidates) != 1:
            unkeyed.append(a)
            what = ("matches NO committed blob" if not a.candidates else
                    "matches SEVERAL blobs: "
                    + ", ".join(v[:7] for v in a.candidates))
            out.append(f"{base}: {what}; left unkeyed")
            continue
        excl = len(a.blob.raw) - len(a.rows)
        cs = a.match_commits
        which = (cs[0][:7] if len(cs) == 1 else
                 f"{len(cs)} commits, first {cs[0][:7]}, last {cs[-1][:7]}")
        own = ("its introducing commit is one of them"
               if a.commit in cs else
               f"NOT its introducing commit {a.commit[:7]}")
        out.append(f"{base}: blob {a.blob.oid[:7]}, {len(a.blob.raw)} raw "
                   f"sites, {excl} excluded")
        out.append(f"          rows equal the scored sites at {which}; "
                   f"{own}")
        if a.reason_mismatch:
            out.append("          reasons that differ from the source line: "
                       + "; ".join(f"L{n} row {r!r}, source {s!r}"
                                   for n, r, s in a.reason_mismatch))
        if a.recorded_key_mismatch:
            out.append("          RECORDED SITE KEY DIFFERS at "
                       + ", ".join(f"L{n}" for n in a.recorded_key_mismatch))
        if a.measured_ok is False:
            out.append("          MEASURED SHA256 DIFFERS from the matched "
                       "blob")
        elif a.measured_ok:
            out.append("          measured.source.sha256 equals the matched "
                       "blob")

    # File names under their own keys: the transition counts below go into
    # the same summary, and a count must not land on a list of names.
    summary = {
        "transitions": [],
        "unkeyed": [a.name for a in unkeyed],
        "header_disagrees": [a.name for a in archives if a.header_disagrees],
        "recorded_key_differs": [a.name for a in archives
                                 if a.recorded_key_mismatch],
        "measured_sha256_differs": [a.name for a in archives
                                    if a.measured_ok is False],
    }
    out.append("")
    out.append(f"== Transitions, in introduction order ({len(archives) - 1}) "
               "==")
    tot = defaultdict(int)
    identical_content = identical_lines = 0
    ties = unkeyed_transitions = 0
    for a, b in zip(archives, archives[1:]):
        if a.keyed is None or b.keyed is None:
            out.append(f"{a.label} -> {b.label}: NOT KEYED (a file has no "
                       "unique blob)")
            unkeyed_transitions += 1
            continue
        tie = a.commit == b.commit
        ties += tie
        j = describe(a, b, out, tie=tie)
        tot["paired"] += len(j["paired"])
        tot["arrive"] += len(j["arrived"])
        tot["arrive_caught"] += j["arrived_caught"]
        tot["depart"] += len(j["departed"])
        tot["depart_survivors"] += j["departed_survivors"]
        tot["down"] += len(j["down"])
        tot["up"] += len(j["up"])
        identical_content += j["same_keys"]
        identical_lines += j["line_view"]["identical"]
        tot["same_blob"] += j["same_blob"]
        summary["transitions"].append({
            "from": a.name, "to": b.name, "paired": len(j["paired"]),
            "caught_before": j["caught_a"], "caught_after": j["caught_b"],
            "arrive": len(j["arrived"]), "arrive_caught": j["arrived_caught"],
            "arrive_readmitted": len(j["arrived_unexcluded"]),
            "depart": len(j["departed"]),
            "depart_excluded": len(j["departed_excluded"]),
            "depart_survivors": j["departed_survivors"],
            "caught_to_surviving": len(j["down"]),
            "surviving_to_caught": len(j["up"]),
            "rows_differ_same_verdict": len(j["other"]),
            "same_key_set": j["same_keys"],
            "line_keys_shared": j["line_view"]["shared"],
            "line_caught_before": j["line_view"]["caught_a"],
            "line_caught_after": j["line_view"]["caught_b"],
            "line_down": j["line_view"]["down"],
            "same_line_key_set": j["line_view"]["identical"],
            "same_blob": j["same_blob"],
        })
    n_tr = len(archives) - 1
    summary.update(dict(tot), unkeyed_transitions=unkeyed_transitions,
                   identical_content=identical_content,
                   identical_lines=identical_lines, name_order_ties=ties)

    # The name tiebreak is a convention, and a result that rests on it should
    # say how much. Re-run the transitions under every order of the files
    # within each introducing commit, and report where a fall appears. It is
    # computed before the totals so that the total can say what it rests on.
    tb_out: list[str] = []
    if not unkeyed:
        summary["tiebreak"] = tb = tiebreak_sensitivity(hist, archives,
                                                        tb_out)
    out.append("")
    out.append(f"TOTAL over {n_tr} transitions: {tot['arrive']} arrive, "
               f"{tot['arrive_caught']} caught on arrival; {tot['depart']} "
               f"depart, {tot['depart_survivors']} of them survivors; "
               f"{tot['down']} caught -> surviving; {tot['up']} surviving -> "
               "caught.")
    if unkeyed:
        out.append(f"That {tot['down']} caught -> surviving is over the keyed "
                   "transitions only, in the name order; the tiebreak check "
                   "needs every file keyed and was not run.")
    elif not tb["computed"]:
        out.append(f"That {tot['down']} caught -> surviving is in the name "
                   "order; the tiebreak check was not computed.")
    elif tb["falls"]:
        out.append(f"That {tot['down']} caught -> surviving holds for the "
                   f"name-order tiebreak; {tb['no_fall_orders']} of the "
                   f"{tb['orders']} within-commit orders "
                   f"{_give(tb['no_fall_orders'])} 0 (see the "
                   "tiebreak section).")
    out.append(f"Adjacent pairs with identical key sets: {identical_content} "
               f"of {n_tr} by content key, {identical_lines} of {n_tr} by "
               "line key.")
    out.append(f"Transitions between two files on one blob, the only ones "
               f"where a line key names one site: {tot['same_blob']} of "
               f"{n_tr}.")
    out.append(f"Transitions whose order rests on the name tiebreak: {ties}.")
    if unkeyed_transitions:
        out.append(f"Transitions not keyed: {unkeyed_transitions}.")
    out.extend(tb_out)

    # Every pair of files on one blob, compared row for row over all rows.
    out.append("")
    out.append("== Files that match the same blob, compared row for row ==")
    groups = defaultdict(list)
    for a in archives:
        if a.blob is not None:
            groups[a.blob.oid].append(a)
    for oid, fs in groups.items():
        for i, a in enumerate(fs):
            for b in fs[i + 1:]:
                j = compare(a, b)
                same = sum(1 for k in j["paired"]
                           if not row_diff(j["A"][k], j["B"][k]))
                out.append(
                    f"  {a.label} vs {b.label} (blob {oid[:7]}): "
                    f"{len(j['paired'])} shared keys = {same} identical + "
                    f"{len(j['down']) + len(j['up'])} verdict flips "
                    f"({len(j['up'])} up, {len(j['down'])} down) + "
                    f"{len(j['other'])} other; "
                    f"{len(j['arrived']) + len(j['departed'])} keys in one "
                    "only")

    # Duplicated statements: what the ordinal and the scope are for.
    out.append("")
    out.append("== Statements with more than one site, per matched blob ==")
    for oid, fs in groups.items():
        blob = fs[0].blob
        texts = defaultdict(list)
        for n in blob.raw:
            texts[blob.ids[n]["statement"]].append(n)
        dup = {t: ns for t, ns in texts.items() if len(ns) > 1}
        n_dup = sum(len(ns) for ns in dup.values())
        out.append(f"  blob {oid[:7]} ({', '.join(f.label for f in fs)}): "
                   f"{n_dup} of {len(blob.raw)} sites share their text, in "
                   f"{len(dup)} group{'' if len(dup) == 1 else 's'}")
        for t, ns in sorted(dup.items(), key=lambda kv: kv[1][0]):
            cells = []
            for n in ns:
                ident = blob.ids[n]
                verdicts = ",".join(
                    ("C" if f.keyed[ident["key"]]["caught"] else "S")
                    if ident["key"] in f.keyed else "x" for f in fs)
                cells.append(f"L{n} {ident['scope']}#{ident['ordinal']} "
                             f"[{verdicts}]")
            out.append(f"    x{len(ns)} {t[:64]}")
            out.append("       " + "; ".join(cells))
    out.append("  (C caught, S survived, x not scored, one letter per file "
               "in the order listed)")

    # Ablation: the same join with the scope taken out of the key. It is not
    # a second opinion (it shares the matching and the assumption); it shows
    # which pairings the scope decides, so a key that loses it is visible.
    out.append("")
    out.append("== Ablation: statement text plus a file-wide ordinal, no "
               "scope ==")
    mis_total = 0
    abl_tot = defaultdict(int)
    for a, b in zip(archives, archives[1:]):
        if a.keyed is None or b.keyed is None:
            continue
        real = compare(a, b)
        abl = compare(a, b, keyfn=text_ordinal_key)
        # A misattribution is a pairing the scope-less key makes and the
        # site key does not: one site handed another site's history.
        wrong = sorted(set(abl["partner"].items())
                       - set(real["partner"].items()))
        for key in ("arrived", "departed", "down", "up"):
            abl_tot[key] += len(abl[key])
        abl_tot["arrive_caught"] += abl["arrived_caught"]
        mis_total += len(wrong)
        for n, m in wrong:
            rp = real["partner"].get(n)
            where = (f"L{rp} ({b.blob.ids[rp]['scope']})" if rp else
                     "nothing (it departs)")
            out.append(f"  {a.label} -> {b.label}: {a.label} L{n} "
                       f"({a.blob.ids[n]['scope']}) pairs with {where} under "
                       f"the site key and with L{m} ({b.blob.ids[m]['scope']})"
                       " without the scope")
    out.append(f"  misattributed pairings: {mis_total}. Totals without the "
               f"scope: {abl_tot['arrived']} arrive, {abl_tot['arrive_caught']}"
               f" caught on arrival, {abl_tot['departed']} depart, "
               f"{abl_tot['down']} caught -> surviving, {abl_tot['up']} "
               "surviving -> caught.")
    summary["ablation_misattributed"] = mis_total
    summary["ablation_totals"] = dict(abl_tot)
    out.append("")
    out.append(ASSUMPTION)
    return out, summary


def pair_report(a: Archive, b: Archive) -> list[str]:
    out = [ASSUMPTION, ""]
    j = describe(a, b, out)
    surv = [k for k in j["A"] if not j["A"][k]["caught"]]
    by_scope = defaultdict(lambda: [0, 0, 0])
    for k in surv:
        cell = by_scope[j["A"][k]["scope"]]
        cell[0] += 1
        if k in j["B"]:
            cell[1 if j["B"][k]["caught"] else 2] += 1
    out.append(f"  {a.label}'s {len(surv)} survivors, by scope: caught in "
               f"{b.label} / still surviving / not in {b.label}")
    for scope, (n, c, s) in sorted(by_scope.items()):
        out.append(f"    {scope:40s} {n:3d}: {c} / {s} / {n - c - s}")
    still = [j["A"][k] for k in surv
             if k in j["B"] and not j["B"][k]["caught"]]
    if still:
        out.append("  still surviving: " + ", ".join(
            f"L{r['line']}->L{j['B'][r['key']]['line']}" for r in still))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", type=pathlib.Path, default=TOOL_REPO,
                    help="git repository whose history is read")
    ap.add_argument("--archives", type=pathlib.Path, default=None,
                    help="directory holding the mutation*.json files "
                         "(default: <repo>/paper). A copy may be named here; "
                         "each file is still ordered by where its name was "
                         "added in the repository")
    ap.add_argument("--repo-dir", default="paper",
                    help="where the archives live inside the repository")
    ap.add_argument("--pair", nargs=2, metavar=("A", "B"),
                    help="join two files (name or label) instead")
    ap.add_argument("--json", type=pathlib.Path,
                    help="also write the transition summary here")
    a = ap.parse_args(argv)
    archives_dir = a.archives or (a.repo / a.repo_dir)
    try:
        hist, archives = reconcile(a.repo, archives_dir, a.repo_dir)
    except ReconcileError as e:
        print(f"ABORT: {e}", file=sys.stderr)
        return 2
    if a.pair:
        pick = {}
        for x in archives:
            pick[x.name] = pick[x.label] = x
        try:
            fa, fb = (pick[p] for p in a.pair)
        except KeyError as e:
            print(f"ABORT: no archive named {e}", file=sys.stderr)
            return 2
        if fa.keyed is None or fb.keyed is None:
            print("ABORT: a file in the pair has no unique blob",
                  file=sys.stderr)
            return 2
        print("\n".join(pair_report(fa, fb)))
        return 0
    lines, summary = report(hist, archives)
    print("\n".join(lines))
    if a.json:
        a.json.write_text(json.dumps(summary, indent=1) + "\n")
    return 1 if any(summary[k] for k in PROBLEMS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
