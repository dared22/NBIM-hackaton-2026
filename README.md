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
python3 src/run.py                        # about three minutes
python3 -m unittest discover -s tests     # 32 checks, including leakage audits and two end-to-end attack checks
```

`src/run.py` writes `data/outputs/decisions_2026.csv` (suggested vote,
probability, band, who decides, reasons, guideline with its own words and page
number, evidence link) and
`data/outputs/results.md` (the full output of every script below).

The two models are scored on two different files, so their counts do not add up
to one total.

| Script | What it shows | Result on 2026 |
|---|---|---|
| `src/benchmark/model.py` | File A, `real_votes.csv`: all proposal types, 37 countries, 1,539 proposals, 66 against the board. Vote history only | 24 hits and 14 false alarms at 38 flags; "same as last time" has 22 and 16 |
| `src/agent/pay_model.py` | File B, Norges Bank's N-PX filings: 1,200 US pay votes, 114 against the board. History plus company facts read from each meeting's proxy | 72 hits and 25 false alarms at 97 flags; "same as last season" has 42 and 55 |
| `src/agent/director_rules.py` | US director elections in file A, 2019-2026: 1,742 nominees, 93 against. NBIM's written rules (chair who is also CEO; more than five boards) applied to SEC role data. No training, no AI model | 38 hits and 12 false alarms at 50 flags; "same as last time" has 36 and 37 at 73 flags. From 2019 to 2024 NBIM opposed 28 of 28 chair-and-CEO nominees; in 2026, 0 of 5 |
| `src/agent/proposal_rules.py` | All proposals in file A, 2019-2026, whose title falls under an NBIM rule that can be read from the title ("other business", declassify the board, written consent, simple majority, proxy access, independent chair, poison pill). No training, no AI model | NBIM voted as its rule says on 73 of 73. The rule means "against the board" on 66, all 66 were, and 21 of them are first-time items "same as last time" cannot flag |
| `src/agent/position_papers_test.py` | NBIM's twelve position papers (`data/policy/position_papers.json`): do they add anything to the tool? | Citations yes: the tool names the same paper as NBIM on 28 of 31 director rule hits. Prediction no: given the papers, the decision model goes from 6 to 71 false alarms |
| `src/agent/history_model.py` | Experiment on file A: does what the ballot reveals (director order, board size, labels) help? | No change on test years 2022-2025; not adopted |
| `src/agent/data_audit.py` | Every column of all three vote files | Report in `data/outputs/data_audit.md` |
| `src/agent/rule_check.py` | Decision model checks guideline sections against the proposal wording | Finds nothing the history model does not |
| `src/agent/routing.py` | Is the confidence honest, what does a lower "ask a person" level cost, and when does NBIM abstain | Below 5% the tool is wrong about 2% of the time and nothing in the vote file picks those out; abstaining is a market habit the tool now follows |
| `src/agent/robustness.py` | Instructions hidden in the proposal text, with and without a guardrail | Both models can be thrown off; the guardrail flags every instruction attack with no false alarms on 66,663 real texts |

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
