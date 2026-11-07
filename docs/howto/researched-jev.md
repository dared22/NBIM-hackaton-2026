# Compare researched Jev predictions

Use this workflow to predict NBIM votes from guideline questions, dated company
documents, and verified earlier votes. It writes a separate experiment and leaves
the existing predictor unchanged.

> **Note:** This is a preview feature currently under active development.

## Run a comparison

Run these commands from the repository root with Python 3.10 or newer:

```bash
python3 run.py predict
python3 run.py refresh researched-jev --year 2026 --limit-meetings 10
python3 run.py compare-jev --year 2026
```

The refresh requires the authenticated `firecrawl` CLI and `OPENROUTER_API_KEY`
in your environment or `.env`. It contacts Firecrawl, Internet Archive, SEC,
and OpenRouter and can incur charges. It samples whole meetings with seed 42,
without looking at outcomes, and performs at most five searches per meeting.
Reduce `--limit-meetings` for a smaller run. Run the same refresh again to reuse
cached searches, documents, and Jev answers.

The comparison reads saved inputs without network access. Its output directory
defaults to `data/outputs`; use `--output-dir` to change it. To compare against
the current predictor, that directory must contain its `decisions_2026.csv`.
The current predictor supports only 2026; other experiment years need their own
baseline file. The summary reports the matched comparison size explicitly.

Open these generated files:

- `comparison_jev_2026.csv`: proposed votes, probabilities, current-model scores,
  actual outcomes, guideline references, evidence URLs, and review flags.
- `qa_jev_2026.jsonl`: questions, answers, exact supplied passages, source proofs,
  earlier history, and final model requests.
- `comparison_jev_2026.json`: precision, recall, Brier error, evidence coverage,
  review count, and cached Jev costs. Threshold metrics use 0.5 without tuning.

## Inspect the evidence

Review the Q&A export before interpreting a prediction. Each rule receives a
`yes`, `no`, `unknown`, or `not_applicable` answer. A separate Jev request uses
those completed answers to predict `FOR`, `MOT`, or `AVSTÅ`. Missing facts retain
a tentative prediction and a review flag. Passage IDs identify context supplied
to Jev; they are not generated reasoning or proof that its interpretation is
correct. Firecrawl credits are separate from the reported Jev cost.

The [routing registry](../../src/evidence/research_policy.py) covers all 24
proposal types. Catchall types and amendments consider the full policy. Other
types use relevant rules plus disclosure and bundling checks. Jev checks each
rule's ballot subject and market conditions; selecting a rule does not establish
that it applies. Dividends, repurchases, and voting frequency have no invented
dedicated rule.

Company evidence must have a SEC filing date or an actual archive capture
strictly before meeting day. Search snippets, current pages with old date tags,
same-day sources, and archive redirects are excluded. Install `requirements.txt`
to extract text from archived PDFs; scanned PDFs without text remain evidence
gaps. Documents describing NBIM voting decisions
are excluded from company evidence, even if published before the meeting.

The [policy manifest](../../data/policy/research_editions.json) records the 2025
edition's official publication listing, dated February 17, 2025, and the hash of
the stored transcription. The workflow selects the latest verified available
edition before the cutoff, rather than assuming an April effective date. Add
verified editions to that manifest when needed; dates before its first entry
produce a missing-policy flag. The manifest is a curated source of truth and
does not automatically detect subsequently published policy editions.

## Supply verified earlier voting history

The supplied vote CSV lacks publication timestamps. Its earlier outcomes are
therefore omitted unless you supply matching publication evidence. Omitted
history is counted and flagged; the workflow does not assume that an earlier
meeting date establishes publication timing.

Store publication records in
`data/evidence/researched_jev/history_publications.jsonl`, one JSON object per
line with these fields:

- `vote_key`: the earlier CSV row's `meeting_id-item_no`.
- `document`: a source record from `research_sources.source_record`, containing
  `url`, `text`, `available_on`, `sha256`, and `proof`.
- `quote`: an exact passage from the document containing the CSV's company,
  proposal text, ISO meeting date, and normalized vote (`FOR`, `MOT`, or `AVSTÅ`).

For an archived publication, `proof` contains `kind: "archive"` and its
14-digit `timestamp`; `document.snapshot_url` must identify that exact capture.
Verify the original source and capture before adding it. For SEC evidence, the
proof contains `kind: "sec_filing"`, `filed`, and `accession`, matching the
document's SEC archive URL. The content hash must match the supplied text.

Refresh after adding publication evidence. Jev receives up to six verified
earlier votes of the same proposal type at the company, prioritizing identical
proposal wording and then recent dates. Current and same-day votes never enter
the history. Original publication documents stay in the audit record rather
than being sent wholesale to the final predictor.

## Interpret the results

Treat the comparison as exploratory: 2026 already influenced development.
Compare the matched metrics, evidence coverage, and review flags together.
A lack of retrieved evidence does not establish a company disclosure failure.

The final model inputs replace known issuer and nominee names with aliases.
This reduces reliance on identity but cannot prove that a modern model has no
historical outcomes in its training data. The historical reconstruction controls
the documents and labels supplied to the model, not its learned knowledge.

Return to the [application guide](../../README.md) for the existing prediction
and dashboard workflow.
