# VAC — Verifiable Agent Claims

## Capability Evidence Bundle, v0.1

A VAC bundle is the unit of a capability claim about an AI system: one
directory holding a manifest (`vac.json`) and the evidence artifacts the
claim is derived from, pinned by content hash, with the exact instructions
for re-earning every verdict from the issuer's own deterministic grader.
The design premise is **do not trust the issuer** — including us. Anything
a reader must take on faith is a defect in the bundle, not a feature of
the format.

VAC is the trust layer over two live issuers, and its two evidence
profiles are their formats verbatim:

- [agent-certlab](https://github.com/egnaro9/agent-certlab) — capability
  contracts for coding agents. Evidence is `bundle.json` (per-task
  verdicts with full unified diffs and the agent's raw output), regraded
  independently by `python -m certlab.regrade`.
- [reference-fleet](https://github.com/egnaro9/reference-fleet) —
  certified defect models and the audit board. Evidence is
  `board/results.json` (aggregate rows stamped with `fleet_commit`) plus
  `board/raw_results.jsonl` (per-request paired outcomes), reproduced
  byte-identically by `python audit/run_audit.py` at the stamped commit.

## 1. The object

```
my-claim/                    # any directory name; no semantics attached
├── vac.json                 # the manifest — everything normative is here
└── evidence/…               # artifacts, any layout, every file listed + hashed
```

A bundle is **closed**: every file in the directory other than `vac.json`
MUST appear in the manifest's `evidence` list with its sha256. A file
present but unlisted is a verification failure (`unlisted-file`) — a
verified bundle cannot smuggle content. Bundles MAY be shipped as a
`.tar.gz` of the directory; verifiers extract (rejecting absolute paths,
`..`, links) and verify the directory.

## 2. `vac.json` — the manifest

Top level: an object with exactly these six required members plus
`vac_version`. Unknown extra keys are permitted (forward compatibility)
but carry no meaning in v0.1.

| field | type | rule |
|---|---|---|
| `vac_version` | string | exactly `"0.1"` |
| `claim` | object | the claim, its scope, and its **non-claims** |
| `subject` | object | what the claim is about, pinned |
| `protocol` | object | who graded it, how, at what commit, over what hashed inputs |
| `evidence` | array | every artifact path + sha256 |
| `results` | object | declared numbers, each recomputable offline from artifacts |
| `replay` | object | exact commands to re-earn the verdicts from the issuer |

### 2.1 `claim`

| field | type | rule |
|---|---|---|
| `capability` | string | non-empty; the one-sentence claim |
| `scope` | string | non-empty; where the claim holds — task set, grading regime, environment |
| `limitations` | array of strings | **REQUIRED, non-empty** |

`limitations` is load-bearing, not decorative: a bundle without explicit
non-claims is **invalid** (`empty-limitations`). A capability statement
that does not say what it does *not* cover is an advertisement, and VAC
does not carry advertisements.

### 2.2 `subject`

| field | type | rule |
|---|---|---|
| `kind` | string | `"agent"` or `"suite-archetype"` |
| `id` | string | non-empty; the subject's name as the issuer ran it |
| `version` | object | **non-empty**; every identifier that pins the exact subject — model id, harness commit, config, seed, rate. Free-form keys; a claim about an unpinned subject is unverifiable and rejected |

### 2.3 `protocol`

| field | type | rule |
|---|---|---|
| `issuer` | string | non-empty; the issuing repo as plain `owner/name` text |
| `issuer_commit` | string | non-empty; the issuer commit that produced **and regrades** this evidence |
| `task` | string | non-empty; task family / archetype / board identifier within the issuer |
| `hashes` | object | non-empty; the content hashes pinning protocol inputs — e.g. certlab's `taskset_hash` + `prompt_hash`, or the fleet's `fleet_commit` stamp |
| `grading` | string | non-empty; how verdicts are computed — MUST describe a deterministic procedure |
| `control_policy` | string | non-empty; the negative controls the protocol ran (certlab: null/oracle/test-deleter calibration agents; fleet: the clean twin graded beside every defective response) |

One commit pins everything: `issuer_commit` is the single commit at which
the evidence was produced and at which replay must run. Where an artifact
carries its own stamp (certlab's `harness_commit`, the fleet's
`fleet_commit`), it MUST equal `protocol.issuer_commit`
(`stamp-mismatch`), and hashes named in `protocol.hashes` MUST equal
their counterparts inside the artifacts.

### 2.4 `evidence`

Array, at least one entry, each:

| field | type | rule |
|---|---|---|
| `path` | string | relative, forward-slash, no `..`, not `vac.json`, unique |
| `sha256` | string | 64 lowercase hex chars; sha256 of the file's bytes |

### 2.5 `results`

| field | type | rule |
|---|---|---|
| `summary` | object | headline numbers for humans; every number MUST also appear in (or be derivable from) a check below — registries reject summaries that outrun their checks |
| `checks` | array | non-empty; each an **evidence-profile check** the verifier recomputes offline |

A check's `profile` MUST be one of the profiles in §3
(`unknown-profile` otherwise). Declared numbers that the verifier cannot
recompute from committed artifacts do not exist, as far as VAC is
concerned.

### 2.6 `replay`

| field | type | rule |
|---|---|---|
| `issuer_commit` | string | non-empty (`missing-issuer-commit`); MUST equal `protocol.issuer_commit` (`issuer-commit-mismatch`) |
| `commands` | array of strings | non-empty; the exact sequence: clone the issuer, check out `issuer_commit`, install, run its deterministic regrader/audit against this bundle's artifacts |
| `expected` | string | non-empty; the expected outcome — exit code and report text |

Replay commands are opaque shell text addressed to a human or a CI job;
VAC assigns no semantics to their contents (a clone URL inside a command
is text, not a protocol-level identifier — see §7).

## 3. Evidence profiles

A profile is a pair: an artifact format and the exact offline
recomputation a verifier performs against it. v0.1 defines two.

### 3.1 `certlab-bundle-v1`

Check shape: `{"profile": "certlab-bundle-v1", "artifact": <path>,
"expect": {…}}` where `artifact` is a listed evidence path holding an
agent-certlab `bundle.json` (object with a `verdicts` array; each verdict
has boolean `policy_ok`, `tests_ok`, `fixed`).

Recomputation: from the artifact's verdicts, compute
`verdicts = len(verdicts)`, `fixed`, `policy_ok`, `tests_ok` as counts of
`true`. Every key in `expect` MUST name one of those four fields and
equal its recomputed value (`summary-mismatch`). Stamp binding per §2.3:
the artifact's `taskset_hash`/`prompt_hash` vs `protocol.hashes`, and its
`harness_commit` vs `protocol.issuer_commit`.

What this proves offline: the declared counts are exactly what the
committed verdicts say. What it does not prove: that the verdicts are
correct — that is `python -m certlab.regrade`, which rematerializes
issued files, reapplies the bundle's diffs, and re-earns every verdict;
the replay block runs it.

### 3.2 `fleet-board-v1`

Check shape: `{"profile": "fleet-board-v1", "aggregate": <path>,
"raw": <path>, "expect": {…}?}` where `aggregate` is a reference-fleet
`results.json` (object with `rows`, each
`{suite, member, n, detected, detection_rate, false_alarms,
false_alarm_rate}`) and `raw` is the paired per-request evidence
`raw_results.jsonl` (one JSON object per line:
`{suite, member, i, defective_failed, clean_passed, detected}`).

Recomputation, per aggregate row, over the raw lines with the same
`(suite, member)`:

- every raw line must satisfy
  `detected == (defective_failed AND clean_passed)` — the paired protocol
  is internal to each line, not taken on faith;
- `n` = line count, `detected` = count of `detected`, `false_alarms` =
  count of `clean_passed == false`, `detection_rate` =
  `round(detected/n, 3)`, `false_alarm_rate` = `round(false_alarms/n, 3)`;
- each recomputed value MUST equal the row's (`raw-aggregate-mismatch`);
- rows with no raw lines, and raw `(suite, member)` groups with no row,
  are failures — aggregates and raw evidence must cover each other
  exactly.

`expect.rows`, when present, MUST equal the number of aggregate rows.
Stamp binding per §2.3: the aggregate's `fleet_commit` vs
`protocol.issuer_commit` and `protocol.hashes.fleet_commit`.

What this does not prove: that the board's numbers came from real suite
runs — that is `python audit/run_audit.py` at the stamped commit
reproducing `results.json` byte-identically; the replay block runs it.

## 4. Structural verification vs semantic replay

Two distinct acts, never to be conflated:

- **Structural verification** (`python -m vac.verify <bundle>`): zero
  network, zero issuer code. Proves the manifest is schema-valid, every
  artifact is present and hash-identical, the bundle is closed,
  limitations are stated, stamps agree, and every declared number is
  recomputed from the artifacts themselves. Exit 0 only when clean;
  otherwise one **named reason per failure** (the vocabulary used in this
  spec: `missing-manifest`, `invalid-json`, `schema-violation`,
  `empty-limitations`, `missing-artifact`, `sha256-mismatch`,
  `unlisted-file`, `duplicate-artifact`, `unknown-profile`,
  `check-artifact-not-listed`, `artifact-unparsable`, `summary-mismatch`,
  `raw-aggregate-mismatch`, `stamp-mismatch`, `missing-issuer-commit`,
  `issuer-commit-mismatch`, `unsafe-archive`).
- **Semantic replay**: clone the issuer at `issuer_commit`, run its
  deterministic regrader/audit per `replay.commands`, compare against
  `replay.expected`. This re-earns the verdicts. The structural verifier
  never performs it and says so in its output — a structural PASS means
  the bundle is *internally honest*, not that the issuer's grader agrees.

A bundle that passes structure but fails replay is the interesting case:
it is a precise, reproducible accusation against the issuer.

## 5. Registry rules

A registry is a curated list of accepted bundles (in this repo:
`registry.json`, landing in a follow-up commit — see README). Whatever
its form, a registry MUST reject a claim when any of the following holds:

1. **Unpinned versions** — no `issuer_commit`, or `subject.version`
   empty. A claim about "the agent, roughly" verifies nothing.
2. **Unhashed artifacts** — any evidence outside the manifest's
   sha256 list, or any referenced-but-missing artifact.
3. **Nondeterministic grading** — the `grading` description names an LLM
   judge, human scoring, or any wall-clock- or sampling-dependent
   procedure without a pinned seed. If replay cannot reproduce it
   byte-for-byte, it is not evidence in v0.1.
4. **No declared scope** — missing/empty `claim.scope`.
5. **No declared limitations** — `claim.limitations` absent or empty.
   Non-claims are mandatory.
6. **Unrecomputable results** — any `results` number not covered by a
   profile check over committed artifacts.
7. **Failing structural verification** — the verifier's exit code is the
   floor, not the bar.

Acceptance is two-gated: structural verification (machine, this repo's
tool) then semantic replay (machine, issuer's tool, run by registry CI).
A registry that skips the replay gate MUST say so on every entry.

## 6. The challenge protocol

Any reader may challenge an accepted bundle. Three challenge classes:

- **Replay challenge** — "I ran `replay.commands` at `issuer_commit` and
  did not get `replay.expected`." The strongest class: it is a
  reproducible counter-evidence recipe, and the challenger attaches their
  full transcript.
- **Coverage challenge** — "the evidence does not support the stated
  `capability`/`scope`": e.g. the task set is narrower than the scope
  sentence implies, the control policy admits a trivial subject, or the
  summary cites numbers outside any check.
- **Scope challenge** — "the limitations are incomplete": a demonstrated
  failure inside the claimed scope that no listed limitation excludes.
  Requires a reproducible demonstration, held to the same standard as the
  bundle (pinned versions, hashed artifacts, exact commands).

Resolution procedure, in order, no step optional:

1. **Freeze** the challenged bundle: its content hash is recorded and it
   is never edited in place — bundles are immutable once challenged.
2. **Re-run the verifier** (structural) and the **replay block**
   (semantic) at `issuer_commit`, by a party other than the issuer where
   possible.
3. **Attach outputs**: full verifier output and replay transcripts are
   appended to the registry entry as challenge evidence — hashed, like
   everything else.
4. **Mark the entry** with exactly one outcome:
   - `confirmed` — challenge failed; replay and structure both hold. The
     challenge record stays attached (a survived challenge is evidence).
   - `narrowed` — the claim over-reached; a successor bundle with tighter
     `scope`/`limitations` is issued and the old entry points to it.
   - `superseded` — a newer bundle (new issuer commit, new evidence)
     replaces this one for reasons other than the challenge.
   - `invalidated` — replay or structure failed on re-run; the entry is
     dead and stays visible as a dead entry. Registries do not delete.

This section is **spec only**: v0.1 ships no tooling for challenges. The
procedure is executable by hand with the verifier and the replay block,
which is the point — the protocol must not depend on tooling that could
itself be challenged.

## 7. Explicitly refused in v0.1

Named refusals, so their absence reads as a decision rather than an
oversight:

- **Signatures.** A signature proves who spoke, not that they spoke the
  truth. VAC's trust object is replayability; signing an unreplayable
  bundle would launder it. Signatures can layer on later without changing
  the format.
- **URIs / identity schemes.** No DIDs, no PURLs, no resolvable
  identifiers. `issuer` is plain text; replay commands are opaque shell
  text. Naming authorities are a trust dependency this layer refuses.
- **Accounts.** No issuer registration, no login, no reputation scores.
  A bundle's standing is its verifier output and its challenge history.
- **Hosted registry.** `registry.json` is a file in a repo, reviewed like
  code. A hosted service would put an operator between the reader and the
  evidence.
- **Docker images.** Environment pinning is `issuer_commit` plus the
  issuer's own dependency declarations. Shipping opaque filesystem images
  as "reproducibility" hides exactly the drift this protocol exists to
  surface. (Recorded env facts inside artifacts, like certlab's `env`
  block, are welcome — as evidence, not as a substitute for replay.)

## 8. Versioning

`vac_version` is the format contract. v0.1 verifiers MUST refuse any
other value rather than guess. Additive, non-breaking fields may appear
under unknown keys today; anything that changes verification semantics is
a new version. No timestamps appear anywhere in this format: time, where
it matters, is expressed as commits and content hashes, which are
checkable — dates are not.
