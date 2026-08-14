# vac-protocol

**VAC — Verifiable Agent Claims.** A tiny protocol for capability claims
about AI systems that a stranger can check without trusting the person
making them. A claim ships as a **Capability Evidence Bundle**: one
directory with a manifest (`vac.json`), the evidence artifacts pinned by
sha256, declared numbers that a verifier recomputes from those artifacts
offline, and the exact commands to re-earn every verdict from the
issuer's own deterministic grader. [SPEC.md](SPEC.md) is the format.

The framing is deliberate: **here is the contract, the evidence, the
verifier, and the replay instructions — do not trust us, run it.** A
bundle that asks for faith at any step is invalid by construction: no
pinned versions, no hashed artifacts, no deterministic grading, no
declared scope, or no declared *limitations* — each alone is grounds for
rejection. Non-claims are mandatory; a capability statement that will not
say what it does not cover is an advertisement, and VAC does not carry
advertisements.

VAC is the trust layer over two live issuers, whose formats are the
protocol's two evidence profiles verbatim:

- [agent-certlab](https://github.com/egnaro9/agent-certlab) — capability
  contracts for coding agents; verdicts with full diffs in `bundle.json`,
  independently regraded by `python -m certlab.regrade`.
- [reference-fleet](https://github.com/egnaro9/reference-fleet) —
  certified defect models; board aggregates stamped with `fleet_commit`,
  paired per-request evidence in `raw_results.jsonl`, reproduced
  byte-identically by `python audit/run_audit.py` at the stamped commit.

## Quickstart

```
pip install -e ".[test]" && python -m pytest tests/ -q
python -m vac.verify fixtures/valid                # exit 0, structural PASS
python -m vac.verify fixtures/tamper-raw-aggregate # named reasons, exit 1
```

The verifier is structural: zero network, zero issuer code, stdlib only.
It proves the bundle is *internally honest* — schema, hashes, closure
(no unlisted files), stated limitations, stamp agreement, and every
declared number recomputed from the committed artifacts (certlab verdict
counts from `bundle.json`; fleet aggregates from `raw_results.jsonl`).
It does **not** prove the issuer's grader agrees — that is **semantic
replay**, the bundle's `replay` block says exactly how to run it, and the
tool prints that distinction on every invocation so a green check is
never mistaken for a replay.

`fixtures/` is the verifier's own evidence: one valid synthetic bundle
and six tampered variants — missing artifact, wrong sha256, inflated
verdict count, empty limitations, missing issuer commit, and a cooked
board row with a *fixed* hash that only recomputation from raw catches.
CI requires the valid bundle to pass and **every** tamper to be refused
(the invalidation-liveness job): a gate must prove it can block.

## Try to falsify it

[REPLAY_REQUEST.md](REPLAY_REQUEST.md) is the ten-minute path: verify a real
capability contract structurally, then re-earn its verdicts with the
issuer's own regrader — no API keys, no accounts. Confirmations,
discrepancies, and blocked replays all get filed and published.

## Registry and replay

[registry.json](registry.json) is the registry: a file, reviewed like
code. `python -m vac.registry` regenerates it mechanically by scanning the
configured local issuer checkouts at their **committed HEAD trees** —
hashing committed blobs, never the working tree — and running the
structural verifier over every configured bundle. Each accepted entry pins
name, issuer, `issuer_commit`, every artifact's sha256, and the raw URL on
`main` those bytes must be servable from. A configured bundle that is not
yet admissible (emitter not landed, or verification naming failures) is
recorded **pending with its exact reason** — never fabricated, never
silently dropped. Acceptance stays two-gated per SPEC.md §5, and each gate
is enforced by CI, not memory:

- **[pages.yml](.github/workflows/pages.yml)** — the registry page
  ([index.html](index.html)) may deploy only after the fixtures prove the
  verifier can pass *and block*, and `python -m vac.registry
  --check-fetched` rebuilds the registry from the artifacts **fetched at
  their public URLs** byte-identically. The page can say "pending"; it
  cannot overstate.
- **[replay.yml](.github/workflows/replay.yml)** — the independent replay
  (weekly + on demand): per accepted entry, download every artifact by its
  registry URL, refuse any byte that does not hash to its pin, re-run
  `python -m vac.verify`, then execute the bundle's replay block verbatim
  — clone the issuer at the pinned commit and re-earn the verdicts with
  its own regrader (certlab: `python -m certlab.regrade`; fleet:
  `python audit/run_audit.py` + byte-compare). Until every issuer commit
  and emitted bundle is pushed public, this workflow **fails with the
  precise reason** — that is its job.

[INVALIDATION.md](INVALIDATION.md) is the public walkthrough of the gate
refusing: one flipped hex digit, the verifier's real captured rejection,
restore, pass.

Explicitly refused in v0.1 (SPEC.md §7): signatures, URIs/identity
schemes, accounts, hosted registry, Docker images. The trust object is
replayability; everything else can layer on later without changing the
format.

MIT. Part of a program on verifiable evaluation:
[evalmut](https://github.com/egnaro9/evalmut) →
[reference-fleet](https://github.com/egnaro9/reference-fleet) →
[agent-certlab](https://github.com/egnaro9/agent-certlab) → this
protocol.
