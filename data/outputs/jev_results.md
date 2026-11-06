# Jev pipeline: walk-forward results with company facts

Produced by `python -m nbim_vote.report_results`, from saved Jev answers (no API calls).

## Read this first

- **2026 is not a clean holdout.** It was run six times (v2-v7) while the design changed. The first run, before any change made after seeing it, is the honest 2026 number (table below). Its F1 is close to the tuned run; its review share is much higher. The cut in review effort was found while looking at 2026.
- 2024 and 2025 were used to design and check the system. 2022 and 2023 were run with several Jev input variants (v4-v7, v5-v7); git cannot show that the design was frozen before their results were seen. They are still the cleanest years.
- **Citations are scored optimistically for 2022-2024.** The map from proposal type to candidate guideline sections (`TYPE_TO_SECTIONS`) was built from the sections NBIM cited at meetings before 2025, so those years' own citations helped decide which rules Jev may name.
- **Jev may have seen NBIM's votes in training.** NBIM's votes and rationales are public since 2013 and Jev's training cutoff is unknown. Jev alone scores about the same in every year (F1 40-47%), including 2026, so there is no sign of a large effect, but it cannot be ruled out for the earlier years.
- **The board-MOT rule was chosen on 2021-2025** (the share of board-MOT proposals where the recommendation matches NBIM's vote), which overlaps the test years 2022-2025. It touches 14-27 proposals a year.
- **Confidence** is the combined score's rank against the previous 12 months, not Jev's own confidence. It decides which proposals a person sees.

## How each year is scored

- **Walk-forward.** The combination (weights, review share, model flag) is fitted on all earlier years with a Jev run, pooled. The triage model trains on earlier years only.
- **Live review share.** Each proposal is ranked against the previous 12 months of scores, starting from last year's run, as a live system would. Nothing from later in the year is used.
- **Recommendation:** MOT when Jev votes MOT and the triage model is at or above the flag, or when one of NBIM's director rules, applied in code to facts filed before the meeting, fires with verified facts and is trusted. AVSTÅ when Jev's top choice is AVSTÅ. Otherwise the board's recommendation, except that a board MOT becomes FOR when Jev and the triage model both say NBIM would not oppose. Every MOT, AVSTÅ and departure from the board goes to a person.
- **Skip rule:** a group (proposal type, or nominee role in Japan, Korea or the US) skips review when NBIM opposed none of at least 100 such proposals in earlier years.
- **Company facts**, all from documents filed before the meeting: Japan (EDINET annual reports: nominee role, board independence), US (main's reading of each proxy: nominee role, independence, chair, attendance; last year's vote results from SEC 8-K item 5.07; CEO pay), Korea (OpenDART: board composition, CEO also chair; nominee role from the ballot). They go to the triage model and into Jev's input.
- **Target:** NBIM voted MOT. Abstentions count as not MOT.

## Every test year

| Year | Fitted on | Proposals | MOT | Board F1 | Jev alone F1 | Precision | Recall | F1 | Review | MOT reaching a person | AP combined | Right section: code / Jev |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 2021-2021 | 1772 | 112 | 24.8% | 43.3% | 54.5% | 37.5% | **44.4%** | **37.1%** | 99 (88.4%) | 0.373 | 27 / 27 of 29 |
| 2023 | 2021-2022 | 1761 | 100 | 36.2% | 47.5% | 71.2% | 52.0% | **60.1%** | **40.3%** | 84 (84.0%) | 0.453 | 28 / 27 of 29 |
| 2024 | 2021-2023 | 1883 | 98 | 17.1% | 40.5% | 70.6% | 49.0% | **57.8%** | **46.1%** | 95 (96.9%) | 0.545 | 38 / 34 of 38 |
| 2025 | 2021-2024 | 1909 | 112 | 20.2% | 46.4% | 73.8% | 42.9% | **54.2%** | **35.6%** | 97 (86.6%) | 0.566 | 36 / 33 of 37 |
| 2026 (tuned on it) | 2021-2025 | 1539 | 66 | 20.0% | 43.1% | 62.5% | 53.0% | **57.4%** | **44.4%** | 64 (97.0%) | 0.538 | 27 / 26 of 27 |
| **2026 clean (v2, as first run)** | 2025 only | 1539 | 66 | 20.0% | – | 53.8% | 53.0% | **53.4%** | **73.4%** | 66 (100.0%) | – | – |

2021 is not a test year: there is no earlier Jev year to fit on. 2019 and 2020 have no runs: the triage model needs two earlier years of votes. The clean 2026 row is the pipeline as it stood then (Jev + triage model, routing fitted on 2025, no company facts, no live review share), read from `results_2026_history_v2.csv`. Right section: correct MOT recommendations where the guideline section named matches the one NBIM cited, with citations from code (the default) and from Jev.

## What each piece adds

Average over the test years. Each row adds one piece to the row above.

| Setup | F1 | Precision | Recall | Review | MOT reaching a person |
|---|---:|---:|---:|---:|---:|
| No company facts, ranked within the year | **54.7%** | 67.7% | 46.4% | **46.9%** | 87.7% |
| + live review share (previous 12 months) | **54.7%** | 67.7% | 46.4% | **47.9%** | 88.5% |
| + company facts in the model and in Jev's input | **53.9%** | 65.7% | 46.1% | **43.1%** | 90.4% |
| + NBIM's director rules in code, with trust monitor | **54.1%** | 66.5% | 45.9% | **43.3%** | 90.6% |
| + skip rule | **54.1%** | 66.5% | 45.9% | **40.7%** | 90.6% |
| + main's pay model on US say-on-pay votes (the full system) | **54.8%** | 66.5% | 46.9% | **40.7%** | 90.6% |

## Main's pay model on US say-on-pay votes

Main's model (`src/agent/pay_model.py` on main, ported in `pay_model.py`): logistic regression on NBIM's say-on-pay votes from Norges Bank's N-PX filings, with pay facts from each meeting's own proxy (pay size, the 25 million dollar level, pay against peers, pay growth against shareholder returns, and NBIM's vote last season). Here it is fitted walk-forward: the model for a year sees only N-PX votes at meetings before 1 January that year, and SEC API figures reported after the meeting are not used. It decides like a director rule: MOT at its own cut-off (chosen on earlier votes), a person above 5 %. N-PX starts in July 2023, so it scores 2024 onwards.

On all N-PX pay votes (its own data, much larger than this branch's sample):

| Year | Pay votes | Against | AP | AP, last season's vote only | Precision at cut-off | Recall at cut-off |
|---|---:|---:|---:|---:|---:|---:|
| 2024 | 1524 | 135 | 0.579 | 0.108 | 45.8% | 60.0% |
| 2025 | 1429 | 118 | 0.678 | 0.199 | 48.3% | 70.3% |
| 2026 | 1039 | 100 | 0.702 | 0.222 | 63.3% | 76.0% |

On this branch's US say-on-pay votes, in the full pipeline:

| Year | Pay model | Linked pay votes | NBIM MOT | Recommended MOT, right | False alarms | MOT reaching a person | Reviewed |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | without | 0 | 0 | 0 | 0 | 0 | 0 |
| 2022 | with | 0 | 0 | 0 | 0 | 0 | 0 |
| 2023 | without | 0 | 0 | 0 | 0 | 0 | 0 |
| 2023 | with | 0 | 0 | 0 | 0 | 0 | 0 |
| 2024 | without | 33 | 6 | 0 | 0 | 6 | 32 |
| 2024 | with | 33 | 6 | 4 | 2 | 6 | 32 |
| 2025 | without | 31 | 4 | 2 | 2 | 4 | 30 |
| 2025 | with | 31 | 4 | 3 | 2 | 4 | 30 |
| 2026 | without | 18 | 0 | 0 | 2 | 0 | 18 |
| 2026 | with | 18 | 0 | 0 | 2 | 0 | 18 |

Ten MOT votes in 2024-2025 is far too few to measure precision here; the N-PX table is the real test of the model.

## With and without Jev

Without Jev (`--no-jev`), the triage model's own call replaces Jev's vote, the combination is refitted without Jev's feature on the same earlier years, and the director rules, skip rule and code citations work as before. Everything else is the same walk-forward setup.

| Year | Pipeline | Precision | Recall | F1 | Review | MOT reaching a person | AP combined |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | with Jev | 54.5% | 37.5% | **44.4%** | **37.1%** | 99 (88.4%) | 0.373 |
| 2022 | without Jev | 45.7% | 28.6% | **35.2%** | **42.9%** | 97 (86.6%) | 0.317 |
| 2023 | with Jev | 71.2% | 52.0% | **60.1%** | **40.3%** | 84 (84.0%) | 0.453 |
| 2023 | without Jev | 41.6% | 47.0% | **44.1%** | **42.2%** | 78 (78.0%) | 0.432 |
| 2024 | with Jev | 70.6% | 49.0% | **57.8%** | **46.1%** | 95 (96.9%) | 0.545 |
| 2024 | without Jev | 54.5% | 55.1% | **54.8%** | **57.0%** | 97 (99.0%) | 0.512 |
| 2025 | with Jev | 73.8% | 42.9% | **54.2%** | **35.6%** | 97 (86.6%) | 0.566 |
| 2025 | without Jev | 64.5% | 43.8% | **52.1%** | **40.1%** | 100 (89.3%) | 0.530 |
| 2026 | with Jev | 62.5% | 53.0% | **57.4%** | **44.4%** | 64 (97.0%) | 0.538 |
| 2026 | without Jev | 47.6% | 59.1% | **52.7%** | **47.7%** | 61 (92.4%) | 0.551 |
| **Average** | with Jev | 66.5% | 46.9% | **54.8%** | **40.7%** | 90.6% | 0.495 |
| **Average** | without Jev | 50.8% | 46.7% | **47.8%** | **46.0%** | 89.1% | 0.469 |

## Citations: code or Jev

On every proposal NBIM voted MOT on with a guideline section in its rationale, whether or not it was recommended: does the citation name NBIM's section? Jev's is the MOT rule it rated highest; code's comes from `src/nbim_vote/citations.py` (rule in code, then NBIM's earlier reason for the same item, then for the same company and proposal type, then a text model trained on earlier years only). Both see only earlier meetings. Jev's candidate rules were mapped from NBIM's citations before 2025, so Jev's 2022-2024 numbers are optimistic. The order of the code sources was set before this comparison and checked on 2020-2021 only.

| Year | NBIM MOT with a section | Jev names it | Code names it |
|---|---:|---:|---:|
| 2022 | 95 | 69 (72.6%) | 74 (77.9%) |
| 2023 | 77 | 43 (55.8%) | 64 (83.1%) |
| 2024 | 88 | 74 (84.1%) | 68 (77.3%) |
| 2025 | 99 | 69 (69.7%) | 70 (70.7%) |
| 2026 | 58 | 45 (77.6%) | 45 (77.6%) |
| **All** | 417 | **300 (71.9%)** | **321 (77.0%)** |

Code citations by source, all test years:

| Source | Cases | Names NBIM's section |
|---|---:|---:|
| text model | 153 | 102 (66.7%) |
| NBIM's earlier reason, same item | 139 | 136 (97.8%) |
| NBIM's earlier reason, same company | 103 | 62 (60.2%) |
| rule in code | 22 | 21 (95.5%) |

## When the board recommends MOT

Mostly shareholder proposals. The earlier rule voted FOR unless Jev and the model both said MOT, which went against the board without a reason. The vote now follows the board unless Jev and the model both say NBIM would support the proposal.

| Year | Board MOT | NBIM MOT | Matches NBIM, earlier rule | Matches NBIM, now | Matches NBIM, always follow the board |
|---|---:|---:|---:|---:|---:|
| 2022 | 25 | 17 | 6 | 14 | 17 |
| 2023 | 27 | 23 | 17 | 24 | 23 |
| 2024 | 19 | 10 | 12 | 14 | 10 |
| 2025 | 17 | 13 | 13 | 13 | 13 |
| 2026 | 14 | 8 | 10 | 11 | 8 |

## Abstentions (AVSTÅ)

AVSTÅ is recommended when Jev's top choice is AVSTÅ, and always goes to a person. NBIM abstains on about 0.5% of proposals.

| Year | Recommended AVSTÅ | NBIM abstained on those | NBIM abstentions in all |
|---|---:|---:|---:|
| 2022 | 3 | 2 | 14 |
| 2023 | 8 | 1 | 2 |
| 2024 | 2 | 1 | 1 |
| 2025 | 2 | 0 | 0 |
| 2026 | 1 | 0 | 5 |

## Skip rule

Groups that skip review, learned from earlier years only:

| Year | Groups | Proposals skipped | MOT among them |
|---|---:|---:|---:|
| 2022 | type: DIVIDEND; type: ROUTINE | 0 | 0 |
| 2023 | type: ROUTINE | 0 | 0 |
| 2024 | Japan: executive director; Japan: independent outside director; Japan: inside director; type: ROUTINE | 95 | 0 |
| 2025 | Japan: executive director; Japan: independent outside director; Japan: inside director; type: ROUTINE | 32 | 0 |
| 2026 | Japan: executive director; Japan: independent outside director; Japan: inside director; type: ROUTINE | 96 | 0 |

## NBIM's director rules, applied in code

Each rule is NBIM's own (guideline number), applied to facts filed before the meeting: US facts from main's AI reading of the proxy (a quote checked against the text), Japanese facts from the EDINET annual report. A rule decides MOT on its own only when NBIM followed it at the last 2 earlier meetings where it fired and its facts are verified; otherwise the proposal goes to a person with the fact. The trust rule is main's, untuned. The rules were chosen from the guideline text and main's list, which main says was made after looking at all years.

| Year | Rule | Fired | NBIM MOT | Decided alone | MOT when decided | Sent to a person |
|---|---:|---:|---:|---:|---:|---:|
| 2022 | 1.1.1 (Japan EDINET) | 5 | 0 | 0 | – | 5 |
| 2022 | 1.2.1 (US proxy) | 1 | 1 | 0 | – | 1 |
| 2022 | 1.3.1 (US proxy) | 6 | 5 | 5 | 5/5 | 1 |
| 2022 | 2.1.1 (US proxy) | 2 | 1 | 0 | – | 2 |
| 2022 | 2.1.2 (US proxy) | 2 | 1 | 0 | – | 2 |
| 2023 | 1.1.1 (Japan EDINET) | 7 | 0 | 0 | – | 7 |
| 2023 | 1.2.1 (US proxy) | 1 | 0 | 0 | – | 1 |
| 2023 | 1.3.1 (US proxy) | 6 | 5 | 1 | 1/1 | 5 |
| 2023 | 2.1.1 (US proxy) | 3 | 1 | 0 | – | 3 |
| 2023 | 2.1.2 (US proxy) | 1 | 0 | 0 | – | 1 |
| 2024 | 1.1.1 (Japan EDINET) | 3 | 0 | 0 | – | 3 |
| 2024 | 1.3.1 (US proxy) | 6 | 5 | 4 | 3/4 | 2 |
| 2024 | 2.1.1 (US proxy) | 2 | 0 | 0 | – | 2 |
| 2025 | 1.1.1 (Japan EDINET) | 4 | 0 | 0 | – | 4 |
| 2025 | 1.3.1 (US proxy) | 6 | 4 | 2 | 1/2 | 4 |
| 2025 | 2.1.2 (US proxy) | 2 | 0 | 0 | – | 2 |
| 2025 | 2.3.1 (US proxy) | 1 | 1 | 0 | – | 1 |
| 2026 | 1.1.1 (Japan EDINET) | 3 | 0 | 0 | – | 3 |
| 2026 | 1.3.1 (US proxy) | 5 | 0 | 0 | – | 5 |
| 2026 | 2.1.2 (US proxy) | 2 | 0 | 0 | – | 2 |
| 2026 | 2.3.1 (US proxy) | 1 | 0 | 0 | – | 1 |

## Coverage of the company facts

| Proposals | In test years | With facts | NBIM MOT |
|---|---:|---:|---:|
| Japan director | 1170 | 1170 (100.0%) | 47 |
| Korea director | 168 | 168 (100.0%) | 24 |
| US director | 1126 | 1124 (99.8%) | 57 |
| US pay vote | 134 | 132 (98.5%) | 13 |

## Resistance test

An instruction is added to what the agent reads; see `resistance_2025_def14a_n60_enriched.md`, `resistance_2025_history_n100_enriched.md` for the full tables. Run with `python -m nbim_vote.jev_mvp --year 2025 --n 100 --level history --resistance --enrich`.

## What to keep in mind

- How each year was used: 2021 run with several Jev input variants (v4-v7); 2022 run with several Jev input variants (v4-v7); 2023 run with several Jev input variants (v5-v7); 2024 used to check the design; 2025 used to design the system; 2026 holdout, run six times (v2-v7) while the design changed.
- EDINET only keeps AGM vote results from mid-2024, so Japanese last-year support reaches 2025-26 only. US vote results go back to 2018.
- US nominee facts come from main's AI reading of each proxy; their accuracy is main's, and is checked there.
- Each MOT vote is 1-2 percentage points of recall, so small differences between years are noise.
