# Progress: where we are and what is next

**Deadline: Friday 6 November, 12:00.** Presentations 12:00-14:00.

How to use this file: when you finish or start something, change the tables
below and add one line to the log at the bottom. Keep it short. Write your
name in the "Who" column so nobody builds the same thing twice.

Last full update: Fri 00:11.

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
| Proxy reader for US director elections (AI model reads, code decides) | `src/agent/fetch_board_facts.py`, `src/agent/board_rules.py` | Done | Facts with checked quotes for 98% of 1,742 nominees. Tool acts alone on 45, right on 39 (87%); simple rule 36 of 73. 12 more against-votes reach a person with the fact |
| Check of the proxy reader by a second model | `src/agent/board_reader_check.py` | Done | 16 meetings, 122 nominees: same answer on 98.2% of facts; rules fire on the same nominees for 120 of 122 |
| Director rules on SEC insider filings (second source) | `src/agent/director_rules.py` | Done | 38 hits and 12 false alarms; agrees with the proxy reader on 98.9% of nominees |
| Wording rules, all countries | `src/agent/proposal_rules.py` | Done | NBIM voted as its rule says on 79 of 79; 72 against-votes found with no false alarms, 27 of them first-time items |
| NBIM's position papers | `data/policy/position_papers.json`, `src/agent/position_papers_test.py` | Done | Each decision names the paper NBIM would cite (28 of 31 match on director hits). No gain for prediction |
| Guideline check with a decision model | `src/agent/rule_check.py` | Done | No gain from wording alone |
| Resistance test and guardrail | `src/agent/robustness.py` | Done | All instruction attacks flagged, no false alarms on 66,663 real texts |
| One answer per proposal | `src/agent/pay_overlap.py`, `src/run.py` | Done | US pay proposals that are in both files were answered twice. They now get the pay model's answer (5 of 8 against-votes found on those, history model 2). File A 2026: 36 automatic "against" suggestions, 25 right |
| Confidence and routing | `src/agent/routing.py` | Done | Below 5% the tool is wrong about 2% of the time; no signal in the vote file picks those out. The 5% level is kept, with a table of what other levels cost. Abstain suggested where a market has the habit (18 of 19 right in 2021-2025) |
| Pay structure reader (AI model) | `src/agent/fetch_pay_structure.py`, `src/agent/pay_structure_test.py` | Done, not adopted as model input | 675 proxies read with a checked quote for every answer. No gain at 10 to 25 million dollars. At 25 million or more it helped on the training seasons and hurt on 2026, so the pay model is unchanged. Shown as evidence on 152 pay decisions |
| Low-information gate and drift monitor | `src/run.py`, `src/agent/director_rules.py` | Done | The tool never follows the board alone when it has no facts |
| One decision per proposal | `data/outputs/decisions_2026.csv` | Done | 2,739 proposals with vote, probability, band, reasons, guideline, the guideline's own words and page number, evidence link |
| Data audit of all three vote files | `src/agent/data_audit.py` | Done | Report in `data/outputs/data_audit.md` |
| Model card | `docs/model-card.md` | Done | Target, data, results, limits, sources |
| Checks | `tests/test_agent.py` | Done | 54 pass, including leakage audits and two end-to-end attack checks |

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
| 6 | Done: facts for US directors read from proxies (independence, committees, roles, boards) | Iftikhar |
| 7 | Done, no gain: how pay is built for CEOs paid 10 to 25 million dollars, read from the proxy text by an AI model (pilot) | Iftikhar |

## Branches not yet in `main`

| Branch | Who | What | Note |
|---|---|---|---|
| `llm_search` | dared22 | AI model reads proxies for director facts (independence, committees, chair, CEO), with a quote for each fact | Pilot on 5 meetings, no accuracy number yet. Adds `src/policy.py` |
| `policy-retrieval` | M03ZGH | Finds guideline rules that match a proposal by keywords | Reviewed, not needed in `main`. Valid JSON, but NBIM's own section is among its candidates for 27 of 63 against-votes in 2026; the picker in `main` gets 45. Its good idea, quoting each rule's text and page, is now in `decisions_2026.csv` |
| `marie` | marie | Jev decision model on NBIM votes; new guidelines file | Very large: 249 files changed. Check what should go into `main` |
| `rule-check` | Iftikhar | Same as `main` | Can be deleted |

## Things to know before presenting

- The two models are scored on two different files. File A is the organisers'
  `real_votes.csv` (1,539 proposals in 2026, 66 against). File B is Norges
  Bank's own SEC filings (1,200 US pay votes in season 2026, 114 against).
  The counts do not add up to one total.
- `npx_votes.csv` is another investor, and its `against_board` column looks
  wrong. Proof in `data/outputs/data_audit.md`, section 2.
- The 2026 season was scored five times for the pay model. The reported
  numbers are from before the fifth scoring, which was a rejected experiment.
  This is stated in the model card.
- Volkswagen holds 125 of the 744 against-votes in file A.
- AI tools used must be listed in the README: Claude Code, Microsoft-Decision-1,
  Claude Haiku 5.5 and Claude Sonnet 5.5 through OpenRouter, plus whatever the other branches
  used (DeepSeek, Jev).
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
- Thu 20:23 Iftikhar: reviewed `policy-retrieval`. Every cited guideline in `decisions_2026.csv` now carries its own words and page number (new column `guideline_text`), with a check that the quotes are word for word.
- Thu 20:40 Iftikhar: confidence and routing report (`src/agent/routing.py`); abstain rule in the pipeline; pay misses studied on the training seasons, five more inputs tested and left out.
- Thu 21:03 Iftikhar: AI reader of pay structure built and piloted on 299 proxies (training seasons). No gain, so the rest were not read and the pay model is unchanged.
- Thu 21:13 Iftikhar: US pay proposals that sit in both vote files now get one answer, from the pay model. One false alarm fewer on file A in 2026.
- Thu 21:14 Iftikhar: a non-linear pay model (boosted trees) tested on the training seasons: no gain, logistic model kept.
- Thu 22:46 Iftikhar: proxy reader for US director elections. An AI model reads facts with checked quotes, code applies nine NBIM rules, and a rule acts alone only after NBIM followed it twice in a row. In the pipeline; file A 2026 now 35 automatic 'against' suggestions, 25 right, and 52 of 66 against-votes suggested or seen.
- Thu 23:02 Iftikhar: pay reader extended to CEO pay of 25 million dollars or more. Better on the training seasons, worse on 2026, so not adopted. Its findings now appear as evidence with quotes on 152 pay decisions.
- Thu 23:05 Iftikhar: wording rule for appointing one person as chair and managing director or CEO (rule 1.3.1, India): 6 of 6, none in 2026. Changes to governing documents looked at and left with a person.
- Thu 23:18 Iftikhar: a second, stronger model re-read 13 meetings to check the proxy reader: 98.2% the same answers. It exposed a 'founder of another company' mistake, now fixed in code. OpenRouter key: about 3 dollars left of 10, and new calls are being refused by its credit check.
- Thu 23:33 Iftikhar: reader check completed to 16 meetings (the key works again). Pay vote and director votes at the same meeting tested: a link, but too few cases to act on.
- Fri 00:11 Iftikhar: added the one-line rule 'against if CEO pay is 25 million dollars or more' as a baseline for the pay model. It finds 83 of 114 with 72 false alarms; the model finds 79 with 31.
