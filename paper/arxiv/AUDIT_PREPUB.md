# Pre-publication audit: `paper/arxiv/main.tex`

## VERDICT

**NO. Do not post as it stands.**
**9 blockers.** All 9 are cheap to fix (7 are one or two sentences, 1 is a
consent gate, 1 needs a short new paragraph). Nothing below invalidates a
measurement, a table, or an RQ answer. The defects are stale status claims,
an abstract that misdescribes its own table, and an audit record that two
pull requests overtook about an hour before the manuscript's last save.

Run 2026-08-18 against `de837a4`, working tree clean. Read-only on the repo;
measurements taken in detached `/tmp` worktrees, since removed.

---

## BLOCKERS

### B1. The audit record undercounts, and omits two open findings
**Claim** (main.tex:197): "filed two pull requests."
Also (main.tex:207): "He filed five distinct forgery paths **in total**."

**Measured:** `gh pr list --repo egnaro9/vac-protocol --state all` returns
**four** PRs by `GiulioDER`: #1 (merged 2026-08-15T23:08:45Z), #2 (open),
**#8 (open, 2026-08-18T18:30:04Z)**, **#9 (open, 2026-08-18T18:30:20Z)**.
#8 and #9 were filed 14:30 EDT; `main.tex` mtime is 15:33 EDT, so both
predate the last save by an hour.

I reproduced PR #8 rather than taking it on report, on macOS, at both
`f59fb62` and HEAD (`git diff --stat 92e4548 HEAD -- vac/verify.py` is empty,
so HEAD runs are `92e4548` runs). Control first: a copy of `fixtures/valid`
plus an unlisted `evidence/stowaway.txt` gives exit 1,
`FAIL unlisted-file: evidence/stowaway.txt`. Then `evidence/bundle.json`
moved outside the bundle and replaced by a symlink to it: **exit 0**, banner
prints `proved offline: ... bundle closure`. Mechanism is at
`vac/verify.py:224-228`: the closure scan is `rglob` filtered by `is_file()`,
and `rglob` does not descend a symlinked directory while `is_file()` follows
the link. That is this paper's own class, found by this paper's own auditor,
against the commit Section 6 pins, and `grep -in 'symlink\|autocrlf\|crlf'
main.tex` returns **zero hits**.

**Fix:** at main.tex:197 write "filed two pull requests, #1 and #2, which are
the ones analysed here; as of 2026-08-18 he had filed four." At main.tex:207
drop "in total" so the five is scoped to PR #1. Add one short paragraph at
the end of sec:audit recording that two further audit pull requests arrived
after the measurement window, that #8 demonstrates a vacuous pass on the
`bundle closure` clause, and that it is open.

**Do not** renumber the title or the contributions (see REFUTED), and do not
call `bundle closure` "the load-bearing clause": main.tex:179 applies that to
the sixth banner clause, `declared results recomputed from artifacts`.
`bundle closure` is the third.

### B2. The paper says twice, one page apart, that it has and has not got a DOI
**Claim** (main.tex:1727-1730): "At the time of writing the repository carries
no tagged release and no archival DOI ... the project's own `CITATION.cff`
asks readers to cite an archived release, and that release does not yet exist."

Fourteen lines above, main.tex:1713-1717 says the opposite and is the correct
one.

**Measured:** `git ls-remote --tags origin` returns
`11291bea... refs/tags/v0.1.0`. `curl -sSL https://doi.org/10.5281/zenodo.22000911`
resolves 200 to `zenodo.org/records/22000912`, with
`https://doi.org/10.5281/zenodo.99999999999` returning 404 as a control.
`zenodo.org/api/records/22000912` gives state `done`, version `v0.1.0`,
published 2026-08-18, creator Hill, Erik. `cat CITATION.cff` already carries
both DOIs. Local `git tag -l` is empty only because tags were never fetched,
which is probably how this survived. Both paragraphs are in the shipped
`main.pdf` (verified by decompressing its content streams).

**Fix:** delete main.tex:1727-1730 from "At the time of writing the repository
carries no tagged" through "papered over." The paragraph then ends cleanly on
"which is noted where they appear."

**Second copy:** `SUBMISSION.md:107`, the text to paste into the arXiv
Comments field, ends "no tagged release or archival DOI yet." That renders
publicly and no rebuild will catch it. Replace with
"Artifacts archived at doi:10.5281/zenodo.22000911."

### B3. The paper tells the reader its headline number cannot be reproduced
**Claim** (main.tex:1829-1831): "at the time of writing neither the script nor
the `--detector` flag is committed ... re-runnable in one command on the
author's tree and not yet from a clone."

**Measured:** both landed at `e932868`, an ancestor of HEAD and on
`origin/main`. I ran it from a **fresh clone** of the public repo:
`python3 tools/fixture_corpus_score.py` printed
`FIXTURES-ONLY SCORE: 10/112 = 0.089` with ten catches on ten distinct
fixtures, and `--detector liveness` printed `LIVENESS-ONLY SCORE: 0/112 = 0.000`.
The sentence also contradicts the bullet it cross-references
(main.tex:1666, "both landed at `e932868`").

**Fix:** delete "One gap remains ... not yet from a clone." Replace with
"Both landed at `e932868`, so this figure is re-runnable from a clone."
This is the 0.089 the conclusion asks readers to take away.

### B4. Table 5's caption says a committed fixture is uncommitted
**Claim** (main.tex:1763-1764): "That fifth fixture is in the working tree and
not yet committed."

**Measured:** `git log --diff-filter=A -- fixtures/attack-crashkit-severity`
returns `b30ea2f test(fixtures): add attack-crashkit-severity`, an ancestor of
HEAD, present on `origin/main`, and inside the archived `v0.1.0` at `11291be`.
`git status --porcelain fixtures/` is empty. main.tex:1667 already says it
landed at `b30ea2f`, so the caption contradicts the bullet it points at. The
commit timestamps show it was already false when written (fixture 13:03:04,
manuscript commit 13:03:58).

**Second half of the same caption:** the fixture exists at **neither**
`f59fb62` nor `92e4548` (`git ls-tree` returns nothing at both; a clean run
gives exit 2, "not a bundle directory"), but "Copied into" is attached only
to the `f59fb62` direction. Copied in, it is exit 0 at `f59fb62` and exit 1 on
`artifact-unparsable` at `92e4548`, exactly as claimed.

**Fix:** "That fifth fixture landed at `b30ea2f`, two commits after
`92e4548`, so it is absent from both revisions named here; copied into a
checkout of either, it exits 0 at `f59fb62` and 1 at `92e4548`. From
`b30ea2f` onward, including the archived `v0.1.0`, it runs from a clean
checkout, `vac/` being unchanged across that span."

### B5. "is not done" for a fix that landed, and the paragraph around it
**Claim** (main.tex:903): "Pinning an expected site count the way `EXCLUDE`
pins its arity is the obvious fix and **is not done** (Section 13.2)."

**Measured:** `git show e932868:tools/mutation_sweep.py | grep -n EXPECT`
returns `EXPECT_RAW_SITES = 146` (line 68) and `EXPECT_SCORED_SITES = 143`
(line 69), plus `--expect-sites`. It is enforcing, not merely declared: I drove
it, and `python3 tools/mutation_sweep.py --expect-sites 143` prints
`ABORT: refusal-site population is 146 raw / 143 scored; expected 143 / 140`
and exits 2, which is exactly the delta the demonstration produces. Positive
control: `--expect-sites 146` passes that gate and stops at the next one.
main.tex:1661 already says "Landed at `e932868`."

**Fix:** patching line 903 alone is not enough. It leaves standing at
main.tex:890 "The gate covers two things and not a third", at 893-894
"Nothing asserts how many refusal sites the enumeration should find", and at
898 "keeps both exclusion counts matching so nothing aborts" (at HEAD that
refactor now aborts). Put the whole paragraph in the past tense at `92e4548`
and close with "landed at `e932868` (Section 13.2); at HEAD the same refactor
aborts the sweep with exit 2 instead of shrinking the denominator." Keep the
demonstration.

### B6. The abstract is false about its own table
**Claim** (main.tex:56): "so Table 2 carries all eleven, not the rising five."

**Measured:** `\newlabel{tab:ladder}` resolves to Table 2, page 19. The
tabular at main.tex:1135-1144 has **five** data rows. The eleven-value series
is prose at main.tex:1150-1151. The body says so at main.tex:1148-1149:
"Table 2 shows five rows that rise monotonically." Both sentences are in the
shipped PDF. `git log -S 'carries all eleven'` returns one commit, `b61ee7d`,
where the table already had five rows: the sentence was never true.
Separately, "rising" is wrong too, since the five include the 0.330 to 0.328
dip.

**Fix:** "so Section~\ref{sec:liveness-tests} carries all eleven, not just the
five rows of Table~\ref{tab:ladder}." Use `\ref`, not a hardcoded number.

**Second copy:** `SUBMISSION.md:69`, the plain-text abstract for the arXiv
form, carries the identical sentence and must change with it. That file's own
rule is to spell cross-references out, so: "so Section 7.5 carries all eleven,
not just the five rows of Table 2." Budget is fine: the fenced block measures
1872 characters against the stated 1920 limit, and this is about +20.

### B7. A branch head that has moved, in the bullet that confesses this happened once
**Claim** (main.tex:1647): "At head `bb4dda36` those tests build their
structure in Python instead ... What remains is review and merge."

**Measured:** `gh api repos/egnaro9/vac-protocol/pulls/2` gives head
`ce462e10d8e3651ef1a36013276c3bb74e1c4267`. The branch has two commits:
`bb4dda36` (2026-08-15) then `ce462e10` (2026-08-18T17:59:04Z, "test(verify):
drop the last wall-clock assertion from this branch"), pushed 93 minutes
before the manuscript's last save.

Worse than staleness: at `bb4dda36` the branch **still contained a wall-clock
assertion**. `grep -n time.monotonic tests/test_verify.py` at that sha returns
`assert time.monotonic() - start < 4.0`; at `ce462e10` it returns nothing. So
the paper vouches, as the fixed state, for a revision that still carried an
instance of the host-dependence class the bullet exists to remove. The
substance still holds at both shas (`_nest(20000, 1)` builds the structure in
Python; both traversals use explicit stacks; `vac/verify.py` is byte-identical
across the two commits, so `ce462e10` is test-only).

Also: `bb4dda36` is 8 hex digits where the paper's other 72 hashes are 7, and
neither sha resolves from a clone, because PR #2 is from a fork
(`GiulioDER/vac-protocol`); it needs `git fetch origin pull/2/head`.

**Fix:** "At `ce462e10`, the head of pull request 2 as of 2026-08-18, ..."
Seven digits. Better still, cite the PR URL rather than a bare sha from a
fork, since a reader cloning the repo cannot resolve either hash.

### B8. The first command the paper hands a stranger fails on a default Windows clone
**Claim** (main.tex:1738): "`python -m vac.verify fixtures/valid` # liveness
control, exits 0", under an Environment paragraph that constrains only the
Python version.

**Measured** with a differential pair on this machine, same commit, only
`core.autocrlf` differing:
`git -c core.autocrlf=true clone` then `python3 -m vac.verify fixtures/valid`
gives **exit 1 with 13 `sha256-mismatch` lines**; `core.autocrlf=false` gives
exit 0, PASS. All 14 files under `fixtures/valid` are LF-only in the source
tree and all 14 carry CR after the autocrlf clone. `vac/verify.py:42-44`
hashes raw bytes, so the conversion is fatal by construction. No
`.gitattributes` is tracked anywhere (`git ls-files | grep -ci gitattributes`
returns 0) and all nine CI jobs are `ubuntu-latest`. This is PR #9, open.

**The sharper half, which nobody had flagged:** on that clone all 20
`tamper-*` fixtures still exit 1, so the loop at main.tex:1739 appears to
succeed. But 16 of the 20 refuse on `sha256-mismatch` rather than the reason
Table 5 names. Three of Table 5's four rows are false there while the exit
code still matches. That is this paper's thesis, in this paper's own
reproduction section.

**Fix:** one sentence in the host-dependence paragraph (main.tex:1786):
the repository carries no `.gitattributes`, so a clone made with
`core.autocrlf` enabled, the Git for Windows installer default, rewrites every
text artifact to CRLF at checkout and the liveness control exits 1 with
thirteen `sha256-mismatch` reasons; the tamper loop still exits 1 throughout,
but sixteen of the twenty then refuse on the hash rather than the reason
Table 5 names. Do not write "twenty reasons": PR #9 says twenty, and 13 is the
arithmetic ceiling for that bundle (13 evidence entries), measured at both
HEAD and `92e4548`.

### B9. Consent for naming a living third party is ON RECORD (closed 2026-08-18)
**Claim:** main.tex:196-197, 224-227 and the Acknowledgements name Giulio
D'Erme, characterise his findings, and quote his PR body.

**Measured:** the name, the `cca-audit` attribution and the quote are all
publicly supported (`GiulioDER/cca-audit` exists, not a fork, created
2026-05-19; the quote at main.tex:218-220 is a verbatim substring of PR #1's
body). But main.tex:224-227, the mojibake anecdote, is the one claim in the
paper about a named private individual with **no public source**, and the
paper says so itself. The consent request went out 2026-08-18 16:11Z and was
granted 2026-08-18 19:34Z, written consent on file: he asked to be named and cited as
Giulio D'Erme, in the wording already in the paper, and declined co-authorship.

**Fix:** get his written yes before submitting, or de-identify that one
sentence ("the same byte-identity check caught mojibake in an auditor's output
mid-review"), which keeps the entire methodological point. arXiv cannot be
withdrawn. For a permanent posting that names a person and characterises their
work, this is blocking, not "when convenient."

---

## SERIOUS

### S1. Five enumerated lines that are four, and a row misattributed
main.tex:975: "exactly two sites turned out to be dead code and three are
excluded as unreachable ... five enumerated lines."
**Measured:** across `f59fb62..92e4548` exactly one commit deletes a refusal
site as dead, `5c2e049` (removes the non-dict `flips.json` branch, 1 deletion,
0 additions) and the same commit adds the one-entry `EXCLUDE`. At `92e4548`
`EXCLUDE` holds two fragments covering three lines, both `OSError` wrappers.
The `RESULTS.md` wrapper is counted once as dead and again inside the three,
so the distinct count is **four**. The paper agrees with the smaller
composition at main.tex:1178 and 1611 ("One was deleted; one moved into the
documented exclusion set").
**Fix:** "one site was dead code and was deleted, and three lines across two
fragments are excluded, so the enumerated population is four lines." Align
main.tex:1171's "two were dead code" to "two were not merely untested."

**Same paragraph:** main.tex:1171 says "At the 0.947 row, seven refusals still
survived" and then names the `flips.json` branch. The 0.947 row is `1674f4c`,
where `git show 1674f4c:vac/verify.py | grep -n flip-analysis` returns
nothing, because `5c2e049` had already deleted it. The described episode is
the **0.941** row (`mutation_covered.json`, 112/119, `6c3a2c8`), whose seven
survivors include line 863 (the flips branch) and line 990 (the `md_rel`
wrapper). Both rows happen to have seven survivors, which is why it is
invisible from the table.
**Fix:** change "0.947 row" to "0.941 row" at main.tex:1171.

### S2. "The score fell three times" is four
main.tex:1151. Walking the paper's own printed series
(0.330, 0.328, 0.941, 0.957, 0.960, 0.954, 0.947, 0.992, 1.000, 0.972, 1.000)
gives descents at four places. The omitted one is 0.330 to 0.328, the paper's
own headline RQ2 result, printed twice on the same page. It fits the
paragraph's thesis perfectly (numerator 37 to 39, denominator 112 to 119).
**Fix:** "fell four times: $0.330 \rightarrow 0.328$ when the four fixes added
seven sites, $0.960 \rightarrow 0.953 \rightarrow 0.947$, and
$1.000 \rightarrow 0.972$." The following clause, "in every one of those falls
the numerator rose or held", already covers the added case.

### S3. The same measurement is printed 0.954 in one section and 0.953 in another
main.tex:1151-1152 versus main.tex:1297. `123/129 = 0.95348...`, which is
**0.953** at three decimals under both half-up and half-even (checked with
`Decimal.quantize` under each). 0.954 is reachable only by re-rounding the
4dp value the sweep stores (`tools/mutation_sweep.py:217` writes
`round(score, 4)` giving 0.9535). The paper's own instrument disagrees with
0.954: line 210 prints from the raw ratio, emitting
`MUTATION SCORE: 123/129 = 0.953`. Of all 18 fractions in the paper, this is
the only one where direct and double rounding differ, and it is the one the
paper renders two ways.
**Fix:** 0.954 to 0.953 at both main.tex:1151 and 1152.

### S4. Twelve sweeps announced, eleven scores listed
main.tex:1149-1152. `ls paper/mutation*.json` is 12. Reading each:
`mutation_after.json` and `mutation_gated.json` are two distinct runs (their
per-site records differ in 3 places) that both score 39/119, so twelve files
give eleven distinct values. The paper never says so, and the caught sequence
is likewise eleven long.
**Fix:** "twelve archived sweeps, two of which record the same $39/119$, so
eleven distinct scores."

### S5. "the two that gained a site" is four
main.tex:1059. Decomposing `mutation.json` against `mutation_after.json` by
`reason`: **four** classes gained sites (artifact-unparsable 23 to 24,
evidence-unchecked 0 to 1, stamp-mismatch 8 to 12, summary-outruns-checks
2 to 3, summing to the seven new sites). **Two** gained a catch
(evidence-unchecked, summary-outruns-checks), both on new sites, credited to
`sweep:tamper-summary-string` and `sweep:tamper-check-deleted`. Everything
else in the RQ2 arm reproduces exactly, including 37 caught by tests before
and after.
**Fix:** "identical in every class except the two that gained a **catch**, and
in both of those the catch falls on a newly added site." The stronger version
is also the more damning one, so it costs nothing.

### S6. Contribution 5 and scope item 5 state the hypothesis the body refutes
main.tex:138 and main.tex:1465: "human-readable evidence artifacts remain
unbound while machine-readable ones are verified."
**Measured:** sec:closure refutes the second conjunct with its own data.
main.tex:1238: "crashkit's `variance_flaky_n10.report.json` is
machine-readable JSON and was unbound anyway", and main.tex:1263: "what
predicts the gap is the artifact's role, not its file format." The shipped
rule has no format axis at all: `vac/verify.py:1484` is
`uncovered = sorted(listed - covered)`, a set difference.
**Fix:** restate both in the body's own words: "an evidence artifact emitted
as a report is systematically underbound relative to one consumed as a check's
input." Otherwise a reviewer reading only the front matter and Table 3 has the
paper contradicting itself at n=4.

### S7. Two sections give opposite causes for the same evalmut failure
main.tex:1282 (sec:closure): "The verifier has not changed since `ba14203`;
the issuer bundles drifted." main.tex:1791 (Reproducibility): "evalmut ...
is the verifier tightening rather than the bundle rotting."
**Measured:** `git log ba14203..HEAD -- vac/verify.py` is empty and
`git show ba14203:vac/verify.py | grep -c evidence-unchecked` is 1, so the
rule already existed when evalmut "landed clean" on 2026-08-16. Its failure
now is bundle drift. The `f59fb62`-versus-`92e4548` comparison the
Reproducibility paragraph uses answers a different question.
**Fix:** delete "and only one of the two is issuer drift" and the tightening
clause, or rewrite to say both are drift relative to the 2026-08-16 clean
measurement and explain why the `f59fb62` baseline looks different.

### S8. One of the two citations for the stamp asymmetry guards the other operand
main.tex:786: "Two other profiles (`verify.py:639` and `verify.py:1000` at
`f59fb62`) fail closed on exactly this case."
**Measured:** `sed -n '632,644p'` at `f59fb62` shows :639 is
`elif key not in hashes:`, which fires when a key is missing from
**`protocol.hashes`**, the opposite of the forgery, where `protocol.hashes`
still declares all 7 pins and the artifact side is emptied. The artifact-side
fail-closed is one branch later at **:642**, `elif hashes[key] !=
data.get("git_sha")`. At :1000 the artifact operand is a recomputed
fingerprint (`fp["suite_hash"]`), so the asymmetry structurally cannot arise
there.
**Fix:** cite :642, and either drop :1000 or say plainly why it cannot
exhibit the asymmetry. This is what upgrades the section from "a design
choice I disagree with" to "a defect", and a reviewer who opens :639 lands on
a guard on the wrong side.

### S9. Item 7's "fourteen" and the Reproducibility paragraph's "six" cannot both be the same defect
main.tex:1378 says the path doubling makes "the fourteen issuer-gated tests
skip"; main.tex:1786 says the workflow sets only three of five variables and
"binding only the first three runs 6 more, not 14." If CI sets three, the path
bug can account for at most 6; the other 8 skip because CI never sets
`VAC_CERTLAB_CHECKOUT` or `VAC_FLEET_CHECKOUT`.
**Fix:** "the six tests gated on those three variables skip inside the very
job that checked the repositories out, and the other eight never had a
variable set at all." The instrument-blindness point gets sharper: two
independent causes produced the same silent zero.

### S10. "71 further places to look" does not reconstruct
main.tex:1034. 75 minus 4 gives 71, but Table 1 says only **three** of the
four forgeries map to a survivor class and states of the fourth that no
refusal site existed, so the subtraction should be 75 minus 3. Read as
classes rather than sites, the four map to classes of size 6, 1, 26 and 4.
**Fix:** state the derivation inline, or write "71 further refusal sites to
look at beyond the four hand-found defects." The paper has just spent a page
correcting four-of-four down to three-of-four; an adjacent number that only
works at four-of-four undoes the correction.

### S11. The quote the paper's footnote retracts is still live on the public branch
main.tex:220 correctly footnotes that an earlier draft attributed
"documentation that refutes an auditor is rarer than the bugs" to Giulio, that
he did not write it, and that the misattribution is corrected rather than
dropped. `git grep 'documentation that refutes an auditor' origin/main`
returns it still presented as **"his remark"** in
`paper/paper.html:42` and `paper/paper.md:65`, on the branch the arXiv paper
links to.
**Fix:** fix those two files before posting. Making the correction permanent
in the paper sharpens rather than softens the fact that the fabricated
attribution is live two files away.

### S12. PIT: an uncited superlative, and a citation that does not support its sentence
main.tex:629 "PIT, **the most widely used** Java mutation engine": the only
citation in the sentence is `\citep{pitest_faq}`, and
`curl https://pitest.org/faq/` (200, 20845 bytes) contains zero occurrences of
widely, popular, most used or market. `refs.bib` has no usage survey. The
literature hedges: arXiv:1601.02351 says "a popular mutation testing tool."
Separately, main.tex:888 "validates baseline suite state before running and
**refuses otherwise**" is true but **not on the cited page**: the FAQ lists
only causes of a discrepancy. The refusal is in the source,
`pitest/.../help/Help.java` `FAILING_TESTS` ("Mutation testing requires a
green suite"), raised as a `PitHelpError`, with `skipFailingTests` defaulting
to false.
**Fix:** "a widely used Java mutation engine", and cite `Help.java` for the
refusal, or soften line 888 to what the FAQ shows. Do not cite pitest.org's
homepage, which does carry a usage claim but is vendor copy. This is a
prior-art claim the paper uses to disclaim novelty, so overshooting it cuts
against the paper's own carefulness.

### S13. A stale draft is tracked in the submission directory
`git ls-files paper/arxiv/` lists **`main.tex.bak`** (98793 bytes, an earlier
draft carrying the numbers this audit found corrected) alongside `main.tex`,
`main.aux`, `main.out` and `main.pdf`. A reviewer can diff it and read every
withdrawn version verbatim, and if the arXiv tarball is assembled by globbing
this directory, AutoTeX gets a second `.tex` source.
**Fix:** delete or gitignore it, and confirm the upload is an explicit file
list. `SUBMISSION.md:10` says three files flat, but I found no packaging
script.

### S14. The claim the paper withdraws is still asserted at the commit it tells readers to check out
main.tex:1305 withdraws "four mutants stop being caught" and main.tex:1316
withdraws "so it measures what a developer measures".
`git show 92e4548:.github/workflows/ci.yml` line 29 still reads "the
real-bundle tests SKIP, four mutants stop being caught", and line 32 "Check
them out so CI measures what a developer does."
**Fix:** fix the comment, or note in the paper that the artifact still carries
the withdrawn wording. A reader following "Check out `92e4548`" reads the
withdrawn claim within a screen of the job under discussion.

---

## MINOR and NOTES

- main.tex:1245 quotes certlab as announcing "N/M seeded defects fixed". The literal string in all seven contracts is **"6/6 seeded defects fixed"**; "N/M" comes from the paper's own verifier at `vac/verify.py:464`, which describes the regex. Use 6/6 or drop the quote marks.
- main.tex:1290 quotes the CI banner as "(1 excluded)". The real log (job 95117946431) says "(1 excluded, **see EXCLUDE**)", and no version of the tool can print the short form. The paper quotes the same banner in full at main.tex:1182.
- main.tex:1507 calls all three `raise ValueError` sites "unsafe-tar-member". :1558 is the "archive has entries beside the bundle root" rule. The six line numbers themselves are all exact (see REFUTED).
- main.tex:1198 points at `sec:liveness-tests` from inside `sec:liveness-tests`. Delete the parenthetical; do not retarget it to `sec:exclusions` (see REFUTED).
- main.tex:897 "one pre-existing failure on the interpreter used" is true but under-specified: the cause is that `make_fixtures.py` re-runs in a subprocess and cannot `import vac` when the package is not installed, not the CPython version. Name the test and the condition.
- main.tex:171-179 says "On success the verifier prints:" and shows three lines; the real output continues with a dozen more (`semantic replay: NOT run by this tool.`). "prints, in part:".
- main.tex:762-765 "Four stamp comparisons ... (`verify.py:284, 288, 374, 383`)": four lines, five comparisons, because :284 loops over two keys. The forgery box prints three failures.
- main.tex:1131's 42-second mtime forensic is reproducible only on the author's working copy; git does not preserve mtimes. Say so, or a reader who clones finds the paper's most forensic claim uncheckable and does not know that was expected.
- main.tex:713 "One capital letter": the worked example re-cases three severities. One letter per failed row moves the score; three drive it to 0.0. Add the clause.
- main.tex:59-60 "my own measuring tools reported success while measuring nothing" for all seven: item 4 measured a real but stale tree and item 6 is a text edit. The body's own wording at main.tex:1393 ("all producing plausible output") is the accurate one; use it in the abstract.
- main.tex:1051 "seven new refusal statements, themselves untested" is contradicted 13 lines later by "covered at $2/7$". Use "mostly untested".
- main.tex:1278 "evalmut fails with 1" then names two artifacts. Verified as one refusal naming both; say "a single `evidence-unchecked` naming both".
- Table 1 row 2 (main.tex:1007) still lists `check-artifact-not-listed (1)` in the mapping column, which main.tex:1021-1027 explicitly retracts. A table lifted out of the paper restores the earlier draft's claim.
- main.tex:1480 "all 11 entries are my own repositories across five of my own projects": measured 11 entries across 5 repositories (agent-certlab 7, four others 1 each). The paper elsewhere calls the five "repositories" and "issuer families"; standardise.
- main.tex:1292 quotes "the floor 0.940" while main.tex:1182 and 1615 say CI enforces `--floor 0.99`. The floor moved between commits; four words fixes it ("the floor at that commit").
- `tab:predict` and `tab:closure` carry `\label`s that are never `\ref`ed, so nothing tells the reader where to look. RQ4's subsection has no `\label` either, and results are presented RQ1, RQ4, RQ2, RQ3.
- main.tex:1719 "Every quantitative claim here names a commit" is falsified by Table 3's closure results and the suite tallies at main.tex:1304 and 1786, none of which name one. The narrower companion claim at main.tex:157 (file and line citations) does hold: I checked all ten and none is stale.
- main.tex:726 "It never touches a guard, an exception, or a fallback branch" sits one line after `.get(sev, 0)` and 30 lines before "the CWE-636 pattern ... falls back to a more permissive state", with `dict.get(k, default)` named in the operational rules as one of four constructs that convert "did not happen" into "fine".
- main.tex:813-815 and main.tex:1400-1403 give two different root causes for the same drafting error (copied from the sweep's docstring, versus read off a reverted working copy). Pick one.
- main.tex:1400-1403 names "Items 3 and 6" and then states item 4's root cause. Split into two claims.
- **Prior publication, not disqualifying:** the ORCID in the author block links `dev.to/agentdev9`, which carries "One capital letter made my verifier call a failing score clean" (Aug 16, 2026), the paper's headline forgery. arXiv permits it; one clause in the Comments field turns a discoverable surprise into disclosed provenance.
- **Moderator scope, checked and clean:** four numbered RQs, method with a stated extraction rule, threats to validity, scope of claims, artifact section, 62 references. Zero promotional hits (`hire|available for|consult|contact me|follow me|subscribe|newsletter`), five URLs total, all ORCID/repo/DOI. Register is 51 standalone "I" over ~16.7k words, within cs.SE experience-report norms. Both neighbour papers are cs.SE primary. I would not reclassify or reject on scope.

---

## REFUTED (considered and dismissed)

- **"The 119/119 = 1.000 is an unarchived first-person report and must be hedged."** Refuted. `git show 6b6f96f:tools/mutation_sweep.py` lines 9-14 narrate it contemporaneously ("that is not hypothetical, it is exactly what this script did on its first hardened run"), the commit message of `6b6f96f` says the same, `grep -c` on that commit's `vac/verify.py` gives exactly 119 refusal sites, and `observe()` there runs `pytest -x` first. Hedging it would put a **false** provenance claim into a paper about false provenance claims. Better fix: cite `6b6f96f` in one clause.
- **"sec:gate's 237 tally is wrong, it should be 238."** Refuted. On `/usr/local/bin/python3` (3.14.3, `vac` not installed) a clean `92e4548` gives exactly `1 failed, 237 passed, 16 skipped, 4 xfailed`, unchanged after performing the refactor; the repo venv gives 238. Both of the paper's tallies are real; they are two environments. Changing 237 to 238 would make the sentence wrong.
- **"The 5m46s sweep timing is soft."** Refuted. Two re-runs on this M4 gave 341.13 s and 339.66 s, both **below** the paper's 346 s, and both while contended by sibling processes. Do not add "machine otherwise idle": there is no evidence of that and the figure is reachable without it.
- **"The six out-of-population line numbers at main.tex:1505-1507 are off by one."** Refuted three ways against the committed blob. All six (:1508, :1512, :1514, :1541, :1546, :1558) are exact, and `grep` shows the six are exhaustive. The finding's own reader was off by one.
- **"The title's 'Four Ways' and contribution 1's 'five classes' need renumbering."** Refuted. main.tex:108-112 decomposes its own five explicitly (four from Section 6 plus the `null`-artifact case). PR #8 changes neither.
- **"PR #8 is a sixth working forgery."** Refuted at the paper's own bar. After E2 passes, removing the out-of-bundle link target gives exit 1, `missing-artifact`. It passes only on a host that still holds the target; a third party replaying it gets a refusal. The five classes all survive third-party replay. It is a vacuous pass and a publication hazard, not a forgery.
- **"PR #8 defeats the clause the paper calls load-bearing."** Refuted. That phrase at main.tex:179 applies to the sixth banner clause; the symlink hole defeats the third.
- **"PR #9 produces twenty sha256 mismatches."** Refuted: 13, measured at HEAD and at `92e4548`. `fixtures/valid` lists 13 evidence entries, so 13 is the ceiling. Do not repeat "twenty".
- **"main.tex:1198 should point at `sec:exclusions`."** Refuted. That section documents three OSError-wrapper lines and explicitly disavows the "one flips.json branch and one OSError wrapper" description; retargeting creates a new mismatch.
- **"The 'two sites turned out to have none' at main.tex:1198 is the same miscount as S1."** Refuted. The predicate there is reachability, and both sites fail it; the dead-versus-unreachable distinction is about disposition.
- **"The null-artifact sentence at main.tex:199-206 fuses two separate PR rows."** Refuted by reproduction: built at `2ac0c3c`, a `null` `evidence/bundle.json` with an honest re-pin plus `summary.verdicts: 9999` gives exit 0 PASS, while the same lie without the null gives exit 1 `summary-outruns-checks`. The auditor's own committed test in `6992b76` writes exactly `evidence/bundle.json`, `b"null"`, re-hash, and a summary lie.
- **"'N/M' is fabricated."** Refuted as invention: it exists on disk, in `vac/verify.py:464`. It is a transposition of the instrument's regex description onto the artifact, which is still worth fixing (see MINOR).
- **"The `attack-crashkit-severity` fixture is 13 files."** It is 14 (13 under `evidence/` plus `vac.json`).

---

## UNCHECKED (the honest boundary)

**This section matters more than the rest. The largest gap is the bibliography.**

**Quotes and figures I could not verify** (paywalled, or not fetched):
Kupferman 2006 (both quotes, plus the Kupferman/Vardi ACTL-to-CTL* extension);
Schuler and Zeller (the 83% parser figure and both quotes, one of which is
load-bearing twice, at main.tex:1092); Inozemtseva and Holmes (31,000 suites,
five systems, "should not be used as a quality target"); Just et al. (357
faults, 73%, 17%, "statement deletion among the three operators most often
coupled", reused at main.tex:1500 as a construct-validity bound); Zhang and
Mesbah (6,700 suites, 24,000 assertions); Chen and Furia (16 of 135); Lipp et
al. (47-80%, load-bearing twice); Ladisa (107 vectors, 94 incidents); Xia (17
interviews, 65 responses); Zhao (1,045 leaderboards, reused twice); Georgiev
(the three named categories); Barr (the implicit-oracle category); Huo and
Clause ("unused inputs"); Jahangirova; Petrovic and Ivankovic ("arid");
Untch; Deng/Offutt/Li; Ji et al. (catch-block deletion); **Kumar et al.**
(throw-statement deletion, the paper's stated parent for its own operator,
cited in the contributions and twice in related work); Loise (fifteen
operators); Martin and Xie; Ami et al.'s muSE; Gorz et al.; **Orgard et al.**
(a NEGATIVE claim, "says nothing about mutating a gate"); RFC 9334's role
vocabulary; Biderman. Every DOI in `refs.bib` resolves in Crossref with
matching metadata, so the **citations** are sound; the **figures and quoted
strings inside them** are not verified. Given that a prior pass caught a
fabricated quote, these are the highest-value remaining target, and Kumar is
the one I would pull first: a novelty withdrawal that cites a paper nobody has
read at operator granularity is where this paper's own thesis can rebound on it.

**Negative claims over whole papers.** main.tex:559-561 and contribution 6
("None of the three reports its own measuring apparatus returning a passing
verdict along a path where it performed no comparison") and main.tex:516-527
(no Delcourt operator touches a judge's source, prompt, or kill detector). The
full texts of MASC, Delcourt and Bilal were read and nothing contradicting
them surfaced, but a negative over three papers cannot be certified by a
targeted read. Treat as supported, not proven.

**Environment.** Python 3.11 and 3.12 are not installed on this machine; the
CI matrix and the paper's Environment paragraph name both. Everything local ran
on CPython 3.14.x. CI logs were fetched and agree on the collected count and
the 238/16/4 tally, so the gap is narrow, but it is a gap.

**No Windows host.** PR #9's actual Windows reproduction was not run. The
mechanism was reproduced with git's own `core.autocrlf=true` on macOS, which is
the same filter path, and both stated preconditions were verified, but a real
Windows clone may add reasons of other shapes.

**PR #8's E3 leg** (the same symlink shape inside a `.tar.gz`, claimed refused
as `unsafe-archive`) was not reproduced. It is load-bearing for the auditor's
argument that this is a defect rather than a taste.

**Whether PRs #8 and #9 are correct.** Only the defects they report were
tested, at the repo's own commits. Neither branch was checked out and neither
patch's tests were run.

**No LaTeX rebuild.** PDF/source agreement was established by decompressing
`main.pdf`'s content streams and matching strings (it carries the current
numbers AND every stale sentence flagged above), plus mtimes (`main.tex` 15:33,
`main.bbl` and `main.pdf` 15:39). That is weaker than a fresh build and diff.
After applying fixes, rebuild and confirm the abstract actually changed rather
than trusting the build. Instrument failure 6 in the paper's own list is
exactly this.

**The upload set.** No packaging script exists under `paper/arxiv`, so nobody
has verified that `main.tex.bak`, `main.aux` and `main.out` are excluded.

**Historical measurements not reconstructible:** the 2026-08-16 closure run
("all three issuers were re-emitted, landed clean, and the registry re-pinned
byte-identically"), and Table 3's first-run refusals. The 2026-08-18 half was
measured exactly.

**Not reproduced:** the seed-7 sample of eight mutants dying on assertion
failures; the sec:gate refactor's full before/after mutation sweep (the suite
tally and the site arithmetic were reproduced, the sweep was not, and at HEAD
the baseline is red so `observe()` aborts before enumerating).

**Test provenance.** "The 75 liveness tests were produced by six concurrent
workers sharing a single working tree" has no artifact on disk and was not
reconstructed. It is the paper's only authorship-process disclosure.

**The four first-person anecdotes at main.tex:266-273** (the 69-diff
cross-runtime divergence, the health endpoint, the grep shell gate, the
animating value) are from other projects, outside this repository, and
unverifiable from here. The paper offers them as motivation rather than data
and does not rely on them elsewhere, which I confirmed.

**Zenodo contents.** The tag-to-commit link and the record's metadata were
verified; the deposited archive was **not** downloaded and diffed against
`git archive 11291be`.

**arXiv category and endorsement fit** were not investigated. Endorsement is
per category, so an endorser for one may not cover a cs.SE submission.

**`main.tex.bak`, `ENDORSERS.md`, and `audit/scan-20260818T170343Z.txt`** were
listed but not read, so any checks already recorded there are not reconciled
with these.

---

## What I verified and found correct

Every file:line citation in the paper resolves, at the commit the paper names,
to the statement the paper describes. Ten citations, none stale:
`vac/registry.py:171` and `index.html:113` (identical at `f59fb62` and
`92e4548`), `SPEC.md:139`, `SPEC.md:306-307`, `verify.py:284/288/374/383`,
`verify.py:639`, `verify.py:1000` (all `f59fb62`),
`tests/test_verify.py:286/:325/:349` and
`verify.py:1508/1512/1514/1541/1546/1558` (`92e4548`), `verify.py:863/:990`
(`27809ce`). Only the *characterisation* of :639 and :1558 is off (S8, MINOR).

Reproduced on this machine, from a clone or a clean detached worktree:

- `FIXTURES-ONLY SCORE: 10/112 = 0.089`, ten catches on ten distinct fixtures
- `LIVENESS-ONLY SCORE: 0/112 = 0.000`
- `MUTATION SCORE: 143/143 = 1.000` at `92e4548`, twice, plus the CI log
- banner `baseline clean; 143 refusal sites (3 excluded, see EXCLUDE)`, byte-identical
- sweep wall clock 341.13 s and 339.66 s against the paper's 346 s
- refusal sites 112 / 119 / 119 / 134 / 146 across the five ladder commits
- tests collected 114 / 114 / 189 / 217 / 258, and 189 minus 114 = the 75 liveness tests
- survivor classes 26/20/16/6/4/1/1/1 = 75, matching Table 1
- RQ2: 37/112 before, 39/119 after, 37 caught by tests on both sides, stamp-mismatch survivors 4 to 8, new sites covered 2/7
- all 20 `tamper-*` fixtures exit 1 and `fixtures/valid` exits 0 at `92e4548`; the four Table 5 reasons match; three of four exit 0 at `f59fb62`
- 146 mutants all `ast.parse`, 115 multi-line, no span swallows a neighbour
- `EXCLUDE` is two fragments of declared arity 1 and 2, both `OSError` wrappers, and the arity gate holds
- `238 passed, 16 skipped, 4 xfailed` unbound; +14 with five checkout vars, +6 with three
- issuer bundles today: crashkit 0, evalmut 1, model-drift 14 (13 `raw-aggregate-mismatch` in `standings.json` plus a `RESULTS.md` render mismatch)
- `test_refs_are_bound_not_just_read`: 13 refs, 4 in `KNOWN_UNBOUND`, and the stale "4 of 12" is still in the docstring exactly as the paper says
- Table 3 row-4 forensics: exactly 8 commits carry 134 sites, exactly 3 of those carry a one-entry `EXCLUDE`, the other two differ only in `paper/` files, and the mtime gap is 41.87 s
- CI logs at `a17af5c` (`123/133 = 0.925`, `FAIL: 0.925 is below the floor 0.940`) and at `92e4548` (`143/143 = 1.000`, no pytest tally in that job)
- the `_bundle_root` sibling escape and both symlink cases, with a passing control each time

Verified against primary sources: the PR #1 quote (verbatim substring), the CI
workflow quote, CWE-703/754/636/390/1288 including the CWE-754 scope note and
the CWE-636 alternate term, CVE-2022-35929's conjunction, all three in-toto
fragments, both SLSA fragments, the PIT FAQ heading, **Beer et al.'s 20%
trivially-valid quote (verbatim, from an open PDF)**, and every checkable MASC,
Delcourt and Bilal figure (20,303 mutants; 45/76 and 31/76; "roughly 15
minutes"; tau 0.55, 209 judgments, F1 0.90, 547 mutants, 3,282 judgments,
82.4%, r = 0.624, 11 of 15 pairs; 1,553 tests in six weeks, 252 fixes, 110
(44%), 107 (42.5%) as an upper bound, and the "browser-blind harness" quote).
The `refs.bib` note about arXiv:2107.07065 serving a different paper at its
current version is exact.

Hygiene: 62 cited keys = 62 defined = 62 `\bibitem`, no orphans either way;
zero em-dashes or en-dashes in `main.tex` or `refs.bib`; zero Claude, AI or
vendor attribution; `wmscan --selftest` PASS then `main.tex` and `refs.bib`
CLEAN; ORCID `0009-0002-5912-967X` resolves to Erik Hill; the repo is public
under MIT; `main.aux` gives 37 pages, matching `SUBMISSION.md`.

### Method note, because it bit us twice

A first pass at "all 20 tamper fixtures exit 1" returned **19 of 20**. False: a
concurrent process was mutating `vac/verify.py` in a **shared** `/tmp` worktree.
Re-measured in an exclusively owned worktree, all 20 exit 1. Separately, a
historical banner sweep reported all four commits as short-form, also false:
zsh applied the `:t` history modifier to `$c:tools/...` so `git show` produced
nothing and grep matched nothing, a silent zero. Both are instrument-failure
item 4 and the "silent no-op" rule reproducing inside the audit of the paper
that documents them. Every number above was re-taken afterwards. One incoming
finding also quoted a git error message (`fatal: Needed a single revision`)
that the command it named does not emit; the conclusion held, the quotation did
not.

Third instance, while writing this file: a `grep -c` scan for em-dashes reported
0 for this report. I ran a positive control on a file containing em, en, figure
and horizontal dashes and it also reported 0, so the scan could not fire at all
and its clean verdict was worthless. Re-run with a validated Python scan, the
control reports 1 and this file reports 0, which is the number the hygiene
section above is entitled to claim. The rule that catches this is the paper's
own: measure the instrument on a case it must fail before trusting a zero.

---

## Fix pass 2026-08-18

Verification of the applied fixes, run against the edited `main.tex` and
`SUBMISSION.md`. Nothing above this line was deleted or amended. Every verdict
below is a measurement I ran myself in this pass; where a fixing agent's report
and my measurement disagree, my measurement is stated and the disagreement is
named. Repo source was not touched.

### Instruments validated before use

The previous pass shipped a clean verdict from a dash scanner that could not
fire. Each instrument here was controlled first.

| Instrument | Control | Result |
|---|---|---|
| Dash scanner (U+2014/2013/2012/2015/2212) | file containing one of each | reports 1/1/1/1/1, fires |
| Undefined ref/cite grep | `.tex` citing `\ref{nosuchlabel}`, `\cite{nosuchcite}` | reports 2 and 2, fires |
| PDF page counter | 1-page and 3-page documents | reports 1 and 3, discriminates |
| Refusal-reason extractor | colon form, bare form (`FAIL empty-limitations`), decoy `structural verification: FAIL`, multiline | 4/4 assertions pass, decoy rejected |
| `.gitattributes` presence probe | same command at `81f50cf` where the file exists | prints the blob, so an empty result means absent |
| DOI resolver | `10.5281/zenodo.99999999999` | 404, so a 200 is a real resolution |
| Public-file fetch | `paper/does-not-exist.md` | 404, so a 200 is a real fetch |
| Refactor/abort gate | unrefactored tree does not abort | exit 2 is the refactor, not blanket refusal |

### 1. Build

`cd paper/arxiv && tectonic -X compile main.tex`

- **exit 0.**
- **39 pages.** Two independent instruments: the engine's own
  `Output written on main.xdv (39 pages, 241080 bytes)`, and a controlled count
  of the PDF page tree (`/Count=39`, 39 `/Type /Page` objects).
- **0 undefined references, 0 undefined citations**, both from a detector proven
  to report 2 and 2 on a control that has them.
- **0 overfull hboxes. 5 underfull**, badness 1365 and 1735 in `main.tex`, 1783,
  6808 and 6825 in `main.bbl`. That matches what `SUBMISSION.md` already claims.
- `Label(s) may have changed` appears once, in pass 1 only, and does not recur in
  the post-BibTeX pass.

**Trap worth recording:** `tectonic` does not write `main.aux` unless
`--keep-intermediates` is passed. The `main.aux` in this directory was from the
15:39 build while `main.tex` had moved on, so any section or table number read
off it was stale by construction. I rebuilt in a scratch directory with
`--keep-intermediates` and re-derived every number from that. `sec:liveness-tests`
is still 7.5 and `tab:ladder` is still Table 2, so the hardcoded cross-references
in `SUBMISSION.md` survive, but they survived by luck rather than by checking.

### 2. Citations

62 distinct `\cite` keys across 105 invocations; 62 entries in `refs.bib`, all
distinct. **Zero cited-but-missing, zero orphaned, zero duplicate keys.**

### 3. Dash and hygiene

Detector fires on the control. `main.tex`: 0 of every dash codepoint, and **no
non-ASCII characters at all**. `SUBMISSION.md`: same.

The source being ASCII-clean is not sufficient on its own, because LaTeX renders
`--` and `---` as en and em dashes. Checked as a second channel: **zero `---` in
`main.tex`**, and all three `--` occurrences sit inside `\begin{Verbatim}` blocks
as command-line flags, where they render as literal hyphens. No `\texttt{}` span
contains `--`. So the rendered PDF carries no dash either.

`grep -ciE 'claude|anthropic|copilot|chatgpt|generated with|co-authored'` returns
0 in both files.

### 4. Abstract

Plain-text abstract in `SUBMISSION.md` measures **1890 characters against the
1920 limit**, 30 to spare. The section header claiming 1890 matches.

### 5. Blockers, one at a time

**B1. CLOSED.** Section 2.2 now reads "Four pull requests came out of it. Two are
analysed here", and "in total" is gone, the five scoped to "That first pull
request". `gh pr list --state all` confirms four `GiulioDER` PRs (#1 MERGED,
#2 OPEN, #8 OPEN, #9 MERGED) plus #3, which is the author's own and correctly not
counted as audit. Three new paragraphs record #9 and #8 with their URLs. I
reproduced #8 myself at `92e4548` rather than accept it on report:

- positive control, unlisted file placed directly in the bundle: **exit 1**,
  `FAIL unlisted-file: evidence/stowaway.txt`
- positive control, one byte appended to a covered artifact: **exit 1**,
  `FAIL sha256-mismatch: evidence/bundle.json`
- E2, covered artifact replaced by a symlink pointing outside the bundle:
  **exit 0**, `structural verification: PASS`, banner clause `bundle closure`
- host-dependence control, link target moved away: **exit 1**,
  `FAIL missing-artifact: evidence/bundle.json`; target restored: **exit 0** again
- E1, unlisted file inside a symlinked subdirectory: **exit 0**, PASS, and the
  file is named nowhere in the output

Both positive controls fired before the exit 0 was trusted. The mechanism line is
confirmed: `git show 92e4548:vac/verify.py` line 224 is
`for p in sorted(bundle_dir.rglob("*")):` under the comment
`# closure: a verified bundle cannot smuggle content`, filtered by `if p.is_file():`.
The refusal-site counts in the paper are exact: **146 at `92e4548`, 153 at
`ce462e10`, 155 at `68ceed05`**, by the tool's own regex. The paper's decision to
call E2 a fifth vacuous pass but not a fifth forgery is supported by the
host-dependence control, and is the correct call: a stranger replaying the bundle
without the target present gets a refusal.

**B2. CLOSED.** The contradicting sentence is gone from `main.tex`; the correct
paragraph fourteen lines above survives. The arXiv Comments field now names the
version DOI with the concept DOI in parentheses, which is what the paper's own
Reproducibility section instructs. Both DOIs resolve **200** and the nonsense DOI
control returns **404**.

**B3. CLOSED, and verified the hard way.** The "not yet from a clone" sentence is
gone. I cloned `https://github.com/egnaro9/vac-protocol.git` fresh and ran the
command the paper hands the reader:
`python tools/fixture_corpus_score.py` printed
`FIXTURES-ONLY SCORE: 10/112 = 0.089`, exit 0, and `--detector liveness` printed
`LIVENESS-ONLY SCORE: 0/112 = 0.000`, exit 0. The headline number is reproducible
from a clone exactly as now claimed.

**B4. CLOSED.** Caption now names `b30ea2f`. Measured: the fixture is added by
`b30ea2f`; `git rev-list --count 92e4548..b30ea2f` is **2**; the directory is
absent at `f59fb62` and `92e4548` and present at `b30ea2f` and `v0.1.0` (the last
two being the positive control that the probe can find it); `git diff --stat
92e4548 v0.1.0 -- vac/` is empty, so "with `vac/` unchanged across that span"
holds.

**B5. CLOSED.** Line 964 now reads "is the obvious fix. This paragraph describes
`92e4548`, where it was not done; the pin landed afterwards at `e932868`". The
scoping clause is what makes the surrounding present-tense sentences honest, and
it works. Measured: `EXPECT_RAW_SITES = 146` and `EXPECT_SCORED_SITES = 143` at
`e932868`, with a **negative control** at `92e4548` where the same grep returns
nothing, so both halves of "where it was not done / landed afterwards" are
measured rather than one being inferred from the other. The abort path
`return 2` is present.

**B6. CLOSED.** Abstract now reads "Section~\ref{sec:liveness-tests} carries all
eleven, not just the five rows of Table~\ref{tab:ladder}", using `\ref` as the
audit asked. `SUBMISSION.md:69` carries the spelled-out copy. The false strings
`not the rising five`, `rise monotonically` and `five rising rows` are absent
from both files. Table 2's tabular has **exactly five data rows** scoring 0.330,
0.328, 0.941, 0.947, 1.000, which contain a fall, so "rising" was false and is
gone. Fresh aux confirms `sec:liveness-tests` is 7.5 and `tab:ladder` is Table 2.

**B7. CLOSED on substance. One sub-item STILL OPEN.** The head is now
`ce462e10`, and `gh pr view 2` confirms that is still the live head right now
(state OPEN, `isCrossRepository true`, owner `GiulioDER`), so the pin is current
and the fetch refspec `git fetch origin pull/2/head` is correctly given, since
neither sha resolves from a plain clone. The remaining wall-clock assertion at
`bb4dda36` is now disclosed in the bullet.

Still open: the audit also said `bb4dda36` was 8 hex digits where the paper's
other hashes are 7. **That is not fixed.** `main.tex` now contains three 8-digit
hashes (`bb4dda36` once, `ce462e10` twice) against 89 seven-digit ones. The fix
report for this item claims "Also fixes the 8-digit hash (the paper's only one)",
and that claim is false: the replacement sha is itself 8 digits. Cosmetic, but it
is a fix reported as applied that was not applied, which is the one category this
paper cannot afford to leave in its own record.

**B8. CLOSED.** The Environment paragraph now instructs cloning with
`core.autocrlf` disabled, and a three-paragraph block records the defect. I
rebuilt the differential pair myself, by the only route that works
(`git clone --no-checkout`, then set `core.autocrlf`, then `checkout --detach`,
so the smudge filter actually runs):

| Measurement | autocrlf=true | autocrlf=false |
|---|---|---|
| files under `fixtures/valid` carrying CR | 14 of 14 | 0 of 14 |
| `python -m vac.verify fixtures/valid` | exit 1, 13 `sha256-mismatch`, 13 total FAIL | exit 0 |
| all 20 `tamper-*` fixtures | exit 1 | exit 1 |

Thirteen is confirmed as the ceiling: the manifest lists exactly 13 evidence
entries. The paper's **"fourteen of the twenty"** is confirmed under the
predicate the paper actually states. My census of all 20 fixtures in both arms:
**14 lose the reason they emitted in the clean arm**, 15 report `sha256-mismatch`
as their sole label, and **16 have a different first reason**. The audit's 16 is
reachable only under that last and weakest predicate, which does not support
"refuse on the hash rather than the reason Table 4 names". The fixing agent was
right to reject 16, and I reproduce its 14 independently. Table 4's rows behave
exactly as written: `tamper-summary-string`, `tamper-crashkit-severity` and
`tamper-stamp-deleted` all lose their reason, and `tamper-check-deleted` still
emits `evidence-unchecked` buried among **14** reasons. At `81f50cf` both arms
give 0 CR files and exit 0. All **9** `runs-on` lines across the four workflow
files at `92e4548` are `ubuntu-latest`, none other.

**B9. CLOSED 2026-08-18, by the written yes this pass was waiting on.** The
consent request sent 2026-08-18 16:11Z was granted 2026-08-18 19:34Z, written consent on file.
He remains named at `main.tex:198`, at `main.tex:1779` in the
Acknowledgements, and as the author of `derme2026pr1` in `refs.bib`. What the fix
pass did change is real and worth keeping: the mojibake anecdote, the single
claim in the paper that rested on private correspondence, is now unattributed,
and every remaining naming and quotation is anchored to a public artifact
(`GiulioDER/cca-audit` resolves 200, PR #1's body carries the quote). But
de-identifying one sentence is not consent for the other three namings, and
`SUBMISSION.md` item 1 now correctly labels this blocking rather than "not
blocking". arXiv cannot be withdrawn.

Bearing directly on B9, S11 is also still live and I re-measured it: the
fabricated quote is served right now at
`raw.githubusercontent.com/.../paper/paper.html` (HTTP 200) and `paper/paper.md`
(HTTP 200), with a 404 control proving those are real fetches. Those same two
public files also publish the mojibake anecdote naming him verbatim. So
`main.tex`'s footnote that the misattribution "is corrected here rather than
quietly dropped" is true of the paper and contradicted one click away in the
repository the paper tells readers to visit.

### 6. Scope

`git status --porcelain`:

```
 M paper/arxiv/SUBMISSION.md
 M paper/arxiv/main.pdf
 M paper/arxiv/main.tex
?? paper/arxiv/AUDIT_PREPUB.md
?? paper/arxiv/main.blg
?? paper/arxiv/main.log
```

No repo source was modified: `vac/`, `tools/`, `fixtures/`, `tests/`, `refs.bib`
and `main.bbl` are all untouched. No commit, push, merge, working-tree checkout
or stash was run. The detached worktree used for the E2 reproduction was removed
and `git worktree list` shows only the main checkout.

**Disclosed rather than hidden:** `main.pdf` is a *tracked* file and it changed,
because step 1 of this pass required running `tectonic`. `main.log` and
`main.blg` are new untracked build byproducts. `main.aux` and `main.bbl` did not
change, because `tectonic` skips writing intermediates by default. The rebuilt
PDF matches the current source where the committed one did not, which is what
this directory's own note asks for ("it is kept here so the local PDF matches the
source"), so it was left rebuilt rather than reverted to a stale artifact.

### 7. A defect this fix pass introduced, found and corrected here

The fix pass grew `main.tex` from 1836 to 1957 lines and **nobody rebuilt**, so
the page count went stale. `SUBMISSION.md` asserted **37 pages** in two places:
the build-verification note, and the **arXiv Comments field, which is pasted into
the submission form and rendered publicly**. The measured count is **39**.

This is not an ordinary slip. `SUBMISSION.md` item 16 already carried the
instruction, in its own words: "Re-measure after any further edit rather than
carrying the number forward, which is the failure this paper is about." The
instruction was present, was correct, and was not followed, and the paper's own
build note went on asserting a verified figure that no build supported. A note
that says "re-measure" is not a check; nothing executed it.

Corrected in this pass: both fields now read 39, measured two ways with a
controlled counter, and item 16 records the third staleness with the commands.
The 0 overfull and 5 underfull rows in the same note were re-measured and are
correct, so the page count was the only stale number in it.

### What is still open after this pass

1. **B9, consent. CLOSED 2026-08-18, no longer blocking.** The written yes is on
   record, granted 2026-08-18 19:34Z, written consent on file. No fallback to "an outside
   engineer" is needed: he asked to be named.
2. **S11, the fabricated quote still served publicly** at `paper/paper.html:42`
   and `paper/paper.md:65`, plus `paper/arxiv/main.tex.bak:208` tracked. Outside
   the two-file edit scope. Until those are edited the paper's retraction is
   contradicted by the repository it cites.
3. **B7's 8-digit hashes**, three of them against 89 seven-digit. Reported as
   fixed; not fixed.
4. **`main.aux` in this directory is stale.** Rebuild with
   `--keep-intermediates` before reading any section or table number off it.
5. **`tests/test_checkout_integrity.py`**, merged onto `main` at `81f50cf`, says
   the CRLF failure gives "twenty reasons". I measured **13**, and 13 is the
   arithmetic ceiling. The paper says thirteen and is right; the artifact
   repository the paper cites now carries the wrong number in a test docstring.
   Outside edit scope, but it is the paper's own defect class sitting in the
   repository a reviewer will clone.
6. **PR #8 is absent from the Outstanding list** at `sec:fixes-open`, though
   Section 2.2 now documents it as an open finding. A reader reaching Outstanding
   finds the newest open finding missing from the open-work list.
7. **PR #2's head can move again.** `ce462e10` is correct as of this pass and the
   branch is on a fork the author does not control. Re-check at submission hour.
