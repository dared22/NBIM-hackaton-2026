# Progress: where we are and what is next

**Deadline: Friday 6 November, 12:00.** Presentations 12:00-14:00.

How to use this file: when you finish or start something, change the tables
below and add one line to the log at the bottom. Keep it short. Write your
name in the "Who" column so nobody builds the same thing twice.

Last full update: Fri 03:08.

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
| Combined model, all proposal types (main + Marie's Jev pipeline) | `src/agent/combined_model.py` | Done, in the pipeline | 2022-2025: better than either system alone. 2026: 26 right of 36 automatic suggestions (72%), 10 waved through, 56 of 66 suggested or seen (before 25 of 35, 14, and 52). `USE_COMBINED` in `src/run.py` switches it off |
| History model, all proposal types | `src/benchmark/model.py` | Done | Ties the simple rule: 24 hits against 22 on 2026 |
| Pay model, US pay votes | `src/agent/pay_model.py` | Done | 72 hits against 42 at the same number of flags, season 2026. CEO pay known for 98% of test votes |
| Judge model for US director nominees | `src/agent/judge.py` | Done, in the pipeline | Weighs proxy facts against NBIM's rules and record, no names sent. Right 30 of 43 times when it says 50% or more (2021-2025). 2026 pipeline: 33 automatic suggestions, 26 right (79%) |
| Director facts for Japan and Korea | `src/agent/country_rules.py` | Done, in the pipeline | In Japan NBIM opposes only top executives (27 of 141, none of 739 others). Brings in a person: 11 more against-votes seen on 2022-2025, no change on 2026 |
| Policy watch | `src/agent/policy_watch.py` | Done | NBIM's live guidelines against the stored 2025 edition: 75 of 76 rules identical, rule 1.3.1 softened from "will not" to "may not" |
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
| Checks | `tests/test_agent.py` | Done | 70 pass, including leakage audits and two end-to-end attack checks |

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
3. **The tool found a policy change from the votes, and the written rule had
   changed too.** NBIM opposed 28 of 28 chair-and-CEO nominees in 2019-2024
   and 0 of 5 in 2026, while the 2025 guidelines we were given say "will not
   support". The tool takes a rule's trust away at the first miss and sends
   later cases to a person. NBIM's guidelines web page now says "may not
   support" for exactly that rule, the only one of 76 that was reworded
   (`src/agent/policy_watch.py`).

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
| `marie` | marie | Jev pipeline with company facts for the US, Japan and Korea | Her per-proposal scores are exported into `main` (`data/evidence/jev_pipeline/`) and used by the combined model. The branch itself is 5 GB (downloaded filings) and is not merged |
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

## Note on `min-agent/`

The three files Gemini wrote were read and not run. They refer to files this repo does not
have (`modell.py`, `motstandstest.py`, `kravrespons.md`, `EXPERIMENTS.md`), their five
backlog items are all already done or tested here, and the loop they describe keeps a
change when the 2026 score goes up and reverts it otherwise. That is tuning on the test
year, which the rules penalise, and its `git checkout -- .` would also wipe uncommitted
files. The useful part, one idea per round with a log, is how the night work is run:
ideas are chosen on 2022-2025, and every scoring of 2026 is written down.

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
- Fri 00:30 Iftikhar: four fixes suggested from the 2026 pay misses were tested on the training seasons instead. One holds (last pay vote under 70% support, rule 3.3.5) and now sends the vote to a person. The others were weak or already covered.
- Fri 01:25 Iftikhar: checked Marie's comparison with main, then built the combined model from both systems. Designed on 2022-2025, 2026 scored once. In the pipeline, with a switch.
- Fri 01:47 Iftikhar: combined model improved on 2022-2025: the tool now acts alone only when a rule, a fact or NBIM's own last vote backs the suggestion (precision 52% to 67% there). Five other ideas tested and left out. 2026 has been scored twice with the combined model.
- Fri 02:09 Iftikhar: Japan and Korea director facts (from Marie's EDINET and OpenDART data) used as reasons to bring in a person. Night work continues; Gemini's files in `min-agent/` were checked and not run (see the note in this file).
- Fri 02:23 Iftikhar: tested 'more policy'. The rules we use are in every edition since 2020, so edition dates do not explain misfires. But NBIM's live guidelines page has softened rule 1.3.1 to 'may not', the rule where 2026 votes changed. Policy watch added; no effect on test numbers. Meeting-level signals and vote results from last year's AGM tested on 2022-2025: no gain, left out.
- Fri 02:48 Iftikhar: tested 'AI gathers the facts, a judge decides' with Claude Haiku as judge (no Typesafe key for Jev). On US directors it ranks much better than the history model; in the pipeline it helps a little on 2022-2025 (suggested or seen 315 to 319 of 401) and is adopted. 2026 scored a third time: 33 automatic suggestions, 26 right. Cross-shareholdings in Japan tested: no clean rule, left out.
- Fri 02:59 Iftikhar: judge model tested on pay votes (training seasons, 1,430 votes): worse than the pay model and no gain together, left out. Added 95% intervals and a confidence check for the combined pipeline: 2026 precision 76% (62-90%), suggested or seen 85% (75-94%).
- Fri 03:08 Iftikhar: gave the judge last year's published support for each US director (from SEC vote results). Tested on 2021-2025: slightly worse (average precision 0.608 against 0.619), reverted.
