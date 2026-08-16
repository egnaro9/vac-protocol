# VAC — Verifiable Agent Claims

## Capability Evidence Bundle, v0.1

A VAC bundle is the unit of a capability claim about an AI system: one
directory holding a manifest (`vac.json`) and the evidence artifacts the
claim is derived from, pinned by content hash, with the exact instructions
for re-earning every verdict from the issuer's own deterministic grader.
The design premise is **do not trust the issuer** — including us. Anything
a reader must take on faith is a defect in the bundle, not a feature of
the format.

VAC is the trust layer over five live issuers, and its five evidence
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
- [evalmut](https://github.com/egnaro9/evalmut) — eval-suite mutation
  testing over a mined operator battery. Evidence is the payload of
  `evalmut run <suite> --json --all` (score, tally, and hole classes,
  plus the per-mutation rows they must recompute from), reproduced
  byte-identically by re-running `evalmut run` at the pinned commit.
- [crashkit](https://github.com/egnaro9/crashkit) — the AI crash-test
  platform: frozen adversarial/agentic batteries graded by deterministic
  gradecore predicates under a severity-weighted vulnerability score.
  Evidence is `eval_run.json` (metrics plus per-case rows carrying
  explicit passed/truncated booleans), reproduced byte-identically by
  `python emit_vac.py` at the stamped commit.
- [model-drift](https://github.com/egnaro9/model-drift) — the public LLM
  drift board. Evidence is the committed per-run rows (`metrics.json`
  joined to the `models.json` registry) plus every published derived
  view — standings, flip/probe-alarm analysis, narrative, `RESULTS.md` —
  each recomputed offline from the rows, reproduced byte-identically by
  `python3 emit_vac.py` at the stamped commit.

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

"Derivable" is operational, not rhetorical: every numeric value in
`summary`, at any nesting depth, must equal a quantity some check's §3
recomputation produces — a summary key that names a recomputed field is
held to that field's recomputed value(s) — and any numeric value no check
re-earns is a verification failure (`summary-outruns-checks`).

Descriptive prose passes through. **A numeral wearing quotes does not.** A
`summary` value that is a JSON *string* but parses as a number — `"9999"`,
`"0.5"`, `"12%"` — is a verification failure with the same reason: a headline
number MUST be a JSON number so that it can be compared to a recomputation.
This rule was added after the earlier wording ("non-numeric, descriptive
values pass through") was found to admit a total forgery: retyping every
number in `summary` as a string moved the whole headline out of the
comparison, with no artifact touched and no hash re-pinned. The spec had
permitted a class of lie it had not imagined. If an issuer genuinely needs
prose, it must not be a bare numeral.

Closure, too, is part of "recomputed from artifacts": every artifact listed
in `evidence` MUST be referenced by at least one check. An artifact that is
pinned but read by nothing is unexamined, and the phrase would otherwise mean
*some* artifacts. Uncovered evidence is a verification failure
(`evidence-unchecked`). Deleting the check that recomputes a number must cost
an issuer what breaking it costs; constraining how a check fails does not
constrain whether it runs.

### 2.6 `replay`

| field | type | rule |
|---|---|---|
| `issuer_commit` | string | non-empty (`missing-issuer-commit`); MUST equal `protocol.issuer_commit` (`issuer-commit-mismatch`) |
| `commands` | array of strings | non-empty; the exact sequence: clone the issuer, check out `issuer_commit`, install, run its deterministic regrader/audit against this bundle's artifacts |
| `expected` | string | non-empty; the expected outcome — exit code and report text |

Replay commands are opaque shell text addressed to a human or a CI job;
VAC assigns no semantics to their contents (a clone URL inside a command
is text, not a protocol-level identifier — see §7).

### 2.7 Drafts

`python -m vac.draft <bundle-dir>` scaffolds a manifest over the artifact
files present. The split it enforces is the spec's own: **mechanical**
fields are derived — sha256 for every file, `protocol.issuer` (owner/name
from the enclosing repo's git remote), `protocol.issuer_commit` and
`replay.issuer_commit` (HEAD; a dirty tree is a printed warning, not a
refusal — drafting is not certifying), the replay skeleton's
clone/checkout lines, and a `results.checks` skeleton naming the §3
profiles to pick from — while **judgment** fields come out as markers:
string values beginning `TODO(`, each carrying one line of guidance.
`claim.capability`, `claim.scope`, `claim.limitations`, the `subject`
fields, `protocol.task`/`hashes`/`grading`/`control_policy`, results
semantics, and the replay run/compare lines are judgment. **The drafter
never infers them — never `claim.scope` or `claim.limitations` in
particular**: what a claim covers and what it does not cover are
authored, and a tool that guessed them would manufacture exactly the
advertisement §2.1 refuses to carry.

The marker is grammar, not convention: a verifier MUST refuse any
manifest containing a string value that begins `TODO(`, one named reason
per marker (`draft-incomplete: <path> is an unauthored TODO`), and MUST
refuse **before any other verification** — a draft is a workpiece, not a
candidate claim, and nothing else about it is worth naming until it is
authored (the refusal is a refusal either way, so the short-circuit can
hide nothing). Additive in the §8 sense: the marker grammar is introduced
here and appears in no accepted bundle — CI proves the registry clean of
it — so no existing bundle changes how it verifies.

## 3. Evidence profiles

A profile is a pair: an artifact format and the exact offline
recomputation a verifier performs against it. v0.1 defines five.

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

### 3.3 `evalmut-run-v1`

Check shape: `{"profile": "evalmut-run-v1", "artifact": <path>,
"catalog": <path>?, "expect": {…}}` where `artifact` is a listed
evidence path holding the payload of `evalmut run <suite> --json --all`:
an object with `score`, `tally` (the five outcome counts
`caught`/`missed`/`flagged`/`error`/`na`), `holes` (result rows keyed by
class `vacuous`/`blind`/`error`/`brittle`/`coverage_gap`), and `results`
— the per-mutation rows, each carrying `operator_id`, `family`,
`polarity`, `op_type`, `outcome`. The `--all` form is REQUIRED: a
payload whose `results` is null carries only aggregates, which are a
declaration, not evidence (`artifact-unparsable`). `catalog`, when
present, is a listed path holding `evalmut operators --json` — the
operator battery, each entry with a unique non-empty `id` and a
non-empty `real_origin` (the mined-provenance claim is checkable, not
asserted).

Recomputation, over the rows:

- every row must be internally coherent: outcome `missed` requires
  polarity `defect` and outcome `flagged` requires polarity `equivalent`
  — outcome semantics are internal to each row, not taken on faith;
- the artifact's `tally` must equal the outcome counts over the rows,
  and its `score` must equal `caught / applied` exactly, where
  `applied` = `caught + missed + flagged` (1.0 when nothing applied; the
  payload carries the full-precision float);
- each `holes` class must equal, as a multiset, the rows it is defined
  over: `vacuous` = missed sanity rows, `blind` = missed kill rows,
  `error` = error rows, `brittle` = flagged rows, `coverage_gap` =
  missed diagnostic rows;
- with `catalog` present: every row's `operator_id` names a catalog
  entry and agrees with it on `family`, `polarity`, and `op_type`.

Every key in `expect` MUST name a recomputed field and equal its value
(`summary-mismatch`): the five outcome counts, `applied`, `results`
(row count), `score_3` (= `round(score, 3)`), the hole-class counts
`vacuous`/`blind`/`brittle`/`coverage_gap`, `operators_exercised`
(distinct `operator_id`s over the rows), and — with `catalog` —
`operators` (catalog size).

No stamp binding: the payload is stampless by design (evalmut emits no
clock, commit, or version into results). The pins that scope the claim —
`issuer_commit`, the grader dependency version (e.g.
`gradecore==0.10.0`), suite-file hashes — live in `protocol.hashes` and
`subject.version` and are exercised by the replay block, not recomputed
from this artifact. One replay trap, named here so `replay.expected` can
state it: `evalmut run` exits 1 BY DESIGN when the run finds serious
holes — the finding is the result, and a registry CI that reads that
exit as failure has mis-stated `expected`.

What this does not prove: that the graders actually produced these
outcomes — that is `evalmut run` at the pinned commit reproducing the
payload byte-identically; the replay block runs it.

### 3.4 `crashkit-battery-v1`

Check shape: `{"profile": "crashkit-battery-v1", "artifact": <path>,
"battery_hash_key": <key>, "expect": {…}}` where `artifact` is a listed
evidence path holding a crashkit `eval_run.json` payload: an object with
`git_sha` (the frozen battery's content fingerprint), `metrics`,
`per_kind`, and `cases` — each case carrying explicit boolean `passed`,
`truncated`, `flagged` plus its `kind`, `severity`, and `grader`. A case
without the explicit booleans and kind is `artifact-unparsable`: an
aggregate a verifier could only re-earn by parsing free-text notes is a
declaration, not evidence.

Recomputation, over the case rows, with the severity table fixed by the
profile (`none/low/med/high/critical` = `0/1/2/4/8` — the same weights
crashkit grades with). A graded case carrying a severity **outside** that
table — including a missing one — is `artifact-unparsable`, named by the
offending label.

This replaces an earlier rule that an unknown severity weighs 0. That rule
handed the issuer the denominator: re-casing `critical` to `Critical` on the
FAILED rows alone dropped them to weight 0, and `vulnerability_score`
divided to a clean, false `0.0` through ordinary arithmetic — never touching
a guard or a fallback branch — on a bundle whose own rows recorded three
failures. A weight table that silently absorbs unknown labels is not a
frozen table; it is an issuer-controlled one.

- every case must satisfy `flagged == (NOT passed AND NOT truncated)` —
  flag semantics are internal to each row, not taken on faith;
- the **graded** set is the non-truncated cases; `accuracy` =
  `round(passed / graded, 4)` (0.0 when nothing is graded) and MUST equal
  each of the artifact's four accuracy aliases `metrics.faithfulness`,
  `precision@k`, `recall@k`, `citation_rate`;
- `vulnerability_score` = `round(Σ weight(severity) over graded failed /
  Σ weight(severity) over graded, 4)` (0.0 when the denominator is 0)
  MUST equal the artifact's;
- `flagged_cases`, `n_cases`, `truncations` MUST equal their counts over
  the rows, and `reliability` = `round((cases − errors − truncations) /
  cases, 4)` (errors = rows with `grader == "error"`; 0.0 with no cases)
  MUST equal the artifact's;
- `per_kind` MUST equal, key for key in both directions,
  `{kind: round(passed / total, 4)}` over the graded rows.

Every key in `expect` MUST name a recomputed field and equal its value
(`summary-mismatch`): `accuracy`, `vulnerability_score`, `flagged_cases`,
`n_cases`, `truncations`, `reliability`, `cases`, `graded`, `errors`.

Stamp binding per §2.3: `battery_hash_key` is REQUIRED and names the
`protocol.hashes` entry that MUST equal the artifact's `git_sha` — the
frozen battery fingerprint. This is identity, not integrity (the
fingerprint is short); integrity is the manifest's full sha256 over the
artifact bytes. A key absent from `protocol.hashes`, or a value that
differs from `git_sha`, is `stamp-mismatch`.

What this does not prove: that crashkit's graders produced these rows,
or that the issuer's twin controls (a safe mock scoring exactly 0.0 and
a vulnerable mock exactly 1.0, per its `control_policy`) actually held —
that is `python emit_vac.py` at the pinned commit, which refuses on
control drift and reproduces every artifact byte-identically; the replay
block runs it.

### 3.5 `modeldrift-board-v1`

Check shape: `{"profile": "modeldrift-board-v1", "metrics": <path>,
"registry": <path>, "standings": <path>, "flips": <path>,
"narrative": <path>, "results_md": <path>, "fingerprint": <path>,
"expect": {…}}` — every value a listed evidence path: the stored per-run
rows (`metrics` — an object whose `series` maps each model id to its
ordered point list), the model registry (`registry` — the ordered array
of tracked models), the four published derived views (`standings`,
`flips`, `narrative`, `results_md`), and the frozen suite's fingerprint
(`fingerprint` — `suite_version`, `suite_hash`, `tasks`, `task_ids`).

Recomputation — the board's whole derivation layer re-earned from the
rows:

- **coherence**, over every stored point: `acc` and `reliability` in
  [0,1]; `refusal_rate` null or in [0,1]; `latency_ms` >= 0;
  `runs` >= 1; `acc_spread` >= 0; `fails` ⊆ `fingerprint.task_ids`;
  `graded` (when present) an integer in 1..`fingerprint.tasks`;
  per-series `t` never decreasing; `suite`/`suite_hash` stamps (when
  present) equal to the fingerprint's; when `fails_runs` is present,
  `fails` must be one of its own samples and every sample ⊆ `task_ids`;
  and every `mock:*` point at `acc == 1.0` with empty `fails` — the live
  null control, refused when it moved (a moved control indicts the
  harness, not the models). A coherence violation ends the check:
  nothing derived from sick rows is recomputable.
- **standings**: one row per registry entry, in registry order, from the
  last two stored points of its series — `acc` = the newest point's;
  `delta` = `round(acc − previous, 4)`; verdict
  regressed/improved/unchanged at ±1e-9, `baseline` with one stored
  point, `no-data` with none; `graded` = the newest point's;
  `min_detectable_pts` = `round(100/graded, 3)` (null without `graded`);
  `below_floor` = `1e-9 < |delta×100| < 100/graded`; plus the
  suite-level floor `min_detectable_pts_full_grade` =
  `round(100/fingerprint.tasks, 3)` — the recomputed object MUST equal
  the committed `standings` artifact exactly, key for key.
- **results_md**: the standings table re-rendered from the RECOMPUTED
  rows under the profile's pinned template (accuracy `{:.1f}%`, delta
  `{:+.1f} pts`, floor `±{:.1f}` with the `⚠ below floor` suffix under
  the same inequality, the five verdict icons 🔴🟢⚪🔵⚫, header naming
  `fingerprint.suite_version`) MUST be byte-identical to the committed
  file — a divergence means the board's two stores disagree.
- **flips**: recomputed from the stored `fails` vectors — per non-mock
  series a flip is a task entering or leaving the fails set between
  consecutive fails-bearing points (per-model rows sorted by
  (−flips, task)); `repeat_offenders` = pairs that flipped more than
  once, sorted by (−flips, model); `one_offs` = exactly-once pairs in
  series insertion order; `probe_alarms` = (day, task) pairs where >= 3
  distinct providers (the id prefix before `:`) failed the task on one
  UTC day, sorted by (−n_providers, day, task);
  `models_with_enough_history` = series (mock included) with >= 2
  fails-bearing points — MUST equal the committed `flips` artifact.
- **narrative** internal coherence: `claims_fired` == `len(sentences)`
  and `text` == the whitespace-normalized, tag-stripped `html`.
  Byte-identical REGENERATION of the narrative is the replay block's job
  (the claims generator at the stamped commit), not structural.

Every key in `expect` MUST name a recomputed field and equal its value
(`summary-mismatch`): `rows`, `regressed`, `improved`, `unchanged`,
`baseline`, `no_data`, `series`, `points`, `tasks`,
`min_detectable_pts_full_grade`, `probe_alarms`, `repeat_offenders`,
`one_offs`, `models_with_enough_history`, `claims_fired`; these fifteen
are also the §2.5 summary pool.

Stamp binding per §2.3: `protocol.hashes.suite_hash` MUST equal the
fingerprint's `suite_hash`, and `protocol.hashes.metrics_sha256` /
`registry_sha256` MUST equal the evidence hashes of the `metrics` /
`registry` artifacts (`stamp-mismatch` otherwise) — the derivations are
claims about exactly those input bytes.

What this does not prove: that the stored rows record real probe runs —
the model responses are historical and nondeterministic by construction
(the issuer's own first limitation), so no replay reproduces them — or
that the narrative's sentences are what the issuer's claims generator
emits. That is `python3 emit_vac.py` at the stamped commit re-deriving
the whole bundle byte-identically from the committed rows; the replay
block runs it.

## 4. Structural verification vs semantic replay

Two distinct acts, never to be conflated:

- **Structural verification** (`python -m vac.verify <bundle>`): zero
  network, zero issuer code. Proves the manifest is schema-valid, every
  artifact is present and hash-identical, the bundle is closed,
  limitations are stated, stamps agree, and every declared number is
  recomputed from the artifacts themselves. Exit 0 only when clean;
  otherwise one **named reason per failure** (the vocabulary used in this
  spec: `missing-manifest`, `invalid-json`, `draft-incomplete`,
  `schema-violation`,
  `empty-limitations`, `missing-artifact`, `sha256-mismatch`,
  `unlisted-file`, `duplicate-artifact`, `unknown-profile`,
  `check-artifact-not-listed`, `artifact-unparsable`, `summary-mismatch`,
  `summary-outruns-checks`,
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
a new version. Adding an evidence profile is additive in exactly this
sense — it widens what a bundle may declare without changing how any
existing bundle verifies — so `evalmut-run-v1` (§3.3),
`crashkit-battery-v1` (§3.4), and `modeldrift-board-v1` (§3.5) landed
as v0.1 profile additions, no
version bump. No timestamps appear anywhere in this format: time, where
it matters, is expressed as commits and content hashes, which are
checkable — dates are not.
