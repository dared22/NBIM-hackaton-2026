# Scores exported from Marie's Jev pipeline

One file per year, 2021-2026, one row per proposal in `data/dirty/real_votes.csv`.
Used by `src/agent/combined_model.py`.

| Column | What it is |
|---|---|
| `jev_vote`, `jev_p_mot` | The Jev decision model's vote and its probability that NBIM votes MOT (saved run `_v7`, with company facts) |
| `jev_cited_section` | The guideline section Jev named |
| `triage_p` | Marie's second model (gradient boosting on vote history and company facts), trained on earlier years only |
| `marie_score`, `marie_flag`, `marie_review` | Her own combined score and routing, walk-forward (2022 on) |

The files hold no NBIM vote and no rationale.

How they were made: on branch `marie` at commit `a7d971a`, with numpy and scikit-learn
installed, `python src/agent/export_jev_components.py <out_dir>` (the script is in this
repo for reference; it imports her `src/report_results.py`). It reads her saved Jev answers
and makes no API calls. Jev itself is a hosted model (Typesafe), called by her
`src/jev_mvp.py`.

What Marie's notes say about how the years were used: 2021-2023 were run once after her
design was fixed, 2024 was used to check the design, 2025 to design it, and 2026 was seen
before the design was final.
