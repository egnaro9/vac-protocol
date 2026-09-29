"""The refusal-coverage job must not skip the issuers it checks out.

`.github/workflows/ci.yml` clones three issuer repositories so the mutation
sweep scores the whole suite. From 1674f4c, the commit that added those
checkouts, it set each VAC_*_CHECKOUT to `_issuers/<repo>/vac`, the BUNDLE
directory, while every consumer appends the bundle sub-path itself (they
already did at 1674f4c, so the values were wrong from the start). So each
variable resolved to `_issuers/<repo>/vac/vac`, which exists in none of the
three repositories, every skipif fired, and by c441011 seven tests skipped
inside the one job that had checked the repositories out.

Nothing went red, because skipped is not failed. The sweep prints a ratio and
no pytest tally, so the job reported the same score it would have reported
with the variables unset. CI stayed green across a real regression:
test_real_modeldrift_bundle_summary_is_enforced named a summary scope that
model-drift's v0.2 re-emission had removed, and it was repaired by hand at
2679953 rather than by the job that was supposed to run it.

Two layers, because either alone is escapable:

  * STATIC, here. The committed workflow must point each variable at the
    repository root the checkout step created. This is what goes red if the
    `/vac` is put back.
  * RUNTIME, in tools/mutation_sweep.py. A variable that is SET but resolves
    to no bundle aborts the sweep, so a future misconfiguration this file
    cannot anticipate stops the run instead of shrinking the suite under it.
    The gate's own liveness is proven below.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import shutil
import sys

import pytest

from vac.registry import ISSUERS

REPO = pathlib.Path(__file__).resolve().parents[1]
CI = REPO / ".github/workflows/ci.yml"
SWEEP = REPO / "tools" / "mutation_sweep.py"

CHECKOUT_ENVS = {cfg["checkout_env"]: cfg for cfg in ISSUERS}

# `with: {repository: owner/name, path: p}` on one line, the form the workflow
# uses. A rewrite into block style stops matching, and the arity assertions
# below turn that into a loud failure rather than a silent zero. It is the same
# discipline tools/mutation_sweep.py applies to its EXCLUDE keys.
_CHECKOUT_STEP = re.compile(
    r"repository:\s*(?P<repo>[^,}\s]+)[^}\n]*?path:\s*(?P<path>[^,}\s]+)")
_ENV_LINE = re.compile(
    r"^\s*(?P<var>VAC_[A-Z0-9]+_CHECKOUT):\s*(?P<val>\S+)\s*$", re.MULTILINE)


@pytest.fixture(scope="module")
def ci_text() -> str:
    assert CI.is_file(), f"{CI} is missing"
    return CI.read_text(encoding="utf-8")


def _checkout_paths(text: str) -> dict[str, str]:
    """{owner/name: workspace-relative path} for every issuer checkout step."""
    return {m.group("repo"): m.group("path")
            for m in _CHECKOUT_STEP.finditer(text)}


def _configured(text: str) -> dict[str, str]:
    """{VAC_*_CHECKOUT: value} as the workflow sets them."""
    return {m.group("var"): m.group("val") for m in _ENV_LINE.finditer(text)}


def test_the_workflow_configures_the_issuers_it_checks_out(ci_text):
    """Liveness for the two tests below: if the parse finds nothing, they
    would both pass over an empty set and evidence nothing."""
    paths = _checkout_paths(ci_text)
    configured = _configured(ci_text)
    assert paths, "no issuer checkout step parsed out of ci.yml"
    assert configured, "no VAC_*_CHECKOUT parsed out of ci.yml"
    assert set(configured) <= set(CHECKOUT_ENVS), (
        "ci.yml sets a checkout variable no issuer in vac/registry.py knows: "
        f"{sorted(set(configured) - set(CHECKOUT_ENVS))}")
    for var in configured:
        repo = CHECKOUT_ENVS[var]["repo"].rstrip("/")
        slug = "/".join(repo.split("/")[-2:])
        assert slug in paths, (
            f"{var} is set but {slug} is never checked out, so the variable "
            f"points at nothing and its tests skip")


def test_each_checkout_variable_names_the_repository_root_not_the_bundle(
        ci_text):
    """The defect itself, and the assertion that goes red if it returns.

    Every consumer resolves `<VAC_*_CHECKOUT>/<bundles>`: vac/registry.py
    scan_issuer, tests/test_registry.py and the real-bundle tests in
    tests/test_verify.py. The only correct value is therefore the checkout
    step's own `path`, with no bundle sub-path on the end.
    """
    paths = _checkout_paths(ci_text)
    for var, value in _configured(ci_text).items():
        cfg = CHECKOUT_ENVS[var]
        slug = "/".join(cfg["repo"].rstrip("/").split("/")[-2:])
        want = paths.get(slug)
        assert want is not None, (
            f"{var} is set to {value!r} but no step checks {slug} out, so it "
            f"points at nothing and its tests skip")
        assert value == want, (
            f"{var} is {value!r} but {slug} is checked out at {want!r}. "
            f"Consumers append {cfg['bundles']!r} themselves, so this "
            f"resolves to {value}/{cfg['bundles']}, the tests gated on it "
            f"skip, and the sweep scores a smaller suite at the same number.")


# Both sentences were withdrawn in the paper's Section 7.7 before v1 went out,
# and the job comment outlived them. "four mutants stop being caught" was never
# measured: the checkouts change which TESTS run, and the sweep's score at
# 92e4548 was identical with the variables set and unset. "CI measures what a
# developer does" is false while VAC_CERTLAB_CHECKOUT and VAC_FLEET_CHECKOUT go
# unset, which leaves eight issuer-gated tests and the four fleet-granularity
# tests out of reach in this job.
WITHDRAWN = ("four mutants stop being caught",
             "so CI measures what a developer does")


@pytest.mark.parametrize("claim", WITHDRAWN)
def test_the_job_comment_does_not_repeat_a_withdrawn_claim(ci_text, claim):
    assert claim not in ci_text, (
        f"ci.yml still asserts {claim!r}, which the paper withdrew. A comment "
        f"is the only documentation this job has; a withdrawn claim left in "
        f"it is a claim still being made.")


# --------------------------------------------------------------------------
# The runtime gate. Driven in-process against a synthetic issuer tree: nothing
# below spawns a sweep, runs pytest, mutates vac/verify.py or touches the sweep
# lock, so this file is safe inside a sweep's own detector.

def _load_sweep():
    spec = importlib.util.spec_from_file_location("_sweep_checkout_gate",
                                                  SWEEP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def issuer_tree(tmp_path, monkeypatch):
    """A sweep module rooted at a tree holding one bundle per issuer, laid out
    the way actions/checkout lays them out: `_issuers/<name>/<bundles>`."""
    mod = _load_sweep()
    monkeypatch.setattr(mod, "REPO", tmp_path)
    for cfg in ISSUERS:
        name = cfg["repo"].rstrip("/").rsplit("/", 1)[-1]
        # A glob bundle ("certifications/*") gets one concrete member.
        rel = cfg["bundles"].replace("*", "one")
        d = tmp_path / "_issuers" / name / rel
        d.mkdir(parents=True)
        (d / "vac.json").write_text(json.dumps({"vac_version": "0.2"}) + "\n")
    return mod


def _env(suffix: str = "") -> dict[str, str]:
    return {cfg["checkout_env"]:
            f"_issuers/{cfg['repo'].rstrip('/').rsplit('/', 1)[-1]}{suffix}"
            for cfg in ISSUERS}


def test_the_gate_passes_a_checkout_that_actually_resolves(issuer_tree):
    """The control. Without it, a gate that named every issuer unconditionally
    would pass the test below and fail every real run."""
    assert issuer_tree.checkout_failures(_env()) == []


def test_the_gate_names_every_issuer_whose_path_is_doubled(issuer_tree):
    """The exact shape of the defect: each variable pointed one level too
    deep, at the bundle rather than at the repository."""
    bad = issuer_tree.checkout_failures(_env("/vac"))
    named = {cfg["checkout_env"] for cfg in ISSUERS
             if cfg["bundles"] == "vac"}
    assert named, "no single-directory issuer to double"
    for var in named:
        assert any(line.startswith(var + "=") for line in bad), (
            f"{var} was doubled and the gate did not name it: {bad}")


def test_an_unset_variable_is_not_a_failure(issuer_tree):
    """An absent checkout is an honest skip on a developer's machine. Only a
    variable that is SET and resolves to nothing is a lie."""
    assert issuer_tree.checkout_failures({}) == []


def test_a_variable_pointing_at_an_emptied_checkout_is_a_failure(issuer_tree):
    """Not just the doubling: any configured checkout whose bundle manifest is
    missing would skip, and the gate is keyed on the same predicate the skipif
    reads rather than on the shape of the path."""
    cfg = ISSUERS[0]
    name = cfg["repo"].rstrip("/").rsplit("/", 1)[-1]
    shutil.rmtree(issuer_tree.REPO / "_issuers" / name)
    bad = issuer_tree.checkout_failures(_env())
    assert [line for line in bad
            if line.startswith(cfg["checkout_env"] + "=")], bad


def test_a_doubled_path_aborts_the_sweep_before_it_measures_anything(
        issuer_tree, monkeypatch, capsys):
    """The gate has to stop the run, not just be able to answer. main() must
    abort with rc 2 without reading vac/verify.py, running a detector or
    entering the mutation transaction."""
    def _no_detector(detector="all"):
        raise AssertionError("the sweep ran a detector over a skipped suite")

    def _no_transaction(*a, **k):
        raise AssertionError("the sweep reached its mutation transaction")

    monkeypatch.setattr(issuer_tree, "observe", _no_detector)
    monkeypatch.setattr(issuer_tree, "_sweep_transaction", _no_transaction)
    monkeypatch.setattr(issuer_tree, "SRC", issuer_tree.REPO / "absent.py")
    for var, value in _env("/vac").items():
        monkeypatch.setenv(var, value)
    monkeypatch.setattr(sys, "argv", ["mutation_sweep.py", "--floor", "0.99"])

    rc = issuer_tree.main()
    err = capsys.readouterr().err
    assert rc == 2
    assert "a configured issuer checkout does not resolve" in err
    assert "VAC_MODELDRIFT_CHECKOUT=_issuers/model-drift/vac" in err


def test_a_resolving_path_lets_the_sweep_reach_its_population_check(
        issuer_tree, monkeypatch, capsys):
    """Liveness for the abort above: with the same tree and the corrected
    values, main() gets past the checkout gate and fails later, on the source
    file this fixture does not provide.

    The evidence is the exception, because that is where this run ends. Its
    filename must be the absent source: reading it is the first thing main()
    does after the gate, so a gate that raised instead of returning, or any
    FileNotFoundError from earlier, names some other file or none.

    The streams are searched too, but only once a marker has proven each
    capture non-empty. This test used to assert the gate's text was absent
    from stderr alone, and on every real run that capture is empty, so the
    assertion could not tell a silent gate from a capture that saw nothing.
    The marker is written through the sweep module's own `sys`, the object
    its print calls resolve at call time. The abort test above proves the
    gate's text does land in a capture set up this way.
    """
    for var, value in _env().items():
        monkeypatch.setenv(var, value)
    monkeypatch.setattr(issuer_tree, "SRC", issuer_tree.REPO / "absent.py")
    monkeypatch.setattr(sys, "argv", ["mutation_sweep.py", "--floor", "0.99"])
    marker = "capture-is-live"
    print(marker, file=issuer_tree.sys.stdout)
    print(marker, file=issuer_tree.sys.stderr)

    with pytest.raises(FileNotFoundError) as caught:
        issuer_tree.main()
    said = str(caught.value)
    assert caught.value.filename == str(issuer_tree.SRC), (
        f"main() raised before reaching the source read: {said!r}")
    assert "does not resolve" not in said, said

    out, err = capsys.readouterr()
    for stream, text in (("stdout", out), ("stderr", err)):
        assert marker in text, (
            f"the {stream} capture never saw the marker, so searching it "
            f"proves nothing: {text!r}")
        assert "does not resolve" not in text, (
            f"the checkout gate spoke on {stream} for a resolving checkout: "
            f"{text!r}")
