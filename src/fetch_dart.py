"""Fetch the Korean companies' boards from OpenDART, the Korean Financial Supervisory Service's filing system.

Run from the repository root. Needs OPENDART_API_KEY in .env (free, https://opendart.fss.or.kr).
    python src/fetch_dart.py

For each company and business year, the annual report's list of executives (exctvSttus):
every registered director as inside (사내이사), outside (사외이사) or other non-executive
(기타비상무이사), with roles such as representative director (대표이사) and board chair (의장).
The receipt number starts with the filing date, so a meeting only uses reports filed before it.

Output: data/evidence/dart/companies.csv and data/evidence/dart/executives.csv.
"""

import csv
import io
import os
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "evidence" / "dart"
VOTES = ROOT / "data" / "dirty" / "real_votes.csv"
API = "https://opendart.fss.or.kr/api"
YEARS = range(2017, 2026)
REPORTS = {"11011": "annual", "11012": "half-year"}


def key():
    load_dotenv(ROOT / ".env")
    value = os.environ.get("OPENDART_API_KEY")
    if not value:
        raise SystemExit("Set OPENDART_API_KEY in .env.")
    return value


def companies(api_key):
    OUT.mkdir(parents=True, exist_ok=True)
    """Vote-file company -> DART corp code, on the 6-digit stock code. A shortened code is matched on its start and the name."""
    votes = {}
    with open(VOTES, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["country"] == "South Korea":
                votes.setdefault(r["company_id"], (r["company"], r["ticker"].strip()))
    cached = OUT / "CORPCODE.zip"  # About 3.5 MB and slow to serve, so it is downloaded once.
    if not cached.exists():
        with requests.get(f"{API}/corpCode.xml", params={"crtfc_key": api_key}, timeout=(30, 900), stream=True) as z:
            cached.write_bytes(b"".join(z.iter_content(1 << 16)))
    root = ET.fromstring(zipfile.ZipFile(cached).read("CORPCODE.xml"))
    listed = [(e.findtext("corp_code"), e.findtext("corp_name"), e.findtext("stock_code").strip()) for e in root.iter("list")]
    listed = [c for c in listed if c[2]]
    out = []
    for company_id, (name, ticker) in sorted(votes.items()):
        hits = [c for c in listed if c[2] == ticker.zfill(6)] if len(ticker) >= 5 else [c for c in listed if c[2].startswith(ticker)]
        out.append({"company_id": company_id, "company": name, "ticker": ticker, "corp_code": hits[0][0] if len(hits) == 1 else "",
                    "dart_name": hits[0][1] if len(hits) == 1 else "", "status": "ok" if len(hits) == 1 else f"{len(hits)} candidates"})
    return out


def main():
    api_key = key()
    OUT.mkdir(parents=True, exist_ok=True)
    found = companies(api_key)
    with open(OUT / "companies.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(found[0]))
        w.writeheader()
        w.writerows(found)
    print(f"Companies matched: {sum(c['status'] == 'ok' for c in found)} of {len(found)}",
          [c["company"] for c in found if c["status"] != "ok"])
    rows = []
    for c in found:
        if not c["corp_code"]:
            continue
        for year in YEARS:
            for code, kind in REPORTS.items():
                r = requests.get(f"{API}/exctvSttus.json", params={"crtfc_key": api_key, "corp_code": c["corp_code"],
                                                                  "bsns_year": str(year), "reprt_code": code}, timeout=60).json()
                time.sleep(0.1)
                for x in r.get("list", []) if r.get("status") == "000" else []:
                    rows.append({"company_id": c["company_id"], "corp_code": c["corp_code"], "bsns_year": year, "report": kind,
                                 "rcept_no": x.get("rcept_no", ""), "filed": f"{x['rcept_no'][:4]}-{x['rcept_no'][4:6]}-{x['rcept_no'][6:8]}",
                                 "name": x.get("nm", ""), "position": x.get("ofcps", ""), "registered": x.get("rgist_exctv_at", ""),
                                 "full_time": x.get("fte_at", ""), "duties": (x.get("chrg_job") or "").replace("\n", " | ")})
        print(f"  {c['company']}: {sum(r['company_id'] == c['company_id'] for r in rows)} rows", flush=True)
    with open(OUT / "executives.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} executive rows.")


if __name__ == "__main__":
    main()
