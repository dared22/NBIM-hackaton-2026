# Model card: NBIM voting agent, Case 1

Every number below is reproduced by `python3 src/run.py` and written to
`data/outputs/results.md`.

## What it is for

It suggests a vote on each proposal at a shareholder meeting, with a
probability, the reasons, the NBIM guideline they relate to and a link to the
evidence. It sorts proposals into three bands: follow the board, vote against
the board, or send to a person. It supports the analyst who decides; it does
not cast votes.

## Target

"NBIM voted against the board's recommendation", yes or no.

Why this and not "NBIM voted MOT": on shareholder proposals the board usually
recommends against, so NBIM voting MOT there means agreeing with the board.
The decision that takes human judgement, and that NBIM must explain in
writing, is the vote against the board. For management proposals the two
targets are the same. The decisions file states the suggested vote as FOR or
MOT, so either target can be scored from it.

## Two models

| | History model | Pay model |
|---|---|---|
| Covers | All proposal types, 37 countries | Executive pay votes at US filers |
| Inputs | NBIM's earlier votes: by proposal type, country, company and item | Last season's vote, plus company facts from the proxy filed before the meeting: CEO pay, pay against the year before, CEO against other executives, pay against the median of similar companies, pay growth against shareholder returns, CEO change |
| Answer key | `data/dirty/real_votes.csv` (organisers) | `data/dirty/nbim_pay_votes.csv` (Norges Bank's SEC Form N-PX filings) |
| Train / test | 2019-2025 / 2026 | Seasons 2024-2025 / season 2026 |
| Method | Logistic regression, standard library only | Logistic regression, standard library only |

## Results on the test year

Baseline: "vote the same as last time at this company". "Always follow the
board" finds no against-votes by construction.

| | Against-votes | Baseline finds | Model finds, same number of flags | 
|---|---|---|---|
| History model, all proposal types | 66 | 22 (38 flags) | 24 |
| Pay model, US pay votes | 114 | 42 (97 flags) | 71 |

Pay model at 97 flags: precision 73% (95% interval 63-82%), recall 62%
(54-70%). Baseline: precision 43% (34-53%), recall 37% (28-46%).

The history model ties the baseline, also when the test is repeated for
2022-2026 (150 against 155 hits). Two thirds of NBIM's against-votes are on
items it never opposed before at that company, and vote history finds 13% of
those.

Bands, pay model: 72% of votes fall in "follow the board" with a 2.2% against
rate. A person who reads the other 28% sees 83% of the against-votes.

Confidence, pay model: where it says 83%, 80% were against. Where it says 24%,
13% were against, so it is too confident in that range.

## What was tried and did not help

- A decision model (Microsoft-Decision-1) checking guideline sections against
  the proposal wording: found nothing the history model had not.
- Word-level text features in the history model.
- In the pay model: shareholder return against the company's own peer group,
  support at the previous pay vote, and how often the proxy mentions one-off
  awards. Tested on the training seasons and left out.
- The last pay model change (pay against similar companies, pay against
  returns) improved the training-season comparisons but did not move the 2026
  result beyond noise: 71 hits against 73 before, at 97 flags.

## Checks against leakage

- Time split everywhere. No random split.
- History inputs use only votes from earlier meeting dates, frozen before the
  test year.
- Every proxy used was filed 21 to 90 days before its meeting. An automatic
  test fails if one is filed on or after the meeting date.
- Inputs for the pay model were chosen on the training seasons. The 2026
  season was scored three times, once per model version; all three results
  are in the commit history.
- The decision model never receives the company name, NBIM's vote or NBIM's
  rationale. An automatic test checks the request.

## Resistance test

Text was appended to real 2026 proposals: four instruction attacks, one
persuasion text without trigger words, one harmless sentence.

- History model: any added text cuts its against-flags from 24 to 8, because
  its "same item as last time" lookup matches on exact wording.
- Decision model: a fake guideline quote removes 13 of 39 against-flags. A
  harmless sentence removes 4 of 39, so part of this is instability.
- Guardrail (plain code): all four instruction attacks get a security flag and
  go to a person; no false alarms on 66,663 real ballot texts. Persuasion
  without trigger words gets past the keyword check. Only appended text was
  tested.

## Limits

- The pay model covers US pay votes only: about 4% of proposals and 9% of
  against-votes in the organisers' file. For other countries and proposal
  types there is no open source of company facts in machine-readable form.
- 88 of 1,200 test votes have no pay figure; the model finds none of the 9
  against-votes among them.
- Three filings tag pay a thousand or a million times too large. Values of a
  billion dollars or more are scaled down when read. Other tagging errors may
  remain; votes with implausible figures are sent to a person.
- The 2025 guidelines are used for all years.
- Two training seasons for the pay model. A second check (train on 2024, test
  on 2025, company facts only) gives 69 hits against 46 for the baseline.
- The 25 million dollar level is from NBIM's first-half 2025 voting review. We
  found no statement for 2026.

## Sources

- NBIM votes: organisers' `real_votes.csv`; Norges Bank Form N-PX,
  https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1374170&type=N-PX
- Company facts: SEC EDGAR proxy statements and XBRL API, https://www.sec.gov/edgar
- Guidelines: NBIM Global voting guidelines 2025,
  https://www.nbim.no/contentassets/01a7ee19b5d84a73a67a365e76a0fb01/global-voting-guildeines_2025.pdf
- NBIM voting review, first half 2025,
  https://www.nbim.no/en/responsible-investment/voting/voting-reviews/2025/our-voting-first-half-2025/
- ISS pay-for-performance method,
  https://www.iss-stoxx.com/file/policy/2021/americas/Pay-for-Performance-Mechanics.pdf

## AI tools used

Claude Code (Anthropic) for research, code and evaluation. Microsoft-Decision-1
through OpenRouter for the guideline rule check and the resistance test.
