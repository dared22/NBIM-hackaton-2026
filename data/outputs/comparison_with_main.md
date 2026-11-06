# Comparison: marie's Jev pipeline and main's system

Produced by `python src/report_results.py --main-dir <checkout of main>`. Full numbers in `comparison_with_main.csv`.

## How the comparison is made fair

- **Same proposals.** Every year, both systems are scored on exactly the proposals both can score (`data/dirty/real_votes.csv`, rows with a board recommendation and an NBIM vote).
- **Same information.** main's history model freezes its history at the start of each test year; marie uses votes from earlier dates in the same year. main's model is therefore also run here **with live history**, the same information marie has. main's own setting is kept as a second row. Both are main's code, run in this process (its committed 2026 file is reproduced to within 1.7e-16).
- **Same review effort.** The systems send different shares of proposals to a person (marie about 40%, main about 25%), so their F1 and "reaching a person" are not comparable as run. The headline uses measures that do not depend on that: average precision, MOT votes caught when each system's ranking picks the same share of proposals, and precision when each flags as many proposals as there are MOT votes (R-precision).
- **Both targets.** marie is trained to predict NBIM voted MOT; main to predict a vote against the board. They differ on shareholder proposals and abstentions, so every number is shown for both. For the against-the-board target, marie's recommendation counts when it departs from the board, and her score is turned around where the board recommends MOT (as main's combined model does with her scores).
- **Tuning.** marie's design was chosen while looking at 2024-2026 (2026 was run six times). main's history model has a setting (CLIP) chosen on test years 2022-2025, and its full system was built while 2026 was known. The headline therefore averages 2022-2025 and shows 2026 on its own.
- **What is being compared.** marie's row is the whole pipeline: an LLM (Jev), company facts from filings, and a triage model. main's history model uses NBIM's vote history only. marie without Jev (`--no-jev`: triage model, director rules, code citations) and marie's triage model alone are shown too; the latter is the like-for-like machine-learning comparison. main's combined model, where present, adds Jev and marie's triage model to main's own signals and is fitted to predict a vote against the board. It is run three ways: with the scores main committed (exported from this branch at commit a7d971a), with the scores exported from this branch now, and with this branch's final recommendation (board-MOT rule, director rules, AVSTÅ) in place of Jev's raw vote. main's full system (rules, AI proxy reading) is only saved for 2026.

## Headline: average over 2022-2025, equal review effort

| Target | System | Avg precision | Caught, top 10% reviewed | Caught, top 25% reviewed | Caught, top 40% reviewed | R-precision |
|---|---:|---:|---:|---:|---:|---:|
| NBIM voted MOT | marie: Jev pipeline + facts | **0.476** | 59.6% | 78.4% | 87.3% | 48.1% |
| NBIM voted MOT | marie: pipeline without Jev | **0.444** | 56.8% | 77.9% | 84.9% | 46.6% |
| NBIM voted MOT | marie: triage model only (no Jev) | **0.458** | 57.7% | 77.7% | 85.2% | 48.9% |
| NBIM voted MOT | main: history model, as committed | **0.345** | 48.8% | 70.4% | 79.0% | 39.6% |
| NBIM voted MOT | main: history model, live history | **0.348** | 49.7% | 70.3% | 79.8% | 39.4% |
| NBIM voted MOT | main: combined model, marie as committed on main (a7d971a) | **0.445** | 57.6% | 78.2% | 87.6% | 47.3% |
| NBIM voted MOT | main: combined model, current marie | **0.444** | 56.6% | 77.2% | 87.4% | 47.0% |
| NBIM voted MOT | main: combined model, marie's final vote | **0.446** | 56.0% | 78.7% | 87.6% | 46.8% |
| against the board | marie: Jev pipeline + facts | **0.423** | 54.5% | 75.0% | 84.0% | 45.8% |
| against the board | marie: pipeline without Jev | **0.371** | 55.4% | 74.2% | 81.7% | 44.8% |
| against the board | marie: triage model only (no Jev) | **0.402** | 53.8% | 73.8% | 82.2% | 43.0% |
| against the board | main: history model, as committed | **0.408** | 54.4% | 73.1% | 82.0% | 44.0% |
| against the board | main: history model, live history | **0.414** | 55.4% | 73.2% | 82.7% | 44.2% |
| against the board | main: combined model, marie as committed on main (a7d971a) | **0.484** | 60.0% | 75.9% | 85.8% | 48.2% |
| against the board | main: combined model, current marie | **0.484** | 59.1% | 75.7% | 85.5% | 48.5% |
| against the board | main: combined model, marie's final vote | **0.485** | 58.4% | 76.2% | 85.8% | 48.4% |

Differences with 95% intervals (bootstrap over meetings, 2022-2025, years averaged). An interval that contains 0 means the systems cannot be told apart on these years.

| Target | Comparison | Measure | Difference | 95% interval |
|---|---:|---:|---:|---:|
| NBIM voted MOT | marie minus combined model, marie as committed on main (a7d971a) | Avg precision | +0.031 | -0.014 to +0.088 |
| NBIM voted MOT | marie minus combined model, marie as committed on main (a7d971a) | Caught, top 25% | +0.2 pts | -4.4 pts to +7.5 pts |
| NBIM voted MOT | marie minus combined model, current marie | Avg precision | +0.032 | -0.015 to +0.090 |
| NBIM voted MOT | marie minus combined model, current marie | Caught, top 25% | +1.2 pts | -4.2 pts to +7.8 pts |
| NBIM voted MOT | marie minus combined model, marie's final vote | Avg precision | +0.030 | -0.015 to +0.085 |
| NBIM voted MOT | marie minus combined model, marie's final vote | Caught, top 25% | -0.3 pts | -5.0 pts to +6.3 pts |
| NBIM voted MOT | marie minus history model, live history | Avg precision | +0.128 | +0.070 to +0.195 |
| NBIM voted MOT | marie minus history model, live history | Caught, top 25% | +8.1 pts | +0.8 pts to +15.4 pts |
| NBIM voted MOT | marie minus history model, as committed | Avg precision | +0.131 | +0.073 to +0.197 |
| NBIM voted MOT | marie minus history model, as committed | Caught, top 25% | +8.0 pts | +1.2 pts to +16.0 pts |
| NBIM voted MOT | marie minus pipeline without Jev | Avg precision | +0.032 | +0.014 to +0.054 |
| NBIM voted MOT | marie minus pipeline without Jev | Caught, top 25% | +0.5 pts | -2.1 pts to +3.3 pts |
| NBIM voted MOT | marie minus triage model only (no Jev) | Avg precision | +0.019 | -0.007 to +0.042 |
| NBIM voted MOT | marie minus triage model only (no Jev) | Caught, top 25% | +0.7 pts | -2.1 pts to +4.5 pts |
| against the board | marie minus combined model, marie as committed on main (a7d971a) | Avg precision | -0.061 | -0.093 to -0.022 |
| against the board | marie minus combined model, marie as committed on main (a7d971a) | Caught, top 25% | -0.9 pts | -6.3 pts to +4.0 pts |
| against the board | marie minus combined model, current marie | Avg precision | -0.061 | -0.091 to -0.022 |
| against the board | marie minus combined model, current marie | Caught, top 25% | -0.7 pts | -6.3 pts to +3.7 pts |
| against the board | marie minus combined model, marie's final vote | Avg precision | -0.062 | -0.090 to -0.023 |
| against the board | marie minus combined model, marie's final vote | Caught, top 25% | -1.2 pts | -6.6 pts to +3.3 pts |
| against the board | marie minus history model, live history | Avg precision | +0.009 | -0.040 to +0.066 |
| against the board | marie minus history model, live history | Caught, top 25% | +1.8 pts | -5.2 pts to +7.2 pts |
| against the board | marie minus history model, as committed | Avg precision | +0.015 | -0.033 to +0.069 |
| against the board | marie minus history model, as committed | Caught, top 25% | +1.9 pts | -4.9 pts to +7.9 pts |
| against the board | marie minus pipeline without Jev | Avg precision | +0.052 | +0.020 to +0.076 |
| against the board | marie minus pipeline without Jev | Caught, top 25% | +0.8 pts | -2.5 pts to +3.4 pts |
| against the board | marie minus triage model only (no Jev) | Avg precision | +0.021 | -0.001 to +0.041 |
| against the board | marie minus triage model only (no Jev) | Caught, top 25% | +1.2 pts | -2.2 pts to +4.5 pts |

## 2026 on its own (marie tuned on it)

| Target | System | Avg precision | Caught, top 10% reviewed | Caught, top 25% reviewed | Caught, top 40% reviewed | R-precision |
|---|---:|---:|---:|---:|---:|---:|
| NBIM voted MOT | marie: Jev pipeline + facts | 0.539 | 66.7% | 83.3% | 90.9% | 54.5% |
| NBIM voted MOT | marie: pipeline without Jev | 0.553 | 68.2% | 81.8% | 86.4% | 56.1% |
| NBIM voted MOT | marie: triage model only (no Jev) | 0.569 | 68.2% | 83.3% | 83.3% | 56.1% |
| NBIM voted MOT | main: history model, as committed | 0.425 | 54.5% | 68.2% | 92.4% | 40.9% |
| NBIM voted MOT | main: history model, live history | 0.430 | 56.1% | 69.7% | 90.9% | 43.9% |
| NBIM voted MOT | main: combined model, marie as committed on main (a7d971a) | 0.421 | 68.2% | 83.3% | 93.9% | 43.9% |
| NBIM voted MOT | main: combined model, current marie | 0.421 | 66.7% | 83.3% | 93.9% | 43.9% |
| NBIM voted MOT | main: combined model, marie's final vote | 0.424 | 63.6% | 83.3% | 93.9% | 43.9% |
| NBIM voted MOT | main: full system (2026 only) | 0.427 | 68.2% | 81.8% | 93.9% | 43.9% |
| against the board | marie: Jev pipeline + facts | 0.508 | 63.6% | 81.8% | 90.9% | 53.0% |
| against the board | marie: pipeline without Jev | 0.520 | 65.2% | 81.8% | 86.4% | 53.0% |
| against the board | marie: triage model only (no Jev) | 0.514 | 66.7% | 83.3% | 83.3% | 50.0% |
| against the board | main: history model, as committed | 0.453 | 57.6% | 72.7% | 95.5% | 43.9% |
| against the board | main: history model, live history | 0.458 | 59.1% | 74.2% | 93.9% | 47.0% |
| against the board | main: combined model, marie as committed on main (a7d971a) | 0.498 | 68.2% | 84.8% | 93.9% | 48.5% |
| against the board | main: combined model, current marie | 0.498 | 66.7% | 84.8% | 93.9% | 48.5% |
| against the board | main: combined model, marie's final vote | 0.503 | 66.7% | 84.8% | 93.9% | 48.5% |
| against the board | main: full system (2026 only) | 0.505 | 68.2% | 83.3% | 93.9% | 48.5% |

## Each year, ranking measures

| Target | Year | System | Positives | Avg precision | Top 10% | Top 25% | Top 40% | R-precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NBIM voted MOT | 2022 | marie: Jev pipeline + facts | 112 | 0.344 | 58.9% | 75.9% | 84.8% | 45.5% |
| NBIM voted MOT | 2022 | marie: pipeline without Jev | 112 | 0.315 | 55.4% | 76.8% | 80.4% | 40.2% |
| NBIM voted MOT | 2022 | marie: triage model only (no Jev) | 112 | 0.323 | 55.4% | 78.6% | 81.2% | 43.8% |
| NBIM voted MOT | 2022 | main: history model, as committed | 112 | 0.311 | 47.3% | 65.2% | 79.5% | 42.0% |
| NBIM voted MOT | 2022 | main: history model, live history | 112 | 0.316 | 48.2% | 67.0% | 80.4% | 42.0% |
| NBIM voted MOT | 2022 | main: combined model, marie as committed on main (a7d971a) | 112 | 0.461 | 64.3% | 75.9% | 91.1% | 56.2% |
| NBIM voted MOT | 2022 | main: combined model, current marie | 112 | 0.461 | 63.4% | 75.9% | 91.1% | 57.1% |
| NBIM voted MOT | 2022 | main: combined model, marie's final vote | 112 | 0.455 | 60.7% | 75.9% | 91.1% | 53.6% |
| NBIM voted MOT | 2023 | marie: Jev pipeline + facts | 100 | 0.457 | 58.0% | 73.0% | 84.0% | 44.0% |
| NBIM voted MOT | 2023 | marie: pipeline without Jev | 100 | 0.432 | 50.0% | 72.0% | 77.0% | 44.0% |
| NBIM voted MOT | 2023 | marie: triage model only (no Jev) | 100 | 0.488 | 55.0% | 74.0% | 81.0% | 55.0% |
| NBIM voted MOT | 2023 | main: history model, as committed | 100 | 0.264 | 38.0% | 57.0% | 59.0% | 30.0% |
| NBIM voted MOT | 2023 | main: history model, live history | 100 | 0.268 | 39.0% | 56.0% | 59.0% | 30.0% |
| NBIM voted MOT | 2023 | main: combined model, marie as committed on main (a7d971a) | 100 | 0.360 | 44.0% | 71.0% | 76.0% | 34.0% |
| NBIM voted MOT | 2023 | main: combined model, current marie | 100 | 0.361 | 44.0% | 68.0% | 76.0% | 34.0% |
| NBIM voted MOT | 2023 | main: combined model, marie's final vote | 100 | 0.361 | 44.0% | 72.0% | 76.0% | 33.0% |
| NBIM voted MOT | 2024 | marie: Jev pipeline + facts | 98 | 0.539 | 58.2% | 82.7% | 92.9% | 51.0% |
| NBIM voted MOT | 2024 | marie: pipeline without Jev | 98 | 0.506 | 59.2% | 82.7% | 92.9% | 53.1% |
| NBIM voted MOT | 2024 | marie: triage model only (no Jev) | 98 | 0.488 | 56.1% | 79.6% | 91.8% | 45.9% |
| NBIM voted MOT | 2024 | main: history model, as committed | 98 | 0.360 | 56.1% | 82.7% | 92.9% | 40.8% |
| NBIM voted MOT | 2024 | main: history model, live history | 98 | 0.364 | 57.1% | 81.6% | 94.9% | 40.8% |
| NBIM voted MOT | 2024 | main: combined model, marie as committed on main (a7d971a) | 98 | 0.454 | 61.2% | 84.7% | 95.9% | 48.0% |
| NBIM voted MOT | 2024 | main: combined model, current marie | 98 | 0.451 | 60.2% | 83.7% | 94.9% | 45.9% |
| NBIM voted MOT | 2024 | main: combined model, marie's final vote | 98 | 0.463 | 60.2% | 85.7% | 95.9% | 49.0% |
| NBIM voted MOT | 2025 | marie: Jev pipeline + facts | 112 | 0.564 | 63.4% | 82.1% | 87.5% | 51.8% |
| NBIM voted MOT | 2025 | marie: pipeline without Jev | 112 | 0.522 | 62.5% | 80.4% | 89.3% | 49.1% |
| NBIM voted MOT | 2025 | marie: triage model only (no Jev) | 112 | 0.531 | 64.3% | 78.6% | 86.6% | 50.9% |
| NBIM voted MOT | 2025 | main: history model, as committed | 112 | 0.446 | 53.6% | 76.8% | 84.8% | 45.5% |
| NBIM voted MOT | 2025 | main: history model, live history | 112 | 0.445 | 54.5% | 76.8% | 84.8% | 44.6% |
| NBIM voted MOT | 2025 | main: combined model, marie as committed on main (a7d971a) | 112 | 0.507 | 60.7% | 81.2% | 87.5% | 50.9% |
| NBIM voted MOT | 2025 | main: combined model, current marie | 112 | 0.503 | 58.9% | 81.2% | 87.5% | 50.9% |
| NBIM voted MOT | 2025 | main: combined model, marie's final vote | 112 | 0.507 | 58.9% | 81.2% | 87.5% | 51.8% |
| NBIM voted MOT | 2026 | marie: Jev pipeline + facts | 66 | 0.539 | 66.7% | 83.3% | 90.9% | 54.5% |
| NBIM voted MOT | 2026 | marie: pipeline without Jev | 66 | 0.553 | 68.2% | 81.8% | 86.4% | 56.1% |
| NBIM voted MOT | 2026 | marie: triage model only (no Jev) | 66 | 0.569 | 68.2% | 83.3% | 83.3% | 56.1% |
| NBIM voted MOT | 2026 | main: history model, as committed | 66 | 0.425 | 54.5% | 68.2% | 92.4% | 40.9% |
| NBIM voted MOT | 2026 | main: history model, live history | 66 | 0.430 | 56.1% | 69.7% | 90.9% | 43.9% |
| NBIM voted MOT | 2026 | main: combined model, marie as committed on main (a7d971a) | 66 | 0.421 | 68.2% | 83.3% | 93.9% | 43.9% |
| NBIM voted MOT | 2026 | main: combined model, current marie | 66 | 0.421 | 66.7% | 83.3% | 93.9% | 43.9% |
| NBIM voted MOT | 2026 | main: combined model, marie's final vote | 66 | 0.424 | 63.6% | 83.3% | 93.9% | 43.9% |
| NBIM voted MOT | 2026 | main: full system (2026 only) | 66 | 0.427 | 68.2% | 81.8% | 93.9% | 43.9% |
| against the board | 2022 | marie: Jev pipeline + facts | 117 | 0.309 | 53.8% | 72.6% | 79.5% | 43.6% |
| against the board | 2022 | marie: pipeline without Jev | 117 | 0.298 | 57.3% | 72.6% | 76.9% | 42.7% |
| against the board | 2022 | marie: triage model only (no Jev) | 117 | 0.298 | 56.4% | 73.5% | 77.8% | 42.7% |
| against the board | 2022 | main: history model, as committed | 117 | 0.407 | 53.0% | 66.7% | 82.1% | 46.2% |
| against the board | 2022 | main: history model, live history | 117 | 0.416 | 53.8% | 69.2% | 82.9% | 47.0% |
| against the board | 2022 | main: combined model, marie as committed on main (a7d971a) | 117 | 0.428 | 56.4% | 70.9% | 89.7% | 47.0% |
| against the board | 2022 | main: combined model, current marie | 117 | 0.427 | 54.7% | 70.9% | 89.7% | 47.9% |
| against the board | 2022 | main: combined model, marie's final vote | 117 | 0.421 | 52.1% | 70.9% | 89.7% | 46.2% |
| against the board | 2023 | marie: Jev pipeline + facts | 83 | 0.365 | 47.0% | 65.1% | 78.3% | 42.2% |
| against the board | 2023 | marie: pipeline without Jev | 83 | 0.261 | 47.0% | 63.9% | 69.9% | 41.0% |
| against the board | 2023 | marie: triage model only (no Jev) | 83 | 0.379 | 43.4% | 66.3% | 74.7% | 38.6% |
| against the board | 2023 | main: history model, as committed | 83 | 0.319 | 48.2% | 66.3% | 68.7% | 36.1% |
| against the board | 2023 | main: history model, live history | 83 | 0.326 | 49.4% | 65.1% | 68.7% | 37.3% |
| against the board | 2023 | main: combined model, marie as committed on main (a7d971a) | 83 | 0.428 | 54.2% | 67.5% | 71.1% | 43.4% |
| against the board | 2023 | main: combined model, current marie | 83 | 0.432 | 54.2% | 67.5% | 71.1% | 44.6% |
| against the board | 2023 | main: combined model, marie's final vote | 83 | 0.422 | 54.2% | 67.5% | 71.1% | 41.0% |
| against the board | 2024 | marie: Jev pipeline + facts | 98 | 0.523 | 57.1% | 81.6% | 91.8% | 50.0% |
| against the board | 2024 | marie: pipeline without Jev | 98 | 0.490 | 58.2% | 81.6% | 91.8% | 51.0% |
| against the board | 2024 | marie: triage model only (no Jev) | 98 | 0.473 | 54.1% | 78.6% | 90.8% | 45.9% |
| against the board | 2024 | main: history model, as committed | 98 | 0.438 | 61.2% | 83.7% | 93.9% | 46.9% |
| against the board | 2024 | main: history model, live history | 98 | 0.449 | 62.2% | 82.7% | 95.9% | 46.9% |
| against the board | 2024 | main: combined model, marie as committed on main (a7d971a) | 98 | 0.543 | 66.3% | 84.7% | 95.9% | 52.0% |
| against the board | 2024 | main: combined model, current marie | 98 | 0.540 | 65.3% | 83.7% | 94.9% | 51.0% |
| against the board | 2024 | main: combined model, marie's final vote | 98 | 0.559 | 65.3% | 85.7% | 95.9% | 54.1% |
| against the board | 2025 | marie: Jev pipeline + facts | 103 | 0.495 | 60.2% | 80.6% | 86.4% | 47.6% |
| against the board | 2025 | marie: pipeline without Jev | 103 | 0.433 | 59.2% | 78.6% | 88.3% | 44.7% |
| against the board | 2025 | marie: triage model only (no Jev) | 103 | 0.457 | 61.2% | 76.7% | 85.4% | 44.7% |
| against the board | 2025 | main: history model, as committed | 103 | 0.467 | 55.3% | 75.7% | 83.5% | 46.6% |
| against the board | 2025 | main: history model, live history | 103 | 0.466 | 56.3% | 75.7% | 83.5% | 45.6% |
| against the board | 2025 | main: combined model, marie as committed on main (a7d971a) | 103 | 0.539 | 63.1% | 80.6% | 86.4% | 50.5% |
| against the board | 2025 | main: combined model, current marie | 103 | 0.536 | 62.1% | 80.6% | 86.4% | 50.5% |
| against the board | 2025 | main: combined model, marie's final vote | 103 | 0.536 | 62.1% | 80.6% | 86.4% | 52.4% |
| against the board | 2026 | marie: Jev pipeline + facts | 66 | 0.508 | 63.6% | 81.8% | 90.9% | 53.0% |
| against the board | 2026 | marie: pipeline without Jev | 66 | 0.520 | 65.2% | 81.8% | 86.4% | 53.0% |
| against the board | 2026 | marie: triage model only (no Jev) | 66 | 0.514 | 66.7% | 83.3% | 83.3% | 50.0% |
| against the board | 2026 | main: history model, as committed | 66 | 0.453 | 57.6% | 72.7% | 95.5% | 43.9% |
| against the board | 2026 | main: history model, live history | 66 | 0.458 | 59.1% | 74.2% | 93.9% | 47.0% |
| against the board | 2026 | main: combined model, marie as committed on main (a7d971a) | 66 | 0.498 | 68.2% | 84.8% | 93.9% | 48.5% |
| against the board | 2026 | main: combined model, current marie | 66 | 0.498 | 66.7% | 84.8% | 93.9% | 48.5% |
| against the board | 2026 | main: combined model, marie's final vote | 66 | 0.503 | 66.7% | 84.8% | 93.9% | 48.5% |
| against the board | 2026 | main: full system (2026 only) | 66 | 0.505 | 68.2% | 83.3% | 93.9% | 48.5% |

## Each system as it runs (own thresholds and review share, not directly comparable)

Recommended MOT: marie's recommendation; main's "likely AGAINST board" band (full system: suggested MOT or AVSTÅ). Review: share of proposals a person sees, including every recommended MOT.

| Target | Year | System | Precision | Recall | F1 | Hits | False alarms | Review | Reaching a person |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NBIM voted MOT | 2022 | marie: Jev pipeline + facts | 56.1% | 41.1% | 47.4% | 46 | 36 | 37.1% | 99/112 |
| NBIM voted MOT | 2022 | marie: pipeline without Jev | 46.8% | 33.0% | 38.7% | 37 | 42 | 42.6% | 98/112 |
| NBIM voted MOT | 2022 | main: history model, as committed | 39.4% | 46.4% | 42.6% | 52 | 80 | 21.7% | 73/112 |
| NBIM voted MOT | 2022 | main: history model, live history | 42.1% | 45.5% | 43.8% | 51 | 70 | 21.3% | 72/112 |
| NBIM voted MOT | 2022 | main: combined model, marie as committed on main (a7d971a) | 53.2% | 59.8% | 56.3% | 67 | 59 | 22.9% | 85/112 |
| NBIM voted MOT | 2022 | main: combined model, current marie | 51.1% | 60.7% | 55.5% | 68 | 65 | 23.5% | 85/112 |
| NBIM voted MOT | 2022 | main: combined model, marie's final vote | 51.2% | 58.0% | 54.4% | 65 | 62 | 23.1% | 85/112 |
| NBIM voted MOT | 2022 | Follow the board | 68.0% | 15.2% | 24.8% | 17 | 8 | – | – |
| NBIM voted MOT | 2023 | marie: Jev pipeline + facts | 71.2% | 52.0% | 60.1% | 52 | 21 | 42.4% | 84/100 |
| NBIM voted MOT | 2023 | marie: pipeline without Jev | 56.1% | 55.0% | 55.6% | 55 | 43 | 43.1% | 77/100 |
| NBIM voted MOT | 2023 | main: history model, as committed | 27.4% | 31.0% | 29.1% | 31 | 82 | 26.3% | 57/100 |
| NBIM voted MOT | 2023 | main: history model, live history | 30.5% | 29.0% | 29.7% | 29 | 66 | 26.0% | 57/100 |
| NBIM voted MOT | 2023 | main: combined model, marie as committed on main (a7d971a) | 46.6% | 34.0% | 39.3% | 34 | 39 | 29.6% | 73/100 |
| NBIM voted MOT | 2023 | main: combined model, current marie | 48.5% | 33.0% | 39.3% | 33 | 35 | 29.8% | 72/100 |
| NBIM voted MOT | 2023 | main: combined model, marie's final vote | 30.2% | 35.0% | 32.4% | 35 | 81 | 30.0% | 74/100 |
| NBIM voted MOT | 2023 | Follow the board | 85.2% | 23.0% | 36.2% | 23 | 4 | – | – |
| NBIM voted MOT | 2024 | marie: Jev pipeline + facts | 70.7% | 41.8% | 52.6% | 41 | 17 | 42.0% | 94/98 |
| NBIM voted MOT | 2024 | marie: pipeline without Jev | 58.9% | 43.9% | 50.3% | 43 | 30 | 55.7% | 97/98 |
| NBIM voted MOT | 2024 | main: history model, as committed | 47.9% | 23.5% | 31.5% | 23 | 25 | 27.1% | 84/98 |
| NBIM voted MOT | 2024 | main: history model, live history | 47.9% | 23.5% | 31.5% | 23 | 25 | 27.5% | 83/98 |
| NBIM voted MOT | 2024 | main: combined model, marie as committed on main (a7d971a) | 53.0% | 35.7% | 42.7% | 35 | 31 | 25.3% | 84/98 |
| NBIM voted MOT | 2024 | main: combined model, current marie | 53.0% | 35.7% | 42.7% | 35 | 31 | 25.4% | 83/98 |
| NBIM voted MOT | 2024 | main: combined model, marie's final vote | 49.4% | 42.9% | 45.9% | 42 | 43 | 25.2% | 85/98 |
| NBIM voted MOT | 2024 | Follow the board | 52.6% | 10.2% | 17.1% | 10 | 9 | – | – |
| NBIM voted MOT | 2025 | marie: Jev pipeline + facts | 76.8% | 38.4% | 51.2% | 43 | 13 | 37.1% | 97/112 |
| NBIM voted MOT | 2025 | marie: pipeline without Jev | 72.6% | 40.2% | 51.7% | 45 | 17 | 40.5% | 100/112 |
| NBIM voted MOT | 2025 | main: history model, as committed | 58.1% | 38.4% | 46.2% | 43 | 31 | 24.7% | 86/112 |
| NBIM voted MOT | 2025 | main: history model, live history | 58.1% | 38.4% | 46.2% | 43 | 31 | 24.3% | 86/112 |
| NBIM voted MOT | 2025 | main: combined model, marie as committed on main (a7d971a) | 58.8% | 44.6% | 50.8% | 50 | 35 | 20.2% | 88/112 |
| NBIM voted MOT | 2025 | main: combined model, current marie | 58.4% | 46.4% | 51.7% | 52 | 37 | 20.1% | 88/112 |
| NBIM voted MOT | 2025 | main: combined model, marie's final vote | 57.8% | 46.4% | 51.5% | 52 | 38 | 19.7% | 88/112 |
| NBIM voted MOT | 2025 | Follow the board | 76.5% | 11.6% | 20.2% | 13 | 4 | – | – |
| NBIM voted MOT | 2026 | marie: Jev pipeline + facts | 64.8% | 53.0% | 58.3% | 35 | 19 | 41.1% | 63/66 |
| NBIM voted MOT | 2026 | marie: pipeline without Jev | 52.8% | 57.6% | 55.1% | 38 | 34 | 49.1% | 63/66 |
| NBIM voted MOT | 2026 | main: history model, as committed | 56.4% | 33.3% | 41.9% | 22 | 17 | 25.1% | 45/66 |
| NBIM voted MOT | 2026 | main: history model, live history | 55.0% | 33.3% | 41.5% | 22 | 18 | 25.4% | 47/66 |
| NBIM voted MOT | 2026 | main: combined model, marie as committed on main (a7d971a) | 43.3% | 43.9% | 43.6% | 29 | 38 | 28.1% | 55/66 |
| NBIM voted MOT | 2026 | main: combined model, current marie | 45.9% | 42.4% | 44.1% | 28 | 33 | 28.1% | 55/66 |
| NBIM voted MOT | 2026 | main: combined model, marie's final vote | 34.9% | 45.5% | 39.5% | 30 | 56 | 27.9% | 55/66 |
| NBIM voted MOT | 2026 | main: full system (2026 only) | 50.7% | 56.1% | 53.2% | 37 | 36 | 29.2% | 56/66 |
| NBIM voted MOT | 2026 | Follow the board | 57.1% | 12.1% | 20.0% | 8 | 6 | – | – |
| against the board | 2022 | marie: Jev pipeline + facts | 51.4% | 30.8% | 38.5% | 36 | 34 | 37.1% | 92/117 |
| against the board | 2022 | marie: pipeline without Jev | 43.3% | 38.5% | 40.7% | 45 | 59 | 42.6% | 92/117 |
| against the board | 2022 | main: history model, as committed | 44.7% | 50.4% | 47.4% | 59 | 73 | 21.7% | 78/117 |
| against the board | 2022 | main: history model, live history | 46.3% | 47.9% | 47.1% | 56 | 65 | 21.3% | 78/117 |
| against the board | 2022 | main: combined model, marie as committed on main (a7d971a) | 47.6% | 51.3% | 49.4% | 60 | 66 | 22.9% | 83/117 |
| against the board | 2022 | main: combined model, current marie | 45.1% | 51.3% | 48.0% | 60 | 73 | 23.5% | 83/117 |
| against the board | 2022 | main: combined model, marie's final vote | 44.9% | 48.7% | 46.7% | 57 | 70 | 23.1% | 83/117 |
| against the board | 2022 | Follow the board | 32.0% | 6.8% | 11.3% | 8 | 17 | – | – |
| against the board | 2023 | marie: Jev pipeline + facts | 55.4% | 37.3% | 44.6% | 31 | 25 | 42.4% | 66/83 |
| against the board | 2023 | marie: pipeline without Jev | 45.2% | 39.8% | 42.3% | 33 | 40 | 43.1% | 58/83 |
| against the board | 2023 | main: history model, as committed | 29.2% | 39.8% | 33.7% | 33 | 80 | 26.3% | 55/83 |
| against the board | 2023 | main: history model, live history | 32.6% | 37.3% | 34.8% | 31 | 64 | 26.0% | 55/83 |
| against the board | 2023 | main: combined model, marie as committed on main (a7d971a) | 49.3% | 43.4% | 46.2% | 36 | 37 | 29.6% | 57/83 |
| against the board | 2023 | main: combined model, current marie | 51.5% | 42.2% | 46.4% | 35 | 33 | 29.8% | 57/83 |
| against the board | 2023 | main: combined model, marie's final vote | 32.8% | 45.8% | 38.2% | 38 | 78 | 30.0% | 58/83 |
| against the board | 2023 | Follow the board | 14.8% | 4.8% | 7.3% | 4 | 23 | – | – |
| against the board | 2024 | marie: Jev pipeline + facts | 73.5% | 36.7% | 49.0% | 36 | 13 | 42.0% | 94/98 |
| against the board | 2024 | marie: pipeline without Jev | 59.7% | 37.8% | 46.2% | 37 | 25 | 55.7% | 96/98 |
| against the board | 2024 | main: history model, as committed | 56.2% | 27.6% | 37.0% | 27 | 21 | 27.1% | 85/98 |
| against the board | 2024 | main: history model, live history | 56.2% | 27.6% | 37.0% | 27 | 21 | 27.5% | 84/98 |
| against the board | 2024 | main: combined model, marie as committed on main (a7d971a) | 59.1% | 39.8% | 47.6% | 39 | 27 | 25.3% | 84/98 |
| against the board | 2024 | main: combined model, current marie | 59.1% | 39.8% | 47.6% | 39 | 27 | 25.4% | 83/98 |
| against the board | 2024 | main: combined model, marie's final vote | 55.3% | 48.0% | 51.4% | 47 | 38 | 25.2% | 85/98 |
| against the board | 2024 | Follow the board | 47.4% | 9.2% | 15.4% | 9 | 10 | – | – |
| against the board | 2025 | marie: Jev pipeline + facts | 70.0% | 34.0% | 45.8% | 35 | 15 | 37.1% | 88/103 |
| against the board | 2025 | marie: pipeline without Jev | 67.3% | 35.9% | 46.8% | 37 | 18 | 40.5% | 91/103 |
| against the board | 2025 | main: history model, as committed | 56.8% | 40.8% | 47.5% | 42 | 32 | 24.7% | 78/103 |
| against the board | 2025 | main: history model, live history | 56.8% | 40.8% | 47.5% | 42 | 32 | 24.3% | 78/103 |
| against the board | 2025 | main: combined model, marie as committed on main (a7d971a) | 56.5% | 46.6% | 51.1% | 48 | 37 | 20.2% | 80/103 |
| against the board | 2025 | main: combined model, current marie | 56.2% | 48.5% | 52.1% | 50 | 39 | 20.1% | 80/103 |
| against the board | 2025 | main: combined model, marie's final vote | 55.6% | 48.5% | 51.8% | 50 | 40 | 19.7% | 80/103 |
| against the board | 2025 | Follow the board | 23.5% | 3.9% | 6.7% | 4 | 13 | – | – |
| against the board | 2026 | marie: Jev pipeline + facts | 63.8% | 45.5% | 53.1% | 30 | 17 | 41.1% | 63/66 |
| against the board | 2026 | marie: pipeline without Jev | 51.6% | 48.5% | 50.0% | 32 | 30 | 49.1% | 63/66 |
| against the board | 2026 | main: history model, as committed | 61.5% | 36.4% | 45.7% | 24 | 15 | 25.1% | 48/66 |
| against the board | 2026 | main: history model, live history | 60.0% | 36.4% | 45.3% | 24 | 16 | 25.4% | 50/66 |
| against the board | 2026 | main: combined model, marie as committed on main (a7d971a) | 47.8% | 48.5% | 48.1% | 32 | 35 | 28.1% | 56/66 |
| against the board | 2026 | main: combined model, current marie | 50.8% | 47.0% | 48.8% | 31 | 30 | 28.1% | 56/66 |
| against the board | 2026 | main: combined model, marie's final vote | 38.4% | 50.0% | 43.4% | 33 | 53 | 27.9% | 56/66 |
| against the board | 2026 | main: full system (2026 only) | 43.8% | 48.5% | 46.0% | 32 | 41 | 29.2% | 53/66 |
| against the board | 2026 | Follow the board | 42.9% | 9.1% | 15.0% | 6 | 8 | – | – |

## What to keep in mind

- marie reuses main's AI proxy facts for US directors and main's CEO pay figures, so part of marie's company-fact signal is main's work.
- How marie's years were used while designing: 2021 run once, after the design was fixed; 2022 run once, after the design was fixed; 2023 run once, after the design was fixed; 2024 used to check the design; 2025 used to design the system; 2026 holdout, run six times (v2-v7) while the design changed.
- With 60-110 positives a year, differences of a few votes are noise; use the intervals above.
