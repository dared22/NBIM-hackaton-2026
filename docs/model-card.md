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
targets are the same. The decisions file states the suggested vote as FOR,
MOT or AVSTÅ, so either target can be scored from it.

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
| B | One-line rule: against if CEO pay is 25 million dollars or more | 155 | 83 | 72 | 54% | 73% |
| B | Pay model, as many flags as the one-line rule | 155 | 87 | 68 | 56% | 76% |
| B | Pay model at its own cut-off | 110 | 79 | 31 | 72% | 69% |

The one-line rule is the strongest simple comparison, and it needs the same
pay figure the model uses. Against it the model's gain is in precision, not
in how many against-votes it finds: with as many flags it finds 87 against
83, and at its own cut-off it finds 79 with 31 false alarms where the rule
has 72. The larger gap, 72 against 42, is against "same as last season",
which uses no company facts.

Brackets are 95% intervals from resampling votes.

The history model ties the baseline, also when the test is repeated for
2022-2026 (150 against 155 hits). Two thirds of NBIM's against-votes are on
items it never opposed before at that company, and vote history finds 13% of
those.

Who decides, on the test sets (from `data/outputs/decisions_2026.csv`):

| | File A | File B |
|---|---|---|
| Decided automatically | 75% | 74% |
| Sent to a person | 25% | 26% |
| Against-votes suggested by the tool or sent to a person | 79% | 90% |
| Against-votes the tool followed the board on by itself | 21% | 10% |
| Precision of the automatic "against" suggestions | 71% | 70% |

One answer per proposal. The annual pay vote of 36 US companies is in both
files. The tool used to answer those twice, and the two answers could differ.
On the 81 such proposals in 2024-2026 the pay model finds 5 of the 8
against-votes with 7 flags, and the history model finds 2 with 6 flags
(`src/agent/pay_overlap.py`). For 2024 and 2025 the pay model's scores come
from a model that had not seen the company, which is not a time split. 2026 is
the real test and has no against-votes among them: there the pay model raises
one false alarm where the history model raises two. These proposals in file A
now get the pay model's answer, which took the automatic "against"
suggestions on file A from 37 (25 right) to 36 (25 right).

Low-information gate: the tool never follows the board on its own when it has
nothing to go on. A pay vote with no pay figure, a company it has never seen,
a missing board recommendation and figures that look wrong all go to a person.
When 88 test votes had no pay figure, they sat in the automatic pile with a
10% against rate, against 1% where the figure was known, and the gate caught
them. After more companies were linked (see below) only 27 test votes lack a
figure. The gate now moves 75 votes on file B to a person, 3 of them
against-votes.

Low support at the last pay vote (rule 3.3.5). A teammate's review of the 2026
misses suggested four fixes. Because they were found by looking at the test
year's answers, each was tested on the training seasons instead, on the votes
the model would have waved through (1,885 votes, 31 against, 1.6%):

| Suggested reason to send a vote to a person | Votes | Against | Rate |
|---|---|---|---|
| The last pay vote had under 70% support | 36 | 4 | 11% |
| CEO pay of 20 to 25 million dollars | 41 | 2 | 5% |
| More than one CEO paid in the year | 116 | 3 | 3% |
| NBIM voted against last season | 2 | 0 | - |
| Other executives paid more than the CEO | 0 | 0 | already sent to a person |

Only the first stands out, and it is also what rule 3.3.5 says. It is now a
reason to send the vote to a person, with the sentence from the proxy. It
never changes the score. On 2026 it sends 20 more votes to a person and one
of them is an against-vote. A softer step from 20 to 25 million dollars had
already been tested as a model input and gave nothing.

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

## Director elections at US companies: an AI model reads the facts, code applies the rules

`src/agent/fetch_board_facts.py` and `src/agent/board_rules.py`. This is the
method the industry is moving to (JPMorgan's Proxy IQ, ISS PolicySteward,
Tumelo's ProxyBeacon): the company's own filing goes in, facts with citations
come out. Ours keeps two things apart:

1. **An AI model only reads.** For each US meeting it gets the board passages
   of the proxy filed before the meeting, the names on the ballot and fixed
   questions: is the nominee independent, an executive of this company, its
   CEO, its chair, on which committees, on which other listed boards, a
   founder; how many independent directors and women the board has. It never
   sees NBIM's rules or votes. Every answer needs a quote, and the quote is
   checked against the text. Model: Claude Haiku 5.5, about 1.50 dollars for
   all 214 meetings.
2. **Code applies NBIM's rules** to those facts (1.1.1, 1.1.2, 1.2.1, 1.2.2,
   1.2.3, 1.3.1, 2.1.1, 2.1.2, 2.3.1), so the same facts always give the same
   answer and each answer names its rule.

What the reader delivered: the proxy was found for 214 of 218 meetings, and
1,706 of 1,742 nominees (98%). Independence is answered for 98% of them, and
90% of those answers have a quote that was found in the text. On "chair and
CEO" the proxy and the SEC's insider filings, two independent sources, agree
on 98.9% of nominees.

Three reader mistakes were found and fixed, two by checking its answers
against NBIM's votes and one by the second reader (below). It took an executive of another company (a director who is CEO
elsewhere) for an executive of this one: the question was sharpened, and code
now overrules "executive" when the company calls the same person independent.
It also applied an attendance sentence about one director to another: an
attendance quote must now contain the nominee's surname.

What NBIM does when each rule's condition is met, all years:

| Signal | Fires | NBIM against | Share |
|---|---|---|---|
| 1.3.1 chair who is also CEO, not a founder (proxy) | 36 | 32 | 89% |
| 1.3.1 chair and CEO (SEC filings) | 38 | 32 | 84% |
| 1.3.1 chair and CEO who founded the company (proxy) | 11 | 4 | 36% |
| 2.1.1 chairs this board and another company's board (proxy) | 18 | 10 | 56% |
| 2.1.1 more than five boards (SEC filings) | 12 | 6 | 50% |
| 2.1.1 more than five boards (proxy) | 8 | 3 | 38% |
| 1.2.1 executive on the pay committee (proxy) | 3 | 2 | 67% |
| 2.3.1 nomination chair, fewer than two women on the board (proxy) | 12 | 4 | 33% |
| 2.1.2 attended under 75 percent (proxy) | 8 | 1 | 12% |

NBIM votes against 5.3% of all US director nominees, so every one of these is
a real signal, but only the first is close to a rule in practice. The founder
exception is in the guidelines' own text ("we may support this for a limited
period"), and it shows in the votes. Attendance is applied with exceptions
(illness, a director who joined mid-year). "Two women" was not NBIM's practice
in 2019-2020 (0 of 6) and is from 2021 (4 of 6). Rules 1.1.1 and 1.2.3 never
fire: every US board in the file states a majority of independent directors.

How reliable the reader is (`src/agent/board_reader_check.py`). A second,
stronger model (Claude Sonnet 5.5) read a random sample of 16 meetings again,
with exactly the same passages, names and questions: 122 nominees. Where both
answered, the two models gave the same answer on 1,442 of 1,469 facts
(98.2%): independence 117 of 117, CEO 122 of 122, chair 121 of 121, audit and
pay committee 122 of 122 each. NBIM's rules would fire on the same nominees
for 120 of 122. The two that differ are a count of other boards (the first
reader counted private companies) and a count of women on one board. The
check also exposed a third reader mistake, now corrected in code: "founder"
was answered yes for people who founded some other firm, so the quote must
now name this company. After the corrections the two readers do not disagree
on any fact a rule rests on in the sample. Agreement between two models is
not the same as being right, nobody checked the answers by hand, and 16
meetings is a small sample.

The link between the pay vote and the director votes was tested too (rule
3.2.2: no support for pay committee members when the board has not answered
concerns about pay). At the 16 US meetings in file A where NBIM voted against
pay, it also voted against 2 of the 8 pay committee chairs and 2 of the 16
other members. Where it supported pay it opposed 1% and 3% of them. So there
is a link, but 8 chairs is too few to act on, and the pay vote at the same
meeting is not known beforehand. The reviewer is shown the fact; the tool
does not act on it.

When the tool acts on its own. A signal has to earn trust: the tool suggests
"against" by itself only when NBIM followed that signal at the last two
meetings where it fired. Before that, and after any miss, the nominee goes to
a person with the fact and its quote. Only votes at earlier meetings are used.

| Method, all years (93 against-votes) | Flags | Hits | False alarms | Precision |
|---|---|---|---|---|
| Same as last time | 73 | 36 | 37 | 49% |
| Before: two rules on SEC filings, with the drift monitor | 43 | 37 | 6 | 86% |
| Now: trusted signals, the tool acts alone | 45 | 39 | 6 | 87% |

Another 50 nominees go to a person because a signal fired without trust, and
12 of them are against-votes. So 51 of the 93 against-votes (55%) are either
suggested or put in front of a person with the fact, the rule and the quote.
In 2026 the tool makes no automatic suggestion on directors and sends 11
nominees to a person, one of them the year's only against-vote among US
directors (Franklin Myers, who chairs two boards). The earlier version made
one wrong automatic suggestion that year.

The honest size of this: the gain in automatic hits is small, 39 against 37.
What changed is that every US director nominee now comes with checked facts
and quotes, the tool no longer acts on a written rule NBIM has stopped
following, and 42 against-votes remain that no signal points at. 24 of those
cite "board decisions and conduct" (14 at one company in one year), which is a
reaction to something the company did and is not stated in a proxy.

Limits: 36 companies and 93 against-votes, so every share above rests on few
cases. Which facts to ask for, and which two judgement facts may earn trust,
was decided after looking at all years, 2026 included; the trust rule itself
was not tuned. "Developed market, large or mid cap" is assumed for every
company. "Independent" is the company's own statement, and NBIM makes its own
assessment: at Fluence Energy in 2025 it opposed eight directors citing board
independence, one of whom the company calls independent, on a board that
states exactly the one third the guidelines ask of a controlled company.

## Proposals whose wording decides the vote: written rules applied to the title

`src/agent/proposal_rules.py`. No training and no AI model. Some of NBIM's
rules are about what a proposal asks for, and the title says it: declassify
the board (3.1.2), majority voting in director elections (3.1.5), proxy
access (3.1.8), the right to act by written consent (4.2.2), separate chair
and CEO (1.3.3), abolish an anti-takeover measure such as a supermajority
requirement (6.2-AT.3), no support for a new poison pill (6.2-AT.2), no
support for the agenda item "other business" (5.2.2, which names that item in
its own text), and no support for appointing one person as both chair and CEO
or managing director (1.3.1, where the title says so, as in "Approve
Appointment of ... as Chairman and Managing Director").

Scored on every proposal in file A, all countries, 2019-2026. 79 proposals
fall under one of these rules, and NBIM voted as the rule says on all 79.
The rule means a vote against the board on 72 of them (the board recommended
the opposite), and all 72 were against-votes, including 9 of 9 in 2026.

| Rule | Proposals | NBIM voted as the rule says |
|---|---|---|
| 5.2.2, "other business" | 44 | 44 |
| 6.2-AT.3, abolish supermajority or takeover defence | 11 | 11 |
| 4.2.2, written consent | 6 | 6 |
| 3.1.2, declassify the board | 5 | 5 |
| 1.3.1, one person appointed chair and CEO or managing director (India) | 6 | 6 |
| 1.3.3, separate chair and CEO | 3 | 3 |
| 6.2-AT.2, poison pill | 2 | 2 |
| 3.1.5 and 3.1.8, majority voting and proxy access | 2 | 2 |

"Same as last time" already covers 45 of the 72, because the same item comes
back each year. The other 27 are first-time items it cannot flag, and all 27
were against-votes. On the 150 shareholder proposals (50 against the board):

| Method | Flags | Hits | False alarms | Precision | Recall |
|---|---|---|---|---|---|
| Same as last time | 12 | 11 | 1 | 92% | 22% |
| Rules from the wording | 20 | 20 | 0 | 100% | 40% |
| Same as last time, or a rule | 25 | 24 | 1 | 96% | 48% |

The tool cites the same guideline section as NBIM in 61 of the 64 hits where
NBIM gave a reason. The three that differ are appointments of a chair and
managing director, where NBIM cited board independence instead.

The appointment rule was added last, after the others, and none of its six
cases is in 2026, so it does not change the test-year result. With a looser
wording that also takes "Chairman and Whole-time Director" and "Vice
Chairman", NBIM opposed 9 of 17, which is why the pattern is kept strict.

Changes to governing documents (rule 4.3.2, "not in the best interest of
shareholders") were looked at and left with a person. The titles that sound
like a cut in shareholder rights are mostly ones NBIM supports: limiting
officers' liability 0 of 8 against, virtual-only meetings 1 of 19. The ones
it opposed in 2026 (moving incorporation from Delaware to Texas, a higher
threshold for shareholder proposals) had no earlier cases to learn from, and
a rule written for them now would be written with the answer in hand.

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

## Confidence and routing: when the tool asks a person

`src/agent/routing.py`, on NBIM's vote file. Every test year from 2022 to 2026
is scored by a model fitted on earlier years only.

- **Is the confidence honest?** Below 10% the stated probability matches what
  happened (the tool says 3.3%, 3.2% were against-votes). Between 10% and 70%
  the tool says more than what happened: a stated 54% was an against-vote 41%
  of the time. A correction learned from earlier years was better in 2 of 5
  years, so it is not used. A reviewer should read the middle band as "worth
  a look", which is how the tool uses it.
- **The 5% level.** Below it the tool follows the board on its own, and it is
  then wrong about 2% of the time (1.9% in 2022-2025, 1.6% in 2026). Lowering
  the level to 3% means a person reads 32% of proposals instead of 20%, and
  the share of against-votes waved through falls from 26% to 19% (2022-2025).
  In 2026 the same change would have cut the waved-through against-votes from
  18 to 3, but the level may not be chosen on the test year. The 5% level is
  kept. It is a choice between reading time and missed against-votes, and the
  table in `results.md` is what to choose from.
- **Can anything pick out the ones waved through?** Two tests: wording never
  seen before, and another item at the same meeting that the tool flags or is
  unsure about. No group stands out (0.5% to 3.4% against in every group in
  2022-2025). The against-votes the tool waves through look like the other
  proposals in the vote file. This is the same limit as before: without a
  fact about the company, the vote file does not hold the answer.
- **Abstain.** NBIM abstained 68 times in the file. 28 of those are on items
  with no board recommendation (Brazil, cumulative voting) and are outside
  the target. 39 are votes against the board, and most of them follow a
  market habit: in Denmark 13 of 13 against-votes on directors were cast as
  abstentions, and in Taiwan 20 of 27 against-votes across several item types. The tool learns the habit from earlier years and then
  writes its "against the board" suggestion as AVSTÅ. Given a vote against
  the board, the rule said abstain 19 times in 2021-2025 and was right 18
  times. In 2026 it finds none of the 5 abstentions (Vietnam and Switzerland,
  no such history) and fires once, on a suggestion that was a false alarm
  anyway.

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
- In the pay model, a look at the misses on the training seasons: the model
  finds 92% of its hits where the CEO is paid 25 million dollars or more. The
  against-votes it misses are mostly at 10 to 25 million (median 17 million).
  Tested there and left out, no gain: "compensation actually paid" (three
  forms), finer steps in pay size (15, 20 and 35 million), total pay over the
  years in the table, and pay of 15 to 25 million combined with pay well above
  similar companies. What separates these votes is likely how the pay is
  built (lock-in, performance terms), which the tagged figures do not show.
  The 2026 season was not scored again.
- How the CEO's pay is built, read from the proxy text by an AI model
  (`src/agent/fetch_pay_structure.py`, Claude Haiku 5.5, every answer with a
  quote that is checked against the text). Ten questions: one-off awards, the
  performance-based share of equity, lock-in years, holding after vesting,
  performance period, bonus against target, pay raised by discretion,
  previous say-on-pay support, changes after shareholder feedback, CEO
  change. Pilot on 299 proxies from the training seasons at CEO pay of 10 to
  25 million dollars (all 89 against-votes and 210 others). NBIM votes
  against 7% of the time in this band, and for most answers that barely
  moves: lock-in of three, four or five years 5%, 6%, 6%; a one-off award
  8% against 5% without. Added to the pay inputs the answers move the hits
  in the sample from 51 to at most 53 of 89
  (`src/agent/pay_structure_test.py`). NBIM's stated reason for these votes
  is lock-in and how pay is built, but its votes at this pay level do not
  follow the ten things we could read.
- The same reader where the CEO is paid 25 million dollars or more (377
  proxies, all seasons). On the training seasons three answers do separate
  the votes there: a one-off award (NBIM against 68% with one, 31% where the
  proxy says there was none), the performance-based share of the CEO's equity
  (41% against at three quarters or more, 89% where none is stated), and
  support at the last pay vote (27% against at 90% or more, 7 of 7 under
  70%). As three inputs they improved both training-season comparisons
  (average precision 0.658 to 0.675 and 0.544 to 0.567), so the 2026 season
  was scored with them, once. It came out worse: average precision 0.660
  against 0.698, the same 72 hits at 97 flags, and 81 hits with 54 false
  alarms at its own cut-off against 79 with 31. The pay model is kept as it
  was. The reader's findings are shown on 152 pay decisions as evidence with
  their quotes, and are not part of the score. That also keeps one property
  intact: no text from a company filing can move the pay score.
- A non-linear pay model (small boosted trees, on the model's inputs and on
  the raw figures) in place of the logistic model. On the training seasons it
  finds 73 against-votes where the logistic model finds 76 at the same number
  of flags, with average precision 0.618 against 0.601. No clear gain, and
  its reasons are harder to state, so the logistic model is kept.
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
  season was scored five times: once for each of three model versions, once
  more after 239 more companies were linked with no change to the model, and
  once with three inputs read from the proxy text, which were rejected because
  that result was worse. The reported numbers are from the model as it stood
  before that fifth scoring. All five results are in the commit history or in
  `data/outputs/results.md`.
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
Claude Sonnet 5.5 through OpenRouter read 16 meetings a second time, to
measure how often two models agree on the facts. Claude Haiku 5.5 through OpenRouter reads proxies in two places: board and
nominee facts for US director elections (214 meetings; the facts are used by
the director rules, which are plain code) and how CEO pay is built (675
proxies; shown as evidence, not used by any model). The model only reads. It never sees NBIM's
votes or rules, and it does not decide a vote.
