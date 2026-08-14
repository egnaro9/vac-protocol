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

## Registry and replay — the seam

This commit ships the spec, the verifier, and the fixtures. The registry
and CI replays land in a **follow-up commit by another builder**, against
two seams left deliberately open:

- **`registry.json`** (repo root): an array of entries
  `{"bundle": <path or repo+commit>, "status": "accepted" | "confirmed" |
  "narrowed" | "superseded" | "invalidated", "challenges": [...]}` —
  semantics in SPEC.md §5–6. Acceptance is two-gated: structural
  verification (this repo's tool), then semantic replay (the issuer's
  tool, run by registry CI). Nothing in the verifier or spec needs to
  change to add it.
- **A `replay` CI job**: for each registered bundle, clone the issuer at
  `replay.issuer_commit`, run `replay.commands`, compare against
  `replay.expected`. The bundle format already carries everything such a
  job needs; the existing `invalidation-liveness` job in
  [ci.yml](.github/workflows/ci.yml) is the pattern to extend.

Explicitly refused in v0.1 (SPEC.md §7): signatures, URIs/identity
schemes, accounts, hosted registry, Docker images. The trust object is
replayability; everything else can layer on later without changing the
format.

MIT. Part of a program on verifiable evaluation:
[evalmut](https://github.com/egnaro9/evalmut) →
[reference-fleet](https://github.com/egnaro9/reference-fleet) →
[agent-certlab](https://github.com/egnaro9/agent-certlab) → this
protocol.
