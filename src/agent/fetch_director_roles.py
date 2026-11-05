"""Fetch who is a director or officer of which US company, and with what title.

Run from the repo root (needs internet, about 5 minutes):
    python3 src/agent/fetch_director_roles.py

Source: the SEC's Insider Transactions Data Sets, one file per quarter,
    https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/<year>q<n>_form345.zip
Directors and officers of US-listed companies must report their shareholdings
(Forms 3, 4 and 5). Each report states the person, the company, whether the
person is a director or an officer, and the officer's title. It is structured
data, so no AI model is needed to read it.

What is kept
    Every report by a person who has ever reported at one of the US companies
    in data/dirty/real_votes.csv, at any company. Reports at other companies
    are needed to count how many boards a person sits on.

Output
    data/evidence/director_roles.csv        one row per person, company, month,
                                            role and title
    data/evidence/director_issuer_link.csv  which company in the vote file was
                                            linked to which SEC company number

Companies are linked by name, not by ticker: several tickers in the vote file
belong to other companies (BLK is BlackRock, not Blackbaud).
"""

import collections
import csv
import datetime
import io
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from fetch_proxy_pay import get  # noqa: E402

VOTES = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
OUT_ROLES = os.path.join(ROOT, "data", "evidence", "director_roles.csv")
OUT_LINK = os.path.join(ROOT, "data", "evidence", "director_issuer_link.csv")
BASE = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets"
QUARTERS = [f"{y}q{q}" for y in range(2017, 2027) for q in (1, 2, 3, 4)]
DROP = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "LLC", "THE",
        "HOLDINGS", "HOLDING", "GROUP", "DE", "NEW", "MD", "TX", "COM"}
csv.field_size_limit(10 ** 9)


def normalise(name):
    name = re.sub(r"/[A-Z]{2,3}/?", " ", name.upper())      # 'FIRST COMMONWEALTH FINANCIAL CORP /PA/'
    words = re.sub(r"[^A-Z0-9 ]", " ", name.replace("&", " AND ")).split()
    return " ".join(w for w in words if w not in DROP)


def iso(date):
    """'31-OCT-2025' -> '2025-10-31'."""
    try:
        return datetime.datetime.strptime(date.title(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return ""


def read_tsv(z, name):
    with z.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t"))


def main():
    with open(VOTES, encoding="utf-8-sig", newline="") as f:
        ours = {}
        for r in csv.DictReader(f):
            if r["country"] == "United States":
                ours[r["company_id"]] = r["company"]
    print(f"{len(ours)} US companies in the vote file")

    reports = []  # (owner_cik, owner_name, issuer_cik, issuer_name, month, relationship, title)
    for q in QUARTERS:
        status, raw = get(f"{BASE}/{q}_form345.zip")
        if status != 200:
            print(f"  {q}: HTTP {status}, skipped")
            continue
        z = zipfile.ZipFile(io.BytesIO(raw))
        subs = {r["ACCESSION_NUMBER"]: r for r in read_tsv(z, "SUBMISSION.tsv")}
        n = 0
        for r in read_tsv(z, "REPORTINGOWNER.tsv"):
            s = subs.get(r["ACCESSION_NUMBER"])
            date = iso(s["FILING_DATE"]) if s else ""
            if not date:
                continue
            reports.append((r["RPTOWNERCIK"].lstrip("0"), r["RPTOWNERNAME"], s["ISSUERCIK"].lstrip("0"), s["ISSUERNAME"],
                            date[:7], r["RPTOWNER_RELATIONSHIP"], (r.get("RPTOWNER_TITLE") or "").strip()))
            n += 1
        print(f"  {q}: {n} reports", flush=True)

    # Link our companies to SEC issuers by name. A company may have had several names.
    names = collections.defaultdict(set)
    for _, _, issuer, issuer_name, *_ in reports:
        names[normalise(issuer_name)].add(issuer)
    link = {}
    for cid, name in sorted(ours.items()):
        hits = names.get(normalise(name), set())
        link[cid] = next(iter(hits)) if len(hits) == 1 else ""
    issuer_to_company = {cik: cid for cid, cik in link.items() if cik}
    latest_name = {}
    for _, _, issuer, issuer_name, month, *_ in reports:
        if issuer in issuer_to_company and month >= latest_name.get(issuer, ("", ""))[0]:
            latest_name[issuer] = (month, issuer_name)
    with open(OUT_LINK, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company_id", "company", "issuer_cik", "sec_name", "status"])
        for cid, name in sorted(ours.items(), key=lambda kv: kv[1]):
            cik = link[cid]
            w.writerow([cid, name, cik, latest_name.get(cik, ("", ""))[1], "linked" if cik else "no unique name match"])
    print(f"Linked {len(issuer_to_company)} of {len(ours)} companies by name. Not linked: "
          f"{[ours[c] for c, k in link.items() if not k]}")

    people = {owner for owner, _, issuer, *_ in reports if issuer in issuer_to_company}
    rows = sorted({(issuer_to_company.get(issuer, ""), issuer, issuer_name, owner, owner_name, month, rel, title)
                   for owner, owner_name, issuer, issuer_name, month, rel, title in reports if owner in people})
    with open(OUT_ROLES, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company_id", "issuer_cik", "issuer_name", "person_cik", "person_name", "month", "relationship", "title"])
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows for {len(people)} people to {os.path.relpath(OUT_ROLES, ROOT)}")


if __name__ == "__main__":
    main()
