# Data audit

Produced by `python3 src/agent/data_audit.py`. Counts come straight from the raw files.

## 1. Main file: data/dirty/real_votes.csv

13757 rows, 22 columns, 13761 Windows line endings, 3 proposal texts contain a line break.

### 1.1 Empty cells per column

  Column            | Empty | Distinct values
  ------------------+-------+----------------
  injection_flag    |     0 |               1
  meeting_id        |     0 |            1161
  company_id        |     0 |             194
  company           |     0 |             194
  ticker            |     0 |             194
  country           |     0 |              37
  market            |     0 |               2
  meeting_date      |     0 |             603
  item_no           |     0 |              67
  proposal_number   |     0 |             709
  proposal_text     |     0 |            5110
  proponent         |     0 |               2
  mgmt_rec_raw      |     0 |               6
  nbim_vote_raw     |     0 |               8
  mgmt_rec          |   421 |               4
  nbim_vote         |   334 |               4
  against_board     |   433 |               3
  rationale_text    | 13130 |              35
  position_paper    | 13390 |              16
  year              |     0 |               8
  proposal_type     |     0 |              24
  rationale_section | 13139 |              18

### 1.2 Keys and duplicates

- Exact duplicate rows: 0
- meeting_id + item_no is a unique key: True
- Meetings with more than one company: 0
- Companies with more than one name, ticker or country: 0
- The same wording twice in one meeting: 26 cases

### 1.3 How the answer columns were built

  Board (raw) |  NBIM (raw) | Board |  NBIM | against_board |  Rows
  ------------+-------------+-------+-------+---------------+------
  For         |         For |   FOR |   FOR |           0.0 | 12503
  For         |     Against |   FOR |   MOT |           1.0 |   607
  None        |        None |       |       |       (empty) |   283
  Against     |     Against |   MOT |   MOT |           0.0 |    77
  For         |    Withhold |   FOR |   MOT |           1.0 |    54
  None        |         For |       |   FOR |       (empty) |    51
  Against     |         For |   MOT |   FOR |           1.0 |    44
  For         |     Abstain |   FOR | AVSTÅ |           1.0 |    36
  One Year    |    One Year |       |       |       (empty) |    34
  None        |     Abstain |       | AVSTÅ |       (empty) |    28
  None        |     Against |       |   MOT |       (empty) |    19
  For         | Do Not Vote |   FOR |       |       (empty) |    11
  Three Years | Three Years |       |       |       (empty) |     4
  Against     |     Abstain |   MOT | AVSTÅ |           1.0 |     3
  None        | Do Not Vote |       |       |       (empty) |     2
  Abstain     |     Abstain | AVSTÅ | AVSTÅ |       (empty) |     1

433 rows have no against_board value and are left out of every evaluation:
- 334 have no NBIM vote (non-voting items such as 'Open Meeting', and 13 'Do Not Vote').
- 98 have an NBIM vote but no board recommendation ({'FOR': 51, 'MOT': 19, 'AVSTÅ': 28}), mostly director elections in Brazil, Kuwait, Taiwan.
- An abstention against a board recommendation counts as against the board (39 rows).

### 1.4 Over time (13324 rows with an answer)

  Year | Rows | Against | Developed | Emerging | Meetings | Companies | Against-votes with NBIM's reason
  -----+------+---------+-----------+----------+----------+-----------+---------------------------------
  2019 | 1447 |    6.7% |      8.0% |     4.1% |      120 |       117 |                             0/97
  2020 | 1488 |    5.6% |      6.2% |     4.4% |      126 |       121 |                            72/83
  2021 | 1525 |    6.4% |      7.3% |     4.2% |      133 |       129 |                            92/97
  2022 | 1772 |    6.6% |      5.1% |     9.6% |      144 |       140 |                          107/117
  2023 | 1761 |    4.7% |      5.3% |     3.6% |      155 |       151 |                            83/83
  2024 | 1883 |    5.2% |      5.0% |     5.6% |      168 |       164 |                            98/98
  2025 | 1909 |    5.4% |      5.6% |     5.0% |      170 |       165 |                          103/103
  2026 | 1539 |    4.3% |      4.0% |     4.7% |      140 |       135 |                            63/66

2019 has no reasons at all. 2026 stops in September.

### 1.5 Companies

- 193 companies in 37 countries; 105 developed, 88 emerging.
- 65 companies have no against-vote in the whole file.
- The 10 companies with most against-votes hold 296 of 744 (40%).
  Company                      |       Country | Rows | Against
  -----------------------------+---------------+------+--------
  Volkswagen AG                |       Germany |  320 |     125
  Tesla, Inc.                  | United States |   74 |      31
  Arbonia AG                   |   Switzerland |  179 |      30
  ORLEN SA                     |        Poland |  328 |      22
  TCC Group Holdings CO., LTD. |        Taiwan |   71 |      18
  LOTTE Chemical Corp.         |   South Korea |   74 |      17
- Companies first seen per year: {'2019': 117, '2020': 8, '2021': 13, '2022': 9, '2023': 12, '2024': 14, '2025': 13, '2026': 7}. A company's first year has no history to learn from.

### 1.6 Countries (at least 150 rows)

  Country        | Rows | Companies | Against | Against without the top company
  ---------------+------+-----------+---------+--------------------------------
  Japan          | 2403 |        28 |    1.9% |                            1.7%
  United States  | 2327 |        36 |    7.0% |                            5.8%
  China          |  966 |        15 |    4.2% |                            3.5%
  United Kingdom |  965 |        10 |    0.5% |                            0.3%
  Sweden         |  702 |         3 |    2.3% |                            1.5%
  India          |  643 |        16 |    5.3% |                            4.6%
  Switzerland    |  561 |         3 |    8.9% |                            5.2%
  Germany        |  548 |         5 |   24.8% |                            4.8%
  Cayman Islands |  491 |         8 |    3.9% |                            3.3%
  South Korea    |  488 |        12 |    7.6% |                            4.8%
  Taiwan         |  345 |         8 |    7.8% |                            3.3%
  Poland         |  328 |         1 |    6.7% |                               -
  Malaysia       |  301 |         8 |    0.0% |                            0.0%
  Denmark        |  222 |         2 |    6.3% |                            5.5%
  Thailand       |  215 |         3 |    9.3% |                            8.5%
  Hong Kong      |  212 |         1 |    0.0% |                            0.0%
  Canada         |  208 |         5 |    5.8% |                            1.2%
  South Africa   |  171 |         1 |    0.6% |                               -
  Bermuda        |  152 |         1 |    0.7% |                               -

### 1.7 Proposal types

  Type               | Rows | Against | Share of all against-votes
  -------------------+------+---------+---------------------------
  DIRECTOR_ELECTION  | 6542 |    5.4% |                        48%
  AUDITOR            | 1091 |    2.3% |                         3%
  FIN_STATEMENTS     |  816 |    1.0% |                         1%
  DISCHARGE          |  759 |   15.0% |                        15%
  DIVIDEND           |  650 |    0.8% |                         1%
  OTHER_MGMT         |  618 |    5.5% |                         5%
  SAY_ON_PAY         |  550 |    8.2% |                         6%
  DIRECTOR_PAY       |  379 |    0.5% |                         0%
  EQUITY_PLAN        |  375 |    1.9% |                         1%
  ARTICLES           |  337 |   10.1% |                         5%
  SHARE_ISSUANCE     |  334 |    2.1% |                         1%
  ROUTINE            |  311 |    1.0% |                         0%
  SHARE_REPURCHASE   |  192 |    0.0% |                         0%
  RPT                |  181 |    7.2% |                         2%
  MERGER             |   48 |    8.3% |                         1%
  OTHER_BUSINESS     |   44 |  100.0% |                         6%
  SHP_OTHER          |   42 |   19.0% |                         1%
  SHP_SUSTAINABILITY |   24 |   58.3% |                         2%
  SHP_GOVERNANCE     |   20 |   85.0% |                         2%
  ANTITAKEOVER       |    5 |   40.0% |                         0%
  SHP_INDEP_CHAIR    |    3 |  100.0% |                         0%
  DUAL_CLASS         |    2 |    0.0% |                         0%
  CLASSIFY_BOARD     |    1 |    0.0% |                         0%

OTHER_MGMT is a catch-all. Inside it:
- named director or manager appointed: 55 rows, against 14.5%
- pay, commission or allowance: 110 rows, against 3.6%
- rules, systems or articles changed: 57 rows, against 19.3%

### 1.8 Shareholder proposals

150 with an answer. Board recommends: {'MOT': 121, 'FOR': 29}. NBIM votes: {'MOT': 77, 'FOR': 70, 'AVSTÅ': 3}.
NBIM's support for proposals the board opposed, by year: 2019 4/7, 2020 5/7, 2021 7/8, 2022 8/25, 2023 4/27, 2024 9/17, 2025 4/17, 2026 3/13

### 1.9 New situations and repeats

Of 744 against-votes: NBIM opposed the same item at that company before in 189, supported it before in 119, and the item was not seen before in 436.
- opposed last time: 305 rows, against now 62.0%
- supported last time: 6996 rows, against now 1.7%
- item not seen before: 6023 rows, against now 7.2%

### 1.10 Inside a meeting

- 1156 meetings. No against-vote in 760, one in 282, two or more in 114.
- Order on the ballot, meetings with at least three director items:
  Director listed | Rows | Against | Against, where NBIM had not opposed that person before
  ----------------+------+---------+-------------------------------------------------------
  first           |  807 |   14.0% |                                                   8.3%
  second          |  807 |    4.7% |                                                   3.9%
  third or later  | 4613 |    3.2% |                                                   2.3%

  Same, by country (people NBIM had not opposed before):
  Country        | First listed | Against | Listed later | Against
  ---------------+--------------+---------+--------------+--------
  United States  |          183 |    4.4% |         1445 |    3.2%
  Japan          |          180 |    8.9% |         1694 |    0.1%
  United Kingdom |           49 |    0.0% |          380 |    0.3%
  Cayman Islands |           35 |   11.4% |          115 |    2.6%
  India          |           31 |    3.2% |           88 |    6.8%
  South Korea    |           30 |   36.7% |          164 |    4.9%
  Malaysia       |           23 |    0.0% |           71 |    0.0%
  Thailand       |           22 |    9.1% |           62 |    3.2%
  Sweden         |           20 |    0.0% |          157 |    5.1%
  Canada         |           19 |    0.0% |          145 |    4.8%
  Switzerland    |           19 |   15.8% |          184 |    5.4%
  Taiwan         |           16 |   18.8% |          122 |    2.5%

- Number of directors on the ballot:
  Director items in the meeting | Rows | Against
  ------------------------------+------+--------
  1-2                           |  315 |   17.5%
  3-6                           | 1281 |    8.8%
  7-9                           | 1826 |    5.1%
  10-12                         | 2056 |    3.0%
  13 or more                    | 1064 |    3.0%

- What the wording of a director item says:
  Wording                                          | Rows | Against
  -------------------------------------------------+------+--------
  named 'independent' or 'outside'                 |  174 |    4.0%
  named 'non-independent', 'inside' or 'executive' |  222 |   13.5%
  supervisory board                                |   70 |   37.1%
  chair in the wording                             |  101 |   14.9%
  several people in one item                       |   28 |   25.0%
  all director items                               | 6542 |    5.4%

- If NBIM opposed anything at a company's previous meeting, it opposes something at the next in 58% of cases; otherwise in 21%.

## 2. Second file: data/dirty/npx_votes.csv

52906 rows from US Form N-PX filings. It is another investor's votes, not NBIM's, although the column is called nbim_vote.
- Empty columns: ticker, proposal_number, rationale_text, position_paper, rationale_section.
- 11659 texts are in capitals, 771 are notes to voters and not proposals, 141 carry the organisers' injection flag.
- The against_board column marks 1936 rows. The source field it is built on means 'this vote was for or against management' and marks 2626 rows. Only 833 rows are in both.
- Proof from the 149 proposals that are in both files: where the N-PX field says FOR, the vote is FOR when NBIM's file says the board recommended FOR (118 rows) and AGAINST when the board recommended against (25 rows). So the field is 'for management', not 'the board recommended for'.
- Use `mgmt_rec_raw == 'AGAINST'` as the answer for this file.

## 3. Pay file: data/dirty/nbim_pay_votes.csv

4877 rows from Norges Bank's own Form N-PX filings: {'2024-08-30': 1890, '2025-08-29': 1630, '2026-08-28': 1357}.
- Exact duplicate rows: 7. Rows with no vote recorded: 20.
- Votes (vote, for or against management): {('FOR', 'FOR'): 3976, ('ONE YEAR', 'FOR'): 436, ('AGAINST', 'AGAINST'): 411, ('THREE YEARS', 'FOR'): 30, ('', ''): 20, ('AGAINST', 'FOR'): 2}
- Frequency votes ('ONE YEAR' and so on) were never against management. Merger payout votes are one-off events.
- Every category is 'SECTION 14A SAY-ON-PAY VOTES': the file holds pay votes only.
