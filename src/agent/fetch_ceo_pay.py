"""Fetch CEO pay for the companies in NBIM's pay votes, with filing dates.

Run from the repo root (takes about 6 minutes, needs internet):
    python3 src/agent/fetch_ceo_pay.py

Source: SEC EDGAR XBRL API, https://data.sec.gov/api/xbrl/companyconcept/
Since 2023 US proxy statements must tag a "pay versus performance" table.
Two tags are fetched per company:
    PeoTotalCompAmt            total pay of the CEO (principal executive officer)
    NonPeoNeoAvgTotalCompAmt   average total pay of the other named executives

Every fact keeps the date it was filed, so the pay model can use only
figures that were public before the meeting.

Steps
    1. Link each company name in data/dirty/nbim_pay_votes.csv to an SEC company
       number (CIK). Only exact matches after normalising the name; names that
       match more than one company are skipped, not guessed.
    2. Download the two tags for each linked company.
    3. Write data/evidence/ceo_pay.csv (one row per fact) and data/evidence/pay_company_link.csv
       (which name was linked to which CIK, or why not).

The SEC asks for a contact address in the User-Agent. It is read from
startpakke/case1_stemmegivning/hent_npx.py.
"""

import collections
import concurrent.futures
import csv
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
OUT_PAY = os.path.join(ROOT, "data", "evidence", "ceo_pay.csv")
OUT_LINK = os.path.join(ROOT, "data", "evidence", "pay_company_link.csv")
TAGS = ["PeoTotalCompAmt", "NonPeoNeoAvgTotalCompAmt"]
FORMS = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
         "LLC", "LP", "THE", "HOLDINGS", "HOLDING", "GROUP", "NV", "SA", "AG", "TRUST", "AND", "OF",
         "NEW", "DE", "MD", "COM"}


def normalise(name):
    name = name.upper().replace("&", " AND ").replace("’", "'")
    words = re.sub(r"[^A-Z0-9 ]", " ", name).split()
    return " ".join(w for w in words if w not in FORMS)


def get(url, tries=5):
    """GET with the SEC's required User-Agent. Returns (status, bytes)."""
    for attempt in range(tries):
        time.sleep(0.5)  # 5 workers x 0.5 s keeps us at or under 10 requests a second
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return 200, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, b""
            if attempt == tries - 1:
                return e.code, b""
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries - 1:
                return 0, b""
        time.sleep(2.0 * (attempt + 1))


def sec_names():
    """Normalised company name -> set of (cik, SEC name), from two SEC lists."""
    names = collections.defaultdict(set)
    status, raw = get("https://www.sec.gov/files/company_tickers.json")
    if status != 200:
        raise SystemExit(f"Could not fetch the SEC company list (HTTP {status})")
    for c in json.loads(raw).values():
        names[normalise(c["title"])].add((int(c["cik_str"]), c["title"]))
    # Companies that filed a pay table but are no longer listed (merged, delisted).
    for year in (2022, 2023, 2024, 2025):
        status, raw = get(f"https://data.sec.gov/api/xbrl/frames/ecd/PeoTotalCompAmt/USD/CY{year}.json")
        if status == 200:
            for d in json.loads(raw)["data"]:
                names[normalise(d["entityName"])].add((int(d["cik"]), d["entityName"]))
    return names


def main():
    with open(VOTES, encoding="utf-8", newline="") as f:
        issuers = {}
        for r in csv.DictReader(f):
            issuers.setdefault(r["cusip"], r["utsteder"])
    print(f"{len(issuers)} companies in {os.path.relpath(VOTES, ROOT)}")

    names = sec_names()
    links, ciks = [], {}
    for cusip, name in sorted(issuers.items()):
        hits = {cik for cik, _ in names.get(normalise(name), ())}
        if len(hits) == 1:
            cik = next(iter(hits))
            sec_name = next(n for c, n in names[normalise(name)] if c == cik)
            links.append([cusip, name, cik, sec_name, "linked"])
            ciks[cik] = sec_name
        else:
            links.append([cusip, name, "", "", "no match" if not hits else "ambiguous name"])
    print(f"Linked {sum(1 for l in links if l[4] == 'linked')} companies to {len(ciks)} SEC company numbers; "
          f"{sum(1 for l in links if l[4] == 'no match')} no match, "
          f"{sum(1 for l in links if l[4] == 'ambiguous name')} ambiguous")

    jobs = [(cik, tag) for cik in sorted(ciks) for tag in TAGS]
    facts, status_count, lock, done, started = [], collections.Counter(), threading.Lock(), [0], time.time()

    def work(job):
        cik, tag = job
        status, raw = get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/ecd/{tag}.json")
        rows = []
        if status == 200:
            for d in json.loads(raw).get("units", {}).get("USD", []):
                rows.append([cik, ciks[cik], tag, d.get("start", ""), d["end"], d["val"],
                             d.get("form", ""), d.get("filed", ""), d.get("accn", "")])
        with lock:
            facts.extend(rows)
            status_count[(tag, status if status != 200 or rows else "200 but empty")] += 1
            done[0] += 1
            if done[0] % 500 == 0:
                print(f"  {done[0]}/{len(jobs)} requests, {time.time() - started:.0f}s", flush=True)

    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        list(pool.map(work, jobs))

    facts.sort(key=lambda r: (r[0], r[2], r[4], r[7]))
    with open(OUT_PAY, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cik", "sec_name", "tag", "period_start", "period_end", "value_usd", "form", "filed", "accession"])
        w.writerows(facts)
    with open(OUT_LINK, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cusip", "name_in_votes", "cik", "sec_name", "status"])
        w.writerows(links)

    print(f"\nWrote {len(facts)} facts to {os.path.relpath(OUT_PAY, ROOT)} in {time.time() - started:.0f}s")
    for (tag, status), n in sorted(status_count.items(), key=str):
        print(f"  {tag}: HTTP {status}: {n} companies")
    with_pay = len({r[0] for r in facts if r[2] == TAGS[0]})
    print(f"Companies with at least one CEO pay figure: {with_pay} of {len(ciks)} linked, {len(issuers)} in total")


if __name__ == "__main__":
    main()
