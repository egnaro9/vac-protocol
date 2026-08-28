"""Registry generator and fetch-mode checker for the VAC registry (SPEC.md
section 5). The registry is a FILE in this repo, reviewed like code — no
hosted service, no operator between the reader and the evidence.

  python -m vac.registry                  regenerate registry.json by scanning
                                          the configured LOCAL issuer checkouts
                                          at their committed HEAD trees
  python -m vac.registry --check-fetched  rebuild every accepted entry from the
                                          artifacts FETCHED at their registry
                                          URLs and require byte-identity with
                                          committed registry.json (the pages.yml
                                          gate: the page deploys only what is
                                          actually fetchable and verified)
  python -m vac.registry --fetch-bundle NAME --dest DIR
                                          download one entry's artifacts,
                                          sha256-checked against the registry
                                          (replay.yml starts here)
  python -m vac.registry --emit-matrix    accepted entries as compact JSON for
                                          the replay CI matrix (stdout only)
  python -m vac.registry --list-pending   exit 1 naming every pending entry

Local mode hashes COMMITTED bytes (`git cat-file blob HEAD:<path>`), never the
working tree, so a half-written emitter cannot leak into the registry. A
configured bundle that is not yet admissible is recorded PENDING with its
exact reason — the configured directory absent from the committed tree
entirely, vac.json absent, or structural verification naming its failures —
never fabricated and never silently dropped; the scan is re-run mechanically
once the issuer lands the fix.
Acceptance keeps SPEC.md section 5 rule 7 as the floor: no entry exists
unless the verifier exits clean over the committed bytes. Everything emitted
is byte-reproducible: content derives only from committed issuer trees; no
clocks, no environment, no network state.
"""

from __future__ import annotations

import difflib
import json
import re
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from .verify import _sha256, verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry.json"
REGISTRY_VERSION = "0.1"

USAGE = ("usage: python -m vac.registry "
         "[--check-fetched | --fetch-bundle NAME --dest DIR | "
         "--emit-matrix | --list-pending]")

# The configured issuers. `bundles` is either one committed directory or a
# `<prefix>/*` glob over the committed tree — enumeration is mechanical, so a
# new certification directory lands in the registry by re-running the scan.
ISSUERS = [
    {"repo": "https://github.com/egnaro9/agent-certlab",
     "checkout_env": "VAC_CERTLAB_CHECKOUT",
     "default_checkout": "../agent-certlab",
     "bundles": "certifications/*"},
    {"repo": "https://github.com/egnaro9/reference-fleet",
     "checkout_env": "VAC_FLEET_CHECKOUT",
     "default_checkout": "../reference-fleet",
     "bundles": "board/vac"},
    {"repo": "https://github.com/egnaro9/evalmut",
     "checkout_env": "VAC_EVALMUT_CHECKOUT",
     "default_checkout": "../evalmut",
     "bundles": "vac"},
    {"repo": "https://github.com/egnaro9/crashkit",
     "checkout_env": "VAC_CRASHKIT_CHECKOUT",
     "default_checkout": "../crashkit",
     "bundles": "vac"},
    {"repo": "https://github.com/egnaro9/model-drift",
     "checkout_env": "VAC_MODELDRIFT_CHECKOUT",
     "default_checkout": "../model-drift",
     "bundles": "vac"},
]

PROTOCOL_LINE = (
    "acceptance is two-gated (SPEC.md section 5): structural verification by "
    "python -m vac.verify — at generation, and again over FETCHED artifacts "
    "before every pages deploy — then semantic replay by the issuer's own "
    "deterministic regrader in .github/workflows/replay.yml")

# SPEC.md section 5: a registry that skips the replay gate must say so on
# every entry. These entries do not skip it — they delegate it to CI, and say
# exactly where.
GATES = {
    "structural": "python -m vac.verify — clean at registry generation; "
                  "re-proven against the fetched artifacts before every "
                  "pages deploy",
    "semantic": "NOT run at generation — delegated to "
                ".github/workflows/replay.yml (workflow_dispatch + weekly), "
                "which clones the issuer at issuer_commit and re-earns "
                "every verdict with the issuer's own regrader",
    "grading": "NOT machine-checked. SPEC 5 rule 3 is enforced by human "
               "review of protocol.grading at PR time, plus replay, which "
               "fails a grader that cannot reproduce byte-for-byte. No "
               "check reads this field beyond requiring it non-empty",
}


class RegistryError(Exception):
    pass


def _j(obj) -> str:
    return json.dumps(obj, indent=1) + "\n"


def _owner_name(repo_url: str) -> tuple[str, str]:
    parts = repo_url.rstrip("/").split("/")
    return parts[-2], parts[-1]


def _raw_url(repo_url: str, commit: str, bundle_path: str, rel: str) -> str:
    """A commit-addressed raw URL.

    This used to hardcode `main`. A sha256 pin paired with a mutable ref can
    only be right by accident: the moment the issuer pushes, the pin and the
    bytes disagree and every bundle stops replaying. Measured 2026-08-21, all
    47 artifacts were addressed this way and none of the 11 entries had an
    issuer_commit that actually held its own pinned bytes. Address the commit
    the bytes were read from, and a bundle stays replayable forever."""
    owner, name = _owner_name(repo_url)
    return (f"https://raw.githubusercontent.com/{owner}/{name}/{commit}/"
            f"{bundle_path}/{rel}")


def _git(checkout: pathlib.Path, *args: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(checkout), *args],
                          capture_output=True)
    if proc.returncode != 0:
        raise RegistryError(f"git {' '.join(args)} failed in {checkout}: "
                            f"{proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout


def _bundle_dirs(pattern: str, head_files: list[str]) -> list[str]:
    if pattern.endswith("/*"):
        prefix = pattern[:-2]
        return sorted({f.split("/", 2)[0] + "/" + f.split("/", 2)[1]
                       for f in head_files
                       if f.startswith(prefix + "/") and f.count("/") >= 2})
    return [pattern] if any(f.startswith(pattern + "/")
                            for f in head_files) else []


def _entry(issuer: str, repo_url: str, bundle_path: str,
           bundle_dir: pathlib.Path, rels: list[str],
           pinned_commit: str) -> tuple[dict | None, list[str]]:
    """One registry entry from a MATERIALIZED bundle dir, or named reasons.

    The verifier's exit code is the floor (SPEC.md section 5 rule 7): a
    bundle that fails structural verification produces no entry, and a
    manifest whose protocol.issuer names a different owner/name than the
    configured issuer is claiming someone else's authority — refused, not
    reconciled. (Comparison is on the trailing owner/name pair, so a
    host-prefixed issuer like 'github.com/owner/name' binds to the same
    identity as the SPEC's plain 'owner/name'.)"""
    failures = verify_bundle(bundle_dir)
    if failures:
        return None, [f"structural: {f}" for f in failures]
    man = json.loads((bundle_dir / "vac.json").read_text(encoding="utf-8"))
    man_issuer = "/".join(
        str(man["protocol"]["issuer"]).rstrip("/").split("/")[-2:])
    if man_issuer != issuer:
        return None, [f"issuer-mismatch: manifest protocol.issuer "
                      f"{man['protocol']['issuer']!r} != configured issuer "
                      f"{issuer!r}"]
    return {
        "name": f"{issuer.split('/')[1]}/{bundle_path.rsplit('/', 1)[-1]}",
        "issuer": issuer,
        "issuer_repo": repo_url,
        # The issuer's own declaration, kept as a claim.
        "issuer_commit": man["protocol"]["issuer_commit"],
        # The commit these bytes were actually read from. This is the fact the
        # URLs and hashes are anchored to, and the two can legitimately differ:
        # the manifest records when the issuer emitted, this records where the
        # registry found the artifacts it hashed.
        "pinned_commit": pinned_commit,
        # WHICH RULE THIS ENTRY WAS ACCEPTED UNDER. 0.1 and 0.2 differ in what
        # they guarantee about the summary: 0.1 merges recomputation pools by
        # bare field name and admits a loose second tier, 0.2 keys them
        # scope.field and has no second tier (SPEC 2.5.1). A registry holding
        # both cannot leave a reader to guess which applies to a given entry.
        #
        # Indexed, never .get() with a default: verify_bundle has already
        # refused an absent or unsupported version above, so a missing key
        # here is a broken invariant and should raise rather than quietly
        # publish an entry as 0.1.
        "vac_version": man["vac_version"],
        "bundle_path": bundle_path,
        "capability": man["claim"]["capability"],
        "subject": f"{man['subject']['kind']}: {man['subject']['id']}",
        "summary": man["results"]["summary"],
        "profiles": sorted({c["profile"] for c in man["results"]["checks"]}),
        "artifacts": [{"path": r, "sha256": _sha256(bundle_dir / r),
                       "url": _raw_url(repo_url, pinned_commit,
                                       bundle_path, r)}
                      for r in sorted(rels)],
        "status": "accepted",
        "challenges": [],
        "gates": GATES,
    }, []


def scan_issuer(cfg: dict) -> tuple[list[dict], list[dict]]:
    """(accepted entries, pending records) for one issuer, read exclusively
    from the committed HEAD tree of its local checkout. A committed bundle
    that fails verification is PENDING with its named reasons — recorded
    non-acceptance, so the registry keeps regenerating mechanically while
    the issuer fixes its emitter."""
    checkout = (ROOT / (os.environ.get(cfg["checkout_env"])
                        or cfg["default_checkout"])).resolve()
    owner, name = _owner_name(cfg["repo"])
    issuer = f"{owner}/{name}"
    if not (checkout / ".git").exists():
        raise RegistryError(
            f"issuer checkout not found at {checkout} — clone "
            f"{cfg['repo']} there or set {cfg['checkout_env']}")
    head_sha = _git(checkout, "rev-parse", "HEAD").decode().strip()
    # A pinned URL to an unpushed commit is a 404 for everyone but this laptop.
    # Refuse at generation rather than publish a bundle nobody else can fetch.
    # Only meaningful when the checkout HAS a remote. A repo with none is a
    # local fixture, not an unpushed publication, and refusing it would gate
    # the tests rather than the failure this exists to catch.
    if _git(checkout, "remote").strip():
        remotes = _git(checkout, "branch", "-r", "--contains",
                       head_sha).decode()
        if not remotes.strip():
            raise RegistryError(
                f"{issuer}: HEAD {head_sha[:12]} is on no remote branch — "
                f"push it before registering, or the pinned artifact URLs "
                f"will 404 for everyone but this machine")
    head_files = _git(checkout, "ls-tree", "-r", "--name-only",
                      "HEAD").decode().splitlines()
    entries, pending = [], []
    dirs = _bundle_dirs(cfg["bundles"], head_files)
    if not dirs and not cfg["bundles"].endswith("/*"):
        # a configured single-directory bundle with nothing committed is a
        # named hole in the registry, not a silent absence (a glob names a
        # family and may honestly be empty; a directory is a promise)
        pending.append({
            "name": f"{name}/{cfg['bundles'].rsplit('/', 1)[-1]}",
            "issuer": issuer,
            "issuer_repo": cfg["repo"],
            "bundle_path": cfg["bundles"],
            "reason": f"no committed files at {cfg['bundles']} — the "
                      "issuer's vac emitter has not landed; re-run "
                      "python -m vac.registry once it has"})
    for bp in dirs:
        entry_name = f"{name}/{bp.rsplit('/', 1)[-1]}"
        if _git(checkout, "status", "--porcelain", "--", bp).strip():
            print(f"note: {entry_name}: working tree dirty under {bp}; "
                  "the registry reads committed HEAD bytes", file=sys.stderr)
        rels = sorted(f[len(bp) + 1:] for f in head_files
                      if f.startswith(bp + "/"))
        if "vac.json" not in rels:
            pending.append({
                "name": entry_name,
                "issuer": issuer,
                "issuer_repo": cfg["repo"],
                "bundle_path": bp,
                "reason": f"vac.json is not in the committed tree at {bp} — "
                          "the issuer's vac emitter has not landed; re-run "
                          "python -m vac.registry once it has"})
            continue
        with tempfile.TemporaryDirectory() as td:
            bdir = pathlib.Path(td)
            for rel in rels:
                p = bdir / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(_git(checkout, "cat-file", "blob",
                                   f"HEAD:{bp}/{rel}"))
            entry, rej = _entry(issuer, cfg["repo"], bp, bdir, rels,
                                head_sha)
        if rej:
            pending.append({
                "name": entry_name,
                "issuer": issuer,
                "issuer_repo": cfg["repo"],
                "bundle_path": bp,
                "reason": "refused at generation: " + "; ".join(rej)
                          + " — fix the committed bundle and re-run "
                          "python -m vac.registry"})
        else:
            entries.append(entry)
    return entries, pending


def _assemble(entries: list[dict], pending: list[dict]) -> dict:
    return {"registry_version": REGISTRY_VERSION,
            "protocol": PROTOCOL_LINE,
            "entries": sorted(entries, key=lambda e: e["name"]),
            "pending": sorted(pending, key=lambda p: p["name"])}


def build(issuers: list[dict]) -> dict:
    entries, pending = [], []
    for cfg in issuers:
        e, p = scan_issuer(cfg)
        entries += e
        pending += p
    return _assemble(entries, pending)


# --------------------------------------------------------------------------
def _fetch(url: str, timeout: float = 60.0) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RegistryError(f"fetch-failed: {url}: HTTP {e.code} — is the "
                            "emitter commit pushed to main?")
    except urllib.error.URLError as e:
        raise RegistryError(f"fetch-failed: {url}: {e.reason}")


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _mutable_ref_failures(doc: dict) -> list[str]:
    """Refuse a sha256 pin that is paired with a mutable ref.

    A pin says "these exact bytes". A ref like `main` says "whatever is there
    now". Together they are a promise that expires silently on the issuer's
    next push, which is exactly how this registry went stale for four days in
    August 2026 while still advertising replayable bundles. The ref between the
    repo name and the path must be a full 40-hex commit sha, or the entry is
    refused at check time rather than at some stranger's replay."""
    out: list[str] = []
    for e in doc.get("entries") or []:
        for a in e.get("artifacts") or []:
            url = a.get("url", "")
            m = re.match(r"^https://raw\.githubusercontent\.com/"
                         r"[^/]+/[^/]+/([^/]+)/", url)
            if not m:
                out.append(f"mutable-ref: {e.get('name')}: unrecognised "
                           f"artifact URL form: {url}")
            elif not _SHA_RE.match(m.group(1)):
                out.append(f"mutable-ref: {e.get('name')}: {a.get('path')} is "
                           f"pinned by sha256 but addressed at the mutable ref "
                           f"{m.group(1)!r} — address the commit instead")
    return out


def check_fetched(reg_path: pathlib.Path = REGISTRY,
                  fetch=_fetch) -> list[str]:
    """Rebuild every accepted entry from the artifacts fetched at their
    registry URLs; require the rebuilt registry to be BYTE-IDENTICAL to the
    committed one. Pending records carry through verbatim — an all-pending
    registry checks clean and the page honestly says 'pending'."""
    if not reg_path.is_file():
        return [f"registry.json missing at {reg_path} — "
                "run python -m vac.registry"]
    committed = reg_path.read_text(encoding="utf-8")
    doc = json.loads(committed)
    failures: list[str] = []
    rebuilt: list[dict] = []
    failures.extend(_mutable_ref_failures(doc))
    for e in doc.get("entries") or []:
        with tempfile.TemporaryDirectory() as td:
            bdir = pathlib.Path(td)
            rels, broken = [], False
            for a in e["artifacts"]:
                try:
                    data = fetch(a["url"])
                except RegistryError as err:
                    failures.append(f"{e['name']}: {err}")
                    broken = True
                    continue
                p = bdir / a["path"]
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                rels.append(a["path"])
                actual = _sha256(p)
                if actual != a["sha256"]:
                    failures.append(
                        f"sha256-drift: {e['name']}/{a['path']}: registry "
                        f"{a['sha256']}, fetched {actual} — main has moved "
                        "past the registry; regenerate registry.json and "
                        "commit the diff")
                    broken = True
            if broken:
                continue
            entry, rej = _entry(e["issuer"], e["issuer_repo"],
                                e["bundle_path"], bdir, rels,
                                e.get("pinned_commit", ""))
        if rej:
            failures.extend(f"{e['name']}: {r}" for r in rej)
        else:
            rebuilt.append(entry)
    if failures:
        return failures
    text = _j(_assemble(rebuilt, doc.get("pending") or []))
    if text != committed:
        diff = difflib.unified_diff(
            committed.splitlines(), text.splitlines(),
            "registry.json (committed)", "registry.json (rebuilt from "
            "fetched artifacts)", lineterm="")
        return ["registry-drift: committed registry.json is not what the "
                "fetched artifacts regenerate:"] + list(diff)[:120]
    return []


def fetch_bundle(entry_name: str, dest: pathlib.Path,
                 reg_path: pathlib.Path = REGISTRY,
                 fetch=_fetch) -> list[str]:
    """Download one accepted entry's artifacts into `dest`, refusing any byte
    that does not hash to its registry pin."""
    doc = json.loads(reg_path.read_text(encoding="utf-8"))
    entry = next((e for e in doc.get("entries") or []
                  if e["name"] == entry_name), None)
    if entry is None:
        names = [e["name"] for e in doc.get("entries") or []]
        return [f"no accepted entry named {entry_name!r} in registry.json "
                f"(accepted: {names or 'none'})"]
    failures: list[str] = []
    for a in entry["artifacts"]:
        try:
            data = fetch(a["url"])
        except RegistryError as err:
            failures.append(str(err))
            continue
        p = dest / a["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        actual = _sha256(p)
        if actual != a["sha256"]:
            failures.append(f"sha256-mismatch: {a['path']}: registry "
                            f"{a['sha256']}, fetched {actual} — refusing "
                            "the download; the registry pin is the contract")
    return failures


def matrix(doc: dict) -> list[dict]:
    return [{"name": e["name"], "issuer": e["issuer"],
             "issuer_repo": e["issuer_repo"],
             "issuer_commit": e["issuer_commit"],
             "bundle_path": e["bundle_path"]}
            for e in doc.get("entries") or []]


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        try:
            doc = build(ISSUERS)
        except RegistryError as e:
            print(f"ERROR {e}")
            return 2
        REGISTRY.write_text(_j(doc))
        for e in doc["entries"]:
            print(f"ACCEPTED {e['name']}: issuer_commit "
                  f"{e['issuer_commit']}, {len(e['artifacts'])} artifacts")
        for p in doc["pending"]:
            print(f"PENDING  {p['name']}: {p['reason']}")
        print(f"wrote registry.json: {len(doc['entries'])} accepted, "
              f"{len(doc['pending'])} pending")
        return 0
    if args == ["--check-fetched"]:
        failures = check_fetched()
        for f in failures:
            print(f"FAIL {f}")
        print("check-fetched: " + ("PASS — registry.json regenerates "
                                   "byte-identically from fetched artifacts"
                                   if not failures else
                                   f"FAIL — {len(failures)} line(s) above"))
        return 1 if failures else 0
    if len(args) == 4 and args[0] == "--fetch-bundle" and args[2] == "--dest":
        dest = pathlib.Path(args[3])
        failures = fetch_bundle(args[1], dest)
        for f in failures:
            print(f"FAIL {f}")
        if not failures:
            print(f"fetched {args[1]} into {dest}: every artifact "
                  "sha256-verified against the registry")
        return 1 if failures else 0
    if args == ["--emit-matrix"]:
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        m = matrix(doc)
        if not m:
            print(f"no accepted entries in registry.json — nothing to "
                  f"replay; {len(doc.get('pending') or [])} pending "
                  "(python -m vac.registry --list-pending for reasons)",
                  file=sys.stderr)
            return 1
        print(json.dumps(m, separators=(",", ":")))
        return 0
    if args == ["--list-pending"]:
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for p in doc.get("pending") or []:
            print(f"PENDING {p['name']}: {p['reason']}")
        if doc.get("pending"):
            return 1
        print("no pending entries")
        return 0
    print(USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
