"""EXCLUDE's rationales, held to the exceptions their handlers actually name.

tools/mutation_sweep.py drops a refusal from the denominator when nothing
bundle-shaped can reach it. All four excluded lines were justified the same
way: the artifact is a declared ref, so it was opened and sha256'd by
_verify_artifacts before the check runs, and only a filesystem race could make
the later read fail. That is an argument about OSError, and for a handler that
catches OSError alone it is a good one.

Three of the four sat in `except (OSError, UnicodeDecodeError)`, where it
proves nothing. The hash pass reads bytes; a correctly hashed artifact that is
not valid UTF-8 raises on the decode instead. The two render read wrappers
were reachable, had no test, and were scored as though they did not exist
while the sweep reported 1.000 over the rest. They have left EXCLUDE. The
third, the reliability-floor read of RESULTS.md, is reachable the same way; it
is waived below, with a test behind it and the decision still open.

So the rule below: an excluded refusal whose handler names anything besides
OSError has to be listed in WAIVED, with what makes it different. Putting the
render wrappers back turns this red instead of quietly shrinking the
denominator by two.

This file reads vac/verify.py, which is what makes a test a bogus sweep
detector: a mutant removes an emission site, a test that reads sites goes red,
and the refusal scores as caught with no behaviour tested anywhere. It is
written not to be one. A mutant replaces a refusal append with `pass`, which
can only make an EXCLUDE key match FEWER lines, and every assertion here is
one-directional over the lines that are found. A mutant cannot turn it red.
The arity of each key is the sweep's own check, deliberately not repeated
here, because that one IS red under a mutant.
"""
from __future__ import annotations

import ast
import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
SWEEP = REPO / "tools" / "mutation_sweep.py"
SRC = REPO / "vac" / "verify.py"

# Excluded keys whose handler catches more than OSError, each with the reason
# it stays excluded anyway.
#
# "unreadable while checking ": the second RESULTS.md read, in the 0.2
# reliability-floor check. Measured reachable on 2026-09-17, the same way the
# render wrappers are: a 0.2 bundle whose RESULTS.md is correctly hashed and
# not valid UTF-8 reaches the decode. It is covered end to end by
# tests/test_refusals_modeldrift_floor.py, so the exclusion understates the
# score by one rather than hiding a survivor, and whether to drop it is a
# deliberate decision that has not been taken. Delete the waiver in the same
# change that drops the entry.
WAIVED = {"unreadable while checking "}


def _load_sweep():
    spec = importlib.util.spec_from_file_location("_sweep_exclusions", SWEEP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _handler_exceptions(tree: ast.AST, lineno: int) -> set[str] | None:
    """The exception names of the innermost `except` around `lineno`.

    None when the line is in no handler at all, which is not this file's
    business: the OSError-wrapper rationale is not what such an entry would
    be claiming. An empty set is a bare `except`, which claims even less than
    a broad one.
    """
    best: tuple[int, set[str]] | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not node.lineno <= lineno <= (node.end_lineno or node.lineno):
            continue
        names: set[str] = set()
        if isinstance(node.type, ast.Name):
            names = {node.type.id}
        elif isinstance(node.type, ast.Tuple):
            names = {e.id for e in node.type.elts if isinstance(e, ast.Name)}
        if best is None or node.lineno > best[0]:
            best = (node.lineno, names)
    return None if best is None else best[1]


def _broad_exclusions() -> set[str]:
    mod = _load_sweep()
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines()
    broad = set()
    for key in mod.EXCLUDE:
        for n, ln in enumerate(lines, 1):
            # the sweep's own matching: a refusal line containing the key
            if mod.REFUSAL.match(ln) and key in ln:
                names = _handler_exceptions(tree, n)
                if names is not None and (names - {"OSError"} or not names):
                    broad.add(key)
    return broad


def test_an_excluded_refusal_in_a_broad_handler_must_be_waived():
    """The defect this file exists for: `except (OSError, UnicodeDecodeError)`
    excluded on an argument that only covers OSError."""
    broad = _broad_exclusions()
    assert broad <= WAIVED, (
        "excluded refusals whose handler catches more than OSError: "
        f"{sorted(broad - WAIVED)}. The declared-ref hash pass reads bytes, "
        "so it is an argument about OSError and nothing else. Reach the line "
        "with a non-UTF-8 artifact before excluding it.")


def test_the_waiver_is_live():
    """A waiver outlives its entry silently otherwise, and the next reader
    takes it for a rationale. Reads the sweep's constants only, never
    vac/verify.py."""
    mod = _load_sweep()
    assert WAIVED <= set(mod.EXCLUDE), (
        f"waived keys that are not excluded any more: "
        f"{sorted(WAIVED - set(mod.EXCLUDE))}")


SYNTHETIC = """
def narrow(f):
    try:
        read()
    except OSError as e:
        f.append(f"artifact-unparsable: {rel}: {e}")


def broad(f):
    try:
        read()
    except (OSError, UnicodeDecodeError) as e:
        f.append(f"artifact-unparsable: {rel}: {e}")


def loose(f):
    f.append("schema-violation: nothing to catch here")
"""


def test_the_reader_tells_a_broad_handler_from_a_narrow_one():
    """Liveness for the rule above. A reader that returned {"OSError"} for
    everything, or None for everything, would make that test pass while
    checking nothing. Synthetic source on purpose: reading vac/verify.py for
    this would make the file red under a mutant and score a refusal as caught
    with no behaviour behind it.
    """
    tree = ast.parse(SYNTHETIC)
    by_line = {n: ln for n, ln in enumerate(SYNTHETIC.splitlines(), 1)}
    appends = [n for n, ln in by_line.items() if ".append(" in ln]
    assert len(appends) == 3, appends
    narrow, broad, loose = (_handler_exceptions(tree, n) for n in appends)
    assert narrow == {"OSError"}
    assert broad == {"OSError", "UnicodeDecodeError"}
    assert loose is None
