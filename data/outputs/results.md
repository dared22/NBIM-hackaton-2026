# Results

Produced by `python3 src/run.py`. Test year 2026; nothing from 2026 is used to fit or tune.

## Decisions

One row per proposal is in `data/outputs/decisions_2026.csv`.

### US executive pay votes (history + company facts)
- Proposals: 1200; NBIM voted against the board on 114.
- Decided automatically: 903 (75%). Sent to a person: 297 (25%).
- Automatic 'against the board' suggestions: 101, of which 71 were right (precision 70%, recall 62%).
- Against-votes inside the pile sent to a person: 31 (27% of all against-votes).
- Against-votes the tool waved through with the board: 12 (11% of all against-votes).
- With a person reading the review pile, 102 of 114 against-votes are either suggested or seen (89%).
- Sent to a person although the model's probability was low (nothing to go on, or a rule applies that the tool does not act on alone): 75 proposals; 3 of them were against-votes.

### All proposal types (history, plus NBIM rules for US directors and worded proposals)
- Proposals: 1539; NBIM voted against the board on 66.
- Decided automatically: 1159 (75%). Sent to a person: 380 (25%).
- Automatic 'against the board' suggestions: 35, of which 25 were right (precision 71%, recall 38%).
- Against-votes inside the pile sent to a person: 27 (41% of all against-votes).
- Against-votes the tool waved through with the board: 14 (21% of all against-votes).
- With a person reading the review pile, 52 of 66 against-votes are either suggested or seen (79%).
- Sent to a person although the model's probability was low (nothing to go on, or a rule applies that the tool does not act on alone): 36 proposals; 4 of them were against-votes.

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
Company facts for the test votes: 1170 from the meeting's own proxy, 3 from the SEC API, 27 none. CEO pay known for 1172 (98%).
Proxies were filed 21 to 90 days before the meeting (median 43).

Results on season 2026 (95% intervals from resampling votes)
  Method                             | Precision |     95% | Recall |     95% |    F1 | Flagged | Hits | False alarms | Missed
  -----------------------------------+-----------+---------+--------+---------+-------+---------+------+--------------+-------
  Always with board                  |      0.0% |   0%-0% |   0.0% |   0%-0% |  0.0% |       0 |    0 |            0 |    114
  Same as last season                |     43.3% | 34%-53% |  36.8% | 28%-46% | 39.8% |      97 |   42 |           55 |     72
  History only, top 97               |     43.3% | 34%-53% |  36.8% | 28%-46% | 39.8% |      97 |   42 |           55 |     72
  History + company facts, top 97    |     74.2% | 65%-83% |  63.2% | 55%-71% | 68.2% |      97 |   72 |           25 |     42
  History + company facts, p >= 0.37 |     71.8% | 63%-80% |  69.3% | 61%-77% | 70.5% |     110 |   79 |           31 |     35

  'top 97' rows flag exactly as many votes as the same-as-last-season baseline, so they compare like for like.
  Average precision: history + company facts 0.698, history only 0.246, random 0.095
  Brier score (lower is better): model 0.0451, always saying 8.5% 0.0861

By what was known about the company
  What was known                   | Votes | Against | Found | Recall | False alarms
  ---------------------------------+-------+---------+-------+--------+-------------
  CEO pay known                    |  1172 |     113 |    79 |    70% |           30
  only other executives' pay known |     1 |       0 |     0 |      - |            1
  no pay figure                    |    27 |       1 |     0 |     0% |            0

New situations: against-votes at companies NBIM did not oppose last season
  72 such votes. Same-as-last-season finds 0 by construction; the model finds 38 in its top 97 and 43 at p >= 0.37.

Bands on the test season
  Band                 | Votes | Share | Real against-votes | Share of all against | Against rate
  ---------------------+-------+-------+--------------------+----------------------+-------------
  likely WITH board    |   877 |   73% |                 15 |                  13% |         1.7%
  send to human        |   213 |   18% |                 20 |                  18% |         9.4%
  likely AGAINST board |   110 |    9% |                 79 |                  69% |        71.8%

Is the confidence honest? (predicted vs actual share against)
  Predicted | Votes | Model says | Actual
  ----------+-------+------------+-------
  0%-5%     |   877 |       2.2% |   1.7%
  5%-15%    |   116 |       8.1% |   6.0%
  15%-35%   |    90 |      23.5% |  14.4%
  35%-60%   |    29 |      43.2% |  34.5%
  60%-100%  |    88 |      83.7% |  78.4%

Against rate by CEO pay, test season
  CEO total pay | Votes | Against | Against rate
  --------------+-------+---------+-------------
  under $10m    |   432 |       8 |           2%
  $10-25m       |   585 |      22 |           4%
  $25-40m       |   107 |      47 |          44%
  $40m or more  |    48 |      36 |          75%
  no CEO figure |    28 |       1 |           4%

Model weights (positive = pushes towards AGAINST)
   +1.49  prev_against   NBIM voted against this company's pay last season
   -0.63  prev_for       NBIM supported this company's pay last season
   -0.70  pay_size       size of the CEO's total pay
   +1.52  pay_25m        CEO pay is at or above the 25 million dollar level NBIM reviews more strictly
   +1.09  pay_doubled    CEO pay at least doubled from the year before
   +0.58  ceo_vs_others  CEO pay is many times the other executives' average
   +2.47  others_size    size of the other named executives' average pay
   +0.33  high_pay_lost  CEO pay of 25 million dollars or more while shareholders have lost money
   +0.46  ceo_changed    more than one CEO was paid during the year
   +0.70  pay_vs_peers   CEO pay as a multiple of the median at companies of similar industry and size
   +1.14  pay_outran_returns CEO pay has grown faster than shareholder returns over the years in the pay table

Wrote 1200 scored votes to data/outputs/pay_votes_2026.csv
```

## Pay model, how the inputs were chosen (training seasons only)

`python3 src/agent/pay_model.py --develop`

```text
Training seasons only. AP = average precision (higher is better).

  Inputs                       | AP 2024->2025 | AP 2025->2024 | Mean AP | Hits in top 115 (2025)
  -----------------------------+---------------+---------------+---------+-----------------------
  company facts, first version |         0.629 |         0.514 |   0.572 |                     74
  + pay_vs_peers               |         0.650 |         0.533 |   0.591 |                     76
  + pay_outran_returns         |         0.639 |         0.534 |   0.586 |                     71
  + all of them                |         0.658 |         0.544 |   0.601 |                     76

  For comparison, 'same as last season' on 2025: 46 hits with 115 flags.
  Share of training votes with the measure: pay vs peers 95%, pay vs returns trend 92%
```

## The same US pay proposals in both files: which model should answer?

`python3 src/agent/pay_overlap.py`

```text
  Year                              | US pay votes in NBIM's file | also in the SEC file | against the board | History model: flags | hits | Pay model: flags | hits | Pay model waved through an against-vote
  ----------------------------------+-----------------------------+----------------------+-------------------+----------------------+------+------------------+------+----------------------------------------
  2024 (scored without the company) |                          33 |                   32 |                 5 |                    0 |    0 |                3 |    3 |                                       0
  2025 (scored without the company) |                          31 |                   31 |                 3 |                    4 |    2 |                3 |    2 |                                       1
  2026 (the real test)              |                          18 |                   18 |                 0 |                    2 |    0 |                1 |    0 |                                       0
  all three                         |                          82 |                   81 |                 8 |                    6 |    2 |                7 |    5 |                                       1

  On the 81 proposals in both files the pay model finds 5 of the 8 against-votes with 7 flags.
  The history model finds 2 with 6 flags. In 2026 there were no against-votes among them,
  and the pay model raises one false alarm where the history model raises two.
  src/run.py now gives these proposals the pay model's answer, so each proposal has one answer.
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

## Director elections at US companies: facts read from the proxy, and rules that must earn trust

`python3 src/agent/board_rules.py`

```text
US director nominees in NBIM's file: 1742, 93 against the board, 2019-2026
Proxy read for 1707 of them (98%); the nominee was found in the proxy for 1706.

1. How much did the reader find, and was the quote in the text?
  Fact about the nominee | Answered | Share | of which with a quote found
  -----------------------+----------+-------+----------------------------
  independent            |     1673 |   98% |                        1501
  executive              |     1706 |  100% |                         734
  ceo                    |     1704 |  100% |                         489
  board_chair            |     1669 |   98% |                         272
  executive_elsewhere    |     1672 |   98% |                        1067
  other_public_boards    |     1431 |   84% |                        1428
  audit_committee        |     1705 |  100% |                from a table
  pay_committee          |     1704 |  100% |                from a table
  nomination_committee   |     1701 |  100% |                from a table
  gender                 |     1688 |   99% |                from a table

2. Two sources, one question: chair and CEO, from the proxy and from SEC insider filings
                       | SEC filings: chair and CEO | SEC filings: not
  ---------------------+----------------------------+-----------------
  Proxy: chair and CEO |                         33 |               13
  Proxy: not           |                          5 |             1575
   The two sources agree on 1608 of 1626 nominees (98.9%).
   On 'is an executive of this company' they agree on 1609 of 1626 (99.0%): both yes 198, proxy only 8, SEC filings only 9.

3. Each rule on its own, all years (no training)
  Rule  | Fires | NBIM against | Share | With every quote found: against/fires | NBIM named the same section
  ------+-------+--------------+-------+---------------------------------------+----------------------------
  1.2.1 |     3 |            2 |   67% |                                   2/3 |                           1
  1.3.1 |    36 |           32 |   89% |                                 32/35 |                          27
  2.1.1 |     8 |            3 |   38% |                                   3/8 |                           3
  2.1.2 |     8 |            1 |   12% |                                   1/8 |                           1
  2.3.1 |    12 |            4 |   33% |                                   3/9 |                           4
   For comparison, NBIM votes against 5.3% of all US director nominees.

4. Facts for rules that the guidelines say need judgement
  Rule  |                                                                  Fact | Nominees | NBIM against | Share
  ------+-----------------------------------------------------------------------+----------+--------------+------
  1.3.1 |                                 chair and CEO who founded the company |       11 |            4 |   36%
  2.1.1 |                         chairs this board and another company's board |       18 |           10 |   56%
  2.1.1 |              executive elsewhere with two or more other listed boards |       86 |           11 |   13%
  3.2.1 | nomination committee member, majority-supported proposal not acted on |        2 |            0 |    0%
  3.1.3 |                                         nominee to a classified board |      219 |           19 |    9%
  3.2.2 |        pay committee member, NBIM opposed pay at the previous meeting |       23 |            3 |   13%
  3.2.2 |                 pay committee member, last pay vote under 70% support |       30 |            0 |    0%
   The first two can earn trust like a rule (section 5). The others are shown to the reviewer only.

5. Every signal from both sources, all years: how often NBIM voted against when it fired
  Signal                   | Fires | NBIM against | Share | While trusted: against/fires
  -------------------------+-------+--------------+-------+-----------------------------
  1.2.1 (proxy)            |     3 |            2 |   67% |                          0/1
  1.3.1 (SEC filings)      |    38 |           32 |   84% |                        29/30
  1.3.1 (proxy)            |    36 |           32 |   89% |                        29/29
  1.3.1 founder (proxy)    |    11 |            4 |   36% |                          1/2
  2.1.1 (SEC filings)      |    12 |            6 |   50% |                          3/4
  2.1.1 (proxy)            |     8 |            3 |   38% |                          0/0
  2.1.1 two chairs (proxy) |    18 |           10 |   56% |                          6/8
  2.1.2 (proxy)            |     8 |            1 |   12% |                          0/0
  2.3.1 (proxy)            |    12 |            4 |   33% |                          1/1
   A signal is trusted once NBIM has followed it at 2 meetings in a row, and loses the trust at the first miss.

6. As a predictor of 'against the board', all years
  Method                                                     | Flags | Hits | False alarms | Precision | Recall
  -----------------------------------------------------------+-------+------+--------------+-----------+-------
  Always with board                                          |     0 |    0 |            0 |         - |     0%
  Same as last time                                          |    73 |   36 |           37 |       49% |    39%
  Before: rules on SEC insider filings, with the old monitor |    43 |   37 |            6 |       86% |    40%
  Any signal fires (no trust rule)                           |    95 |   51 |           44 |       54% |    55%
  Trusted signals only: the tool acts alone                  |    45 |   39 |            6 |       87% |    42%
  Trusted signals, or same as last time                      |    86 |   46 |           40 |       53% |    49%
   Signals that fired without trust send 50 more nominees to a person, 12 of them against-votes. So 51 of the 93 against-votes are either suggested or put in front of a person with the fact and its quote.

7. By period
  Years     | Against-votes | Same as last time: hits/flags | Tool acts alone: hits/flags | Sent to a person with the fact: against/total
  ----------+---------------+-------------------------------+-----------------------------+----------------------------------------------
  2019-2024 |            76 |                         30/59 |                       34/39 |                                         11/32
  2025      |            16 |                           6/9 |                         5/6 |                                           0/7
  2026      |             1 |                           0/5 |                         0/0 |                                          1/11
  all years |            93 |                         36/73 |                       39/45 |                                         12/50

8. The against-votes no signal points at, by NBIM's stated reason
   42 of 93: GVG 3.2 24, none given 8, GVG 1.1 8, GVG 2.1 1, GVG 1.3 1
   GVG 3.2 is 'board decisions and conduct': a reaction to something the company did, which a proxy does not state.

Wrote 1742 nominees to data/outputs/board_rules.csv
```

## Proposals whose wording decides the vote: NBIM's written rules applied to the title

`python3 src/agent/proposal_rules.py`

```text
All proposals in NBIM's file: 13324, 744 against the board, 2019-2026
Proposals whose wording falls under a clear-cut rule: 73 (20 from shareholders, 53 from management)

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
  5.2.2    |                 vote on unspecified "other business" |       MOT |        44 |            44 |  100% |                      44 |                              44

2. As a predictor of 'against the board' on shareholder proposals (no training, all years)
   150 shareholder proposals with an answer, 50 against the board
  Method                           | Flags | Hits | False alarms | Precision | Recall
  ---------------------------------+-------+------+--------------+-----------+-------
  Always with board                |     0 |    0 |            0 |         - |     0%
  Same as last time                |    12 |   11 |            1 |       92% |    22%
  Clear-cut rules from the wording |    20 |   20 |            0 |      100% |    40%
  Same as last time, or a rule     |    25 |   24 |            1 |       96% |    48%

   All proposals where a rule means 'against the board' (management and shareholder proposals)
   66 proposals, 66 against the board. 'Same as last time' covers 45 of them; the other 21 are first-time items it cannot flag, and 21 of those were against-votes.

3. By period, with the drift monitor
  Years     | Rules alone: hits/flags | Monitor: automatic hits/flags | Monitor: sent to a person, against/total
  ----------+-------------------------+-------------------------------+-----------------------------------------
  2019-2025 |                   57/57 |                         57/57 |                                      0/0
  2026      |                     9/9 |                           9/9 |                                      0/0
  all years |                   66/66 |                         66/66 |                                      0/0

4. Does the tool cite the section NBIM itself gave?
   Of 58 rule hits where NBIM gave a reason, the tool's section matches NBIM's in 58: {('GVG 4.2', 'GVG 4.2'): 5, ('GVG 5.2', 'GVG 5.2'): 39, ('GVG 6.2', 'GVG 6.2'): 6, ('GVG 3.1', 'GVG 3.1'): 6, ('GVG 1.3', 'GVG 1.3'): 2}

5. Against-votes on shareholder proposals that no clear-cut rule covers, by NBIM's stated reason
    {'GVG 5.3': 21, 'none given': 4, 'GVG 4.3': 2, 'GVG 3.1': 2, 'GVG 1.1': 1}
    GVG 5.3 is sustainability reporting, where every rule needs judgement.

Wrote 73 proposals to data/outputs/proposal_rules.csv
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

## Position papers: do they add anything?

`python3 src/agent/position_papers_test.py`

```text
12 position papers loaded: Board diversity, Board independence, CEO remuneration, Corporate sustainability reporting, Individual vote count in board elections, Industry expertise on the board, Multiple share classes, Proxy access at US companies, Related-party transactions, Separation of chairperson and CEO, Shareholder rights in equity issuances, Time commitment of board members

1. Statements with a number or threshold in NBIM's positions
   [Board diversity] Boards where either gender has less than 30 percent representation should consider setting targets for gender diversity and report on progress.
   [Board independence] A majority of shareholder-elected board members should be independent of management, dominant shareholders, and business relationships.
   [Board independence] In majority-controlled companies, at least a third of board members should be independent.
   [Board independence] The audit committee should have a majority of independent members, and management should not serve on the audit or remuneration committees.
   [CEO remuneration] A substantial proportion of total annual remuneration should be provided as shares that are locked in for at least five and preferably ten years, regardless of resignation or retirement.
   [Industry expertise on the board] A majority of independent board members should have fundamental industry insight.
   [Industry expertise on the board] At least two of the independent members should have worked in the industry.
   [Multiple share classes] One share should give one vote.
   [Proxy access at US companies] We support the introduction of holding periods of up to three years and holding requirements of up to three percent.
   [Proxy access at US companies] We will accept a limit on the number of board seats to be affected by proxy access candidates if at least two seats or 20 percent of the board can be filled by such candidates.
   [Shareholder rights in equity issuances] Issuances without pre-emptive rights should not exceed 10 percent of the existing share capital.
   [Shareholder rights in equity issuances] General authorities to issue shares should last no longer than 15 months, or until the next annual shareholder meeting.
   [Time commitment of board members] Board members of listed companies should not serve on more than five boards at one time.

   Most repeat the guidelines (five boards, half independent, a third at controlled companies,
   three years and three percent for proxy access). New compared with the guidelines:
   - share issues without pre-emptive rights should not exceed 10 percent; authorities at most 15 months
   - a chair of a leading company should not chair another company
   - boards with under 30 percent of either gender should set targets
   - at least two independent members should have worked in the industry
   - pay: shares locked in for five to ten years; no number for how much pay is too much

2. The 10 percent threshold for share issues, against NBIM's votes
   334 share issue proposals, 7 against the board. Only 14 state a percentage in the title.
  Pre-emptive rights         |        Size | Proposals | NBIM against
  ---------------------------+-------------+-----------+-------------
  without pre-emptive rights | 10% or less |         8 |            1
  without pre-emptive rights |    over 10% |         6 |            0
   The threshold cannot be applied to most proposals (no percentage in the title), and where it can,
   NBIM did not vote against the ones above 10 percent.

3. Does the tool name the same position paper as NBIM?
  Rules             | Rule hits | NBIM named a paper | Tool names the same paper | NBIM named none | Tool also names none
  ------------------+-----------+--------------------+---------------------------+-----------------+---------------------
  US director rules |        38 |                 31 |                        28 |               7 |                    0
  wording rules     |        66 |                  3 |                         3 |              63 |                   62
   NBIM's own pairing of guideline section and paper, all against-votes: GVG 1.1 -> Board independence (84); GVG 1.3 -> Separation of chairperson and CEO (50); GVG 2.1 -> Time commitment of board members (49); GVG 1.2 -> Board independence (46); GVG 3.3 -> CEO remuneration (43); GVG 5.3 -> Corporate sustainability reporting (21); GVG 2.3 -> Board diversity (17); GVG 3.2 -> Corporate sustainability reporting (16)

4. Decision model on the proposal wording, 2026, with and without the papers
  Decision model given         | Cut-off | Flags | Hits | False alarms | New vs history model: hits/flags | Top section = NBIM's section
  -----------------------------+---------+-------+------+--------------+----------------------------------+-----------------------------
  guidelines only              |   0.133 |    13 |    7 |            6 |                              0/6 |                        38/63
  guidelines + position papers |   0.060 |    83 |   12 |           71 |                             1/70 |                        33/63
   66 against-votes in 2026. The history model alone finds 24.
```

## Confidence and routing: when should the tool ask a person?

`python3 src/agent/routing.py`

```text
1. Is the confidence honest? Test years 2022-2026, 8864 proposals
  The tool says | Proposals | Average stated | Actually against the board
  --------------+-----------+----------------+---------------------------
  0% to 2%      |      4764 |           0.8% |                       1.3%
  2% to 5%      |      1882 |           3.3% |                       3.2%
  5% to 10%     |      1011 |           7.1% |                       6.1%
  10% to 20%    |       609 |          14.2% |                       8.7%
  20% to 40%    |       263 |          27.3% |                      23.2%
  40% to 70%    |       255 |          54.1% |                      41.2%
  70% to 100%   |        80 |          82.7% |                      78.8%
   Below 10% the stated probability matches what happened. Between 10% and 70% the tool
   says more than what happened, so a stated 50% is closer to 40%.

2. Does a correction learned from earlier years help? (Brier score, lower is better)
  Test year | As it is | With correction
  ----------+----------+----------------
  2022      |   0.0499 |          0.0516
  2023      |   0.0421 |          0.0408
  2024      |   0.0385 |          0.0384
  2025      |   0.0376 |          0.0389
  2026      |   0.0309 |          0.0310
   The correction is better in 2 of 5 years. It is not used.

3. The level below which the tool follows the board on its own
  Level | 2022-2025: a person reads | against-votes waved through | 2026: a person reads | against-votes waved through | wrong among those waved through
  ------+---------------------------+-----------------------------+----------------------+-----------------------------+--------------------------------
  5%    |                     20.0% |            105 of 401 (26%) |                22.5% |                    18 of 66 |                            1.6%
  4%    |                     25.3% |             91 of 401 (23%) |                29.3% |                    11 of 66 |                            1.0%
  3%    |                     32.2% |             75 of 401 (19%) |                38.0% |                     3 of 66 |                            0.3%
  2%    |                     40.6% |             59 of 401 (15%) |                46.8% |                     3 of 66 |                            0.4%
   Judged on 2022-2025: going from 5% to 3%, a person reads about 60% more proposals and
   most of the against-votes that were waved through still are. The gain in 2026 is larger,
   but the level may not be chosen on 2026. The 5% level is kept. The level is a choice between
   reading time and missed against-votes, and this table is what to choose from.

4. Can anything pick out the against-votes among the proposals the tool waves through (below 5%)?
  Group                                           | 2022-2025: proposals | against | share | 2026: proposals | against | share
  ------------------------------------------------+----------------------+---------+-------+-----------------+---------+------
  director election, wording never seen           |                  551 |      19 |  3.4% |             128 |       5 |  3.9%
  director election, wording seen 1-4 times       |                 1596 |      38 |  2.4% |             246 |       1 |  0.4%
  director election, wording seen 5 or more times |                  413 |       2 |  0.5% |             175 |       3 |  1.7%
  other proposal, wording never seen              |                  662 |      13 |  2.0% |             133 |       5 |  3.8%
  other proposal, wording seen 1-4 times          |                  710 |      16 |  2.3% |             110 |       3 |  2.7%
  other proposal, wording seen 5 or more times    |                 1561 |      17 |  1.1% |             361 |       1 |  0.3%
  Group                                      | 2022-2025: proposals | against | share | 2026: proposals | against | share
  -------------------------------------------+----------------------+---------+-------+-----------------+---------+------
  nothing else stands out at the meeting     |                 2642 |      52 |  2.0% |             415 |       5 |  1.2%
  the tool flags another item at the meeting |                 1233 |      24 |  1.9% |             302 |       7 |  2.3%
  the tool is unsure about another item      |                 1618 |      29 |  1.8% |             436 |       6 |  1.4%
   No group stands out enough to send to a person: in 2022-2025 the share of against-votes is
   between 0.5% and 3.4% in every group, and the order of the groups changes between the periods.
   The against-votes the tool waves through look like the other proposals in the vote file.

5. Abstain. Of NBIM's votes against the board, how many were cast as abstentions, and does
   the market habit learned from earlier years say so? (given that the vote is against the board)
  Year | Votes against the board | cast as abstain | Rule says abstain | of which right
  -----+-------------------------+-----------------+-------------------+---------------
  2021 |                      97 |               8 |                 4 |              4
  2022 |                     117 |              14 |                12 |             11
  2023 |                      83 |               2 |                 2 |              2
  2024 |                      98 |               1 |                 1 |              1
  2025 |                     103 |               0 |                 0 |              0
  2026 |                      66 |               5 |                 0 |              0
  all  |                     564 |              30 |                19 |             18
   Markets with the habit over the whole file: Denmark director election (13 of 13), Taiwan articles (5 of 6), Taiwan dividend (4 of 4), Taiwan fin statements (4 of 4), Taiwan merger (3 of 3), Taiwan routine (3 of 3), Vietnam director election (2 of 2)
   In 2026 the rule finds none of that year's abstentions: they are in markets with no such history.
   Other abstentions in the file are on items with no board recommendation (Brazil, cumulative
   voting), which have no 'against the board' answer and are outside the target.
```

## Pilot: does how the CEO's pay is built explain the pay against-votes?

`python3 src/agent/pay_structure_test.py`

```text
Training seasons, CEO pay 10 to 25 million dollars: 1211 pay votes, 89 against (7%).
Proxies read: 301 votes, all 89 against-votes and 212 of the others (each stands for 5.3).

1. NBIM's against-votes by what the proxy says
  Question                 |                         Answer | Against | With the board (sampled) | Estimated against rate
  -------------------------+--------------------------------+---------+--------------------------+-----------------------
  special_award            |                             no |       8 |                       29 |                     5%
                           |                            yes |      65 |                      142 |                     8%
                           | not stated, or quote not found |      16 |                       41 |                     7%
  performance_share_pct    |                      50 to 59% |      19 |                       64 |                     5%
                           |                      60 to 74% |      26 |                       70 |                     7%
                           |                    75% or more |       9 |                       28 |                     6%
                           |                      under 50% |       5 |                       15 |                     6%
                           | not stated, or quote not found |      30 |                       35 |                    14%
  longest_lock_years       |                        3 years |      19 |                       63 |                     5%
                           |                        4 years |      12 |                       36 |                     6%
                           |                5 years or more |       8 |                       23 |                     6%
                           |                  under 3 years |       1 |                        0 |                   100%
                           | not stated, or quote not found |      49 |                       90 |                     9%
  holding_after_vesting    |                             no |       8 |                       29 |                     5%
                           |                            yes |      11 |                       38 |                     5%
                           | not stated, or quote not found |      70 |                      145 |                     8%
  performance_period_years |                        3 years |      58 |                      178 |                     6%
                           |                   over 3 years |       8 |                        5 |                    23%
                           |                  under 3 years |       4 |                        8 |                     9%
                           | not stated, or quote not found |      19 |                       21 |                    15%
  bonus_pct_of_target      |                    100 to 149% |      21 |                       51 |                     7%
                           |                   150% or more |       6 |                       35 |                     3%
                           |                     under 100% |      15 |                       38 |                     7%
                           | not stated, or quote not found |      47 |                       88 |                     9%
  upward_discretion        |                             no |       9 |                       36 |                     5%
                           |                            yes |      34 |                       65 |                     9%
                           | not stated, or quote not found |      46 |                      111 |                     7%
  prior_support_pct        |                      70 to 89% |       6 |                       20 |                     5%
                           |                    90% or more |      12 |                       48 |                     5%
                           |                      under 70% |       8 |                        4 |                    27%
                           | not stated, or quote not found |      63 |                      140 |                     8%
  changed_after_feedback   |                             no |       7 |                       21 |                     6%
                           |                            yes |      30 |                       69 |                     8%
                           | not stated, or quote not found |      52 |                      122 |                     7%
  ceo_change               |                             no |      12 |                       44 |                     5%
                           |                            yes |      30 |                       40 |                    12%
                           | not stated, or quote not found |      47 |                      128 |                     6%
   The questions are written out in src/agent/fetch_pay_structure.py. Quotes for every answer are in
   data/evidence/pay_structure.csv.

2. Do the answers add anything to the current pay inputs? (the sample, five folds by company)
  Inputs                               | Average precision | Hits in the top 89
  -------------------------------------+-------------------+-------------------
  current pay inputs                   |             0.574 |                 51
  + no performance-based equity stated |             0.594 |                 50
  + previous support under 70%         |             0.576 |                 51
  + performance period over 3 years    |             0.567 |                 53
  + CEO change in the text             |             0.580 |                 50
  + one-off award                      |             0.566 |                 50
  + pay raised by discretion           |             0.574 |                 49
  + all six                            |             0.585 |                 51
   Flagging everything in this sample would give an average precision of 0.296.
   No input moves the hits by more than two. The differences are noise at this sample size.

3. How often the reader found an answer with a quote in the text
  Question                 | Answered with a quote found | Share of proxies read
  -------------------------+-----------------------------+----------------------
  special_award            |                         243 |                   81%
  performance_share_pct    |                         235 |                   79%
  longest_lock_years       |                         161 |                   54%
  holding_after_vesting    |                          86 |                   29%
  performance_period_years |                         259 |                   87%
  bonus_pct_of_target      |                         165 |                   55%
  upward_discretion        |                         144 |                   48%
  prior_support_pct        |                          98 |                   33%
  changed_after_feedback   |                         126 |                   42%
  ceo_change               |                         126 |                   42%
   193 answers were dropped because their quote was not found word for word in the text.
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
