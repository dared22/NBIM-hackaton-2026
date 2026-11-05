"""Board facts for Japanese director elections, read from EDINET filings dated before the meeting.

Run from the repository root after src/fetch_edinet.py:
    python src/japan_facts.py        # writes data/evidence/edinet/boards.csv and votes.csv, then a summary

Sources
    Annual securities report (yuho, type 120/130), as XBRL converted to CSV by EDINET.
      - every director, tagged with a romanised ID such as 'SaitoNoboruMember' and a title
      - '...Proposal' fields: when the report is filed before the AGM, the board as proposed for it
      - outside and independent directors, named in the officers and governance text
    Extraordinary report after a general meeting (type 180): votes for and against each item.
      EDINET only keeps these from mid-2024, so only 2025 and 2026 meetings get last year's votes.

No look-ahead: a meeting only uses reports submitted before the meeting date.
"""

import csv
import io
import re
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDINET = ROOT / "data" / "evidence" / "edinet"
DOCS = EDINET / "docs"
DIRECTOR = re.compile(r"取締役")
AUDITOR_ONLY = re.compile(r"^(常勤)?監査役$")
EXECUTIVE = re.compile(r"代表|社長|会長|執行役|ＣＥＯ|ＣＦＯ|ＣＯＯ|CEO|CFO|COO|副社長|専務|常務")


def clean(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def member_tokens(context):
    """'..._E01780-000SaitoNoboruMember' -> {'saito', 'noboru'}"""
    m = re.search(r"-\d{3}([A-Za-z]+?)(Member|$)", context)
    name = m.group(1) if m else ""
    return {w.lower() for w in re.findall(r"[A-Z][a-z]*", name) if len(w) >= 2}


def read_yuho(path):
    """Directors now and as proposed, with outside and independent ones marked."""
    with zipfile.ZipFile(path) as zf:
        name = next((n for n in zf.namelist() if "jpcrp" in n and n.endswith(".csv")), None)
        if not name:
            return None
        rows = list(csv.reader(io.StringIO(zf.read(name).decode("utf-16")), delimiter="\t"))
    people = {"current": defaultdict(dict), "proposal": defaultdict(dict)}
    text = ""
    for r in rows[1:]:
        element, context, value = r[0], r[2], r[-1]
        part = "proposal" if element.endswith("Proposal") else "current"
        if element.startswith("jpcrp_cor:NameInformationAboutDirectorsAndCorporateAuditors"):
            people[part][context]["name"] = clean(value)
        elif element.startswith("jpcrp_cor:OfficialTitleOrPositionInformationAboutDirectorsAndCorporateAuditors"):
            people[part][context]["title"] = clean(value)
        elif "TextBlock" in element and ("Officers" in element or "Outside" in element or "CorporateGovernance" in element):
            text += clean(value)
    # Short sentences only: the officer table has no full stops, so it reads as one long sentence with every name.
    sentences = [s for s in re.split(r"[。]", text) if len(s) <= 400]
    # The officer list's footnote is the reliable source: "取締役 A、B 及び C は、社外取締役であります".
    # Read back from each "…は、社外取締役であります" to the start of its note: the note can be glued to the table.
    notes = []
    for m in re.finditer(r"社外取締役で(?:あります|す)", text):
        before = text[max(0, m.start() - 250):m.start()]
        starts = [before.rfind("。"), before.rfind("(注)")] + [x.end() for x in re.finditer(r"\d\.(?=取締役|監査|社外)", before)]
        notes.append(before[max(starts) + 1 if max(starts) >= 0 else 0:])
    footnote = "|".join(notes)
    nearby = "|".join(re.findall(r"社外取締役.{0,12}|.{0,12}氏?[（(]社外取締役", "|".join(sentences)))
    independent_text = "|".join(s for s in sentences if "独立役員" in s or "独立社外" in s)
    registers_independent = "独立役員" in text or "独立社外取締役" in text or "独立性" in text
    boards = {}
    for part, found in people.items():
        directors = []
        for context, p in found.items():
            title, name = p.get("title", ""), p.get("name", "")
            if not name or not DIRECTOR.search(title) or AUDITOR_ONLY.match(title):
                continue
            executive = bool(EXECUTIVE.search(title))
            named = name in footnote if footnote else name in nearby
            outside = not executive and (named or "社外" in title)  # An outside director is never an executive.
            directors.append({"tokens": member_tokens(context), "name": name, "title": title, "outside": outside, "executive": executive})
        # Independence: the directors the text names as independent officers. Many reports instead register
        # all outside directors without naming them; then every outside director counts as independent.
        named_independent = [d for d in directors if d["outside"] and d["name"] in independent_text]
        for d in directors:
            d["independent"] = d["outside"] and (d in named_independent if named_independent else registers_independent)
        boards[part] = directors
    boards["stated_outside"] = stated_outside(text)
    return boards


def stated_outside(text):
    """The report's own count, e.g. '取締役7名のうち社外取締役は4名', to check the extraction against."""
    m = re.search(r"取締役(\d+)名[^。|]{0,25}?社外取締役(?:は)?(\d+)名", text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def filings():
    with open(EDINET / "filings.csv", encoding="utf-8", newline="") as f:
        unique = {r["docID"]: r for r in csv.DictReader(f)}  # an interrupted index can write a day twice
    return [r for r in unique.values() if r["withdrawalStatus"] in ("0", "")]


def build_boards():
    """One row per annual report: board size, outside and independent share, as filed and as proposed."""
    out = []
    for doc in filings():
        if doc["docTypeCode"] not in ("120", "130"):
            continue
        path = DOCS / f"{doc['docID']}_5.zip"
        if not path.exists():
            continue
        boards = read_yuho(path)
        if not boards:
            continue
        for part, directors in boards.items():
            if part not in ("current", "proposal") or not directors:
                continue
            for d in directors:
                out.append({"edinet_code": doc["edinetCode"], "doc_id": doc["docID"], "submitted": doc["submitDateTime"][:10],
                            "period_end": doc["periodEnd"], "part": part, "board_size": len(directors),
                            "outside": sum(x["outside"] for x in directors), "independent": sum(x["independent"] for x in directors),
                            "name": d["name"], "tokens": " ".join(sorted(d["tokens"])), "title": d["title"],
                            "is_outside": int(d["outside"]), "is_independent": int(d["independent"]), "is_executive": int(d["executive"])})
    with open(EDINET / "boards.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    return out


def read_vote_results(path):
    """Votes per item from an extraordinary report after a general meeting: [(item label, support %)]."""
    with zipfile.ZipFile(path) as zf:
        html = "".join(zf.read(n).decode("utf-8", "replace") for n in zf.namelist() if n.endswith(".htm") and "PublicDoc" in n)
    if "賛成" not in html:
        return []
    results = []
    for row in re.findall(r"<tr.*?</tr>", html, flags=re.S):
        cells = [clean(re.sub(r"<[^>]+>", " ", c)) for c in re.findall(r"<t[dh].*?</t[dh]>", row, flags=re.S)]
        cells = [c for c in cells if c]
        if len(cells) < 4:
            continue
        pct = next((c for c in reversed(cells) if re.fullmatch(r"\d{1,3}(\.\d+)?%?", c.replace("％", "%"))), None)
        if pct is None:
            continue
        results.append((cells[0], float(pct.rstrip("%"))))
    return results


def build_votes():
    out = []
    for doc in filings():
        if doc["docTypeCode"] != "180":
            continue
        path = DOCS / f"{doc['docID']}_1.zip"
        if not path.exists():
            continue
        for label, support in read_vote_results(path):
            out.append({"edinet_code": doc["edinetCode"], "doc_id": doc["docID"], "submitted": doc["submitDateTime"][:10],
                        "item": label, "support_pct": support})
    if out:
        with open(EDINET / "votes.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0]))
            w.writeheader()
            w.writerows(out)
    return out


NOT_A_NAME = r"(?i)\b(elect|re-?elect|director|nominee|as|to|the|board|of|member|statutory|auditor|alternate|appoint|and|who|is|audit|committee|supervisory|substitute)\b"
PROPOSED_WINDOW_DAYS = 45  # A report this close before the meeting describes the board proposed for it.


def nominee_tokens(proposal_text):
    """'Elect Director Saito, Noboru' -> {'saito', 'noboru'}"""
    return {w.lower() for w in re.findall(r"[A-Za-z]{2,}", re.sub(NOT_A_NAME, " ", proposal_text))}


class JapanFacts:
    """Facts for one Japanese director election, from filings submitted before the meeting date."""

    def __init__(self):
        self.ok = (EDINET / "boards.csv").exists() and (EDINET / "companies.csv").exists()
        if not self.ok:
            return
        with open(EDINET / "companies.csv", encoding="utf-8", newline="") as f:
            self.code = {r["company_id"]: r["edinet_code"] for r in csv.DictReader(f) if r["edinet_code"]}
        self.reports = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # code -> (submitted, doc) -> part -> directors
        with open(EDINET / "boards.csv", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                self.reports[r["edinet_code"]][(r["submitted"], r["doc_id"])][r["part"]].append(r)
        self.votes = defaultdict(list)  # code -> [(submitted, item, support)]
        if (EDINET / "votes.csv").exists():
            with open(EDINET / "votes.csv", encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    self.votes[r["edinet_code"]].append((r["submitted"], r["item"], float(r["support_pct"])))

    def board_for(self, code, meeting_date):
        """(board, report date, proposed?) from the latest annual report submitted before the meeting."""
        earlier = sorted(k for k in self.reports.get(code, {}) if k[0] < meeting_date)
        if not earlier:
            return None, None, False
        submitted, doc = earlier[-1]
        parts = self.reports[code][(submitted, doc)]
        days = (_date(meeting_date) - _date(submitted)).days
        if days <= PROPOSED_WINDOW_DAYS and parts.get("proposal"):
            return parts["proposal"], submitted, True
        return parts.get("current") or parts.get("proposal"), submitted, False

    def for_row(self, row):
        if not self.ok or row["country"] != "Japan" or row["proposal_type"] != "DIRECTOR_ELECTION":
            return None
        code = self.code.get(row["company_id"])
        board, submitted, proposed = self.board_for(code, row["meeting_date"]) if code else (None, None, False)
        if not board:
            return {"found": False}
        size = len(board)
        outside = sum(int(d["is_outside"]) for d in board)
        independent = sum(int(d["is_independent"]) for d in board)
        wanted = nominee_tokens(row["proposal_text"])
        match = [d for d in board if wanted and wanted <= set(d["tokens"].split())]
        nominee = match[0] if len(match) == 1 else None
        last = [v for v in self.votes.get(code, []) if v[0] < row["meeting_date"] and (_date(row["meeting_date"]) - _date(v[0])).days <= 400]
        board_names = {d["name"] for d in board}
        director_votes = [s for _, item, s in last if any(n and n in item for n in board_names)]
        nominee_votes = [s for _, item, s in last if nominee and nominee["name"] in item]
        return {
            "found": True, "report_submitted": submitted, "proposed_board": proposed,
            "board_size": size, "outside": outside, "independent": independent,
            "independent_share": independent / size,
            "nominee_found": nominee is not None,
            "nominee_outside": bool(nominee and int(nominee["is_outside"])),
            "nominee_independent": bool(nominee and int(nominee["is_independent"])),
            "nominee_executive": bool(nominee and int(nominee["is_executive"])),
            "nominee_representative": bool(nominee and "代表" in nominee["title"]),
            "nominee_title": nominee["title"] if nominee else "",
            "nominee_last_support": min(nominee_votes) if nominee_votes else None,
            "lowest_director_support_last_agm": min(director_votes) if director_votes else None,
        }


SAFE_MIN_ELECTIONS = 100  # A nominee group is skipped only after this many earlier elections with no MOT.


def nominee_group(facts):
    """The nominee's role, for the skip rule. None when the nominee or the board is unknown."""
    if not facts or not facts.get("found") or not facts.get("nominee_found"):
        return None
    if facts["nominee_representative"]:
        return "representative director"
    if facts["nominee_independent"]:
        return "independent outside director"
    if facts["nominee_outside"]:
        return "outside director"
    return "executive director" if facts["nominee_executive"] else "inside director"


def safe_groups(rows, japan, before_date):
    """Nominee groups NBIM never opposed in at least SAFE_MIN_ELECTIONS earlier elections.

    Only votes from meetings before before_date are used, so this can be applied to later meetings.
    """
    seen = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["meeting_date"] >= before_date or r["nbim_vote"] not in ("FOR", "MOT", "AVSTÅ"):
            continue
        group = nominee_group(japan.for_row(r))
        if group:
            seen[group][0] += 1
            seen[group][1] += r["nbim_vote"] == "MOT"
    return {g for g, (n, mot) in seen.items() if n >= SAFE_MIN_ELECTIONS and mot == 0}


def _date(text):
    import datetime
    return datetime.date.fromisoformat(text[:10])


def main():
    boards = build_boards()
    votes = build_votes()
    reports = {(b["edinet_code"], b["doc_id"]) for b in boards}
    print(f"Annual reports read: {len(reports)}; director rows: {len(boards)}; vote rows: {len(votes)}")


if __name__ == "__main__":
    main()
