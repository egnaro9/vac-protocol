"""Submission scaffolder for VAC capability evidence bundles (SPEC.md §2.7).

`python -m vac.draft <bundle-dir>` writes `<bundle-dir>/vac.json` with every
MECHANICAL manifest field derived from what is actually there — sha256 for
each artifact file present, `protocol.issuer` (owner/name from the enclosing
repo's git remote), `protocol.issuer_commit` (HEAD, with a dirty-tree
warning printed but drafting allowed: drafting is not certifying), the
replay skeleton's clone/checkout lines, and a `results.checks` skeleton
naming the known profiles to pick from — and every JUDGMENT field emitted
as an explicit `TODO(<field>): <one-line guidance>` marker for a human to
replace. The verifier refuses any manifest still carrying a marker
(`draft-incomplete`), so a draft can never be passed off as a claim.

vac draft NEVER infers claim.scope or claim.limitations. What a claim
covers and what it does NOT cover are the load-bearing judgment of the
bundle; a tool that guessed them would manufacture exactly the
advertisement VAC exists to refuse.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from .verify import PROFILES, VAC_VERSION, _sha256, _todo_failures

USAGE = """\
usage: python -m vac.draft <bundle-dir>

Scaffolds <bundle-dir>/vac.json over the artifact files present:
MECHANICAL fields are derived — per-file sha256, issuer (owner/name from
the enclosing repo's git remote), issuer_commit (HEAD; a dirty tree is a
printed warning, not a refusal — drafting is not certifying), the replay
skeleton's clone/checkout lines, a results.checks skeleton naming the
profiles to pick from. JUDGMENT fields — claim.capability, claim.scope,
claim.limitations, subject, protocol semantics, results, the replay
run/compare lines — come out as TODO(...) markers with one-line guidance,
and python -m vac.verify refuses the manifest (draft-incomplete) until a
human replaces every one.

vac draft never infers claim.scope or claim.limitations: what a claim
covers and what it does not cover are authored judgments, not derivable
metadata (SPEC.md §2.7)."""


def _todo(field: str, guidance: str) -> str:
    return f"TODO({field}): {guidance}"


# --------------------------------------------------------------------------
# Git facts — every derivation best-effort: absent facts become markers,
# never guesses.
def _git(cwd: pathlib.Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip()


def _issuer_from_remote(url: str) -> str | None:
    """Trailing owner/name from an https or ssh remote URL, or None."""
    tail = url.rstrip("/")
    if tail.endswith(".git"):
        tail = tail[:-4]
    parts = [p for p in tail.replace(":", "/").split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else None


def git_facts(bundle_dir: pathlib.Path) -> dict:
    """{'top','commit','dirty','remote','issuer'} from the repo enclosing
    `bundle_dir`; {} when there is none. Values are None when a fact
    cannot be derived (no HEAD, no remote) — the drafter marks those."""
    rc, top = _git(bundle_dir, "rev-parse", "--show-toplevel")
    if rc != 0:
        return {}
    rc, commit = _git(bundle_dir, "rev-parse", "--short=7", "HEAD")
    facts: dict = {"top": top, "commit": commit if rc == 0 and commit
                   else None}
    rc, status = _git(bundle_dir, "status", "--porcelain")
    facts["dirty"] = rc == 0 and bool(status)
    remote = None
    rc, names = _git(bundle_dir, "remote")
    if rc == 0 and names:
        remotes = names.splitlines()
        name = "origin" if "origin" in remotes else remotes[0]
        rc, url = _git(bundle_dir, "remote", "get-url", name)
        remote = url if rc == 0 and url else None
    facts["remote"] = remote
    facts["issuer"] = _issuer_from_remote(remote) if remote else None
    return facts


# --------------------------------------------------------------------------
def scan_artifacts(bundle_dir: pathlib.Path) -> list[dict]:
    """Every file under the directory except vac.json, hashed — exactly the
    closure the verifier will demand (SPEC.md §1)."""
    rels = sorted(p.relative_to(bundle_dir).as_posix()
                  for p in bundle_dir.rglob("*") if p.is_file())
    return [{"path": r, "sha256": _sha256(bundle_dir / r)}
            for r in rels if r != "vac.json"]


def draft_manifest(evidence: list[dict], *, issuer: str | None = None,
                   commit: str | None = None,
                   remote: str | None = None) -> dict:
    """The drafted manifest — a pure function of the artifact list and the
    git facts, so fixtures and tests regenerate it byte-identically.
    Mechanical fields filled; every judgment field a TODO(...) marker."""
    ic = commit or _todo("protocol.issuer_commit",
                         "no git HEAD found — the issuer commit that "
                         "produced and regrades this evidence")
    return {
        "vac_version": VAC_VERSION,
        "claim": {
            "capability": _todo("claim.capability",
                                "one sentence — the capability this "
                                "evidence supports, and no more"),
            "scope": _todo("claim.scope",
                           "where the claim holds — task set, grading "
                           "regime, environment; never inferred"),
            "limitations": [
                _todo("claim.limitations",
                      "the non-claims — what this evidence does NOT "
                      "cover; at least one; never inferred"),
            ],
        },
        "subject": {
            "kind": _todo("subject.kind", "'agent' or 'suite-archetype'"),
            "id": _todo("subject.id",
                        "the subject's name exactly as the issuer ran it"),
            "version": {
                "TODO": _todo("subject.version",
                              "every identifier that pins the exact "
                              "subject — model id, harness commit, "
                              "config, seed"),
            },
        },
        "protocol": {
            "issuer": issuer or _todo("protocol.issuer",
                                      "no git remote found — the issuing "
                                      "repo as plain owner/name text"),
            "issuer_commit": ic,
            "task": _todo("protocol.task",
                          "task family / archetype / board identifier "
                          "within the issuer"),
            "hashes": {
                "TODO": _todo("protocol.hashes",
                              "named content hashes pinning protocol "
                              "inputs — e.g. a taskset hash or a "
                              "suite-file sha256"),
            },
            "grading": _todo("protocol.grading",
                             "how verdicts are computed — must describe "
                             "a deterministic procedure"),
            "control_policy": _todo("protocol.control_policy",
                                    "the negative controls the protocol "
                                    "ran — null/oracle subjects, clean "
                                    "twins"),
        },
        "evidence": evidence,
        "results": {
            "summary": {
                "TODO": _todo("results.summary",
                              "headline numbers — every one must be "
                              "re-earned by a check below (SPEC.md "
                              "§2.5)"),
            },
            "checks": [
                {"profile": _todo("results.checks[0].profile",
                                  "pick one of: " + ", ".join(PROFILES)),
                 "TODO": _todo("results.checks[0]",
                               "add the chosen profile's artifact "
                               "reference keys and its expect object "
                               "(SPEC.md §3)")},
            ],
        },
        "replay": {
            "issuer_commit": commit or _todo("replay.issuer_commit",
                                             "must equal "
                                             "protocol.issuer_commit"),
            "commands": [
                f"git clone {remote} issuer" if remote else
                _todo("replay.commands",
                      "no git remote found — git clone <issuer repo> "
                      "issuer"),
                f"git -C issuer checkout {commit}" if commit else
                _todo("replay.commands",
                      "git -C issuer checkout <issuer_commit>"),
                _todo("replay.commands",
                      "install, then run the issuer's deterministic "
                      "regrader/audit over this bundle's artifacts"),
                _todo("replay.commands",
                      "byte-compare the regraded output against the "
                      "committed artifacts; nonzero on any difference"),
            ],
            "expected": _todo("replay.expected",
                              "the exact outcome — exit code and report "
                              "text"),
        },
    }


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] in ("-h", "--help"):
        print(USAGE)
        return 2
    d = pathlib.Path(args[0])
    if not d.is_dir():
        print(f"{USAGE}\nnot a directory: {d}")
        return 2
    if (d / "vac.json").exists():
        print(f"refusing to overwrite {d / 'vac.json'} — drafting over an "
              "existing manifest would destroy authored judgment; delete "
              "it first to re-draft")
        return 2
    if (d / ".git").exists():
        print(f"refusing to draft {d} — it contains .git, and a bundle is "
              "closed (SPEC.md §1): every file would have to be listed as "
              "evidence, git internals included. Put the artifacts in a "
              "subdirectory of the repo and draft that.")
        return 2
    evidence = scan_artifacts(d)
    if not evidence:
        print(f"no artifact files under {d} — a bundle needs at least one "
              "evidence artifact (SPEC.md §2.4)")
        return 2
    facts = git_facts(d)
    if facts.get("dirty") and facts.get("commit"):
        print(f"WARNING: working tree dirty at {facts['top']} — "
              f"issuer_commit {facts['commit']} may not contain the bytes "
              "just hashed. Drafting is not certifying; commit before "
              "anything downstream treats this manifest as a claim.",
              file=sys.stderr)
    m = draft_manifest(evidence, issuer=facts.get("issuer"),
                       commit=facts.get("commit"),
                       remote=facts.get("remote"))
    (d / "vac.json").write_text(json.dumps(m, indent=1) + "\n",
                                encoding="utf-8")
    derived = [f"{len(evidence)} artifact(s) hashed"]
    if facts.get("issuer"):
        derived.append(f"issuer {facts['issuer']}")
    if facts.get("commit"):
        derived.append(f"issuer_commit {facts['commit']}")
    print(f"drafted {d / 'vac.json'}: " + ", ".join(derived))
    print(f"{len(_todo_failures(m))} judgment field(s) remain as TODO(...) "
          "markers — python -m vac.verify refuses this bundle "
          "(draft-incomplete) until a human replaces every one. Only "
          "mechanical fields were derived; vac draft never infers "
          "claim.scope or claim.limitations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
