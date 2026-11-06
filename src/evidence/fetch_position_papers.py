"""evidence.fetch position papers: NBIM voting decision support."""

import datetime
import html
import json
import os
import re
import time
import urllib.request

from src import data as paths
from src.data import ROOT

OUT = paths.POSITION_PAPERS
INDEX = "https://www.nbim.no/en/responsible-investment/position-papers/"
AGENT = "Mozilla/5.0 (student hackathon project, reads public policy pages)"


def get(url):
    time.sleep(0.4)
    req = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", errors="replace")


def page_text(page):
    """The readable text of the main part of an NBIM page, one paragraph per line."""
    m = re.search(r"<main\b.*?</main>", page, re.S)
    body = m.group(0) if m else page
    body = re.sub(r"<(script|style|nav|footer|header)\b.*?</\1>", " ", body, flags=re.S | re.I)
    body = re.sub(r"</(p|h1|h2|h3|h4|li|div)>", "\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{2,}", "\n\n", "\n".join(lines)).strip()


def main():
    index = get(INDEX)
    slugs = sorted(
        set(re.findall(r'href="/en/responsible-investment/position-papers/([a-z0-9-]+)/?"', index))
    )
    papers = []
    for slug in slugs:
        url = INDEX + slug + "/"
        page = get(url)
        title = re.search(r"<title>(.*?)</title>", page, re.S)
        title = html.unescape(title.group(1)).split("|")[0].strip() if title else slug
        text = page_text(page)
        start = text.find("Norges Bank Investment Management position")
        ends = [
            i
            for i in (text.find("\nBackground", start), text.find("\nArguments for", start))
            if i > start
        ]
        end = min(ends) if ends else -1
        position = (
            text[start:end].replace("Norges Bank Investment Management position", "").strip()
            if start >= 0 and end > start
            else ""
        )
        papers.append(
            {
                "slug": slug,
                "title": title,
                "url": url,
                "fetched": datetime.date.today().isoformat(),
                "position": position,
                "text": text,
            }
        )
        print(f"  {title}: {len(text)} characters, position {len(position)} characters")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=1)
    print(f"Wrote {len(papers)} papers to {os.path.relpath(OUT, ROOT)}")
