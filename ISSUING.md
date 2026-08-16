# Issuing a bundle when you are not us

Everything in the registry today was issued by one person, which makes it one
multi-repository fixture rather than a protocol anyone can use. If you issue a
bundle, you are the first real test of whether this spec is writable against by
someone who did not write it. Hitting something ambiguous is a useful outcome,
not a failed attempt. [Open an issue](https://github.com/egnaro9/vac-protocol/issues)
when you do.

You do not need our formats. `rows-aggregate-v1` (SPEC §3.7) takes rows in
whatever shape you already publish.

## The whole path

```bash
pip install "git+https://github.com/egnaro9/vac-protocol"

cd your-repo
mkdir vac && cp path/to/your/results.json vac/     # whatever you already emit
python -m vac.draft vac
```

`vac draft` derives only the mechanical fields: per-file sha256, your issuer and
commit from the git remote, the replay skeleton. Everything that is a judgment
comes out as a `TODO(...)` marker, and `python -m vac.verify vac` refuses the
bundle until every one is replaced. It will not guess your scope or your
limitations, because those are claims, not metadata.

Fill in the TODOs, then:

```bash
python -m vac.verify vac
```

## The one part that is not obvious

Your `results.checks` entry has to say **how each declared number is
recomputed**, not just what it is. That is the whole point: a verifier that took
your numbers on faith would be decoration.

```json
{
  "profile": "rows-aggregate-v1",
  "artifact": "results.json",
  "rows_key": "cases",
  "recompute": {
    "accuracy":   {"op": "rate_true", "field": "passed", "round": 4},
    "n_cases":    {"op": "count"},
    "worst_case": {"op": "min",  "field": "score", "round": 4},
    "mean_score": {"op": "mean", "field": "score", "round": 4}
  },
  "expect": {"accuracy": 0.8, "n_cases": 5.0, "worst_case": 0.42, "mean_score": 0.822}
}
```

`rows_key` names the array inside your document; omit it if the document *is*
the array. `op` is one of `count`, `sum`, `mean`, `rate_true`, `min`, `max`. The
recipe is data, never code, so there is nothing to evaluate and no way to smuggle
logic through it.

Every declared number must appear in `recompute`, and every recomputed value must
match what you declared. If they disagree, the verifier names which one and by
how much.

## A complete, verifiable example

[`examples/outsider/`](examples/outsider) is a bundle from a fictional issuer
(`someone-else/mytool`) using their own artifact shape. It verifies:

```bash
python -m vac.verify examples/outsider
```

Copy it and replace the contents. Note what it does **not** do: one of its five
cases fails, and the bundle reports it as failing. A bundle whose suite is
suspiciously clean is less convincing, not more.

## Things that will refuse you, and why

| refusal | cause |
|---|---|
| `draft-incomplete` | a `TODO(...)` marker is still in the manifest |
| `empty-limitations` | `claim.limitations` is empty. A claim that says nothing about what it does not cover is an advertisement |
| `rows[] is empty` | every aggregate over nothing is trivially satisfiable |
| `... is not the type op ... requires` | e.g. `rate_true` over strings. Types are named, never coerced |
| `... is not one of count/sum/...` | an unrecognised `op`. Unknown values are refused, never defaulted |
| `declared but the recipe does not recompute it` | you declared a number without saying where it came from |
| `evidence-unchecked` | an artifact is listed but no check reads it |
| `summary-outruns-checks` | a headline number no check re-earns |

## What a PASS actually means

That the numbers you declared are recomputable from the artifacts you shipped,
and that the bundle is internally closed. **It does not mean your rows are
honest.** Nothing offline can establish that. That is what `replay` is for: the
exact commands a stranger runs to re-earn your artifacts from your code at the
pinned commit.

A bundle using `rows-aggregate-v1` leans harder on its replay block than one
using a profile that knows your grader, because the verifier here recomputes
arithmetic over rows it cannot independently produce. Say so in
`claim.limitations`. The example does.

## If your shape does not fit

`rows-aggregate-v1` handles per-row aggregates. If your evidence is genuinely
something else, that is worth an issue rather than a workaround. Bending your
artifact to fit a profile makes the bundle less honest, which is the opposite of
the point.
