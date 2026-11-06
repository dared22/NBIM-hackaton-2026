"""The judge: an AI model weighs the facts the tool has gathered against NBIM's rules and NBIM's record.

Run from the repo root:
    python3 src/agent/judge.py                    # the comparison below, from cached answers (no key, no internet)
    python3 src/agent/judge.py --fill 2025        # ask the judge about every proposal up to that year that has no answer yet

The idea (the team's "let the AI gather the facts and let a judge decide")
    The tool collects, for a US director nominee: the facts read from the proxy (independent,
    executive, chair, CEO, founder, committees, other boards, attendance, the board's size,
    independence and number of women), NBIM's vote on the nominee last time, every NBIM rule
    whose condition is met, and how often NBIM actually followed that rule at earlier
    meetings. The combined model sees most of this as two yes/no inputs. The judge sees all
    of it, with NBIM's rules in NBIM's words, and returns a probability, a rule and a reason.

What the judge is and is not given
    - No company name and no person's name, so it cannot answer from memory of the company.
    - No vote from the meeting being judged or from any later meeting. "Last time" and the
      rule records come from earlier meetings only (board_rules.earn_trust, and the history
      frozen before the year).
    - No year. The record tells it whether NBIM has been following a rule.
    - It is told that NBIM's written rules are not always its practice.

    The judge is not trained on NBIM's votes, so every year is a test year for it. Its
    probability becomes one more input to the combined model, with a weight fitted on
    earlier years.

Model: Claude Haiku 5.5 through OpenRouter. Answers are cached in src/agent/cache/judge.jsonl,
keyed by the proposal and by the exact text sent, so a changed fact means a new question.
"""

import argparse
import collections
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from benchmark import model as bm  # noqa: E402
import board_rules as br  # noqa: E402
import rule_check as rc  # noqa: E402
from fetch_pay_structure import call_model  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
CACHE = os.path.join(ROOT, "src", "agent", "cache", "judge.jsonl")
MODEL = "anthropic/claude-haiku-5.5"
DIRECTOR_SECTIONS = ("1.1", "1.2", "1.3", "2.1", "2.3", "3.2")
SPEND_LIMIT = 2.0   # dollars per run


def system_prompt():
    with open(rc.GUIDELINES, encoding="utf-8") as f:
        g = json.load(f)
    rules = "\n".join(f"[{r['id']}] {r['tekst']}" for r in g["regler"] if r["underseksjon"] in DIRECTOR_SECTIONS)
    return (
        "You estimate how Norges Bank Investment Management (NBIM) will vote on a director election at a US company. "
        "You are given NBIM's own voting rules, facts about the nominee and the board taken from the company's proxy "
        "statement, and NBIM's record: how it voted on this nominee before, and how often it has actually followed each "
        "rule that applies. NBIM supports the board on about 95 percent of director elections. Its written rules are not "
        "always its practice, so weigh the record.\n"
        "Reply with one JSON object and nothing else: {\"probability_against\": <0-100>, \"rule\": \"<rule id or none>\", "
        "\"reason\": \"<one sentence>\"}\n\nNBIM's rules on directors:\n" + rules)


def director_state(r, d):
    """What the judge is told about one US director nominee. `r` is the vote-file row with the history
    model's "same item last time"; `d` is the row from board_rules.load_scored(). None if the proxy was not read."""
    n, b = d["n"], d["b"]
    if not n or not n["found"]:
        return None
    v = br.val
    others = v(n, "other_public_boards")
    return {
        "board_recommendation": r["mgmt_rec"],
        "facts": {
            "independent": v(n, "independent"), "executive_of_this_company": br.is_executive(n), "ceo": v(n, "ceo"),
            "board_chair": v(n, "board_chair"), "founder_of_this_company": "yes" if br.is_founder(n) else "no",
            "audit_committee": v(n, "audit_committee"), "pay_committee": v(n, "pay_committee"),
            "nomination_committee": v(n, "nomination_committee"),
            "other_listed_boards": None if others is None else len(others), "chairs_another_board": v(n, "chairs_other_board"),
            "full_time_executive_elsewhere": v(n, "executive_elsewhere"),
            "attended_under_75_percent": v(n, "attended_under_75_pct"),
            "board": {"size": v(b, "board_size"), "independent": v(b, "independent_directors"), "women": v(b, "women_directors"),
                      "controlled_company": v(b, "controlled_company"), "classified_board": v(b, "classified_board"),
                      "support_at_last_pay_vote_percent": v(b, "prior_pay_support_pct")},
        },
        "nbim_record": {
            "nbim_vote_on_this_nominee_last_time": {1: "against the board", 0: "with the board", None: "no earlier vote"}[r["prev_same_item"]],
            "rules_that_apply": [{"rule": g["name"], "what": g["text"][:160], "nbim_followed_it_at_earlier_meetings": g["record"]}
                                 for g in d["signals"]],
            "notes": [t for _, t, _ in d["notes"]][:4],
        },
    }


def request_body(state):
    return {"model": MODEL, "max_tokens": 300, "usage": {"include": True}, "reasoning": {"enabled": False},
            "messages": [{"role": "system", "content": system_prompt()},
                         {"role": "user", "content": json.dumps(state, ensure_ascii=False, sort_keys=True)}]}


def state_key(key, state):
    return key + ":" + hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def load_cache():
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                cache[rec["key"]] = rec
    return cache


def parse(reply):
    """(probability, rule, reason) or None if the reply does not fit the form."""
    m = re.search(r"\{.*\}", reply or "", re.S)
    try:
        ans = json.loads(m.group(0))
        p = float(ans["probability_against"]) / 100
    except (AttributeError, ValueError, KeyError, TypeError):
        return None
    if not 0 <= p <= 1:
        return None
    return p, str(ans.get("rule") or "none")[:20], str(ans.get("reason") or "")[:300]


def director_rows(up_to):
    """(vote-file row, facts row, state) for every US director nominee up to a year, each year scored
    with the history frozen before it."""
    rows = bm.read_votes(VOTES)
    directors = {(r["meeting_id"], r["item_no"]): r for r in br.load_scored()}
    out = []
    for year in sorted({int(r["meeting_date"][:4]) for r in rows}):
        if year > up_to or year < 2021:
            continue
        _, test, _, _ = bm.run_year(rows, year)
        for r in test:
            d = directors.get((r["meeting_id"], r["item_no"]))
            state = director_state(r, d) if d else None
            if state:
                out.append((r, d, state))
    return out


def answer_for(key, state, cache):
    rec = cache.get(state_key(key, state))
    return rec["p"] if rec else None


def fill(up_to):
    cache = load_cache()
    todo = [(r, s) for r, _, s in director_rows(up_to) if state_key(f"{r['meeting_id']}-{r['item_no']}", s) not in cache]
    print(f"{len(cache)} answers cached, {len(todo)} proposals to ask about (up to {up_to})")
    key = rc.api_key()
    if todo and not key:
        raise SystemExit("No OPENROUTER_API_KEY in .env")
    lock, spent, done = threading.Lock(), [0.0], [0]

    def work(item):
        r, state = item
        if spent[0] > SPEND_LIMIT:
            return
        try:
            reply = call_model(request_body(state), key)
        except RuntimeError as e:
            print("  call failed:", str(e)[:120], flush=True)
            return
        got = parse(reply["choices"][0]["message"]["content"])
        with lock:
            spent[0] += (reply.get("usage") or {}).get("cost") or 0.0
            if got:
                rec = {"key": state_key(f"{r['meeting_id']}-{r['item_no']}", state), "p": got[0], "rule": got[1], "reason": got[2], "model": MODEL}
                with open(CACHE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
                done[0] += 1

    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        list(pool.map(work, todo))
    print(f"{done[0]} new answers, ${spent[0]:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill", type=int, default=0, help="ask the judge about every proposal up to this year that has no answer")
    a = ap.parse_args()
    if a.fill:
        fill(a.fill)
        return
    cache = load_cache()
    items = [(r, s) for r, _, s in director_rows(2026)]
    scored = [(r, answer_for(f"{r['meeting_id']}-{r['item_no']}", s, cache)) for r, s in items]
    scored = [(r, p) for r, p in scored if p is not None]
    print(f"US director nominees 2021-2026 with proxy facts: {len(items)}. Judged: {len(scored)}.\n")
    print("1. What the judge's probability means (all judged nominees)")
    out = []
    for label, lo, hi in (("under 5%", 0, .05), ("5% to under 20%", .05, .2), ("20% to under 50%", .2, .5), ("50% or more", .5, 1.01)):
        for period, keep in (("2021-2025", lambda y: y <= "2025"), ("2026", lambda y: y == "2026")):
            g = [r for r, p in scored if lo <= p < hi and keep(r["meeting_date"][:4])]
            if g:
                out.append([label, period, len(g), sum(r["y"] for r in g), f"{sum(r['y'] for r in g) / len(g):.0%}"])
    bm.table(["The judge says", "Years", "Nominees", "NBIM against", "Share"], out)

    print("\n2. Ranking of US director nominees, by year (AP = average precision; history = the history model alone)")
    out = []
    for year in sorted({r["meeting_date"][:4] for r, _ in scored}):
        g = [(r, p) for r, p in scored if r["meeting_date"][:4] == year]
        ys = [r["y"] for r, _ in g]
        if sum(ys):
            k = max(1, round(0.2 * len(g)))
            top = lambda sc: sum(ys[i] for i in sorted(range(len(g)), key=lambda i: -sc[i])[:k])
            pj, ph = [p for _, p in g], [r["p"] for r, _ in g]
            out.append([year, len(g), sum(ys), f"{bm.average_precision(ph, ys):.3f}", f"{bm.average_precision(pj, ys):.3f}",
                        f"{top(ph)}/{sum(ys)}", f"{top(pj)}/{sum(ys)}"])
    bm.table(["Year", "Nominees", "Against", "AP history", "AP judge", "History: in the top fifth", "Judge: in the top fifth"], out)
    print("   How the judge's probability is used, and what it adds to the whole pipeline, is in src/agent/combined_model.py.")


if __name__ == "__main__":
    main()
