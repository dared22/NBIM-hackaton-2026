"""Read two things from the text of each proxy that are not in the tagged table:
last year's shareholder support for pay, and mentions of one-off awards.

Run from the repo root (needs internet, about 15 minutes, resumes if stopped):
    python3 src/agent/fetch_proxy_text.py
    python3 src/agent/fetch_proxy_text.py --limit 30   # quick test

Why
    NBIM says it votes against pay packages that "include substantial one-off
    awards" and packages that are "not appropriately adjusted by the board in
    response to shareholder concerns raised in previous years" (voting review,
    first half 2025; guideline rules 3.3.5 and 3.3.6). ISS lists the same two
    points in its qualitative review. Neither is in the tagged pay table.

What is read, with plain pattern matching (no AI model)
    1. Prior support: the first percentage that appears in a sentence about
       "say-on-pay" or the "advisory vote", within 80 characters of "votes
       cast", "approved", "support" or "in favor". The sentence is kept with
       it, so a person can check it.
    2. One-off awards: how many times the proxy uses words such as "one-time
       award", "special award", "retention award", "sign-on", "inducement",
       "make-whole", "severance" and "accelerated vesting", per 100,000
       characters of text.

The same proxies as fetch_proxy_pay.py are used (data/evidence/proxy_meetings.csv),
so every document was filed before its meeting.

Output: data/evidence/proxy_text.csv
"""

import argparse
import concurrent.futures
import csv
import html
import os
import re
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from fetch_proxy_pay import get  # noqa: E402

MEET = os.path.join(ROOT, "data", "evidence", "proxy_meetings.csv")
OUT = os.path.join(ROOT, "data", "evidence", "proxy_text.csv")
COLS = ["cik", "meeting_date", "status", "chars", "prior_support", "prior_support_sentence",
        "one_off_per_100k", "one_time", "special_award", "retention", "sign_on", "severance", "accelerated"]

TOPIC = re.compile(r"say[- ]on[- ]pay|advisory vote|advisory (?:basis|resolution)|executive compensation program", re.I)
RESULT = re.compile(r"votes? cast|approv|support|in favor|voted for", re.I)
PERCENT = re.compile(r"(\d{2,3}(?:\.\d+)?)\s?(?:%|percent)")
WORDS = {
    "one_time": r"one[- ]time (?:\w+ ){0,3}(?:award|grant|bonus|payment)|special one[- ]time",
    "special_award": r"special (?:\w+ ){0,2}(?:award|grant|bonus)|mega[- ]grant|front[- ]loaded",
    "retention": r"retention (?:\w+ ){0,2}(?:award|grant|bonus)",
    "sign_on": r"sign[- ]on|inducement (?:award|grant)|make[- ]whole|new[- ]hire (?:award|grant)",
    "severance": r"severance (?:payment|benefit|agreement)|separation (?:payment|agreement)",
    "accelerated": r"accelerat\w+ (?:of )?(?:the )?vesting|vesting (?:\w+ ){0,3}accelerat",
}


def plain(doc):
    text = doc.decode("utf-8", errors="replace")
    text = re.sub(r"<(script|style|ix:header)\b.*?</\1>", " ", text, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text)


def prior_support(text):
    """First support percentage stated right next to a say-on-pay result, with its sentence.

    The percentage must sit within 80 characters of a result word ("votes cast",
    "approved", "support", "in favor"), which skips thresholds such as "a
    majority (50%)" elsewhere in the sentence.
    """
    for sentence in re.split(r"(?<=[.;])\s", text):
        if len(sentence) > 600 or not TOPIC.search(sentence):
            continue
        marks = [m.start() for m in RESULT.finditer(sentence)]
        for m in PERCENT.finditer(sentence):
            value = float(m.group(1))
            if 20 <= value <= 100 and any(abs(m.start() - k) <= 80 for k in marks):
                return value, sentence.strip()[:300]
    return None


def read(doc):
    text = plain(doc)
    counts = {name: len(re.findall(rx, text, re.I)) for name, rx in WORDS.items()}
    support = prior_support(text)
    return [len(text), f"{support[0]:g}" if support else "", support[1] if support else "",
            f"{sum(counts.values()) * 100000 / max(len(text), 1):.2f}"] + [counts[k] for k in WORDS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    with open(MEET, encoding="utf-8", newline="") as f:
        meetings = [r for r in csv.DictReader(f) if r["url"]]
    done = set()
    if os.path.exists(OUT) and not a.limit:
        with open(OUT, encoding="utf-8", newline="") as f:
            done = {(r["cik"], r["meeting_date"]) for r in csv.DictReader(f) if r["status"] == "ok"}
    todo = [m for m in meetings if (m["cik"], m["meeting_date"]) not in done]
    if a.limit:
        todo = todo[:: max(1, len(todo) // a.limit)][:a.limit]
    print(f"{len(meetings)} proxies, {len(done)} already read, {len(todo)} to fetch")
    if not todo:
        return
    path = OUT if not a.limit else OUT + ".test"
    out_file = open(path, "a" if done else "w", newline="", encoding="utf-8")
    out = csv.writer(out_file)
    if not done:
        out.writerow(COLS)
    lock, count, started = threading.Lock(), [0], time.time()

    def work(m):
        status, raw = get(m["url"])
        row = [m["cik"], m["meeting_date"]] + (["ok"] + read(raw) if status == 200 else ["download failed"] + [""] * 10)
        with lock:
            out.writerow(row)
            count[0] += 1
            if count[0] % 250 == 0:
                out_file.flush()
                print(f"  {count[0]}/{len(todo)} proxies, {time.time() - started:.0f}s", flush=True)

    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        list(pool.map(work, todo))
    out_file.close()
    print(f"Read {count[0]} proxies in {time.time() - started:.0f}s -> {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
