"""Policy watch: has NBIM changed the wording of a voting rule since the edition the tool holds?

Run from the repo root:
    python3 src/agent/policy_watch.py            # compare the saved copy of the live page (no internet)
    python3 src/agent/policy_watch.py --fetch    # download NBIM's guidelines page again first

Why
    The tool applies NBIM's rules from the 2025 edition of the Global Voting Guidelines
    (startpakke/case1_stemmegivning/retningslinjer_2025.json, taken from the PDF dated May
    2025). NBIM also publishes the guidelines as a web page and updates it. If a rule is
    reworded there, the tool should know, because a rule that said "will not" and now says
    "may not" has become a judgement call.

What it does
    It takes every rule sentence from the web page and looks for it, word for word, among
    the rules of the stored edition. Rules of the stored edition that are no longer on the
    page are reported with the closest sentence that is, so a rewording shows as a pair.

What it found (page fetched 6 November 2026)
    One rule differs. Rule 1.3.1, stored edition: "We will not support the election of a
    chairperson who is also the CEO of the company." Web page: "We may not support the
    election of a chairperson who is also the CEO of the company." It is the only rule on
    the page that uses "may".

    That is the rule where NBIM's votes changed: it opposed 28 of 28 chair-and-CEO nominees
    in this file in 2019-2024, 4 of 5 in 2025, and 0 of 5 in 2026. NBIM's report on its
    voting in the first half of 2025 still describes opposing the chair and CEO at about
    305 US companies, so the rewording came after that. The page carries no date, so we
    cannot say whether the softer wording was public before each 2026 meeting. For that
    reason it is not used to score 2026: the tool found the change from the votes alone
    (src/agent/board_rules.py takes away a rule's trust at the first miss). From the day
    the page was fetched, a rule whose live wording is softer is treated as a judgement
    call: its cases go to a person.

Output: data/policy/guidelines_live.json (the sentences as fetched, with the date) and a
printed comparison.
"""

import argparse
import datetime
import difflib
import html
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORED = os.path.join(ROOT, "startpakke", "case1_stemmegivning", "retningslinjer_2025.json")
LIVE = os.path.join(ROOT, "data", "policy", "guidelines_live.json")
URL = "https://www.nbim.no/en/responsible-investment/voting/global-voting-guidelines/"
AGENT = "Mozilla/5.0 (student hackathon project, reads public policy pages)"
RULE_START = re.compile(r"^(We (will|may|would|do)\b|At a\b|At an\b|In general\b|In (developed|emerging) markets\b)")


def plain(text):
    """Lower case, straight quotes, single spaces: for comparing sentences, not for showing them."""
    text = html.unescape(text).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def fetch():
    """The rule sentences on NBIM's guidelines page, in page order."""
    req = urllib.request.Request(URL, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=40) as r:
        page = r.read().decode("utf-8", errors="replace")
    main = re.search(r"<main\b.*?</main>", page, re.S)
    body = re.sub(r"<(script|style|nav|footer|header)\b.*?</\1>", " ", main.group(0) if main else page, flags=re.S | re.I)
    items = re.findall(r"<li\b[^>]*>(.*?)</li>", body, re.S) + re.findall(r"<p\b[^>]*>(.*?)</p>", body, re.S)
    sentences = []
    for item in items:
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", item))).strip()
        if RULE_START.match(text) and text not in sentences:
            sentences.append(text)
    return {"url": URL, "fetched": datetime.date.today().isoformat(), "sentences": sentences}


def softened(old, new):
    """True when the live wording is weaker than the stored one: "will not" or "will" became "may"."""
    return bool(re.search(r"\bwe will\b", plain(old)) and re.search(r"\bwe may\b", plain(new))
                and not re.search(r"\bwe may\b", plain(old)))


def compare(stored_rules, live_sentences, intro_sentences=()):
    """Returns (same, reworded, gone, new). reworded: (rule id, stored text, live text, softened?).
    intro_sentences: the stored edition's introductions, which are on the page too and are not rules."""
    intros = " ".join(plain(s) for s in intro_sentences)
    live = {plain(s): s for s in live_sentences if plain(s) not in intros}
    stored = {plain(r["tekst"]): r for r in stored_rules}
    same = [r["id"] for key, r in stored.items() if key in live]
    unmatched_live = [s for key, s in live.items() if key not in stored]
    reworded, gone = [], []
    for key, r in stored.items():
        if key in live:
            continue
        close = difflib.get_close_matches(key, [plain(s) for s in unmatched_live], n=1, cutoff=0.8)
        if close:
            text = next(s for s in unmatched_live if plain(s) == close[0])
            unmatched_live.remove(text)
            reworded.append((r["id"], r["tekst"], text, softened(r["tekst"], text)))
        else:
            gone.append((r["id"], r["tekst"]))
    return same, reworded, gone, unmatched_live


def softened_rules():
    """Rule ids whose live wording is softer than the stored edition, with the date the page was fetched.
    Empty if no copy of the live page has been saved."""
    if not os.path.exists(LIVE):
        return {}, ""
    with open(LIVE, encoding="utf-8") as f:
        live = json.load(f)
    with open(STORED, encoding="utf-8") as f:
        stored = json.load(f)
    _, reworded, _, _ = compare(stored["regler"], live["sentences"], introductions(stored))
    return {rid: new for rid, _, new, soft in reworded if soft}, live["fetched"]


def introductions(stored):
    return [s for u in stored["underseksjoner"] for s in u.get("innledning", [])] + [p["tekst"] for p in stored.get("prinsipper", [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="download NBIM's guidelines page again")
    a = ap.parse_args()
    if a.fetch:
        live = fetch()
        if len(live["sentences"]) < 40:
            raise SystemExit(f"Only {len(live['sentences'])} rule sentences found on the page. Not saved: the page layout may have changed.")
        os.makedirs(os.path.dirname(LIVE), exist_ok=True)
        with open(LIVE, "w", encoding="utf-8") as f:
            json.dump(live, f, ensure_ascii=False, indent=1)
    if not os.path.exists(LIVE):
        raise SystemExit("No saved copy of the live page. Run with --fetch.")
    with open(LIVE, encoding="utf-8") as f:
        live = json.load(f)
    with open(STORED, encoding="utf-8") as f:
        stored = json.load(f)
    same, reworded, gone, new = compare(stored["regler"], live["sentences"], introductions(stored))
    print(f"Stored edition: {stored['meta']['tittel']}, {len(stored['regler'])} rules.")
    print(f"NBIM's web page, fetched {live['fetched']}: {len(live['sentences'])} rule sentences.")
    print(f"\nWord for word the same: {len(same)} rules.")
    print(f"Reworded: {len(reworded)}.")
    for rid, old, text, soft in reworded:
        print(f"  [{rid}]{' SOFTER' if soft else ''}")
        print(f"     stored: {old}")
        print(f"     live:   {text}")
    print(f"In the stored edition, not found on the page: {len(gone)}.")
    for rid, old in gone:
        print(f"  [{rid}] {old}")
    print(f"On the page, not in the stored edition: {len(new)}.")
    for text in new:
        print(f"  {text}")
    soft = [rid for rid, _, _, s in reworded if s]
    if soft:
        print(f"\nRules that became softer: {', '.join(soft)}. From {live['fetched']} the tool treats them as judgement calls:")
        print("their cases go to a person. They are not used to score meetings before that date.")


if __name__ == "__main__":
    main()
