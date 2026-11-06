"""Fetch the Japanese companies' filings from EDINET, the Japanese Financial Services Agency's filing system.

Run from the repository root. Needs EDINET_API_KEY in .env (free, https://api.edinet-fsa.go.jp).
    python -m nbim_vote.fetch_edinet index      # list every filing by these companies, one request per day
    python -m nbim_vote.fetch_edinet download   # download the annual and extraordinary reports found

What is kept
    120  annual securities report (yuho): directors, with outside and independent ones marked
    130  amended annual report
    180  extraordinary report: after a general meeting, the vote count for every item
EDINET only keeps extraordinary reports for a limited time: none are listed before mid-2024.

Output, all in data/evidence/edinet/
    companies.csv   which company in the vote file is which EDINET filer
    filings.csv     one row per filing kept
    days_done.txt   days already indexed, so an interrupted run can continue
    docs/<docID>_<type>.zip   the documents (type 5 = XBRL as CSV, type 1 = the full filing)

Both steps can be interrupted and started again.
"""

import argparse
import csv
import datetime
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "evidence" / "edinet"
VOTES = ROOT / "data" / "dirty" / "real_votes.csv"
API = "https://api.edinet-fsa.go.jp/api/v2"
KEEP = {"120", "130", "180"}
FIRST_DAY = datetime.date(2018, 6, 1)
HEADERS = {"User-Agent": "NBIM hackathon research"}
FIELDS = ["docID", "edinetCode", "secCode", "filerName", "docTypeCode", "docDescription", "periodStart", "periodEnd",
          "submitDateTime", "xbrlFlag", "pdfFlag", "withdrawalStatus"]


def key():
    load_dotenv(ROOT / ".env")
    value = os.environ.get("EDINET_API_KEY")
    if not value:
        raise SystemExit("Set EDINET_API_KEY in .env.")
    return value


def get(url, params, attempts=5):
    for attempt in range(attempts):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=120)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    raise SystemExit(f"EDINET failed for {url}")


def simplify(name):
    return re.sub(r"[^A-Z]", "", name.upper().replace("CORPORATION", "").replace("CORP", "").replace("CO", "").replace("LTD", "").replace("INC", ""))


def companies():
    """Vote-file company -> EDINET code, matched on securities code. Three-digit tickers in the vote file
    have lost their last digit, so those are matched on the first three digits and the English name."""
    votes = {}
    with open(VOTES, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["country"] == "Japan":
                votes.setdefault(r["company_id"], (r["company"], r["ticker"].strip()))
    with open(OUT / "EdinetcodeDlInfo.csv", encoding="utf-8") as f:
        code = [row for row in csv.reader(f)][2:]
    code = [row for row in code if len(row) >= 12 and row[11].strip()]
    out = []
    for company_id, (name, ticker) in sorted(votes.items()):
        hits = [row for row in code if row[11].strip()[:4] == ticker[:4]] if len(ticker) == 4 else \
               [row for row in code if row[11].strip()[:3] == ticker and simplify(row[7])[:5] == simplify(name)[:5]]
        out.append({"company_id": company_id, "company": name, "ticker": ticker,
                    "edinet_code": hits[0][0] if len(hits) == 1 else "", "edinet_name": hits[0][7] if len(hits) == 1 else "",
                    "status": "ok" if len(hits) == 1 else f"{len(hits)} candidates"})
    with open(OUT / "companies.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    return out


def index(api_key, workers=4):
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = {c["edinet_code"] for c in companies() if c["edinet_code"]}
    done_path, filings_path = OUT / "days_done.txt", OUT / "filings.csv"
    done = set(done_path.read_text().split()) if done_path.exists() else set()
    days, day = [], FIRST_DAY
    while day <= datetime.date.today():
        if day.isoformat() not in done:
            days.append(day.isoformat())
        day += datetime.timedelta(days=1)

    def fetch(d):
        results = get(f"{API}/documents.json", {"date": d, "type": 2, "Subscription-Key": api_key}).json().get("results") or []
        return d, [doc for doc in results if doc.get("edinetCode") in wanted and doc.get("docTypeCode") in KEEP]

    new_file = not filings_path.exists()
    kept = 0
    with open(filings_path, "a", encoding="utf-8", newline="") as f, open(done_path, "a") as log, \
            ThreadPoolExecutor(max_workers=workers) as pool:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for n, (d, docs) in enumerate(pool.map(fetch, days), 1):
            w.writerows(docs)
            kept += len(docs)
            f.flush()
            log.write(d + "\n")
            log.flush()
            if n % 200 == 0:
                print(f"  {n}/{len(days)} days, {kept} filings kept", flush=True)
    print(f"Indexed {len(days)} days. Filings kept this run: {kept}.")


def read_filings():
    """filings.csv without duplicates: an interrupted index can write a day twice."""
    with open(OUT / "filings.csv", encoding="utf-8", newline="") as f:
        return list({r["docID"]: r for r in csv.DictReader(f)}.values())


def download(api_key):
    docs = OUT / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    filings = read_filings()
    count = 0
    for doc in filings:
        if doc["withdrawalStatus"] not in ("0", ""):
            continue
        types = ["5"] if doc["docTypeCode"] in ("120", "130") and doc["xbrlFlag"] == "1" else ["1"]
        for t in types:
            path = docs / f"{doc['docID']}_{t}.zip"
            if path.exists():
                continue
            r = get(f"{API}/documents/{doc['docID']}", {"type": t, "Subscription-Key": api_key})
            if r.headers.get("content-type", "").startswith("application/json"):
                print("  not available:", doc["docID"], doc["docTypeCode"], t)
                continue
            path.write_bytes(r.content)
            count += 1
            time.sleep(0.1)
    print(f"Downloaded {count} documents to {docs.relative_to(ROOT)}.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("index", "download"))
    a = p.parse_args()
    {"index": index, "download": download}[a.step](key())


if __name__ == "__main__":
    main()
