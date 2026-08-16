# Replay request: try to falsify this

Every claim in [registry.json](registry.json) says it can survive an
independent replay. Nobody outside this project has tested that yet. If you
have ten minutes, you can be the first. And if you break something, that
result gets published, not buried.

## The ten-minute path (no API keys, no GPU)

```
pip install "git+https://github.com/egnaro9/vac-protocol"
git clone https://github.com/egnaro9/agent-certlab && cd agent-certlab
python -m vac.verify certifications/claude-code-ledger-2026-08-14
pip install -e ".[test]" && python -m certlab.regrade
```

That is: structural verification of a real capability contract (schema,
sha256 of every artifact, closure, offline recomputation of its counts),
then a semantic replay. Every verdict re-earned from the recorded diffs by
the issuer's own regrader. Nothing in it consults an agent, an LLM, or us.

The deeper replays are in each bundle's `replay` block (`vac.json` prints
them on every verify): the reference-fleet audit re-run takes ~10 minutes
and needs Node (`npx promptfoo` is fetched by the issuer's own tooling);
re-running the *agents themselves* is not part of replay. Grading replay is
the claim, agent replay is not (each contract says this explicitly).

## The three outcomes, all useful

- **Confirmed**: you got byte-identical results / `consistent` verdicts.
  File an issue titled `replay-report: <bundle> confirmed` with your OS,
  Python version, and the tool output.
- **Mismatch**: the verifier or a regrader disagreed with the published
  claim. File `discrepancy: <bundle>` with the exact output. This is the
  most valuable outcome; see below for what happens next.
- **Cannot decide**: something blocked the replay (environment, network,
  unclear instructions). File `replay-blocked: <bundle>`. An instruction a
  stranger cannot follow is a defect in the bundle, not in the stranger.

Challenges beyond replay are welcome under the
[challenge protocol](SPEC.md#6-the-challenge-protocol): a **coverage challenge**
("your grader cannot detect failure class X") or a **scope challenge**
("your public wording claims more than the protocol establishes").

## What we publish if you find a failure

The disputed bundle is frozen, the verifier and replay are re-run publicly,
raw outputs are attached, and the contract is marked **confirmed, narrowed,
superseded, or invalidated**: in the registry, visibly. An invalidation is
a first-class result for this project, not an embarrassment: the entire
thesis is that unsupported claims must fail mechanically. See
[INVALIDATION.md](INVALIDATION.md) for what that looks like when we do it
to ourselves.

## Credit

A confirmed or falsifying replay gets named acknowledgment in this README
and the registry entry's reproduction history (or anonymity, your choice).
Authorship on any resulting write-up is reserved for substantive research
contribution beyond a replay. The same standard we hold ourselves to.

## Cost summary

| Replay | Time | Needs |
|---|---|---|
| Structural verify (any bundle) | ~1 min | Python 3.11+ |
| certlab semantic regrade (all 6 contracts) | ~5 min | Python only |
| fleet audit byte-reproduction | ~10 min | Python + Node |

No API keys, no accounts, no payment. If any of this takes meaningfully
longer than the table says, that is also worth an issue.
