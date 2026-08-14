# Invalidation — watching the gate refuse

The thesis of this protocol is not that claims pass; it is that
**unsupported claims FAIL, visibly and by name**. A verifier whose refusal
you have never seen is a rubber stamp, so this walkthrough tampers with a
bundle in front of you and shows the exact rejection — then restores it and
shows the pass, proving the gate keys on content, not on ceremony. Every
terminal block below is real captured output of the command above it, run
from a clean checkout of this repo with the package installed
(`pip install -e .`). Nothing is authored by hand; regenerate all of it
yourself in under a minute.

## 1. A copy of the honest bundle passes

`fixtures/valid` is the committed valid bundle. Work on a scratch copy so
the fixture itself stays pristine:

```
$ cp -r fixtures/valid demo
$ python -m vac.verify demo
structural verification: PASS (demo)
  proved offline: manifest schema, artifact presence + sha256, bundle closure,
  stated limitations, stamp agreement, declared results recomputed from artifacts.
semantic replay: NOT run by this tool. A structural PASS means the bundle is
  internally honest, not that the issuer's grader agrees. To re-earn the
  verdicts, run the bundle's replay block at the pinned issuer_commit:
    $ git clone https://github.com/example/toy-issuer issuer
    $ git -C issuer checkout f1e2d3c
    $ python -m pip install -e ./issuer
    $ python -m toy_issuer.regrade evidence/bundle.json
    $ python issuer/audit/run_audit.py --check evidence/results.json
    expected: regrade exits 0 reporting 'consistent'; audit reproduces results.json byte-identically at the stamped commit
```

Exit code 0 — and even the PASS refuses to overstate itself: the tool
prints on every run that semantic replay was **not** performed, and echoes
the replay block so the reader holds the recipe, not a promise.

## 2. Tamper exactly one hex digit

Flip the first character of the manifest's declared hash for
`evidence/bundle.json`. One digit — the smallest possible lie:

```
$ python - <<'PY'
import json, pathlib
p = pathlib.Path("demo/vac.json")
m = json.loads(p.read_text())
e = m["evidence"][0]                      # evidence/bundle.json
e["sha256"] = ("0" if e["sha256"][0] != "0" else "1") + e["sha256"][1:]
p.write_text(json.dumps(m, indent=1) + "\n")
print("tampered", e["path"], "->", e["sha256"])
PY
tampered evidence/bundle.json -> 04931fe8d466c2cfdbf3c15013d8aa013bc54a2e340fb89737972ef3612550d4
```

## 3. The verifier refuses, by name, with both hashes

```
$ python -m vac.verify demo
FAIL sha256-mismatch: evidence/bundle.json: manifest 04931fe8d466c2cfdbf3c15013d8aa013bc54a2e340fb89737972ef3612550d4, file 64931fe8d466c2cfdbf3c15013d8aa013bc54a2e340fb89737972ef3612550d4
structural verification: FAIL — 1 named reason(s) (demo)
  proved offline: manifest schema, artifact presence + sha256, bundle closure,
  stated limitations, stamp agreement, declared results recomputed from artifacts.
semantic replay: NOT run by this tool. A structural PASS means the bundle is
  internally honest, not that the issuer's grader agrees. To re-earn the
  verdicts, run the bundle's replay block at the pinned issuer_commit:
    $ git clone https://github.com/example/toy-issuer issuer
    $ git -C issuer checkout f1e2d3c
    $ python -m pip install -e ./issuer
    $ python -m toy_issuer.regrade evidence/bundle.json
    $ python issuer/audit/run_audit.py --check evidence/results.json
    expected: regrade exits 0 reporting 'consistent'; audit reproduces results.json byte-identically at the stamped commit
```

Exit code 1. The rejection is a **named reason carrying its own evidence**:
`sha256-mismatch`, the artifact path, the manifest's claim (`04931f…`) and
what the bytes actually hash to (`64931f…`) — a reader can see the single
flipped digit in the output itself. No score, no warning level, no
"93% verified": the bundle's word disagreed with its bytes, so the bundle
is refused.

## 4. Restore, and the same gate passes the same bytes

```
$ cp fixtures/valid/vac.json demo/vac.json
$ python -m vac.verify demo
structural verification: PASS (demo)
  proved offline: manifest schema, artifact presence + sha256, bundle closure,
  stated limitations, stamp agreement, declared results recomputed from artifacts.
semantic replay: NOT run by this tool. A structural PASS means the bundle is
  internally honest, not that the issuer's grader agrees. To re-earn the
  verdicts, run the bundle's replay block at the pinned issuer_commit:
    $ git clone https://github.com/example/toy-issuer issuer
    $ git -C issuer checkout f1e2d3c
    $ python -m pip install -e ./issuer
    $ python -m toy_issuer.regrade evidence/bundle.json
    $ python issuer/audit/run_audit.py --check evidence/results.json
    expected: regrade exits 0 reporting 'consistent'; audit reproduces results.json byte-identically at the stamped commit
$ rm -rf demo
```

Exit code 0 again. Both directions are now demonstrated on the same bundle:
the gate fires on the lie and only on the lie.

## Where this same refusal is enforced without you

A gate you have to remember to run is half a gate. The rejection above is
wired into every path a claim takes to the public:

- **CI liveness** — the `invalidation-liveness` job in
  [ci.yml](.github/workflows/ci.yml) requires the committed valid fixture
  to pass and **every** committed tamper to be refused, on every push. The
  six tampers cover distinct failure classes, one edit each:
  `missing-artifact`, `sha256-mismatch`, an inflated verdict count
  (`summary-mismatch`), `empty-limitations`, `missing-issuer-commit`, and a
  cooked board row with a *fixed* hash that only recomputation from raw
  evidence catches (`raw-aggregate-mismatch`).
- **Registry admission** — `python -m vac.registry` builds
  [registry.json](registry.json) exclusively from committed issuer bytes
  and records any bundle that fails verification as *pending with its
  named reasons*, never as an entry (SPEC.md section 5, rule 7).
- **The published page** — the `verify` job in
  [pages.yml](.github/workflows/pages.yml) re-fetches every registered
  artifact at its public URL and requires the registry to regenerate
  byte-identically before [the page](index.html) may deploy: the page can
  say "pending", it cannot overstate.
- **Independent replay** — [replay.yml](.github/workflows/replay.yml)
  downloads every artifact by URL, refuses any byte that does not hash to
  its registry pin, re-runs this same structural verification, then
  executes each bundle's replay block at the pinned issuer commit to
  re-earn the verdicts with the issuer's own grader.

A claim that survives all of that is not "trusted" — it is merely, so far,
unrefuted, and carries the exact instructions for refuting it. That is the
only standing VAC issues.
