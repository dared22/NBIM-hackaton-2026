"""Read pay figures straight from each meeting's own proxy statement.

Run from the repo root (needs internet, about 20-30 minutes for everything):
    python3 src/agent/fetch_proxy_pay.py              # all meetings, resumes if stopped
    python3 src/agent/fetch_proxy_pay.py --limit 20   # quick test on 20 meetings

Why: the SEC's XBRL API drops a pay figure when the company tags it per named
CEO, and it only exposes each company's newest filing. The proxy statement
itself carries the tagged "pay versus performance" table for every company
that must publish one, and it has a filing date we can check against the
meeting date.

For each company meeting in data/dirty/nbim_pay_votes.csv
    1. Look up the company's filings (data.sec.gov/submissions).
    2. Pick the last definitive proxy filed 1-120 days before the meeting.
       A proxy filed on or after the meeting date is never used.
    3. Download it and read the machine-readable tags (inline XBRL, "ecd:"
       names). No AI model and no free-text guessing.
    4. Keep the tagged numbers, drop the document.

Output
    data/evidence/proxy_pay.csv       one row per tagged figure: meeting, filing,
                             filing date, tag, fiscal year, named CEO, value
    data/evidence/proxy_meetings.csv  one row per meeting: which filing was used, or why
                             none was found

Scope: US filers only. Every company in data/dirty/nbim_pay_votes.csv files a US
proxy, because the file only holds votes required by US rules.

The SEC asks for a contact address in the User-Agent. It is read from
startpakke/case1_stemmegivning/hent_npx.py.
"""

import argparse
import collections
import concurrent.futures
import csv
import datetime
import gzip
import html
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "startpakke", "case1_stemmegivning"))
from hent_npx import USER_AGENT  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "nbim_pay_votes.csv")
LINK = os.path.join(ROOT, "data", "evidence", "pay_company_link.csv")
OUT_PAY = os.path.join(ROOT, "data", "evidence", "proxy_pay.csv")
OUT_MEET = os.path.join(ROOT, "data", "evidence", "proxy_meetings.csv")

PROXY_FORMS = ["DEF 14A", "DEFR14A", "DEFC14A", "DEFM14A"]  # in order of preference
MAX_DAYS_BEFORE = 120
TAGS = {"PeoTotalCompAmt", "PeoActuallyPaidCompAmt", "NonPeoNeoAvgTotalCompAmt",
        "TotalShareholderRtnAmt", "PeerGroupTotalShareholderRtnAmt"}
PAY_COLS = ["cik", "meeting_date", "accession", "form", "filed", "tag", "period_start", "period_end", "person", "value"]
MEET_COLS = ["cik", "meeting_date", "status", "accession", "form", "filed", "url", "figures"]


def get(url, tries=5):
    """GET with the SEC's required User-Agent, gzip to keep downloads small. Returns (status, bytes)."""
    for attempt in range(tries):
        time.sleep(0.5)  # 5 workers x 0.5 s keeps us at or under 10 requests a second
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return 200, raw
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, b""
            if attempt == tries - 1:
                return e.code, b""
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == tries - 1:
                return 0, b""
        time.sleep(2.0 * (attempt + 1))


def company_filings(cik, earliest):
    """All proxy filings of a company as (filed, form, accession, document), newest first."""
    status, raw = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    if status != 200:
        return None
    data = json.loads(raw)
    blocks = [data["filings"]["recent"]]
    # Very active filers keep only their newest filings in "recent".
    for extra in data["filings"].get("files", []):
        if extra.get("filingTo", "9999") >= earliest:
            status, raw = get("https://data.sec.gov/submissions/" + extra["name"])
            if status == 200:
                blocks.append(json.loads(raw))
    out = []
    for b in blocks:
        for form, filed, acc, doc in zip(b["form"], b["filingDate"], b["accessionNumber"], b["primaryDocument"]):
            if form in PROXY_FORMS and doc:
                out.append((filed, form, acc, doc))
    return sorted(set(out), reverse=True)


def pick_proxy(filings, meeting_date):
    """Last proxy filed 1 to MAX_DAYS_BEFORE days before the meeting, preferring DEF 14A."""
    day = datetime.date.fromisoformat(meeting_date)
    first = (day - datetime.timedelta(days=MAX_DAYS_BEFORE)).isoformat()
    last = (day - datetime.timedelta(days=1)).isoformat()
    window = [f for f in filings if first <= f[0] <= last]
    for form in PROXY_FORMS:
        hits = [f for f in window if f[1] == form]
        if hits:
            return hits[0]
    return None


def number(text, attrs):
    """Turn the displayed text of a tagged figure into a number, or None."""
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ").strip()
    fmt = attrs.get("format", "")
    dash = text in ("-", "—", "–")
    if "zerodash" in fmt or "fixed-zero" in fmt or dash:
        return 0.0
    if not text:
        return None
    negative = attrs.get("sign") == "-" or (text.startswith("(") and text.endswith(")"))
    digits = re.sub(r"[^\d.,]", "", text)
    if "comma-decimal" in fmt or "numcommadot" in fmt:
        digits = digits.replace(".", "").replace(",", ".")
    else:
        digits = digits.replace(",", "")
    try:
        value = float(digits) * 10 ** int(attrs.get("scale", "0") or 0)
    except ValueError:
        return None
    return -value if negative else value


def read_tags(doc):
    """Tagged pay figures in a proxy: (tag, period_start, period_end, person, value)."""
    text = doc.decode("utf-8", errors="replace")
    contexts = {}
    for cid, body in re.findall(r"<(?:xbrli:)?context\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</(?:xbrli:)?context>", text, re.S):
        start = re.search(r"<(?:xbrli:)?startDate>\s*([\d-]+)", body)
        end = re.search(r"<(?:xbrli:)?(?:endDate|instant)>\s*([\d-]+)", body)
        members = re.findall(r"<(?:xbrldi:)?explicitMember[^>]*dimension=\"([^\"]+)\"[^>]*>\s*([^<\s]+)", body)
        contexts[cid] = (start.group(1) if start else "", end.group(1) if end else "", members)
    out = set()
    for attr_text, inner in re.findall(r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", text, re.S):
        attrs = dict(re.findall(r"([\w:-]+)=\"([^\"]*)\"", attr_text))
        tag = attrs.get("name", "").split(":")[-1]
        if not attrs.get("name", "").startswith("ecd:") or tag not in TAGS:
            continue
        start, end, members = contexts.get(attrs.get("contextRef", ""), ("", "", []))
        # Keep plain figures and figures split per named person; skip other breakdowns.
        if any(not dim.endswith("IndividualAxis") for dim, _ in members):
            continue
        value = number(inner, attrs)
        if value is not None and end:
            out.add((tag, start, end, members[0][1].split(":")[-1] if members else "", value))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only about N meetings, spread over the list (test run)")
    a = ap.parse_args()

    link = {}
    with open(LINK, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] == "linked":
                link[r["cusip"]] = int(r["cik"])
    meetings = collections.defaultdict(set)
    with open(VOTES, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["cusip"] in link:
                meetings[link[r["cusip"]]].add(r["moetedato"])

    done = set()
    if os.path.exists(OUT_MEET) and not a.limit:
        with open(OUT_MEET, encoding="utf-8", newline="") as f:
            done = {(int(r["cik"]), r["meeting_date"]) for r in csv.DictReader(f) if r["status"] != "download failed"}
    todo = sorted((cik, d) for cik, ds in meetings.items() for d in ds if (cik, d) not in done)
    if a.limit:
        todo = todo[:: max(1, len(todo) // a.limit)][:a.limit]
    by_cik = collections.defaultdict(list)
    for cik, d in todo:
        by_cik[cik].append(d)
    print(f"{sum(len(v) for v in meetings.values())} company meetings, {len(done)} already done, {len(todo)} to fetch")
    if not todo:
        return

    pay_path, meet_path = (OUT_PAY, OUT_MEET) if not a.limit else (OUT_PAY + ".test", OUT_MEET + ".test")
    mode = "a" if done else "w"
    pay_file = open(pay_path, mode, newline="", encoding="utf-8")
    meet_file = open(meet_path, mode, newline="", encoding="utf-8")
    pay_out, meet_out = csv.writer(pay_file), csv.writer(meet_file)
    if mode == "w":
        pay_out.writerow(PAY_COLS)
        meet_out.writerow(MEET_COLS)
    lock, count, started, status_count = threading.Lock(), [0], time.time(), collections.Counter()
    earliest = (datetime.date.fromisoformat(min(d for _, d in todo)) - datetime.timedelta(days=MAX_DAYS_BEFORE)).isoformat()

    def work(item):
        cik, dates = item
        filings = company_filings(cik, earliest)
        for d in sorted(dates):
            row, facts = [cik, d, "", "", "", "", "", 0], []
            if filings is None:
                row[2] = "download failed"
            else:
                pick = pick_proxy(filings, d)
                if not pick:
                    row[2] = "no proxy filed 1-120 days before the meeting"
                else:
                    filed, form, acc, doc = pick
                    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
                    status, raw = get(url)
                    if status != 200:
                        row[2:7] = ["download failed", acc, form, filed, url]
                    else:
                        facts = read_tags(raw)
                        row[2:8] = ["ok" if facts else "proxy has no tagged pay table", acc, form, filed, url, len(facts)]
            with lock:
                meet_out.writerow(row)
                for tag, start, end, person, value in facts:
                    pay_out.writerow([cik, d, row[3], row[4], row[5], tag, start, end, person, f"{value:.0f}"])
                status_count[row[2]] += 1
                count[0] += 1
                if count[0] % 250 == 0:
                    pay_file.flush()
                    meet_file.flush()
                    print(f"  {count[0]}/{len(todo)} meetings, {time.time() - started:.0f}s", flush=True)

    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        list(pool.map(work, by_cik.items()))
    pay_file.close()
    meet_file.close()
    print(f"\nFetched {count[0]} meetings in {time.time() - started:.0f}s -> {os.path.relpath(meet_path, ROOT)}")
    for status, n in status_count.most_common():
        print(f"  {n:5d}  {status}")


if __name__ == "__main__":
    main()
