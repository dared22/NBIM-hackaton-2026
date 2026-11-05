# Progress: where we are and what is next

**Deadline: Friday 6 November, 12:00.** Presentations 12:00-14:00.

How to use this file: when you finish or start something, change the tables
below and add one line to the log at the bottom. Keep it short. Write your
name in the "Who" column so nobody builds the same thing twice.

Last full update: Thursday 19:48.

## What must be delivered

| Deliverable | Status | Who |
|---|---|---|
| One-page response (the rules call it the most important) | Not started. `docs/model-card.md` is close to a first draft | |
| 5-minute demo, preferably running | Not started. `data/outputs/decisions_2026.csv` holds the content for it | |
| Code with a README where one command reproduces the main result | Done: `python3 src/run.py` | |
| Answers to the three jury questions (target, production, one more week) | Not written. Notes in `docs/model-card.md` | |
| E-mail to milad.tootoonchi@nmbu.no: subject "<group name> Hackathon H2026 demo", all names in the body | Not sent | |

## What is built and merged into `main`

| Piece | File | Status | Result |
|---|---|---|---|
| History model, all proposal types | `src/benchmark/model.py` | Done | Ties the simple rule: 24 hits against 22 on 2026 |
| Pay model, US pay votes | `src/agent/pay_model.py` | Done | 72 hits against 42 at the same number of flags, season 2026. CEO pay known for 98% of test votes |
| Director rules, US director elections | `src/agent/director_rules.py` | Done | 38 hits and 12 false alarms; simple rule 36 and 37 (2019-2026) |
| Wording rules, all countries | `src/agent/proposal_rules.py` | Done | NBIM voted as its rule says on 73 of 73; 66 against-votes found with no false alarms, 21 of them first-time items |
| NBIM's position papers | `data/policy/position_papers.json`, `src/agent/position_papers_test.py` | Done | Each decision names the paper NBIM would cite (28 of 31 match on director hits). No gain for prediction |
| Guideline check with a decision model | `src/agent/rule_check.py` | Done | No gain from wording alone |
| Resistance test and guardrail | `src/agent/robustness.py` | Done | All instruction attacks flagged, no false alarms on 66,663 real texts |
| Low-information gate and drift monitor | `src/run.py`, `src/agent/director_rules.py` | Done | The tool never follows the board alone when it has no facts |
| One decision per proposal | `data/outputs/decisions_2026.csv` | Done | 2,739 proposals with vote, probability, band, reasons, guideline, evidence link |
| Data audit of all three vote files | `src/agent/data_audit.py` | Done | Report in `data/outputs/data_audit.md` |
| Model card | `docs/model-card.md` | Done | Target, data, results, limits, sources |
| Checks | `tests/test_agent.py` | Done | 32 pass, including leakage audits and two end-to-end attack checks |

Run everything: `python3 src/run.py` (about three minutes, no key, no internet).
Run the checks: `python3 -m unittest discover -s tests`.
On a Mac where `python3` fails on certificates, use `/usr/bin/python3`.

## The three results to present

1. **Vote history alone is not enough.** On all proposal types it ties "vote
   the same as last time". Two thirds of NBIM's against-votes are on items it
   never opposed before at that company.
2. **Facts make the difference.** With pay figures read from each company's
   proxy, the tool finds 72 of 114 against-votes on US pay where the simple
   rule finds 42. With roles from SEC filings, NBIM's own rule "no chair who
   is also CEO" is right 84% of the time it fires.
3. **Policy and practice differ.** NBIM opposed 28 of 28 chair-and-CEO
   nominees in 2019-2024 and 0 of 5 in 2026, while the 2025 guidelines still
   contain the rule. A rule that is wrong twice in a row is now suspended and
   its cases go to a person.

## Decisions the team still has to make

- **Which target to lead with.** The models predict "NBIM voted against the
  board". The README and `docs/case1-architecture.md` name "NBIM voted MOT" as
  the primary target. They differ on shareholder proposals. The jury's first
  question is about this. Suggestion in `docs/model-card.md`.
- **Group name** for the e-mail subject.
- **Who presents what** in the five minutes.

## What is next

| Priority | Task | Who |
|---|---|---|
| 1 | Write the one-page response from `docs/model-card.md` | |
| 2 | Build the demo: show `decisions_2026.csv` with filters, the evidence links and the injection toggle | |
| 3 | Write and rehearse the three jury answers | |
| 4 | Merge or park the open branches below, so `main` is what we hand in | |
| 5 | Ask Andreas (Case 1 contact): is the `against_board` column in `npx_votes.csv` built correctly? Which investor is it? | |
| 6 | If time: independence and committee facts for US directors (rules 1.1 and 1.2), from the AI reader on `llm_search` | |

## Branches not yet in `main`

| Branch | Who | What | Note |
|---|---|---|---|
| `llm_search` | dared22 | AI model reads proxies for director facts (independence, committees, chair, CEO), with a quote for each fact | Pilot on 5 meetings, no accuracy number yet. Adds `src/policy.py` |
| `policy-retrieval` | M03ZGH | Finds guideline sections that match a proposal | Also adds `src/policy.py`: will conflict with `llm_search` |
| `marie` | marie | Jev decision model on NBIM votes; new guidelines file | Very large: 249 files changed. Check what should go into `main` |
| `rule-check` | Iftikhar | Same as `main` | Can be deleted |

## Things to know before presenting

- The two models are scored on two different files. File A is the organisers'
  `real_votes.csv` (1,539 proposals in 2026, 66 against). File B is Norges
  Bank's own SEC filings (1,200 US pay votes in season 2026, 114 against).
  The counts do not add up to one total.
- `npx_votes.csv` is another investor, and its `against_board` column looks
  wrong. Proof in `data/outputs/data_audit.md`, section 2.
- The 2026 season was scored three times for the pay model, once per version.
  This is stated in the model card.
- Volkswagen holds 125 of the 744 against-votes in file A.
- AI tools used must be listed in the README: Claude Code, Microsoft-Decision-1
  through OpenRouter, plus whatever the other branches used (DeepSeek, Jev).
- Do not commit `.env`. It holds the OpenRouter key and is ignored by git.

## Log

Add newest at the bottom: day, time, name, what changed.

- Thu 12:00 Iftikhar: repo cloned, case chosen (Case 1), NBIM pay votes pulled from SEC.
- Thu 12:50 Iftikhar: history model and baselines on `real_votes.csv`.
- Thu 14:30 Iftikhar: guideline check and resistance test; both documented as they came out.
- Thu 15:10 Iftikhar: first pay model with SEC API figures.
- Thu 16:10 Iftikhar: pay figures read from each meeting's own proxy; 71 of 114.
- Thu 17:30 Iftikhar: `src/run.py`, tests, model card, data audit.
- Thu 18:00 Iftikhar: low-information gate; ballot-detail experiment (no gain).
- Thu 18:40 Iftikhar: director rules from SEC role data; chair-and-CEO finding; drift monitor.
- Thu 18:55 Iftikhar: merged into `main`, this file added.
- Thu 19:05 Iftikhar: wording rules for shareholder proposals (declassify, written consent, simple majority and so on): 22 of 22.
- Thu 19:20 Iftikhar: NBIM's 12 position papers loaded and tested. Good for citations, no gain for prediction.
- Thu 19:30 Iftikhar: "other business" rule (5.2.2) added to the wording rules: 44 of 44. Unnamed auditor and unnamed directors tested and left out.
- Thu 19:48 Iftikhar: 239 more companies linked to the SEC (acquired, delisted or oddly spelled names); pay coverage 93% -> 98%. Appended-text defence now inside the pipeline with end-to-end checks. Recency weighting and merger payouts tested, no gain.
