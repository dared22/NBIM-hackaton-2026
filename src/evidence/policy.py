"""Explicit refresh of the saved NBIM guideline comparison."""

import datetime
import html
import json
import re
import urllib.request
from pathlib import Path

from src import data as paths

URL = "https://www.nbim.no/en/responsible-investment/voting/global-voting-guidelines/"

AGENT = "Mozilla/5.0 (student hackathon project, reads public policy pages)"

RULE_START = re.compile(
    r"^(We (will|may|would|do)\b|At a\b|At an\b|In general\b|In (developed|emerging) markets\b)"
)


def fetch():
    """The rule sentences on NBIM's guidelines page, in page order."""
    req = urllib.request.Request(URL, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=40) as r:
        page = r.read().decode("utf-8", errors="replace")
    main = re.search(r"<main\b.*?</main>", page, re.S)
    body = re.sub(
        r"<(script|style|nav|footer|header)\b.*?</\1>",
        " ",
        main.group(0) if main else page,
        flags=re.S | re.I,
    )
    items = re.findall(r"<li\b[^>]*>(.*?)</li>", body, re.S) + re.findall(
        r"<p\b[^>]*>(.*?)</p>", body, re.S
    )
    sentences = []
    for item in items:
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", item))).strip()
        if RULE_START.match(text) and text not in sentences:
            sentences.append(text)
    return {"url": URL, "fetched": datetime.date.today().isoformat(), "sentences": sentences}


def refresh() -> None:
    live = fetch()
    if len(live["sentences"]) < 40:
        raise SystemExit(
            f"Only {len(live['sentences'])} rule sentences found. Not saved: the page layout may have changed."
        )
    destination = Path(paths.LIVE_GUIDELINES)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(live, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved {len(live['sentences'])} guideline sentences to {destination}")
