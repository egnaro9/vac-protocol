"""vac draft derives every mechanical field and refuses to author judgment:
per-file sha256, issuer, and pinned commit come from what is actually there;
capability, scope, limitations, subject, protocol semantics, results, and
the replay run/compare lines come out as explicit TODO(...) markers the
verifier refuses by name. Both halves of the contract are pinned here —
the derivations are exact, the markers are refused, a dirty tree warns but
drafts, and the README flow (draft -> human authors -> verify green) is
proven end to end."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

from vac.draft import _issuer_from_remote, main as draft
from vac.verify import verify_bundle

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
REMOTE = "https://github.com/example/toy-issuer"


def _artifacts(dest: pathlib.Path) -> None:
    """The valid fixture's evidence files, manifest removed — a directory
    of artifacts awaiting a draft."""
    shutil.copytree(FIX / "valid", dest)
    (dest / "vac.json").unlink()


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t",
         "-c", "user.email=t@example.com", *args],
        check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path: pathlib.Path, remote: str = REMOTE) -> pathlib.Path:
    """An issuer-shaped checkout: the bundle is a SUBDIRECTORY of the repo
    (the real layout — certifications/x, vac/), returned as the bundle
    dir; git facts must be found through the enclosing repo."""
    repo = tmp_path / "repo"
    d = repo / "my-claim"
    _artifacts(d)
    subprocess.run(["git", "init", "-q", str(repo)],
                   check=True, capture_output=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "x")
    _git(repo, "remote", "add", "origin", remote)
    return d


def _head(repo: pathlib.Path) -> str:
    return _git(repo, "rev-parse", "--short=7", "HEAD")


def test_draft_derives_the_mechanical_fields(tmp_path, capsys):
    d = _repo(tmp_path)
    assert draft([str(d)]) == 0
    man = json.loads((d / "vac.json").read_text())
    # evidence: exactly the valid manifest's list — same files, same
    # hashes, same order — derived, not transcribed
    valid = json.loads((FIX / "valid/vac.json").read_text())
    assert man["evidence"] == valid["evidence"]
    # issuer + commit from the enclosing repo; clone/checkout filled
    head = _head(d)
    assert man["protocol"]["issuer"] == "example/toy-issuer"
    assert man["protocol"]["issuer_commit"] == head
    assert man["replay"]["issuer_commit"] == head
    assert man["replay"]["commands"][:2] == [
        f"git clone {REMOTE} issuer", f"git -C issuer checkout {head}"]
    out = capsys.readouterr().out
    assert "never infers claim.scope or claim.limitations" in out


def test_drafted_bundle_is_refused_exactly_like_the_fixture(tmp_path):
    """A live draft and the committed draft fixture carry the same 16
    unauthored markers — the exact reason strings are pinned in
    test_verify.DRAFT_REASONS against the fixture; here the live output
    is held to the identical refusal."""
    d = _repo(tmp_path)
    assert draft([str(d)]) == 0
    failures = verify_bundle(d)
    assert failures == verify_bundle(FIX / "tamper-draft-incomplete")
    assert len(failures) == 16
    assert all(f.startswith("draft-incomplete: ") for f in failures)


def test_draft_then_author_then_verify_green(tmp_path):
    """The README flow, end to end: draft over bare artifacts, a human
    authors every judgment field (here: the valid fixture's real values),
    and the same directory verifies clean — proving the drafted
    mechanical half needed no correction."""
    d = tmp_path / "b"
    _artifacts(d)
    assert draft([str(d)]) == 0
    man = json.loads((d / "vac.json").read_text())
    valid = json.loads((FIX / "valid/vac.json").read_text())
    for k in ("claim", "subject", "protocol", "results", "replay"):
        man[k] = valid[k]
    assert man == valid  # the drafted evidence list was already exact
    (d / "vac.json").write_text(json.dumps(man, indent=1) + "\n")
    assert verify_bundle(d) == []


def test_dirty_tree_warns_but_drafts(tmp_path, capsys):
    """Drafting is not certifying: a dirty tree gets a printed warning,
    never a refusal — the draft still lands, hashing the bytes present."""
    d = _repo(tmp_path)
    art = d / "evidence/bundle.json"
    art.write_text(art.read_text() + "\n")
    assert draft([str(d)]) == 0
    err = capsys.readouterr().err
    assert "WARNING: working tree dirty" in err
    assert "Drafting is not certifying" in err
    man = json.loads((d / "vac.json").read_text())
    assert man["protocol"]["issuer_commit"] == _head(d)


def test_no_enclosing_repo_marks_issuer_and_commit(tmp_path):
    """Absent git facts become markers, never guesses."""
    d = tmp_path / "b"
    _artifacts(d)
    assert draft([str(d)]) == 0
    man = json.loads((d / "vac.json").read_text())
    assert man["protocol"]["issuer"].startswith("TODO(")
    assert man["protocol"]["issuer_commit"].startswith("TODO(")
    assert man["replay"]["issuer_commit"].startswith("TODO(")
    assert all(c.startswith("TODO(")
               for c in man["replay"]["commands"][:2])


def test_ssh_remote_parses_to_the_same_issuer(tmp_path):
    d = _repo(tmp_path, remote="git@github.com:example/toy-issuer.git")
    assert draft([str(d)]) == 0
    man = json.loads((d / "vac.json").read_text())
    assert man["protocol"]["issuer"] == "example/toy-issuer"
    # the clone line carries the remote verbatim — a URL is opaque text
    assert man["replay"]["commands"][0] == \
        "git clone git@github.com:example/toy-issuer.git issuer"
    assert _issuer_from_remote("https://github.com/a/b/") == "a/b"
    assert _issuer_from_remote("justonepart") is None


def test_draft_is_deterministic(tmp_path):
    d = _repo(tmp_path)
    assert draft([str(d)]) == 0
    first = (d / "vac.json").read_bytes()
    (d / "vac.json").unlink()
    assert draft([str(d)]) == 0
    assert (d / "vac.json").read_bytes() == first


def test_refuses_to_overwrite_an_existing_manifest(tmp_path, capsys):
    d = tmp_path / "b"
    shutil.copytree(FIX / "valid", d)  # vac.json present and authored
    before = (d / "vac.json").read_bytes()
    assert draft([str(d)]) == 2
    assert "refusing to overwrite" in capsys.readouterr().out
    assert (d / "vac.json").read_bytes() == before


def test_a_repo_root_is_refused(tmp_path, capsys):
    """A bundle is closed: drafting a directory that contains .git would
    put git internals on the evidence list. Named refusal, not a hash of
    the object database."""
    d = _repo(tmp_path).parent  # the repo root, .git inside
    assert draft([str(d)]) == 2
    assert "contains .git" in capsys.readouterr().out
    assert not (d / "vac.json").exists()


def test_a_dir_without_artifacts_is_refused(tmp_path, capsys):
    d = tmp_path / "empty"
    d.mkdir()
    assert draft([str(d)]) == 2
    assert "at least one" in capsys.readouterr().out
    assert not (d / "vac.json").exists()


def test_help_states_the_no_inference_rule(capsys):
    assert draft(["--help"]) == 2
    out = capsys.readouterr().out
    assert "never infers claim.scope or claim.limitations" in out
