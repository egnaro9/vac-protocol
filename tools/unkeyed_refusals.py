#!/usr/bin/env python3
"""Enumerate the refusals from the other side: which emitted codes no
obligation names.

obligations.json reads forward, from a normative clause in SPEC.md to the
refusal that enforces it. Read that way the ledger can only ever report on
what it already covers. A refusal the ledger names nowhere is invisible to it,
so the size of that residue has been a sentence in prose carrying a number
nothing regenerates. This reads the other way: from every statement in
vac/verify.py that emits a refusal code, back to the entries that name that
code, and prints what is left over.

WHAT THE RESIDUE IS, AND WHAT IT IS NOT. It is counted by CODE, so it bounds
nothing in either direction:

  inflation    an alias site enforces part of a rule an entry already names
               under a different code, so it is counted as uncovered while the
               rule behind it is covered;
  deflation    a site that shares a code an entry names is not in the residue
               at all, whether or not it enforces the clause that entry names.

Both directions are printed beside the residue, the second as the named codes
carrying more sites than entries, so the figure cannot be read as a coverage
bound. Which residue codes are aliases, which enforce a specification sentence
that carries no MUST, and which have no specification basis at all, is a
reading of SPEC.md: it is not derived here and this tool does not guess at it.

THREE POPULATIONS, all printed, because they differ and published figures have
been quoted from the wrong one:

  emissions    every statement that emits a code: the collected appends, the
               early returns in verify_bundle, and the one CLI print that
               reports the archive refusals raised inside _extract_tar;
  appends      the collected reasons alone;
  scored       the appends the mutation sweep scores, that is the appends
               minus the sites its EXCLUDE table declares unreachable.

vac/registry.py is not read here, and neither is any issuer repository.

  python tools/unkeyed_refusals.py [--json out.json]
  python tools/unkeyed_refusals.py --verify OTHER/vac/verify.py \
                                   --ledger OTHER/obligations.json

Reading anything other than this tree's own files turns the pin check off,
because the sweep's pinned population belongs to this revision.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
# The siblings that read the emission sites and that define the scored
# population. Put on the path explicitly so the import does not depend on how
# this script was launched.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ledger_sources import APPEND, PRINT, RETURN, refusal_sites  # noqa: E402
from mutation_sweep import (EXCLUDE, EXPECT_RAW_SITES,  # noqa: E402
                            EXPECT_SCORED_SITES, REFUSAL)

DEFAULT_VERIFY = ROOT / "vac" / "verify.py"
DEFAULT_LEDGER = ROOT / "obligations.json"


def scored_lines(source: str, exclude: dict | None = None) -> tuple[set[int], set[int]]:
    """(the append lines the mutation sweep scores, the lines EXCLUDE removes).

    Read the sweep's way, by line, so this reports the population the score is
    actually taken over rather than a second opinion about it. Refuses when
    EXCLUDE does not match the source as declared: an exclusion matching fewer
    lines than declared inflates the denominator and one matching more shrinks
    it, and either makes every share printed below wrong by a silent amount.

    `exclude` defaults to the sweep's table, read when this is called rather
    than when it was defined, so a caller measuring another source can put its
    own table in front of it.
    """
    exclude = EXCLUDE if exclude is None else exclude
    lines = source.splitlines()
    sites = [i for i, ln in enumerate(lines, 1) if REFUSAL.match(ln)]
    excluded: set[int] = set()
    bad = []
    for key, (want, _why) in exclude.items():
        hits = [i for i in sites if key in lines[i - 1]]
        if len(hits) != want:
            bad.append(f"{key!r} expected {want} line(s), matched {len(hits)}")
        excluded.update(hits)
    if bad:
        raise ValueError("EXCLUDE does not match the source as declared: "
                         + "; ".join(bad))
    return {i for i in sites if i not in excluded}, excluded


def measure(verify_source: str, ledger: dict, scored: set[int] | None = None,
            excluded: set[int] = frozenset()) -> dict:
    """The reverse enumeration over one verifier source and one ledger.

    `scored` and `excluded` come from scored_lines(). Pass neither to report
    the emission populations alone, which is what a source the sweep's EXCLUDE
    table does not describe allows.
    """
    sites = refusal_sites(verify_source)
    by_code: dict[str, list] = collections.defaultdict(list)
    for s in sites:
        by_code[s.code].append(s)
    # How many entries name each code. An entry with no refusal_site names
    # none: that is the ledger saying the obligation is unmeasured, and
    # counting it here would turn a disclosed gap into coverage.
    named = collections.Counter(o["refusal_site"] for o in ledger["obligations"]
                                if o.get("refusal_site"))
    codes = sorted(by_code)
    unkeyed = [c for c in codes if c not in named]

    def rows(chosen: list[str]) -> list[dict]:
        return [{"code": c,
                 "sites": len(by_code[c]),
                 "appends": sum(1 for s in by_code[c] if s.kind == APPEND),
                 "kinds": dict(collections.Counter(s.kind for s in by_code[c])),
                 "lines": [s.line for s in by_code[c]],
                 "entries": named.get(c, 0)}
                for c in chosen]

    unkeyed_sites = [s for s in sites if s.code not in named]
    unkeyed_appends = [s for s in unkeyed_sites if s.kind == APPEND]
    report = {
        "population": {
            "emissions": len(sites),
            "by_kind": dict(collections.Counter(s.kind for s in sites)),
            "codes": len(codes),
        },
        "ledger": {
            "entries": len(ledger["obligations"]),
            "entries_naming_a_code": sum(named.values()),
            "codes_named": len(named),
            "codes_named_but_never_emitted": sorted(set(named) - set(by_code)),
        },
        "unkeyed": {
            "codes": len(unkeyed),
            "emissions": len(unkeyed_sites),
            "append_codes": len({s.code for s in unkeyed_appends}),
            "appends": len(unkeyed_appends),
            "by_code": rows(unkeyed),
        },
        # The deflation side: one code standing for several clauses. These
        # sites are outside the residue by construction, whatever they enforce.
        "shared": rows([c for c in codes
                        if named.get(c, 0) and len(by_code[c]) > named[c]]),
        "scored": None,
    }
    if scored is None:
        return report

    appends = {s.line for s in sites if s.kind == APPEND}
    if appends != scored | set(excluded):
        raise ValueError(
            "the append population read from the AST and the one the sweep "
            "reads by line do not agree: "
            f"{sorted(appends - (scored | set(excluded)))} seen only by the "
            f"AST, {sorted((scored | set(excluded)) - appends)} seen only by "
            "the line pattern. One of the two readers is counting a refusal "
            "the other cannot see, so neither population is trustworthy.")
    in_scope = [s for s in unkeyed_appends if s.line in scored]
    report["scored"] = {
        "population": len(scored),
        "excluded": len(excluded),
        "unkeyed": len(in_scope),
        "share": round(len(in_scope) / len(scored), 4) if scored else 0.0,
        "unkeyed_and_excluded": len(unkeyed_appends) - len(in_scope),
    }
    return report


def render(report: dict) -> str:
    pop, led, un = report["population"], report["ledger"], report["unkeyed"]
    kinds = pop["by_kind"]
    shape = ", ".join(f"{kinds[k]} {k}{'s' if kinds[k] != 1 else ''}"
                      for k in (APPEND, RETURN, PRINT) if k in kinds)
    out = [
        "refusal population of the verifier source",
        f"  {pop['emissions']} emission statements ({shape})",
        f"  {pop['codes']} refusal codes",
        f"  ledger: {led['entries']} entries, {led['entries_naming_a_code']} "
        f"naming a refusal code, {led['codes_named']} distinct codes",
    ]
    if led["codes_named_but_never_emitted"]:
        out.append("  named by an entry and emitted nowhere: "
                   + ", ".join(led["codes_named_but_never_emitted"]))
    out += ["", "UNKEYED: codes that no obligation entry names",
            f"  {'code':<34}{'sites':>7}{'appends':>9}"]
    for r in sorted(un["by_code"], key=lambda r: (-r["sites"], r["code"])):
        out.append(f"  {r['code']:<34}{r['sites']:>7}{r['appends']:>9}")
    out += [
        f"  {un['codes']} codes over {un['emissions']} of the "
        f"{pop['emissions']} emissions",
        f"  {un['append_codes']} codes over {un['appends']} of the "
        f"{kinds.get(APPEND, 0)} appends",
    ]
    sc = report["scored"]
    if sc is None:
        out.append("  scored population: not established for this source, so "
                   "no share is printed")
    else:
        out.append(f"  scored population: {sc['unkeyed']} of {sc['population']}"
                   f" ({sc['share'] * 100:.1f} percent); "
                   f"{sc['unkeyed_and_excluded']} further unkeyed append(s) "
                   f"sit in the sweep's EXCLUDE table")
    out += ["", "WHAT THIS DOES NOT BOUND",
            "  Counted by code. An alias site enforcing part of an already "
            "named rule inflates it.",
            "  Sites sharing a code an entry names are outside it whatever "
            "they enforce:"]
    if report["shared"]:
        for r in sorted(report["shared"], key=lambda r: -r["sites"]):
            out.append(f"    {r['code']:<34}{r['sites']:>7} sites"
                       f"{r['entries']:>5} "
                       f"{'entry' if r['entries'] == 1 else 'entries'}")
    else:
        out.append("    (none: no named code carries more sites than entries)")
    out.append("  Which residue codes are aliases, which enforce a "
               "specification sentence carrying no MUST, and")
    out.append("  which have no specification basis, is a reading of SPEC.md "
               "and is not derived here.")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verify", type=pathlib.Path, default=DEFAULT_VERIFY,
                    help="the verifier source to enumerate")
    ap.add_argument("--ledger", type=pathlib.Path, default=DEFAULT_LEDGER,
                    help="the obligation ledger to enumerate against")
    ap.add_argument("--json", type=pathlib.Path,
                    help="write the whole report, emission lines included")
    ap.add_argument("--no-pin", action="store_true",
                    help="do not compare the population to the sweep's pins")
    a = ap.parse_args(argv)

    own_tree = (a.verify.resolve() == DEFAULT_VERIFY.resolve()
                and a.ledger.resolve() == DEFAULT_LEDGER.resolve())
    pin = own_tree and not a.no_pin
    source = a.verify.read_text(encoding="utf-8")
    ledger = json.loads(a.ledger.read_text(encoding="utf-8"))
    try:
        scored, excluded = scored_lines(source)
    except ValueError as e:
        if own_tree:
            print(f"ABORT: {e}", file=sys.stderr)
            return 2
        # Another revision may legitimately not be the tree EXCLUDE describes.
        # Say so and print the emission populations, which stand on their own.
        print(f"note: {e}\nnote: the scored population is left out of this "
              "report", file=sys.stderr)
        scored = excluded = None
    try:
        report = (measure(source, ledger) if scored is None
                  else measure(source, ledger, scored, excluded))
    except ValueError as e:
        print(f"ABORT: {e}", file=sys.stderr)
        return 2

    if pin:
        raw = report["population"]["by_kind"].get(APPEND, 0)
        got = (raw, report["scored"]["population"])
        want = (EXPECT_RAW_SITES, EXPECT_SCORED_SITES)
        if got != want:
            print(f"ABORT: refusal-site population is {got[0]} raw / {got[1]} "
                  f"scored; the mutation sweep pins {want[0]} / {want[1]}. "
                  "Every share in this report is taken over that population, "
                  "so a report against a population nobody decided to change "
                  "would print figures the sweep's score does not share. "
                  "Update the sweep's pins in the commit that changes the "
                  "population, or pass --no-pin for a one-off reading.",
                  file=sys.stderr)
            return 2
    print(render(report))
    if a.json:
        a.json.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
