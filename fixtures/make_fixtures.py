"""Deterministic generator for the committed verifier fixtures.

One VALID miniature bundle — fully synthetic (fictional issuer
`example/toy-issuer`, fictional subject `toy-agent`), self-contained, and
carrying one artifact per evidence profile so the single valid fixture
exercises every clean path in the verifier — plus six tampered variants,
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


def valid_bundle() -> dict[str, str]:
    """{relative path: file text} for the valid fixture."""
    agg, raw_text = _fleet_board()
    evidence = {
        "evidence/bundle.json": _j(_certlab_bundle()),
        "evidence/results.json": _j(agg),
        "evidence/raw_results.jsonl": raw_text,
    }
    manifest = {
        "vac_version": "0.1",
        "claim": {
            "capability": "toy-agent fixes seeded single-edit defects in the "
                          "toy substrate, and the toy board detects the toy "
                          "fleet's defect classes",
            "scope": "exactly the synthetic task set and request set named "
                     "by protocol.hashes; artifacts-only deterministic "
                     "grading; nothing beyond it",
            "limitations": [
                "synthetic fixture: issuer and subject are fictional; this "
                "bundle exercises the verifier, not a real agent",
                "single-file, single-edit defects only; multi-file repair "
                "is not claimed",
                "board rows cover the two toy defect classes only",
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
            "task": "toy-intervals + toy-board",
            "hashes": {"taskset_hash": TASKSET_HASH,
                       "prompt_hash": PROMPT_HASH,
                       "fleet_commit": COMMIT},
            "grading": "deterministic: policy (suite byte-identical) then "
                       "tests; board rows recomputed from paired raw lines",
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
                        "detection_rate_min": 0.5},
            "checks": [
                {"profile": "certlab-bundle-v1",
                 "artifact": "evidence/bundle.json",
                 "expect": {"verdicts": 3, "fixed": 2,
                            "policy_ok": 3, "tests_ok": 2}},
                {"profile": "fleet-board-v1",
                 "aggregate": "evidence/results.json",
                 "raw": "evidence/raw_results.jsonl",
                 "expect": {"rows": 2}},
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
            ],
            "expected": "regrade exits 0 reporting 'consistent'; audit "
                        "reproduces results.json byte-identically at the "
                        "stamped commit",
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
