# NBIM voting agent — Case 1

This project recommends **FOR**, **MOT**, or **AVSTÅ** for a shareholder
proposal, cites the relevant NBIM voting guideline, and sends uncertain cases
to a person. We evaluate recommendations against NBIM's published votes.

The current repository contains the supplied data, a structured copy of the
2025 guidelines, an architecture plan, and a historical benchmark. The policy
and US director-evidence modules are implemented; the Jev voting and evaluation
pipeline remains to be integrated.

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
│   ├── prepared/              # Prepared proposal inputs; splits planned
│   ├── evidence/              # Cached, dated meeting documents
│   └── outputs/               # Planned: predictions and evaluation reports
├── docs/
│   └── case1-architecture.md  # Detailed design and benchmark protocol
├── src/
│   ├── prepare.py             # Planned: clean votes and separate inputs/labels
│   ├── policy.py              # Select and cite guideline sections
│   ├── evidence.py            # Retrieve pre-meeting US director facts
│   ├── decision.py            # Planned: Jev vote and human-review gate
│   ├── evaluate.py            # Planned: baselines and holdout metrics
│   ├── run.py                 # Planned: one end-to-end command
│   └── benchmark/             # Existing historical disagreement model
├── tests/                     # Focused evidence and pipeline checks
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

The policy source is the
[structured 2025 guidelines](startpakke/case1_stemmegivning/retningslinjer_2025.json).
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

The `src/run.py` and `src/evaluate.py` commands in the layout above are planned
and are not runnable yet. The [architecture plan](docs/case1-architecture.md)
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

For evidence commands, offline replay, and the downstream contract, see the
[director evidence reference](docs/reference/director-evidence.md).

For the full pipeline explanation, evidence limitations, and proposed steps
toward reliable Jev decisions, see the
[director evidence pipeline](docs/director-evidence-pipeline.md).
