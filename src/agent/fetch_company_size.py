"""Fetch each company's industry code and yearly revenue, to build peer groups.

Run from the repo root (needs internet, about 3 minutes):
    python3 src/agent/fetch_company_size.py

Why: the proxy advisers judge CEO pay against similar companies. ISS compares
pay with the median of 12-24 peers chosen by industry and size ("Multiple of
Median"). To do the same we need an industry code and a size figure per company.

Sources (SEC EDGAR, open, no key)
    Industry: the SIC code in https://data.sec.gov/submissions/CIK##########.json
    Revenue:  https://data.sec.gov/api/xbrl/frames/us-gaap/<tag>/USD/CY<year>.json
              for the tags Revenues and
              RevenueFromContractWithCustomerExcludingAssessedTax.
              One request returns every company for that year.

Output
    data/evidence/company_size.csv  one row per company and fiscal year end:
                                    cik, sic, industry, period_end, revenue_usd

A fiscal year's revenue is published in the annual report, which comes out
before the proxy statement for the following annual meeting.
"""

import collections
import concurrent.futures
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from fetch_proxy_pay import get  # noqa: E402

LINK = os.path.join(ROOT, "data", "evidence", "pay_company_link.csv")
OUT = os.path.join(ROOT, "data", "evidence", "company_size.csv")
REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]
YEARS = range(2020, 2027)


def main():
    with open(LINK, encoding="utf-8", newline="") as f:
        ciks = sorted({int(r["cik"]) for r in csv.DictReader(f) if r["status"] == "linked"})
    print(f"{len(ciks)} companies")

    # Revenue: the larger of the two tags for the same company and fiscal year end.
    revenue = collections.defaultdict(dict)
    wanted = set(ciks)
    for tag in REVENUE_TAGS:
        for year in YEARS:
            status, raw = get(f"https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/CY{year}.json")
            if status != 200:
                print(f"  {tag} {year}: HTTP {status}")
                continue
            rows = json.loads(raw)["data"]
            for d in rows:
                if d["cik"] in wanted and d["val"] > 0:
                    revenue[d["cik"]][d["end"]] = max(revenue[d["cik"]].get(d["end"], 0), d["val"])
            print(f"  {tag} {year}: {len(rows)} companies in the SEC frame")

    industry = {}

    def work(cik):
        status, raw = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if status == 200:
            d = json.loads(raw)
            industry[cik] = (d.get("sic", ""), d.get("sicDescription", ""))

    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        list(pool.map(work, ciks))

    n = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cik", "sic", "industry", "period_end", "revenue_usd"])
        for cik in ciks:
            sic, name = industry.get(cik, ("", ""))
            ends = sorted(revenue.get(cik, {})) or [""]
            for end in ends:
                w.writerow([cik, sic, name, end, f"{revenue[cik][end]:.0f}" if end else ""])
                n += 1
    print(f"Wrote {n} rows to {os.path.relpath(OUT, ROOT)}")
    print(f"Industry code for {sum(1 for c in ciks if industry.get(c, ('',))[0])} companies, "
          f"revenue for {sum(1 for c in ciks if revenue.get(c))}")


if __name__ == "__main__":
    main()
