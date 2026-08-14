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

`python -m vac.verify <bundle-dir | bundle.tar.gz>` — exit 0 only when
structurally clean; otherwise one named reason per failure, all of them.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tarfile
import tempfile

VAC_VERSION = "0.1"
PROFILES = ("certlab-bundle-v1", "fleet-board-v1", "evalmut-run-v1")
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
    pp = pathlib.PurePosixPath(p)
    return bool(pp.parts) and not pp.is_absolute() and ".." not in pp.parts


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
            prof = c.get("profile") if isinstance(c, dict) else c
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
def _load_json(bundle_dir: pathlib.Path, rel: str, f: list[str]):
    try:
        return json.loads((bundle_dir / rel).read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        f.append(f"artifact-unparsable: {rel}: {e}")
        return None


def _check_certlab(bundle_dir: pathlib.Path, check: dict, proto: dict,
                   f: list[str]) -> None:
    art = check["artifact"]
    data = _load_json(bundle_dir, art, f)
    if data is None:
        return
    verdicts = data.get("verdicts")
    if not isinstance(verdicts, list):
        f.append(f"artifact-unparsable: {art}: no verdicts[] array")
        return
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


def _check_fleet(bundle_dir: pathlib.Path, check: dict, proto: dict,
                 f: list[str]) -> None:
    agg = _load_json(bundle_dir, check["aggregate"], f)
    raw_rel = check["raw"]
    try:
        raw = [json.loads(ln) for ln in
               (bundle_dir / raw_rel).read_text().splitlines() if ln.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        f.append(f"artifact-unparsable: {raw_rel}: {e}")
        return
    if agg is None:
        return
    rows = agg.get("rows")
    if not isinstance(rows, list):
        f.append(f"artifact-unparsable: {check['aggregate']}: no rows[] array")
        return
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
        seen.add(key)
        lines = groups.get(key)
        if not lines:
            f.append(f"raw-aggregate-mismatch: {key[0]}/{key[1]}: aggregate "
                     "row has no raw lines")
            continue
        n = len(lines)
        det = sum(1 for ln in lines if ln.get("detected") is True)
        fa = sum(1 for ln in lines if ln.get("clean_passed") is not True)
        rec = {"n": n, "detected": det, "false_alarms": fa,
               "detection_rate": round(det / n, 3),
               "false_alarm_rate": round(fa / n, 3)}
        for k, v in rec.items():
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


# evalmut hole classes: name -> (outcome, op_type or None) over the rows.
_EVALMUT_HOLES = (("vacuous", "missed", "sanity"),
                  ("blind", "missed", "kill"),
                  ("error", "error", None),
                  ("brittle", "flagged", None),
                  ("coverage_gap", "missed", "diagnostic"))


def _check_evalmut(bundle_dir: pathlib.Path, check: dict, proto: dict,
                   f: list[str]) -> None:
    art = check["artifact"]
    data = _load_json(bundle_dir, art, f)
    if data is None:
        return
    rows = data.get("results")
    if not isinstance(rows, list) or not all(isinstance(r, dict)
                                             for r in rows):
        # without the per-mutation rows nothing is recomputable — the
        # aggregate alone is a declaration, not evidence
        f.append(f"artifact-unparsable: {art}: no results[] array "
                 "(evalmut-run-v1 requires the --json --all payload)")
        return
    tally = data.get("tally")
    if not isinstance(tally, dict):
        f.append(f"artifact-unparsable: {art}: no tally object")
        return
    holes = data.get("holes")
    if not isinstance(holes, dict):
        f.append(f"artifact-unparsable: {art}: no holes object")
        return
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
        cat = _load_json(bundle_dir, cat_rel, f)
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


_CHECK_REFS = {"certlab-bundle-v1": ("artifact",),
               "fleet-board-v1": ("aggregate", "raw"),
               "evalmut-run-v1": ("artifact",)}
_CHECK_OPT_REFS = {"evalmut-run-v1": ("catalog",)}
_CHECK_FNS = {"certlab-bundle-v1": _check_certlab,
              "fleet-board-v1": _check_fleet,
              "evalmut-run-v1": _check_evalmut}


def _coherence(bundle_dir: pathlib.Path, m: dict,
               trusted: set[str]) -> list[str]:
    f: list[str] = []
    results = m.get("results") if isinstance(m.get("results"), dict) else {}
    proto = m.get("protocol") if isinstance(m.get("protocol"), dict) else {}
    listed = {e["path"] for e in m.get("evidence") or []
              if isinstance(e, dict) and _safe_relpath(e.get("path"))}
    for c in results.get("checks") or []:
        if not isinstance(c, dict) or c.get("profile") not in PROFILES:
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
        if usable:
            _CHECK_FNS[c["profile"]](bundle_dir, c, proto, f)
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
    failures = _validate_manifest(m)
    art_failures, trusted = _verify_artifacts(bundle_dir, m)
    failures += art_failures
    failures += _coherence(bundle_dir, m, trusted)
    return failures


def _extract_tar(tar_path: pathlib.Path, dest: pathlib.Path) -> None:
    with tarfile.open(tar_path, "r:*") as tf:
        for mem in tf.getmembers():
            pp = pathlib.PurePosixPath(mem.name)
            if pp.is_absolute() or ".." in pp.parts \
                    or not (mem.isfile() or mem.isdir()):
                raise ValueError(f"unsafe member {mem.name!r}")
        try:
            tf.extractall(dest, filter="data")
        except TypeError:  # no filter= on this python; members vetted above
            tf.extractall(dest)


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
            except (ValueError, tarfile.TarError) as e:
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
