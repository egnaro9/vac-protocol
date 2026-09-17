"""What the obligation tools read from the artifacts, read one way.

Two facts feed the ledger that are not human judgement: which refusal codes
vac/verify.py emits, and which tests reference each code. Both
tools/build_obligations.py and tools/check_obligations.py take them from here.
The checker still restates every judgement table instead of importing the
builder; this module holds no judgement, only extraction, and sharing it is
what keeps the builder from deriving a binding the checker would refuse.

Both facts used to come from regexes over raw text, and both were wrong:

  codes     "([a-z][a-z0-9-]{4,40}): over the whole of vac/verify.py matched
            `suite` from the tail of a raw-aggregate-mismatch message and
            `usage` from the CLI usage string, and missed every code emitted
            bare (`empty-limitations`) or by print (`unsafe-archive`).
  bindings  splitting a test file at `def test_` gave each test everything up
            to the next one, so a comment sitting after a test bound it to
            whatever code the comment named.

So both are read from the AST. A code is the leading token of a refusal
literal at an emission site. A test references a code only through a string
literal it can act on: in its body or in a parametrize decorator. Comments
are not in the AST, and the docstring is prose, so neither can bind. Nor can
a literal the test cannot act on: the reason for a skip or an xfail, either
side of a comparison that holds only when the refusal is absent, a branch
behind a constant false condition, or a string that is only a statement.

Only module-level test functions that pytest runs as written are sites, so a
class method or an async test is not one. A test that reaches its code
through a module constant or a helper names no code in its own body, and
binds nothing. A literal is still not an assertion: a code used in a dead
branch whose condition is not a constant still binds.
"""
from __future__ import annotations

import ast
import pathlib
import re

# The shape of every code in SPEC 4's vocabulary: lowercase words joined by
# hyphens, at least two of them.
CODE_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")
# The lists vac/verify.py collects refusals in. Kept in step with the mutation
# sweep's REFUSAL pattern, which counts the same appends as refusal sites.
REFUSAL_LISTS = ("f", "failures")
# A test ABOUT the ledger is not evidence that an obligation is enforced.
# test_obligation_ledger.py names refusal codes in its own fixtures, so without
# this the ledger cites itself as its own evaluation site.
LEDGER_SELF_TEST = "test_obligation_ledger.py"


def _leading_literal(node) -> tuple[str, bool] | None:
    """(the literal text a string expression starts with, whether that text is
    the whole string). None if it does not start with literal text."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, True
    if (isinstance(node, ast.JoinedStr) and node.values
            and isinstance(node.values[0], ast.Constant)):
        return node.values[0].value, len(node.values) == 1
    return None


def _code_of(text: str, whole: bool) -> str | None:
    """`code: detail` gives `code`, and a bare `code` gives itself. Text cut
    short by an f-string field before any colon has no readable code."""
    if ":" in text:
        head = text.split(":", 1)[0]
    elif whole:
        head = text
    else:
        return None
    return head if CODE_RE.fullmatch(head) else None


def _printed(node: ast.Call):
    """The expression a print() call prints, seen through _printable()."""
    if not node.args:
        return None
    arg = node.args[0]
    if (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)
            and arg.func.id == "_printable" and arg.args):
        arg = arg.args[0]
    return arg


def refusal_codes(source: str) -> dict[str, list[int]]:
    """Every refusal code `source` emits, mapped to the lines emitting it.

    Emission sites, which are all the shapes vac/verify.py uses:
      f.append(...) / failures.append(...)   the collected reasons
      return ["code: ..."]                   verify_bundle's early refusals
      print("FAIL code: ...")                the archive refusal in main()
    A print of "FAIL " followed by a field is the reporter echoing reasons
    already collected, and is not a site. An append whose code cannot be read
    raises: the mutation sweep counts it as a refusal site, so dropping it here
    would leave the ledger blind to a refusal the sweep scores.
    """
    found: dict[str, list[int]] = {}

    def add(code: str, line: int) -> None:
        found.setdefault(code, []).append(line)

    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in REFUSAL_LISTS):
            lead = _leading_literal(node.args[0]) if node.args else None
            code = _code_of(*lead) if lead else None
            if code is None:
                raise ValueError(
                    f"line {node.lineno}: {node.func.value.id}.append() emits "
                    "a refusal whose code cannot be read from its literal")
            add(code, node.lineno)
        elif isinstance(node, ast.Return) and isinstance(node.value, ast.List):
            for elt in node.value.elts:
                lead = _leading_literal(elt)
                code = _code_of(*lead) if lead else None
                if code is not None:
                    add(code, elt.lineno)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "print"):
            lead = _leading_literal(_printed(node))
            if lead and lead[0].startswith("FAIL "):
                code = _code_of(lead[0][len("FAIL "):], lead[1])
                if code is not None:
                    add(code, node.lineno)
    return {k: sorted(v) for k, v in sorted(found.items())}


# pytest calls whose strings say why a test does not check anything.
NOT_A_CHECK = {"skip", "skipif", "xfail", "importorskip"}
# Comparisons that can only hold when what they name is absent.
ABSENCE_OPS = (ast.NotIn, ast.NotEq, ast.IsNot)


def _call_name(node: ast.Call) -> str | None:
    f = node.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)


def _literals(nodes) -> list[str]:
    """The string literals under `nodes` that a test can act on."""
    out = []
    todo = list(nodes)
    while todo:
        n = todo.pop()
        if isinstance(n, ast.Call) and _call_name(n) in NOT_A_CHECK:
            continue
        if (isinstance(n, ast.Expr)
                and isinstance(n.value, (ast.Constant, ast.JoinedStr))):
            continue
        if (isinstance(n, ast.Compare)
                and all(isinstance(op, ABSENCE_OPS) for op in n.ops)):
            continue
        if isinstance(n, ast.If) and isinstance(n.test, ast.Constant):
            todo.extend(n.body if n.test.value else n.orelse)
            continue
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
        todo.extend(ast.iter_child_nodes(n))
    return out


def literals_by_test(tests_dir: pathlib.Path) -> dict[str, list[str]]:
    """`tests/<file>::<test>` -> the string literals that test can act on, in
    its body and its parametrize decorators, for every module-level test
    function. The docstring is left out, and so is every other decorator:
    a skip or xfail mark only says why the test does not run or check."""
    idx: dict[str, list[str]] = {}
    for p in sorted(tests_dir.glob("test_*.py")):
        if p.name == LEDGER_SELF_TEST:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for fn in tree.body:
            if not (isinstance(fn, ast.FunctionDef)
                    and fn.name.startswith("test_")):
                continue
            body = fn.body
            if ast.get_docstring(fn, clean=False) is not None:
                body = body[1:]
            params = [d for d in fn.decorator_list
                      if isinstance(d, ast.Call)
                      and _call_name(d) == "parametrize"]
            idx[f"tests/{p.name}::{fn.name}"] = sorted(_literals(params + body))
    return idx


def references(literals: list[str], code: str) -> bool:
    """A literal references `code` if it opens with the code as a whole token,
    or carries `code:` as a whole token anywhere (a reason printed after a
    prefix, or one of several joined into one string)."""
    opens = re.compile(rf"{re.escape(code)}(?![a-z0-9-])")
    inside = re.compile(rf"(?<![a-z0-9-]){re.escape(code)}:")
    return any(opens.match(s) or inside.search(s) for s in literals)
