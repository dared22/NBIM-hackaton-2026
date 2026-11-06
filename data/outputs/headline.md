# Headline numbers, test year 2026

Written by `python3 src/run.py`. The year was not used to fit or choose anything, except where `docs/model-card.md` says how often it has been scored.

## NBIM's vote file, all countries: 1539 proposals, 66 against the board

Always following the board is right on 96% of proposals and finds none of the 66.

| Method | Says against | Right | Wrong | Precision | Recall |
|---|---|---|---|---|---|
| Always follow the board | 0 | 0 | 0 | - | 0% |
| Same as last time at this company | 38 | 22 | 16 | 58% | 33% |
| The tool, acting alone | 33 | 26 | 7 | 79% | 39% |

The tool sends 404 proposals (26%) to a person, and 30 against-votes are among them. So 56 of the 66 against-votes (85%) are either suggested by the tool or put in front of a person, and 10 are waved through.

### If a person reads more

The 5% level, below which the tool follows the board on its own, is a setting. Lower it and more proposals go to a person, in the order of the tool's own probability. The careful level is the one that would have put 90% of the against-votes of the earlier years (2022-2025) in front of a person or in the tool's own suggestions. It was chosen on those years only.

| Level | Sent to a person | Share | Against-votes suggested or seen | Waved through |
|---|---|---|---|---|
| 5% (as above) | 404 | 26% | 56 of 66 (85%) | 10 |
| 3% | 610 | 40% | 64 of 66 (97%) | 2 |
| Careful level, 2.1% | 751 | 49% | 65 of 66 (98%) | 1 |
| 2% | 811 | 53% | 65 of 66 (98%) | 1 |
| 1% | 1139 | 74% | 66 of 66 (100%) | 0 |

The proposals a lower level adds are the rows of `data/outputs/decisions_2026.csv` decided automatically with the board, sorted by `probability_against_board`.

## US executive pay votes: 1200 votes, 114 against the board

Always following the board is right on 90% of votes and finds none of the 114.

| Method | Says against | Right | Wrong | Precision | Recall |
|---|---|---|---|---|---|
| Always follow the board | 0 | 0 | 0 | - | 0% |
| Same as last season | 97 | 42 | 55 | 43% | 37% |
| Against if the CEO is paid 25 million dollars or more | 155 | 83 | 72 | 54% | 73% |
| The tool, acting alone | 93 | 69 | 24 | 74% | 61% |

The tool sends 371 votes (31%) to a person, and 36 against-votes are among them. So 105 of the 114 against-votes (92%) are either suggested or seen, and 9 are waved through.

## How to read these

- "Says against" for the tool counts only what it suggests on its own. What it sends to a person is counted in the sentence under each table.
- The two test sets are separate files and do not add up to one total.
- Intervals, the earlier years and everything that was tested and left out are in `data/outputs/results.md` and `docs/model-card.md`.
