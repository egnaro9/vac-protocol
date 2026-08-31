"""Emit obligations.json: one entry per normative clause in SPEC.md.

Only the MAPPING table below is human judgement. Everything else is derived
from the artifacts, so a careless edit here cannot invent a span, a clause, or
a test that does not exist:

  obligation_id     positional, stable while a clause keeps its section+order
  source_span       SPEC.md line, resolved at build time
  normative_text    quoted from SPEC.md, never retyped
  evaluation_sites  DERIVED: the tests that reference the refusal code
  refusal_site      human: which mechanism fails when the obligation is violated
  property_token    human: the specific operational property, dotted
  status            human: mapped | partially_mapped | unmeasured
  rationale         human: why the site supports the obligation, or why none does

`unmeasured` is a first-class outcome. An obligation with no executable site is
the finding, not a gap to paper over by pointing at a test that does not bind it.
"""
from __future__ import annotations
import json, pathlib, re, sys, collections

ROOT = pathlib.Path(__file__).resolve().parents[1]
OBLIGATION_RE = re.compile(r'\bMUST NOT\b|\bMUST\b|\bSHALL NOT\b|\bSHALL\b')

# property-token namespace -> addressee, where the mapping is EXACT.
# A prefix belongs here only if every clause using it has the same addressee.
EXACT_PREFIX = {
    "bundle": "verifier", "evidence": "verifier", "results": "verifier",
    "replay": "verifier", "verifier": "verifier",
    "certlab": "verifier", "fleet": "verifier", "evalmut": "verifier",
    "crashkit": "verifier", "modeldrift": "verifier",
    "registry": "registry",
}
# Prefixes that genuinely span addressees. `protocol` does: protocol.hashes.*
# is recomputed by the verifier, protocol.grading.* is prose a human reads.
# These REQUIRE an explicit adjudication in MAPPING; the builder refuses to
# guess, and narrowing the prefix to two segments to dodge that would hide the
# judgement rather than record it.
AMBIGUOUS_PREFIX = {"protocol"}

# line -> (refusal_site, property_token, status, rationale, addressee|None)
# addressee is None wherever EXACT_PREFIX settles it; a string is an explicit
# adjudication and is only permitted for an AMBIGUOUS_PREFIX token.
MAPPING = {
 52:("missing-artifact","evidence.artifact.listed_with_sha256","mapped","Every bundle file must be an evidence entry carrying its sha256; the verifier refuses a bundle file that no evidence row lists."),
 58:("unsafe-bundle","bundle.contains_no_symlinks","mapped","Symlink members are rejected before any hashing, so a link cannot smuggle content in from outside the bundle."),
109:(None,"protocol.grading.describes_deterministic_process","unmeasured","Prose obligation. Nothing reads protocol.grading beyond requiring it non-empty, so 'describes a deterministic process' is enforced by human review at PR time and by replay, not by the verifier. Tracked as egnaro9/vac-protocol#6.","reviewer"),
115:("stamp-mismatch","protocol.hashes.commit_key_equals_issuer_commit","mapped","A commit-shaped hash key must equal protocol.issuer_commit or the stamp binding is refused.","verifier"),
116:("stamp-mismatch","protocol.hashes.equal_artifact_values","mapped","Each pinned hash must equal the value carried by the artifact it pins.","verifier"),
132:("summary-outruns-checks","results.summary.number_bound_to_a_check","mapped","A headline number with no check that recomputes it is refused, which is the closure rule for summaries."),
135:("unknown-profile","results.checks.profile_is_known","mapped","A check naming a profile outside SPEC 3 is refused rather than skipped."),
149:("schema-violation","results.summary.number_is_json_number","mapped","A stringified headline number cannot be compared to a recomputation, so it is a schema violation rather than a soft warning."),
158:("evidence-unchecked","evidence.artifact.referenced_by_a_check","mapped","Closure in the other direction: an evidence artifact no check reads is refused."),
213:("unscopable-check","results.scope.matches_token_grammar","mapped","A scope derived from the primary evidence filename must match [A-Za-z0-9_-]+ or the check is unscopable."),
214:("unscopable-check","results.scope.unique_within_bundle","mapped","Two checks sharing a scope would merge two pools, which is the same-name recompute hole; refused."),
256:("issuer-commit-mismatch","replay.issuer_commit_equals_protocol","mapped","The replay recipe must check out the same commit the bundle was stamped at."),
283:("draft-incomplete","bundle.contains_no_draft_markers","mapped","A draft marker anywhere in the bundle is refused; the marker is grammar, not convention."),
285:("draft-incomplete","bundle.one_refusal_per_draft_marker","mapped","Refusals are emitted per marker rather than collapsed to one, so the count of unauthored spots is visible."),
307:("summary-mismatch","certlab.expect.names_a_recomputed_field","mapped","An expect key that names no recomputed field is withheld from the pool rather than treated as satisfied."),
321:(None,"registry.free_text_pool_key_not_admitted_to_pool","unmeasured","A rule addressed to registries rather than to the verifier. vac.registry does not implement a free-text-pool admission distinction, so nothing refuses a registry that gets this wrong."),
351:("raw-aggregate-mismatch","fleet.row.recomputes_from_raw","mapped","Each aggregate row is recomputed from the raw rows and must equal the declared value."),
356:("summary-mismatch","fleet.expect.rows_equals_row_count","mapped","expect.rows, when present, is compared to the recomputed row count."),
390:("raw-aggregate-mismatch","evalmut.case_name_in_declared_corpus","mapped","Citing a case the corpus does not contain is refused, so a finding cannot reference an absent row."),
391:("raw-aggregate-mismatch","evalmut.case_count_equals_corpus_size","mapped","case_count is recomputed from the corpus."),
422:("summary-mismatch","evalmut.expect.names_a_recomputed_field","mapped","expect keys must name a recomputed field and equal it."),
472:("raw-aggregate-mismatch","crashkit.accuracy_equals_all_four_aliases","mapped","accuracy is recomputed and compared against every alias the artifact publishes, so one alias cannot drift."),
477:("raw-aggregate-mismatch","crashkit.severity_weighted_score_recomputes","mapped","The severity-weighted score is recomputed over graded rows."),
478:("raw-aggregate-mismatch","crashkit.counts_equal_row_tallies","mapped","flagged_cases, n_cases and truncations are recounted from the rows."),
481:("raw-aggregate-mismatch","crashkit.reliability_recomputes","mapped","reliability is recomputed as (cases - errors - truncations) / cases."),
482:("raw-aggregate-mismatch","crashkit.per_kind_equal_both_directions","mapped","per_kind is compared key-for-key in both directions, so an extra or missing kind is refused."),
485:("summary-mismatch","crashkit.expect.names_a_recomputed_field","mapped","expect keys must name a recomputed field and equal it."),
496:("stamp-mismatch","crashkit.battery_hash_key_equals_git_sha","mapped","battery_hash_key names the protocol.hashes entry that must equal the artifact's git_sha."),
543:("raw-aggregate-mismatch","modeldrift.min_detectable_object_recomputes","mapped","The min-detectable object is recomputed from the fingerprint task count."),
549:("suite","modeldrift.suite_byte_identical_to_committed","mapped","The suite named by the fingerprint must be byte-identical to the committed copy."),
560:("raw-aggregate-mismatch","modeldrift.models_with_enough_history_equals_flips","mapped","The recomputed series count is compared to the committed flips artifact."),
566:("summary-mismatch","modeldrift.expect.names_a_recomputed_field","mapped","expect keys must name a recomputed field and equal it."),
573:("raw-aggregate-mismatch","modeldrift.flips_row_latest_whole_object_equality","mapped","Each flips row carries latest and is compared by whole-object equality, so its wording is normative."),
581:("stamp-mismatch","modeldrift.suite_hash_equals_fingerprint","mapped","protocol.hashes.suite_hash must equal the fingerprint's suite hash."),
583:("stamp-mismatch","modeldrift.registry_sha256_equals_evidence_hashes","mapped","registry_sha256 must equal the evidence hashes of the metrics and models artifacts."),
692:("schema-violation","registry.rejects_claim_on_listed_conditions","partially_mapped","vac.registry refuses a bundle whose structural verification fails, which covers the verifier-checkable conditions in the list. The conditions that are matters of registry POLICY rather than bundle structure are not separately enforced."),
722:(None,"registry.discloses_skipped_replay_gate_per_entry","unmeasured","A disclosure obligation on registry prose. Every entry carries a gates.semantic string, but nothing checks that the string is honest about whether replay ran."),
791:("schema-violation","verifier.refuses_unimplemented_vac_version","mapped","A vac_version outside SUPPORTED_VERSIONS is refused rather than guessed at."),
792:("schema-violation","verifier.applies_declared_version_semantics","partially_mapped","The verifier branches on the declared version for the rules that differ between 0.1 and 0.2 (scope binding, rel_floor). It is mapped for the rules that actually diverge; there is no general check that every rule consults the declared version."),
}

ADDRESSEES = {"verifier", "registry", "reviewer"}
VAGUE = {"correctness","works","valid","correct","good","ok","behaviour","behavior","quality","sane"}

def clauses():
    lines = (ROOT/"SPEC.md").read_text().splitlines()
    sec = ""
    out = []
    for i, l in enumerate(lines, 1):
        if l.startswith("#"):
            sec = l.lstrip("#").strip()
        if OBLIGATION_RE.search(l):
            out.append({"line": i, "section": sec, "text": l.strip()})
    return out

def code_to_tests():
    codes = sorted(set(re.findall(r'"([a-z][a-z0-9-]{4,40}):', (ROOT/"vac"/"verify.py").read_text())))
    bind = collections.defaultdict(list)
    for p in sorted((ROOT/"tests").glob("test_*.py")):
        # A test ABOUT the ledger is not evidence that an obligation is enforced.
        # test_obligation_ledger.py names refusal codes in its own fixtures, so
        # without this the ledger cites itself as its own evaluation site.
        if p.name == "test_obligation_ledger.py":
            continue
        for part in re.split(r"^(?=def test_)", p.read_text(), flags=re.M):
            m = re.match(r"def (test_\w+)", part)
            if not m:
                continue
            for c in codes:
                if f'"{c}' in part or f"'{c}" in part or f"{c}:" in part:
                    bind[c].append(f"tests/{p.name}::{m.group(1)}")
    return bind

def pick(sites, token, cap=4):
    """Rank by overlap between the test name and the property token. Derived,
    so the same ledger is produced on any machine, and never hand-picked."""
    words = {w for w in re.split(r"[._]", token) if len(w) > 3}
    return sorted(sites, key=lambda s: (-sum(w in s.lower() for w in words), s))[:cap]

def main():
    cl = clauses()
    bind = code_to_tests()
    unmapped = [c["line"] for c in cl if c["line"] not in MAPPING]
    if unmapped:
        sys.exit(f"build refuses: {len(unmapped)} clause(s) with no MAPPING row: {unmapped}")
    entries = []
    for n, c in enumerate(cl, 1):
        row = MAPPING[c["line"]]
        site, token, status, why = row[:4]
        explicit = row[4] if len(row) > 4 else None
        pre = token.split(".")[0]
        if pre in AMBIGUOUS_PREFIX:
            if explicit not in ADDRESSEES:
                sys.exit(f"build refuses: SPEC.md:{c['line']} uses ambiguous prefix "
                         f"{pre!r} and carries no explicit addressee adjudication")
            addressee, basis = explicit, "adjudicated"
        elif pre in EXACT_PREFIX:
            if explicit is not None and explicit != EXACT_PREFIX[pre]:
                sys.exit(f"build refuses: SPEC.md:{c['line']} declares addressee "
                         f"{explicit!r} against exact prefix {pre!r} -> {EXACT_PREFIX[pre]!r}")
            addressee, basis = EXACT_PREFIX[pre], "derived-from-token-prefix"
        else:
            sys.exit(f"build refuses: SPEC.md:{c['line']} token prefix {pre!r} is in "
                     f"neither EXACT_PREFIX nor AMBIGUOUS_PREFIX")
        entries.append({
            "obligation_id": f"SPEC-{n:02d}",
            "source_span": f"SPEC.md:{c['line']}",
            "section": c["section"],
            "normative_text": c["text"],
            "property_token": token,
            "addressee": addressee,
            "addressee_basis": basis,
            "refusal_site": site,
            "evaluation_sites": pick(bind.get(site, []), token) if site else [],
            "status": status,
            "rationale": why,
        })
    doc = {
        "ledger_version": "1",
        "spec": "SPEC.md",
        "note": "Derived by tools/build_obligations.py. Human judgement is confined to its MAPPING table; spans, clause text and evaluation sites are extracted from the artifacts.",
        "obligations": entries,
    }
    (ROOT/"obligations.json").write_text(json.dumps(doc, indent=1) + "\n")
    tally = collections.Counter(e["status"] for e in entries)
    who = collections.Counter(e["addressee"] for e in entries)
    print(f"  wrote obligations.json: {len(entries)} obligations {dict(tally)}")
    print(f"  by addressee: {dict(who)}")

if __name__ == "__main__":
    main()
