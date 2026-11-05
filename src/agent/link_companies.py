"""Link more companies in NBIM's pay votes to their SEC number.

Run from the repo root (no internet, a second):
    python3 src/agent/link_companies.py

fetch_ceo_pay.py links a company by its name in the SEC's current ticker list.
That list only holds companies that are listed today, so companies that have
since been acquired or delisted were left without a link, and without pay
figures. data/evidence/sec_issuer_names.csv (from fetch_director_roles.py)
holds every company name that appears in insider filings from 2017 to 2026,
including companies that no longer exist.

This script fills in data/evidence/pay_company_link.csv for the companies that
had no link. A company is linked only when its normalised name matches exactly
one SEC number. After running it, run fetch_proxy_pay.py and
fetch_company_size.py again; they only fetch what is new.
"""

import collections
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))
from fetch_director_roles import normalise  # noqa: E402

import re  # noqa: E402

LINK = os.path.join(ROOT, "data", "evidence", "pay_company_link.csv")
NAMES = os.path.join(ROOT, "data", "evidence", "sec_issuer_names.csv")


def loose(name):
    """A second key for names the SEC writes differently: "Lowe's" / "LOWES",
    "D.R. Horton" / "HORTON D R", "T. Rowe Price Group" / "PRICE T ROWE GROUP".
    Apostrophes are dropped, initials are joined, and word order is ignored."""
    words = normalise(re.sub(r"['’]", "", name).replace(".", " ")).split()
    merged, run = [], ""
    for w in words:
        if len(w) == 1:
            run += w
        else:
            if run:
                merged.append(run)
                run = ""
            merged.append(w)
    if run:
        merged.append(run)
    return " ".join(sorted(merged))


def main():
    by_name = collections.defaultdict(set)
    by_loose = collections.defaultdict(set)
    shown = {}
    with open(NAMES, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            by_name[normalise(r["issuer_name"])].add(r["issuer_cik"])
            by_loose[loose(r["issuer_name"])].add(r["issuer_cik"])
            shown[r["issuer_cik"]] = r["issuer_name"]
    with open(LINK, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    taken = {r["cik"] for r in rows if r["status"].startswith("linked")}
    added = ambiguous = 0
    for r in rows:
        if r["status"].startswith("linked"):
            continue
        hits = by_name.get(normalise(r["name_in_votes"]), set()) or by_loose.get(loose(r["name_in_votes"]), set())
        if len(hits) == 1:
            cik = next(iter(hits))
            r["cik"], r["sec_name"], r["status"] = cik, shown[cik], "linked"
            r["source"] = "name in SEC insider filings"
            added += 1
            taken.add(cik)
        elif len(hits) > 1:
            r["status"] = "ambiguous name"
            ambiguous += 1
    for r in rows:
        r.setdefault("source", "SEC ticker list or pay data" if r["status"] == "linked" else "")
        if not r["source"] and r["status"] == "linked":
            r["source"] = "SEC ticker list or pay data"
    cols = ["cusip", "name_in_votes", "cik", "sec_name", "status", "source"]
    with open(LINK, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in cols} for r in rows)
    status = collections.Counter(r["status"] for r in rows)
    print(f"Linked {added} more companies by their name in insider filings ({ambiguous} names matched more than one).")
    print(f"Now: {dict(status)}")
    print("Still without a link: " + ", ".join(r["name_in_votes"] for r in rows if r["status"] != "linked")[:600])


if __name__ == "__main__":
    main()
