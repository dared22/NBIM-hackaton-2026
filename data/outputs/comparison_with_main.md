# Comparison: marie's Jev pipeline (with company facts) and main's system

Produced by `python src/report_results.py --main-dir <checkout of main>`. Same proposals for both systems every year (`data/dirty/real_votes.csv`). marie is scored walk-forward with a live review share. Full numbers in `comparison_with_main.csv`.

main predicts **against the board**, marie predicts **NBIM voted MOT**. They differ on shareholder proposals and abstentions, so every number is shown for both targets.

## Headline: average over 2022-2026

| Target | System | F1 | Precision | Recall | Review | Reaching a person | Avg precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| NBIM voted MOT | marie: Jev pipeline + facts | **51.3%** | 67.1% | 42.1% | 39.5% | 88.6% | 0.489 |
| NBIM voted MOT | main: history model | **38.3%** | 45.9% | 34.5% | 25.0% | 70.6% | 0.361 |
| NBIM voted MOT | Follow the board | **23.7%** | 67.9% | 14.4% | – | – | – |
| against the board | marie: Jev pipeline + facts | **43.4%** | 55.8% | 36.2% | 39.5% | 85.3% | 0.393 |
| against the board | main: history model | **42.2%** | 49.7% | 39.0% | 25.0% | 73.6% | 0.417 |
| against the board | Follow the board | **11.1%** | 32.1% | 6.8% | – | – | – |

## Year by year, target: NBIM voted MOT

| Year | System | Precision | Recall | F1 | Hits | False alarms | Review | Reaching a person | Never seen | Avg precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022 | marie: Jev pipeline + facts | 53.2% | 29.5% | **37.9%** | 33 | 29 | 36.0% | 92/112 (82.1%) | 20 | 0.344 |
| 2022 | main: history model | 39.4% | 46.4% | **42.6%** | 52 | 80 | 21.7% | 73/112 (65.2%) | 39 | 0.311 |
| 2022 | Follow the board | 68.0% | 15.2% | **24.8%** | 17 | 8 | – | – | – | – |
| 2023 | marie: Jev pipeline + facts | 72.2% | 52.0% | **60.5%** | 52 | 20 | 41.9% | 84/100 (84.0%) | 16 | 0.457 |
| 2023 | main: history model | 27.4% | 31.0% | **29.1%** | 31 | 82 | 26.3% | 57/100 (57.0%) | 43 | 0.264 |
| 2023 | Follow the board | 85.2% | 23.0% | **36.2%** | 23 | 4 | – | – | – | – |
| 2024 | marie: Jev pipeline + facts | 69.6% | 39.8% | **50.6%** | 39 | 17 | 41.9% | 94/98 (95.9%) | 4 | 0.539 |
| 2024 | main: history model | 47.9% | 23.5% | **31.5%** | 23 | 25 | 27.1% | 84/98 (85.7%) | 14 | 0.360 |
| 2024 | Follow the board | 52.6% | 10.2% | **17.1%** | 10 | 9 | – | – | – | – |
| 2025 | marie: Jev pipeline + facts | 76.4% | 37.5% | **50.3%** | 42 | 13 | 36.8% | 96/112 (85.7%) | 16 | 0.564 |
| 2025 | main: history model | 58.1% | 38.4% | **46.2%** | 43 | 31 | 24.7% | 86/112 (76.8%) | 26 | 0.446 |
| 2025 | Follow the board | 76.5% | 11.6% | **20.2%** | 13 | 4 | – | – | – | – |
| 2026 | marie: Jev pipeline + facts | 64.2% | 51.5% | **57.1%** | 34 | 19 | 41.1% | 63/66 (95.5%) | 3 | 0.539 |
| 2026 | main: history model | 56.4% | 33.3% | **41.9%** | 22 | 17 | 25.1% | 45/66 (68.2%) | 21 | 0.425 |
| 2026 | main: full system (2026 only) | 62.5% | 45.5% | **52.6%** | 30 | 18 | 27.4% | 55/66 (83.3%) | 11 | 0.426 |
| 2026 | Follow the board | 57.1% | 12.1% | **20.0%** | 8 | 6 | – | – | – | – |

## Year by year, target: against the board

| Year | System | Precision | Recall | F1 | Hits | False alarms | Review | Reaching a person | Never seen | Avg precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022 | marie: Jev pipeline + facts | 53.2% | 28.2% | **36.9%** | 33 | 29 | 36.0% | 86/117 (73.5%) | 31 | 0.321 |
| 2022 | main: history model | 44.7% | 50.4% | **47.4%** | 59 | 73 | 21.7% | 78/117 (66.7%) | 39 | 0.407 |
| 2022 | Follow the board | 32.0% | 6.8% | **11.3%** | 8 | 17 | – | – | – | – |
| 2023 | marie: Jev pipeline + facts | 43.1% | 37.3% | **40.0%** | 31 | 41 | 41.9% | 65/83 (78.3%) | 18 | 0.340 |
| 2023 | main: history model | 29.2% | 39.8% | **33.7%** | 33 | 80 | 26.3% | 55/83 (66.3%) | 28 | 0.319 |
| 2023 | Follow the board | 14.8% | 4.8% | **7.3%** | 4 | 23 | – | – | – | – |
| 2024 | marie: Jev pipeline + facts | 64.3% | 36.7% | **46.8%** | 36 | 20 | 41.9% | 93/98 (94.9%) | 5 | 0.439 |
| 2024 | main: history model | 56.2% | 27.6% | **37.0%** | 27 | 21 | 27.1% | 85/98 (86.7%) | 13 | 0.438 |
| 2024 | Follow the board | 47.4% | 9.2% | **15.4%** | 9 | 10 | – | – | – | – |
| 2025 | marie: Jev pipeline + facts | 61.8% | 33.0% | **43.0%** | 34 | 21 | 36.8% | 87/103 (84.5%) | 16 | 0.425 |
| 2025 | main: history model | 56.8% | 40.8% | **47.5%** | 42 | 32 | 24.7% | 78/103 (75.7%) | 25 | 0.467 |
| 2025 | Follow the board | 23.5% | 3.9% | **6.7%** | 4 | 13 | – | – | – | – |
| 2026 | marie: Jev pipeline + facts | 56.6% | 45.5% | **50.4%** | 30 | 23 | 41.1% | 63/66 (95.5%) | 3 | 0.441 |
| 2026 | main: history model | 61.5% | 36.4% | **45.7%** | 24 | 15 | 25.1% | 48/66 (72.7%) | 18 | 0.453 |
| 2026 | main: full system (2026 only) | 52.1% | 37.9% | **43.9%** | 25 | 23 | 27.4% | 52/66 (78.8%) | 14 | 0.454 |
| 2026 | Follow the board | 42.9% | 9.1% | **15.0%** | 6 | 8 | – | – | – | – |

## Same review effort

Each system's ranking picks the same number of proposals for a person. Cells: MOT votes caught · against-the-board votes caught.

| Year | Reviewed | marie | main |
|---|---:|---:|---:|
| 2022 | 10.0% | 66/112 · 62/117 | 53/112 · 62/117 |
| 2022 | 25.0% | 85/112 · 80/117 | 73/112 · 78/117 |
| 2022 | 40.0% | 95/112 · 92/117 | 89/112 · 96/117 |
| 2023 | 10.0% | 58/100 · 37/83 | 38/100 · 40/83 |
| 2023 | 25.0% | 73/100 · 54/83 | 57/100 · 55/83 |
| 2023 | 40.0% | 84/100 · 65/83 | 59/100 · 57/83 |
| 2024 | 10.0% | 57/98 · 55/98 | 55/98 · 60/98 |
| 2024 | 25.0% | 81/98 · 80/98 | 81/98 · 82/98 |
| 2024 | 40.0% | 91/98 · 90/98 | 91/98 · 92/98 |
| 2025 | 10.0% | 71/112 · 60/103 | 60/112 · 57/103 |
| 2025 | 25.0% | 92/112 · 83/103 | 86/112 · 78/103 |
| 2025 | 40.0% | 98/112 · 89/103 | 95/112 · 86/103 |
| 2026 | 10.0% | 44/66 · 40/66 | 36/66 · 38/66 |
| 2026 | 25.0% | 55/66 · 54/66 | 45/66 · 48/66 |
| 2026 | 40.0% | 60/66 · 60/66 | 61/66 · 63/66 |

## What to keep in mind

- main's per-year numbers are its **history model** only. Its full system (director and board rules, a low-information gate, abstentions, AI proxy reading) is only saved for 2026. main's pay model scores a different file.
- marie reuses main's AI proxy facts for US directors and main's CEO pay figures.
- How marie's years were used while designing: 2021 run once, after the design was fixed; 2022 run once, after the design was fixed; 2023 run once, after the design was fixed; 2024 used to check the design; 2025 used to design the system; 2026 holdout, seen before the design was final.
- With 60-110 positives a year, differences of a few votes are noise.
