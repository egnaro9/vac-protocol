"""The registry generator must accept only what verifies, record everything
else PENDING with its exact reason (absent emitter, structural failure,
stolen issuer identity — named, never fabricated, never silently dropped),
hash COMMITTED bytes rather than the working tree, and regenerate
byte-identically — from local checkouts and from fetched artifacts alike."""

from __future__ import annotations

import json
import pathlib
import shutil
import re
import subprocess

from vac.registry import (RegistryError, _j, _mutable_ref_failures,
                          build, check_fetched,
                          fetch_bundle, matrix)
from vac.verify import _sha256

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
BP = "certifications/toy-2026-08-14"
RAW_HOST = "https://raw.githubusercontent.com/example/toy-issuer"


def _raw(repo: pathlib.Path) -> str:
    """Artifact URLs are addressed at the commit whose bytes were hashed.

    These used to assert `/main/`, which locked in the defect they should have
    caught: a sha256 pin on a mutable ref stops matching the moment the issuer
    pushes. The test now derives the expected commit the same way the registry
    does, so it fails if the generator ever goes back to a branch name."""
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    return f"{RAW_HOST}/{head}/{BP}"


def _issuer(tmp_path, with_vac=True, mangle=None) -> pathlib.Path:
    repo = tmp_path / "toy-issuer"
    dest = repo / BP
    shutil.copytree(FIX / "valid", dest)
    if not with_vac:
        (dest / "vac.json").unlink()
    if mangle:
        mangle(dest)
    subprocess.run(["git", "init", "-q", str(repo)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@example.com", "commit", "-q",
                    "-m", "x"], check=True, capture_output=True)
    return repo


def _cfg(repo, url="https://github.com/example/toy-issuer") -> dict:
    return {"repo": url, "checkout_env": "VAC_TEST_UNSET_ENV",
            "default_checkout": str(repo), "bundles": "certifications/*"}


def test_valid_committed_bundle_is_accepted(tmp_path):
    repo = _issuer(tmp_path)
    doc = build([_cfg(repo)])
    assert [p["name"] for p in doc["pending"]] == []
    (e,) = doc["entries"]
    assert e["name"] == "toy-issuer/toy-2026-08-14"
    assert e["issuer"] == "example/toy-issuer"
    assert e["issuer_commit"] == "f1e2d3c"  # from vac.json, not from git
    # ...and separately, the commit the registry actually hashed. The manifest
    # states a claim; this records the fact the URLs and pins are anchored to.
    assert re.match(r"^[0-9a-f]{40}$", e["pinned_commit"]), e["pinned_commit"]
    assert e["bundle_path"] == BP
    assert e["status"] == "accepted" and e["challenges"] == []
    assert [a["path"] for a in e["artifacts"]] == [
        "evidence/RESULTS.md", "evidence/bundle.json",
        "evidence/eval_run.json", "evidence/evalmut_fixtures.json", "evidence/evalmut_run.json",
        "evidence/flips.json", "evidence/metrics.json",
        "evidence/models.json", "evidence/narrative.json",
        "evidence/operators.json", "evidence/raw_results.jsonl",
        "evidence/results.json", "evidence/standings.json",
        "evidence/suite-fingerprint.json", "vac.json"]
    raw = _raw(repo)
    for a in e["artifacts"]:
        assert a["sha256"] == _sha256(FIX / "valid" / a["path"])
        assert a["url"] == f"{raw}/{a['path']}"
        # the ref between repo and path must be an immutable commit sha
        assert re.match(rf"^{RAW_HOST}/[0-9a-f]{{40}}/", a["url"]), a["url"]
    # SPEC.md section 5: the replay gate is not skipped silently — every
    # entry says where each gate runs
    assert "replay.yml" in e["gates"]["semantic"]


def test_absent_vac_json_is_pending_not_fabricated(tmp_path):
    doc = build([_cfg(_issuer(tmp_path, with_vac=False))])
    assert doc["entries"] == []
    (p,) = doc["pending"]
    assert p["name"] == "toy-issuer/toy-2026-08-14"
    assert "vac.json is not in the committed tree" in p["reason"]
    assert "sha256" not in json.dumps(p)  # nothing invented for a pending row


def test_absent_bundle_dir_is_pending_not_dropped(tmp_path):
    """A configured single-directory bundle path with nothing committed
    under it is a named hole in the registry, not a silent absence — the
    evalmut case until its emitter lands."""
    repo = _issuer(tmp_path)  # has certifications/... but no vac/
    cfg = {"repo": "https://github.com/example/toy-issuer",
           "checkout_env": "VAC_TEST_UNSET_ENV",
           "default_checkout": str(repo), "bundles": "vac"}
    doc = build([cfg])
    assert doc["entries"] == []
    (p,) = doc["pending"]
    assert p["name"] == "toy-issuer/vac"
    assert p["bundle_path"] == "vac"
    assert "no committed files at vac" in p["reason"]
    assert "sha256" not in json.dumps(p)  # nothing invented for a pending row


def test_registry_hashes_committed_bytes_not_the_working_tree(tmp_path):
    repo = _issuer(tmp_path)
    (repo / BP / "evidence/bundle.json").write_text("{\"cooked\": true}\n")
    (e,) = build([_cfg(repo)])["entries"]
    art = next(a for a in e["artifacts"]
               if a["path"] == "evidence/bundle.json")
    assert art["sha256"] == _sha256(FIX / "valid/evidence/bundle.json")


def test_structural_failure_is_pending_with_named_reasons(tmp_path):
    def mangle(dest):
        man = json.loads((dest / "vac.json").read_text())
        man["evidence"][0]["sha256"] = "0" * 64
        (dest / "vac.json").write_text(_j(man))
    doc = build([_cfg(_issuer(tmp_path, mangle=mangle))])
    assert doc["entries"] == []
    (p,) = doc["pending"]
    assert "refused at generation" in p["reason"]
    assert "sha256-mismatch" in p["reason"]


def test_foreign_issuer_identity_is_refused(tmp_path):
    doc = build([_cfg(_issuer(tmp_path),
                      url="https://github.com/somebody/else")])
    assert doc["entries"] == []
    assert "issuer-mismatch" in doc["pending"][0]["reason"]


def test_host_prefixed_issuer_binds_to_the_same_identity(tmp_path):
    def mangle(dest):
        man = json.loads((dest / "vac.json").read_text())
        man["protocol"]["issuer"] = "github.com/example/toy-issuer"
        # editing the manifest is safe: vac.json is never its own evidence
        (dest / "vac.json").write_text(_j(man))
    doc = build([_cfg(_issuer(tmp_path, mangle=mangle))])
    assert len(doc["entries"]) == 1 and doc["pending"] == []
    assert doc["entries"][0]["issuer"] == "example/toy-issuer"


def test_registry_regenerates_byte_identically(tmp_path):
    cfg = _cfg(_issuer(tmp_path))
    assert _j(build([cfg])) == _j(build([cfg]))


def _served_by(repo: pathlib.Path):
    raw = _raw(repo)

    def fetch(url: str) -> bytes:
        assert url.startswith(raw + "/"), url
        rel = url[len(raw) + 1:]
        blob = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "blob", f"HEAD:{BP}/{rel}"],
            capture_output=True)
        if blob.returncode != 0:
            raise RegistryError(f"fetch-failed: {url}: HTTP 404 — is the "
                                "emitter commit pushed to main?")
        return blob.stdout
    return fetch


def test_check_fetched_round_trips(tmp_path):
    repo = _issuer(tmp_path)
    reg = tmp_path / "registry.json"
    reg.write_text(_j(build([_cfg(repo)])))
    assert check_fetched(reg, fetch=_served_by(repo)) == []


def test_check_fetched_names_drifted_bytes(tmp_path):
    repo = _issuer(tmp_path)
    reg = tmp_path / "registry.json"
    reg.write_text(_j(build([_cfg(repo)])))
    served = _served_by(repo)

    def drifted(url):
        data = served(url)
        return data + b" " if url.endswith("evidence/bundle.json") else data
    failures = check_fetched(reg, fetch=drifted)
    assert any(f.startswith("sha256-drift: toy-issuer/toy-2026-08-14/"
                            "evidence/bundle.json") for f in failures)


def test_check_fetched_names_the_unfetchable_artifact(tmp_path):
    repo = _issuer(tmp_path)
    reg = tmp_path / "registry.json"
    reg.write_text(_j(build([_cfg(repo)])))

    def gone(url):
        raise RegistryError(f"fetch-failed: {url}: HTTP 404 — is the "
                            "emitter commit pushed to main?")
    failures = check_fetched(reg, fetch=gone)
    assert failures and all("HTTP 404" in f for f in failures)


def test_check_fetched_flags_a_hand_edited_registry(tmp_path):
    """The committed registry must be exactly what the artifacts regenerate —
    a hand-sweetened capability line is registry-drift, not an edit."""
    repo = _issuer(tmp_path)
    doc = build([_cfg(repo)])
    doc["entries"][0]["capability"] = "does everything, trust me"
    reg = tmp_path / "registry.json"
    reg.write_text(_j(doc))
    failures = check_fetched(reg, fetch=_served_by(repo))
    assert failures and failures[0].startswith("registry-drift:")


def test_fetch_bundle_refuses_drift_and_unknown_names(tmp_path):
    repo = _issuer(tmp_path)
    reg = tmp_path / "registry.json"
    reg.write_text(_j(build([_cfg(repo)])))
    dest = tmp_path / "dl"
    assert fetch_bundle("toy-issuer/toy-2026-08-14", dest, reg,
                        fetch=_served_by(repo)) == []
    assert (dest / "vac.json").is_file()
    served = _served_by(repo)
    failures = fetch_bundle("toy-issuer/toy-2026-08-14", tmp_path / "dl2",
                            reg, fetch=lambda u: served(u) + b" ")
    assert failures and all(f.startswith("sha256-mismatch:")
                            for f in failures)
    assert fetch_bundle("no/such", tmp_path / "dl3", reg,
                        fetch=served)[0].startswith("no accepted entry")


def test_matrix_carries_exactly_what_replay_needs(tmp_path):
    doc = build([_cfg(_issuer(tmp_path))])
    (m,) = matrix(doc)
    assert m == {"name": "toy-issuer/toy-2026-08-14",
                 "issuer": "example/toy-issuer",
                 "issuer_repo": "https://github.com/example/toy-issuer",
                 "issuer_commit": "f1e2d3c",
                 "bundle_path": BP}


def test_committed_registry_is_wellformed():
    doc = json.loads((ROOT / "registry.json").read_text())
    assert doc["registry_version"] == "0.1"
    names = [e["name"] for e in doc["entries"]] + \
            [p["name"] for p in doc["pending"]]
    assert len(names) == len(set(names))
    for e in doc["entries"]:
        assert e["status"] in ("accepted", "confirmed", "narrowed",
                               "superseded", "invalidated")
        assert e["issuer_commit"] and e["artifacts"]
        for a in e["artifacts"]:
            assert len(a["sha256"]) == 64
            assert a["url"].startswith("https://raw.githubusercontent.com/")
    for p in doc["pending"]:
        assert p["reason"]


def test_a_sha256_pin_on_a_mutable_ref_is_refused():
    """The defect this registry shipped with, now a failing condition.

    Every artifact was addressed at `main` while carrying a sha256 pin. That
    is a promise that expires on the issuer's next push, and on 2026-08-21 it
    had: two entries served bytes that no longer matched their own pins, and
    the daily verification had been failing for four days. A pin and a mutable
    ref cannot both be authoritative.
    """
    doc = {"entries": [{
        "name": "toy/entry",
        "artifacts": [
            {"path": "vac.json", "sha256": "0" * 64,
             "url": f"{RAW_HOST}/main/{BP}/vac.json"},
            {"path": "ok.json", "sha256": "0" * 64,
             "url": f"{RAW_HOST}/{'a' * 40}/{BP}/ok.json"},
        ]}]}
    failures = _mutable_ref_failures(doc)
    assert len(failures) == 1, failures
    assert "mutable-ref" in failures[0]
    assert "vac.json" in failures[0]
    assert "'main'" in failures[0]


def test_the_mutable_ref_guard_passes_a_fully_pinned_registry():
    doc = {"entries": [{
        "name": "toy/entry",
        "artifacts": [{"path": "vac.json", "sha256": "0" * 64,
                       "url": f"{RAW_HOST}/{'b' * 40}/{BP}/vac.json"}]}]}
    assert _mutable_ref_failures(doc) == []
