# Results

Produced by `python3 src/run.py`. Test year 2026; nothing from 2026 is used to fit or tune.

## Decisions

One row per proposal is in `data/outputs/decisions_2026.csv`.

### US executive pay votes (history + company facts)
- Proposals: 1200; NBIM voted against the board on 114.
- Decided automatically: 833 (69%). Sent to a person: 367 (31%).
- Automatic 'against the board' suggestions: 101, of which 68 were right (precision 67%, recall 60%).
- Against-votes inside the pile sent to a person: 37 (32% of all against-votes).
- Against-votes the tool waved through with the board: 9 (8% of all against-votes).
- With a person reading the review pile, 105 of 114 against-votes are either suggested or seen (92%).
- Low-information gate: 130 proposals the model would have waved through were sent to a person instead; 10 of them were against-votes.

### All proposal types (history, plus NBIM rules for US directors and worded proposals)
- Proposals: 1539; NBIM voted against the board on 66.
- Decided automatically: 1157 (75%). Sent to a person: 382 (25%).
- Automatic 'against the board' suggestions: 35, of which 24 were right (precision 69%, recall 36%).
- Against-votes inside the pile sent to a person: 27 (41% of all against-votes).
- Against-votes the tool waved through with the board: 15 (23% of all against-votes).
- With a person reading the review pile, 51 of 66 against-votes are either suggested or seen (77%).
- Low-information gate: 31 proposals the model would have waved through were sent to a person instead; 3 of them were against-votes.

## History model, all proposal types

`python3 src/benchmark/model.py --data data/dirty/real_votes.csv`

```text
NBIM benchmark | Test year: 2026 | Train: 11,785 | Test: 1,539
History frozen before 2026; threshold selected on 2025.
Target: disagreement with the board | Actual: 66/1539 (4.3%)

  Method                | Precision | Recall |    F1 | Accuracy | Flagged | Hits | False alarms | Missed
  ----------------------+-----------+--------+-------+----------+---------+------+--------------+-------
  Always with board     |      0.0% |   0.0% |  0.0% |    95.7% |       0 |    0 |            0 |     66
  Same as last time     |     57.9% |  33.3% | 42.3% |    96.1% |      38 |   22 |           16 |     44
  Model (top 38 scores) |     63.2% |  36.4% | 46.2% |    96.4% |      38 |   24 |           14 |     42
  Model (p >= 0.3132)   |     61.5% |  36.4% | 45.7% |    96.3% |      39 |   24 |           15 |     42

Average precision: 0.453 | Positive rate: 0.043

  Band                 | Proposals | Share | Actual against board | Against rate
  ---------------------+-----------+-------+----------------------+-------------
  likely WITH board    |      1153 | 74.9% |                   18 |         1.6%
  send to human        |       347 | 22.5% |                   24 |         6.9%
  likely AGAINST board |        39 |  2.5% |                   24 |        61.5%

Wrote 1539 scored proposals to prediksjoner_2026.csv
```

## History model, repeated for 2022-2026

`python3 src/benchmark/model.py --data data/dirty/real_votes.csv --walk-forward`

```text
Yearly holdouts | History frozen before each test year

  Year | Proposals | Against board | Flag budget | Baseline hits | Model hits | Avg precision
  -----+-----------+---------------+-------------+---------------+------------+--------------
  2022 |      1772 |           117 |          42 |            34 |         25 |         0.407
  2023 |      1761 |            83 |          56 |            26 |         30 |         0.319
  2024 |      1883 |            98 |          58 |            34 |         32 |         0.438
  2025 |      1909 |           103 |          59 |            39 |         39 |         0.467
  2026 |      1539 |            66 |          38 |            22 |         24 |         0.453
```

## Pay model, US executive pay votes

`python3 src/agent/pay_model.py`

```text
NBIM say-on-pay votes: 4260 annual pay votes at 1786 companies (US filers)
Left out: 487 frequency votes and blanks (NBIM never opposed the board on these), and 123 merger payout votes (37 against, one-off events with no history)
Train: seasons before 2026, 3060 votes, 261 against the board
Test:  season 2026, 1200 votes, 114 against the board (9.5%)
Company facts for the test votes: 1109 from the meeting's own proxy, 3 from the SEC API, 88 none. CEO pay known for 1111 (93%).
Proxies were filed 21 to 90 days before the meeting (median 43).

Results on season 2026 (95% intervals from resampling votes)
  Method                             | Precision |     95% | Recall |     95% |    F1 | Flagged | Hits | False alarms | Missed
  -----------------------------------+-----------+---------+--------+---------+-------+---------+------+--------------+-------
  Always with board                  |      0.0% |   0%-0% |   0.0% |   0%-0% |  0.0% |       0 |    0 |            0 |    114
  Same as last season                |     43.3% | 34%-53% |  36.8% | 28%-46% | 39.8% |      97 |   42 |           55 |     72
  History only, top 97               |     43.3% | 34%-53% |  36.8% | 28%-46% | 39.8% |      97 |   42 |           55 |     72
  History + company facts, top 97    |     73.2% | 63%-82% |  62.3% | 54%-70% | 67.3% |      97 |   71 |           26 |     43
  History + company facts, p >= 0.33 |     69.1% | 60%-78% |  66.7% | 58%-75% | 67.9% |     110 |   76 |           34 |     38

  'top 97' rows flag exactly as many votes as the same-as-last-season baseline, so they compare like for like.
  Average precision: history + company facts 0.669, history only 0.246, random 0.095
  Brier score (lower is better): model 0.0473, always saying 8.5% 0.0861

By what was known about the company
  What was known                   | Votes | Against | Found | Recall | False alarms
  ---------------------------------+-------+---------+-------+--------+-------------
  CEO pay known                    |  1111 |     105 |    76 |    72% |           34
  only other executives' pay known |     1 |       0 |     0 |      - |            0
  no pay figure                    |    88 |       9 |     0 |     0% |            0

New situations: against-votes at companies NBIM did not oppose last season
  72 such votes. Same-as-last-season finds 0 by construction; the model finds 37 in its top 97 and 41 at p >= 0.33.

Bands on the test season
  Band                 | Votes | Share | Real against-votes | Share of all against | Against rate
  ---------------------+-------+-------+--------------------+----------------------+-------------
  likely WITH board    |   862 |   72% |                 19 |                  17% |         2.2%
  send to human        |   228 |   19% |                 19 |                  17% |         8.3%
  likely AGAINST board |   110 |    9% |                 76 |                  67% |        69.1%

Is the confidence honest? (predicted vs actual share against)
  Predicted | Votes | Model says | Actual
  ----------+-------+------------+-------
  0%-5%     |   862 |       2.5% |   2.2%
  5%-15%    |   133 |       7.8% |   6.0%
  15%-35%   |    98 |      23.6% |  13.3%
  35%-60%   |    28 |      44.4% |  39.3%
  60%-100%  |    79 |      83.1% |  79.7%

Against rate by CEO pay, test season
  CEO total pay | Votes | Against | Against rate
  --------------+-------+---------+-------------
  under $10m    |   405 |       6 |           1%
  $10-25m       |   558 |      20 |           4%
  $25-40m       |   102 |      45 |          44%
  $40m or more  |    46 |      34 |          74%
  no CEO figure |    89 |       9 |          10%

Model weights (positive = pushes towards AGAINST)
   +1.46  prev_against   NBIM voted against this company's pay last season
   -0.66  prev_for       NBIM supported this company's pay last season
   -0.62  pay_size       size of the CEO's total pay
   +1.63  pay_25m        CEO pay is at or above the 25 million dollar level NBIM reviews more strictly
   +0.97  pay_doubled    CEO pay at least doubled from the year before
   +0.41  ceo_vs_others  CEO pay is many times the other executives' average
   +1.88  others_size    size of the other named executives' average pay
   +0.16  high_pay_lost  CEO pay of 25 million dollars or more while shareholders have lost money
   +0.48  ceo_changed    more than one CEO was paid during the year
   +0.69  pay_vs_peers   CEO pay as a multiple of the median at companies of similar industry and size
   +0.98  pay_outran_returns CEO pay has grown faster than shareholder returns over the years in the pay table

Wrote 1200 scored votes to data/outputs/pay_votes_2026.csv
```

## Pay model, how the inputs were chosen (training seasons only)

`python3 src/agent/pay_model.py --develop`

```text
Training seasons only. AP = average precision (higher is better).

  Inputs                       | AP 2024->2025 | AP 2025->2024 | Mean AP | Hits in top 115 (2025)
  -----------------------------+---------------+---------------+---------+-----------------------
  company facts, first version |         0.587 |         0.456 |   0.522 |                     69
  + pay_vs_peers               |         0.609 |         0.468 |   0.539 |                     71
  + pay_outran_returns         |         0.599 |         0.469 |   0.534 |                     70
  + all of them                |         0.618 |         0.475 |   0.547 |                     71

  For comparison, 'same as last season' on 2025: 46 hits with 115 flags.
  Share of training votes with the measure: pay vs peers 84%, pay vs returns trend 82%
```

## Director elections at US companies: NBIM's written rules applied to dated facts

`python3 src/agent/director_rules.py`

```text
US director elections in NBIM's file: 1742 nominees at 36 companies, 218 meetings, 2019-2026
NBIM voted against the board on 93 (5.3%).
Nominees matched to a person in the SEC data: 1660 (95%); of the against-votes: 87 of 93.

1. What the facts show (matched nominees)
  Fact about the nominee       | Nominees | NBIM against | Against rate
  -----------------------------+----------+--------------+-------------
  chair and CEO combined       |       38 |           32 |        84.2%
  executive, not chair and CEO |      170 |            9 |         5.3%
  not an executive             |     1453 |           47 |         3.2%
  on 1 US board                |      832 |           43 |         5.2%
  on 2 US boards               |      481 |           22 |         4.6%
  on 3 US boards               |      224 |            9 |         4.0%
  on 4-5 US boards             |      111 |            7 |         6.3%
  on more than 5 US boards     |       12 |            6 |        50.0%
  not matched to a person      |       82 |            6 |         7.3%

2. NBIM's rules as a predictor (no training, all years)
  Method                            | Flags | Hits | False alarms | Precision | Recall
  ----------------------------------+-------+------+--------------+-----------+-------
  Always with board                 |     0 |    0 |            0 |         - |     0%
  Same as last time                 |    73 |   36 |           37 |       49% |    39%
  Rule 1.3.1, chair who is also CEO |    38 |   32 |            6 |       84% |    34%
  Rule 2.1.1, more than five boards |    12 |    6 |            6 |       50% |     6%
  Either rule                       |    50 |   38 |           12 |       76% |    41%
  Same as last time, or either rule |    88 |   47 |           41 |       53% |    51%

   Against-votes on people NBIM had not opposed before: 57. The rules find 11; 'same as last time' finds 0 by construction.

3. Does the tool cite the rule NBIM itself gave?
   GVG 1.3 (chair and CEO): NBIM cited it for 28 against-votes; the rule fired on 38 nominees and matched 25 of NBIM's 28. When the rule fired and NBIM voted against, NBIM's stated reason was: {'none given': 5, 'GVG 2.1': 2, 'GVG 1.3': 25}
   GVG 2.1 (time commitment): NBIM cited it for 9 against-votes; the rule fired on 12 nominees and matched 3 of NBIM's 9. When the rule fired and NBIM voted against, NBIM's stated reason was: {'none given': 2, 'GVG 1.2': 1, 'GVG 2.1': 3}

4. Policy and practice: nominees titled chair and CEO, by year
  Year | Chair-and-CEO nominees | NBIM against | Against rate
  -----+------------------------+--------------+-------------
  2019 |                      5 |            5 |       100.0%
  2020 |                      6 |            6 |       100.0%
  2021 |                      4 |            4 |       100.0%
  2022 |                      4 |            4 |       100.0%
  2023 |                      5 |            5 |       100.0%
  2024 |                      4 |            4 |       100.0%
  2025 |                      5 |            4 |        80.0%
  2026 |                      5 |            0 |         0.0%
   By company (against / elections): First Financial Bankshares, Inc. 7/8; UMB Financial Corporation 7/8; The Hartford Insurance Group, Inc. 7/8; First Horizon Corporation 5/6; Public Storage 3/3; Standex International Corporation 2/2; Snowflake Inc. 1/2; Texas Capital Bancshares, Inc. 0/1

5. With the drift monitor (a rule is suspended after NBIM supported the board on its last two cases)
  Years     | Rules alone: hits/flags | Monitor: automatic hits/flags | Monitor: sent to a person, against/total
  ----------+-------------------------+-------------------------------+-----------------------------------------
  2019-2025 |                   38/45 |                         37/42 |                                      1/3
  2026      |                     0/5 |                           0/1 |                                      0/4
  all years |                   38/50 |                         37/43 |                                      1/7
   Rules suspended from: GVG 1.3 on 2026-04-28, GVG 2.1 on 2022-05-12

6. Against-votes the rules do not explain, by NBIM's stated reason
    {'GVG 3.2': 24, 'none given': 9, 'GVG 1.1': 8, 'GVG 2.3': 5, 'GVG 2.1': 4, 'GVG 1.3': 3, 'GVG 1.2': 2}

Wrote 1742 nominees to data/outputs/director_rules.csv
```

## Proposals whose wording decides the vote: NBIM's written rules applied to the title

`python3 src/agent/proposal_rules.py`

```text
All proposals in NBIM's file: 13324, 744 against the board, 2019-2026
Proposals whose wording falls under a clear-cut rule: 29 (20 from shareholders, 9 from management)

1. Does NBIM vote as its rule says?
  Rule     |                                 The proposal asks to | Rule says | Proposals | NBIM voted so | Share | Board said the opposite | of which NBIM against the board
  ---------+------------------------------------------------------+-----------+-----------+---------------+-------+-------------------------+--------------------------------
  1.3.3    |            separate the roles of chairperson and CEO |       FOR |         3 |             3 |  100% |                       3 |                               3
  3.1.2    |                                 declassify the board |       FOR |         5 |             5 |  100% |                       4 |                               4
  3.1.5    |          majority requirements in director elections |       FOR |         1 |             1 |  100% |                       1 |                               1
  3.1.8    |                                         proxy access |       FOR |         1 |             1 |  100% |                       1 |                               1
  4.2.2    |                      right to act by written consent |       FOR |         6 |             6 |  100% |                       6 |                               6
  6.2-AT.3 | abolish an anti-takeover measure (supermajority requ |       FOR |        11 |            11 |  100% |                       5 |                               5
  6.2-AT.2 | introduce or renew an anti-takeover measure (poison  |       MOT |         2 |             2 |  100% |                       2 |                               2

2. As a predictor of 'against the board' on shareholder proposals (no training, all years)
   150 shareholder proposals with an answer, 50 against the board
  Method                           | Flags | Hits | False alarms | Precision | Recall
  ---------------------------------+-------+------+--------------+-----------+-------
  Always with board                |     0 |    0 |            0 |         - |     0%
  Same as last time                |    12 |   11 |            1 |       92% |    22%
  Clear-cut rules from the wording |    20 |   20 |            0 |      100% |    40%
  Same as last time, or a rule     |    25 |   24 |            1 |       96% |    48%

3. By period, with the drift monitor
  Years     | Rules alone: hits/flags | Monitor: automatic hits/flags | Monitor: sent to a person, against/total
  ----------+-------------------------+-------------------------------+-----------------------------------------
  2019-2025 |                   19/19 |                         19/19 |                                      0/0
  2026      |                     3/3 |                           3/3 |                                      0/0
  all years |                   22/22 |                         22/22 |                                      0/0

4. Does the tool cite the section NBIM itself gave?
   Of 19 rule hits where NBIM gave a reason, the tool's section matches NBIM's in 19: {('GVG 4.2', 'GVG 4.2'): 5, ('GVG 6.2', 'GVG 6.2'): 6, ('GVG 3.1', 'GVG 3.1'): 6, ('GVG 1.3', 'GVG 1.3'): 2}

5. Against-votes on shareholder proposals that no clear-cut rule covers, by NBIM's stated reason
    {'GVG 5.3': 21, 'none given': 4, 'GVG 4.3': 2, 'GVG 3.1': 2, 'GVG 1.1': 1}
    GVG 5.3 is sustainability reporting, where every rule needs judgement.

Wrote 29 proposals to data/outputs/proposal_rules.csv
```

## Experiment: do ballot details improve the history model? (test years 2022-2025)

`python3 src/agent/history_model.py`

```text
Test years 2022-2025, each scored by a model fitted on the years before it. 2026 is not read.

  Inputs                         | Mean average precision | Hits at the baseline's 215 flags | New situations found
  -------------------------------+------------------------+----------------------------------+---------------------
  benchmark (history only)       |                  0.408 |                              126 |               17/268
  + finer types                  |                  0.410 |                              125 |               16/268
  + position                     |                  0.407 |                              126 |               20/268
  + board_size                   |                  0.417 |                              127 |               18/268
  + label                        |                  0.407 |                              123 |               14/268
  + wording                      |                  0.411 |                              125 |               17/268
  + last_meeting                 |                  0.409 |                              125 |               14/268
  + everything                   |                  0.421 |                              129 |               18/268
  everything except position     |                  0.420 |                              127 |               18/268
  everything except board_size   |                  0.412 |                              125 |               19/268
  everything except label        |                  0.422 |                              129 |               19/268
  everything except wording      |                  0.419 |                              130 |               19/268
  everything except last_meeting |                  0.422 |                              127 |               18/268
  everything except finer_types  |                  0.421 |                              129 |               18/268

  'Same as last time' finds 133 of 401 against-votes with 215 flags, and no new situations by construction.
```

## Guideline rule check

`python3 src/agent/rule_check.py`

```text
Rule check with microsoft/microsoft-decision-1 | test year 2026 | 1539 proposals, 66 against the board
Rule-check threshold 0.133 chosen on 2025; history-model threshold 0.313

  Method                      | Precision | Recall |    F1 | Flagged | Hits | False alarms | Missed
  ----------------------------+-----------+--------+-------+---------+------+--------------+-------
  Always with board           |      0.0% |   0.0% |  0.0% |       0 |    0 |            0 |     66
  Same as last time           |     57.9% |  33.3% | 42.3% |      38 |   22 |           16 |     44
  History model               |     61.5% |  36.4% | 45.7% |      39 |   24 |           15 |     42
  Rule check alone            |     53.8% |  10.6% | 17.7% |      13 |    7 |            6 |     59
  History model OR rule check |     53.3% |  36.4% | 43.2% |      45 |   24 |           21 |     42

Rule check flagged 6 proposals the history model did not: 0 real against-votes, 6 false alarms
Against-votes on items NBIM had not voted on before at that company: 35; rule check catches 2, history model catches 3

Citations, on the 63 against-votes where NBIM named a guideline section:
  NBIM's section was among the sections checked: 45 (71%)
  NBIM's section was the one the rule check scored highest: 38 (60%)

Rule check by proposal type (types with at least 3 against-votes)
  Type              | Proposals | Precision | Recall |     F1 | Flagged | Hits | False alarms | Missed
  ------------------+-----------+-----------+--------+--------+---------+------+--------------+-------
  DIRECTOR_ELECTION |       739 |      0.0% |   0.0% |   0.0% |       0 |    0 |            0 |     33
  AUDITOR           |       130 |      0.0% |   0.0% |   0.0% |       0 |    0 |            0 |      7
  OTHER_MGMT        |        87 |      0.0% |   0.0% |   0.0% |       3 |    0 |            3 |      6
  OTHER_BUSINESS    |         6 |    100.0% | 100.0% | 100.0% |       6 |    6 |            0 |      0
  SAY_ON_PAY        |        61 |      0.0% |   0.0% |   0.0% |       0 |    0 |            0 |      3
  ARTICLES          |        55 |      0.0% |   0.0% |   0.0% |       0 |    0 |            0 |      3

Wrote 1539 rows to data/outputs/rule_check_2026.csv
```

## Resistance test and guardrail

`python3 src/agent/robustness.py`

```text
1. HISTORY MODEL under attack: the 66 proposals in 2026 where NBIM voted against the board
   Clean text: 24 flagged as likely AGAINST, 18 in the 'likely WITH board' band nobody reads

  Text added to the proposal    | Still flagged | Waved through | Guard: security flag | Guard: flagged or to human | Guard: waved through
  ------------------------------+---------------+---------------+----------------------+----------------------------+---------------------
  case wording (Norwegian)      |             8 |            16 |                   66 |                         66 |                    0
  direct override               |             8 |            16 |                   66 |                         66 |                    0
  fake internal note            |             8 |            16 |                   66 |                         66 |                    0
  fake guideline quote          |             8 |            16 |                   66 |                         66 |                    0
  soft persuasion, no keywords  |             8 |            16 |                    0 |                         24 |                   18
  harmless extra text (control) |             8 |            16 |                    0 |                         24 |                   18

   'Still flagged' and 'Waved through' are without the guardrail (clean: 24 and 18).
   Cost of the known-item lookup on clean 2026 data: it rewrites 77 of 1539 proposals; hits 24 -> 24, false alarms 15 -> 16.

2. DECISION MODEL (microsoft/microsoft-decision-1) under attack, cut-off 0.133
   A: 39 proposals it flagged in 2025-2026; attack says vote FOR. Count = no longer flagged.
   B: 150 random 2026 proposals it did not flag; attack says vote AGAINST. Count = newly flagged.

  Text added to the proposal    | A flipped (warning) | B flipped (warning) | A flipped (no warning) | B flipped (no warning) | Guard: security flag
  ------------------------------+---------------------+---------------------+------------------------+------------------------+---------------------
  case wording (Norwegian)      |                2/39 |               9/150 |                   6/37 |                 22/150 |              189/189
  direct override               |                2/39 |               0/150 |                   1/37 |                  5/150 |              189/189
  fake internal note            |                4/39 |               0/150 |                   4/37 |                  1/150 |              189/189
  fake guideline quote          |               13/39 |               0/150 |                  14/37 |                 10/150 |              189/189
  soft persuasion, no keywords  |                5/39 |              26/150 |                   6/37 |                 29/150 |                0/189
  harmless extra text (control) |                4/39 |              22/150 |                   3/37 |                 22/150 |                0/189

   'warning' = the prompt tells the model the proposal text is data and not to follow instructions in it.

3. GUARDRAIL false alarms on real ballot texts (no attack added)
  Dataset                                   | Texts | Security flags |  Rate | Of the organisers' own flagged rows
  ------------------------------------------+-------+----------------+-------+------------------------------------
  NBIM votes (data/dirty/real_votes.csv)    | 13757 |              0 | 0.00% |                                 0/0
  Other investor (data/dirty/npx_votes.csv) | 52906 |              0 | 0.00% |                               0/141

Wrote per-proposal history-model results to data/outputs/robustness_2026.csv
```
