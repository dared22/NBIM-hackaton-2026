"""evidence.judge: NBIM voting decision support."""

import concurrent.futures
import hashlib
import json
import re
import threading

from src import data as paths
from src.data import read_records
from src.evidence import rule_check as rc
from src.evidence.http import call_model
from src.models import history as bm
from src.rules import board as br

VOTES = paths.VOTES
CACHE = paths.JUDGE
MODEL = "anthropic/claude-haiku-5.5"
DIRECTOR_SECTIONS = ("1.1", "1.2", "1.3", "2.1", "2.3", "3.2")
SPEND_LIMIT = 2.0  # dollars per run


def system_prompt():
    with open(rc.GUIDELINES, encoding="utf-8") as f:
        g = json.load(f)
    rules = "\n".join(
        f"[{r['id']}] {r['tekst']}" for r in g["regler"] if r["underseksjon"] in DIRECTOR_SECTIONS
    )
    return (
        "You estimate how Norges Bank Investment Management (NBIM) will vote on a director election at a US company. "
        "You are given NBIM's own voting rules, facts about the nominee and the board taken from the company's proxy "
        "statement, and NBIM's record: how it voted on this nominee before, and how often it has actually followed each "
        "rule that applies. NBIM supports the board on about 95 percent of director elections. Its written rules are not "
        "always its practice, so weigh the record.\n"
        'Reply with one JSON object and nothing else: {"probability_against": <0-100>, "rule": "<rule id or none>", '
        '"reason": "<one sentence>"}\n\nNBIM\'s rules on directors:\n' + rules
    )


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
            "independent": v(n, "independent"),
            "executive_of_this_company": br.is_executive(n),
            "ceo": v(n, "ceo"),
            "board_chair": v(n, "board_chair"),
            "founder_of_this_company": "yes" if br.is_founder(n) else "no",
            "audit_committee": v(n, "audit_committee"),
            "pay_committee": v(n, "pay_committee"),
            "nomination_committee": v(n, "nomination_committee"),
            "other_listed_boards": None if others is None else len(others),
            "chairs_another_board": v(n, "chairs_other_board"),
            "full_time_executive_elsewhere": v(n, "executive_elsewhere"),
            "attended_under_75_percent": v(n, "attended_under_75_pct"),
            "board": {
                "size": v(b, "board_size"),
                "independent": v(b, "independent_directors"),
                "women": v(b, "women_directors"),
                "controlled_company": v(b, "controlled_company"),
                "classified_board": v(b, "classified_board"),
                "support_at_last_pay_vote_percent": v(b, "prior_pay_support_pct"),
            },
        },
        "nbim_record": {
            "nbim_vote_on_this_nominee_last_time": {
                1: "against the board",
                0: "with the board",
                None: "no earlier vote",
            }[r["prev_same_item"]],
            "rules_that_apply": [
                {
                    "rule": g["name"],
                    "what": g["text"][:160],
                    "nbim_followed_it_at_earlier_meetings": g["record"],
                }
                for g in d["signals"]
            ],
            "notes": [t for _, t, _ in d["notes"]][:4],
        },
    }


def request_body(state):
    return {
        "model": MODEL,
        "max_tokens": 300,
        "usage": {"include": True},
        "reasoning": {"enabled": False},
        "messages": [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": json.dumps(state, ensure_ascii=False, sort_keys=True)},
        ],
    }


def state_key(key, state):
    return (
        key
        + ":"
        + hashlib.sha256(
            json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
    )


def load_cache():
    return read_records(CACHE, lambda r: r["key"])


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


def fill(up_to):
    cache = load_cache()
    todo = [
        (r, s)
        for r, _, s in director_rows(up_to)
        if state_key(f"{r['meeting_id']}-{r['item_no']}", s) not in cache
    ]
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
                rec = {
                    "key": state_key(f"{r['meeting_id']}-{r['item_no']}", state),
                    "p": got[0],
                    "rule": got[1],
                    "reason": got[2],
                    "model": MODEL,
                }
                with open(CACHE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
                done[0] += 1

    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        list(pool.map(work, todo))
    print(f"{done[0]} new answers, ${spent[0]:.2f}")
