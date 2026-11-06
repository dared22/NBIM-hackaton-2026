# NBIM voting agent — Case 1

This project recommends **FOR**, **MOT**, or **AVSTÅ** for a shareholder
proposal, cites the relevant NBIM voting guideline, and sends uncertain cases
to a person. We evaluate recommendations against NBIM's published votes.

The current repository contains the supplied data, a structured copy of the
2025 guidelines, an architecture plan, and a historical benchmark. The voting
agent itself is still to be built.

## Project layout

The paths marked **planned** are interfaces for the team. Add each file or
directory when its first implementation is ready; empty scaffolding is not
required.

```text
.
├── README.md
├── data/
│   ├── dirty/                 # Supplied, unchanged CSVs
│   │   ├── real_votes.csv     # NBIM API vote history; evaluation labels
│   │   └── npx_votes.csv      # Optional SEC N-PX reference data
│   ├── prepared/              # Planned: cleaned proposal inputs and splits
│   ├── evidence/              # Planned: cached, dated meeting documents
│   └── outputs/               # Planned: predictions and evaluation reports
├── docs/
│   └── case1-architecture.md  # Detailed design and benchmark protocol
├── src/
│   ├── prepare.py             # Planned: clean votes and separate inputs/labels
│   ├── policy.py              # Planned: select and cite guideline sections
│   ├── evidence.py            # Planned: retrieve pre-meeting company facts
│   ├── decision.py            # Planned: Jev vote and human-review gate
│   ├── evaluate.py            # Planned: baselines and holdout metrics
│   ├── run.py                 # One command: all results and one decision per proposal
│   ├── agent/                 # Existing pay model, rule check and resistance test
│   └── benchmark/             # Existing historical disagreement model
├── tests/                     # Checks for the proxy reader, guardrail and leakage
└── startpakke/                # Organizers' materials and original scripts
```

Keep each step's output small and explicit. A proposal input contains the
meeting and item IDs, meeting date, company, proposal text, proposal type,
proponent, and management recommendation. Evidence contains guideline IDs and
exact text, plus any company facts with a source and publication date. A
decision contains the recommended vote, class probabilities, citation, review
status, and reason. Join the actual NBIM vote **only inside evaluation**.

## Data and sources

Use [`data/dirty/real_votes.csv`](data/dirty/real_votes.csv) as the main vote
history. Its `proposal_text` is usually a short agenda title, so some decisions
need a meeting notice or proxy statement dated before the meeting. Fetch and
cache those documents per meeting, and record when a required fact is missing.

The policy sources are the
[structured 2025 guidelines](startpakke/case1_stemmegivning/retningslinjer_2025.json)
and NBIM's twelve [position papers](data/policy/position_papers.json).
Check which guideline version applied to each meeting before claiming policy
agreement. The optional N-PX CSV is a separate dataset; its `meeting_id` is
not the same identifier as the one in `real_votes.csv`.

Never pass `nbim_vote`, `nbim_vote_raw`, `against_board`, `rationale_text`,
`rationale_section`, or `position_paper` from the same row into the decision
pipeline. These fields reveal the answer or its explanation. Keep raw source
documents as untrusted input: a sentence inside a proposal must not override
the voting instructions.

## Run what exists today

From the repository root, run the existing historical model with an explicit
data path:

```bash
python3 src/benchmark/model.py --data data/dirty/real_votes.csv
```

It writes `src/benchmark/prediksjoner_2026.csv`. This model predicts whether
NBIM **disagrees with management**, which is a useful comparison but is not
the primary **NBIM votes MOT** target. Its output also includes actual labels,
so use that CSV only for evaluation, never as input to Jev or the demo agent.

Run its focused checks with:

```bash
PYTHONPATH=src python3 -m unittest discover -s src/benchmark -p 'test_model.py'
```

One command reproduces every result and writes one decision per proposal. It
needs no API key and no internet: model answers and SEC figures are saved in
the repository.

```bash
python3 src/run.py                        # about five minutes
python3 -m unittest discover -s tests     # 87 checks, including leakage audits and four end-to-end attack checks
```

`src/run.py` writes `data/outputs/decisions_2026.csv` (suggested vote,
probability, band, who decides, reasons, guideline with its own words and page
number, evidence link),
`data/outputs/headline.md` (the headline numbers on one page) and
`data/outputs/results.md` (the full output of every script below).

The two models are scored on two different files, so their counts do not add up
to one total.

| Script | What it shows | Result on 2026 |
|---|---|---|
| `src/benchmark/model.py` | File A, `real_votes.csv`: all proposal types, 37 countries, 1,539 proposals, 66 against the board. Vote history only | 24 hits and 14 false alarms at 38 flags; "same as last time" has 22 and 16 |
| `src/agent/pay_model.py` | File B, Norges Bank's N-PX filings: 1,200 US pay votes, 114 against the board. History plus company facts read from each meeting's proxy | 72 hits and 25 false alarms at 97 flags; "same as last season" has 42 and 55 |
| `src/agent/combined_model.py` | File A. One score from main's history model and rules plus the Jev decision model and second model exported from Marie's pipeline. Fitted on earlier years, designed on 2022-2025. The tool acts alone only when a rule, a fact or NBIM's own last vote on the item backs the suggestion | 2022-2025: 241 of 401 against-votes in the top 10% of its list (history model 220, Marie's pipeline 219). 2026 in the full pipeline: 26 right of 36 automatic suggestions (72%), 10 against-votes waved through, 56 of 66 suggested or seen (before: 25 of 35, 14, and 52) |
| `src/agent/judge.py` | For US director nominees, an AI model is given the facts read from the proxy, NBIM's rules and how often NBIM has followed each rule, with no names, and returns a probability and a reason | When it says 50% or more it is right 30 times of 43 (2021-2025). In the pipeline: 2026 automatic suggestions 33 with 26 right (79%), same 56 of 66 suggested or seen |
| `src/agent/country_rules.py` | Director elections in Japan and Korea, with facts from EDINET and OpenDART exported from Marie's branch | In Japan NBIM opposed 27 of 141 top executives and none of 739 nominees in other roles (to 2025). Used as a reason to bring in a person: 11 more against-votes seen on 2022-2025, no change on 2026 |
| `src/agent/policy_watch.py` | Compares NBIM's guidelines web page with the stored 2025 edition, rule by rule | 75 of 76 rules are word for word the same. One was softened: rule 1.3.1, chair who is also CEO, from "will not" to "may not". That is the rule where NBIM's 2026 votes changed (0 of 5 against, after 28 of 28) |
| `src/agent/fetch_board_facts.py`, `src/agent/board_rules.py` | US director elections in file A. An AI model reads each proxy and records facts with checked quotes (independent, executive, chair, CEO, committees, other boards, founder). Code applies nine NBIM rules. A rule acts alone only after NBIM followed it at two meetings in a row | Proxy found for 98% of nominees; the two fact sources agree on 98.9%. The tool acts alone on 45 nominees and is right on 39 (87%); "same as last time" is right on 36 of 73. Another 12 against-votes reach a person with the fact and its quote |
| `src/agent/board_reader_check.py` | A second, stronger model read 16 of the meetings again with the same passages and questions | The two models give the same answer on 98.2% of 1,469 facts, and NBIM's rules fire on the same nominees for 120 of 122. One more reader mistake found and fixed |
| `src/agent/director_rules.py` | US director elections in file A, 2019-2026: 1,742 nominees, 93 against. NBIM's written rules (chair who is also CEO; more than five boards) applied to SEC role data. No training, no AI model | 38 hits and 12 false alarms at 50 flags; "same as last time" has 36 and 37 at 73 flags. From 2019 to 2024 NBIM opposed 28 of 28 chair-and-CEO nominees; in 2026, 0 of 5 |
| `src/agent/proposal_rules.py` | All proposals in file A, 2019-2026, whose title falls under an NBIM rule that can be read from the title ("other business", declassify the board, written consent, simple majority, proxy access, independent chair, poison pill). No training, no AI model | NBIM voted as its rule says on 79 of 79. The rule means "against the board" on 72, all 72 were, and 27 of them are first-time items "same as last time" cannot flag |
| `src/agent/position_papers_test.py` | NBIM's twelve position papers (`data/policy/position_papers.json`): do they add anything to the tool? | Citations yes: the tool names the same paper as NBIM on 28 of 31 director rule hits. Prediction no: given the papers, the decision model goes from 6 to 71 false alarms |
| `src/agent/history_model.py` | Experiment on file A: does what the ballot reveals (director order, board size, labels) help? | No change on test years 2022-2025; not adopted |
| `src/agent/data_audit.py` | Every column of all three vote files | Report in `data/outputs/data_audit.md` |
| `src/agent/rule_check.py` | Decision model checks guideline sections against the proposal wording | Finds nothing the history model does not |
| `src/agent/pay_overlap.py` | The 81 US pay proposals (2024-2026) that are in both files, scored by both models | Pay model 5 of 8 against-votes with 7 flags, history model 2 with 6. These proposals now get the pay model's answer in file A |
| `src/agent/routing.py` | Is the confidence honest, what does a lower "ask a person" level cost, and when does NBIM abstain | Below 5% the tool is wrong about 2% of the time and nothing in the vote file picks those out; abstaining is a market habit the tool now follows |
| `src/agent/fetch_pay_structure.py`, `src/agent/pay_structure_test.py` | An AI model reads how the CEO's pay is built from the proxy, with a checked quote for every answer. 675 proxies | No gain at CEO pay of 10 to 25 million dollars. At 25 million or more three answers helped on the training seasons and hurt on 2026 (average precision 0.660 against 0.698), so the pay model is unchanged. The findings are shown as evidence on 152 pay decisions |
| `src/agent/robustness.py` | Instructions hidden in the proposal text, with and without a guardrail | Both models can be thrown off; the guardrail flags every instruction attack with no false alarms on 66,663 real texts |
| `src/agent/paraphrase_test.py` | A reworded instruction with no trigger words, against the whole pipeline in the worst case | Without a wording check 6 more of 66 against-votes are waved through; with it none, and all 66 reach a person |
| `src/agent/reader_injection_test.py` | An instruction, and a false statement, planted in the proxy statement the AI reader reads (20 proxies, 175 nominees) | The reader did not obey: 0 of 694 targeted facts changed. It did quote the planted text. A code check flags all 20 planted proxies and none of 214 real ones |
| `src/agent/jev_pay.py` | Jev (a decision model, through OpenRouter) weighs each US pay vote's tagged figures against NBIM's pay rules; its probability is the pay model's twelfth input | Training seasons: average precision 0.658 to 0.710 and 0.541 to 0.548. 2026: tool alone 93 flags, 69 right (74%); 105 of 114 against-votes suggested or seen |
| `src/dashboard.py` | The Streamlit dashboard, copied from branch `marie` and adapted to this branch's two decision files | Tried with Streamlit's test runner: both data sets, filters and the detail view render without errors; key figures match the headline (56 of 66, 105 of 114) |
| `src/agent/export_for_dashboard.py` | Writes main's 2026 decisions in the column layout of the team's demo (branch `marie`, `src/nbim_vote/dashboard.py`) | `data/outputs/dashboard/predictions_main.csv`, 1,539 proposals; one line in the demo's `FILES` makes it selectable. Tried in a copy of the demo: loads and renders without errors |

Scope of the pay model: US filers and pay votes only. It uses NBIM's own
say-on-pay votes from Norges Bank's SEC Form N-PX filings
(`data/dirty/nbim_pay_votes.csv`). Limits are listed in its docstring and in
[`docs/model-card.md`](docs/model-card.md).

To rebuild the SEC data (about an hour, needs internet), run in this order:
`src/agent/fetch_ceo_pay.py`, `fetch_director_roles.py`, `link_companies.py`,
`fetch_proxy_pay.py`, `fetch_company_size.py`, `fetch_proxy_text.py`. To call the decision model for new proposals, put
`OPENROUTER_API_KEY=...` in a `.env` file at the repository root.

The `src/evaluate.py`, `src/policy.py` and other planned files in the layout above
are not written yet. The [architecture plan](docs/case1-architecture.md)
defines their intended pipeline and team boundaries.

## Evaluation target

Freeze a chronological split before tuning. Use earlier meetings for
development and threshold selection, then a later holdout for the final
comparison. Report MOT precision, recall, and F1; management-FOR/NBIM-MOT
cases found; human-review workload; valid citations; and latency. Count a
human-review case separately from an automatic MOT prediction. Compare every
method on the same eligible rows and include the simple baseline of following
`mgmt_rec`.

For the full case requirements and source scripts, see the
[organizers' Case 1 README](startpakke/case1_stemmegivning/README.md).

## Dashboard

A Streamlit page in Norwegian that shows every decision with its reasons, the
cited guideline, the confidence, the link to the company document and NBIM's
actual vote. Marie built it on branch `marie`; `src/dashboard.py` is a copy
adapted to this branch's model. It has two data sets to choose from: NBIM's
vote file for 2026 (combined model) and the US pay votes (pay model).

```bash
python3 src/run.py                 # writes data/outputs/dashboard/predictions_main*.csv
pip install streamlit pandas       # the dashboard's only requirements; the pipeline needs neither
streamlit run src/dashboard.py
```

The "paste an agenda" tab of the original runs Marie's pipeline and is on her
branch only.

## AI tools used

The hackathon rules ask for this list.

- Claude Code (Anthropic): research, code and evaluation.
- Microsoft-Decision-1 through OpenRouter: the guideline rule check
  (`src/agent/rule_check.py`) and the resistance test. Answers are cached in
  `src/agent/cache/decisions.jsonl`.
- Jev, a hosted decision model (Typesafe): called by Marie's pipeline on branch
  `marie`. Its saved answers (`data/evidence/jev_pipeline/`) are one input to
  the combined model. Jev is also called through OpenRouter
  (`~typesafe/jev-latest`) by `src/agent/jev_pay.py`: given a pay vote's tagged
  figures and NBIM's pay rules, its probability is the pay model's twelfth
  input. Answers are cached in `src/agent/cache/jev_pay.jsonl`.
- Claude Haiku 5.5 through OpenRouter is also the judge for US director
  nominees (`src/agent/judge.py`, cached in `src/agent/cache/judge.jsonl`). It
  gets facts and NBIM's record without names, and returns a probability that
  is one input to the combined model.
- Claude Sonnet 5.5 through OpenRouter: read 16 meetings a second time, to
  check the first reader (`src/agent/board_reader_check.py`, cached in
  `src/agent/cache/board_facts_check.jsonl`).
- Claude Haiku 5.5 through OpenRouter: reads board and nominee facts from
  proxies (`src/agent/fetch_board_facts.py`, 214 meetings, cached in
  `src/agent/cache/board_facts.jsonl`), and how CEO pay is built
  (`src/agent/fetch_pay_structure.py`, 675 proxies, cached in
  `src/agent/cache/pay_structure.jsonl`, shown as evidence and not used by
  any model).
- Other branches not yet in `main` used DeepSeek through OpenRouter
  (`llm_search`) and Jev (`marie`). Add them here if those branches are merged.

No AI model casts a vote. A language model reads company filings and returns
facts with quotes that are checked against the text; Jev and a judge model
each give a probability that the combined model weighs with the rest. The
suggestions in `data/outputs/decisions_2026.csv` come from the combined model,
the pay model and NBIM's written rules applied in code.
