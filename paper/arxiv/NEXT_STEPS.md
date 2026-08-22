# arXiv submission: ordered plan

Written 2026-08-18. Two gates remain and neither is the manuscript.
Endorsement code `SYXI8C`, cs.SE. Draft `submit/7963507` expires **2026-09-01**.

Legend: **[E]** only Erik can do it (login, send, click). **[C]** Claude does it.

---

## Step 1 [E] Zenodo DOI, today. 15 minutes.

Time-critical because arXiv:2608.14315 landed 2026-08-14 and you have no public
timestamp on the arXiv version.

1. zenodo.org, log in with GitHub.
2. Settings -> GitHub, flip the toggle ON for `egnaro9/vac-protocol`.
3. On GitHub, cut a release (tag `v0.1.0`). Zenodo mints a DOI from it.
4. Paste the DOI into `CITATION.cff` and into the paper's Reproducibility section.

This does not burn the arXiv option. arXiv accepts work posted elsewhere.

## Step 2 [E] The authoritative endorser check. 2 minutes.

**Logged in**, open https://arxiv.org/abs/2608.14315 and click
**"Which authors of this paper are endorsers?"** near the bottom.

It returns 401 to anyone not logged in, so only you can run it. It converts my
date arithmetic into arXiv's own answer for those five authors. Tell Claude the
result.

## Step 3 [C] Reposition against the neighbour paper. Half a day.

Add to Related Work and narrow the novelty claim:
- arXiv:2608.14315, Delcourt et al., mutation testing of semantic judges. Their
  operators mutate the artifact under judgment; ours deletes refusal sites in the
  checker. Say that difference explicitly.
- arXiv:2308.02310, Nadkarni et al., MASC. The methodological ancestor: inject
  known defects, measure which checks stay silent. If this is not cited the
  related work has a hole.
- arXiv:2606.22475, Mughal, "All Green, Still Broken". Same thesis, other domain.

Then rebuild, rerun `~/bin/arxiv-scan`, re-verify the abstract length.

## Step 4 [C] Draft the endorsement ask.

Opens with a specific technical observation about THEIR paper. Endorsement code
in the last two lines, not the first. Paper PDF and repo link attached, because
arXiv's rule is "know the person **or** see the paper" and you can only supply
the second half.

## Step 5 [E] Send exactly one ask. Then wait.

arXiv says it is inappropriate to email many endorsers at once or to re-email the
same one. The form records an explicit **negative** vote, so a bad ask costs more
than silence. One per week, down this order:

1. a verified endorser from 2608.14315 (step 2 tells you which)
2. Martin Monperrus, monperrus@kth.se (178 papers, publicly welcomes cold mail)
3. Ali Hassaan Mughal (independent, cleared this exact gate with no institution;
   pull his email off the paper header, the one in search results is unverified)
4. Adwait Nadkarni, apnadkarni at wm.edu
5. Christoph Treude, ctreude@smu.edu.sg
6. Santiago Torres-Arias, santiagotorres@purdue.edu (in-toto lead)

Realistic: 4 to 6 asks over 3 to 6 weeks to land one yes.

## Step 6 [E] Run the co-author track in parallel.

This dissolves the gate entirely: a co-author who already submits to arXiv posts
it, you claim the paper, and you accumulate your own standing for paper two.
Costs shared authorship and some control over framing.

Live options: an author of 2608.14315, or prof. Grzegorz Nalepa (Bartek's
doctoral supervisor, 25 arXiv papers, 20 in window) via a warm introduction from
Bartek. **Bartek himself cannot endorse: zero arXiv papers, measured.**

Giulio's answer to your question 3 is also this track. He replied 2026-08-18 19:34Z
and granted consent (see the closed item below); check that reply for whether
it also answers question 3.

## Step 7 [E] Then submit.

Accept the agreement, CC BY, cs.SE primary, cs.CR cross-list, upload
`main.tex` + `main.bbl` + `refs.bib` flat. Never `audit/`, never `main.pdf`.
`SUBMISSION.md` has the metadata to paste and 15 items to sign off.

---

## Not blocking, do when convenient

- **[DONE 2026-08-18]** Giulio's consent for the named acknowledgment. Requested
  16:11Z, granted 2026-08-18 19:34Z, written consent on file: he asked to be named and
  cited as Giulio D'Erme, in the wording already in the paper, and declined
  co-authorship. Four corrections from the same reply are in at `81dfc7a`. The
  quote was already safe regardless: it cites the public merged PR.
- **[E]** Push the three commits (`e932868`, `b30ea2f`, `b61ee7d`). Needed before
  a Zenodo release can include them.
- **[C]** A separate one-line commit for the pre-existing em-dashes in
  `tools/mutation_sweep.py:213` and `fixtures/make_fixtures.py`.

## The thing worth fixing beyond this paper

You have been publishing this thread on dev.to since 2026-07-15. The arXiv
version is still unposted a month later, and someone else filed on 2026-08-14.
The gap between "I did the work" and "it is citable" is the actual problem. Step
1 closes half of it today.
