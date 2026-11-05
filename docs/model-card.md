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

## Two models and a rule engine

The rule engine for US director elections is described further down.

| | History model | Pay model |
|---|---|---|
| Covers | All proposal types, 37 countries | Executive pay votes at US filers |
| Inputs | NBIM's earlier votes: by proposal type, country, company and item | Last season's vote, plus company facts from the proxy filed before the meeting: CEO pay, pay against the year before, CEO against other executives, pay against the median of similar companies, pay growth against shareholder returns, CEO change |
| Answer key | `data/dirty/real_votes.csv` (organisers) | `data/dirty/nbim_pay_votes.csv` (Norges Bank's SEC Form N-PX filings) |
| Train / test | 2019-2025 / 2026 | Seasons 2024-2025 / season 2026 |
| Method | Logistic regression, standard library only | Logistic regression, standard library only |

## Results on the test year

The two models are scored on two different files. They are not parts of one
total, which is why the second file has more against-votes than the first.

| | File A: all proposal types | File B: US executive pay votes |
|---|---|---|
| Source | Organisers' `real_votes.csv` (NBIM's website records) | Norges Bank's SEC Form N-PX filings |
| Companies | 194, in 37 countries | 1,786, US filers |
| Test set | 2026: 1,539 proposals | Season 2026: 1,200 pay votes |
| Against the board in the test set | 66 (4.3%) | 114 (9.5%) |
| Model | History model | Pay model |

Baseline: "vote the same as last time at this company". "Always follow the
board" finds no against-votes by construction. Each model is compared with the
baseline at the same number of flags.

| File | Method | Flags | Hits | False alarms | Precision | Recall |
|---|---|---|---|---|---|---|
| A | Always follow the board | 0 | 0 | 0 | 0% | 0% |
| A | Same as last time | 38 | 22 | 16 | 58% | 33% |
| A | History model | 38 | 24 | 14 | 63% | 36% |
| B | Always follow the board | 0 | 0 | 0 | 0% | 0% |
| B | Same as last season | 97 | 42 | 55 | 43% (34-53%) | 37% (28-46%) |
| B | Pay model | 97 | 72 | 25 | 74% (65-83%) | 63% (55-71%) |

Brackets are 95% intervals from resampling votes.

The history model ties the baseline, also when the test is repeated for
2022-2026 (150 against 155 hits). Two thirds of NBIM's against-votes are on
items it never opposed before at that company, and vote history finds 13% of
those.

Who decides, on the test sets (from `data/outputs/decisions_2026.csv`):

| | File A | File B |
|---|---|---|
| Decided automatically | 76% | 75% |
| Sent to a person | 24% | 25% |
| Against-votes suggested by the tool or sent to a person | 77% | 89% |
| Against-votes the tool followed the board on by itself | 23% | 11% |
| Precision of the automatic "against" suggestions | 68% | 70% |

Low-information gate: the tool never follows the board on its own when it has
nothing to go on. A pay vote with no pay figure, a company it has never seen,
a missing board recommendation and figures that look wrong all go to a person.
When 88 test votes had no pay figure, they sat in the automatic pile with a
10% against rate, against 1% where the figure was known, and the gate caught
them. After more companies were linked (see below) only 27 test votes lack a
figure. The gate now moves 75 votes on file B to a person, 3 of them
against-votes.

Company coverage. 239 companies in the pay votes were first left without a
link to the SEC, because the SEC's current ticker list only holds companies
listed today and writes some names differently (LOWES, HORTON D R). They were
linked through the company names in insider filings
(`src/agent/link_companies.py`). CEO pay is now known for 98% of the test
votes, up from 93%. This raised the comparison scores on the training seasons
and gave 72 hits at 97 flags on 2026, against 71 before.

Confidence, pay model: where it says 84%, 78% were against. Where it says 24%,
14% were against, so it is too confident in that range.

## Director elections at US companies: written rules applied to facts

`src/agent/director_rules.py`. No training and no AI model. NBIM's guidelines
contain clear-cut rules about directors. Two of them can be checked against
the SEC's records of who is a director or officer of which company, and with
what title (Insider Transactions Data Sets, Forms 3, 4 and 5):

- Rule 1.3.1: "We will not support the election of a chairperson who is also
  the CEO of the company."
- Rule 2.1.1: no support for a director "who sits on more than five boards".

Scored on all US director elections in file A: 1,742 nominees at 36 companies,
2019-2026, 93 against the board. Because nothing is fitted, every year is a
test year. 95% of nominees were matched to a person in the SEC data.

| Method | Flags | Hits | False alarms | Precision | Recall |
|---|---|---|---|---|---|
| Same as last time | 73 | 36 | 37 | 49% | 39% |
| Rule 1.3.1, chair who is also CEO | 38 | 32 | 6 | 84% | 34% |
| Rule 2.1.1, more than five boards | 12 | 6 | 6 | 50% | 6% |
| Either rule | 50 | 38 | 12 | 76% | 41% |
| Same as last time, or either rule | 88 | 47 | 41 | 53% | 51% |

- The rules find 11 of the 57 against-votes on people NBIM had not opposed
  before. "Same as last time" finds none of those by construction.
- The tool cites the rule NBIM itself gave: NBIM cited section 1.3 for 28
  against-votes, and rule 1.3.1 fired on 25 of them.

Policy and practice. From 2019 to 2024 NBIM voted against every nominee titled
chair and CEO at these companies: 28 of 28. In 2025 it was 4 of 5. In 2026 it
was 0 of 5, including four people it had opposed every year before. The 2025
guidelines we were given still contain rule 1.3.1. So in 2026 NBIM's practice
at these companies no longer followed that written rule, and a tool that
applied it blindly would have been wrong five times.

Drift monitor. Each rule is watched: when NBIM has supported the board the
last two times a rule fired, the rule is suspended and its later cases go to a
person. With the monitor, 2019-2025 gives 37 hits in 42 automatic suggestions
(88%). In 2026 it makes one wrong suggestion, then suspends the rule and sends
the other four cases to a person.

Limits: 36 companies. Board counts cover US-listed companies only and are a
lower bound, which is why rule 2.1.1 misses 6 of NBIM's 9 "time commitment"
votes. A title is what the company wrote on the form, so a CEO who chairs the
board but is titled only "CEO" is missed (3 of NBIM's 28). Independence and
committee membership are not in this data, so rules 1.1 and 1.2 are not
covered. The monitor uses NBIM's own earlier votes, which NBIM would have.

## Proposals whose wording decides the vote: written rules applied to the title

`src/agent/proposal_rules.py`. No training and no AI model. Some of NBIM's
rules are about what a proposal asks for, and the title says it: declassify
the board (3.1.2), majority voting in director elections (3.1.5), proxy
access (3.1.8), the right to act by written consent (4.2.2), separate chair
and CEO (1.3.3), abolish an anti-takeover measure such as a supermajority
requirement (6.2-AT.3), no support for a new poison pill (6.2-AT.2), and no
support for the agenda item "other business" (5.2.2, which names that item in
its own text).

Scored on every proposal in file A, all countries, 2019-2026. 73 proposals
fall under one of these rules, and NBIM voted as the rule says on all 73.
The rule means a vote against the board on 66 of them (the board recommended
the opposite), and all 66 were against-votes, including 9 of 9 in 2026.

| Rule | Proposals | NBIM voted as the rule says |
|---|---|---|
| 5.2.2, "other business" | 44 | 44 |
| 6.2-AT.3, abolish supermajority or takeover defence | 11 | 11 |
| 4.2.2, written consent | 6 | 6 |
| 3.1.2, declassify the board | 5 | 5 |
| 1.3.3, separate chair and CEO | 3 | 3 |
| 6.2-AT.2, poison pill | 2 | 2 |
| 3.1.5 and 3.1.8, majority voting and proxy access | 2 | 2 |

"Same as last time" already covers 45 of the 66, because the same item comes
back each year. The other 21 are first-time items it cannot flag, and all 21
were against-votes. On the 150 shareholder proposals (50 against the board):

| Method | Flags | Hits | False alarms | Precision | Recall |
|---|---|---|---|---|---|
| Same as last time | 12 | 11 | 1 | 92% | 22% |
| Rules from the wording | 20 | 20 | 0 | 100% | 40% |
| Same as last time, or a rule | 25 | 24 | 1 | 96% | 48% |

The tool cites the same guideline section as NBIM in 58 of the 58 hits where
NBIM gave a reason.

Tested and left out: "auditor not named" (rule 5.1.2). Auditor proposals with
no firm in the title are opposed 3.2% of the time, against 1.7% where a firm
is named, so the title does not show whether the name was disclosed. Director
items that name nobody ("Elect Directors") are opposed 10 times out of 24,
which is not consistent enough for a rule.

Limits: small numbers outside "other business". The wording patterns were
written after looking at the proposal titles in the file, so they were not
written blind; the rules themselves are NBIM's. 21 of the 30 uncovered
against-votes on shareholder proposals cite sustainability reporting (section
5.3), where every rule needs judgement, so those stay with a person.

## NBIM's position papers

The case names two policy sources: the Global Voting Guidelines and the
position papers. All twelve papers are in `data/policy/position_papers.json`
(`src/agent/fetch_position_papers.py`), and `src/agent/position_papers_test.py`
tests what they add.

- **Citations: they help.** NBIM names a position paper next to many of its
  against-votes. Each decision now names the paper for the cited rule, with a
  link. On the US director rule hits, NBIM named a paper for 31 and the tool
  names the same one for 28. On the wording rules NBIM named a paper for 3 and
  the tool names the same one for all 3; where NBIM named none, the tool names
  none in 18 of 19.
- **Prediction: they do not help.** Most papers restate the guidelines. One
  new threshold could be checked: share issues without pre-emptive rights
  "should not exceed 10 percent". Only 14 of 334 share issue proposals state a
  percentage in the title, and NBIM opposed none of the 6 above 10 percent.
- **In the decision model they make it worse.** Given each section's paper as
  well as its rules, the decision model on the proposal wording goes from 13
  flags (7 hits, 6 false alarms) to 83 flags (12 hits, 71 false alarms) on
  2026, and finds one against-vote the history model had missed.

The papers describe what NBIM thinks a good board does. They are written as
"the board should", not "we will vote against", and they give no facts about
any company.

## What was tried and did not help

- A decision model (Microsoft-Decision-1) checking guideline sections against
  the proposal wording: found nothing the history model had not.
- Word-level text features in the history model.
- Giving recent years more weight in the history model (half-lives of one to
  six years). Slightly worse at every setting on test years 2022-2025.
- Merger payout votes (123 in file B, 37 against). Neither NBIM's last regular
  pay vote at the company nor the pay figures separate them, so they stay
  with a person.
- What the ballot itself reveals (the director's place on the ballot, how many
  directors are up, independence labels, wording, finer proposal types, the
  company's previous meeting). The data audit shows strong patterns, for
  example in Japan the first director listed is opposed 8.9% of the time and
  the others 0.1%. Added to the model they change nothing on test years
  2022-2025 (`src/agent/history_model.py`), so they were not adopted.
- In the pay model: shareholder return against the company's own peer group,
  support at the previous pay vote, and how often the proxy mentions one-off
  awards. Tested on the training seasons and left out.
- The last pay model change (pay against similar companies, pay against
  returns) improved the training-season comparisons but did not move the 2026
  result beyond noise: 71 hits against 73 before, at 97 flags. Linking more
  companies afterwards gave 72.

## Checks against leakage

- Time split everywhere. No random split.
- History inputs use only votes from earlier meeting dates, frozen before the
  test year.
- Every proxy used was filed 21 to 90 days before its meeting. An automatic
  test fails if one is filed on or after the meeting date.
- Inputs for the pay model were chosen on the training seasons. The 2026
  season was scored four times: once for each of three model versions, and
  once more after 239 more companies were linked with no change to the model.
  All four results are in the commit history.
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
- The appended-text defence is part of the decision pipeline, not only of the
  test script. Two end-to-end checks run on every 2026 proposal the tool
  suggests "against" on automatically: with an instruction appended, every one
  ends in human review with a security flag; with a harmless sentence
  appended, none is waved through.
- Text cannot move the pay score. The pay model's inputs are tagged figures
  and NBIM's earlier votes; nothing is built from the prose of a company's
  filing. A sentence in a proxy claiming the package meets NBIM's guidelines
  has no input to act on. A test checks this.

## Limits

- The pay model covers US pay votes only: about 4% of proposals and 9% of
  against-votes in the organisers' file. For other countries and proposal
  types there is no open source of company facts in machine-readable form.
- 27 of 1,200 test votes have no pay figure (1 against-vote among them); 66
  companies are still not linked to the SEC.
- Three filings tag pay a thousand or a million times too large. Values of a
  billion dollars or more are scaled down when read. Other tagging errors may
  remain; votes with implausible figures are sent to a person.
- The 2025 guidelines are used for all years.
- Two training seasons for the pay model. A second check (train on 2024, test
  on 2025, company facts only) gives 76 hits against 46 for the baseline.
- The 25 million dollar level is from NBIM's first-half 2025 voting review. We
  found no statement for 2026.

## Sources

- NBIM votes: organisers' `real_votes.csv`; Norges Bank Form N-PX,
  https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1374170&type=N-PX
- Company facts: SEC EDGAR proxy statements and XBRL API, https://www.sec.gov/edgar
- Director and officer roles: SEC Insider Transactions Data Sets,
  https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
- Position papers: https://www.nbim.no/en/responsible-investment/position-papers/
- Guidelines: NBIM Global voting guidelines 2025,
  https://www.nbim.no/contentassets/01a7ee19b5d84a73a67a365e76a0fb01/global-voting-guildeines_2025.pdf
- NBIM voting review, first half 2025,
  https://www.nbim.no/en/responsible-investment/voting/voting-reviews/2025/our-voting-first-half-2025/
- ISS pay-for-performance method,
  https://www.iss-stoxx.com/file/policy/2021/americas/Pay-for-Performance-Mechanics.pdf

## AI tools used

Claude Code (Anthropic) for research, code and evaluation. Microsoft-Decision-1
through OpenRouter for the guideline rule check and the resistance test.
