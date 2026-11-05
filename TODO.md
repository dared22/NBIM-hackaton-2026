# Case 1 TODO

This checklist tracks what remains to fulfill the
[architecture plan](docs/case1-architecture.md). It includes work available on
other branches so you can integrate existing implementations before building
anything twice. Checked items mean an artifact exists and was inspected; they
do not mean the complete agent is integrated or ready for delivery.

## Audit scope and assumptions

Reviewed on November 5, 2026, after fetching every branch from `origin`.
The plan is the source of truth: NBIM API votes are the answer key, the 2025
guidelines are the policy source, Jev returns a typed vote, and unsupported
decisions go to a person. Use the current `src/` and `data/dirty/` layout.
The architecture document still contains paths from before that reorganization.

| Branch or working tree | Inspected revision | What is available | Remaining integration issue |
|---|---|---|---|
| `origin/main` | `9ad1242` | Current layout, benchmark, guidelines, preprocessing notebook, separate inputs/labels/splits, and quality report. | No integrated agent; preprocessing needs explicit validation-year and eligibility rules. |
| Local `main`, local `llm_search`, and `origin/policy-retrieval` | `b56fcc6` | Same committed tree: README, architecture, and historical benchmark. | Behind remote `main`; the policy branch has no additional committed retrieval implementation. |
| Local and remote `case1-nbim-votes` | `37f7ad9` | Earlier `modell.py`, N-PX data, and prediction export. | The current benchmark supersedes this model and fixes history/metric behavior. Do not replace it with the older copy. |
| `origin/marie` | `d9a5c58` | Jev MVP, tests, MOT evaluator, adapted DEF 14A downloader, document cache, model cache, and saved runs. | Uses the older layout; evidence validation, holdout freezing, records, and final delivery remain incomplete. |
| `origin/rule-check` | `f32ddd7` | Cached Microsoft Decision rule experiment, resistance tests, SEC pay extraction, and pay model. | Uses the older layout, a different decision model, and disagreement targets; the pay experiment uses a separate N-PX dataset. |
| Uncommitted work on local `llm_search` | Not a commit | `src/evidence.py`, `tests/test_evidence.py`, a saved evidence packet, and `src/retrival/data.ipynb`. | Director-evidence prototype only; it is not shared through a branch commit or connected to Jev. The notebook explores data distributions. |

Branch-specific implementations can be inspected at these audited revisions:

- [Preprocessing notebook on main](https://github.com/dared22/NBIM-hackaton-2026/blob/9ad1242/data/prepared/preprocessor.ipynb).
- [Jev MVP on marie](https://github.com/dared22/NBIM-hackaton-2026/blob/d9a5c58/startpakke/case1_stemmegivning/jev_mvp.py)
  and its [saved-run evaluator](https://github.com/dared22/NBIM-hackaton-2026/blob/d9a5c58/startpakke/case1_stemmegivning/evaluate_jev.py).
- [Adapted DEF 14A downloader on marie](https://github.com/dared22/NBIM-hackaton-2026/blob/d9a5c58/startpakke/case1_stemmegivning/hent_def14a.py).
- [Rule-check experiment](https://github.com/dared22/NBIM-hackaton-2026/blob/f32ddd7/agent/rule_check.py),
  [resistance experiment](https://github.com/dared22/NBIM-hackaton-2026/blob/f32ddd7/agent/robustness.py),
  and [pay model](https://github.com/dared22/NBIM-hackaton-2026/blob/f32ddd7/agent/pay_model.py).

## Work already available

Reuse these artifacts. Each has limitations addressed by the unchecked tasks
below; their existence does not satisfy an entire architecture module.

- [x] Collect the canonical NBIM history in
  [data/dirty/real_votes.csv](data/dirty/real_votes.csv): 13,757 rows.
- [x] Structure 76 rules, three principles, exact policy text, and PDF page
  references in the
  [2025 guidelines JSON](startpakke/case1_stemmegivning/retningslinjer_2025.json).
  Independent verification against the original PDF remains open.
- [x] Implement the [historical benchmark](src/benchmark/model.py), with frozen
  test-year history, validation-selected thresholds, and nine passing tests.
  Its target is disagreement with management, not the MOT vote itself.
- [x] Generate 13,325 aligned, uniquely keyed input/label/split records on
  `origin/main`; input columns contain none of the six prohibited label fields.
  The split has 11,786 development rows and 1,539 holdout rows.
- [x] Implement a Jev `Choice` request, request-field allowlist, response cache,
  initial citation/review logic, and meeting-based sampling on `marie`.
  All 12 MVP tests pass in an isolated copy.
- [x] Save real Jev runs for 2025 at proposal/rules/history levels and for 2026
  at history level. The response cache identifies `jev-1.14.0`.
  There is no saved full document-backed Jev run in the audited tree.
- [x] Adapt the DEF 14A downloader to NBIM input fields on `marie`; its log
  records 220 successful document links out of 1,161 attempted meetings.
  Source selection and cache coverage still need validation for the final scope.
- [x] Build a local US director-evidence prototype with cached pre-meeting SEC
  filings, rule requirements, exact-quote checks, and explicit unknowns.
  Four evidence tests pass. Its saved example has 21 unknown rule findings out
  of 25; no vote decision is produced.
- [x] Run and cache the `rule-check` experiment for 1,539 eligible 2026 rows,
  including candidate-section and citation-recovery diagnostics.
  These are binary disagreement scores, not typed Jev votes.
- [x] Implement and cache proposal-instruction resistance experiments on
  `rule-check`. Cached replay reproduces flips even with the prompt warning:
  the fake-guideline attack removes 13 of 39 clean flags, and the Norwegian
  attack adds flags on 9 of 150 previously unflagged proposals.
  These are experiment results, not results for the final Jev pipeline.
- [x] Build SEC proxy pay extraction and a statistical pay comparison on
  `rule-check`. It runs offline on 1,200 season-2026 pay votes, with 114
  disagreement positives. It is separate from the 1,539-row API-vote holdout.

## Verified evaluation gaps

These findings determine the remaining tasks. Existing 2026 results have
already been inspected, so describe subsequent use of that dataset honestly;
do not call it an untouched test set.

| Check | Audit result | Consequence |
|---|---|---|
| Management baseline, eligible calendar-2026 rows | 1,539 rows; 66 MOT votes; TP 8, FP 6, FN 58, TN 1,467 for binary MOT detection. Precision 57.1%, recall 12.1%, F1 20.0%; three-way agreement 95.7%. | Reproduce this from the shared evaluator. There are 58 management-FOR/NBIM-MOT cases to measure separately. |
| Eligibility across implementations | Preprocessing includes one management-AVSTÅ/NBIM-AVSTÅ proposal in 2025, key `1929957` / `11`; the MVP excludes it. | Prepared data has 1,910 rows for 2025, while MVP development runs use 1,909. Agree on one evaluation mask. |
| Saved Jev history run, before evidence gate | A p(MOT) threshold of 0.61 selected on 2025 gives 21 hits, 15 false alarms, and 45 misses in 2026: precision 58.3%, recall 31.8%, F1 41.2%. | These are ungated retrospective results, not automatic production performance. |
| Saved Jev history run, original review gate | Only 7 of 1,539 decisions are automatic; 1,532 enter review. Automatic MOT hits are 5 of 66. | Build usable sourced evidence and evaluate automatic coverage alongside recall. Do not solve this by bypassing evidence checks. |
| MVP history construction | `prior_votes()` filters by proposal date, but does not freeze history before 2026. Ten eligible 2026 inputs have earlier same-year company/type history available. | Freeze any history comparison before the holdout and regenerate affected requests. Keep historical-label comparisons separate from the plan's evidence-only request. |
| Separate threshold evaluator | `evaluate_jev.py` creates automatic/review bands from p(MOT) without preserving the MVP's evidence/citation route. | Consolidate routing and evaluation so a score threshold cannot turn an unsupported decision into an automatic one. |
| Source provenance | MVP state omits policy pages; decisions omit full probabilities, sourced facts, explanation, and elapsed time. Pay API fallback uses figures as reported in later filings. | Complete the records and reject future-published facts, regardless of their fiscal period. |
| Existing N-PX checks | Five tests fail: three downloader signature errors and two duplicate-row parsing assertions. | Resolve if retaining that ingestion route; this does not block the API-vote core. |

## P0: Settle scope, integrate, and freeze the data contract

Complete these tasks before tuning the combined system. Suggested owners follow
the architecture: data + integration, policy + evidence, and Jev + decision.

- [ ] **Choose the supported proposal types and markets.** Owner: whole team.
  Start with wording-supported proposals and a small dated-document subset;
  the local evidence prototype already covers US director elections. Record
  required facts per selected rule and route unsupported types to review.
  Verify: the scope, exclusions, and coverage denominator are written down
  before selecting examples or tuning thresholds.
- [ ] **Integrate the reusable branch work into the current layout.** Owner:
  integration. Bring in remote-main preprocessing, adapt the `marie` MVP and
  evaluator, and preserve the local evidence work. Port useful `rule-check`
  experiments separately. Resolve old imports and paths without restoring old
  copies of the benchmark or datasets.
  Verify: a clean checkout imports the integrated modules and runs their
  focused tests; all needed work is committed on a shared branch.
- [ ] **Define and validate the three shared records.** Owner: integration
  with all module owners. Key every record by `meeting_id` + `item_no`.
  Proposal: date, company, market/country, text, type, proponent, and
  `mgmt_rec`.
  Evidence: rule ID, exact text, PDF page/URL, dated fact excerpts and source
  URLs, required missing facts, and conflicts. Decision: vote, all three class
  probabilities, cited rule/facts, explanation, route, review reasons, and time.
  Verify: each module reads/writes these records without ad hoc field renaming.
- [ ] **Enforce the input/answer boundary.** Owner: data + decision. Keep
  `nbim_vote`, `nbim_vote_raw`, `against_board`, `rationale_text`,
  `rationale_section`, and `position_paper` out of current-proposal requests,
  evidence records, and prediction-only outputs. Keep past vote/rationale
  prompts in a separately labeled history comparison, if retained.
  Verify: canary labels cannot appear in serialized requests; changing holdout
  labels cannot change requests, predictions, routes, or selected thresholds.
- [ ] **Make preprocessing runnable without notebook interaction.** Owner:
  data. Reuse `prepare()` from the remote-main notebook as `src/prepare.py`,
  retaining key/date/vote validation, raw-data preservation, separated labels,
  and the quality report. Keep the notebook as a caller if useful.
  Verify: one command regenerates equivalent records from the canonical CSV.
- [ ] **Unify eligibility and freeze explicit chronological partitions.**
  Owner: data. Decide how management AVSTÅ is handled; retain the architecture's
  1,539-row 2026 comparison. Separate pre-2025 statistical history, 2025
  development/threshold selection, and the fixed 2026 test rows. Check guideline
  applicability dates and exclude or disclose meetings outside its validity.
  Verify: unique aligned keys, no meeting crossing partitions, fixed row counts
  and data hash, and no guideline claims for earlier historical meetings.
- [ ] **Freeze all history and tuning artifacts.** Owner: data + decision.
  Freeze statistical/history inputs before each validation/test period; fix
  the MVP's same-year holdout history path. Save selected scope, model version,
  prompt, retrieval mapping, thresholds, and split with each run.
  Verify: flipping any 2026 outcome leaves those artifacts and requests
  unchanged. Disclose prior inspection of 2026; if further choices use its
  outcomes, label results retrospective or reserve a fresh untouched holdout.

## P1: Complete policy retrieval and company evidence

Reuse the existing JSON and evidence tools. Keep plain lookup and local caches;
the plan does not require a vector database or full-market document collection.

- [ ] **Implement `src/policy.py` using the shared evidence record.** Owner:
  policy. Return one to three plausible candidate sections from input wording,
  proposal type, and market, with exact rules, IDs, pages, and PDF URL. Include
  principles such as `P.1` through the same validated lookup. Return explicit
  no-match results. The MVP currently maps director elections to five sections.
  Verify: every returned ID/text/page exists in the JSON, and no label is read.
- [ ] **Verify policy citations against the original PDF.** Owner: policy.
  Check text and page references for the selected scope, and verify the stated
  guideline version applies to the evaluated dates.
  Verify: each displayed citation opens the correct source and page; derived
  `avledet` metadata is not presented as verbatim policy.
- [ ] **Evaluate retrieval after prediction.** Owner: policy + evaluation.
  Compare candidate and selected sections with historical `rationale_section`
  only in evaluation. The rule-check experiment learns its mapping from
  pre-2025 rationales; keep that as an explicit comparison if reused, rather
  than silently substituting it for the plan's input-based lookup.
  Verify: saved retrieval hit/coverage results and tests for unknown types,
  country-specific rules, and bounded candidate counts.
- [ ] **Connect evidence retrieval to selected rule requirements.** Owner:
  evidence. Turn the local one-proposal script into a callable step accepting
  prepared proposals and candidate rules. Remove its 2025-only sampling
  restriction from the pipeline path. Fetch only facts needed for those rules,
  rather than asking about all 25 director rules for every input.
  Verify: a 2026 prepared proposal can use cached evidence; wording-only rules
  do not trigger unnecessary retrieval/model calls.
- [ ] **Validate company, meeting, and nominee identity.** Owner: evidence.
  Reuse the adapted downloader and local filing selector. Confirm that the
  selected proxy concerns the intended meeting; recent publication alone
  does not establish this. The local script currently records meeting/nominee
  checks without enforcing them as a decision gate.
  Verify: ambiguous company matches, wrong meetings, absent nominees, and
  post-meeting sources produce missing evidence and human review.
- [ ] **Preserve auditable facts and missing facts.** Owner: evidence. Store
  source URL, publication date, exact excerpt/location, rule requirement, and
  extraction provenance with every fact. Keep the source document in a cache
  reusable across agenda items. Check that excerpts establish the required
  condition, not just that a model supplied a literal quote.
  Verify: fabricated quotes, partial conditions, contradictory sources, and
  absent facts cannot become supported findings; replay works from the cache.
- [ ] **Handle the supported market boundary explicitly.** Owner: evidence.
  For non-US cases in scope, use dated company meeting materials. Otherwise,
  record unavailable evidence and send those proposals to review.
  Verify: every eligible row stays in the coverage denominator, including
  missing documents and retrieval failures. Do not evaluate only cache hits or
  the downloader's label-enriched `--utvalg` sample as representative.
- [ ] **Keep the pay experiment separate unless deliberately integrated.**
  Owner: evidence + evaluation. If using pay facts, map CIK/CUSIP/company and
  meeting identity to canonical proposal keys; distinguish July-to-June filing
  seasons from calendar years. Preserve tagged source excerpts/locations and
  cached documents. Reject SEC API fallback facts published after the meeting.
  Verify: common-row, point-in-time-safe comparisons, or a separately labeled
  N-PX appendix; never combine the two datasets' metrics or meeting IDs.

## P1: Complete Jev decisions and the review gate

Use `marie`'s typed MVP as the starting point. The Microsoft Decision rule-check
experiment can remain a comparison; it does not replace the planned Jev path.

- [ ] **Implement the integrated `src/decision.py` request.** Owner: decision.
  Send the proposal, management recommendation, candidate policy, and sourced
  facts to one bounded FOR/MOT/AVSTÅ `Choice` request, with evidence sufficiency
  assessed for the same proposal. Keep proposal/documents as untrusted data.
  Verify: saved requests contain the full required context and no answers.
- [ ] **Validate responses and emit a complete decision record.** Owner:
  decision. Validate the vote and all three finite, normalized probabilities;
  retain the model/prompt version, citations, fact references, explanation,
  review reason, and elapsed time. Keep cached replay tied to request content.
  Verify: malformed/incomplete responses cannot produce automatic decisions;
  one record is produced per input, including failures routed to review.
- [ ] **Make the evidence gate deterministic.** Owner: decision + evidence.
  Require human review for missing required facts, invalid citations,
  conflicting evidence, no plausible policy, or insufficient probability.
  Apply the same checks to FOR decisions; `P.1` does not prove that missing
  company facts are unnecessary. Show management's vote as a labeled baseline
  when the agent cannot justify its own recommendation.
  Verify: focused cases exercise every review reason, and no unsupported
  decision becomes automatic through a score-only evaluator or fallback.
- [ ] **Choose probability and review thresholds on 2025 only.** Owner:
  decision + evaluation. Use p(MOT) for MOT detection and report how the chosen
  thresholds trade precision, recall, and review workload. Keep probability
  selection separate from mandatory evidence checks.
  Verify: persist thresholds and apply them unchanged to test rows; the
  automatic/review routes are identical in predictions, reports, and demo.
- [ ] **Build explanations from verified citations and facts.** Owner:
  decision. Explain the rule condition, the evidence that meets it, and any
  uncertainty. Do not use NBIM's historical rationale as the current answer's
  explanation or present a correlation from the benchmark as a policy finding.
  Verify: a reviewer can trace each factual claim to the saved dated excerpt.

## P1: Complete the common evaluator and first vertical slice

Reuse MOT metric and sampling code from `marie`, plus the benchmark's checked
confusion-matrix logic. Evaluate saved decisions without changing their routes.

- [ ] **Implement `src/evaluate.py` with keyed label joins.** Owner:
  evaluation. Join outcomes after decisions; reject duplicate or missing keys.
  Include always-FOR and follow-management baselines on exactly the same
  eligible rows as every method. Port useful saved-run analysis without its
  independent score-only routing logic.
  Verify: a hand-counted confusion matrix and the 2026 management baseline
  above reproduce exactly; empty prediction subsets cannot inflate coverage.
- [ ] **Report the primary and business metrics.** Owner: evaluation. For
  each method, report MOT precision, recall, F1, TP, FP, FN, and the number of
  management-FOR/NBIM-MOT cases found. Count only automatic decisions in
  automatic MOT recall, including the business-value breakdown.
  Verify: review cases are not counted as automatically caught MOT votes.
- [ ] **Report human workload and explanation quality.** Owner: evaluation.
  Include automatic coverage, review count, true MOT votes entering review,
  valid policy-citation rate, and sourced-required-fact coverage. Identify the
  denominator for each measure. Label assumed perfect human review as an
  upper bound unless actual reviewer outcomes are collected.
  Verify: automatic + review counts equal the complete eligible population;
  invalid or irrelevant citations do not count merely because an ID is present.
- [ ] **Evaluate comparisons against the right target.** Owner: evaluation.
  Keep the historical model and rule-check disagreement metrics labeled as
  such. Define how any disagreement score maps to a three-way vote using
  `mgmt_rec`, then evaluate that method against actual `nbim_vote == "MOT"`.
  Verify: management-MOT/NBIM-FOR and abstention cases are handled explicitly;
  equal positive counts are not mistaken for identical target labels.
- [ ] **Implement `src/run.py` and prove the first vertical slice.** Owner:
  integration. Connect clean proposal -> policy -> required company facts ->
  Jev -> evidence/probability gate -> prediction log -> evaluator-only label
  join. Provide an offline replay mode using saved real responses.
  Verify: one supported proposal yields a fully sourced recommendation, and
  one missing-evidence proposal yields review, from the documented command.

## P2: Validate operation, robustness, and the final comparison

Run this stage after the integrated slice and evaluator pass their checks.
Existing cache replays establish reproducibility, not live request latency.

- [ ] **Run a representative pilot of about 100 proposals.** Owner:
  integration + evaluation. Keep meetings intact and cover supported types,
  evidence gaps, management-MOT cases, and review paths. Keep any label-enriched
  diagnostic sample separate from the representative sample.
  Verify: save scope, counts, model calls, cache hits, cost, failures, and
  end-to-end median and 95th-percentile latency, with cold/warm cache
  identified.
- [ ] **Run the resistance test on the actual integrated pipeline.** Owner:
  decision + integration. Inject the required instruction into proposal text
  and into a retrieved company document. Reuse the existing clean/attacked
  pairing, fake-guideline attacks, and harmless-text controls.
  Verify: save vote/probability/route changes and report observed failures,
  including attacks that pass keyword guards. Do not report the separate
  Microsoft experiment as Jev resistance performance.
- [ ] **Run and save the fixed 2026 comparison.** Owner: evaluation. Use
  unchanged development-selected settings and cached, dated sources. Include
  all 1,539 eligible rows, routing unavailable evidence to review. Report any
  narrower supported subset separately with its coverage.
  Verify: baseline, automatic metrics, review workload, citation/fact quality,
  latency, and model-call totals all come from the same saved decisions.
  Disclose earlier 2026 experiments and any remaining evaluation limitations.
- [ ] **Complete focused regression checks.** Owner: all module owners.
  Cover record/key validation, label isolation, frozen history, bounded policy
  lookup, source dates/identity, missing/conflicting evidence, invalid model
  responses, review accounting, and cached replay.
  Verify: the integrated test command passes without live API access; real
  model results and dry-run stub results are clearly separated.
- [ ] **Resolve the optional N-PX ingestion failures if retaining that path.**
  Owner: data. Align `hent_xml()` with its tests and correct duplicate ancestor
  parsing, or document that the optional downloader is outside the delivered
  API-vote workflow. Verify: if advertised as supported, all five existing
  `test_hent_npx.py` tests pass and the resulting votes are checked separately.

## P2: Deliver the demo and reproducible handoff

Finish the artifacts required by the architecture without adding unrelated
product features.

- [ ] **Prepare the agenda demo.** Owner: integration. Show each proposal's
  recommendation, policy citation, dated supporting fact, probability, and
  automatic/review status. Clearly identify the management baseline. Include
  one supported case, one uncertain case, and the resistance-test outcome.
  Verify: the full demonstration fits five minutes and can replay from cache.
- [ ] **Update the README and setup instructions.** Owner: integration.
  Document actual preprocessing/run/evaluation commands, required dependencies,
  environment-variable names, cached replay, supported scope, split, and
  output locations. Correct stale architecture paths, update the claim that
  the agent is unbuilt, and link this checklist.
  Verify: another teammate can reproduce the principal metric from a clean
  checkout with one documented evaluation command.
- [ ] **Write the one-page response.** Owner: whole team. Include the problem,
  method, management baseline, measured MOT results, review workload, sourced
  explanations, robustness findings, limitations, and next steps. Distinguish
  the API holdout from the optional N-PX pay experiment.
  Verify: every quoted number matches saved reports; address problem
  understanding and evaluation (30% each), explanation and robustness (20%
  each), as specified in the architecture.
- [ ] **Package the final reproducible run.** Owner: integration. Share the
  integrated revision, fixed split/settings, prediction-only log, separate
  labels/evaluation report, replay responses, and required source cache or
  retrieval instructions.
  Verify: no required file exists only as uncommitted local work; the demo,
  README command, and one-page response describe the same implementation.

## Audit verification

The following checks were executed during this assessment. Branch experiments
ran from isolated temporary copies, with decision-model cache misses blocked;
no branches were merged and no paid model calls were made.

- Current benchmark: **9 tests passed**.
- Local evidence prototype: **4 tests passed**.
- `marie` Jev MVP: **12 tests passed**.
- Existing N-PX downloader: **5 tests failed** (3 errors, 2 assertion failures).
- Prepared-data key alignment, uniqueness, label exclusion, split membership,
  baseline counts, and saved Jev result labels were independently checked.
- Cached rule-check/resistance experiments and the pay model reproduced
  offline. The resistance audit's extra optional N-PX false-alarm dataset was
  not included in the temporary copy.
- Live API behavior, original-PDF citation accuracy, a full document-backed
  Jev run, and final delivery artifacts remain unverified/open as listed above.
