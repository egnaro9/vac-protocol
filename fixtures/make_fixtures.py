"""Deterministic generator for the committed verifier fixtures.

One VALID miniature bundle — fully synthetic (fictional issuer
`example/toy-issuer`, fictional subject `toy-agent`), self-contained, and
carrying one check per evidence profile so the single valid fixture
exercises every clean path in the verifier — plus eight tampered variants,
each the valid bundle with exactly one edit, each tripping exactly one
named failure class:

  tamper-missing-artifact       artifact listed in the manifest, file gone
  tamper-wrong-sha256           manifest hash disagrees with the file bytes
  tamper-verdict-count          declared `fixed` count inflated over honest
                                artifacts (the artifact still hashes clean)
  tamper-empty-limitations      claim.limitations = []
  tamper-missing-issuer-commit  replay block lost its pinned commit
  tamper-raw-aggregate          aggregate row inflated AND re-hashed — the
                                realistic attack: cook the board, fix the
                                hash, hope nobody recomputes from raw
  tamper-evalmut-summary        mutation tally cooked AND re-hashed, rows
                                honest — only recomputation from the rows
                                names the lie
  tamper-evalmut-rows           a missed mutation relabeled caught in the
                                rows AND re-hashed — tally, score, holes,
                                and the declared counts all contradict the
                                rows they must recompute from

Byte-reproducible by construction: no timestamps, no randomness, stable
key order. `python fixtures/make_fixtures.py [out_dir]` regenerates
everything; tests assert the committed fixtures match a fresh run.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import sys

COMMIT = "f1e2d3c"
TASKSET_HASH = "00112233445566aa"
PROMPT_HASH = "aabbccdd00112233"
SUITE_HASH = "ffeeddcc99887766"


def _j(obj) -> str:
    return json.dumps(obj, indent=1) + "\n"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _certlab_bundle() -> dict:
    """agent-certlab-shaped bundle.json: 3 verdicts, 2 fixed."""
    diff1 = ("--- issued/toy.py\n+++ after/toy.py\n@@ -1 +1 @@\n"
             "-def contains(lo, hi, x): return lo <= x <= hi\n"
             "+def contains(lo, hi, x): return lo <= x < hi\n")
    diff2 = ("--- issued/toy.py\n+++ after/toy.py\n@@ -2 +2 @@\n"
             "-def positive(n): return n < 0\n"
             "+def positive(n): return n > 0\n")
    return {
        "schema": 1,
        "agent_id": "toy-agent",
        "agent_kind": "synthetic",
        "model": None,
        "harness_commit": COMMIT,
        "taskset_hash": TASKSET_HASH,
        "prompt_hash": PROMPT_HASH,
        "grading": "artifacts-only; policy (suite byte-identical, allowed "
                   "paths) then tests; fixed = both",
        "verdicts": [
            {"task_id": "toy-off-by-one",
             "defect_class": "boundary/off-by-one",
             "policy_ok": True, "tests_ok": True, "fixed": True,
             "failure_mode": "", "changed_files": ["toy.py"],
             "diffs": {"toy.py": diff1},
             "agent_note": "exit 0"},
            {"task_id": "toy-inverted-guard",
             "defect_class": "inverted-condition",
             "policy_ok": True, "tests_ok": True, "fixed": True,
             "failure_mode": "", "changed_files": ["toy.py"],
             "diffs": {"toy.py": diff2},
             "agent_note": "exit 0"},
            {"task_id": "toy-swapped-args",
             "defect_class": "argument-order",
             "policy_ok": True, "tests_ok": False, "fixed": False,
             "failure_mode": "tests-failed", "changed_files": [],
             "diffs": {},
             "agent_note": "exit 0; no edit made"},
        ],
    }


def _fleet_board() -> tuple[dict, str]:
    """reference-fleet-shaped results.json + raw_results.jsonl text."""
    raw = (
        [{"suite": "toy-suite", "member": "toy-defect-a", "i": i,
          "defective_failed": True, "clean_passed": True, "detected": True}
         for i in range(4)]
        + [{"suite": "toy-suite", "member": "toy-defect-b", "i": 0,
            "defective_failed": True, "clean_passed": True, "detected": True},
           {"suite": "toy-suite", "member": "toy-defect-b", "i": 1,
            "defective_failed": True, "clean_passed": True, "detected": True},
           {"suite": "toy-suite", "member": "toy-defect-b", "i": 2,
            "defective_failed": False, "clean_passed": True, "detected": False},
           {"suite": "toy-suite", "member": "toy-defect-b", "i": 3,
            "defective_failed": True, "clean_passed": False, "detected": False}]
    )
    agg = {
        "schema": 1,
        "protocol": "paired: detected = defective fails AND clean passes; "
                    "rates exact over the fixed request set",
        "fleet_commit": COMMIT,
        "rows": [
            {"suite": "toy-suite", "member": "toy-defect-a", "n": 4,
             "detected": 4, "detection_rate": 1.0,
             "false_alarms": 0, "false_alarm_rate": 0.0, "engine": "python"},
            {"suite": "toy-suite", "member": "toy-defect-b", "n": 4,
             "detected": 2, "detection_rate": 0.5,
             "false_alarms": 1, "false_alarm_rate": 0.25, "engine": "python"},
        ],
    }
    raw_text = "\n".join(json.dumps(r, separators=(",", ":"))
                         for r in raw) + "\n"
    return agg, raw_text


def _evalmut_run() -> tuple[dict, list[dict]]:
    """evalmut-shaped `run --json --all` payload + `operators --json`
    catalog: 8 rows over 5 toy operators, leaving one hole of each
    surviving class (blind, brittle, coverage gap) so every recomputation
    path is live."""
    ops = [
        {"id": "toy-blank", "family": "truncation", "polarity": "defect",
         "op_type": "sanity", "field": "output",
         "defect_shape": "blank output in place of the answer",
         "real_origin": "toy corpus: a grader that passed an empty reply"},
        {"id": "toy-truncate", "family": "truncation", "polarity": "defect",
         "op_type": "kill", "field": "output",
         "defect_shape": "reply cut off before it reaches the answer",
         "real_origin": "toy corpus: a token-cap truncation shipped green"},
        {"id": "toy-negate", "family": "presence-proxy", "polarity": "defect",
         "op_type": "kill", "field": "output",
         "defect_shape": "the checked keyword appears, but negated",
         "real_origin": "toy corpus: a gate that greps for a token its own "
                        "block message contains"},
        {"id": "toy-typeflip", "family": "json", "polarity": "defect",
         "op_type": "diagnostic", "field": "output",
         "defect_shape": "json value type flipped under a key-presence check",
         "real_origin": "toy corpus: a schema check that reads keys, "
                        "never values"},
        {"id": "toy-disclaimer", "family": "equivalent",
         "polarity": "equivalent", "op_type": "kill", "field": "output",
         "defect_shape": "trailing disclaimer after a complete answer",
         "real_origin": "toy corpus: a verbatim matcher that failed "
                        "appended boilerplate"},
    ]
    by_id = {o["id"]: o for o in ops}

    def row(case, grader, op_id, outcome, detail, preview=""):
        op = by_id[op_id]
        return {"case_name": case, "grader_id": grader,
                "operator_id": op_id, "family": op["family"],
                "polarity": op["polarity"], "op_type": op["op_type"],
                "outcome": outcome, "real_origin": op["real_origin"],
                "defect_shape": op["defect_shape"], "detail": detail,
                "mutant_preview": preview, "grader_error": None}

    rows = [
        row("toy-exact", "exact", "toy-blank", "caught", "rejected blank"),
        row("toy-exact", "exact", "toy-truncate", "caught",
            "rejected the cut-off reply"),
        row("toy-exact", "exact", "toy-disclaimer", "flagged",
            "failed a still-correct output", "42 (not financial advice)"),
        row("toy-exact", "exact", "toy-typeflip", "na",
            "n/a: operator not applicable here"),
        row("toy-contains", "contains", "toy-negate", "missed",
            "needs all of ['capital']", "I did NOT name the capital."),
        row("toy-contains", "contains", "toy-typeflip", "missed",
            "value type flipped, key still present"),
        row("toy-contains", "contains", "toy-blank", "caught",
            "rejected blank"),
        row("toy-contains", "contains", "toy-disclaimer", "caught",
            "accepted the equivalent"),
    ]
    counts = {k: sum(1 for r in rows if r["outcome"] == k)
              for k in ("caught", "missed", "flagged", "error", "na")}
    applied = counts["caught"] + counts["missed"] + counts["flagged"]
    payload = {
        "score": counts["caught"] / applied,
        "tally": counts,
        "holes": {
            "vacuous": [r for r in rows if r["outcome"] == "missed"
                        and r["op_type"] == "sanity"],
            "blind": [r for r in rows if r["outcome"] == "missed"
                      and r["op_type"] == "kill"],
            "error": [r for r in rows if r["outcome"] == "error"],
            "brittle": [r for r in rows if r["outcome"] == "flagged"],
            "coverage_gap": [r for r in rows if r["outcome"] == "missed"
                             and r["op_type"] == "diagnostic"],
        },
        "baseline_failures": [],
        "results": rows,
    }
    return payload, ops


def valid_bundle() -> dict[str, str]:
    """{relative path: file text} for the valid fixture."""
    agg, raw_text = _fleet_board()
    mut_payload, mut_ops = _evalmut_run()
    mut_tally = mut_payload["tally"]
    mut_applied = (mut_tally["caught"] + mut_tally["missed"]
                   + mut_tally["flagged"])
    evidence = {
        "evidence/bundle.json": _j(_certlab_bundle()),
        "evidence/results.json": _j(agg),
        "evidence/raw_results.jsonl": raw_text,
        "evidence/evalmut_run.json": _j(mut_payload),
        "evidence/operators.json": _j(mut_ops),
    }
    manifest = {
        "vac_version": "0.1",
        "claim": {
            "capability": "toy-agent fixes seeded single-edit defects in the "
                          "toy substrate, the toy board detects the toy "
                          "fleet's defect classes, and the toy suite's "
                          "mutation holes are exactly what its rows "
                          "recompute to",
            "scope": "exactly the synthetic task set, request set, and "
                     "suite named by protocol.hashes; artifacts-only "
                     "deterministic grading; nothing beyond it",
            "limitations": [
                "synthetic fixture: issuer and subject are fictional; this "
                "bundle exercises the verifier, not a real agent",
                "single-file, single-edit defects only; multi-file repair "
                "is not claimed",
                "board rows cover the two toy defect classes only",
                "mutation rows cover the five toy operators only; the "
                "three surviving holes are the finding, not a defect of "
                "the fixture",
            ],
        },
        "subject": {
            "kind": "agent",
            "id": "toy-agent",
            "version": {"build": "toy-1", "model": None},
        },
        "protocol": {
            "issuer": "example/toy-issuer",
            "issuer_commit": COMMIT,
            "task": "toy-intervals + toy-board + toy-mutation-run",
            "hashes": {"taskset_hash": TASKSET_HASH,
                       "prompt_hash": PROMPT_HASH,
                       "fleet_commit": COMMIT,
                       "suite_hash": SUITE_HASH},
            "grading": "deterministic: policy (suite byte-identical) then "
                       "tests; board rows recomputed from paired raw lines; "
                       "mutation tallies and holes recomputed from per-row "
                       "outcomes",
            "control_policy": "null-agent scores 0/3 and oracle-agent 3/3 "
                              "before any real verdict; a clean twin is "
                              "graded beside every defective response",
        },
        "evidence": [
            {"path": p, "sha256": _sha(t)}
            for p, t in sorted(evidence.items())
        ],
        "results": {
            "summary": {"tasks": 3, "fixed": 2, "board_rows": 2,
                        "detection_rate_min": 0.5,
                        "mutation_score_3": round(
                            mut_tally["caught"] / mut_applied, 3),
                        "mutation_blind_spots": len(
                            mut_payload["holes"]["blind"])},
            "checks": [
                {"profile": "certlab-bundle-v1",
                 "artifact": "evidence/bundle.json",
                 "expect": {"verdicts": 3, "fixed": 2,
                            "policy_ok": 3, "tests_ok": 2}},
                {"profile": "fleet-board-v1",
                 "aggregate": "evidence/results.json",
                 "raw": "evidence/raw_results.jsonl",
                 "expect": {"rows": 2}},
                {"profile": "evalmut-run-v1",
                 "artifact": "evidence/evalmut_run.json",
                 "catalog": "evidence/operators.json",
                 "expect": {
                     **mut_tally,
                     "applied": mut_applied,
                     "results": len(mut_payload["results"]),
                     "score_3": round(mut_tally["caught"] / mut_applied, 3),
                     "vacuous": len(mut_payload["holes"]["vacuous"]),
                     "blind": len(mut_payload["holes"]["blind"]),
                     "brittle": len(mut_payload["holes"]["brittle"]),
                     "coverage_gap": len(
                         mut_payload["holes"]["coverage_gap"]),
                     "operators": len(mut_ops),
                     "operators_exercised": len(
                         {r["operator_id"]
                          for r in mut_payload["results"]}),
                 }},
            ],
        },
        "replay": {
            "issuer_commit": COMMIT,
            "commands": [
                "git clone https://github.com/example/toy-issuer issuer",
                f"git -C issuer checkout {COMMIT}",
                "python -m pip install -e ./issuer",
                "python -m toy_issuer.regrade evidence/bundle.json",
                "python issuer/audit/run_audit.py --check "
                "evidence/results.json",
                "python -m toy_issuer.mutrun --check "
                "evidence/evalmut_run.json",
            ],
            "expected": "regrade exits 0 reporting 'consistent'; audit and "
                        "mutrun reproduce results.json and evalmut_run.json "
                        "byte-identically at the stamped commit (mutrun "
                        "exits 1 by design: the toy suite has holes)",
        },
    }
    return {"vac.json": _j(manifest), **evidence}


def tampered_variants(valid: dict[str, str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}

    t = dict(valid)  # artifact listed, file gone
    del t["evidence/bundle.json"]
    out["tamper-missing-artifact"] = t

    m = json.loads(valid["vac.json"])  # manifest hash disagrees with bytes
    assert m["evidence"][0]["path"] == "evidence/bundle.json"
    m["evidence"][0]["sha256"] = "0" * 64
    out["tamper-wrong-sha256"] = {**valid, "vac.json": _j(m)}

    m = json.loads(valid["vac.json"])  # declared count inflated, 2 -> 3
    m["results"]["checks"][0]["expect"]["fixed"] = 3
    m["results"]["summary"]["fixed"] = 3
    out["tamper-verdict-count"] = {**valid, "vac.json": _j(m)}

    m = json.loads(valid["vac.json"])  # a claim with no non-claims
    m["claim"]["limitations"] = []
    out["tamper-empty-limitations"] = {**valid, "vac.json": _j(m)}

    m = json.loads(valid["vac.json"])  # replay lost its pin
    del m["replay"]["issuer_commit"]
    out["tamper-missing-issuer-commit"] = {**valid, "vac.json": _j(m)}

    # cook the board AND fix the hash — only recomputation from raw catches it
    agg = json.loads(valid["evidence/results.json"])
    row = next(r for r in agg["rows"] if r["member"] == "toy-defect-b")
    row["detected"], row["detection_rate"] = 3, 0.75
    agg_text = _j(agg)
    m = json.loads(valid["vac.json"])
    for e in m["evidence"]:
        if e["path"] == "evidence/results.json":
            e["sha256"] = _sha(agg_text)
    out["tamper-raw-aggregate"] = {**valid,
                                   "evidence/results.json": agg_text,
                                   "vac.json": _j(m)}

    def _rehash_mut(mp: dict) -> dict[str, str]:
        text = _j(mp)
        man = json.loads(valid["vac.json"])
        for e in man["evidence"]:
            if e["path"] == "evidence/evalmut_run.json":
                e["sha256"] = _sha(text)
        return {**valid, "evidence/evalmut_run.json": text,
                "vac.json": _j(man)}

    # cook the mutation tally AND fix the hash, rows honest — only
    # recomputation from the rows names the lie
    mp = json.loads(valid["evidence/evalmut_run.json"])
    mp["tally"]["caught"] = 5
    out["tamper-evalmut-summary"] = _rehash_mut(mp)

    # relabel a missed mutation as caught in the rows AND fix the hash —
    # the realistic attack on a mutation report: one label flipped, all
    # aggregates left at their published values
    mp = json.loads(valid["evidence/evalmut_run.json"])
    r = next(r for r in mp["results"] if r["operator_id"] == "toy-negate")
    r["outcome"] = "caught"
    out["tamper-evalmut-rows"] = _rehash_mut(mp)
    return out


def main(out_dir: pathlib.Path) -> None:
    valid = valid_bundle()
    bundles = {"valid": valid, **tampered_variants(valid)}
    for name, files in sorted(bundles.items()):
        d = out_dir / name
        if d.exists():
            shutil.rmtree(d)
        for rel, text in sorted(files.items()):
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        print(f"{name}: {len(files)} file(s)")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1
         else pathlib.Path(__file__).resolve().parent)
