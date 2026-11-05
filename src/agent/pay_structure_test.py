"""Does how the CEO's pay is built explain NBIM's pay against-votes? A pilot, and the answer is no.

Run from the repo root (no internet, no API key; the AI reader's answers are cached):
    python3 src/agent/pay_structure_test.py

The pay model finds NBIM's against-votes where the CEO is paid 25 million
dollars or more and misses most of those at 10 to 25 million. NBIM's stated
reason for its pay against-votes is about how pay is built (shares locked in
for five to ten years, one-off awards, boards that do not respond to
shareholders). fetch_pay_structure.py reads ten such facts from the proxy text
with an AI model, each with a quote that is checked against the text.

The pilot: training seasons only, CEO pay of 10 to 25 million dollars, every
against-vote and a random draw of the others, 299 proxies. The test season was
not read.

Because the sample holds all the against-votes and only some of the others,
the "estimated against rate" counts each sampled vote with the board as many
times as needed to stand for all of them.

Result: no answer separates the against-votes well enough to matter. Added to
the current pay inputs, the answers move the hits in the sample from 51 to at
most 53 of 89.

Second test: CEO pay of 25 million dollars or more, where NBIM votes against
about six times in ten. Every such proxy was read (training seasons first,
then the test season). Here three answers do separate the votes on the
training seasons: a one-off award, the performance-based share of equity, and
support at the last pay vote. Added to the pay model as three inputs they
improved both training-season comparisons, so the test season was scored with
them, once. It came out worse than the model without them. The pay model is
therefore unchanged, and the reader's answers are shown as evidence only.
"""

import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from benchmark import model as bm  # noqa: E402
import fetch_pay_structure as fp  # noqa: E402
import pay_model as pm  # noqa: E402

NOT_STATED = "not stated, or quote not found"
BUCKETS = {
    "performance_share_pct": ((50, "under 50%"), (60, "50 to 59%"), (75, "60 to 74%"), (1e9, "75% or more")),
    "longest_lock_years": ((3, "under 3 years"), (3.5, "3 years"), (4.5, "4 years"), (1e9, "5 years or more")),
    "performance_period_years": ((3, "under 3 years"), (3.5, "3 years"), (1e9, "over 3 years")),
    "bonus_pct_of_target": ((100, "under 100%"), (150, "100 to 149%"), (1e9, "150% or more")),
    "prior_support_pct": ((70, "under 70%"), (90, "70 to 89%"), (1e9, "90% or more")),
}
EXTRA = ["no performance-based equity stated", "previous support under 70%", "performance period over 3 years",
         "CEO change in the text", "one-off award", "pay raised by discretion"]


def bucket(key, kind, answer):
    if not answer["verified"]:
        return NOT_STATED
    if kind == "yes_no":
        return answer["answer"]
    return next(label for limit, label in BUCKETS[key] if answer["answer"] < limit)


def extra_inputs(answers):
    v = lambda k: answers[k]["answer"] if answers[k]["verified"] else None
    return [
        1.0 if v("performance_share_pct") is None and v("performance_period_years") is None else 0.0,
        1.0 if v("prior_support_pct") is not None and v("prior_support_pct") < 70 else 0.0,
        1.0 if v("performance_period_years") is not None and v("performance_period_years") > 3.4 else 0.0,
        1.0 if v("ceo_change") == "yes" else 0.0,
        1.0 if v("special_award") == "yes" else 0.0,
        1.0 if v("upward_discretion") == "yes" else 0.0,
    ]


def main():
    rows, _ = pm.load_rows()
    cache = fp.load_cache()
    key_of = lambda r: (str(r["c"].get("cik")), r["moetedato"])
    band = [r for r in rows if r["season"] < pm.TEST_SEASON and r["pay"] and fp.MIN_PAY <= r["pay"] < pm.STRICT_LEVEL
            and r["c"].get("kind") == "proxy"]
    read = [r for r in band if key_of(r) in cache]
    if not read:
        raise SystemExit("No cached answers. Run src/agent/fetch_pay_structure.py --pilot 300 first.")
    n_against = sum(r["y"] for r in read)
    n_with = len(read) - n_against
    weight = (len(band) - sum(r["y"] for r in band)) / n_with
    print(f"Training seasons, CEO pay 10 to 25 million dollars: {len(band)} pay votes, {sum(r['y'] for r in band)} against "
          f"({sum(r['y'] for r in band) / len(band):.0%}).")
    print(f"Proxies read: {len(read)} votes, all {n_against} against-votes and {n_with} of the others "
          f"(each stands for {weight:.1f}).\n")

    print("1. NBIM's against-votes by what the proxy says")
    out = []
    for key, kind, question in fp.QUESTIONS:
        cells = collections.defaultdict(lambda: [0, 0])
        for r in read:
            cells[bucket(key, kind, cache[key_of(r)]["answers"][key])][r["y"]] += 1
        for label in sorted(cells, key=lambda b: (b == NOT_STATED, b)):
            others, against = cells[label]
            out.append([key if label == sorted(cells, key=lambda b: (b == NOT_STATED, b))[0] else "", label, against, others,
                        f"{against / (against + others * weight):.0%}"])
    bm.table(["Question", "Answer", "Against", "With the board (sampled)", "Estimated against rate"], out)
    print("   The questions are written out in src/agent/fetch_pay_structure.py. Quotes for every answer are in")
    print("   data/evidence/pay_structure.csv.")

    print("\n2. Do the answers add anything to the current pay inputs? (the sample, five folds by company)")
    facts = [i for i, f in enumerate(pm.FEATURES) if f[0] not in ("prev_against", "prev_for")]
    for r in read:
        r["extra"] = extra_inputs(cache[key_of(r)]["answers"])
    ys = [r["y"] for r in read]

    def held_out(extra):
        ps = [0.0] * len(read)
        x = lambda r: [r["x"][i] for i in facts] + [r["extra"][j] for j in extra]
        for fold in range(5):
            inside = [r for r in read if pm.fold_of(r) != fold]
            w = bm.fit_logistic([x(r) for r in inside], [r["y"] for r in inside])
            for i, r in enumerate(read):
                if pm.fold_of(r) == fold:
                    ps[i] = bm.predict(w, x(r))
        top = sorted(range(len(read)), key=lambda i: -ps[i])[:n_against]
        return f"{bm.average_precision(ps, ys):.3f}", sum(ys[i] for i in top)

    out = [["current pay inputs", *held_out([])]]
    out += [["+ " + name, *held_out([j])] for j, name in enumerate(EXTRA)]
    out += [["+ all six", *held_out(list(range(len(EXTRA))))]]
    bm.table(["Inputs", "Average precision", f"Hits in the top {n_against}"], out)
    print(f"   Flagging everything in this sample would give an average precision of {n_against / len(read):.3f}.")
    print("   No input moves the hits by more than two. The differences are noise at this sample size.")

    print("\n3. How often the reader found an answer with a quote in the text")
    bm.table(["Question", "Answered with a quote found", "Share of proxies read"],
             [[k, n, f"{n / len(cache):.0%}"] for k, n in
              ((k, sum(1 for rec in cache.values() if rec["answers"][k]["verified"])) for k, _, _ in fp.QUESTIONS)])
    lost = sum(1 for rec in cache.values() for a in rec["answers"].values()
               if a["answer"] not in ("unknown", None) and not a["verified"])
    print(f"   {lost} answers were dropped because their quote was not found word for word in the text.")

    high_pay(rows, cache, key_of)


def high_pay(rows, cache, key_of):
    """The second test: CEO pay of 25 million dollars or more."""
    train = [r for r in rows if r["season"] < pm.TEST_SEASON]
    test = [r for r in rows if r["season"] == pm.TEST_SEASON]
    band = [r for r in train if r["pay"] and r["pay"] >= pm.STRICT_LEVEL and key_of(r) in cache]
    print(f"\n4. CEO pay of 25 million dollars or more, training seasons: {len(band)} votes, "
          f"{sum(r['y'] for r in band)} against ({sum(r['y'] for r in band) / len(band):.0%})")
    out = []
    for key, kind, _ in fp.QUESTIONS:
        if key not in ("special_award", "performance_share_pct", "prior_support_pct"):
            continue
        cells = collections.defaultdict(lambda: [0, 0])
        for r in band:
            cells[bucket(key, kind, cache[key_of(r)]["answers"][key])][r["y"]] += 1
        for i, label in enumerate(sorted(cells, key=lambda b: (b == NOT_STATED, b))):
            others, against = cells[label]
            out.append([key if i == 0 else "", label, against + others, against, f"{against / (against + others):.0%}"])
    bm.table(["Question", "Answer", "Votes", "Against", "Against rate"], out)

    print("\n5. The three answers as inputs to the pay model (+1, 0 or -1 each; see pay_model.structure_inputs)")
    with_inputs = lambda group: [dict(r, x=r["x"] + r["xs"]) for r in group]
    names = [f[0] for f in pm.FEATURES]
    facts = [i for i, n in enumerate(names) if n not in ("prev_against", "prev_for")]
    s24, s25 = [r for r in train if r["season"] == 2024], [r for r in train if r["season"] == 2025]
    out = []
    for label, wrap, cols in (("pay model as it is", lambda g: g, facts),
                              ("with the three inputs", with_inputs, facts + [len(names) + j for j in range(3)])):
        a24, a25 = wrap(s24), wrap(s25)
        _, p25 = pm.fit_predict(a24, a25, cols)
        _, p24 = pm.fit_predict(a25, a24, cols)
        out.append([label, f"{bm.average_precision(p25, [r['y'] for r in s25]):.3f}",
                    f"{bm.average_precision(p24, [r['y'] for r in s24]):.3f}"])
    bm.table(["Training seasons, company facts only", "AP 2024 -> 2025", "AP 2025 -> 2024"], out)

    out, ys = [], [r["y"] for r in test]
    n = sum(1 for r in test if r["prev"] == 1)
    for label, wrap, width in (("pay model as it is", lambda g: g, len(names)), ("with the three inputs", with_inputs, len(names) + 3)):
        _, ps, honest = pm.fit_calibrated(wrap(train), wrap(test), list(range(width)))
        thr = bm.best_f1_threshold(honest, [r["y"] for r in train])
        top = pm.top_flags(ps, n)
        own = [p >= thr for p in ps]
        out.append([label, f"{bm.average_precision(ps, ys):.3f}", sum(y for f, y in zip(top, ys) if f),
                    f"{sum(y for f, y in zip(own, ys) if f)} of {sum(own)} (at {thr:.2f})",
                    f"{sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys):.4f}"])
    bm.table([f"Test season {pm.TEST_SEASON}", "Average precision", f"Hits in the top {n}", "Hits at its own cut-off", "Brier score"], out)
    print("   The three inputs helped on both training-season comparisons and hurt on the test season.")
    print("   The pay model is kept as it is. This was the fifth time the test season was scored.")


if __name__ == "__main__":
    main()
