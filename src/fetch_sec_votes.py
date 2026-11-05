"""Fetch last year's general-meeting vote results for the US companies, from SEC form 8-K item 5.07.

Run from the repository root (needs internet; the SEC asks for a contact in the User-Agent, set in src/hent_npx.py):
    python src/fetch_sec_votes.py

Companies must report the results of a shareholder vote within four business days, in an 8-K
under item 5.07. This reads the vote tables in those filings: votes for and against each director
and each proposal. Support = for / (for + against or withheld).

Companies are linked to the SEC by data/evidence/main/director_issuer_link.csv (from main).

Output: data/evidence/sec_votes/votes.csv, one row per vote line:
    company_id, issuer_cik, filed, accession, url, context, label, votes_for, votes_against, support
'context' is the text just before the table, so a table without labels can still be placed
(for example 'Proposal 2 - advisory vote on executive compensation').
Not every filing uses tables; those are skipped and counted.
"""

import csv
import html
import json
import re
import time
import urllib.request
from pathlib import Path

from hent_npx import USER_AGENT

ROOT = Path(__file__).resolve().parents[1]
LINK = ROOT / "data" / "evidence" / "main" / "director_issuer_link.csv"
OUT = ROOT / "data" / "evidence" / "sec_votes"
FIRST = "2018-01-01"


def get(url, tries=5):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            time.sleep(0.15)  # The SEC allows 10 requests a second.
            return data
        except Exception:
            time.sleep(2 ** attempt)
    return None


def filings_507(cik):
    """Every 8-K with item 5.07 since FIRST: (filed, accession, primary document)."""
    data = json.loads(get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))
    pages = [data["filings"]["recent"]] + [json.loads(get(f"https://data.sec.gov/submissions/{f['name']}")) for f in data["filings"].get("files", [])]
    out = []
    for page in pages:
        for form, filed, acc, doc, items in zip(page["form"], page["filingDate"], page["accessionNumber"], page["primaryDocument"], page["items"]):
            if form.startswith("8-K") and "5.07" in (items or "") and filed >= FIRST:
                out.append((filed, acc, doc))
    return out


def number(text):
    text = text.replace(",", "").replace("$", "").strip()
    return int(text) if re.fullmatch(r"\d{3,}", text) else None


def plain(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def vote_lines(page):
    """(context, label, for, against) for each table row with at least two vote counts."""
    page = re.sub(r"(?is)<(script|style).*?</\1>", " ", page)
    out, last_end = [], 0
    for table in re.finditer(r"(?is)<table.*?</table>", page):
        context = plain(page[last_end:table.start()])[-300:]
        last_end = table.end()
        for row in re.findall(r"(?is)<tr.*?</tr>", table.group(0)):
            cells = [plain(c) for c in re.findall(r"(?is)<t[dh].*?</t[dh]>", row)]
            cells = [c for c in cells if c and c not in ("$", "%")]
            counts = [n for n in (number(c) for c in cells) if n is not None]
            if len(counts) < 2:
                continue
            label = next((c for c in cells if number(c) is None and re.search(r"[A-Za-z]{2}", c)), "")
            out.append((context, label, counts[0], counts[1]))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with open(LINK, encoding="utf-8", newline="") as f:
        companies = [r for r in csv.DictReader(f) if r["issuer_cik"]]
    rows, without_tables = [], 0
    for c in companies:
        for filed, acc, doc in filings_507(c["issuer_cik"]):
            url = f"https://www.sec.gov/Archives/edgar/data/{int(c['issuer_cik'])}/{acc.replace('-', '')}/{doc}"
            page = get(url)
            lines = vote_lines(page.decode("utf-8", "replace")) if page else []
            without_tables += not lines
            for context, label, yes, no in lines:
                rows.append({"company_id": c["company_id"], "issuer_cik": c["issuer_cik"], "filed": filed, "accession": acc, "url": url,
                             "context": context, "label": label, "votes_for": yes, "votes_against": no,
                             "support": round(100 * yes / (yes + no), 2) if yes + no else ""})
        print(f"  {c['company'][:40]}: {sum(r['company_id'] == c['company_id'] for r in rows)} vote lines", flush=True)
    with open(OUT / "votes.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} vote lines from {len({r['accession'] for r in rows})} filings; {without_tables} filings had no vote table.")


if __name__ == "__main__":
    main()
