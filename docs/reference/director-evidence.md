# Director evidence interface

Use these modules to prepare sourced evidence for US director elections.
The output is evidence for the decision module, not a voting recommendation.
For the full flow, known limitations, and proposed Jev integration steps, read
[how director evidence reaches a Jev decision](../director-evidence-pipeline.md).

## Run retrieval

Run from the repository root with Python 3.10 or later. The prepared input
uses the same columns as the preprocessing artifact from `origin/main`.

```bash
python3 src/evidence.py --inputs data/prepared/inputs.csv --year 2025 \
  --meeting-id 1950494 --output-dir /tmp/director-evidence-live
```

Set `SEC_USER_AGENT` to your organization and contact email, and configure
`OPENROUTER_API_KEY` in the environment or repository `.env`. Optionally set
`OPENROUTER_MODEL`; the endpoint must support strict JSON-schema output.
The default is the existing prototype's `deepseek/deepseek-v4.1-flash`.
Missing credentials produce explicit evidence gaps. Do not commit credentials.

An output directory contains `evidence.jsonl`, `summary.json`, and `report.txt`.
Use a fresh directory for each run; an existing packet file is never overwritten.
Omit `--meeting-id` for a whole year. Add `--item-no` to select one output item;
extraction still uses the meeting's selected input rows for cache reuse.
Only 2025 and 2026 US director-election rows are selected by the command.

Replay the saved twenty-nominee development pilot without network credentials:

```bash
python3 src/evidence.py --inputs data/evidence/pilot-v1/inputs.csv \
  --year 2025 --offline --output-dir /tmp/director-evidence-replay
```

Use `--cache` to choose a separate cache. An offline cache miss remains a gap.
Use `--overrides` with a reviewed issuer mapping when exact normalized company
names are ambiguous or have changed. Each mapping entry has this shape:

```json
{
  "554219": {
    "company": "Blackbaud, Inc.",
    "cik": 1280058,
    "source_url": "https://www.sec.gov/edgar/browse/?CIK=1280058",
    "reviewed_by": "Your reviewer name"
  }
}
```

Overrides still require a matching issuer name in the SEC submissions data.
The ticker is never sufficient to establish issuer identity.

## Call the modules

The callable interfaces use dictionaries described by the TypedDict records
in [records.py](../../src/records.py).

```python
# Run with PYTHONPATH=src from the repository root.
import csv
from evidence import collect_meeting_evidence, build_packet
from records import proposal_input, build_decision_context

with open("data/evidence/pilot-v1/inputs.csv") as source:
    rows = [proposal_input(row) for row in csv.DictReader(source)]
meeting = [row for row in rows if row["meeting_id"] == "1950494"]
evidence = collect_meeting_evidence(meeting, offline=True)
packet = build_packet(meeting[0], evidence)
context = build_decision_context(packet)
assert context["routing_contract"]["automatic_for_allowed"] is False
```

`select_policy(proposal, company_evidence)` in
[policy.py](../../src/policy.py) is pure lookup and ranking. The collector shares
meeting facts and extracts nominees in batches of five. Exact source checks
produce partial facts first. A separate model grounding pass can promote a
claim to known only with matching evidence; manual source audit remains
necessary because model verification can also make mistakes.

## Interpret evidence and coverage

Facts distinguish `known`, `partial`, `unknown`, and `conflicting`. Each sourced
fact includes its typed value, source URL, filing date, raw-document hash,
canonical-text offsets, quotation, and population/time scope. Offsets refer to
the canonical text produced by `TextOnly`, not raw HTML byte positions.

The collector requires a matching issuer, a meeting-notice/date association,
and sourced evidence that each nominee is on the current election slate.
Only definitive proxies filed strictly before the meeting are eligible.
Recent publication alone does not establish meeting identity.

The policy module indexes all 25 candidate US election rules and selects up to
three sections. Core coverage is independence (`1.1.1–1.1.3`), committee roles
and independence (`1.2.1–1.2.3`), combined chair/CEO roles (`1.3.1`), and numeric
outside-commitment concerns (`2.1.1`). Other checks are `not_implemented`.
Sections rank by concerns, unresolved core facts, assessed checks, and numeric
section order. Omitted rules retain coverage and concern metadata.

An incomplete board-role list does not establish an absence of overboarding.
Missing cap classification is not inferred from SEC reporting categories.
Founder exceptions and discretionary workload judgments require review.

The handoff carries exact selected rules, subsection context, principles,
readiness and omission metadata. The downstream owner must check the cited
rule condition, required facts, conflicts, exceptions and probability gate
before an automatic MOT. All other cases require review. Management's vote can
be displayed as a labelled baseline; it is not an evidence-backed FOR result.

Both years use the supplied 2025 policy as an explicitly fixed-version
experiment. The repository has already inspected 2026 outcomes; do not describe
that comparison as untouched. No outcomes or historical rationales enter these
modules. Unsupported countries, types, years, and malformed election titles
produce explicit gaps rather than a recommendation.

## Verify changes

Run focused contract tests and the existing benchmark checks:

```bash
python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m unittest discover -s src/benchmark -p 'test_model.py'
```

The [architecture](../case1-architecture.md) explains the remaining Jev,
review-gate, evaluator, and integration responsibilities.
