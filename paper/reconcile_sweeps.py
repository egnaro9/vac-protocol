#!/usr/bin/env python3
"""Diff archived mutation sweeps per-site.

Answers a reviewer question raised on the paper announcement thread: a mutation
score is a count over a population that is re-enumerated every run, so two
adjacent sweeps can only be diffed when they enumerate the SAME sites.

Site identity here is the bare line number, which is exactly the key under
suspicion.  A pair reported as "not diffable" is therefore UNDECIDABLE from
the archive, not proof that the population changed: a source edit that shifts
every line produces the same signature as a genuine re-enumeration.
"""
import json, sys, pathlib

ORDER = ["mutation.json", "mutation_after.json", "mutation_covered.json",
         "mutation_v2.json", "mutation_v3.json", "mutation_gated.json",
         "mutation_final.json", "mutation_final2.json", "mutation_v5.json",
         "mutation_v6.json", "mutation_v7.json", "mutation_v8.json"]


def load(path):
    d = json.loads(pathlib.Path(path).read_text())
    rows = d.get("results") if isinstance(d, dict) else d
    hdr = (d.get("score"), d.get("caught"), d.get("total")) if isinstance(d, dict) else None
    return hdr, {r["line"]: r["caught"] for r in rows}


def main(base="."):
    base = pathlib.Path(base)
    sweeps = {f: load(base / f) for f in ORDER}

    print("== per-sweep (header vs recomputed) ==")
    for f, (hdr, m) in sweeps.items():
        c = sum(1 for v in m.values() if v)
        recomputed = f"{c}/{len(m)}={c/len(m):.4f}"
        note = "" if hdr and hdr[1] == c and hdr[2] == len(m) else "  <-- no header, score is derived not recorded"
        print(f"{f:24s} header={hdr} recomputed={recomputed}{note}")

    print("\n== duplicate sweeps (same key set AND same verdicts) ==")
    names = list(sweeps)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if sweeps[a][1] == sweeps[b][1]:
                print(f"  {a} and {b} are the same run under two names")

    print("\n== adjacent pairs ==")
    diffable = 0
    for a, b in zip(ORDER, ORDER[1:]):
        A, B = sweeps[a][1], sweeps[b][1]
        shared = set(A) & set(B)
        up = sum(1 for k in shared if not A[k] and B[k])
        down = sum(1 for k in shared if A[k] and not B[k])
        ca, cb = sum(A.values()), sum(B.values())
        if set(A) == set(B):
            diffable += 1
            verdict = f"DIFFABLE  survived->caught={up}  caught->survived={down}"
        else:
            verdict = f"UNDECIDABLE  shared={len(shared)}  onlyA={len(set(A)-set(B))}  onlyB={len(set(B)-set(A))}"
        print(f"{a:22s} -> {b:22s} {ca}/{len(A)}={ca/len(A):.3f} -> {cb}/{len(B)}={cb/len(B):.3f}  {verdict}")
    print(f"\n{diffable} of {len(ORDER)-1} adjacent pairs are diffable per-site.")

    A = sweeps[ORDER[0]][1]
    Z = sweeps[ORDER[-1]][1]
    print(f"headline endpoints {ORDER[0]} -> {ORDER[-1]}: share {len(set(A)&set(Z))} line keys "
          f"of {len(A)} and {len(Z)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).parent)
