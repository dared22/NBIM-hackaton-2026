"""Experiment: does what the ballot itself reveals improve the history model?

Result: no. On test years 2022-2025 the additions below leave the model where
it was (hits at the baseline's flag count 126 -> 129 of 401, against 133 for
"same as last time"; share of against-votes seen when reading the riskiest
25% of proposals 73% -> 74%). The benchmark in src/benchmark/model.py is
kept, and this version was not scored on 2026.

Run from the repo root (no internet, no API key):
    python3 src/agent/history_model.py             # the comparison on 2022-2025
    python3 src/agent/history_model.py --test-year 2026   # score a year with all additions

The benchmark in src/benchmark/model.py uses NBIM's earlier votes only. The
data audit (src/agent/data_audit.py) showed that the ballot holds more:

    position      the first director listed is opposed far more often than the
                  rest in some countries (Japan, South Korea, Taiwan)
    board size    few directors on the ballot goes with more against-votes
    labels        some ballots say who is independent and who is not
    wording       "chair", "supervisory board", several people in one item
    finer types   the catch-all type OTHER_MGMT hides director appointments,
                  pay items and rule changes
    last meeting  whether NBIM opposed anything at the company's previous meeting

All of these are read from the agenda, which is public before the meeting. No
outside data is used and it works in every country.

Each addition is a rate learned from earlier meetings only, in the same way as
the benchmark's inputs, and frozen before the test year.

Honest note on how these were found: the audit tables covered the whole file,
including 2026. The weights are fitted on earlier years only, and --develop
shows whether each addition helps on test years 2022-2025, but the ideas
themselves were not found blind to 2026.
"""

import argparse
import collections
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
from benchmark import model as bm  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
M = 8.0  # smoothing: how many "virtual" votes the broader average counts for

GROUPS = [
    ("position", "this director's place on the ballot, in this country"),
    ("board_size", "how many directors are on the ballot"),
    ("label", "the ballot says whether this nominee is independent"),
    ("wording", "the item mentions a chair, a supervisory board or several people at once"),
    ("last_meeting", "NBIM opposed something at this company's previous meeting"),
]


def finer_type(r):
    """Split the catch-all type OTHER_MGMT by wording."""
    if r["proposal_type"] != "OTHER_MGMT":
        return r["proposal_type"]
    t = r["proposal_text"].lower()
    if re.search(r"appoint(ment)? .* as |as (managing|whole-time|executive|independent) director", t):
        return "OTHER_APPOINTMENT"
    if re.search(r"amend|rules|system|procedure", t):
        return "OTHER_RULES"
    if re.search(r"remuneration|commission|allowance|bonus", t):
        return "OTHER_PAY"
    return "OTHER_MGMT"


def describe_ballot(rows):
    """Attach what the agenda says about each item. Uses no votes."""
    meetings = collections.defaultdict(list)
    for r in rows:
        meetings[r["meeting_id"]].append(r)
    for items in meetings.values():
        items.sort(key=lambda r: int(r["item_no"]))
        directors = [r for r in items if r["proposal_type"] == "DIRECTOR_ELECTION"]
        for r in directors:
            t = r["proposal_text"].lower()
            r["_label"] = ("non-independent" if re.search(r"non-independent|inside director|executive director", t)
                           else "independent" if re.search(r"independent|outside", t) else "")
        labelled = [r for r in directors if r["_label"]]
        share = sum(1 for r in labelled if r["_label"] == "independent") / len(labelled) if len(labelled) >= 3 else None
        n = len(directors)
        for r in items:
            r["keys"] = {}
        for i, r in enumerate(directors):
            t = r["proposal_text"].lower()
            if n >= 3:
                r["keys"]["position"] = ("position", r["country"], "first" if i == 0 else "later")
            r["keys"]["board_size"] = ("board_size", "1-2" if n <= 2 else "3-6" if n <= 6 else "7-9" if n <= 9 else "10+")
            if r["_label"]:
                mix = "" if share is None else "under half independent" if share < 0.5 else "half or more independent"
                r["keys"]["label"] = ("label", r["_label"], mix)
            word = ("several" if re.search(r"^elect (directors|board|supervisory board members|members)|slate|bundled", t)
                    else "supervisory" if "supervisory" in t else "chair" if "chair" in t else "")
            if word:
                r["keys"]["wording"] = ("wording", word)


def add_ballot_features(rows, history_before=None):
    """Rates for each ballot description, learned from earlier meeting dates only."""
    counts = collections.defaultdict(lambda: [0, 0])
    last_meeting = {}  # company -> did NBIM oppose anything at its latest meeting

    def rate(key, prior):
        n, k = counts[key]
        return (k + M * prior) / (n + M)

    by_date = collections.defaultdict(list)
    for r in rows:
        by_date[r["meeting_date"]].append(r)
    for date in sorted(by_date):
        todays = by_date[date]
        for r in todays:
            p_type = rate(("type", r["proposal_type"]), rate("all", 0.05))
            s = []
            for name, _ in GROUPS[:-1]:
                key = r["keys"].get(name)
                s.append(bm.cap(bm.logit(rate(key, p_type)) - bm.logit(p_type)) if key else 0.0)
            before = last_meeting.get(r["company_id"])
            s.append(1.0 if before is True else -0.5 if before is False else 0.0)
            r["s"] = s
        if history_before is not None and date >= history_before:
            continue
        opposed = collections.defaultdict(bool)
        for r in todays:
            for key in ["all", ("type", r["proposal_type"])] + list(r["keys"].values()):
                counts[key][0] += 1
                counts[key][1] += r["y"]
            opposed[(r["company_id"], r["meeting_id"])] |= bool(r["y"])
        for (company, _), any_against in opposed.items():
            last_meeting[company] = any_against


def prepare(rows, test_year, use):
    """Copies of the rows before and in the test year, with all inputs attached."""
    year = lambda r: int(r["meeting_date"][:4])
    part = [r.copy() for r in rows if year(r) <= test_year]
    if use.get("finer_types"):
        for r in part:
            r["type_given"], r["proposal_type"] = r["proposal_type"], finer_type(r)
    freeze = f"{test_year}-01-01"
    bm.add_history_features(part, freeze)
    describe_ballot(part)
    add_ballot_features(part, freeze)
    keep = [i for i, (name, _) in enumerate(GROUPS) if use.get(name)]
    for r in part:
        r["x"] = r["x"] + [r["s"][i] for i in keep]
    return [r for r in part if year(r) < test_year], [r for r in part if year(r) == test_year]


ALL = {name: True for name, _ in GROUPS}
ALL["finer_types"] = True


def run_year(rows, test_year, use=None):
    """Fit on earlier years, score the test year. Returns (train, test, weights, cut-off)."""
    use = ALL if use is None else use
    year = lambda r: int(r["meeting_date"][:4])
    # Cut-off from the last training year, scored by a model that never saw it.
    fit_part, val_part = prepare(rows, test_year - 1, use)
    w_val = bm.fit_logistic([r["x"] for r in fit_part], [r["y"] for r in fit_part])
    threshold = bm.best_f1_threshold([bm.predict(w_val, r["x"]) for r in val_part], [r["y"] for r in val_part])
    train, test = prepare(rows, test_year, use)
    w = bm.fit_logistic([r["x"] for r in train], [r["y"] for r in train])
    for r in test:
        r["p"] = bm.predict(w, r["x"])
        r["band"] = "likely AGAINST board" if r["p"] >= threshold else "likely WITH board" if r["p"] < bm.LOW else "send to human"
    return train, test, w, threshold


def top_flags(ps, n):
    order = sorted(range(len(ps)), key=lambda i: -ps[i])[:n]
    flags = [False] * len(ps)
    for i in order:
        flags[i] = True
    return flags


def develop(rows):
    """Which additions help? Test years 2022-2025 only; 2026 is not read."""
    years = range(2022, 2026)
    none = {}
    sets = [("benchmark (history only)", none), ("+ finer types", {"finer_types": True})]
    sets += [(f"+ {name}", {name: True}) for name, _ in GROUPS]
    sets += [("+ everything", ALL)]
    sets += [(f"everything except {name}", {k: v for k, v in ALL.items() if k != name}) for name in ALL]
    print("Test years 2022-2025, each scored by a model fitted on the years before it. 2026 is not read.\n")
    out = []
    for label, use in sets:
        hits = flags = base = pos = new_hits = new_pos = 0
        aps = []
        for ty in years:
            _, test, _, _ = run_year(rows, ty, use)
            ys, ps = [r["y"] for r in test], [r["p"] for r in test]
            n = sum(1 for r in test if r["prev_same_item"] == 1)
            flagged = top_flags(ps, n)
            hits += sum(y for f, y in zip(flagged, ys) if f)
            new_hits += sum(1 for f, r in zip(flagged, test) if f and r["y"] and r["prev_same_item"] != 1)
            new_pos += sum(1 for r in test if r["y"] and r["prev_same_item"] != 1)
            base += sum(r["y"] for r in test if r["prev_same_item"] == 1)
            flags += n
            pos += sum(ys)
            aps.append(bm.average_precision(ps, ys))
        out.append([label, f"{sum(aps) / len(aps):.3f}", hits, f"{new_hits}/{new_pos}"])
    bm.table(["Inputs", "Mean average precision", f"Hits at the baseline's {flags} flags", "New situations found"], out)
    print(f"\n  'Same as last time' finds {base} of {pos} against-votes with {flags} flags, and no new situations by construction.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-year", type=int, default=0)
    a = ap.parse_args()
    rows = bm.read_votes(VOTES)
    if not a.test_year:
        develop(rows)
        return

    _, old, _, old_thr = bm.run_year(rows, a.test_year)
    train, test, w, thr = run_year(rows, a.test_year)
    ys = [r["y"] for r in test]
    n = sum(1 for r in test if r["prev_same_item"] == 1)
    print(f"History model v2 | test year {a.test_year} | train {len(train)} | test {len(test)}, {sum(ys)} against the board\n")
    bm.table(["Method", "Precision", "Recall", "F1", "Accuracy", "Flagged", "Hits", "False alarms", "Missed"],
             [bm.metric_row("Always with board", [False] * len(test), test),
              bm.metric_row("Same as last time", [r["prev_same_item"] == 1 for r in test], test),
              bm.metric_row(f"Benchmark, top {n}", top_flags([r["p"] for r in old], n), old),
              bm.metric_row(f"Version 2, top {n}", top_flags([r["p"] for r in test], n), test),
              bm.metric_row(f"Benchmark, p >= {old_thr:.2f}", [r["p"] >= old_thr for r in old], old),
              bm.metric_row(f"Version 2, p >= {thr:.2f}", [r["p"] >= thr for r in test], test)])
    print(f"\n  Average precision: version 2 {bm.average_precision([r['p'] for r in test], ys):.3f}, "
          f"benchmark {bm.average_precision([r['p'] for r in old], [r['y'] for r in old]):.3f}, random {sum(ys) / len(ys):.3f}")
    new = [r for r in test if r["y"] and r["prev_same_item"] != 1]
    print(f"  New situations (not opposed before at that company): {len(new)}. Version 2 finds "
          f"{sum(1 for r in new if r['p'] >= thr)}, the benchmark {sum(1 for r in old if r['y'] and r['prev_same_item'] != 1 and r['p'] >= old_thr)}.")

    print("\nBands")
    bm.table(["Band", "Proposals", "Share", "Actual against board", "Against rate"],
             [[b, len(v), f"{len(v) / len(test):.1%}", sum(r["y"] for r in v), f"{sum(r['y'] for r in v) / len(v):.1%}" if v else "-"]
              for b, v in ((b, [r for r in test if r["band"] == b]) for b in ("likely WITH board", "send to human", "likely AGAINST board"))])

    print("\nWeights for the additions (positive = pushes towards AGAINST)")
    names = [name for name, _ in bm.FEATURES] + [name for name, _ in GROUPS]
    for name, wi in list(zip(names, w[1:]))[len(bm.FEATURES):]:
        print(f"  {wi:+6.2f}  {name:<13} {dict(GROUPS)[name]}")

    path = os.path.join(ROOT, "data", "outputs", f"history_v2_{a.test_year}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["meeting_id", "item_no", "meeting_date", "company", "country", "proposal_type", "proposal_text",
                     "mgmt_rec", "probability_against", "band", "actual_against"])
        for r in sorted(test, key=lambda r: -r["p"]):
            wr.writerow([r["meeting_id"], r["item_no"], r["meeting_date"], r["company"], r["country"],
                         r.get("type_given", r["proposal_type"]), r["proposal_text"], r["mgmt_rec"],
                         f"{r['p']:.3f}", r["band"], r["y"]])
    print(f"\nWrote {len(test)} scored proposals to {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
