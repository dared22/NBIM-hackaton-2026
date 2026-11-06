# Headline numbers, test year 2026

## Prediction quality: MOT votes

Positive class: actual vote MOT (US pay AGAINST/WITHHOLD is mapped to MOT). AVSTÅ is not MOT. Automatic-only recall uses all actual MOT votes, including those sent to review. TP = correct MOT, FP = incorrect MOT, FN = missed MOT. Undefined metrics are shown as 0%. History is frozen before the test year/season; missing history follows the board. The datasets are scored separately.

### All proposal types

1539 proposals; 66 actual MOT votes.

| Method                     | Predicted MOT | TP | FP | FN | Precision | Recall | F1    |
| -------------------------- | ------------- | -- | -- | -- | --------- | ------ | ----- |
| Model: all suggestions     | 54            | 34 | 20 | 32 | 63.0%     | 51.5%  | 56.7% |
| Model: automatic only      | 31            | 24 | 7  | 42 | 77.4%     | 36.4%  | 49.5% |
| Baseline: follow board     | 14            | 8  | 6  | 58 | 57.1%     | 12.1%  | 20.0% |
| Baseline: repeat last vote | 51            | 30 | 21 | 36 | 58.8%     | 45.5%  | 51.3% |

### US executive pay votes

1200 proposals; 114 actual MOT votes.

| Method                       | Predicted MOT | TP | FP | FN  | Precision | Recall | F1    |
| ---------------------------- | ------------- | -- | -- | --- | --------- | ------ | ----- |
| Model: all suggestions       | 99            | 75 | 24 | 39  | 75.8%     | 65.8%  | 70.4% |
| Model: automatic only        | 93            | 69 | 24 | 45  | 74.2%     | 60.5%  | 66.7% |
| Baseline: follow board       | 0             | 0  | 0  | 114 | 0.0%      | 0.0%   | 0.0%  |
| Baseline: repeat last season | 98            | 43 | 55 | 71  | 43.9%     | 37.7%  | 40.6% |
| Baseline: CEO pay >= $25m    | 155           | 83 | 72 | 31  | 53.5%     | 72.8%  | 61.7% |

### US executive pay votes (history + company facts)
- Proposals: 1200; NBIM voted against the board on 114.
- Decided automatically: 829 (69%). Sent to a person: 371 (31%).
- Automatic 'against the board' suggestions: 93, of which 69 were right (precision 74%, recall 61%).
- Against-votes inside the pile sent to a person: 36 (32% of all against-votes).
- Against-votes the tool waved through with the board: 9 (8% of all against-votes).
- With a person reading the review pile, 105 of 114 against-votes are either suggested or seen (92%).
- Sent to a person although the model's probability was low (nothing to go on, or a rule applies that the tool does not act on alone): 85 proposals; 2 of them were against-votes.

### All proposal types (combined model, plus NBIM rules for US directors and worded proposals)
- Proposals: 1539; NBIM voted against the board on 66.
- Decided automatically: 1135 (74%). Sent to a person: 404 (26%).
- Automatic 'against the board' suggestions: 33, of which 26 were right (precision 79%, recall 39%).
- Against-votes inside the pile sent to a person: 30 (45% of all against-votes).
- Against-votes the tool waved through with the board: 10 (15% of all against-votes).
- With a person reading the review pile, 56 of 66 against-votes are either suggested or seen (85%).
- Sent to a person although the model's probability was low (nothing to go on, or a rule applies that the tool does not act on alone): 47 proposals; 1 of them were against-votes.
