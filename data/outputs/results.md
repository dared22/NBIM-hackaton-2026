# Results

Produced by `python3 src/run.py`. Test year 2026; nothing from 2026 is used to fit or tune.

## Decisions

One row per proposal is in `data/outputs/decisions_2026.csv`.

### US executive pay votes (history + company facts)
- Proposals: 1200; NBIM voted against the board on 114.
- Decided automatically: 963 (80%). Sent to a person: 237 (20%).
- Automatic 'against the board' suggestions: 101, of which 68 were right (precision 67%, recall 60%).
- Against-votes inside the pile sent to a person: 27 (24% of all against-votes).
- Against-votes the tool waved through with the board: 19 (17% of all against-votes).
- With a person reading the review pile, 95 of 114 against-votes are either suggested or seen (83%).

### All proposal types (history only)
- Proposals: 1539; NBIM voted against the board on 66.
- Decided automatically: 1192 (77%). Sent to a person: 347 (23%).
- Automatic 'against the board' suggestions: 39, of which 24 were right (precision 62%, recall 36%).
- Against-votes inside the pile sent to a person: 24 (36% of all against-votes).
- Against-votes the tool waved through with the board: 18 (27% of all against-votes).
- With a person reading the review pile, 48 of 66 against-votes are either suggested or seen (73%).

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
