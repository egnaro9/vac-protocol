# vac-protocol

**VAC: Verifiable Agent Claims.** A tiny protocol for capability claims
about AI systems that a stranger can check without trusting the person
making them. A claim ships as a **Capability Evidence Bundle**: one
directory with a manifest (`vac.json`), the evidence artifacts pinned by
sha256, declared numbers that a verifier recomputes from those artifacts
offline, and the exact commands to re-earn every verdict from the
issuer's own deterministic grader. [SPEC.md](SPEC.md) is the format;
[REPLAY_REQUEST.md](REPLAY_REQUEST.md) is the standing invitation to
falsify a live claim in ten minutes.

The framing is deliberate: **here is the contract, the evidence, the
verifier, and the replay instructions. Do not trust us, run it.** A
bundle that asks for faith at any step is invalid by construction: no
pinned versions, no hashed artifacts, no deterministic grading, no
declared scope, or no declared *limitations*: each alone is grounds for
rejection. Non-claims are mandatory; a capability statement that will not
say what it does not cover is an advertisement, and VAC does not carry
advertisements.

VAC is the trust layer over five live issuers, whose formats are the
protocol's five evidence profiles verbatim:

- [agent-certlab](https://github.com/egnaro9/agent-certlab). Capability
  contracts for coding agents; verdicts with full diffs in `bundle.json`,
  independently regraded by `python -m certlab.regrade`.
- [reference-fleet](https://github.com/egnaro9/reference-fleet) -
  certified defect models; board aggregates stamped with `fleet_commit`,
  paired per-request evidence in `raw_results.jsonl`, reproduced
  byte-identically by `python audit/run_audit.py` at the stamped commit.
- [evalmut](https://github.com/egnaro9/evalmut). Eval-suite mutation
  testing over a mined operator battery; score, tally, and hole classes
  with the per-mutation rows they must recompute from
  (`evalmut run <suite> --json --all`), reproduced byte-identically by
  re-running `evalmut run` at the pinned commit.
- [crashkit](https://github.com/egnaro9/crashkit). The AI crash-test
  platform; severity-weighted battery metrics recomputed from per-case
  rows with explicit passed/truncated booleans (`eval_run.json`),
  reproduced byte-identically by `python emit_vac.py` at the stamped
  commit.
- [model-drift](https://github.com/egnaro9/model-drift). The public LLM
  drift board; standings, flip/probe-alarm analysis, narrative, and the
  rendered table all recomputed from the committed per-run rows
  (`metrics.json` joined to `models.json`), reproduced byte-identically
  by `python3 emit_vac.py` at the stamped commit.

## Issuing a bundle

You do not need our artifact formats. `rows-aggregate-v1` takes rows in the shape
you already publish, and you declare how each headline number is recomputed from
them. [ISSUING.md](ISSUING.md) walks the whole path, with a worked example from a
fictional outside issuer that verifies as-is.

Every entry in the registry today was issued by one person. If you issue one, you
are the first real test of whether this spec is writable against by someone who
did not write it.

## Quickstart

```
pip install -e ".[test]" && python -m pytest tests/ -q
python -m vac.verify fixtures/valid                # exit 0, structural PASS
python -m vac.verify fixtures/tamper-raw-aggregate # named reasons, exit 1
```

The verifier is structural: zero network, zero issuer code, stdlib only.
It proves the bundle is *internally honest*: schema, hashes, closure
(no unlisted files), stated limitations, stamp agreement, and every
declared number recomputed from the committed artifacts (certlab verdict
counts from `bundle.json`; fleet aggregates from `raw_results.jsonl`;
evalmut tallies, score, and hole classes from the per-mutation rows;
crashkit metrics from the per-case rows under fixed severity weights;
modeldrift standings, flips, and the rendered table from the stored
per-run rows).
It does **not** prove the issuer's grader agrees. That is **semantic
replay**, the bundle's `replay` block says exactly how to run it, and the
tool prints that distinction on every invocation so a green check is
never mistaken for a replay.

`fixtures/` is the verifier's own evidence: one valid synthetic bundle
(one check per profile) and sixteen tampered variants. Missing
artifact, wrong sha256, inflated verdict count, empty limitations,
missing issuer commit, then a cooked-rows and a cooked-aggregate tamper
per recomputing profile (a board row, a mutation tally and a relabeled
mutation, crash-test metrics and a relabeled case, a sweetened drift
point and cooked drift standings. Every one re-hashed so only
recomputation from the rows names it), three summary-only cooks
that only SPEC.md §2.5's outrun rule catches, and a drafted-but-unfinished
bundle (every judgment field still a `TODO(...)` marker) that the draft
gate refuses wholesale.
CI requires the valid bundle to pass and **every** tamper to be refused
(the invalidation-liveness job): a gate must prove it can block.

## Drafting a bundle

`python -m vac.draft` is the scaffolder for issuers: point it at a
directory of evidence artifacts and it derives every **mechanical**
manifest field. Per-file sha256, issuer and pinned commit from the
enclosing git repo (a dirty tree is a printed warning, not a refusal:
drafting is not certifying), the replay skeleton's clone/checkout lines,
a checks skeleton naming the profiles to pick from. And emits every
**judgment** field as an explicit `TODO(...)` marker with one-line
guidance:

```
python -m vac.draft my-claim/    # mechanical fields derived, judgment fields marked
$EDITOR my-claim/vac.json        # a human authors capability, scope, limitations,
                                 #   subject, protocol semantics, checks, replay
python -m vac.verify my-claim/   # green only when every marker is gone and every
                                 #   declared number re-earns from the artifacts
```

The split is enforced, not advisory: the verifier refuses any manifest
still carrying a marker (`draft-incomplete: <path> is an unauthored
TODO`) before checking anything else, so a draft can never be passed off
as a claim. And the drafter never infers `claim.scope` or
`claim.limitations` (SPEC.md §2.7): what a claim covers and what it does
not cover are authored judgments. A tool that guessed them would
manufacture exactly the advertisement VAC refuses to carry.

## Try to falsify it

[REPLAY_REQUEST.md](REPLAY_REQUEST.md) is the ten-minute path: verify a real
capability contract structurally, then re-earn its verdicts with the
issuer's own regrader. No API keys, no accounts. Confirmations,
discrepancies, and blocked replays all get filed and published.

## Registry and replay

[registry.json](registry.json) is the registry: a file, reviewed like
code. `python -m vac.registry` regenerates it mechanically by scanning the
configured local issuer checkouts at their **committed HEAD trees** -
hashing committed blobs, never the working tree. And running the
structural verifier over every configured bundle. Each accepted entry pins
name, issuer, `issuer_commit`, every artifact's sha256, and the raw URL on
`main` those bytes must be servable from. A configured bundle that is not
yet admissible (emitter not landed, or verification naming failures) is
recorded **pending with its exact reason**: never fabricated, never
silently dropped. Acceptance stays two-gated per SPEC.md §5, and each gate
is enforced by CI, not memory:

- **[pages.yml](.github/workflows/pages.yml)**: the registry page
  ([index.html](index.html)) may deploy only after the fixtures prove the
  verifier can pass *and block*, and `python -m vac.registry
  --check-fetched` rebuilds the registry from the artifacts **fetched at
  their public URLs** byte-identically. The page can say "pending"; it
  cannot overstate.
- **[replay.yml](.github/workflows/replay.yml)**: the independent replay
  (weekly + on demand): per accepted entry, download every artifact by its
  registry URL, refuse any byte that does not hash to its pin, re-run
  `python -m vac.verify`, then execute the bundle's replay block verbatim
 : clone the issuer at the pinned commit and re-earn the verdicts with
  its own regrader (certlab: `python -m certlab.regrade`; fleet:
  `python audit/run_audit.py` + byte-compare; evalmut:
  `evalmut run <suite> --json --all` + byte-compare. The third profile,
  `evalmut-run-v1`, SPEC.md §3.3; crashkit: `python emit_vac.py` +
  byte-compare. The fourth profile, `crashkit-battery-v1`, SPEC.md
  §3.4; model-drift: `python3 emit_vac.py` + byte-compare. The fifth
  profile, `modeldrift-board-v1`, SPEC.md §3.5). Until every issuer
  commit and emitted bundle is pushed public, this workflow **fails with
  the precise reason**: that is its job.

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
