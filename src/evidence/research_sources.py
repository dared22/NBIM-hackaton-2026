"""Dated evidence acquisition. Search results are discovery hints, never model inputs."""

import csv
import datetime as dt
import hashlib
import io
import json
import random
import re
import subprocess
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from src import data as paths
from src.evidence import fetch_board_facts as proxy
from src.evidence.http import USER_AGENT, get

CACHE = Path(paths.ROOT) / "data/evidence/researched_jev"


def digest(value: bytes | dict) -> str:
    """Stable identity for source bytes and requests."""
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def append(path: Path, record: dict) -> None:
    """Append an audit record without replacing previous runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def records(path: Path) -> list[dict]:
    """Read an optional JSONL audit file."""
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def sample_meetings(rows: list[dict], year: int, limit: int) -> list[list[dict]]:
    """Sample whole meetings without inspecting outcomes."""
    if limit < 1:
        raise ValueError("Meeting limit must be positive")
    groups = {}
    for row in rows:
        if row["meeting_date"].startswith(str(year)):
            groups.setdefault(row["meeting_id"], []).append(row)
    keys = sorted(groups)
    random.Random(42).shuffle(keys)
    return [groups[key] for key in keys[:limit]]


def admitted(document: dict, cutoff: str) -> bool:
    """Validate availability proof and cached content integrity on every replay."""
    try:
        day = dt.date.fromisoformat(document["available_on"])
        if day >= dt.date.fromisoformat(cutoff):
            return False
        if digest(document["text"].encode()) != document["sha256"]:
            return False
        proof = document["proof"]
        url = urlparse(document["url"])
        if proof["kind"] == "sec_filing":
            return (
                url.hostname == "www.sec.gov"
                and url.path.startswith("/Archives/edgar/data/")
                and proof["filed"] == document["available_on"]
                and proof["accession"].replace("-", "") in url.path.split("/")
            )
        if proof["kind"] == "archive":
            stamp = proof["timestamp"]
            archive = urlparse(document["snapshot_url"])
            return (
                archive.hostname == "web.archive.org"
                and archive.path == f"/web/{stamp}id_/{document['url']}"
                and dt.datetime.strptime(stamp, "%Y%m%d%H%M%S").date() == day
            )
    except (KeyError, TypeError, ValueError):
        return False
    return False


def has_target_answer(text: str) -> bool:
    """Conservatively exclude documents describing NBIM voting decisions."""
    return bool(
        re.search(
            r"(?:NBIM|Norges Bank)[\s\S]{0,250}(?:vot(?:e|ed|ing)|withhold|abstain)"
            r"|(?:vot(?:e|ed|ing)|withhold|abstain)[\s\S]{0,250}(?:NBIM|Norges Bank)",
            text,
            re.I,
        )
    )


def source_record(url: str, text: str, available_on: str, proof: dict, **extra) -> dict:
    """Build a content-addressed source audit record."""
    return {
        "url": url,
        "text": text,
        "available_on": available_on,
        "sha256": digest(text.encode()),
        "proof": proof,
        **extra,
    }


def document_text(raw: bytes) -> str:
    """Extract text from captured HTML or PDF bytes; never fetch linked resources."""
    if raw.startswith(b"%PDF"):
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
        except PdfReadError:
            return ""
    return proxy.plain(raw).strip()


class Researcher:
    """At most five Firecrawl searches per meeting; cache immutable evidence."""

    def __init__(self, cache: Path = CACHE):
        self.cache = cache
        self.searches = 0
        self.failures: list[str] = []

    def search(self, query: str) -> list[str]:
        identity = digest({"query": query, "version": 1})
        path = self.cache / "search" / f"{identity}.json"
        if not path.exists():
            self.searches += 1
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["firecrawl", "search", query, "--limit", "5", "--json", "-o", str(path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        data = json.loads(path.read_text())
        return [r["url"] for r in data.get("data", {}).get("web", [])]

    def archived(self, url: str, cutoff: str) -> dict | None:
        """Use an actual pre-cutoff snapshot, never the current page's date tag."""
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.endswith("nbim.no"):
            return None  # Voting history has a separate explicit allowlist.
        last = dt.date.fromisoformat(cutoff) - dt.timedelta(days=1)
        query = urlencode(
            {
                "url": url,
                "output": "json",
                "filter": "statuscode:200",
                "to": last.strftime("%Y%m%d") + "235959",
                "filter!": "mimetype:warc/revisit",
                "limit": "-1",
            }
        )
        status, raw = get("https://web.archive.org/cdx/search/cdx?" + query, tries=1)
        if status != 200:
            return None
        try:
            entries = json.loads(raw)
            item = dict(zip(entries[0], entries[-1])) if len(entries) > 1 else {}
            stamp = item.get("timestamp", "")
            date = dt.datetime.strptime(stamp, "%Y%m%d%H%M%S").date().isoformat()
        except (ValueError, TypeError, KeyError, IndexError):
            return None
        snapshot = f"https://web.archive.org/web/{stamp}id_/{url}"
        with urlopen(Request(snapshot, headers={"User-Agent": USER_AGENT}), timeout=30) as response:
            # Wayback can redirect a requested capture to a different date or live URL.
            # Refuse that substitution, even if the requested timestamp looked safe.
            if response.geturl() != snapshot:
                return None
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            return None
        text = document_text(raw)
        if not text.strip():
            return None
        doc = source_record(
            url, text, date, {"kind": "archive", "timestamp": stamp}, snapshot_url=snapshot
        )
        return doc if admitted(doc, cutoff) else None

    def meeting(self, rows: list[dict]) -> list[dict]:
        """Fetch the proxy plus dated archives; retain rejected-source diagnostics."""
        row = rows[0]
        cutoff = row["meeting_date"]
        cache_file = self.cache / "meetings" / f"{row['meeting_id']}-{cutoff}.json"
        if cache_file.exists():
            saved = [d for d in json.loads(cache_file.read_text()) if admitted(d, cutoff)]
            if saved:
                return saved
        documents = []
        if row["country"] == "United States":
            with open(paths.DIRECTOR_ISSUER_LINK, newline="") as handle:
                links = {
                    r["company_id"]: r for r in csv.DictReader(handle) if r["status"] == "linked"
                }
            link = links.get(row["company_id"])
            if link:
                cik = int(link["issuer_cik"])
                filings = proxy.company_filings(cik, str(int(cutoff[:4]) - 1) + "-01-01")
                pick = proxy.pick_proxy(filings or [], cutoff)
                if pick:
                    filed, form, acc, name = pick
                    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{name}"
                    status, raw = get(url, tries=1)
                    if status == 200:
                        documents.append(
                            source_record(
                                url,
                                proxy.plain(raw),
                                filed,
                                {
                                    "kind": "sec_filing",
                                    "filed": filed,
                                    "accession": acc,
                                    "form": form,
                                },
                            )
                        )
        topics = sorted({r["proposal_type"].replace("_", " ").lower() for r in rows})
        queries = [f'"{row["company"]}" {cutoff[:4]} proxy annual meeting before:{cutoff}']
        queries += [f'"{row["company"]}" {cutoff[:4]} {t} before:{cutoff}' for t in topics]
        seen = {d["url"] for d in documents}
        for query in queries[:5]:
            try:
                urls = self.search(query)
                # Bound downloads too; search snippets never enter the evidence state.
                for url in urls[:2]:
                    if url in seen:
                        continue
                    seen.add(url)
                    doc = self.archived(url, cutoff)
                    if doc:
                        documents.append(doc)
            except (subprocess.SubprocessError, OSError, ValueError) as error:
                self.failures.append(f"{row['meeting_id']}: {type(error).__name__}")
        documents = [
            d for d in documents if admitted(d, cutoff) and not has_target_answer(d["text"])
        ]
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(documents, ensure_ascii=False))
        return documents


def earlier_votes(row: dict, rows: list[dict], cache: Path = CACHE) -> tuple[list[dict], int]:
    """Join earlier outcomes only to archived publication proofs with matching quotes.

    publication records contain vote_key, document, and quote. The source must
    explicitly contain the company, proposal, date and vote; no inferred dates.
    """
    proofs = {p["vote_key"]: p for p in records(cache / "history_publications.jsonl")}
    earlier = [
        r
        for r in rows
        if r["company_id"] == row["company_id"]
        and r["meeting_date"] < row["meeting_date"]
        and r["proposal_type"] == row["proposal_type"]
    ]
    eligible = []
    for past in earlier:
        proof = proofs.get(f"{past['meeting_id']}-{past['item_no']}", {})
        doc, quote = proof.get("document", {}), proof.get("quote", "")
        if not admitted(doc, row["meeting_date"]) or not quote or quote not in doc["text"]:
            continue
        if not all(
            str(past[k]).casefold() in quote.casefold()
            for k in ("company", "proposal_text", "meeting_date", "nbim_vote")
        ):
            continue
        eligible.append(
            {
                "proposal": past["proposal_text"],
                "date": past["meeting_date"],
                "vote": past["nbim_vote"],
                "source_sha256": doc["sha256"],
                "publication": proof,
            }
        )
    return sorted(
        eligible,
        key=lambda p: (p["proposal"] != row["proposal_text"], -int(p["date"].replace("-", ""))),
    )[:6], len(earlier) - len(eligible)
