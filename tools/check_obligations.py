"""Refuse an obligation ledger that has drifted from SPEC.md or from the tests.

Deterministic. It never decides whether a mapping is INTELLECTUALLY right; it
decides whether the ledger still corresponds to artifacts that exist:

  C1  a normative clause in SPEC.md with no ledger entry
  C2  a referenced site that no longer exists (refusal code, test file, test fn)
  C3  a property token that does not bind: the named test does not reference the
      refusal site, or the token's prefix contradicts the clause's section
  C4  status 'mapped' with no executable reference behind it
  C5  duplicate obligation ids, or a vague property token
  C6  normative_text that no longer matches the line it cites
  C7  a missing or disallowed addressee / addressee_basis
  C8  an addressee contradicting its namespace, or a basis contradicting its prefix
  C9  an adjudicated addressee that is not the reviewed ruling for its subfamily

C4 is the one that stops the ledger from flattering itself. Marking an
obligation mapped is a claim that something fails when it is violated, and this
refuses that claim unless a test names the mechanism.
"""
from __future__ import annotations
import json, pathlib, re, sys, collections

ROOT = pathlib.Path(__file__).resolve().parents[1]
OBLIGATION_RE = re.compile(r'\bMUST NOT\b|\bMUST\b|\bSHALL NOT\b|\bSHALL\b')
VAGUE = {"correctness","works","valid","correct","good","ok","behaviour","behavior",
         "quality","sane","proper","right","fine","checked","tested","verified"}
STATUSES = {"mapped","partially_mapped","unmeasured"}
ADDRESSEES = {"verifier","registry","reviewer"}
# Kept in step with tools/build_obligations.py. Duplicated deliberately: the
# checker must be able to refuse a ledger without importing the generator that
# produced it, or it only ever agrees with itself.
EXACT_PREFIX = {
    "bundle":"verifier","evidence":"verifier","results":"verifier","replay":"verifier",
    "verifier":"verifier","certlab":"verifier","fleet":"verifier","evalmut":"verifier",
    "crashkit":"verifier","modeldrift":"verifier","registry":"registry",
}
AMBIGUOUS_PREFIX = {"protocol"}
# Independently restated, like EXACT_PREFIX above, and for the same reason. This
# is the table that makes an adjudication accountable: without it the checker
# proves a field was filled in, not that it holds the reviewed answer.
ADJUDICATED = {
    "protocol.grading.": "reviewer",
    "protocol.hashes.":  "verifier",
}
BASES = {"derived-from-token-prefix","adjudicated"}
# token prefix -> the section fragment the clause must sit under
PREFIX_SECTION = {"certlab":"certlab","fleet":"fleet","evalmut":"evalmut",
                  "crashkit":"crashkit","modeldrift":"modeldrift"}

def spec_clauses():
    lines = (ROOT/"SPEC.md").read_text().splitlines()
    sec=""; out={}
    for i,l in enumerate(lines,1):
        if l.startswith("#"): sec=l.lstrip("#").strip()
        if OBLIGATION_RE.search(l): out[i]=(sec, l.strip())
    return out

def test_index():
    idx={}
    for p in sorted((ROOT/"tests").glob("test_*.py")):
        if p.name == "test_obligation_ledger.py":
            continue  # see build_obligations.py: the ledger may not cite itself
        for part in re.split(r"^(?=def test_)", p.read_text(), flags=re.M):
            m=re.match(r"def (test_\w+)", part)
            if m: idx[f"tests/{p.name}::{m.group(1)}"]=part
    return idx

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    led_path = pathlib.Path(argv[argv.index("--ledger")+1]) if "--ledger" in argv else ROOT/"obligations.json"
    if not led_path.is_file():
        print("REFUSED: obligations.json is missing"); return 1
    led = json.loads(led_path.read_text())
    obs = led["obligations"]
    clauses = spec_clauses()
    tests = test_index()
    codes = set(re.findall(r'"([a-z][a-z0-9-]{4,40}):', (ROOT/"vac"/"verify.py").read_text()))
    bad = []

    # C1
    covered = {int(o["source_span"].split(":")[1]) for o in obs}
    for line,(sec,txt) in sorted(clauses.items()):
        if line not in covered:
            bad.append(f"C1 no ledger entry for SPEC.md:{line} [{sec}] {txt[:70]}")

    seen = collections.Counter(o["obligation_id"] for o in obs)
    for oid,n in seen.items():
        if n > 1: bad.append(f"C5 duplicate obligation_id {oid} appears {n} times")

    for o in obs:
        oid = o["obligation_id"]
        st, site, token = o["status"], o.get("refusal_site"), o.get("property_token","")
        line = int(o["source_span"].split(":")[1])

        who, basis = o.get("addressee"), o.get("addressee_basis")
        pre0 = token.split(".")[0]
        # C7 present and allowed
        if who not in ADDRESSEES:
            bad.append(f"C7 {oid}: addressee {who!r} is not one of {sorted(ADDRESSEES)}")
        if basis not in BASES:
            bad.append(f"C7 {oid}: addressee_basis {basis!r} is not one of {sorted(BASES)}")
        # C8 bound to the stable prefix mapping
        if pre0 in EXACT_PREFIX:
            if who != EXACT_PREFIX[pre0]:
                bad.append(f"C8 {oid}: addressee {who!r} contradicts exact prefix "
                           f"{pre0!r} -> {EXACT_PREFIX[pre0]!r}")
            if basis != "derived-from-token-prefix":
                bad.append(f"C8 {oid}: prefix {pre0!r} is exact, so basis must be "
                           f"derived-from-token-prefix, not {basis!r}")
        elif pre0 in AMBIGUOUS_PREFIX:
            if basis != "adjudicated":
                bad.append(f"C8 {oid}: prefix {pre0!r} is ambiguous, so the addressee "
                           f"must be adjudicated, not {basis!r}")
            # C9: the adjudication must carry the reviewed answer, not merely exist
            hits = [a for pre, a in ADJUDICATED.items() if token.startswith(pre)]
            if len(hits) != 1:
                bad.append(f"C9 {oid}: token {token!r} is under ambiguous prefix {pre0!r} "
                           f"but matches {len(hits)} ADJUDICATED rules, so its adjudication "
                           f"answers to nothing")
            elif who != hits[0]:
                bad.append(f"C9 {oid}: adjudicated as {who!r}; the reviewed ruling for "
                           f"{token!r} is {hits[0]!r}")
        else:
            bad.append(f"C8 {oid}: token prefix {pre0!r} is in neither EXACT_PREFIX "
                       f"nor AMBIGUOUS_PREFIX, so its addressee is unaccountable")

        if st not in STATUSES:
            bad.append(f"C5 {oid}: status {st!r} is not one of {sorted(STATUSES)}")

        # C5 vague token
        parts = [p for p in re.split(r"[._]", token) if p]
        if len(token.split(".")) < 2 or not parts:
            bad.append(f"C5 {oid}: property_token {token!r} is not a dotted operational property")
        for p in parts:
            if p.lower() in VAGUE:
                bad.append(f"C5 {oid}: property_token {token!r} contains the vague term {p!r}")

        # C6 clause drift
        if line not in clauses:
            bad.append(f"C6 {oid}: SPEC.md:{line} no longer carries a normative clause")
        elif clauses[line][1] != o["normative_text"]:
            bad.append(f"C6 {oid}: normative_text no longer matches SPEC.md:{line}")

        # C2 refusal site exists
        if site is not None and site not in codes:
            bad.append(f"C2 {oid}: refusal_site {site!r} is not a code vac/verify.py emits")

        # C2 evaluation sites exist
        for s in o["evaluation_sites"]:
            if s not in tests:
                bad.append(f"C2 {oid}: evaluation_site {s} does not exist")

        # C3 the named test must actually reference the refusal site
        if site is not None:
            for s in o["evaluation_sites"]:
                body = tests.get(s)
                if body is not None and site not in body:
                    bad.append(f"C3 {oid}: {s} does not reference refusal_site {site!r}")

        # C3 token prefix must not contradict the clause's section
        pre = token.split(".")[0].lower()
        if pre in PREFIX_SECTION and line in clauses:
            if PREFIX_SECTION[pre] not in clauses[line][0].lower():
                bad.append(f"C3 {oid}: token prefix {pre!r} contradicts section {clauses[line][0]!r}")

        # C4 mapped must be executable
        if st == "mapped" and (site is None or not o["evaluation_sites"]):
            bad.append(f"C4 {oid}: status 'mapped' with no executable reference")
        if st == "unmeasured" and (site or o["evaluation_sites"]):
            bad.append(f"C4 {oid}: status 'unmeasured' but a site is claimed")

    tally = collections.Counter(o["status"] for o in obs)
    who_t = collections.Counter(o.get("addressee") for o in obs)
    unmeasured_who = collections.Counter(o.get("addressee") for o in obs if o["status"]=="unmeasured")
    print(f"  {len(obs)} obligations from {len(clauses)} normative clauses "
          f"[mapped {tally['mapped']} | partial {tally['partially_mapped']} | unmeasured {tally['unmeasured']}]")
    print(f"  by addressee: {dict(who_t)}   unmeasured by addressee: {dict(unmeasured_who)}")
    if bad:
        print(f"REFUSED: {len(bad)} finding(s)")
        for b in bad: print("   ", b)
        return 1
    print("  obligation ledger: PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
