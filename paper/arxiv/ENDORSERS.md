# arXiv cs.SE endorsement: candidates, evidence, and routes

Measured 2026-08-18. Endorsement code `SYXI8C`, category cs.SE.
Eligibility window: an endorser needs 3+ arXiv papers in any cs.* class submitted between
2021-08-18 and 2026-05-18.

Every count below was measured over HTTPS with a positive control run first
(`all:electron` -> 185050). Plain `http://export.arxiv.org` returns an EMPTY body that reads
exactly like "no results", which is how the first pass of this search nearly reported a false
negative. Never trust a zero from this API without a control.

**The authoritative check is not this file.** On any arXiv abstract page, logged in, click
"Which authors of this paper are endorsers?". It returns 401 to anonymous requests, so only
Erik can run it. Use it before spending an ask.

---

## Ranked shortlist: arXiv cs.SE endorsement candidates for Erik Hill

**The headline finding, stated first because it changes the plan:** every person Erik actually knows is ineligible. Giulio D'Erme (0 arXiv papers, measured `au:"D'Erme"` totalResults 0), Alexey Andreev (0), Steve Coffman (0), Mike Czerwinski (0), and Bartek Nawara (0) cannot endorse anyone. Criterion 1 of the ranking is empty. **Every name below is a stranger.** The ranking is therefore over strangers, ordered by proven eligibility, the strength of the specific hook Erik can open with, and whether a contact route was actually verified.

I re-measured the load-bearing claims myself rather than relaying them. Positive control run first: `search_query=all:electron` returned HTTP 200, totalResults 185050 (re-confirmed at the end of the run). All eligibility counts below are my own measurement, window 2021-08-18 to 2026-05-18, papers carrying at least one cs.* category.

---

### 1. The authors of arXiv:2608.14315, led by Houari Sahraoui (Universite de Montreal)

**Eligibility: PROVEN.** `au:"Houari Sahraoui"` returned totalResults 39; I parsed all 39 and counted **25 in-window cs.\* papers**. Three: 2601.19316 (2026-01-27, cs.SE), 2512.21028 (2025-12-24, cs.SE), 2506.04464 (2025-06-04, cs.SE). Clears a bar of 3 by more than eight times.

**Why first:** I fetched the abs page for 2608.14315 directly. Verified: title "Breaking Models to Test the Judge: A Mutation Testing Approach for Semantic Evaluators of Domain Class Diagrams", submission history "From: Kevin Delcourt, [v1] Fri, 14 Aug 2026 13:57:51 UTC", authors Kevin Delcourt, Meriem Ben Chaaben, Abdelhamid Rouatbi, Luciano Marchezan, Houari Sahraoui. That is Erik's method, in cs.SE, posted four days ago. He has to read and cite it whether or not he ever asks for an endorsement.

Treat the **paper** as the target, not the person. The abs page carries the link "Which authors of this paper are endorsers?" (I confirmed the string is present, and that `/auth/show-endorsers/2608.14315` returns 401 anonymously, so Erik must be logged in). One click, logged in, tells him authoritatively which of those five qualify. That converts my inference into arXiv's own answer, and gives up to five pre-qualified endorsers who work on exactly his method. Marchezan or Ben Chaaben are likelier to reply than Sahraoui, who is a Vice-Dean.

**Contact:** houari.sahraoui@umontreal.ca, published on the UdeM DIRO directory. Per-author emails for the others are on the abs page under Submission history.

**Risk to name out loud:** this paper is also a priority problem. Erik's "novel method" framing needs to become "applies mutation testing of evaluators to a new artifact class", or a reviewer will make that correction for him.

### 2. Martin Monperrus (KTH)

**Eligibility: PROVEN.** `au:"Martin Monperrus"` returned totalResults 178. I pulled the 40 most recent and **32 of those alone are in-window cs.\***: 2604.27781 (2026-04-30, cs.SE), 2604.20015 (2026-04-21, cs.SE), 2603.24282 (2026-03-25, cs.SE), plus a sole-authored 2603.17399 (2026-03-18, cs.SE).

**Topical:** hits both axes. Verifiable provenance of software artifacts, SBOM and reproducible-build work on the object side; "Evaluating Cryptographic API Misuse Detectors for Go" (2604.24085) and work on randomness in agentic evals on the method side. An evidence-bundle verifier is native territory.

**Contact:** monperrus@kth.se, on a contact page that states email is the preferred channel and publishes a PGP fingerprint. He has a public record of engaging with unaffiliated researchers. If Erik sends exactly one email, this is the strongest single shot.

### 3. Ali Hassaan Mughal (independent researcher)

**Eligibility: PROVEN, and the cleanest of anyone institutional.** `au:"Ali Hassaan Mughal"` returned totalResults 7; **5 in-window, every one primary cs.SE**, and he is first or sole author on all five: 2605.14568 (2026-05-14), 2604.20462 (2026-04-22), 2602.08242 (2026-02-09), 2503.08464 (2025-03-11, sole author), 2402.15928 (2024-02-24, sole author).

**Why he matters more than his citation count suggests:** he is publishing cs.SE right now with no institution, which means he cleared this exact gate recently and without a supervisor. His 2606.22475 "All Green, Still Broken" is Erik's thesis one domain over. The ask is peer to peer, not favor to stranger.

**Contact: UNVERIFIED.** alihassaanmughal.work@gmail.com came from search-result summaries, not from a PDF I opened. Erik should pull the address off the paper header before sending anything.

### 4. Adwait Nadkarni (William & Mary)

**Eligibility: PROVEN.** `au:"Adwait Nadkarni"` returned totalResults 16, **8 in-window cs.\***: 2602.20446 (2026-02-24, cs.CR), 2510.13102 (2025-10-15, cs.CR), 2502.07257 (2025-02-11, cs.SE), 2308.02310 (2023-08-04, cs.CR), 2308.06695 (2023-08-13, cs.CR). Note his two landmark 2021-02 papers fall before the window and do not count; he still clears the bar without them.

**Topical:** he is the methodological ancestor. MASC (2308.02310) is mutation-based evaluation of static crypto-API misuse detectors: inject known defects into a verifier's inputs, measure which checks stay silent. If Erik's related-work section does not already cite MASC and muSE, that is a hole in the paper independent of endorsement.

**Contact:** "apnadkarni at wm.edu", published in that obfuscated form on his own site, which itself signals he expects cold mail.

### 5. Christoph Treude (Singapore Management University)

**Eligibility: PROVEN.** `au:"Christoph Treude"` returned totalResults 176; of the 40 most recent, **33 are in-window and overwhelmingly primary cs.SE**: 2605.08435 (2026-05-08), 2605.04532 (2026-05-06, sole author), 2604.17940 (2026-04-20), all cs.SE.

**Topical:** the most cs.SE-native person on the list. His LLM-as-judge-for-SE review and road map explicitly calls for methods to validate automated judges. Erik's paper is one concrete instance of that call. Heavy community-service record (artifact evaluation, registered reports), which correlates with helping a newcomer through a procedural gate.

**Contact:** ctreude@smu.edu.sg, plaintext on his own homepage. Weakest personalization hook of the top five, strongest safe-bet profile.

### 6. Santiago Torres-Arias (Purdue)

**Eligibility: PROVEN.** `au:"Santiago Torres-Arias"` returned totalResults 17, **15 in-window cs.\***: 2603.17133 (2026-03-17, cs.SE), 2509.13217 (2025-09-16, cs.CR), 2503.00271 (2025-03-01, cs.SE).

**Topical:** he leads in-toto and contributes to Sigstore. "Evidence-bundle verifier" is literally the artifact class his tooling defines, so a result showing which of a verifier's refusal sites are inert is ammunition for his own specs rather than a critique of them. Contact: santiagotorres@purdue.edu, on the Purdue ECE profile.

---

**Also eligible, deliberately ranked lower.** Gordon Fraser (Gordon.Fraser@uni-passau.de, plaintext, equivalent-mutants work) is a fine alternate if the paper's framing leans mutation-adequacy rather than supply chain. Mike Papadakis is the most active mutation-testing author on arXiv but publishes his email only as an image, so there is no verified contact route. Benoit Baudry, Paolo Tonella, Stella Biderman, Sayash Kapoor, Jasper Dekoninck and Leshem Choshen are all eligible by measurement; they are further from cs.SE, or high-volume inboxes, or both.

**Conditional, check before asking.** Jeffrey Flynt: `au:"Jeffrey Flynt"` returned totalResults 4, and **exactly 3 are in-window, all sole-authored** (2605.11325 cs.IR, 2603.22499 cs.CR, 2603.14997 cs.CL). Sole authorship makes him the provable submitter of all three, which is the strictest reading satisfied, but zero margin and no in-window cs.SE primary. His GroundEval work is a topical twin. Verify via the show-endorsers link on one of his abs pages before spending an ask. Same treatment for Oleg Solozobov (6 in-window, sole-authored).

**Do not ask.** Giulio D'Erme, Alexey Andreev, Steve Coffman, Mike Czerwinski, Bartek Nawara, Kevin Delcourt (only 1 in-window; his two newest are inside the three-month blackout), Konstantine Kahadze (1 paper).

**Correction to a stored belief, flagged deliberately.** The working assumption on record is that Bartek Nawara holds arXiv endorsement rights for cs.AI/cs.CL. I measured `au:"Nawara"` myself: totalResults 1, and the single record is 2506.04662 (2025-06-05, math.AG, Ewelina Nawara). He has no arXiv papers under any name variant, no ORCID works, and one OpenAlex record which is his dissertation. **He cannot endorse anyone for anything.** His supervisor, prof. Grzegorz Nalepa, is eligible (`au:"Nalepa, Grzegorz"` totalResults 25, 20 in-window cs.LG/cs.AI), so Bartek's value here is a possible warm introduction, not the endorsement itself. Any plan built on Bartek endorsing needs rewriting.

---

## Three honest answers

### How likely is a cold request to a stranger to actually work?

Lower than Erik wants, but the route is not against policy, and the reason matters. I fetched arXiv's own endorsement page (https://info.arxiv.org/help/endorsement.html, HTTP 200) rather than working from memory. It says the best endorser is one "you know personally and is knowledgeable in the subject area of your work", and offers the archetype: "A good choice for graduate students would be your thesis advisor". Erik has no advisor and no department. He is outside the design assumption.

But the same page then documents the cold route explicitly: "look for related articles in your field. If your article has citations to recent papers in arXiv, look for those papers in arXiv to find an endorser", find the endorser's email "on the abstract page just under the Submission history heading", and "Contact eligible endorsers and send them the endorsement request email." So contacting the authors of papers he cites is arXiv's own instruction, not a workaround.

The decisive line is in the endorser's responsibilities: "You should know the person that you endorse **or** you should see the paper that the person intends to submit... We do not expect you to read the paper in detail, or verify that the work is correct, but you should check that the paper is appropriate for the subject area." That "or" is the whole game. Erik cannot supply the first half, so he must supply the second half, in full, in the first email. The bar he is clearing is topical appropriateness, not merit, and a paper plus a public repo with 250+ tests and CI clears it cheaply.

Realistic expectation, stated without softening: most sends get silence, not refusal. Plan on roughly four to six carefully personalized asks over three to six weeks to land one yes, with the most senior names least likely to answer at all. Two constraints cap the throughput. arXiv says "it is inappropriate to email large numbers of potential endorsers at once, or to repeatedly email the same endorser", so he cannot spray and he cannot nudge. And "If you feel uncomfortable about endorsing an author for any reason, do not do it" pairs with a form that records an explicit negative vote, so a badly targeted ask to someone with no context can cost him a recorded no rather than a neutral non-answer. Endorsement decisions are private, so he will often not know which happened.

The lever is not who he asks. It is that the paper and the repo link go in the first email, and that the email opens with something about their work.

### Whose paper should he read and engage with first?

**arXiv:2608.14315**, Delcourt, Ben Chaaben, Rouatbi, Marchezan, Sahraoui, submitted 2026-08-14. Three separate reasons, any one of which would be sufficient:

1. He has to cite it. It is the closest published relative of his method, it is four days old, and a reviewer or a skeptical reader will find it in one search. Not citing it looks like he did not check.
2. Reading it is what makes the ask non-cold. The email opens with a specific technical observation about their mutation operators or their killed/survived accounting, and the endorsement code goes in the last two lines, not the first.
3. One abs page yields up to five candidate endorsers, and arXiv will tell him authoritatively which ones qualify via the "Which authors of this paper are endorsers?" link. That link requires login (it returned 401 to me anonymously), so this is a check only Erik can run, and it should be the first thing he does. It removes all inference from the eligibility question for those five people.

Two more to read and cite before sending anything: Nadkarni's MASC (2308.02310), the methodological ancestor of injecting known defects to see what a verifier fails to flag, and Mughal's "All Green, Still Broken" (2606.22475), which is his thesis in another domain and whose author is an unaffiliated cs.SE publisher who could plausibly become a genuine peer rather than a one-time favor.

The cost of this is two or three days before the first email goes out. Pay it.

### Is there a route that avoids the endorsement problem entirely?

Four, with honest costs.

**A co-author who is already an arXiv submitter.** This dissolves the problem: they submit, Erik is listed, he claims the paper, and he accumulates his own standing for paper number two. It also converts an awkward favor-ask into a collaboration offer, which strangers accept far more often than requests. Cost: shared authorship on his flagship, plus some loss of control over framing and timing. And note the route he had penciled in is gone, since Bartek has no arXiv record. Nalepa via Bartek, or an author of 2608.14315, are the live versions of this.

**Zenodo, today, for a citable DOI.** Free, no gate, same-day, and it timestamps priority, which suddenly matters given 2608.14315 landed on 2026-08-14. Cost: near-zero discovery among cs.SE researchers compared with arXiv, and no arXiv-ID credibility signal. It does not burn the arXiv option later, since arXiv accepts work posted elsewhere (that last point is general policy knowledge, not something I measured in this run). OSF Preprints and TechRxiv are equivalent alternatives.

**Skip the preprint and submit to a peer-reviewed venue.** ICSE, FSE, ASE, ISSTA, ICST, or the Mutation workshop. An acceptance beats a preprint for every purpose Erik actually cares about, including the job search, and it makes endorsement moot. Cost: months of latency and a real chance of rejection, with no artifact in public in the meantime unless he pairs it with the Zenodo DOI.

**Institutional email auto-endorsement: closed.** The page states the automatic path requires **both** that "you have claimed ownership of a paper submitted by a co-author" **and** that "your email address meets the institutional email criteria". Erik has neither, and erik@erikhill.dev is not institutional. This only opens up as a side effect of the co-author route.

The combination I would actually run: post to Zenodo now for the priority timestamp, spend two days reading and citing 2608.14315 plus MASC, use the logged-in show-endorsers link on that abs page to pick a verified endorser from its five authors, then one personalized ask per week down the list above with the paper attached, while pursuing a co-author in parallel.

**Files:** measured XML and parsed results are in `/private/tmp/claude-501/-Users-lonimua/3d82d9c3-dd08-4008-8650-40b8b9757f64/scratchpad/arxv/` (`results.json`, `run.log`, per-query `.xml`, `endorse2.html`, `abs14315.html`).

---

## Appendix: Bartek Nawara, measured

{
  "candidates": [
    {
      "name": "Bartlomiej \"Bartek\" Nawara (Bart\u0142omiej Nawara)",
      "affiliation": "PhD 2017-2023, Institute of Philosophy / Interdisciplinary Studies, Jagiellonian University, Krakow. Doctoral supervisor: prof. dr hab. inz. Grzegorz J. Nalepa. Now industry: Senior AI/ML Engineer and NLP Researcher (production LLM/NLP, agentic architectures, RAG, EU AI Act).",
      "eligible": "NO",
      "evidence": "ZERO arXiv papers, in the window or ever. Measured: au:\"Nawara\" returns totalResults 1, and that single record is NOT him: arXiv:2506.04662v1, published 2025-06-05, primary_category math.AG, \"The Hesse pencil of plane curves and osculating conics\", author Ewelina Nawara. au:\"Nawara\" AND cat:cs.* returns 0. Every name variant returns 0: au:\"Bartlomiej Nawara\" 0, au:\"Bartek Nawara\" 0, au:\"Nawara Bartlomiej\" 0, au:\"Nawara, B\" 0, au:\"B Nawara\" 0, au:\"Nawara_B\" 0. all:\"Nawara\" (full text, not just author field) also returns 1, the same Ewelina paper. The arXiv author-page convention https://arxiv.org/a/nawara_b_1 returns HTTP 404. There are no 3 IDs and no dates to report because there are no papers. Corroborated off-arXiv: his ORCID 0009-0000-8611-1286 (Bartlomiej Nawara, Jagiellonian University) lists 0 works, no bio, no keywords; OpenAlex author A5130157393 \"Bartlomiej Nawara\" has works_count 1, and that one work is his dissertation \"Philosophical interpretations of Big Data research\" (type: dissertation, venue: Jagiellonian University Repository, no DOI); Semantic Scholar author search \"Bartlomiej Nawara\" returns total 0; DBLP has 33 authors matching Nawara and none is a Bartlomiej. Not a dead-API artifact: positive controls all:electron 185050, au:\"Hinton\" 770, au:\"Bartlomiej\" 867 (so the ASCII Polish given name is indexed and searchable), ti:\"electron\" AND ti:\"spin\" 3421 (so AND parses).",
      "topical_fit": "Real overlap in subject matter, none in publication venue. His doctoral work is philosophy of AI, not software engineering or evaluation methodology: dissertation on philosophical interpretations of Big Data research, plus work on symbol grounding via GPT-3 and a piece titled \"Superintelligence 7 years later. Is GPT-3 a path to Superintelligence?\" (that publication list comes from a ResearchGate search snippet; researchgate.net returned HTTP 403 to direct fetch, so I could not verify it firsthand and it should be treated as unconfirmed). His current industry work (production LLM systems, agentic architectures, RAG, EU AI Act compliance) sits adjacent to eval integrity, and EU AI Act conformity assessment is genuinely close to \"can you trust what your verifier reports\". But he has no cs.SE or empirical-software-engineering publication record, and no arXiv deposits at all, so his relevance is as a domain-conversant reader and possible co-author, not as an endorser and not as a cs.SE track record.",
      "why_they_might_say_yes": "He remains a good collaborator and co-author prospect, and the EU AI Act angle gives mutual interest in whether a verifier's green result means anything. What he CANNOT do is endorse, and the real value here is the redirect: his own doctoral supervisor, prof. Grzegorz J. Nalepa, IS qualified. Measured: au:\"Nalepa, Grzegorz\" returns totalResults 25, of which 20 fall inside the 2021-08-18 to 2026-05-18 window, in cs.LG and cs.AI. Three in-window examples: arXiv:2603.18032v1 submitted 2026-03-09 (cs.LG), arXiv:2511.20236v3 submitted 2025-11-25 (cs.AI), arXiv:2511.03631v2 submitted 2025-11-05 (cs.LG). That clears the 3-paper bar roughly seven times over. Nalepa leads the GEIST group and works on XAI, which is topically close to eval integrity. Bartek is plausibly the warm introduction path to him rather than the endorser himself. Nalepa's eligibility is measured here only from the arXiv API; I did not verify he is a registered arXiv endorser or contact him, per instructions.",
      "public_contact": "NONE. No email is published anywhere I could verify. He has no arXiv paper, so there is no paper-header email. His official institutional page, https://filozofia.uj.edu.pl/en_US/bartlomiej-nawara, lists only his status (mgr, doctoral student, start date 24.10.2018) and his supervisor, with no email address and no publication list. Public profiles exist but carry no contact address: LinkedIn (linkedin.com/in/bart\u0142omiej-nawara-phd), Medium (@barteknawara), Academia.edu (independent.academia.edu/BartekNawara), ResearchGate (403 to fetch). I deliberately did not use the RocketReach result that surfaced in search, since a data-broker scrape is not published contact information."
    }
  ],
  "queries_run": [
    "POSITIVE CONTROL search_query=all:electron -> totalResults 185050",
    "POSITIVE CONTROL search_query=au:\"Hinton\" -> totalResults 770",
    "POSITIVE CONTROL search_query=au:\"Bartlomiej\" -> totalResults 867 (proves ASCII Polish given name is indexed)",
    "POSITIVE CONTROL search_query=ti:\"electron\" AND ti:\"spin\" -> totalResults 3421 (proves boolean AND parses; an earlier run that URL-encoded +AND+ literally returned a meaningless 442167 and was discarded)",
    "search_query=au:\"Nawara\" -> totalResults 1 (arXiv:2506.04662v1, 2025-06-05, math.AG, Ewelina Nawara)",
    "search_query=all:\"Nawara\" -> totalResults 1 (same Ewelina Nawara record)",
    "search_query=au:\"Nawara\" AND cat:cs.* -> totalResults 0",
    "search_query=au:\"Nawara_B\" -> totalResults 0",
    "search_query=au:\"Bartlomiej Nawara\" -> totalResults 0",
    "search_query=au:\"Bartek Nawara\" -> totalResults 0",
    "search_query=au:\"Nawara Bartlomiej\" -> totalResults 0",
    "search_query=au:\"Nawara, B\" -> totalResults 0",
    "search_query=au:\"B Nawara\" -> totalResults 0",
    "search_query=all:\"Philosophical interpretations of Big Data\" (his dissertation title) -> totalResults 0",
    "search_query=ti:\"Superintelligence\" AND all:\"GPT-3\" (his reported paper title) -> totalResults 0",
    "search_query=au:\"Nalepa, Grzegorz\" (doctoral supervisor) -> totalResults 25, 20 inside 2021-08-18..2026-05-18, cs.LG/cs.AI",
    "WebFetch https://arxiv.org/a/nawara_b_1 -> HTTP 404 Not Found",
    "ORCID expanded-search q=family-name:Nawara -> num-found 42; exactly one Bartlomiej Nawara, 0009-0000-8611-1286, Jagiellonian University",
    "ORCID https://pub.orcid.org/v3.0/0009-0000-8611-1286/works -> work count 0",
    "ORCID https://pub.orcid.org/v3.0/0009-0000-8611-1286/person -> name Bartlomiej Nawara, no bio, no emails, no URLs, no keywords",
    "OpenAlex authors?search=Bartlomiej Nawara -> count 1, A5130157393, works_count 1, orcid null",
    "OpenAlex works?filter=author.id:A5130157393 -> 1 work, type dissertation, 'Philosophical interpretations of Big Data research', Jagiellonian University Repository, no DOI",
    "OpenAlex authors?search=Nawara&per-page=100 -> 209 authors, only one Bart* match (the same 1-work record)",
    "Semantic Scholar author/search?query=Bartlomiej Nawara -> total 0",
    "Semantic Scholar author/search?query=B. Nawara -> total 2, neither is him (N. Eissa, Nawara B. Al-Torjman)",
    "DBLP author search q=Nawara -> 33 hits, no Bartlomiej (closest Polish: Piotr Nawara, Tomasz J. Nawara)",
    "DBLP publ search q=Nawara -> 115 hits, none authored by a Bartlomiej Nawara",
    "Crossref works?query.author=Bartlomiej+Nawara -> fuzzy, top 10 are other Nawaras (Leszek, Piotr, Dariusz, Agnieszka, Dina, Ewelina, W)",
    "WebFetch https://filozofia.uj.edu.pl/en_US/bartlomiej-nawara -> mgr, doctoral student from 24.10.2018, supervisor prof. dr hab. inz. Grzegorz Nalepa, no publications listed, no email",
    "WebFetch https://www.researchgate.net/profile/Bartlomiej-Nawara -> HTTP 403 Forbidden, could not verify firsthand",
    "WebSearch \"Bartlomiej Nawara\" Jagiellonian University AI PhD publications -> PhD 2017-2023 Interdisciplinary Studies; ResearchGate snippet claims 3 publications, all philosophy-of-AI"
  ],
  "control_check": "Ran four positive controls over HTTPS before trusting any zero, because plain HTTP returns an empty body that reads identically to \"no results\". search_query=all:electron returned totalResults 185050 and a real title (\"The electronic structure of cuprates from high energy spectroscopy\"), proving the endpoint was alive and parsing. search_query=au:\"Hinton\" returned 770, proving the au: field works. Most importantly for this specific question, search_query=au:\"Bartlomiej\" returned 867, which proves the ASCII-transliterated Polish given name is indexed and searchable, so a zero for au:\"Bartlomiej Nawara\" is a real absence and not a diacritic-handling failure. Finally search_query=ti:\"electron\" AND ti:\"spin\" returned 3421, proving boolean AND parses correctly; this control was added after I noticed an earlier query had URL-encoded +AND+ as literal plus signs and returned a nonsense 442167, and both affected title queries were re-run and discarded."
}
