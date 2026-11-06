# Strict 2026 holdout: learned from 2025 only

Produced by `python -m nbim_vote.holdout_2026` (no API calls; `--jev` adds the frozen-history Jev run). Every fitted part learns from 2025 proposals; 2026 proposals enter with NBIM's vote and rationale blanked, and NBIM's history is frozen on 1 January 2026. The answers are read once, after every recommendation is made. See the module docstring for the details.

2026: 1539 proposals, 66 MOT. Trained on 1909 proposals from 2025.

| Setup | Precision | Recall | F1 | Review | MOT reaching a person | AP combined | AP triage |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline: follow the board | 57.1% | 12.1% | **20.0%** | – | – | – | – |
| Without Jev (strict) | 42.9% | 45.5% | **44.1%** | **57.7%** | 65 (98.5%) | 0.478 | 0.493 |
| With Jev, history frozen at 1 January 2026 (strict in data) | 61.5% | 48.5% | **54.2%** | **45.0%** | 63 (95.5%) | 0.496 | 0.493 |
| With Jev's saved v7 answers (not strict, see below) | 61.5% | 48.5% | **54.2%** | **45.0%** | 63 (95.5%) | 0.496 | 0.493 |

Settings learned from 2025: without Jev: triage flag 0.264, review share 44.8%; Jev frozen: triage flag 0.264, review share 44.8%; Jev v7: triage flag 0.264, review share 44.8%

## Read this

- **Without Jev is strict.** No part of it has seen a 2026 vote, a 2026 rationale or a vote at an earlier 2026 meeting.
- **With Jev, frozen history** asks Jev again with the same input as v7, except that NBIM's earlier votes stop at 31 December 2025 (`--jev`). It sees no 2026 vote. The v7 input design was still chosen while looking at 2026, and Jev may have seen NBIM's public votes in its own training.
- **With Jev's saved v7 answers is not strict.** Those answers were made with NBIM's votes at earlier 2026 meetings in Jev's input.
- **Frozen history costs something.** A live system would know NBIM's votes at earlier 2026 meetings; here a December meeting sees nothing after 31 December 2025. The walk-forward report uses that live history.
- **The design was not made blind.** Inputs, rules and settings were chosen in earlier runs that included 2026. This run keeps 2026 out of the fitting, not out of the design history.
- **One year of training.** The walk-forward report fits on all earlier years; 2025 alone is less data.
- **2026 is small.** 66 MOT votes: each is about 1.5 points of recall.
