# Archived CI logs

GitHub Actions keeps run logs for 90 days
(`gh api repos/egnaro9/vac-protocol/actions/permissions/artifact-and-log-retention`
answers `{"days":90,"maximum_allowed_days":90}`, and 90 is also the maximum the
plan allows). Several figures the arXiv v2 draft cites exist nowhere else: no
post-v1 mutation sweep output is archived in this repository, and the per-site
verdicts for `a17af5c` were only ever printed by a CI job. Once a log expires
the citation becomes uncheckable, so the logs are copied here while they are
still reachable.

`MANIFEST.json` is the record. Per run it holds the run id, the workflow, the
full head commit, the run's creation time, the conclusion, the estimated expiry,
the byte length and a sha256 of the stored file, the ledger items that cite it,
and the exact strings the citation depends on.

The estimated expiry is `run_created_utc` plus 90 days. GitHub measures
retention from completion rather than creation, so a real expiry falls at or
after the estimate and never before it. The earliest here is 2026-11-06.

No `replay` run exists for the fix commit `c441011`: only `vac` and `registry` ran on that push. Any sentence that calls `c441011` green has to say which workflows it means.

## What each log is for

| Ledger item | Runs | The claim it carries |
|---|---|---|
| V2-07 | the eight `vac` runs from `3f49c14` to `0b44bf2`, plus `c441011` | the post-v1 mutation score path: 152/152, 152/152, 157/157, 161/161, 161/161, 166/166, 166/166, 166/166, then 168/168 at the fix commit |
| V2-34 | `vac` at `a17af5c` (run 31927793408, job 95117946431) | 133 verdict lines, 123 caught, survivors at L325, L362, L384, L393, L461, L466, L470, L572, L592 and L1348; the banner and the 0.940 floor |
| V2-46 | `replay` at `50e613e`, at `6a05245` twice and at `0b44bf2`, and `vac` plus `registry` at `c441011` | the named runs that replace the bare phrase "CI green". The replay workflow failed at `50e613e`, the commit v1 was submitted from, on two pending issuer bundles; it failed twice more at `6a05245`; it has passed since 2026-09-11, and its last run before the fix commit was green |
| V2-42 | the five `model-drift` `track` runs | the logged Gemini errors: a TimeoutError on 2026-08-08, the first depleted-credit 429 on 2026-08-09, and all three models refusing from 2026-08-10 |

The `model-drift` rows are marked `conditional` in the manifest. They support a
paragraph that D-12 permits but has not been written. They are archived anyway
because they expire first.

## Re-checking the archive

`tests/test_ci_log_archive.py` verifies it offline: every stored file matches
its recorded length and sha256, every log names its own head commit, and every
string a citation rests on is present in the log that is supposed to print it.

    python -m pytest tests/test_ci_log_archive.py -q

A log is the run's whole output, unfiltered, as `gh run view <id> --log` emits
it. Nothing here is trimmed, reordered or regenerated.
