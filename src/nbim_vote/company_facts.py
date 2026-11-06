"""Company facts for a proposal, from documents filed before the meeting. One place for every source.

Sources (all fetched by the src/fetch_*.py scripts, or copied from main):
    Japan  EDINET annual reports and AGM vote results          src/nbim_vote/japan_facts.py
    US     main's AI reading of each proxy (nominee role, independence, chair, attendance, board)
           data/evidence/main/board_nominees.csv and board_meetings.csv
           last year's vote results, SEC 8-K item 5.07          data/evidence/sec_votes/votes.csv
           CEO pay from each proxy (main)                       data/evidence/main/proxy_pay.csv
    Korea  OpenDART annual and half-year reports: the board     data/evidence/dart/executives.csv

What this gives each proposal
    features(row)   numbers for the triage model (-1 when a fact does not apply)
    state(row)      plain facts with their source, for Jev
    groups(row)     labels for the skip rule (src/nbim_vote/jev_mvp.py): proposal type and nominee role
    chair_ceo(row)  True when a US nominee is both CEO and board chair (NBIM rule 1.3.1)

No look-ahead: every source is filtered on its filing date, strictly before the meeting date.
"""

import csv
import datetime
import math
import re
from collections import defaultdict
from pathlib import Path

from nbim_vote.japan_facts import JapanFacts, nominee_group

from nbim_vote.instructions import strip_instructions

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "data" / "evidence"
LAST_AGM_DAYS = 400  # last year's meeting: a vote result filed at most this long before the meeting
NAME_NOISE = r"(?i)\b(elect|re-?elect|director|nominee|as|to|the|board|of|member|and|mr|ms|dr|jr|sr|ii|iii)\b"

FEATURES = (
    "jp_found", "jp_proposed_board", "jp_independent_share", "jp_majority_independent", "jp_third_independent",
    "jp_nominee_found", "jp_nominee_outside", "jp_nominee_executive", "jp_nominee_representative",
    "jp_nominee_last_support", "jp_lowest_support_last_agm",
    "us_found", "us_independent", "us_executive", "us_ceo", "us_board_chair", "us_chair_ceo", "us_under_75pct",
    "us_board_independent_share", "us_controlled", "us_nominee_last_support", "us_lowest_director_support",
    "us_last_pay_support", "us_majority_shareholder_proposal", "us_ceo_pay_log", "us_ceo_pay_25m",
    "kr_found", "kr_board_size", "kr_outside_share", "kr_ceo_chairs_board", "kr_nominee_role",
)
KOREAN_ROLES = {"inside": 0, "outside": 1, "non-executive": 2, "audit committee": 3}


def date(text):
    return datetime.date.fromisoformat(text[:10])


def days_between(earlier, later):
    return (date(later) - date(earlier)).days


def read(path):
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def name_tokens(text):
    text = re.sub(r"\"[^\"]*\"|\([^)]*\)", " ", text)
    return {w.lower() for w in re.findall(r"[A-Za-z]{2,}", re.sub(NAME_NOISE, " ", text))}


def norm_company(name):
    name = re.sub(r"[^A-Z0-9 ]", " ", name.upper().replace("&", " AND "))
    return " ".join(w for w in name.split() if w not in {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "PLC", "THE", "HOLDINGS", "GROUP"})


class CompanyFacts:
    def __init__(self):
        self.japan = JapanFacts()
        # US: main's proxy facts per nominee and per meeting.
        self.us_nominees = defaultdict(list)
        for r in read(EVIDENCE / "main" / "board_nominees.csv"):
            self.us_nominees[(r["company_id"], r["meeting_date"])].append(r)
        self.us_boards = {(r["company_id"], r["meeting_date"]): r for r in read(EVIDENCE / "main" / "board_meetings.csv")}
        # US: last year's vote results.
        self.us_votes = defaultdict(list)
        for r in read(EVIDENCE / "sec_votes" / "votes.csv"):
            if r["support"]:
                self.us_votes[r["company_id"]].append(r)
        # US: CEO pay, keyed by SEC number and meeting date.
        self.cik_by_name = {}
        for r in read(EVIDENCE / "main" / "pay_company_link.csv"):
            if r["cik"]:
                self.cik_by_name[norm_company(r["name_in_votes"])] = r["cik"]
                self.cik_by_name.setdefault(norm_company(r["sec_name"]), r["cik"])
        self.ceo_pay = {}
        for r in read(EVIDENCE / "main" / "proxy_pay.csv"):
            if r["tag"] == "PeoTotalCompAmt" and r["value"]:
                k = (r["cik"], r["meeting_date"])
                if r["period_end"] >= self.ceo_pay.get(k, ("", 0, ""))[0]:
                    self.ceo_pay[k] = (r["period_end"], float(r["value"]), r["filed"], r["accession"])
        # Documents behind each meeting, for the dashboard's links (meeting_documents()).
        self.def14a = {r["meeting_id"]: r for r in read(ROOT / "data" / "def14a" / "kobling.csv") if r["status"] == "ok" and r["url"]}
        self.proxies = {(r["cik"], r["meeting_date"]): r for r in read(EVIDENCE / "main" / "proxy_meetings.csv")
                        if r["status"] == "ok" and r["url"]}
        self.edinet_docs = defaultdict(list)  # edinet code -> [(submitted, doc id, type, description)]
        for r in read(EVIDENCE / "edinet" / "filings.csv"):
            if r["docTypeCode"] in ("120", "130", "180") and r["withdrawalStatus"] in ("0", ""):
                self.edinet_docs[r["edinetCode"]].append((r["submitDateTime"][:10], r["docID"], r["docTypeCode"], r["docDescription"]))
        # Korea: registered directors per report.
        self.kr_reports = defaultdict(lambda: defaultdict(list))
        for r in read(EVIDENCE / "dart" / "executives.csv"):
            if r["registered"] in ("사내이사", "사외이사", "기타비상무이사"):
                self.kr_reports[r["company_id"]][(r["filed"], r["rcept_no"])].append(r)

    # ------------------------------------------------------------------ US
    def us_director(self, row):
        if row["country"] != "United States" or row["proposal_type"] != "DIRECTOR_ELECTION":
            return None
        board = self.us_boards.get((row["company_id"], row["meeting_date"]))
        if not board or not board.get("proxy_filed") or board["proxy_filed"] >= row["meeting_date"]:
            return {"found": False}
        wanted = name_tokens(strip_instructions(row["proposal_text"]))
        # At least two shared name words (one if the ballot gives only one), and exactly one such nominee.
        matches = [n for n in self.us_nominees[(row["company_id"], row["meeting_date"])]
                   if n["found"] == "1" and wanted and len(wanted & name_tokens(n["ballot_name"])) >= min(2, len(wanted))]
        if len(matches) != 1:
            return {"found": False}
        nominee = matches[0]
        size = float(board["board_size"] or 0)
        independent = float(board["independent_directors"] or 0)
        votes = self.last_votes(row)
        own = [float(v["support"]) for v in votes if wanted and len(wanted & name_tokens(v["label"])) >= 2]
        directors = [float(v["support"]) for v in votes if looks_like_person(v["label"])]
        return {
            "found": True, "source": f"proxy statement filed {board['proxy_filed']} ({board.get('proxy_url', '')})",
            "independent": nominee["independent"], "executive": nominee["executive"] == "yes", "ceo": nominee["ceo"] == "yes",
            "board_chair": nominee["board_chair"] == "yes", "under_75pct": nominee["attended_under_75_pct"] == "yes",
            "board_size": size, "independent_share": independent / size if size else None,
            "controlled": board.get("controlled_company") == "yes",
            "last_support": min(own) if own else None, "lowest_director_support": min(directors) if directors else None,
            # For explanations only (src/nbim_vote/explain.py): the proxy rows the facts were read from, and last year's vote filing.
            "nominee_row": nominee, "board_row": board, "proxy_url": board.get("proxy_url", ""),
            "last_votes_url": votes[0]["url"] if votes else "", "last_votes_filed": votes[0]["filed"] if votes else "",
        }

    def last_votes(self, row):
        """Vote lines from last year's meeting: the latest 8-K filed before this meeting, within a year or so."""
        before = [v for v in self.us_votes.get(row["company_id"], []) if v["filed"] < row["meeting_date"]
                  and days_between(v["filed"], row["meeting_date"]) <= LAST_AGM_DAYS]
        if not before:
            return []
        latest = max(v["filed"] for v in before)
        return [v for v in before if v["filed"] == latest]

    def us_pay(self, row):
        if row["country"] != "United States" or row["proposal_type"] != "SAY_ON_PAY":
            return None
        cik = self.cik_by_name.get(norm_company(row["company"]))
        pay = self.ceo_pay.get((cik, row["meeting_date"])) if cik else None
        votes = self.last_votes(row)
        pay_votes = [float(v["support"]) for v in votes if is_pay_vote(v)]
        shareholder = [float(v["support"]) for v in votes if is_shareholder_proposal(v)]
        if not pay and not votes:
            return {"found": False}
        return {
            "found": True,
            "ceo_pay": pay[1] if pay and pay[2] < row["meeting_date"] else None,
            "ceo_pay_source": f"proxy statement filed {pay[2]}" if pay else "",
            "last_pay_support": min(pay_votes) if pay_votes else None,
            "majority_shareholder_proposal": any(s > 50 for s in shareholder),
            # For explanations only: where the pay figure and last year's votes were filed.
            "ceo_pay_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{pay[3].replace('-', '')}/" if pay and pay[2] < row["meeting_date"] and pay[3] else "",
            "last_votes_url": votes[0]["url"] if votes else "", "last_votes_filed": votes[0]["filed"] if votes else "",
        }

    # ------------------------------------------------------------------ Korea
    def korea_director(self, row):
        if row["country"] != "South Korea" or row["proposal_type"] != "DIRECTOR_ELECTION":
            return None
        reports = sorted(k for k in self.kr_reports.get(row["company_id"], {}) if k[0] < row["meeting_date"])
        role = korean_role(strip_instructions(row["proposal_text"]))
        if not reports:
            return {"found": False, "nominee_role": role}
        filed, rcept = reports[-1]
        board = self.kr_reports[row["company_id"]][(filed, rcept)]
        outside = sum(d["registered"] == "사외이사" for d in board)
        ceo_chair = any("대표이사" in d["duties"] + d["position"] and "의장" in d["duties"] for d in board)
        return {"found": True, "source": f"DART report filed {filed} (receipt {rcept})", "filed": filed,
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept}", "board_size": len(board),
                "outside": outside, "outside_share": outside / len(board), "ceo_chairs_board": ceo_chair, "nominee_role": role,
                # For explanations only: the registered directors as listed in the report.
                "directors": [(d["name"], d["position"], d["registered"], d["duties"]) for d in board]}

    # ------------------------------------------------------------------ outputs
    def features(self, row):
        out = dict.fromkeys(FEATURES, -1.0)
        jp = self.japan.for_row(row)
        if jp is not None:
            out["jp_found"] = float(jp["found"])
            if jp["found"]:
                share = jp["independent_share"]
                out.update(jp_proposed_board=float(jp["proposed_board"]), jp_independent_share=share,
                           jp_majority_independent=float(share >= 0.5), jp_third_independent=float(share >= 1 / 3),
                           jp_nominee_found=float(jp["nominee_found"]), jp_nominee_outside=float(jp["nominee_outside"]),
                           jp_nominee_executive=float(jp["nominee_executive"]), jp_nominee_representative=float(jp["nominee_representative"]),
                           jp_nominee_last_support=_num(jp["nominee_last_support"]), jp_lowest_support_last_agm=_num(jp["lowest_director_support_last_agm"]))
        us = self.us_director(row)
        if us is not None:
            out["us_found"] = float(us["found"])
            if us["found"]:
                out.update(us_independent={"yes": 1.0, "no": 0.0}.get(us["independent"], -1.0), us_executive=float(us["executive"]),
                           us_ceo=float(us["ceo"]), us_board_chair=float(us["board_chair"]), us_chair_ceo=float(us["ceo"] and us["board_chair"]),
                           us_under_75pct=float(us["under_75pct"]), us_board_independent_share=_num(us["independent_share"]),
                           us_controlled=float(us["controlled"]), us_nominee_last_support=_num(us["last_support"]),
                           us_lowest_director_support=_num(us["lowest_director_support"]))
        pay = self.us_pay(row)
        if pay is not None and pay["found"]:
            out.update(us_last_pay_support=_num(pay["last_pay_support"]), us_majority_shareholder_proposal=float(pay["majority_shareholder_proposal"]),
                       us_ceo_pay_log=math.log10(pay["ceo_pay"]) if pay["ceo_pay"] else -1.0,
                       us_ceo_pay_25m=float(pay["ceo_pay"] >= 25e6) if pay["ceo_pay"] else -1.0)
        kr = self.korea_director(row)
        if kr is not None:
            out["kr_found"] = float(kr["found"])
            out["kr_nominee_role"] = float(KOREAN_ROLES.get(kr["nominee_role"], -1))
            if kr["found"]:
                out.update(kr_board_size=float(kr["board_size"]), kr_outside_share=kr["outside_share"], kr_ceo_chairs_board=float(kr["ceo_chairs_board"]))
        return [out[k] for k in FEATURES]

    def state(self, row):
        """Plain facts for Jev, with their source. None when nothing is known."""
        jp = self.japan.for_row(row)
        if jp and jp["found"]:
            # Only the nominee's role: board counts made Jev apply the independence rule far more broadly than NBIM does.
            role = nominee_group(jp) or "not matched to a director in the report"
            return {"source": f"EDINET annual securities report submitted {jp['report_submitted']}, before the meeting",
                    "this_nominee": role, "title_in_report": jp["nominee_title"] or None}
        us = self.us_director(row)
        if us and us["found"]:
            out = {"source": us["source"], "independent": us["independent"], "executive": us["executive"], "ceo": us["ceo"],
                   "board_chair": us["board_chair"], "attended_under_75_percent": us["under_75pct"],
                   "board_independent_share": None if us["independent_share"] is None else round(us["independent_share"], 2)}
            if us["last_support"] is not None:
                out["this_nominee_support_at_last_agm_percent"] = us["last_support"]
            return out
        pay = self.us_pay(row)
        if pay and pay["found"]:
            out = {}
            if pay["ceo_pay"]:
                out.update(ceo_total_pay_usd=round(pay["ceo_pay"]), source=pay["ceo_pay_source"])
            if pay["last_pay_support"] is not None:
                out["support_at_last_pay_vote_percent"] = pay["last_pay_support"]
            return out or None
        kr = self.korea_director(row)
        if kr and kr["found"]:
            return {"source": kr["source"], "registered_directors": kr["board_size"], "outside_directors": kr["outside"],
                    "ceo_also_chairs_board": kr["ceo_chairs_board"], "this_nominee_per_ballot": kr["nominee_role"]}
        return None

    def groups(self, row):
        """Labels the skip rule can learn: the proposal type, and the nominee's role where it is known."""
        out = [f"type: {row['proposal_type']}"]
        role = nominee_group(self.japan.for_row(row))
        if role:
            out.append(f"Japan: {role}")
        kr = self.korea_director(row)
        if kr:
            out.append(f"Korea: {kr['nominee_role']}")
        us = self.us_director(row)
        if us and us["found"]:
            role = "chair and CEO" if us["ceo"] and us["board_chair"] else "executive" if us["executive"] else \
                   f"non-executive, independent {us['independent']}"
            out.append(f"US: {role}")
        return out

    def edinet_vote_report(self, row):
        """(doc id, submitted) of the latest EDINET vote-result report (type 180) within a year before the meeting."""
        code = self.japan.code.get(row["company_id"]) if self.japan.ok else None
        found = sorted(d for d in self.edinet_docs.get(code, []) if d[2] == "180" and d[0] < row["meeting_date"]
                       and days_between(d[0], row["meeting_date"]) <= LAST_AGM_DAYS) if code else []
        return (found[-1][1], found[-1][0]) if found else None

    def meeting_documents(self, row):
        """Every input document for this proposal's meeting, filed before the meeting date, the main one first.

        [{"label", "url", "filed", "about"}]. url is "" where no public link exists. EDINET links open EDINET's
        public document viewer by document ID (disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?<id>); the address works
        but is not documented by EDINET.
        """
        date, out, seen = row["meeting_date"], [], set()

        def add(label, url, filed, about):
            if filed and filed[:10] >= date:
                return  # filed on or after the meeting: not an input
            if url and url in seen:
                return
            seen.add(url)
            out.append({"label": label, "url": url, "filed": (filed or "")[:10], "about": about})

        # US: the proxy statement (notice of meeting), last year's vote results, the CEO pay filing.
        link = self.def14a.get(row["meeting_id"])
        if link:
            add("Innkalling / proxy (DEF 14A)", link["url"], link["filing_date"], "Sakslisten, styrets anbefalinger og fakta om kandidatene")
        cik = self.cik_by_name.get(norm_company(row["company"]))
        proxy = self.proxies.get((cik, date)) if cik else None
        if proxy:
            add(f"Innkalling / proxy ({proxy['form']})", proxy["url"], proxy["filed"], "Sakslisten, lederlønn og styrets anbefalinger")
        board = self.us_boards.get((row["company_id"], date))
        if board and board.get("proxy_url"):
            add("Innkalling / proxy (lest av main sin AI-leser)", board["proxy_url"], board.get("proxy_filed", ""),
                "Fakta om styret og kandidatene, med sitater")
        votes = self.last_votes(row) if row["country"] == "United States" else []
        if votes:
            add("Fjorårets stemmeresultater (8-K, punkt 5.07)", votes[0]["url"], votes[0]["filed"], "Oppslutning om hver sak på forrige generalforsamling")
        pay = self.ceo_pay.get((cik, date)) if cik else None
        if pay and pay[3]:
            add("Lønnstabell i proxy (XBRL)", f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{pay[3].replace('-', '')}/",
                pay[2], "Konsernsjefens samlede lønn")
        # Japan: the annual securities report and last year's vote results, from EDINET.
        code = self.japan.code.get(row["company_id"]) if self.japan.ok else None
        if code:
            docs = sorted(d for d in self.edinet_docs.get(code, []) if d[0] < date)
            annual = [d for d in docs if d[2] in ("120", "130")]
            results = [d for d in docs if d[2] == "180" and days_between(d[0], date) <= LAST_AGM_DAYS]
            picked = ([(annual[-1], "Årsrapport (EDINET, 有価証券報告書)")] if annual else []) + \
                     ([(results[-1], "Fjorårets stemmeresultater (EDINET, 臨時報告書)")] if results else [])
            for (filed, doc, _, about), label in picked:
                add(f"{label} {doc}", f"https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?{doc}", filed, about)
        # Korea: the latest DART report on the board.
        reports = sorted(k for k in self.kr_reports.get(row["company_id"], {}) if k[0] < date)
        if reports:
            filed, rcept = reports[-1]
            add(f"Rapport til DART ({self.kr_reports[row['company_id']][(filed, rcept)][0]['report']})",
                f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept}", filed, "Registrerte styremedlemmer og roller")
        return out

    def chair_ceo(self, row):
        us = self.us_director(row)
        return bool(us and us["found"] and us["ceo"] and us["board_chair"])


def _num(value):
    return -1.0 if value is None else float(value)


def looks_like_person(label):
    words = label.split()
    return 2 <= len(words) <= 5 and not re.search(r"(?i)proposal|ratif|approv|compens|amend|plan|auditor|frequency|vote", label)


def is_pay_vote(v):
    text = (v["label"] + " " + v["context"][-150:]).lower()
    return "compensation" in text and "frequency" not in text and "director compensation" not in text


def is_shareholder_proposal(v):
    text = (v["label"] + " " + v["context"][-150:]).lower()
    return "shareholder proposal" in text or "stockholder proposal" in text


def korean_role(text):
    t = text.lower()
    if "audit committee" in t:
        return "audit committee"
    if "non-independent non-executive" in t or "non-executive" in t:
        return "non-executive"
    if "outside director" in t:
        return "outside"
    if "inside director" in t:
        return "inside"
    return "unknown"


SAFE_MIN_ELECTIONS = 100  # A group skips review only after this many earlier proposals with no MOT.


def safe_groups(rows, company, before_date):
    """Groups NBIM never opposed in at least SAFE_MIN_ELECTIONS proposals before before_date."""
    seen = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["meeting_date"] >= before_date or r["nbim_vote"] not in ("FOR", "MOT", "AVSTÅ"):
            continue
        for g in company.groups(r):
            seen[g][0] += 1
            seen[g][1] += r["nbim_vote"] == "MOT"
    return {g for g, (n, mot) in seen.items() if n >= SAFE_MIN_ELECTIONS and mot == 0}


_FACTS = None


def facts():
    """One shared instance: loading every source takes a few seconds."""
    global _FACTS
    if _FACTS is None:
        _FACTS = CompanyFacts()
    return _FACTS
