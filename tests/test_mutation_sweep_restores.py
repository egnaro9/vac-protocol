"""The sweep edits tracked source to measure it, so it is a transaction.

On 2026-08-28 a run was killed by a timeout between injecting a mutant and
restoring the line, and left `pass  # MUTANT` in vac/verify.py where the
`artifact-unparsable` refusal belongs. A plain try/finally did not save it:
SIGTERM terminates CPython without running finally. These tests pin the
lifecycle, not the intention. See issue #11.
"""
from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys
import time

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

SRC = REPO / "vac" / "verify.py"
SWEEP = REPO / "tools" / "mutation_sweep.py"
LOCK = REPO / ".mutation_sweep.lock"


def _spawn_sweep() -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    return subprocess.Popen(
        [sys.executable, str(SWEEP), "--detector", "liveness"],
        cwd=REPO, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_until_mutated(snapshot: bytes, proc: subprocess.Popen,
                        limit: float = 60.0) -> bool:
    """True once the sweep has actually injected a mutant. Waiting on the
    mutation rather than on a fixed sleep is what makes this test meaningful:
    killing before the first write would prove nothing."""
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if SRC.read_bytes() != snapshot:
            return True
        time.sleep(0.05)
    return False


@pytest.mark.skipif(not SWEEP.is_file(), reason="mutation_sweep.py not present")
def test_sigterm_mid_sweep_leaves_the_tree_byte_identical():
    """The exact failure of 2026-08-28: SIGTERM between inject and restore."""
    assert not LOCK.exists(), "a sweep lock is already held"
    snapshot = SRC.read_bytes()
    proc = _spawn_sweep()
    try:
        mutated = _wait_until_mutated(snapshot, proc)
        if not mutated:
            proc.kill(), proc.wait(timeout=30)
            pytest.skip("sweep never reached a mutation in time")  # noqa
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=60)
        # Capture BEFORE any cleanup. Restoring the file here and then
        # asserting on it would measure this test's own tidy-up, not the
        # sweep's restore, and would pass with the guard ripped out.
        after = SRC.read_bytes()
        lock_held = LOCK.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
        SRC.write_bytes(snapshot)      # belt and braces; the assert is the test
        LOCK.unlink(missing_ok=True)

    assert after == snapshot, (
        "vac/verify.py was NOT restored byte-for-byte after SIGTERM")
    assert b"MUTANT" not in after
    assert not lock_held, "the sweep died holding its lock"


@pytest.mark.skipif(not SWEEP.is_file(), reason="mutation_sweep.py not present")
def test_sigint_mid_sweep_leaves_the_tree_byte_identical():
    """Ctrl-C is the same hazard by a different signal."""
    assert not LOCK.exists(), "a sweep lock is already held"
    snapshot = SRC.read_bytes()
    proc = _spawn_sweep()
    try:
        if not _wait_until_mutated(snapshot, proc):
            proc.kill(), proc.wait(timeout=30)
            pytest.skip("sweep never reached a mutation in time")  # noqa
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=60)
        # Capture BEFORE any cleanup. Restoring the file here and then
        # asserting on it would measure this test's own tidy-up, not the
        # sweep's restore, and would pass with the guard ripped out.
        after = SRC.read_bytes()
        lock_held = LOCK.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
        SRC.write_bytes(snapshot)
        LOCK.unlink(missing_ok=True)

    assert after == snapshot, (
        "vac/verify.py was NOT restored byte-for-byte after SIGINT")
    assert b"MUTANT" not in after
    assert not lock_held, "the sweep died holding its lock"


@pytest.mark.skipif(not SWEEP.is_file(), reason="mutation_sweep.py not present")
def test_a_second_sweep_refuses_while_the_lock_is_held():
    """A concurrent reader of a mutated tree reports phantom failures, so a
    second sweep must refuse rather than interleave."""
    assert not LOCK.exists(), "a sweep lock is already held"
    LOCK.write_text("pid=0\n")
    try:
        env = {**os.environ, "PYTHONPATH": str(REPO)}
        r = subprocess.run(
            [sys.executable, str(SWEEP), "--detector", "liveness"],
            cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
        assert r.returncode == 2, f"expected refusal, got {r.returncode}"
        assert "Another sweep is mutating this tree" in r.stderr
    finally:
        LOCK.unlink(missing_ok=True)
