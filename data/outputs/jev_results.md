# Jev pipeline: walk-forward results with company facts

Produced by `python src/report_results.py`, from saved Jev answers (no API calls).

## How each year is scored

- **Walk-forward.** The combination (weights, review share, model flag) is fitted on all earlier years with a Jev run, pooled. The triage model trains on earlier years only.
- **Live review share.** Each proposal is ranked against the previous 12 months of scores, starting from last year's run, as a live system would. Nothing from later in the year is used.
- **Recommendation:** MOT when Jev votes MOT and the triage model is at or above the flag, or when NBIM's rule 1.3.1 (a US nominee who is both CEO and chair) fires and its drift monitor still trusts it. Every recommended MOT goes to a person.
- **Skip rule:** a group (proposal type, or nominee role in Japan, Korea or the US) skips review when NBIM opposed none of at least 100 such proposals in earlier years.
- **Company facts**, all from documents filed before the meeting: Japan (EDINET annual reports: nominee role, board independence), US (main's reading of each proxy: nominee role, independence, chair, attendance; last year's vote results from SEC 8-K item 5.07; CEO pay), Korea (OpenDART: board composition, CEO also chair; nominee role from the ballot). They go to the triage model and into Jev's input.
- **Target:** NBIM voted MOT. Abstentions count as not MOT.

## Every test year

| Year | Fitted on | Proposals | MOT | Board F1 | Jev alone F1 | Precision | Recall | F1 | Review | MOT reaching a person | AP combined | Right section |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 2021-2021 | 1772 | 112 | 24.8% | 43.3% | 53.2% | 29.5% | **37.9%** | **36.0%** | 92 (82.1%) | 0.344 | 30/33 |
| 2023 | 2021-2022 | 1761 | 100 | 36.2% | 47.5% | 72.2% | 52.0% | **60.5%** | **41.9%** | 84 (84.0%) | 0.457 | 27/29 |
| 2024 | 2021-2023 | 1883 | 98 | 17.1% | 40.5% | 69.6% | 39.8% | **50.6%** | **41.9%** | 94 (95.9%) | 0.539 | 28/31 |
| 2025 | 2021-2024 | 1909 | 112 | 20.2% | 46.4% | 76.4% | 37.5% | **50.3%** | **36.8%** | 96 (85.7%) | 0.564 | 29/33 |
| 2026 | 2021-2025 | 1539 | 66 | 20.0% | 43.1% | 64.2% | 51.5% | **57.1%** | **41.1%** | 63 (95.5%) | 0.539 | 26/27 |

2021 is not a test year: there is no earlier Jev year to fit on. 2019 and 2020 have no runs: the triage model needs two earlier years of votes.

## What each piece adds

Average over the test years. Each row adds one piece to the row above.

| Setup | F1 | Precision | Recall | Review | MOT reaching a person |
|---|---:|---:|---:|---:|---:|
| No company facts, ranked within the year | **51.8%** | 65.4% | 43.5% | **46.7%** | 87.8% |
| + live review share (previous 12 months) | **51.8%** | 65.4% | 43.5% | **48.0%** | 88.1% |
| + company facts in the model and in Jev's input | **51.2%** | 67.6% | 41.9% | **41.8%** | 88.6% |
| + chair-and-CEO rule with drift monitor | **51.3%** | 67.1% | 42.1% | **41.8%** | 88.6% |
| + skip rule (the full system) | **51.3%** | 67.1% | 42.1% | **39.5%** | 88.6% |

## Skip rule

Groups that skip review, learned from earlier years only:

| Year | Groups | Proposals skipped | MOT among them |
|---|---:|---:|---:|
| 2022 | type: DIVIDEND; type: ROUTINE | 0 | 0 |
| 2023 | type: ROUTINE | 0 | 0 |
| 2024 | Japan: executive director; Japan: independent outside director; Japan: inside director; type: ROUTINE | 91 | 0 |
| 2025 | Japan: executive director; Japan: independent outside director; Japan: inside director; type: ROUTINE | 34 | 0 |
| 2026 | Japan: executive director; Japan: independent outside director; Japan: inside director; type: ROUTINE | 76 | 0 |

## Chair-and-CEO rule (US, NBIM rule 1.3.1)

| Year | Nominees who are CEO and chair | NBIM MOT | Rule active (monitor) | MOT when active |
|---|---:|---:|---:|---:|
| 2022 | 6 | 5/6 | 6 | 5/6 |
| 2023 | 6 | 5/6 | 6 | 5/6 |
| 2024 | 6 | 5/6 | 6 | 5/6 |
| 2025 | 6 | 4/6 | 6 | 4/6 |
| 2026 | 5 | 0/5 | 0 | 0/0 |

## Coverage of the company facts

| Proposals | In test years | With facts | NBIM MOT |
|---|---:|---:|---:|
| Japan director | 1170 | 1170 (100.0%) | 47 |
| Korea director | 168 | 168 (100.0%) | 24 |
| US director | 1126 | 1124 (99.8%) | 57 |
| US pay vote | 134 | 132 (98.5%) | 13 |

## What to keep in mind

- **The design was chosen while looking at 2025 and 2026.** Walk-forward fitting removes tuning on the test year, but not that.
- How each year was used: 2021 run once, after the design was fixed; 2022 run once, after the design was fixed; 2023 run once, after the design was fixed; 2024 used to check the design; 2025 used to design the system; 2026 holdout, seen before the design was final.
- EDINET only keeps AGM vote results from mid-2024, so Japanese last-year support reaches 2025-26 only. US vote results go back to 2018.
- US nominee facts come from main's AI reading of each proxy; their accuracy is main's, and is checked there.
- Each MOT vote is 1-2 percentage points of recall, so small differences between years are noise.
