# arXiv submission sheet

Prepared 2026-08-18 against `main.tex` and `refs.bib` in this directory.
Everything below is copy-paste ready except where marked **DECIDE**.

---

## 1. Files to upload

Upload exactly three files, flat (no directories):

```
main.tex
main.bbl
refs.bib
```

`main.bbl` is built and current. arXiv uses a `.bbl` when present and otherwise
auto-detects a bib compiler; `refs.bib` is included so either path works. The
`.bbl` basename must stay `main` to match `main.tex`.

**Do not include `audit/`.** It holds a local pre-publication scan log, not part
of the paper. `main.pdf` is also not uploaded (arXiv builds its own), though it
is kept here so the local PDF matches the source.

Build verified with `tectonic -X compile main.tex`: no errors, no undefined
references, no undefined citations, zero overfull hboxes, 39 pages, 4 tables.
Five underfull (loose) lines remain, which is the deliberate trade: `microtype`,
`hyphenat` and a 3em `\emergencystretch` were added so that unbreakable `\texttt`
tokens stretch a line rather than run into the right margin, where nine of them
previously did, the worst by 52.3pt.

---

## 2. Title

```
Four Ways to Forge a Bundle My Own Verifier Calls Clean: Refusal-Site Mutation Testing of an Evidence-Bundle Verifier
```

The LaTeX title uses `\\` and `\large` for the subtitle; neither survives into
metadata, so the colon form above is what goes in the title field.

## 3. Authors

```
Erik Hill
```

arXiv wants `Firstname Lastname`, no honorifics, affiliations in parentheses.
"Independent Researcher" is a status rather than an institution, so the bare name
is the conventional entry. See **DECIDE 11**.

- ORCID to attach to the submission: `0009-0002-5912-967X`
- Contact email: `erik@erikhill.dev`

Both already appear in the paper's author block.

## 4. Abstract (plain text, 1890 characters, limit 1920)

No LaTeX macros. Section cross-references are spelled out as numbers, matching
the compiled document.

```
I built a protocol whose premise is that a stranger can re-run my claims offline and get the same answer. An outside engineer audited it and broke it: a bundle whose headline numbers were false verified clean, the cheapest forgery four bytes. I merged his fix, then pointed my own instruments at the fixed verifier and found the same defect four more times, in places his audit did not reach. The cheapest is one capital letter.

The unifying defect is not cryptographic or exotic: a check that reports success along a path where it never examined anything. Vacuous pass is a working label, not a discovery; Section 4 names the literatures already occupying it.

So I stopped collecting anecdotes and measured. At f59fb62, under the extraction rule of Section 6, the verifier exposes 112 refusal sites; 75 could be deleted with the whole suite and every tamper fixture still green, a score of 0.330. Three of the four hand-found forgeries fall in surviving classes; the fourth is an obligation with no refusal site. Scored alone, the sixteen-fixture corpus built to prove the verifier can refuse catches 10. Testing the refusals themselves took it to 0.941, then to 1.000 at 92e4548 over a grown population of 146 sites; those denominators differ and the series between them is non-monotone, so Section 7.5 carries all eleven, not just the five rows of Table 2. Fixing the four found defects instead moved 37/112 to 39/119, leaving the pre-existing sites at 37.

Seven times during this study my own measuring tools reported success while measuring nothing; four were built to detect this class, and one returned a perfect 1.000.

Every number here is self-measured on a system I wrote, over a registry that is a closed loop of my own repositories; the one external data point is the audit of Section 2.2. That is stated here rather than buried: it is the paper's credibility, not a caveat.
```

The paper's own abstract was shortened to this text, so the two match in
substance and wording. Do not edit one without the other.

## 5. Primary category

```
cs.SE  (Software Engineering)
```

Justification, one line: the paper defines a mutation operator with a kill
predicate, exclusion set and validity gate, answers four research questions with
measured before-and-after data on a real test suite, and carries a
threats-to-validity section and an artifact section, which is a software-testing
contribution first and everything else second.

## 6. Cross-list categories

```
cs.CR  (Cryptography and Security)
```

Justification: the subject is an attestation-style evidence verifier, the paper
is framed on RFC 9334, in-toto, SLSA and Sigstore, it cites five CWE classes, and
its closest external corroboration is CVE-2022-35929 in cosign.

Nothing else is warranted. cs.LG / cs.CL would be a stretch: evaluation bundles
appear as the subject matter, not as a machine-learning result.

## 7. Comments field

```
39 pages, 4 tables. Case study with source artifacts: verifier, specification, mutation sweep, fixture corpus, registry and archived sweep outputs at https://github.com/egnaro9/vac-protocol (MIT). All figures pinned to commit hashes; release v0.1.0 archived at doi:10.5281/zenodo.22000912 (concept DOI 10.5281/zenodo.22000911).
```

## 8. License

Recommended: **CC BY 4.0**.

Reasons: the artifact repository is already MIT, the paper's value is in being
re-run and argued with, and CC BY is the least restrictive option that still
requires attribution. CC0 gives up attribution for no gain here. The arXiv
non-exclusive licence is the fallback if you want to keep options open for a
venue that objects to CC BY, but few software-engineering venues do.

---

## DECISIONS TO SIGN OFF BEFORE SUBMITTING

These are places where I made an editorial call that is yours to confirm. Items
1 through 4 are the ones I would not submit without reading.

1. **Giulio D'Erme is no longer credited with a sentence he did not write.**
   The draft attributed to him: "documentation that refutes an auditor is rarer
   than the bugs." He did not write that. What he wrote, in the PR #1 body, is
   "four findings refuted by documentation rather than by argument is not the
   usual experience reading someone's spec." Section 2.2 now quotes him verbatim
   with quotation marks and carries a footnote saying the compressed version was
   mine and the misattribution is corrected. **Confirm the quotation is accurate
   and that he is willing to be named and quoted in a public arXiv posting.**
   He is also named in the Acknowledgements. This is the paper's single external
   data point, so a misattributed quote here is the one error a reviewer would
   treat as disqualifying.

   **STATUS, updated 2026-08-21: consent IS on record and this item is closed.**
   Requested 2026-08-18 16:11Z, granted 2026-08-18 19:34Z, written consent on file: he asked
   to be named and cited as Giulio D'Erme, in the wording already in the paper,
   and declined co-authorship. Four corrections from the same
   reply are in at `81dfc7a`. Every naming and every quotation in Section 2 is also
   anchored to a public artifact: the `cca-audit` repository
   (`curl -o /dev/null -w '%{http_code}' https://api.github.com/repos/GiulioDER/cca-audit`
   returns 200, a nonexistent-repo control returns 404); pull requests #1, #2, #8
   and #9 on `egnaro9/vac-protocol` (`gh pr list --repo egnaro9/vac-protocol
   --state all --json number,author,state` shows all four filed by `GiulioDER`,
   #1 and #9 merged, #2 and #8 open); and the quoted sentence, which is verbatim
   from the public #1 body. The one sentence that rested on private
   correspondence, the mojibake anecdote at Section 2, is now unattributed and
   says so. **What still needs his yes is being named in the Acknowledgements and
   in Section 2.** An arXiv posting is permanent and cannot be withdrawn, so this
   is blocking, not "when convenient". If the reply does not arrive in time, the
   paper still works with the name replaced by "an outside engineer" everywhere
   except the pull-request URLs and the `derme2026pr1` citation, which are public
   record either way.

   **Second, and outside the two files this pass could edit: the retracted quote
   is still live on the public branch.** `git grep "documentation that refutes an
   auditor" origin/main` returns it, still presented as "his remark", in
   `paper/paper.html:42`, `paper/paper.md:65` and `paper/arxiv/main.tex.bak:208`.
   It is being served: `curl https://raw.githubusercontent.com/egnaro9/vac-protocol/main/paper/paper.html`
   returns HTTP 200 carrying the sentence at line 42, and `.../paper/paper.md`
   carries it at line 65 (a nonexistent path under the same prefix returns 404, so
   the fetch is real). `main.tex`'s footnote says the misattribution "is corrected
   here rather than quietly dropped", which is true of the paper and false of the
   repository the paper sends readers to. **Fix those three files before posting**,
   or the correction the paper makes is contradicted one click away.

   One fact bearing on the consent question, measured in the same fetch: the same
   two public files already publish the mojibake anecdote naming him, verbatim
   ("my `RESULTS.md` byte-identity check caught mojibake in his own audit output
   mid-review", `paper/paper.html:42` and `paper/paper.md:66`). That makes the
   arXiv posting a request to make an existing disclosure permanent rather than a
   first disclosure. It does not answer the question, and it is not a reason to
   post before he replies.

2. **The headline "the fixture corpus caught zero" is now stated as an
   entailment, and a new measurement replaces it.** At `f59fb62` every one of the
   16 fixtures is asserted by exact verdict and exit code in `TAMPERS`, and the
   sweep's `observe()` short-circuits on the unit suite first, so the fixture
   disjunct is unreachable whenever the suite passes. The zero was arithmetic,
   not a discovery, and presenting it as a discovery would have been the paper
   committing its own subject. I re-ran the same 112 mutants at `f59fb62` with
   the unit-suite disjunct removed: **10 caught of 112, score 0.089.** The
   conclusion is re-anchored on 0.089. **Confirm you are willing to lead with
   0.089 instead of 0.** I think it is the stronger paper: 0 invited the reply
   "that is just how your sweep is ordered", and 0.089 does not.

3. **RESOLVED 2026-08-18.** The 0.089 is now reproducible from a clone:
   `tools/fixture_corpus_score.py` at `e932868`, and
   `fixtures/attack-crashkit-severity` at `b30ea2f`. Original note kept below.

   **That 0.089 was the one number in the paper a reader could not reproduce from
   the repository.** I could not commit the standalone-detector mode, since my brief
   was the `paper/arxiv` directory only. The paper says so explicitly in
   Reproducibility and adds a bullet to Outstanding. **Either add a
   `--detector` mode to `tools/mutation_sweep.py` before you submit, or accept
   shipping one self-flagged unreproducible figure.** I would add the flag: it is
   maybe twenty lines, and the paper's whole ethic is against the alternative.

4. **Table 4's reproduction promise was false for one of four rows, and the
   caption now says so.** `fixtures/tamper-crashkit-severity` re-cases three
   severities but leaves `vulnerability_score` declared at the honest 0.4545, so
   at `f59fb62` it exits 1 with `raw-aggregate-mismatch`, not 0. A reader running
   the promised one command would have read that as a refutation. I verified the
   Section 5.3 forgery is real by completing it (three declared values to 0.0,
   `evidence/eval_run.json` re-pinned honestly): it then exits 0 at `f59fb62` and
   exits 1 at `92e4548` with `artifact-unparsable`. **Better fix than the caption:
   commit the completed attack as `fixtures/attack-crashkit-severity` and restore
   the clean four-row promise.** Repo change, so not mine to make.

5. **Table 2's fourth row is now pinned to `1674f4c`, 217 tests.** The old caption
   said the commit was unrecoverable. It was recoverable: eight commits carry 134
   refusal sites, only three of those carry a one-line exclusion set and can
   produce the denominator 133, and `a17af5c` is ruled out by its own 123/133 in
   Section 7.7; of the remaining two, `1674f4c` introduced the archived sweep file
   and `34c03f6` differs from it only in paper files. I measured 217 tests
   collected at `1674f4c`. Confirm you are happy pinning by derivation rather than
   by a note kept at the time; the caption states the derivation so a reader can
   check it.

6. **The RQ3 result is now explicitly labelled partly circular.** A new paragraph
   says the +0.611 is mostly entailed, because the intervention is defined in the
   metric's own units: a test asserting a site's exact failure list must fail when
   that site is deleted. The aphorism ("the defects you find are a sample; the
   gates you own are the population") is kept, with "and partly true by
   construction" appended. **I rejected the reviewer's advice to delete the
   aphorism.** It is a real heuristic, the paper already hedges it, and the
   section's non-entailed content (reachability, and the CI floor later catching
   an untested comparator) is now stated separately. If you disagree, the
   paragraph to cut is "How much of the +0.611 is entailed."

7. **The RQ2 null result got sharper, not softer.** The old text hedged that
   "much of" the -0.002 was denominator growth. All of it is: the unit suite
   caught 37 before and 37 after, the two extra catches are both on newly added
   sites, and the pre-existing 112 score 37/112 both times. The paper now says the
   effect on the pre-existing population is exactly zero, and that the seven new
   guards were covered at 2/7. Decimal deltas are quoted as fractions throughout,
   with one parenthetical noting that -0.002 is the difference of the rounded
   scores and -0.003 the rounded difference.

8. **Table 2's five rows are now accompanied by the eleven-value record they
   smooth.** Twelve archived sweeps, two of which record the same 39/119, so
   eleven values, and they are non-monotone: 0.330, 0.328,
   0.941, 0.957, 0.960, 0.953, 0.947, 0.992, 1.000, 0.972, 1.000. All four falls
   are denominator growth with a non-decreasing numerator. I added this because
   omitting a datum that weakens the impression of a durable fix is the one
   presentation choice this paper cannot afford, and because it argues for the
   paper's own recommendation (a standing CI floor, not a one-time measurement).
   **Confirm you want the sawtooth in.**

9. **Instrument failure 7 cited the wrong job's output, and the paper now says
   so.** The `238 passed, 16 skipped, 4 xfailed` line comes from `test (3.11)` and
   `test (3.12)`, which never check out the issuers; the `refusal-coverage` job
   emits no pytest tally at all. The underlying defect is confirmed by path
   arithmetic (`_issuers/<repo>/vac` plus a consumer-appended `/vac`; no
   `<repo>/vac/vac` exists in any of the three issuers). I logged the miscitation
   as an eighth entry in that list rather than repairing it silently. **Confirm
   you want it visible.** Quietly fixing it would have been defensible and I chose
   the other way on the grounds that this paper's subject makes the choice.

10. **Four smaller factual corrections, all verified:**
    - The cosign claim dropped a necessary condition. The advisory requires both
      "at least one attestation with a valid signature" and "no attestations of
      the type being verified". Fixed, and "precisely the finding" softened to
      "the same shape as", with the mechanism difference stated.
    - `refs.bib` said `verify-attestaton`. Fixed, and `{\tt}` replaced with
      `\texttt`. Severity was given as "High"; three sources disagree (advisory
      says Moderate, GitHub CNA 7.1 High, NVD 9.8 Critical), so the prose no
      longer asserts a severity and the bib note records all three.
    - "In every case the unchecked artifact was the human-readable one" was false
      for one of four: crashkit's `variance_flaky_n10.report.json` is JSON. The
      class is restated as artifacts produced as reports rather than consumed as a
      check's input, and the crashkit row is named as the case that forced the
      wording.
    - The "land the robustness pull request" bullet was stale. PR #2 head
      `ce462e10`, verified against GitHub on 2026-08-18, already builds the
      deep-nesting fixtures in Python and makes both traversals iterative, so the
      stated blocker is met by the PR itself. Bullet rewritten; the staleness is
      noted in place as instrument failure 4 recurring. The head then went stale a
      second time: `bb4dda36`, the sha an earlier pass named, still asserted a
      wall-clock bound on elapsed time, an instance of the very host-dependence
      class the branch exists to remove. `ce462e10` drops that assertion and leaves
      `vac/` byte-identical, so the bullet now names a dated head, and notes that
      the branch is on a fork and resolves only via `git fetch origin pull/2/head`.

11. **`\ref{sec:artifacts}` resolved to Section 14, the Conclusion.** A `\label`
    after a starred section silently inherits the previous counter. Replaced with
    prose naming the section, plus a one-clause aside that this is the paper's own
    subject in typesetting form. **Cut the aside if it reads as too cute.**

12. **Two claims I declined to add.** A reviewer offered that sampled mutant kills
    are assertion failures rather than crashes; I could verify it only on CPython
    3.14 with one pre-existing failure deselected, not on the project's 3.11 and
    3.12, so the paper says exactly that and no more. A reviewer also proposed
    changing `observe()` to evaluate all three detectors instead of
    short-circuiting; I rejected it as a code change (first-detector-wins is right
    for a CI gate) and fixed the reporting instead.

13. **Author-metadata form.** I recommend the bare name. If you would rather show
    status, arXiv's format would be `Erik Hill (Independent Researcher)`. Your
    call.

14. **Endorsement status is unmeasured.** No arXiv presubmit or upload has been run,
    and the submission flow has not reached the category-specific authorization
    check: draft `submit/7963507` is parked at the Submittal Agreement.
    `erik@erikhill.dev` is a personal-domain address, and linking an ORCID does
    not by itself establish cs.SE authorization. arXiv states that new users, or
    authors submitting to a category they have not published in, **may** need an
    endorsement, and that its endorsement mechanisms are category-specific
    (info.arxiv.org/help/endorsement.html). Proceed through the agreement and
    select `cs.SE` to learn whether a request is required. Do not upload until
    the metadata and reproducibility items above are ready. **Do not state or
    imply approval before arXiv has evaluated the category selection.**

15. **RESOLVED 2026-08-18. New repository work this paper promised.** Three items
    were added to Outstanding and all three have since landed: commit the
    standalone-detector mode (item 3 above, `e932868`), pin the refusal-site
    population so a merging refactor aborts the sweep instead of shrinking the
    denominator (`e932868`), and (my suggestion, not in the paper) commit the
    completed severity attack as a fixture (`b30ea2f`). All three are on
    `origin/main` and inside the archived `v0.1.0`. The denominator
    point is demonstrated in the paper: moving four `stamp-mismatch` refusals into
    a one-line helper leaves the suite byte-identical, does not trip the exclusion
    arity check, and moves the denominator from 143 to 140. `--floor 0.99` is a
    floor on the ratio and would not notice; the population gate does, and this was
    checked by performing that refactor rather than by reading the constant. It
    aborts with exit 2, reporting 143 raw sites and 140 scored against the declared
    146 and 143.

16. **The novelty claim was narrowed, and this is the item to read before you sign
    anything.** Three papers were found that occupy ground an earlier draft was
    implicitly claiming. Section 4.5, "Three close neighbours", is new and names
    them. **What the paper now claims as unclaimed is two things, not three: the
    site selection and the subject.** The two-detector kill predicate was demoted
    out of the residue.

    What each neighbour takes:

    - **MASC** (Ami et al., IEEE S&P 2022, and the FSE 2023 tool paper). 20,303
      mutants against nine crypto-detectors. Grading a checker by mutation is
      theirs at a scale mine does not approach, its first operator is the
      lowercase-`"des"` evasion that my one-capital-letter forgery re-derives, and
      its motivating premise is the published form of my structural ceiling. Its
      Step 6 attributes 45 of 76 flaws to mutation against only 31 of 76 findable
      from literal base instantiations, which is the same shape of result as my
      10/112, from the other side of the pipeline. This paper was cited nowhere in
      the earlier draft while muSE, by the same group, already was. That was an
      oversight, and the paper now says so in its own voice.
    - **Delcourt et al.** (MODELS 2026, arXiv 14 Aug 2026). Mutation testing of
      LLM-as-judge, 547 mutants and 3,282 judgments. Reading per-operator survivors
      as blind spots, and warning that easy mutants inflate the aggregate, are both
      moves this paper makes. Four days ahead of this draft's date line.
    - **Bilal and Mughal** (arXiv 21 June 2026, submitted to IEEE Software). A
      1,553-test suite that stayed green and kept shipping defects, 110 of 252
      fixes at four unobserved seams. Their browser-blind-guard incident is an
      external instance of my RQ2 null result, on a system I did not write, two
      months earlier.

    **What survives, and why I still think it is worth posting.** None of the three
    modifies a line of the checker's own source: two mutate the checker's input and
    the third injects nothing. The refusal-site denominator and the checker's own
    acceptance logic as subject remain unoccupied as far as I can establish. The
    seven instrument failures have no counterpart in any of the three.

    **Three claims I deliberately did not make, having checked them and found them
    unsafe:**
    1. That an *exact* kill predicate is novel. It is the default in conventional
       mutation testing; it looks distinctive here only against two comparators
       that could not have had it. Section 4.8 now says this outright.
    2. That the 10/112 separately-scored corpus result is unshared. MASC's Step 6
       is the counterpart, and the paper names it rather than waiting for a
       reviewer to.
    3. That "pointing a mutation tool at a checker" is a new place to point it in
       any general sense. It is not, and the paper concedes the purpose and the
       reading while keeping only the site.

    **The framing sentence, added once, in Section 4.8:** "Read strictly, then,
    this is a case study carrying a specialised instrument rather than a new
    method." **This is the sentence to accept or reject.** It costs the paper its
    method-contribution framing and buys the reviewer having nothing left to catch
    the paper doing. Given the subject, I judged the trade worth it, but the call
    is yours and reversing it means reversing Sections 4.5, 4.8, contribution 2
    and scope item 2 together.

    Contribution and scope lists both went from five items to six: the separately
    scored 10/112 detector result is now its own item rather than a clause inside
    the instrument item.

    **The page count in this sheet was stale before I touched it, and is now
    corrected twice over.** Section 7's Comments field and the build note both said
    32 pages. I rebuilt the reconstructed pre-edit sources and measured **33**, so
    the sheet was already one page behind. The new related-work material costs
    **four** pages: 33 to 37. Re-measure after any further
    edit rather than carrying the number forward, which is the failure this paper
    is about.

    **It then went stale a third time, and the warning above is why that is worth
    recording.** The 2026-08-18 fix pass took `main.tex` from 1836
    lines to 1957 (`git diff --stat HEAD`: 225 changed lines), the two largest
    additions being a 45-line block in Section 2.2 and a 35-line block in the
    unnumbered Reproducibility section, and nothing was rebuilt, so both fields
    still read 37 against a manuscript that had grown to **39**. Both now read 39, measured two
    ways on 2026-08-18 after `tectonic -X compile main.tex`: the engine's own
    `Output written on main.xdv (39 pages, 241080 bytes)` in `main.log`, and an
    independent count of the PDF page tree, that counter first controlled against a
    one-page and a three-page document so it was known to discriminate. The same
    build reports 0 overfull and 5 underfull boxes, which is what the build note
    above already claims, so the page count was the only stale number in it. Note
    that `tectonic` does not write `main.aux` unless `--keep-intermediates` is
    passed: the copy in this directory is older than `main.tex`, so any section or
    table number read off it must be re-derived from a fresh build, not trusted.

17. **One citation was left without a DOI on purpose.** `delcourt2026judge` prints
    `10.1145/3822455.3838768` in its own HTML front matter, while its arXiv record
    gives `10.1145/3822455.3830329`. Neither resolves; Crossref returns 404 for
    both, and no MODELS 2026 item is registered yet. Publishing either as fact, in
    this paper, would be the paper's own subject in bibliography form. The entry
    cites the arXiv abstract page and says the DOI is unregistered and disputed.
    **Re-check before submission if MODELS 2026 registers by then.**

---

## Verification record for this pass

Measured, not asserted:

| Check | Result |
| --- | --- |
| em-dash (U+2014) in `main.tex` / `refs.bib` | 0 / 0 |
| en-dash (U+2013) in `main.tex` / `refs.bib` | 0 / 0 |
| any non-ASCII byte | 0 in both files |
| `\cite` keys resolving in `refs.bib` | 62 of 62 (was 58 of 58 before this pass; the earlier record's 57 was stale) |
| orphaned `refs.bib` entries | 0 |
| `\ref` targets with no `\label` | 0 |
| undefined references or citations at compile | 0 |
| overfull hboxes in `main.tex` | 0 (was 9, worst 52.3pt into the margin) |
| underfull hboxes | 2 in `main.tex` (badness 1365, 1735), 3 in `main.bbl` |
| `TODO` / `TK` / `XXX` / `FIXME` / placeholder | 0 in both files |
| author block ORCID | `0009-0002-5912-967X` present |
| author block email | `erik@erikhill.dev` present |
| third-party tool or assistant attribution | 0 in source, 0 in PDF metadata |
| PDF metadata Producer / Creator | `xdvipdfmx`, `LaTeX with hyperref` |
| abstract length, plain text | 1872 chars against a 1920 limit, 48 to spare. Counted on the exact string in section 4 of this sheet, which is the string to paste. |

The three "agent" mentions in `main.tex` are the paper's own internal-validity
disclosure that the 75 liveness tests were produced by six concurrent agents.
That is a threats-to-validity statement in the author's voice, not a byline, and
removing it would weaken the paper.

---

## Audit record in Section 2, re-measured 2026-08-18

Section 2 previously said the auditor "filed two pull requests" and scoped five
forgery paths as a total. Both are now corrected, and the two later pull requests
are recorded at the end of that section. Measurements behind the new text:

| Claim in Section 2 | Command | Result |
| --- | --- | --- |
| Four pull requests, not two | `gh pr list --repo egnaro9/vac-protocol --state all --json number,author,state,mergedAt` | #1 merged 2026-08-15T23:08:45Z, #2 open, #8 open, #9 merged 2026-08-18T22:15:00Z, all four by `GiulioDER`. (#3 is not his: `egnaro9`, merged 2026-08-15T23:16:12Z. The repository has five PRs; four are the audit.) |
| #9 merged at `81f50cf`, after the pinned commit | `git show -s --format='%h %cI %s' 81f50cf`; `git ls-tree 92e4548 .gitattributes` | merge commit `81f50cf`, 2026-08-18T18:15:00-04:00; `.gitattributes` absent at `92e4548` |
| E2 passes at `92e4548` | detached worktree at `92e4548`, `cp -R fixtures/valid` copy, covered artifact moved out and replaced by a symlink to it, then `python -m vac.verify <bundle>` | exit 0, `structural verification: PASS`, banner clause `bundle closure` |
| Positive control, unlisted file | same bundle plus `evidence/stowaway.txt` | exit 1, `FAIL unlisted-file: evidence/stowaway.txt` |
| Positive control, tampered artifact | one byte appended to `evidence/bundle.json` | exit 1, `FAIL sha256-mismatch: evidence/bundle.json` |
| Host dependence, why it is a vacuous pass and not a fifth forgery | link target moved away, same bundle re-run | exit 1, `FAIL missing-artifact: evidence/bundle.json` |
| E1, for completeness | unlisted file inside a symlinked subdirectory | exit 0, nothing named |
| Mechanism line | `git show 92e4548:vac/verify.py`, line 224 | `for p in sorted(bundle_dir.rglob("*")):`, filtered by `p.is_file()` |
| Why #8 is not landed | `git show 92e4548:vac/verify.py \| grep -cE '^[[:space:]]*(f\|failures)\.append\('` and the same at `ce462e10` and `68ceed05` | 146 raw sites at `92e4548`, 153 at #8's parent (`ce462e10`, which is #2), 155 at #8's head `68ceed05`; #8's own commit adds exactly two, both `unsafe-bundle: ...: symlink` |

Landing #8 before submission would move the refusal-site denominator the Results
section is scored against (`sec:results`, section 7 in the last build), so it is
recorded as an open finding
against the fixed verifier rather than as a fixed one. That is stated in the
paper, not just here.

**Not re-measured by this pass:** #8's E3 (the same shape inside a `.tar.gz`,
which the PR reports as already refused) and its Windows and Linux test tallies.
Those are taken from the public PR body and are not asserted in the paper.

**Rebuild note.** This pass added three `\url{}` tokens to Section 2 (the
`cca-audit` repository and pull requests #8 and #9). No TeX toolchain is
installed on the machine that made these edits, so nothing here was compiled: the
"overfull hboxes: 0" row in the verification record above predates them and must
be re-measured on the next build, along with the rendered Section 2.
