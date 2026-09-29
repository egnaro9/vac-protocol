"""Emit a finding when the weekly registry replay outcome changes.

`replay.yml` is the second acceptance gate. Every Monday it re-downloads all
accepted registry entries at their pinned URLs, refuses any byte that does not
hash to its pin, re-runs structural verification, and executes each bundle's
own replay block at the pinned issuer commit. It produces a dated, falsifiable
result every week, and that result has had nowhere to go.

This reads replay's OWN per-entry conclusions and reports only when they change
against a committed baseline. It deliberately re-derives nothing: replay's
matrix names each job after the registry entry it replays, so the conclusion of
job "model-drift/vac" IS replay's verdict on that entry, decided by replay's
own predicates. Re-implementing any of that here would create a second opinion
about what a replay means, and the whole point of the gate is that there is
one.

A pass that passed last week is not news. Most weeks this emits nothing, which
is correct: an instrument that always has something to say is measuring itself.

Writes notes/findings.json in the schema modeldrift/external.py accepts. It
does not publish anything. model-drift decides whether a validated finding
becomes a draft pull request, and a human decides whether that draft is posted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "drift-notes/finding@1"
SOURCE = "vac-protocol"
WORKFLOW = "replay.yml"

# Jobs that are scaffolding for the matrix rather than a verdict on an entry.
# `pending` is a verdict, and a named one, so it is kept.
NOT_AN_ENTRY = {"entries"}

# modeldrift/external.py bounds. Mirrored as a guard, never as a substitute for
# validating against the real thing.
MAX_FINDINGS = 25
MAX_EVIDENCE = 12


def latest_outcome(repo: Optional[str] = None) -> Dict[str, Any]:
    """The most recent COMPLETED replay run, as {job name: conclusion}.

    In progress runs are skipped. A run that has not finished has no verdict,
    and treating its absent conclusions as a change would report a finding
    every Monday morning while the gate was still running.
    """
    args = ["gh", "run", "list", "--workflow", WORKFLOW, "--limit", "10",
            "--json", "databaseId,status,conclusion,createdAt"]
    if repo:
        args += ["--repo", repo]
    runs = json.loads(subprocess.run(args, capture_output=True, text=True,
                                     check=True).stdout)
    done = [r for r in runs if r.get("status") == "completed"]
    if not done:
        raise RuntimeError("no completed replay run found")
    run = done[0]

    jargs = ["gh", "run", "view", str(run["databaseId"]), "--json", "jobs"]
    if repo:
        jargs += ["--repo", repo]
    jobs = json.loads(subprocess.run(jargs, capture_output=True, text=True,
                                     check=True).stdout)["jobs"]
    entries = {j["name"]: j.get("conclusion") or "unknown"
               for j in jobs if j["name"] not in NOT_AN_ENTRY}
    return {"run_id": run["databaseId"],
            "when": (run.get("createdAt") or "")[:10],
            "run_conclusion": run.get("conclusion") or "unknown",
            "entries": dict(sorted(entries.items()))}


def summary_of(outcome: Dict[str, Any]) -> Dict[str, str]:
    """The compact, order independent thing that gets compared.

    Deliberately excludes run_id and date. Those change every week and would
    make every run look like a change, which is the failure this file exists
    to avoid.
    """
    return dict(sorted((outcome.get("entries") or {}).items()))


def diff(baseline: Dict[str, str], current: Dict[str, str]) -> Dict[str, List]:
    """What moved. Entries added or removed are changes in their own right."""
    changed = [(k, baseline[k], current[k])
               for k in sorted(set(baseline) & set(current))
               if baseline[k] != current[k]]
    return {"changed": changed,
            "added": sorted(set(current) - set(baseline)),
            "removed": sorted(set(baseline) - set(current))}


def _is_material(d: Dict[str, List]) -> bool:
    return bool(d["changed"] or d["added"] or d["removed"])


def build_finding(outcome: Dict[str, Any], baseline: Dict[str, str],
                  current: Dict[str, str], d: Dict[str, List]) -> Dict[str, Any]:
    """One finding describing the whole transition.

    One rather than one per entry, because a replay run is a single event: if
    four entries fail on the same Monday, that is one thing that happened, and
    four findings would be four posts about it.
    """
    failing = sorted(k for k, v in current.items() if v != "success")
    recovered = [k for k, was, now in d["changed"] if was != "success" and now == "success"]
    broke = [k for k, was, now in d["changed"] if was == "success" and now != "success"]

    if broke:
        head = (f"{len(broke)} registry entr{'y' if len(broke) == 1 else 'ies'} "
                f"stopped replaying: {', '.join(broke[:3])}")
    elif recovered:
        one = len(recovered) == 1
        head = (f"{len(recovered)} registry entr{'y' if one else 'ies'} "
                f"replay{'s' if one else ''} again: {', '.join(recovered[:3])}")
    elif d["added"]:
        head = f"{len(d['added'])} new registry entr{'y' if len(d['added']) == 1 else 'ies'} in the weekly replay"
    else:
        head = f"{len(d['removed'])} registry entr{'y' if len(d['removed']) == 1 else 'ies'} left the weekly replay"

    evidence: List[Dict[str, str]] = [
        {"claim": "the weekly independent replay outcome changed",
         "how": f"run {outcome['run_id']} on {outcome['when']}, workflow {WORKFLOW}, "
                f"overall {outcome['run_conclusion']}"},
    ]
    for name, was, now in d["changed"][:6]:
        evidence.append({"claim": f"{name} went from {was} to {now}",
                         "how": f"job '{name}' in replay run {outcome['run_id']}; "
                                f"the baseline recorded {was}"})
    for name in d["added"][:2]:
        evidence.append({"claim": f"{name} appears in the replay for the first time",
                         "how": f"absent from notes/baseline.json, present in run {outcome['run_id']}"})
    for name in d["removed"][:2]:
        evidence.append({"claim": f"{name} is no longer replayed",
                         "how": f"present in notes/baseline.json, absent from run {outcome['run_id']}"})
    if failing:
        one = len(failing) == 1
        evidence.append({"claim": f"{len(failing)} entr{'y' if one else 'ies'} "
                                  f"{'is' if one else 'are'} not currently replaying",
                         "how": f"not-success conclusions: {', '.join(failing[:5])}"})
    # Root cause is deliberately not asserted. A job conclusion says the gate
    # refused; it does not say whether the artifact 404d, a hash drifted,
    # structural verification refused, or the replay block itself failed.
    evidence.append({"claim": "the cause is not established by this signal alone",
                     "how": "a job conclusion records that the gate refused, not which "
                            "of its steps refused; the run log distinguishes them"})

    return {
        "kind": "replay-change",
        # The subject is the verification gate and the claims it checks, never
        # a model. Filing it otherwise would be the category error the
        # receiving parser refuses outright.
        "about": "harness",
        "subject": "registry-replay",
        "headline": head[:200],
        # Identity is the state arrived at, not the week it was noticed, so a
        # standing failure is reported once and its recovery is reported once.
        "run_key": [_state_key(current)],
        "when": outcome["when"],
        "evidence": evidence[:MAX_EVIDENCE],
    }


def _state_key(current: Dict[str, str]) -> str:
    """Identity of the outcome SET, hashed rather than truncated.

    The obvious version, the serialised summary cut to the field limit, is not
    an identity: two outcomes that differ past the cut share a key, and the
    second is dropped as already-reported. Truncating a value that has to be
    unique is how a partial secret defeated CI masking in this estate once
    already, and the shape of the mistake is the same.
    """
    blob = json.dumps(current, sort_keys=True).encode()
    return f"replay@{hashlib.sha256(blob).hexdigest()[:16]}"


def emit(outcome: Dict[str, Any], baseline_path: Path, out_path: Path,
         acknowledge: bool = False) -> Tuple[int, str]:
    """(finding count, message). Writes nothing on an unchanged outcome."""
    current = summary_of(outcome)
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8")).get("entries", {})
    else:
        # First sight is not a finding. There is nothing to have changed from,
        # and calling a baseline a discovery is how a tripwire becomes an
        # announcement.
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps({"entries": current, "acknowledged_run": outcome["run_id"],
                        "acknowledged_on": outcome["when"]}, indent=1, sort_keys=True) + "\n",
            encoding="utf-8")
        return 0, f"baseline written from run {outcome['run_id']}, {len(current)} entries"

    d = diff(baseline, current)
    if not _is_material(d):
        return 0, f"unchanged: {len(current)} entries, all matching the baseline"

    payload = {"schema": SCHEMA, "source": SOURCE,
               "generated": outcome["when"],
               "findings": [build_finding(outcome, baseline, current, d)][:MAX_FINDINGS]}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")

    if acknowledge:
        # Only ever on an explicit human acknowledgement. Advancing the
        # baseline automatically after a failure would record the change and
        # erase it in the same run, so the next week would read as healthy and
        # the finding would never be reported again.
        baseline_path.write_text(
            json.dumps({"entries": current, "acknowledged_run": outcome["run_id"],
                        "acknowledged_on": outcome["when"]}, indent=1, sort_keys=True) + "\n",
            encoding="utf-8")
        return 1, f"finding written and baseline acknowledged at run {outcome['run_id']}"
    return 1, f"finding written from run {outcome['run_id']}; baseline left as is"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", default="notes/baseline.json")
    ap.add_argument("--out", default="notes/findings.json")
    ap.add_argument("--repo", default=None, help="owner/name, for running outside the repo")
    ap.add_argument("--from-file", default=None,
                    help="read an outcome from JSON instead of calling gh; for tests")
    ap.add_argument("--acknowledge", action="store_true",
                    help="advance the baseline to the current outcome. Human action only: "
                         "never set this in CI, or a change is recorded and erased together.")
    a = ap.parse_args(argv)

    outcome = (json.loads(Path(a.from_file).read_text(encoding="utf-8"))
               if a.from_file else latest_outcome(a.repo))
    n, msg = emit(outcome, Path(a.baseline), Path(a.out), a.acknowledge)
    print(f"  {msg}")
    print(f"\n{n} finding(s)" + ("" if n else " - the replay outcome is what it was, which is a result"))
    # Always 0. An unchanged week is the expected outcome and must not read as
    # a broken job.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
