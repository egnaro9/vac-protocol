"""The depth at which JSON is refused is the verifier's, not the host's.

json.loads recurses once per nesting level, so it gives out wherever the
interpreter's stack does: 994 levels on CPython 3.9.6, 9997 on 3.12.12, 74656
on 3.14.3 and 116191 on 3.14.6. The verifier caught the RecursionError and
named a reason, which stopped the crash but not the dependence. The same
bundle bytes, fixtures/valid plus one extra top-level key (SPEC 2 permits
unknown keys) holding 20000 nested arrays, FAILED invalid-json on 3.12 and
PASSED on 3.14.

So the depth is decided first, on the text, without recursing: more than
MAX_JSON_DEPTH levels is invalid-json on every host. Every document at or
below the limit verifies exactly as it did before. Each boundary is pinned at
both sides, and the deep cases are built as text here rather than committed,
because json.dumps would recurse just as deeply to write them.
"""
from __future__ import annotations

import ast
import codecs
import json
import pathlib
import shutil

import pytest

from vac.verify import (MAX_JSON_DEPTH, _nesting_exceeds, _sha256, main,
                        verify_bundle)

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
ART = "evidence/bundle.json"
RAW = "evidence/raw_results.jsonl"
BOM_REASON = ("Unexpected UTF-8 BOM (decode using utf-8-sig): "
              "line 1 column 1 (char 0)")


def _deep_key(text: str, k: int) -> str:
    """`text` (a JSON object) with one extra first member holding k nested
    arrays, so the document is exactly k + 1 levels deep."""
    assert text.startswith("{")
    return '{"deep": ' + "[" * k + "]" * k + ", " + text[1:]


def _bundle(tmp_path: pathlib.Path, fixture: str = "valid") -> pathlib.Path:
    b = tmp_path / "b"
    shutil.copytree(FIX / fixture, b)
    return b


def _repin(b: pathlib.Path, rel: str) -> None:
    p = b / "vac.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    for e in man["evidence"]:
        if e["path"] == rel:
            e["sha256"] = _sha256(b / rel)
    p.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")


def _deep_manifest(tmp_path, depth, fixture="valid"):
    b = _bundle(tmp_path, fixture)
    p = b / "vac.json"
    p.write_text(_deep_key(p.read_text(encoding="utf-8"), depth - 1),
                 encoding="utf-8")
    return b


def _deep_artifact(tmp_path, depth):
    b = _bundle(tmp_path)
    p = b / ART
    p.write_text(_deep_key(p.read_text(encoding="utf-8"), depth - 1),
                 encoding="utf-8")
    _repin(b, ART)
    return b


def _deep_raw_line(tmp_path, depth, line=2):
    b = _bundle(tmp_path)
    p = b / RAW
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[line - 1] = _deep_key(lines[line - 1], depth - 1)
    p.write_text("".join(lines), encoding="utf-8")
    _repin(b, RAW)
    return b


# ------------------------------------------------------------ the counting


def test_the_limit_is_256_levels():
    assert MAX_JSON_DEPTH == 256


@pytest.mark.parametrize("text,deepest", [
    ("0", 0),
    ('"a [ string"', 0),
    ("[]", 1),
    ("{}", 1),
    ("[[]]", 2),
    ('{"a": [1, {"b": []}]}', 4),
    ('["[[[[", "]]"]', 1),               # brackets inside strings
    ('["\\"[[[["]', 1),                  # an escaped quote does not close
    ('["\\\\", [[]]]', 3),               # an escaped backslash does not either
    ('[]]]][[', 2),                      # a closer with nothing open is ignored
    ('["unterminated [[[[[', 1),         # the rest of the text is the string
    ('["trailing escape \\', 1),
])
def test_nesting_is_counted_from_the_outermost_container(text, deepest):
    """Level 1 is the outermost array or object. Counted lexically, so text
    the parser would reject still gets a depth, and never by recursing."""
    assert not _nesting_exceeds(text, deepest)
    if deepest:
        assert _nesting_exceeds(text, deepest - 1)


def test_the_count_itself_does_not_recurse():
    """A limit far past any host's stack, so a recursive count would die."""
    text = "[" * 100_000 + "]" * 100_000
    assert not _nesting_exceeds(text, 100_000)
    assert _nesting_exceeds(text, 99_999)


# ------------------------------------------------------ the manifest, 0.1 and 0.2


@pytest.mark.parametrize("fixture", ["valid", "v02-twin-arms"])
def test_a_manifest_at_the_limit_verifies_as_before(tmp_path, fixture):
    assert verify_bundle(_deep_manifest(tmp_path, MAX_JSON_DEPTH,
                                        fixture)) == []


@pytest.mark.parametrize("fixture", ["valid", "v02-twin-arms"])
def test_a_manifest_one_level_past_the_limit_is_refused(tmp_path, fixture):
    assert verify_bundle(_deep_manifest(tmp_path, MAX_JSON_DEPTH + 1,
                                        fixture)) == [
        "invalid-json: vac.json: nested deeper than 256 levels"]


@pytest.mark.parametrize("fixture", ["valid", "v02-twin-arms"])
def test_the_20000_deep_manifest_is_refused_on_every_host(tmp_path, fixture):
    """The bundle that failed on 3.12 and passed on 3.14."""
    assert verify_bundle(_deep_manifest(tmp_path, 20001, fixture)) == [
        "invalid-json: vac.json: nested deeper than 256 levels"]


def test_the_cli_output_for_a_deep_manifest_does_not_depend_on_the_host(
        tmp_path, capsys):
    """_report parses vac.json again to echo the replay block. Through the same
    loader, so it cannot echo on one host what it calls unreadable on another."""
    b = _deep_manifest(tmp_path, 20001)
    assert main([str(b)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "FAIL invalid-json: vac.json: nested deeper than 256 levels"
    assert any(line.startswith("    (replay block unreadable") for line in out)
    assert not any(line.startswith("    $ ") for line in out)


# ------------------------------------------------------------ evidence artifacts


def test_an_artifact_at_the_limit_verifies_as_before(tmp_path):
    assert verify_bundle(_deep_artifact(tmp_path, MAX_JSON_DEPTH)) == []


def test_an_artifact_one_level_past_the_limit_is_refused(tmp_path):
    assert verify_bundle(_deep_artifact(tmp_path, MAX_JSON_DEPTH + 1)) == [
        f"invalid-json: {ART}: nested deeper than 256 levels"]


def test_the_20000_deep_artifact_is_refused_on_every_host(tmp_path):
    assert verify_bundle(_deep_artifact(tmp_path, 20001)) == [
        f"invalid-json: {ART}: nested deeper than 256 levels"]


def test_a_json_lines_line_at_the_limit_verifies_as_before(tmp_path):
    assert verify_bundle(_deep_raw_line(tmp_path, MAX_JSON_DEPTH)) == []


def test_a_json_lines_line_one_level_past_the_limit_is_refused(tmp_path):
    assert verify_bundle(_deep_raw_line(tmp_path, MAX_JSON_DEPTH + 1)) == [
        f"invalid-json: {RAW}: line 2 nested deeper than 256 levels"]


def test_the_20000_deep_json_lines_line_is_refused_on_every_host(tmp_path):
    assert verify_bundle(_deep_raw_line(tmp_path, 20001)) == [
        f"invalid-json: {RAW}: line 2 nested deeper than 256 levels"]


def test_every_line_is_measured_before_any_line_is_parsed(tmp_path):
    """A broken first line must not hide a too-deep later one: the parser
    stops at the first error, so the depth has to be decided before it runs."""
    b = _deep_raw_line(tmp_path, 20001, line=3)
    p = b / RAW
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[0] = "{not json\n"
    p.write_text("".join(lines), encoding="utf-8")
    _repin(b, RAW)
    assert verify_bundle(b) == [
        f"invalid-json: {RAW}: line 3 nested deeper than 256 levels"]


def test_the_line_a_refusal_names_is_the_line_in_the_file(tmp_path):
    """Blank lines hold no row, but they are still lines, so the number is the
    one an editor shows. Counting only the rows named line 2 here."""
    b = _deep_raw_line(tmp_path, MAX_JSON_DEPTH + 1, line=2)
    p = b / RAW
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    lines.insert(1, "\n\n")
    p.write_text("".join(lines), encoding="utf-8")
    _repin(b, RAW)
    assert verify_bundle(b) == [
        f"invalid-json: {RAW}: line 4 nested deeper than 256 levels"]


def test_a_line_break_inside_a_string_is_not_nesting(tmp_path):
    """A JSON Lines line ends at a line feed, so that is where depth is
    measured. The rows are still parsed as str.splitlines() cuts them, which
    also cuts at U+2028, and here that cut falls inside a string: the
    brackets after it are string content on a row that is one level deep. The
    parser refuses the string the cut leaves open, first and on every host,
    so the reason stays the parser's. Measured cut by cut, the brackets read
    as nesting on a line 3 the file does not have."""
    b = _bundle(tmp_path)
    p = b / RAW
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    cut = '{"note": "a'
    lines[1] = (cut + " " + "[" * (MAX_JSON_DEPTH + 1) + '", '
                + lines[1][1:])
    p.write_text("".join(lines), encoding="utf-8")
    _repin(b, RAW)
    with pytest.raises(json.JSONDecodeError) as e:
        json.loads(cut)
    assert verify_bundle(b) == [f"artifact-unparsable: {RAW}: {e.value}"]


# --------------------------------------------------------- what did not change


@pytest.mark.parametrize("depth", [3, 20001])
def test_a_manifest_with_a_byte_order_mark_is_refused_as_before(tmp_path,
                                                                 depth):
    """json.loads refuses a leading BOM at offset 0, before it reads any
    nesting, and utf-8 decoding keeps the BOM. The limit leaves that alone: a
    BOM is refused by name at any depth, and a scan that stripped it would be
    the first step to accepting what the parser refuses."""
    b = _bundle(tmp_path)
    p = b / "vac.json"
    text = p.read_text(encoding="utf-8")
    if depth > 3:
        text = _deep_key(text, depth - 1)
    p.write_bytes(codecs.BOM_UTF8 + text.encode("utf-8"))
    assert verify_bundle(b) == [f"invalid-json: vac.json: {BOM_REASON}"]


@pytest.mark.parametrize("depth", [3, 20001])
def test_an_artifact_with_a_byte_order_mark_is_refused_as_before(tmp_path,
                                                                 depth):
    b = _bundle(tmp_path)
    p = b / ART
    text = p.read_text(encoding="utf-8")
    if depth > 3:
        text = _deep_key(text, depth - 1)
    p.write_bytes(codecs.BOM_UTF8 + text.encode("utf-8"))
    _repin(b, ART)
    assert verify_bundle(b) == [f"artifact-unparsable: {ART}: {BOM_REASON}"]


@pytest.mark.parametrize("depth", [None, MAX_JSON_DEPTH + 1, 20001])
def test_a_json_lines_artifact_with_a_byte_order_mark_is_refused_as_before(
        tmp_path, depth):
    """The mark opens the whole text, so the text is refused at its first
    character whatever a later line holds. Measured line by line, only the
    first line was passed over, and a deep third line took the reason."""
    b = _deep_raw_line(tmp_path, depth, line=3) if depth else _bundle(tmp_path)
    p = b / RAW
    p.write_bytes(codecs.BOM_UTF8 + p.read_bytes())
    _repin(b, RAW)
    assert verify_bundle(b) == [f"artifact-unparsable: {RAW}: {BOM_REASON}"]


def test_a_json_lines_line_with_a_byte_order_mark_is_refused_as_before(
        tmp_path):
    """The mark opens line 3, not the text, so only that line goes unmeasured
    and the parser names it at its first character, as it did before."""
    b = _deep_raw_line(tmp_path, 20001, line=3)
    p = b / RAW
    rows = p.read_text(encoding="utf-8").splitlines(keepends=True)
    rows[2] = "\ufeff" + rows[2]
    p.write_text("".join(rows), encoding="utf-8")
    _repin(b, RAW)
    assert verify_bundle(b) == [f"artifact-unparsable: {RAW}: {BOM_REASON}"]


def test_malformed_json_within_the_limit_keeps_its_reason(tmp_path):
    b = _bundle(tmp_path)
    (b / ART).write_text('{"verdicts": [' + "[" * 200, encoding="utf-8")
    _repin(b, ART)
    out = verify_bundle(b)
    assert len(out) == 1 and out[0].startswith(f"artifact-unparsable: {ART}: ")


# What verify.py may take from the json module outside the loader: writing
# JSON, and the error the loader's callers catch. Anything else could decode.
JSON_OUTSIDE_THE_LOADER = {"dumps", "JSONDecodeError"}


def _parses_json(n) -> bool:
    if isinstance(n, ast.Attribute):
        if isinstance(n.value, ast.Name) and n.value.id == "json":
            return n.attr not in JSON_OUTSIDE_THE_LOADER
        return n.attr in ("raw_decode", "scan_once")
    if isinstance(n, ast.ImportFrom):
        return (n.module or "").split(".")[0] == "json"
    if isinstance(n, ast.Import):
        return any(a.name.split(".")[0] == "json"
                   and (a.name != "json" or a.asname is not None)
                   for a in n.names)
    return False


def test_json_is_parsed_in_one_place():
    """Structural, so a new parse added anywhere else in the verifier is red on
    every host, not only on one whose stack happens to be small. Every route to
    a decoder counts, not only json.loads: json.JSONDecoder, raw_decode, a name
    imported from json, or json under another name. On 3.12 such a bypass
    raises a RecursionError that reads just like the loader's refusal, so the
    behavioural tests there stay green."""
    tree = ast.parse((ROOT / "vac" / "verify.py").read_text(encoding="utf-8"))
    loader = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "_json_loads")
    inside = {id(n) for n in ast.walk(loader)}
    stray = [n.lineno for n in ast.walk(tree)
             if _parses_json(n) and id(n) not in inside]
    assert stray == [], f"json parsed outside _json_loads at lines {stray}"


@pytest.mark.parametrize("line", [
    "x = json.loads(t)",
    "x = json.load(fh)",
    "x = json.JSONDecoder().decode(t)",
    "x = json.decoder.JSONDecoder().raw_decode(t)",
    "x = decoder.raw_decode(t)",
    "from json import loads",
    "import json as j",
    "import json.decoder",
])
def test_every_route_to_a_decoder_is_seen(line):
    """Liveness for the structural test above."""
    assert any(_parses_json(n) for n in ast.walk(ast.parse(line)))


@pytest.mark.parametrize("line", [
    "import json",
    "s = json.dumps(x)",
    "E = json.JSONDecodeError",
    "b = raw.decode('utf-8')",
])
def test_what_verify_py_may_use_is_not_a_decoder(line):
    assert not any(_parses_json(n) for n in ast.walk(ast.parse(line)))
