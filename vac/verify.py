"""Structural verifier for VAC capability evidence bundles (SPEC.md v0.1).

Verifies what a bundle can prove OFFLINE, with zero network and zero issuer
code: the manifest is schema-valid, every listed artifact is present and
sha256-identical to its manifest entry, the bundle is closed (no unlisted
files riding along), limitations are stated, stamps agree, and every
declared result is recomputed from the artifacts themselves under the
evidence-profile rules of SPEC.md §3.

What it deliberately does NOT prove: that the issuer's grader would emit
these verdicts. That is SEMANTIC REPLAY — clone the issuer at the pinned
commit and run its deterministic regrader/audit — and the bundle's replay
block records the exact commands. This tool prints that distinction on
every run so a green check is never mistaken for a replay.

One refusal precedes all of that: a manifest still carrying one of
vac.draft's `TODO(` markers is a DRAFT — a workpiece, not a claim — and is
refused wholesale (`draft-incomplete`, one named reason per marker) before
any other verification runs.

`python -m vac.verify <bundle-dir | bundle.tar.gz>` — exit 0 only when
structurally clean; otherwise one named reason per failure, all of them.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import tarfile
import tempfile

VAC_VERSION = "0.1"
PROFILES = ("certlab-bundle-v1", "fleet-board-v1", "evalmut-run-v1",
            "crashkit-battery-v1", "modeldrift-board-v1")
USAGE = "usage: python -m vac.verify <bundle-dir | bundle.tar.gz>"


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_hex64(v) -> bool:
    return (isinstance(v, str) and len(v) == 64
            and all(c in "0123456789abcdef" for c in v))


def _nonempty_str(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _safe_relpath(p) -> bool:
    """Relative, forward-slash, no traversal, not the manifest itself."""
    if not _nonempty_str(p) or p == "vac.json" or "\\" in p:
        return False
    if any(c < " " or c == "\x7f" for c in p):
        return False  # control chars: a terminal-injection channel
    # A drive-anchored name ("C:/x", "C:x") is NOT absolute under
    # PurePosixPath but IS under Windows semantics, where `bundle / "C:/x"`
    # discards the bundle root entirely and reads outside the bundle.
    win = pathlib.PureWindowsPath(p)
    if win.drive or win.is_absolute():
        return False
    pp = pathlib.PurePosixPath(p)
    return bool(pp.parts) and not pp.is_absolute() and ".." not in pp.parts


# --------------------------------------------------------------------------
# Drafts (SPEC.md §2.7): a string value beginning `TODO(` is vac.draft's
# unauthored-judgment marker. A manifest still carrying one is a draft —
# refused wholesale, before any other verification, one named reason per
# marker; nothing else about an unauthored manifest is worth naming.
_TODO_PREFIX = "TODO("


def _todo_failures(m) -> list[str]:
    f: list[str] = []

    def walk(node, path):
        if isinstance(node, dict):
            for k in sorted(node):
                walk(node[k], f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and node.startswith(_TODO_PREFIX):
            f.append(f"draft-incomplete: {path} is an unauthored TODO")

    walk(m, "")
    return f


# --------------------------------------------------------------------------
# Schema (SPEC.md §2) — stdlib only; every violation is one named line.
def _validate_manifest(m: dict) -> list[str]:
    f: list[str] = []

    def need(obj, path, pred, what):
        leaf = path.rsplit(".", 1)[-1]
        v = obj.get(leaf) if isinstance(obj, dict) else None
        if not pred(v):
            f.append(f"schema-violation: {path}: {what}")
            return None
        return v

    if m.get("vac_version") != VAC_VERSION:
        f.append(f"schema-violation: vac_version: must be {VAC_VERSION!r}, "
                 f"got {m.get('vac_version')!r}")

    claim = need(m, "claim", lambda v: isinstance(v, dict),
                 "object required") or {}
    need(claim, "claim.capability", _nonempty_str, "non-empty string required")
    need(claim, "claim.scope", _nonempty_str, "non-empty string required")
    lims = claim.get("limitations")
    if not (isinstance(lims, list) and lims
            and all(_nonempty_str(x) for x in lims)):
        # a claim with no stated non-claims is an advertisement, not a claim
        f.append("empty-limitations")

    subject = need(m, "subject", lambda v: isinstance(v, dict),
                   "object required") or {}
    if subject.get("kind") not in ("agent", "suite-archetype"):
        f.append("schema-violation: subject.kind: "
                 "must be 'agent' or 'suite-archetype'")
    need(subject, "subject.id", _nonempty_str, "non-empty string required")
    if not (isinstance(subject.get("version"), dict) and subject["version"]):
        f.append("schema-violation: subject.version: at least one pinned "
                 "identifier required — an unpinned subject is unverifiable")

    proto = need(m, "protocol", lambda v: isinstance(v, dict),
                 "object required") or {}
    for k in ("issuer", "issuer_commit", "task", "grading", "control_policy"):
        need(proto, f"protocol.{k}", _nonempty_str, "non-empty string required")
    hashes = proto.get("hashes")
    if not (isinstance(hashes, dict) and hashes
            and all(_nonempty_str(v) for v in hashes.values())):
        f.append("schema-violation: protocol.hashes: at least one named "
                 "content hash required")

    ev = m.get("evidence")
    if not (isinstance(ev, list) and ev):
        f.append("schema-violation: evidence: non-empty array required")
    else:
        seen: set[str] = set()
        for i, e in enumerate(ev):
            if not isinstance(e, dict) or not _safe_relpath(e.get("path")):
                f.append(f"schema-violation: evidence[{i}].path: safe "
                         "relative path required")
                continue
            if not _is_hex64(e.get("sha256")):
                f.append(f"schema-violation: evidence[{i}].sha256: 64 "
                         "lowercase hex chars required")
            if e["path"] in seen:
                f.append(f"duplicate-artifact: {e['path']}")
            seen.add(e["path"])

    results = need(m, "results", lambda v: isinstance(v, dict),
                   "object required") or {}
    if not isinstance(results.get("summary"), dict):
        f.append("schema-violation: results.summary: object required")
    checks = results.get("checks")
    if not (isinstance(checks, list) and checks):
        f.append("schema-violation: results.checks: at least one "
                 "profile check required")
    else:
        for i, c in enumerate(checks):
            if not isinstance(c, dict):
                f.append(f"schema-violation: results.checks[{i}]: "
                         "object required")
                continue
            prof = c.get("profile")
            if prof not in PROFILES:
                f.append(f"unknown-profile: results.checks[{i}]: {prof!r}")

    replay = need(m, "replay", lambda v: isinstance(v, dict),
                  "object required") or {}
    rc = replay.get("issuer_commit")
    if not _nonempty_str(rc):
        f.append("missing-issuer-commit")
    elif _nonempty_str(proto.get("issuer_commit")) and rc != proto["issuer_commit"]:
        f.append(f"issuer-commit-mismatch: replay {rc} != "
                 f"protocol {proto['issuer_commit']}")
    cmds = replay.get("commands")
    if not (isinstance(cmds, list) and cmds
            and all(_nonempty_str(c) for c in cmds)):
        f.append("schema-violation: replay.commands: non-empty list of "
                 "commands required")
    if not _nonempty_str(replay.get("expected")):
        f.append("schema-violation: replay.expected: expected outcome required")
    return f


# --------------------------------------------------------------------------
# Artifacts: presence, sha256, closure.
def _verify_artifacts(bundle_dir: pathlib.Path,
                      m: dict) -> tuple[list[str], set[str]]:
    """Returns (failures, paths whose bytes are hash-verified and usable)."""
    f: list[str] = []
    entries = [e for e in m.get("evidence") or []
               if isinstance(e, dict) and _safe_relpath(e.get("path"))]
    listed = {e["path"] for e in entries}
    trusted: set[str] = set()
    for e in entries:
        p = bundle_dir / e["path"]
        if not p.is_file():
            f.append(f"missing-artifact: {e['path']}")
            continue
        if not _is_hex64(e.get("sha256")):
            continue  # already named as a schema-violation
        actual = _sha256(p)
        if actual != e["sha256"]:
            f.append(f"sha256-mismatch: {e['path']}: "
                     f"manifest {e['sha256']}, file {actual}")
        else:
            trusted.add(e["path"])
    # closure: a verified bundle cannot smuggle content
    for p in sorted(bundle_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(bundle_dir).as_posix()
            if rel != "vac.json" and rel not in listed:
                f.append(f"unlisted-file: {rel}")
    return f, trusted


# --------------------------------------------------------------------------
# Evidence profiles (SPEC.md §3): declared numbers re-earned from artifacts.
def _load_json(bundle_dir: pathlib.Path, rel: str, f: list[str],
               want: type = dict):
    """`want` is the shape SPEC 3 gives this artifact.

    Without it a bare scalar (notably the literal `null`) parsed fine and
    carried no evidence, taking the failure path WITHOUT naming a failure;
    and an array reached a caller that calls .get() on it immediately.
    """
    try:
        data = json.loads((bundle_dir / rel).read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        f.append(f"artifact-unparsable: {rel}: {e}")
        return None
    if not isinstance(data, want):
        name = "an object" if want is dict else "an array"
        f.append(f"artifact-unparsable: {rel}: top level must be {name}")
        return None
    return data


def _check_certlab(bundle_dir: pathlib.Path, check: dict, proto: dict,
                   f: list[str]) -> dict[str, list] | None:
    art = check["artifact"]
    data = _load_json(bundle_dir, art, f)
    if data is None:
        return None
    verdicts = data.get("verdicts")
    if not isinstance(verdicts, list):
        f.append(f"artifact-unparsable: {art}: no verdicts[] array")
        return None
    recomputed = {
        "verdicts": len(verdicts),
        "fixed": sum(1 for v in verdicts if v.get("fixed") is True),
        "policy_ok": sum(1 for v in verdicts if v.get("policy_ok") is True),
        "tests_ok": sum(1 for v in verdicts if v.get("tests_ok") is True),
    }
    expect = check.get("expect")
    if not (isinstance(expect, dict) and expect):
        f.append("schema-violation: results.checks[certlab-bundle-v1].expect: "
                 "declared counts required")
    else:
        for k in sorted(expect):
            if k not in recomputed:
                f.append(f"summary-mismatch: {k}: not recomputable under "
                         "certlab-bundle-v1")
            elif expect[k] != recomputed[k]:
                f.append(f"summary-mismatch: {k}: declared {expect[k]}, "
                         f"recomputed {recomputed[k]}")
    # stamp binding (SPEC.md §2.3): one commit, one task set, no forks
    hashes = proto.get("hashes") if isinstance(proto.get("hashes"), dict) else {}
    for k in ("taskset_hash", "prompt_hash"):
        if k in hashes and k in data and hashes[k] != data[k]:
            f.append(f"stamp-mismatch: {k}: protocol {hashes[k]}, "
                     f"artifact {data[k]}")
    ic = proto.get("issuer_commit")
    if _nonempty_str(ic) and "harness_commit" in data \
            and data["harness_commit"] != ic:
        f.append(f"stamp-mismatch: harness_commit: protocol {ic}, "
                 f"artifact {data['harness_commit']}")
    # the summary pool (SPEC.md §2.5): the four counts plus per-failure-mode
    # counts over the verdicts — everything a headline may cite
    pool = {k: [v] for k, v in recomputed.items()}
    modes: dict[str, int] = {}
    for v in verdicts:
        if _nonempty_str(v.get("failure_mode")):
            modes[v["failure_mode"]] = modes.get(v["failure_mode"], 0) + 1
    for mode, cnt in modes.items():
        # A genuine mode name stays a bare pool key, so a headline citing it
        # is held STRICTLY to its own count. What is withheld is a mode whose
        # name collides with a recomputed field: issuer free text must not
        # redefine what `fixed`/`verdicts`/`policy_ok`/`tests_ok` are held to.
        if mode not in recomputed:
            pool.setdefault(mode, []).append(cnt)
    return pool


def _fleet_rates(lines: list) -> dict:
    n = len(lines)
    det = sum(1 for ln in lines if ln.get("detected") is True)
    fa = sum(1 for ln in lines if ln.get("clean_passed") is not True)
    return {"n": n, "detected": det, "false_alarms": fa,
            "detection_rate": round(det / n, 3),
            "false_alarm_rate": round(fa / n, 3)}


def _check_fleet(bundle_dir: pathlib.Path, check: dict, proto: dict,
                 f: list[str]) -> dict[str, list] | None:
    agg = _load_json(bundle_dir, check["aggregate"], f)
    raw_rel = check["raw"]
    try:
        raw = [json.loads(ln) for ln in
               (bundle_dir / raw_rel).read_text().splitlines() if ln.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        f.append(f"artifact-unparsable: {raw_rel}: {e}")
        return None
    if agg is None:
        return None
    rows = agg.get("rows")
    if not isinstance(rows, list):
        f.append(f"artifact-unparsable: {check['aggregate']}: no rows[] array")
        return None
    groups: dict[tuple, list] = {}
    for n, ln in enumerate(raw, 1):
        key = (ln.get("suite"), ln.get("member"))
        # the paired protocol is internal to each line, not taken on faith
        if ln.get("detected") != (ln.get("defective_failed") is True
                                  and ln.get("clean_passed") is True):
            f.append(f"raw-aggregate-mismatch: {key[0]}/{key[1]}: raw line "
                     f"{n} detected flag contradicts its own pair")
        groups.setdefault(key, []).append(ln)
    expect = check.get("expect")
    if isinstance(expect, dict):
        for k in sorted(expect):
            if k != "rows":
                f.append(f"summary-mismatch: {k}: not recomputable under "
                         "fleet-board-v1")
            elif expect[k] != len(rows):
                f.append(f"summary-mismatch: rows: declared {expect[k]}, "
                         f"recomputed {len(rows)}")
    seen: set[tuple] = set()
    for row in rows:
        key = (row.get("suite"), row.get("member"))
        if key in seen:
            f.append(f"raw-aggregate-mismatch: {key[0]}/{key[1]}: duplicate "
                     "aggregate row")
            continue
        seen.add(key)
        lines = groups.get(key)
        if not lines:
            f.append(f"raw-aggregate-mismatch: {key[0]}/{key[1]}: aggregate "
                     "row has no raw lines")
            continue
        for k, v in _fleet_rates(lines).items():
            if row.get(k) != v:
                f.append(f"raw-aggregate-mismatch: {key[0]}/{key[1]}: {k} "
                         f"declared {row.get(k)}, recomputed {v}")
    for key in groups:
        if key not in seen:
            f.append(f"raw-aggregate-mismatch: {key[0]}/{key[1]}: raw lines "
                     "with no aggregate row")
    ic = proto.get("issuer_commit")
    if _nonempty_str(ic) and "fleet_commit" in agg \
            and agg["fleet_commit"] != ic:
        f.append(f"stamp-mismatch: fleet_commit: protocol {ic}, "
                 f"artifact {agg['fleet_commit']}")
    # SPEC 2.3: hashes NAMED in protocol.hashes MUST equal their counterparts
    # inside the artifacts; SPEC 3.2 names fleet_commit for this profile.
    hashes = proto.get("hashes")
    if not isinstance(hashes, dict):
        hashes = {}
    if ("fleet_commit" in hashes and "fleet_commit" in agg
            and hashes["fleet_commit"] != agg["fleet_commit"]):
        f.append(f"stamp-mismatch: hashes.fleet_commit: protocol "
                 f"{hashes['fleet_commit']}, artifact "
                 f"{agg['fleet_commit']}")
    # the summary pool (SPEC.md §2.5), earned from RAW lines only — the
    # aggregate is the claim: per-(suite,member), per-suite, and whole-board
    # stats, so a headline may cite any honest grouping level
    pool: dict[str, list] = {"rows": [len(groups)],
                             "suites": [len({s for s, _ in groups})]}
    by_suite: dict = {}
    for (suite, _member), lines in groups.items():
        by_suite.setdefault(suite, []).extend(lines)
        for k, v in _fleet_rates(lines).items():
            pool.setdefault(k, []).append(v)
    for lines in by_suite.values():
        stats = _fleet_rates(lines)
        stats["members"] = len({ln.get("member") for ln in lines})
        for k, v in stats.items():
            pool.setdefault(k, []).append(v)
    if raw:
        for k, v in _fleet_rates(raw).items():
            pool.setdefault(k, []).append(v)
    return pool


# evalmut hole classes: name -> (outcome, op_type or None) over the rows.
_EVALMUT_HOLES = (("vacuous", "missed", "sanity"),
                  ("blind", "missed", "kill"),
                  ("error", "error", None),
                  ("brittle", "flagged", None),
                  ("coverage_gap", "missed", "diagnostic"))


def _check_evalmut(bundle_dir: pathlib.Path, check: dict, proto: dict,
                   f: list[str]) -> dict[str, list] | None:
    art = check["artifact"]
    data = _load_json(bundle_dir, art, f)
    if data is None:
        return None
    rows = data.get("results")
    if not isinstance(rows, list) or not all(isinstance(r, dict)
                                             for r in rows):
        # without the per-mutation rows nothing is recomputable — the
        # aggregate alone is a declaration, not evidence
        f.append(f"artifact-unparsable: {art}: no results[] array "
                 "(evalmut-run-v1 requires the --json --all payload)")
        return None
    tally = data.get("tally")
    if not isinstance(tally, dict):
        f.append(f"artifact-unparsable: {art}: no tally object")
        return None
    holes = data.get("holes")
    if not isinstance(holes, dict):
        f.append(f"artifact-unparsable: {art}: no holes object")
        return None
    # outcome semantics are internal to each row, not taken on faith:
    # MISSED is only meaningful for a defect, FLAGGED only for an equivalent
    for n, r in enumerate(rows, 1):
        if (r.get("outcome") == "missed" and r.get("polarity") != "defect") \
                or (r.get("outcome") == "flagged"
                    and r.get("polarity") != "equivalent"):
            f.append(f"raw-aggregate-mismatch: {art}: row {n} outcome "
                     f"{r.get('outcome')!r} contradicts its polarity "
                     f"{r.get('polarity')!r}")
    counts = {k: sum(1 for r in rows if r.get("outcome") == k)
              for k in ("caught", "missed", "flagged", "error", "na")}
    for k, v in counts.items():
        if tally.get(k) != v:
            f.append(f"raw-aggregate-mismatch: {art}: tally.{k} declared "
                     f"{tally.get(k)}, recomputed {v}")
    applied = counts["caught"] + counts["missed"] + counts["flagged"]
    score = 1.0 if applied == 0 else counts["caught"] / applied
    if data.get("score") != score:
        f.append(f"raw-aggregate-mismatch: {art}: score declared "
                 f"{data.get('score')}, recomputed {score}")

    def canon(r: dict) -> str:
        return json.dumps(r, sort_keys=True)

    hole_counts: dict[str, int] = {}
    for cls, outcome, op_type in _EVALMUT_HOLES:
        want = [r for r in rows if r.get("outcome") == outcome
                and (op_type is None or r.get("op_type") == op_type)]
        hole_counts[cls] = len(want)
        got = holes.get(cls)
        got = [r for r in got if isinstance(r, dict)] \
            if isinstance(got, list) else []
        if sorted(map(canon, got)) != sorted(map(canon, want)):
            f.append(f"raw-aggregate-mismatch: {art}: holes.{cls} does not "
                     f"recompute from the rows (declared {len(got)}, "
                     f"recomputed {len(want)})")
    recomputed = {
        **counts,
        "applied": applied,
        "results": len(rows),
        "score_3": round(score, 3),
        "vacuous": hole_counts["vacuous"],
        "blind": hole_counts["blind"],
        "brittle": hole_counts["brittle"],
        "coverage_gap": hole_counts["coverage_gap"],
        "operators_exercised": len({r.get("operator_id") for r in rows}),
    }
    # optional catalog binding: the operator battery is pinned as evidence,
    # each entry carrying its mined provenance, and every row must agree
    # with the catalog it claims to be drawn from
    cat_rel = check.get("catalog")
    if _nonempty_str(cat_rel):
        cat = _load_json(bundle_dir, cat_rel, f, want=list)
        if cat is not None:
            if not (isinstance(cat, list)
                    and all(isinstance(o, dict) for o in cat)):
                f.append(f"artifact-unparsable: {cat_rel}: no operator array")
            else:
                ok = True
                for i, o in enumerate(cat, 1):
                    if not (_nonempty_str(o.get("id"))
                            and _nonempty_str(o.get("real_origin"))):
                        f.append(f"artifact-unparsable: {cat_rel}: catalog "
                                 f"entry {i} lacks a non-empty "
                                 "id/real_origin — the battery must be "
                                 "mined, not asserted")
                        ok = False
                by_id = {o["id"]: o for o in cat if _nonempty_str(o.get("id"))}
                if ok and len(by_id) != len(cat):
                    f.append(f"artifact-unparsable: {cat_rel}: duplicate "
                             "operator ids")
                    ok = False
                if ok:
                    for n, r in enumerate(rows, 1):
                        op = by_id.get(r.get("operator_id"))
                        if op is None:
                            f.append(f"raw-aggregate-mismatch: {art}: row "
                                     f"{n} operator "
                                     f"{r.get('operator_id')!r} is not in "
                                     "the catalog")
                            continue
                        for k in ("family", "polarity", "op_type"):
                            if r.get(k) != op.get(k):
                                f.append(f"raw-aggregate-mismatch: {art}: "
                                         f"row {n} {k} {r.get(k)!r} "
                                         "contradicts the catalog's "
                                         f"{op.get(k)!r}")
                    recomputed["operators"] = len(cat)
    expect = check.get("expect")
    if not (isinstance(expect, dict) and expect):
        f.append("schema-violation: results.checks[evalmut-run-v1].expect: "
                 "declared counts required")
    else:
        for k in sorted(expect):
            if k not in recomputed:
                f.append(f"summary-mismatch: {k}: not recomputable under "
                         "evalmut-run-v1")
            elif expect[k] != recomputed[k]:
                f.append(f"summary-mismatch: {k}: declared {expect[k]}, "
                         f"recomputed {recomputed[k]}")
    # no stamp binding: the payload is stampless by design (evalmut emits no
    # clock, commit, or version into results); the pins that scope the claim
    # live in protocol.hashes / subject.version and are exercised by replay
    return {**{k: [v] for k, v in recomputed.items()},
            "score": [score]}  # the summary pool (SPEC.md §2.5)


# crashkit severity weights: SPEC.md §3.4 fixes the table the vulnerability
# score weighs failures with (crashkit.runner.SEVERITY_WEIGHT, frozen here).
_CRASHKIT_WEIGHTS = {"none": 0, "low": 1, "med": 2, "high": 4, "critical": 8}
_CRASHKIT_ACC_ALIASES = ("faithfulness", "precision@k", "recall@k",
                         "citation_rate")


def _check_crashkit(bundle_dir: pathlib.Path, check: dict, proto: dict,
                    f: list[str]) -> dict[str, list] | None:
    art = check["artifact"]
    data = _load_json(bundle_dir, art, f)
    if data is None:
        return None
    cases = data.get("cases")
    if not isinstance(cases, list) or not all(isinstance(c, dict)
                                              for c in cases):
        f.append(f"artifact-unparsable: {art}: no cases[] array")
        return None
    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        f.append(f"artifact-unparsable: {art}: no metrics object")
        return None
    per_kind = data.get("per_kind")
    if not isinstance(per_kind, dict):
        f.append(f"artifact-unparsable: {art}: no per_kind object")
        return None
    for n, c in enumerate(cases, 1):
        # an aggregate re-earnable only by parsing free-text notes is a
        # declaration, not evidence — the explicit booleans are required
        if not (isinstance(c.get("passed"), bool)
                and isinstance(c.get("truncated"), bool)
                and isinstance(c.get("flagged"), bool)
                and _nonempty_str(c.get("kind"))):
            f.append(f"artifact-unparsable: {art}: case {n} lacks the "
                     "explicit passed/truncated/flagged booleans + kind "
                     "(crashkit-battery-v1 refuses note-parsing)")
            return None
    # flag semantics are internal to each row, not taken on faith
    for n, c in enumerate(cases, 1):
        if c["flagged"] != (not c["passed"] and not c["truncated"]):
            f.append(f"raw-aggregate-mismatch: {art}: case {n} flagged "
                     "flag contradicts its own passed/truncated pair")
    graded = [c for c in cases if not c["truncated"]]
    n_cases = len(cases)
    truncs = sum(1 for c in cases if c["truncated"])
    errors = sum(1 for c in cases if c.get("grader") == "error")
    accuracy = round(sum(1 for c in graded if c["passed"])
                     / len(graded), 4) if graded else 0.0
    total_w = sum(_CRASHKIT_WEIGHTS.get(c.get("severity"), 0)
                  for c in graded)
    failed_w = sum(_CRASHKIT_WEIGHTS.get(c.get("severity"), 0)
                   for c in graded if not c["passed"])
    recomputed = {
        "accuracy": accuracy,
        "vulnerability_score": round(failed_w / total_w, 4) if total_w
        else 0.0,
        "flagged_cases": float(sum(1 for c in cases if c["flagged"])),
        "n_cases": float(n_cases),
        "truncations": float(truncs),
        "reliability": round((n_cases - errors - truncs) / n_cases, 4)
        if n_cases else 0.0,
        "cases": n_cases,
        "graded": len(graded),
        "errors": errors,
    }
    for k in _CRASHKIT_ACC_ALIASES:
        if metrics.get(k) != accuracy:
            f.append(f"raw-aggregate-mismatch: {art}: metrics.{k} "
                     f"declared {metrics.get(k)}, recomputed {accuracy}")
    for k in ("vulnerability_score", "flagged_cases", "n_cases",
              "truncations", "reliability"):
        if metrics.get(k) != recomputed[k]:
            f.append(f"raw-aggregate-mismatch: {art}: metrics.{k} "
                     f"declared {metrics.get(k)}, "
                     f"recomputed {recomputed[k]}")
    kinds: dict[str, list[int]] = {}
    for c in graded:
        kinds.setdefault(c["kind"], []).append(1 if c["passed"] else 0)
    want = {k: round(sum(v) / len(v), 4) for k, v in kinds.items()}
    for k in sorted(set(per_kind) | set(want)):
        if per_kind.get(k) != want.get(k):
            f.append(f"raw-aggregate-mismatch: {art}: per_kind[{k!r}] "
                     f"declared {per_kind.get(k)}, "
                     f"recomputed {want.get(k)}")
    # stamp binding (SPEC.md §2.3): the frozen battery's fingerprint —
    # identity only; integrity is the manifest's sha256 over the bytes
    key = check.get("battery_hash_key")
    hashes = proto.get("hashes") if isinstance(proto.get("hashes"), dict) \
        else {}
    if not _nonempty_str(key):
        f.append("schema-violation: results.checks[crashkit-battery-v1]"
                 ".battery_hash_key: name of the protocol.hashes entry "
                 "pinning this artifact's battery required")
    elif key not in hashes:
        f.append(f"stamp-mismatch: {key}: named by the check but absent "
                 "from protocol.hashes")
    elif hashes[key] != data.get("git_sha"):
        f.append(f"stamp-mismatch: {key}: protocol {hashes[key]}, "
                 f"artifact {data.get('git_sha')}")
    expect = check.get("expect")
    if not (isinstance(expect, dict) and expect):
        f.append("schema-violation: results.checks[crashkit-battery-v1]"
                 ".expect: declared numbers required")
    else:
        for k in sorted(expect):
            if k not in recomputed:
                f.append(f"summary-mismatch: {k}: not recomputable under "
                         "crashkit-battery-v1")
            elif expect[k] != recomputed[k]:
                f.append(f"summary-mismatch: {k}: declared {expect[k]}, "
                         f"recomputed {recomputed[k]}")
    return {k: [v] for k, v in recomputed.items()}  # the §2.5 summary pool


# modeldrift standings verdict icons: SPEC.md §3.5 pins the exact RESULTS.md
# rendering so the committed table is re-earned byte for byte from the rows.
_MODELDRIFT_ICON = {"regressed": "🔴", "improved": "🟢", "unchanged": "⚪",
                    "baseline": "🔵", "no-data": "⚫"}


def _modeldrift_standings_rows(series: dict, registry: list) -> list[dict]:
    """One standings row per registry entry, in registry order, from the last
    two stored points of its series (SPEC.md §3.5): verdicts at ±1e-9, delta
    rounded to 4 places, the per-run floor 100/graded, and the below-floor
    flag under the exact inequality the published table prints with."""
    rows = []
    for m in registry:
        pts = series.get(m["id"]) or []
        acc = delta = graded = when = None
        if not pts:
            verdict = "no-data"
        else:
            last = pts[-1]
            g = last.get("graded")
            graded = int(g) if g else None
            when = (last.get("t") or "")[:10] or None
            acc = last.get("acc")
            if len(pts) < 2:
                verdict = "baseline"
            else:
                delta = round(acc - pts[-2].get("acc"), 4)
                verdict = ("regressed" if delta < -1e-9
                           else "improved" if delta > 1e-9 else "unchanged")
        floor = 100.0 / graded if graded else None
        rows.append({
            "id": m["id"], "label": m.get("label") or m["id"], "when": when,
            "acc": acc, "delta": delta, "verdict": verdict, "graded": graded,
            "min_detectable_pts": round(floor, 3) if floor is not None
            else None,
            "below_floor": (floor is not None and delta is not None
                            and 1e-9 < abs(delta * 100) < floor),
        })
    return rows


def _modeldrift_results_md(rows: list[dict], suite_version: str) -> str:
    """The pinned standings template, rendered from RECOMPUTED rows — the
    committed RESULTS.md must be byte-identical or the two disagree."""
    out = []
    for r in rows:
        if r["acc"] is None:
            out.append(f"| {r['label']} | — | — | — | ⚫ no runs yet |")
            continue
        d = "—" if r["delta"] is None else f"{r['delta'] * 100:+.1f} pts"
        floor = 100.0 / r["graded"] if r["graded"] else None
        if floor is None:
            f_txt = "—"
        elif r["delta"] is not None and 1e-9 < abs(r["delta"] * 100) < floor:
            f_txt = f"±{floor:.1f} ⚠ below floor"
        else:
            f_txt = f"±{floor:.1f}"
        out.append(f"| {r['label']} | {r['acc'] * 100:.1f}% | {d} | {f_txt} "
                   f"| {_MODELDRIFT_ICON[r['verdict']]} {r['verdict']} |")
    return (
        f"# Latest standings — suite `{suite_version}`\n\n"
        "_Auto-generated after each scheduled probe. Live chart: "
        "[egnaro9.github.io/model-drift]"
        "(https://egnaro9.github.io/model-drift/)._\n\n"
        "**Min detectable** is the smallest movement a run could show: "
        "`100 / graded calls`. Accuracy is scored over graded calls only — a "
        "truncated call leaves the denominator rather than counting as wrong "
        "— so the floor is not a constant, and a delta beneath it is the "
        "denominator moving, not the model.\n\n"
        "| Model | Accuracy | Δ vs previous | Min detectable | Status |\n"
        "| --- | --- | --- | --- | --- |\n"
        + "\n".join(out) + "\n"
    )


def _modeldrift_flips(series: dict) -> dict:
    """The flip / probe-alarm analysis recomputed from the stored `fails`
    vectors (SPEC.md §3.5): a flip is a task entering or leaving the fails
    set between consecutive fails-bearing points of one non-mock series;
    a probe alarm is a (day, task) failing across >= 3 distinct providers —
    models from different labs do not regress in unison."""
    repeat, once = [], []
    for mid, pts in series.items():
        if mid.startswith("mock:"):
            continue
        seen = [(p.get("t", ""), set(p.get("fails") or []))
                for p in pts if "fails" in p]
        counts: dict[str, int] = {}
        latest: dict[str, str] = {}
        for (_, prev), (t, cur) in zip(seen, seen[1:]):
            for task in cur - prev:
                counts[task] = counts.get(task, 0) + 1
                latest[task] = f"broke on {(t or '')[:10]}"
            for task in prev - cur:
                counts[task] = counts.get(task, 0) + 1
                latest[task] = f"recovered on {(t or '')[:10]}"
        for row in sorted(({"task": t, "flips": n, "latest": latest[t]}
                           for t, n in counts.items()),
                          key=lambda r: (-r["flips"], r["task"])):
            (repeat if row["flips"] > 1 else once).append(
                {"model": mid, **row})
    by_day: dict[str, dict[str, set]] = {}
    for mid, pts in series.items():
        if mid.startswith("mock:"):
            continue
        prov = mid.split(":", 1)[0] if ":" in mid else mid
        for p in pts:
            if "fails" not in p:
                continue
            for task in p.get("fails") or []:
                by_day.setdefault((p.get("t") or "")[:10], {}) \
                    .setdefault(task, set()).add(prov)
    alarms = [{"day": day, "task": task, "providers": sorted(provs),
               "n_providers": len(provs)}
              for day, tasks in by_day.items()
              for task, provs in tasks.items() if len(provs) >= 3]
    alarms.sort(key=lambda a: (-a["n_providers"], a["day"], a["task"]))
    return {
        "repeat_offenders": sorted(repeat,
                                   key=lambda r: (-r["flips"], r["model"])),
        "one_offs": once,
        "probe_alarms": alarms,
        "models_with_enough_history": sum(
            1 for pts in series.values()
            if sum(1 for p in pts if "fails" in p) >= 2),
    }


def _bad_unit(v) -> bool:
    return isinstance(v, bool) or not isinstance(v, (int, float))


def _check_modeldrift(bundle_dir: pathlib.Path, check: dict, proto: dict,
                      f: list[str]) -> dict[str, list] | None:
    met_rel, reg_rel = check["metrics"], check["registry"]
    stand_rel, flips_rel = check["standings"], check["flips"]
    narr_rel, md_rel = check["narrative"], check["results_md"]
    fp_rel = check["fingerprint"]
    metrics = _load_json(bundle_dir, met_rel, f)
    registry = _load_json(bundle_dir, reg_rel, f, want=list)
    stand = _load_json(bundle_dir, stand_rel, f)
    flips = _load_json(bundle_dir, flips_rel, f)
    narr = _load_json(bundle_dir, narr_rel, f)
    fp = _load_json(bundle_dir, fp_rel, f)
    if None in (metrics, registry, stand, flips, narr, fp):
        return None
    series = metrics.get("series") if isinstance(metrics, dict) else None
    if not (isinstance(series, dict)
            and all(isinstance(pts, list)
                    and all(isinstance(p, dict) for p in pts)
                    for pts in series.values())):
        f.append(f"artifact-unparsable: {met_rel}: no series object of "
                 "point lists")
        return None
    if not (isinstance(registry, list)
            and all(isinstance(m, dict) and _nonempty_str(m.get("id"))
                    for m in registry)):
        f.append(f"artifact-unparsable: {reg_rel}: no model registry array "
                 "with ids")
        return None
    task_ids = fp.get("task_ids") if isinstance(fp, dict) else None
    if not (isinstance(task_ids, list) and task_ids
            and all(_nonempty_str(t) for t in task_ids)
            and _nonempty_str(fp.get("suite_version"))
            and _nonempty_str(fp.get("suite_hash"))):
        f.append(f"artifact-unparsable: {fp_rel}: suite_version, "
                 "suite_hash, and task_ids[] required")
        return None
    if not (isinstance(stand, dict) and isinstance(stand.get("rows"), list)
            and all(isinstance(r, dict) for r in stand["rows"])):
        f.append(f"artifact-unparsable: {stand_rel}: no rows[] array")
        return None
    if not isinstance(flips, dict):
        f.append(f"artifact-unparsable: {flips_rel}: no flip-analysis "
                 "object")
        return None
    if not (isinstance(narr, dict) and isinstance(narr.get("sentences"), list)
            and isinstance(narr.get("html"), str)
            and isinstance(narr.get("text"), str)):
        f.append(f"artifact-unparsable: {narr_rel}: sentences[], html, and "
                 "text required")
        return None
    tasks = len(task_ids)
    if fp.get("tasks") != tasks:
        f.append(f"raw-aggregate-mismatch: {fp_rel}: tasks declared "
                 f"{fp.get('tasks')!r}, recomputed {tasks} (len of task_ids)")
        return None
    # per-point coherence: the invariants a stored row must satisfy before
    # any claim is derived from it — nothing derived from sick rows is
    # recomputable, so a violation ends the check
    ids = set(task_ids)
    before = len(f)
    for mid, pts in series.items():
        prev_t = ""
        mock = mid.startswith("mock:")
        for i, p in enumerate(pts):
            w = f"{met_rel}: {mid}[{i}]"
            t = p.get("t")
            t = t if isinstance(t, str) else ""
            if t < prev_t:
                f.append(f"raw-aggregate-mismatch: {w}: t {t!r} precedes "
                         f"{prev_t!r}")
            prev_t = t
            for k in ("acc", "reliability"):
                v = p.get(k)
                if _bad_unit(v) or not 0 <= v <= 1:
                    f.append(f"raw-aggregate-mismatch: {w}: {k} {v!r} "
                             "outside [0,1]")
            rr = p.get("refusal_rate")
            if rr is not None and (_bad_unit(rr) or not 0 <= rr <= 1):
                f.append(f"raw-aggregate-mismatch: {w}: refusal_rate {rr!r} "
                         "outside [0,1]")
            lat = p.get("latency_ms")
            if _bad_unit(lat) or lat < 0:
                f.append(f"raw-aggregate-mismatch: {w}: latency_ms {lat!r} "
                         "not a number >= 0")
            runs = p.get("runs", 1)
            if _bad_unit(runs) or runs < 1:
                f.append(f"raw-aggregate-mismatch: {w}: runs {runs!r} < 1")
            spread = p.get("acc_spread", 0)
            if _bad_unit(spread) or spread < 0:
                f.append(f"raw-aggregate-mismatch: {w}: acc_spread "
                         f"{spread!r} < 0")
            unknown = sorted(set(p.get("fails") or []) - ids)
            if unknown:
                f.append(f"raw-aggregate-mismatch: {w}: fails name tasks "
                         f"outside the suite: {unknown}")
            g = p.get("graded")
            if g is not None and (isinstance(g, bool)
                                  or not isinstance(g, int)
                                  or not 1 <= g <= tasks):
                f.append(f"raw-aggregate-mismatch: {w}: graded {g!r} "
                         f"outside 1..{tasks}")
            if p.get("suite") not in (None, fp["suite_version"]):
                f.append(f"raw-aggregate-mismatch: {w}: suite "
                         f"{p['suite']!r} is not {fp['suite_version']!r}")
            if p.get("suite_hash") not in (None, fp["suite_hash"]):
                f.append(f"raw-aggregate-mismatch: {w}: suite_hash "
                         f"{p['suite_hash']!r} is not {fp['suite_hash']!r}")
            fr = p.get("fails_runs")
            if fr is not None and not (isinstance(fr, list)
                                       and all(isinstance(s, list)
                                               for s in fr)):
                f.append(f"raw-aggregate-mismatch: {w}: fails_runs {fr!r} "
                         "is not a list of samples")
            elif fr is not None:
                for j, sample in enumerate(fr):
                    unknown = sorted(set(sample) - ids)
                    if unknown:
                        f.append(f"raw-aggregate-mismatch: {w}: "
                                 f"fails_runs[{j}] names tasks outside the "
                                 f"suite: {unknown}")
                if (p.get("fails") or []) not in fr:
                    f.append(f"raw-aggregate-mismatch: {w}: fails is not "
                             "one of its own fails_runs samples")
            # the live null control: a moved mock indicts the harness, not
            # the models — nothing derived from rows like that is evidence
            if mock and (p.get("acc") != 1.0 or (p.get("fails") or [])):
                f.append(f"raw-aggregate-mismatch: {w}: the deterministic "
                         f"control moved (acc {p.get('acc')!r}, fails "
                         f"{p.get('fails')!r})")
    if len(f) > before:
        return None
    # standings: the whole published object re-earned from the rows and
    # compared exactly — top-level stamps, floor, and every row, every key
    floor_full = round(100.0 / tasks, 3)
    want_rows = _modeldrift_standings_rows(series, registry)
    want_stand = {"suite_version": fp["suite_version"],
                  "suite_hash": fp["suite_hash"],
                  "min_detectable_pts_full_grade": floor_full,
                  "rows": want_rows}
    for k in ("suite_version", "suite_hash", "min_detectable_pts_full_grade"):
        if stand.get(k) != want_stand[k]:
            f.append(f"raw-aggregate-mismatch: {stand_rel}: {k} declared "
                     f"{stand.get(k)!r}, recomputed {want_stand[k]!r}")
    extra = sorted(set(stand) - set(want_stand))
    if extra:
        f.append(f"raw-aggregate-mismatch: {stand_rel}: unexpected keys "
                 f"{extra}")
    got_rows = stand["rows"]
    if [r.get("id") for r in got_rows] != [r["id"] for r in want_rows]:
        f.append(f"raw-aggregate-mismatch: {stand_rel}: rows do not cover "
                 f"the registry in registry order (declared {len(got_rows)}, "
                 f"recomputed {len(want_rows)})")
    else:
        for got, want in zip(got_rows, want_rows):
            for k, v in want.items():
                if got.get(k) != v:
                    f.append(f"raw-aggregate-mismatch: {stand_rel}: "
                             f"{want['id']}: {k} declared {got.get(k)!r}, "
                             f"recomputed {v!r}")
            extra = sorted(set(got) - set(want))
            if extra:
                f.append(f"raw-aggregate-mismatch: {stand_rel}: "
                         f"{want['id']}: unexpected keys {extra}")
    # the published table, re-rendered from the RECOMPUTED rows under the
    # pinned template — byte-identity or the board's two stores disagree
    try:
        md = (bundle_dir / md_rel).read_bytes()
    except OSError as e:  # unreachable for a trusted artifact; named anyway
        f.append(f"artifact-unparsable: {md_rel}: {e}")
        return None
    if _modeldrift_results_md(want_rows, fp["suite_version"]).encode() != md:
        f.append(f"raw-aggregate-mismatch: {md_rel}: does not re-render "
                 "byte-identically from the recomputed standings rows")
    # flip analysis, re-earned from the stored fails vectors
    want_flips = _modeldrift_flips(series)
    mw = want_flips["models_with_enough_history"]
    if flips.get("models_with_enough_history") != mw:
        f.append(f"raw-aggregate-mismatch: {flips_rel}: "
                 "models_with_enough_history declared "
                 f"{flips.get('models_with_enough_history')!r}, "
                 f"recomputed {mw!r}")
    for k in ("repeat_offenders", "one_offs", "probe_alarms"):
        got = flips.get(k)
        if got != want_flips[k]:
            n_got = len(got) if isinstance(got, list) else got
            f.append(f"raw-aggregate-mismatch: {flips_rel}: {k} does not "
                     f"recompute from the fails vectors (declared {n_got}, "
                     f"recomputed {len(want_flips[k])})")
    extra = sorted(set(flips) - set(want_flips))
    if extra:
        f.append(f"raw-aggregate-mismatch: {flips_rel}: unexpected keys "
                 f"{extra}")
    # narrative internal coherence only: byte-identical REGENERATION of the
    # paragraph is the replay block's job (the claims generator at the
    # stamped commit), not structural
    strip = re.sub(r"\s+", " ",
                   re.sub(r"<[^>]+>", "", narr["html"])).strip()
    if narr.get("claims_fired") != len(narr["sentences"]):
        f.append(f"raw-aggregate-mismatch: {narr_rel}: claims_fired "
                 f"declared {narr.get('claims_fired')!r}, recomputed "
                 f"{len(narr['sentences'])} (one per sentence)")
    if narr["text"] != strip:
        f.append(f"raw-aggregate-mismatch: {narr_rel}: text is not the "
                 "whitespace-normalized, tag-stripped html")
    # stamp binding (SPEC.md §2.3): the pinned suite and the exact input
    # bytes the derivations were run over
    hashes = proto.get("hashes") if isinstance(proto.get("hashes"), dict) \
        else {}
    if hashes.get("suite_hash") != fp["suite_hash"]:
        f.append(f"stamp-mismatch: suite_hash: protocol "
                 f"{hashes.get('suite_hash')}, artifact {fp['suite_hash']}")
    for key, rel in (("metrics_sha256", met_rel),
                     ("registry_sha256", reg_rel)):
        actual = _sha256(bundle_dir / rel)
        if hashes.get(key) != actual:
            f.append(f"stamp-mismatch: {key}: protocol {hashes.get(key)}, "
                     f"artifact {actual}")
    verdicts: dict[str, int] = {}
    for r in want_rows:
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
    recomputed = {
        "rows": len(want_rows),
        "regressed": verdicts.get("regressed", 0),
        "improved": verdicts.get("improved", 0),
        "unchanged": verdicts.get("unchanged", 0),
        "baseline": verdicts.get("baseline", 0),
        "no_data": verdicts.get("no-data", 0),
        "series": len(series),
        "points": sum(len(pts) for pts in series.values()),
        "tasks": tasks,
        "min_detectable_pts_full_grade": floor_full,
        "probe_alarms": len(want_flips["probe_alarms"]),
        "repeat_offenders": len(want_flips["repeat_offenders"]),
        "one_offs": len(want_flips["one_offs"]),
        "models_with_enough_history": mw,
        "claims_fired": len(narr["sentences"]),
    }
    expect = check.get("expect")
    if not (isinstance(expect, dict) and expect):
        f.append("schema-violation: results.checks[modeldrift-board-v1]"
                 ".expect: declared numbers required")
    else:
        for k in sorted(expect):
            if k not in recomputed:
                f.append(f"summary-mismatch: {k}: not recomputable under "
                         "modeldrift-board-v1")
            elif expect[k] != recomputed[k]:
                f.append(f"summary-mismatch: {k}: declared {expect[k]}, "
                         f"recomputed {recomputed[k]}")
    return {k: [v] for k, v in recomputed.items()}  # the §2.5 summary pool


_CHECK_REFS = {"certlab-bundle-v1": ("artifact",),
               "fleet-board-v1": ("aggregate", "raw"),
               "evalmut-run-v1": ("artifact",),
               "crashkit-battery-v1": ("artifact",),
               "modeldrift-board-v1": ("metrics", "registry", "standings",
                                       "flips", "narrative", "results_md",
                                       "fingerprint")}
_CHECK_OPT_REFS = {"evalmut-run-v1": ("catalog",)}
_CHECK_FNS = {"certlab-bundle-v1": _check_certlab,
              "fleet-board-v1": _check_fleet,
              "evalmut-run-v1": _check_evalmut,
              "crashkit-battery-v1": _check_crashkit,
              "modeldrift-board-v1": _check_modeldrift}


def _summary_outruns(summary: dict, pools: list[dict]) -> list[str]:
    """SPEC.md §2.5: every number in results.summary must be re-earned by a
    check's recomputation. A summary key that names a recomputed field is
    held to that field's recomputed value(s); any other numeric value must
    at least equal SOME recomputed quantity ("derivable from a check").
    Non-numeric, descriptive values pass through."""
    by_field: dict[str, set] = {}
    for pool in pools:
        for k, vs in pool.items():
            by_field.setdefault(k, set()).update(vs)
    all_vals: set = set().union(*by_field.values()) if by_field else set()
    f: list[str] = []

    def walk(node, path, key):
        if isinstance(node, dict):
            for k in sorted(node):
                walk(node[k], f"{path}.{k}", k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]", key)
        elif isinstance(node, bool) or not isinstance(node, (int, float)):
            return
        elif key in by_field:
            if node not in by_field[key]:
                got = sorted(by_field[key])
                shown = got[0] if len(got) == 1 else f"one of {got}"
                f.append(f"summary-outruns-checks: {path}: declares {node}, "
                         f"recomputation gives {shown}")
        elif node not in all_vals:
            f.append(f"summary-outruns-checks: {path}: declares {node}, "
                     "no check recomputes it")

    walk(summary, "summary", "summary")
    return f


def _coherence(bundle_dir: pathlib.Path, m: dict,
               trusted: set[str]) -> list[str]:
    f: list[str] = []
    results = m.get("results") if isinstance(m.get("results"), dict) else {}
    proto = m.get("protocol") if isinstance(m.get("protocol"), dict) else {}
    listed = {e["path"] for e in m.get("evidence") or []
              if isinstance(e, dict) and _safe_relpath(e.get("path"))}
    pools: list[dict] = []
    complete = True  # every declared check contributed its recomputation
    for c in results.get("checks") or []:
        if not isinstance(c, dict) or c.get("profile") not in PROFILES:
            complete = False
            continue  # already named as unknown-profile
        usable = True
        refs = list(_CHECK_REFS[c["profile"]])
        refs += [k for k in _CHECK_OPT_REFS.get(c["profile"], ())
                 if k in c]  # optional refs, once named, are held to the bar
        for ref_key in refs:
            r = c.get(ref_key)
            if not _nonempty_str(r) or r not in listed:
                f.append(f"check-artifact-not-listed: {r!r}")
                usable = False
            elif r not in trusted:
                usable = False  # missing/hash-failed: already named
        if not usable:
            complete = False
            continue
        before = len(f)
        pool = _CHECK_FNS[c["profile"]](bundle_dir, c, proto, f)
        if pool is None:
            complete = False
            if len(f) == before:  # fail closed: never skip a check silently
                f.append(f"artifact-unparsable: {c['profile']}: check "
                         "contributed no recomputation")
        else:
            pools.append(pool)
    # summary enforcement (SPEC.md §2.5) runs only over a complete pool — a
    # bundle whose checks cannot recompute already fails on those reasons,
    # and "derivable" is undecidable against a half-built pool
    summary = results.get("summary")
    if complete and pools and isinstance(summary, dict):
        f += _summary_outruns(summary, pools)
    return f


# --------------------------------------------------------------------------
def verify_bundle(bundle_dir: pathlib.Path) -> list[str]:
    """All named failures for the bundle at `bundle_dir`; [] means clean."""
    vac = bundle_dir / "vac.json"
    if not vac.is_file():
        return ["missing-manifest: no vac.json in bundle"]
    try:
        m = json.loads(vac.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return [f"invalid-json: vac.json: {e}"]
    if not isinstance(m, dict):
        return ["invalid-json: vac.json: top level must be an object"]
    todo = _todo_failures(m)
    if todo:
        return todo  # a draft is refused wholesale (SPEC.md §2.7)
    failures = _validate_manifest(m)
    art_failures, trusted = _verify_artifacts(bundle_dir, m)
    failures += art_failures
    failures += _coherence(bundle_dir, m, trusted)
    return failures


def _extract_tar(tar_path: pathlib.Path, dest: pathlib.Path) -> None:
    with tarfile.open(tar_path, "r:*") as tf:
        for mem in tf.getmembers():
            # Vet under BOTH flavours. A member named with Windows separators
            # ("..\\..\\evil") has no ".." part under PurePosixPath, so a
            # posix-only check accepts a genuine escape, and on pythons
            # without filter= the fallback below then writes it.
            pp = pathlib.PurePosixPath(mem.name)
            wp = pathlib.PureWindowsPath(mem.name)
            if not pp.parts or not wp.parts:
                # '.' and './' are the archive's own root entry, which is
                # what "tar -czf b.tar.gz ." writes first. Only an
                # empty-named FILE is the crash vector, where extractall
                # raises an OSError straight out of main.
                if mem.isdir():
                    continue
                raise ValueError(f"unsafe member {mem.name!r}")
            if (pp.is_absolute() or ".." in pp.parts
                    or wp.is_absolute() or wp.drive or wp.root
                    or ".." in wp.parts
                    or not (mem.isfile() or mem.isdir())):
                raise ValueError(f"unsafe member {mem.name!r}")
        try:
            tf.extractall(dest, filter="data")
        except TypeError:  # no filter= on this python; members vetted above
            tf.extractall(dest)
    # SPEC 1: a bundle ships as "a .tar.gz OF THE DIRECTORY", so anything
    # sitting beside the bundle root is not part of the bundle and would
    # never be reached by the closure walk. Name it here, where the cause is
    # visible, rather than letting _bundle_root fall back and report a
    # missing manifest that is plainly present one level down.
    top = sorted(p.name for p in dest.iterdir())
    if len(top) > 1 and not (dest / "vac.json").is_file():
        raise ValueError(
            "archive has entries beside the bundle root: "
            + ", ".join(repr(t) for t in top)
            + " (a bundle tar holds exactly the bundle directory; on macOS set COPYFILE_DISABLE=1)")


def _bundle_root(extracted: pathlib.Path) -> pathlib.Path:
    if (extracted / "vac.json").is_file():
        return extracted
    subdirs = [p for p in extracted.iterdir() if p.is_dir()]
    if len(subdirs) == 1 and (subdirs[0] / "vac.json").is_file():
        return subdirs[0]
    return extracted  # verify_bundle names the missing manifest


def _report(name: str, root: pathlib.Path, failures: list[str]) -> int:
    for reason in failures:
        print(f"FAIL {reason}")
    verdict = "PASS" if not failures else f"FAIL — {len(failures)} named reason(s)"
    print(f"structural verification: {verdict} ({name})")
    print("  proved offline: manifest schema, artifact presence + sha256, "
          "bundle closure,")
    print("  stated limitations, stamp agreement, declared results recomputed "
          "from artifacts.")
    print("semantic replay: NOT run by this tool. A structural PASS means the "
          "bundle is")
    print("  internally honest, not that the issuer's grader agrees. To "
          "re-earn the")
    print("  verdicts, run the bundle's replay block at the pinned "
          "issuer_commit:")
    try:  # best-effort echo of the replay recipe; never affects the verdict
        replay = json.loads((root / "vac.json").read_text()).get("replay", {})
        for cmd in replay.get("commands", []):
            print(f"    $ {cmd}")
        if _nonempty_str(replay.get("expected")):
            print(f"    expected: {replay['expected']}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        print("    (replay block unreadable — see failures above)")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] in ("-h", "--help"):
        print(USAGE)
        return 2
    target = pathlib.Path(args[0])
    if target.is_dir():
        return _report(target.name, target, verify_bundle(target))
    if target.is_file() and target.name.endswith((".tar.gz", ".tgz", ".tar")):
        with tempfile.TemporaryDirectory() as td:
            try:
                _extract_tar(target, pathlib.Path(td))
            except (ValueError, OSError, tarfile.TarError) as e:
                print(f"FAIL unsafe-archive: {e}")
                print(f"structural verification: FAIL — 1 named reason(s) "
                      f"({target.name})")
                return 1
            root = _bundle_root(pathlib.Path(td))
            return _report(target.name, root, verify_bundle(root))
    print(f"{USAGE}\nnot a bundle directory or tar archive: {target}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
