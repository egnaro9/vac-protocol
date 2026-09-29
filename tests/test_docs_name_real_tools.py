"""A documented command must name a file this repo actually has.

`paper/arxiv/v2/CLAIMS.md` opened with "Regenerate this file with the command in
its last section. Nothing below is typed by hand." over a block that ran
`paper/arxiv/v2/regen_claims.py`. That script was never written and never
committed, so the sentence read as provenance for a table that was in fact typed
by hand. Nothing failed, because nothing ever ran the command or looked for the
file. That is the same shape as a coverage ledger nobody can fail: a claim that
costs nothing to make and nothing to keep.

A test cannot decide whether prose was typed by hand. What it can decide is the
mechanical half: if a doc tells a reader to run a script, the script exists.

The rule is narrow on purpose.

  * It fires on an instruction, `python X.py` or `python3 X.py`, and not on a
    mention. `V2_CHANGE_LEDGER.md` names `regen_claims.py` repeatedly as the
    record of this very defect, and must not be flagged for saying so.
  * It fires only on a path rooted at a directory this repo has. Issuer
    instructions in `SPEC.md` and `README.md` name scripts that live in other
    repositories (`audit/run_audit.py`, `emit_vac.py`); this repo cannot
    speak to whether those exist.
  * It does not read review evidence, `paper/arxiv/v2/review/`, and nothing
    else is exempt. See EVIDENCE_DIRS for why and for how narrow that is.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC_SUFFIXES = {".md", ".txt"}
SKIP = {".git", ".venv", "__pycache__", "node_modules", "vac_protocol.egg-info"}

# Review evidence is exempt, and only review evidence. A review packet quotes
# the text it reviewed, withdrawn commands included: packet 1 reproduces the
# `python3 paper/arxiv/v2/regen_claims.py` line that CLAIMS.md used to carry,
# as the record of what was withdrawn and why. A quotation of a withdrawn
# instruction is not an instruction, and editing the quotation to satisfy this
# test would falsify the evidence the reviewer is reading. Packet 1 is also
# frozen for review, so it cannot be edited at all.
#
# The cost, stated: a reproduction command a review packet itself gives is not
# checked by this test. The packets carry their own transcripts for that.
#
# The match is on whole path components from the repo root, so
# `paper/arxiv/v2/REVIEW_PACKAGE.txt`, a `paper/arxiv/v2/review_notes.md`, a
# `review/` directory anywhere else, and the rest of `paper/arxiv/v2/` are all
# still scanned. The tests at the bottom of this file hold it to that.
EVIDENCE_DIRS = (("paper", "arxiv", "v2", "review"),)

# `python X.py` or `python3 X.py`. The lookahead keeps `python3 -m vac.verify`
# and any other flag out: an option is not a script path.
INVOCATION = re.compile(r"\bpython3?\s+(?!-)([A-Za-z0-9_./-]+\.py)\b")

# A doc that carries in-repo commands and is committed, so the scan below has
# subjects in a clean checkout and not only in a working tree. If this file is
# renamed, point LIVENESS_DOC at whatever replaced it rather than deleting the
# assertion: a scan with nothing to scan passes for the wrong reason.
LIVENESS_DOC = "paper/arxiv/AUDIT_PREPUB.md"


def repo_dirs(root: pathlib.Path = ROOT) -> set[str]:
    return {p.name for p in root.iterdir()
            if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP}


def in_repo(rel: str, dirs: set[str]) -> bool:
    """A path this repo can answer for: it has a directory part, and that
    directory is one of ours. A bare `emit_vac.py` names a script in an issuer
    repo's root, not ours, so it is not in scope."""
    return "/" in rel and rel.split("/", 1)[0] in dirs


def is_evidence(rel_path: pathlib.PurePath) -> bool:
    """A file strictly inside one of EVIDENCE_DIRS, compared component by
    component, case included."""
    parts = rel_path.parts
    return any(len(parts) > len(d) and parts[:len(d)] == d
               for d in EVIDENCE_DIRS)


def commands(text: str) -> list[str]:
    return [m.group(1) for line in lines(text) for m in INVOCATION.finditer(line)]


def lines(text: str) -> list[str]:
    """split, not splitlines. str.splitlines also breaks on a lone carriage
    return, a vertical tab, a form feed and the Unicode separators, none of
    which grep or an editor treats as a line break. One of them anywhere above
    a finding would make the reported line number wrong, and a line number that
    does not match what the reader's grep says is worse than none."""
    return text.split("\n")


def scan(root: pathlib.Path = ROOT) -> list[tuple[str, int, str]]:
    """Every in-repo script an instruction in a doc tells a reader to run."""
    dirs = repo_dirs(root)
    out: list[tuple[str, int, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in DOC_SUFFIXES:
            continue
        rel_path = path.relative_to(root)
        if any(part in SKIP or part.startswith(".") for part in rel_path.parts[:-1]):
            continue
        if is_evidence(rel_path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(lines(text), 1):
            for m in INVOCATION.finditer(line):
                rel = m.group(1)
                if in_repo(rel, dirs):
                    out.append((str(rel_path), n, rel))
    return out


def missing(root: pathlib.Path = ROOT) -> list[tuple[str, int, str]]:
    """The findings: scanned instructions whose script is not on disk."""
    return [(doc, n, rel) for doc, n, rel in scan(root)
            if not (root / rel).exists()]


def test_every_documented_in_repo_command_names_a_file_that_exists():
    found = missing()
    assert found == [], (
        "a doc tells a reader to run a script this repo does not have: "
        + "; ".join(f"{doc}:{n} runs {rel}" for doc, n, rel in found)
    )


def test_the_scan_reaches_the_docs_that_carry_commands():
    """Liveness. The refusal above is worth nothing if the scan finds nothing,
    which is what happens when the regex stops matching or the walk stops
    descending."""
    found = scan()
    assert len(found) >= 3, f"the scan found {len(found)} in-repo commands, expected at least 3"
    assert any(doc == LIVENESS_DOC for doc, _, _ in found), (
        f"{LIVENESS_DOC} carries in-repo commands and is committed; the scan "
        "reached none of them"
    )


def test_a_command_naming_another_repo_is_not_flagged():
    """The issuer instructions in SPEC.md and README.md must stay legal. If this
    starts failing, the rule has widened to paths this repo cannot answer for."""
    dirs = repo_dirs()
    text = ("reproduced byte-identically by `python audit/run_audit.py` at the "
            "stamped commit, or by `python3 emit_vac.py`, or by "
            "`$ python issuer/audit/run_audit.py --check evidence/results.json`")
    assert commands(text) == ["audit/run_audit.py", "emit_vac.py",
                              "issuer/audit/run_audit.py"]
    assert [c for c in commands(text) if in_repo(c, dirs)] == []


def test_naming_a_script_without_telling_anyone_to_run_it_is_not_flagged():
    """`V2_CHANGE_LEDGER.md` is the record of this defect. It names the missing
    script in prose and in an `ls` quotation, and neither is an instruction."""
    text = ("CLAIMS.md names `paper/arxiv/v2/regen_claims.py`, which does not "
            "exist.\n`ls` of `regen_claims.py`: no such file.\n"
            "Write `regen_claims.py` or delete `CLAIMS.md`'s provenance line.")
    assert commands(text) == []


def test_an_instruction_to_run_a_missing_in_repo_script_is_flagged():
    """The positive case, on the exact line that was in CLAIMS.md. Without this
    the two refusals above could both be passing on an empty match set."""
    dirs = repo_dirs()
    line = ("cd ~/vac-protocol && python3 paper/arxiv/v2/regen_claims.py   "
            "# emits this file")
    found = commands(line)
    assert found == ["paper/arxiv/v2/regen_claims.py"]
    assert in_repo(found[0], dirs)
    # The refusal, on a sentinel rather than on regen_claims.py. Writing that
    # generator is still an open option, and this test must not be what goes
    # red when someone takes it.
    ghost = "tools/no_such_script_by_design.py"
    assert in_repo(ghost, dirs)
    assert not (ROOT / ghost).exists()


def test_a_reported_line_number_is_the_one_grep_would_print():
    """The characters str.splitlines breaks on and grep does not. A doc holding
    any of them above a finding would shift every line number after it."""
    for odd in ("\r", "\v", "\f", "\x1c", "\x85", "\u2028"):
        command = "python3 tools/fixture_corpus_score.py"
        text = f"filler{odd}filler\n{command}\n"
        assert text.splitlines().index(command) == 2, (
            f"{odd!r} is not a character splitlines breaks on, so it proves "
            "nothing here; drop it from this list")
        hit = [n for n, line in enumerate(lines(text), 1) if command in line]
        assert hit == [2], f"{odd!r} moved the finding to line {hit}"


# The review exemption, both edges, on a built tree rather than on this repo's,
# so neither edge depends on what a packet happens to hold today. The withdrawn
# line is the real one; the ghost is a sentinel no tree will ever gain.
WITHDRAWN = "cd ~/vac-protocol && python3 paper/arxiv/v2/regen_claims.py   # emits this file\n"
GHOST = "tools/no_such_script_by_design.py"


def _tree(root: pathlib.Path, docs: dict[str, str]) -> pathlib.Path:
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "real_tool.py").write_text("", encoding="utf-8")
    for rel, text in docs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_review_evidence_quoting_a_withdrawn_command_is_not_flagged(tmp_path):
    """The packet 1 shape: a review file quoting the withdrawn line, next to a
    doc outside review/ whose command resolves. Nothing is missing. Without the
    exemption the quotation is a finding and this goes red."""
    root = _tree(tmp_path, {
        "paper/arxiv/v2/review/packet1/B2_companion_drafts.md":
            "| 279-284 | the block `" + WITHDRAWN.strip() + "` was withdrawn |\n",
        "paper/arxiv/v2/review/packet2/C_docs_guard.md":
            "the guard used to fail on `python3 " + GHOST + "` in a quote\n",
        "paper/arxiv/v2/CLAIMS.md": "Run `python3 tools/real_tool.py` first.\n",
    })
    assert missing(root) == []
    # Exempt means not read, not read and forgiven: the resolving command
    # outside review/ is still a subject, so the scan is not empty.
    assert scan(root) == [("paper/arxiv/v2/CLAIMS.md", 1, "tools/real_tool.py")]


def test_outside_review_evidence_a_missing_tool_is_still_flagged(tmp_path):
    """Every near miss of the exempt directory is still scanned. Each doc here
    would be exempted by one plausible wrong way to write is_evidence: any
    directory named review, a string prefix without the separator, a
    case-insensitive prefix, or the whole of v2."""
    near_misses = [
        "paper/arxiv/v2/CLAIMS.md",               # the rest of v2
        "paper/arxiv/v2/REVIEW_PACKAGE.txt",      # case-insensitive prefix
        "paper/arxiv/v2/review_notes.md",         # prefix with no separator
        "paper/arxiv/v2/reviewed/notes.md",       # prefix with no separator
        "paper/arxiv/review/notes.md",            # a review dir, other depth
        "docs/review/notes.md",                   # a review dir, elsewhere
    ]
    # A `Review/` sibling is not in this tree: on a case-insensitive disk it
    # is the same directory as `review/`. The path-only test below covers it.
    with_review = near_misses + ["paper/arxiv/v2/review/packet9/quote.md"]
    root = _tree(tmp_path, {rel: f"then run `python3 {GHOST}`\n"
                            for rel in with_review})
    assert sorted(doc for doc, _, _ in missing(root)) == sorted(near_misses)
    assert all(rel == GHOST for _, _, rel in missing(root))


def test_the_exemption_is_a_directory_this_repo_can_hold():
    """is_evidence on paths, without a tree. A file directly named `review`
    at that level is not inside the directory, and the directory itself is
    not a file inside it."""
    P = pathlib.PurePosixPath
    assert is_evidence(P("paper/arxiv/v2/review/packet1/BCD_critic.md"))
    assert is_evidence(P("paper/arxiv/v2/review/x.md"))
    assert not is_evidence(P("paper/arxiv/v2/review"))
    assert not is_evidence(P("paper/arxiv/v2/review.md"))
    assert not is_evidence(P("paper/arxiv/v2/REVIEW_PACKAGE.txt"))
    assert not is_evidence(P("paper/arxiv/v2/Review/x.md"))
    assert not is_evidence(P("x/paper/arxiv/v2/review/x.md"))
