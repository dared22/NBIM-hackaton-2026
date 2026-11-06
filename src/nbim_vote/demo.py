"""Paste an agenda, get FOR / MOT / AVSTÅ per proposal, with the deciding guideline and routing.

The same pipeline as the evaluation (jev_mvp.py), applied to a meeting that has no votes yet:
proposal type from the text (classify.py) -> instruction filter -> guidelines in force on the date
-> NBIM's earlier votes at the company and company facts filed before the date -> (Jev, optional) ->
triage model -> combined score against the previous 12 months -> decision and citation.

By default it runs without Jev and calls no API, so no API key is needed; it takes well under a minute.
Run from the repository root:
    python -m nbim_vote.demo data/demo/hp_2026-04-16.txt --company "HP Inc." --date 2026-04-16
    python -m nbim_vote.demo - --company "Acme" --country Norway --date 2026-05-01 < agenda.txt
    python -m nbim_vote.demo data/demo/hp_2026-04-16.txt --company "HP Inc." --date 2026-04-16 --jev   # also ask Jev (TYPESAFE_API_KEY)

Citations come from the rules in code, NBIM's earlier reasons and a text model (src/nbim_vote/citations.py);
with --jev, --cite jev uses Jev's choice instead.

Agenda format: one proposal per line, as on the ballot. Lines starting with "#" are ignored.
"SH: <text>" marks a shareholder proposal; the board is then assumed to recommend MOT.
"[board: FOR]" or "[board: MOT]" at the end of a line sets the board's recommendation.

The company is matched by name to NBIM's earlier votes; a new name gets no history.
Only meetings with company filings in the data get recommendations (SEC for US listings, EDINET for Japan,
DART for South Korea); for any other meeting the demo says so and stops.
DEF 14A excerpts are not fetched here (the system is fitted at the history level).
"""

import argparse
import csv
import os
import re
import sys
from pathlib import Path

from nbim_vote.classify import proposal_type
from nbim_vote.explain import explain
from nbim_vote.company_facts import safe_groups
from nbim_vote.director_rules import deciding_rule, needs_person as rule_needs_person, rule_states
from nbim_vote.company_facts import facts as company_facts
from nbim_vote.against_board import Signals
from nbim_vote.citations import Citer
from nbim_vote.confidence import Calibrator, raw_confidence
from nbim_vote.explain import fact_reasons
from nbim_vote.jev_mvp import (COMBINATION, COMBINATION_NO_JEV, NO_JEV, RUNS, JevClient, build_history_index, build_questions, build_state, candidate_rules, combined_score,
                     decide, guidelines_for, has_instruction, live_review, load_combination, load_guideline_versions,
                     load_votes, model_answers, scores_for_year)
from nbim_vote.triage_model import score_new

BOARD = re.compile(r"\s*\[board:\s*(FOR|MOT)\]\s*$", re.I)


def parse_agenda(text):
    """[(proposal_text, proponent, board recommendation)]"""
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        proponent = "Management"
        if line[:3].upper() == "SH:":
            proponent, line = "Shareholder", line[3:].strip()
        m = BOARD.search(line)
        board = m.group(1).upper() if m else ("MOT" if proponent == "Shareholder" else "FOR")
        items.append((BOARD.sub("", line), proponent, board))
    return items


def normalise(name):
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def find_company(rows, name):
    """(company_id, market, country) from NBIM's earlier votes, or None for a company not seen before."""
    wanted = normalise(name)
    for r in reversed(rows):
        if normalise(r["company"]) == wanted:
            return r["company_id"], r["market"], r["country"]
    return None


def build_rows(items, company, company_id, country, market, date):
    return [{
        "meeting_id": f"demo-{company_id}-{date}", "item_no": str(i), "proposal_number": str(i), "company_id": company_id,
        "company": company, "ticker": "", "country": country, "market": market, "meeting_date": date, "year": date[:4],
        "proposal_text": text, "proponent": proponent, "mgmt_rec": board, "mgmt_rec_raw": board.title(),
        "proposal_type": proposal_type(text, proponent),
        # No answer key: the meeting has not happened.
        "nbim_vote": "", "nbim_vote_raw": "", "against_board": "", "rationale_text": "", "rationale_section": "",
        "position_paper": "", "injection_flag": "0",
    } for i, (text, proponent, board) in enumerate(items, 1)]


class NoDataError(ValueError):
    """The meeting has no company filings in the data, so the system does not recommend on it."""


def vote_confidence(vote, p_mot):
    """The raw value: p(MOT) for MOT or AVSTÅ, otherwise 1 - p(MOT). See confidence.py for the calibrated one."""
    return raw_confidence(vote, p_mot)


def calibrator(date, no_jev):
    """Calibrated confidence from the dashboard's built predictions before `date`, if they exist (dashboard_data.py)."""
    path = Path(__file__).resolve().parents[2] / "data" / "outputs" / "dashboard" / f"predictions_{'nojev' if no_jev else 'jev'}.csv"
    if not path.exists():
        return Calibrator([])
    with open(path, encoding="utf-8", newline="") as f:
        return Calibrator([r for r in csv.DictReader(f) if r["meeting_date"] < date])


def run_agenda(items, company, date, country=None, market=None, use_jev=False, dry_run=False, cite="code"):
    """Recommendations for one agenda. items: [(proposal_text, proponent, board)] as parse_agenda gives.

    Returns a dict with the meeting's details and one result per proposal. Calls no API unless use_jev is set
    (dry_run uses a stub instead). Raises ValueError when the company is unknown and no country is given, and
    NoDataError when there are no company filings behind the meeting (the data covers SEC filings for US listings,
    EDINET for Japan and DART for South Korea): the system only recommends where it has documents to stand on.
    """
    no_jev = not (use_jev or dry_run)
    if no_jev and cite == "jev":
        raise ValueError("Citations from Jev need Jev.")
    rows = load_votes()
    combination = load_combination(COMBINATION_NO_JEV if no_jev else COMBINATION)
    level = load_combination()["level"]  # the evidence level Jev's answers were fitted on
    found = find_company(rows, company)
    if found:
        company_id, known_market, known_country = found
        earlier_proposals = sum(r["company_id"] == company_id and r["meeting_date"] < date for r in rows)
    else:
        if not country:
            raise ValueError("This company is not in NBIM's earlier votes, so a country is needed.")
        company_id, known_market, known_country, earlier_proposals = f"new:{normalise(company)}", "DM", country, 0
    country, market = country or known_country, market or known_market
    new_rows = build_rows(items, company, company_id, country, market, date)
    known = company_facts()
    documents = known.meeting_documents(new_rows[0]) if new_rows else []
    if not documents:
        raise NoDataError(f"No company filings in the data for {company} ({country}) before {date}. The system only "
                          f"recommends where it has documents behind the meeting: SEC filings for US listings, EDINET "
                          f"for Japan, DART for South Korea.")

    versions = load_guideline_versions()
    history_index = build_history_index([r for r in rows if r["meeting_date"] < date])
    triage = score_new(rows, new_rows)
    client = None if no_jev else JevClient(RUNS / ("cache_DRY_RUN.jsonl" if dry_run else "cache.jsonl"), dry_run=dry_run)

    answered = []
    for row, p_model in zip(new_rows, triage):
        version, by_section = guidelines_for(row["meeting_date"], versions)
        rules = candidate_rules(row["proposal_type"], by_section)
        state = build_state(row, rules, level, history_index, {})
        if no_jev:
            answers, p_mot = model_answers(p_model, combination["model_flag"]), None
        else:
            answers = client.ask(state, build_questions(rules, level, row["mgmt_rec"]))["answers"]
            p_mot = answers["vote"]["probabilities"].get("MOT", 0.0)
        score = combined_score(row, p_mot, p_model, history_index, combination)
        answered.append((row, version, rules, by_section, answers, p_model, score))

    year = int(date[:4])
    earlier = [(d, s) for y in (year - 1, year)
               for d, s in scores_for_year(y, level, combination, rows, history_index, use_jev=not no_jev) if d < date]
    in_share = live_review([date] * len(answered), [x[6] for x in answered], combination["review_share"], earlier)
    skip = safe_groups(rows, known, f"{year}-01-01")
    states = rule_states(rows, known, guidelines_for, versions, extra=new_rows)
    citer = Citer(rows, f"{year}-01-01") if cite == "code" else None
    differ = Signals(rows, f"{year}-01-01")
    calibrate = calibrator(date, no_jev)

    results = []
    for (row, version, rules, by_section, answers, p_model, score), share_hit in zip(answered, in_share):
        safe = any(g in skip for g in known.groups(row))
        signals = states.get((row["meeting_id"], row["item_no"]), [])
        found_instruction = has_instruction(row["proposal_text"])
        cite_fn = None
        if citer:
            facts_text = " ".join(fact_reasons(row, known)[0])
            cite_fn = (lambda vote, row=row, by_section=by_section, signals=signals, facts_text=facts_text:
                       citer.cite(row, vote, by_section, history_index, signals, facts_text))
        d = decide(answers, rules, row["mgmt_rec"], level, p_model=p_model, in_review_share=share_hit and not safe,
                   instruction_found=found_instruction, model_flag=combination["model_flag"],
                   rule_mot=deciding_rule(signals), rule_review=rule_needs_person(signals), cite=cite_fn,
                   support=differ.support(row)[0], abstain=differ.abstain(row)[0])
        why = explain(row, d, rules, version, history_index, known, signals, found_instruction, differ)
        results.append({
            "item_no": int(row["item_no"]), "proposal_text": row["proposal_text"], "proposal_type": row["proposal_type"],
            "proponent": row["proponent"], "mgmt_rec": row["mgmt_rec"], "vote": d["vote"], "route": d["route"],
            "review_reason": d["review_reason"], "p_mot": d["p_mot"], "p_model": p_model, "p_combined": score,
            "confidence": calibrate(d["vote"], row["mgmt_rec"], score)[0],
            "confidence_basis": calibrate(d["vote"], row["mgmt_rec"], score)[1], "citation": d["citation"],
            "citation_source": d["citation_source"], "guideline_text": why["guideline_text"],
            "reasons": [x for x in why["reasons"].split(" | ") if x], "evidence_url": why["evidence_url"],
            "guideline_edition": version, "passages": why["passages"],
        })
    return {"company": company, "date": date, "country": country, "market": market, "known_company": bool(found),
            "earlier_proposals": earlier_proposals, "edition": answered[0][1] if answered else "",
            "model": NO_JEV + " (no Jev)" if no_jev else client.model, "review_share": combination["review_share"],
            "cite": cite, "company_id": company_id, "documents": documents, "results": results}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("agenda", help="a text file with one proposal per line, or - for standard input")
    p.add_argument("--company", required=True)
    p.add_argument("--country", help="needed for a company NBIM has not voted at before")
    p.add_argument("--market", choices=("DM", "EM"), help="developed or emerging market; taken from history when known")
    p.add_argument("--date", required=True, help="meeting date, YYYY-MM-DD")
    p.add_argument("--jev", action="store_true", help="also ask Jev (needs TYPESAFE_API_KEY); without it, no API is called")
    p.add_argument("--dry-run", action="store_true", help="run the Jev path with a stub that follows the board (no API call)")
    p.add_argument("--cite", choices=("code", "jev"), default="code", help="citations from code (default) or from Jev (needs --jev)")
    p.add_argument("--no-jev", action="store_true", help=argparse.SUPPRESS)  # the default now; kept so old commands still work
    a = p.parse_args()
    if not (a.jev or a.dry_run) and a.cite == "jev":
        p.error("--cite jev needs Jev: add --jev.")
    if a.jev and not a.dry_run and not os.environ.get("TYPESAFE_API_KEY"):
        # Checked before any work, so a missing key fails at once and only when Jev is asked for.
        p.error("--jev needs TYPESAFE_API_KEY (in .env or the environment). Leave out --jev to run without Jev.")

    text = sys.stdin.read() if a.agenda == "-" else Path(a.agenda).read_text(encoding="utf-8")
    items = parse_agenda(text)
    if not items:
        raise SystemExit("No proposals found in the agenda.")
    try:
        out = run_agenda(items, a.company, a.date, a.country, a.market, use_jev=a.jev, dry_run=a.dry_run, cite=a.cite)
    except NoDataError as e:
        raise SystemExit(f"No recommendation: {e}")
    except ValueError as e:
        p.error(str(e))

    if out["known_company"]:
        print(f"{a.company}: NBIM has voted at this company before ({out['earlier_proposals']} earlier proposals).")
    else:
        print(f"{a.company}: no earlier NBIM votes, so no history.")
    if not (a.jev or a.dry_run):
        print("*** NO JEV: the triage model, the director rules and the code citations decide. ***")
    elif a.dry_run:
        print("*** DRY RUN: Jev is replaced by a stub that follows the board. ***")
    print(f"\n{a.company}, {a.date}, {out['country']} ({out['market']}). Guidelines: {out['edition']} edition. "
          f"Jev model: {out['model']}. Citations: {a.cite}.")
    print(f"Review: proposals in the top {out['review_share']:.0%} of the previous 12 months' scores, every MOT, "
          f"every AVSTÅ and every departure from the board.\n")
    for r in out["results"]:
        route = "person" if r["route"] == "human_review" else "automatic"
        print(f"{r['item_no']:>3}. {r['proposal_text'][:90]}")
        print(f"     {r['proposal_type']}, board {r['mgmt_rec']}  ->  {r['vote']}   ({route}{': ' + r['review_reason'] if r['review_reason'] else ''})")
        jev = f"Jev p(MOT) {r['p_mot']:.2f}, " if r["p_mot"] != "" else ""
        print(f"     {jev}triage model {r['p_model']:.2f}, combined {r['p_combined']:.2f}, confidence {r['confidence']:.0%}")
        print(f"     {r['guideline_text'] or 'No guideline found: a person decides.'}")
        for reason in r["reasons"]:
            print(f"       - {reason}")
        if r["evidence_url"]:
            print(f"     Evidence: {r['evidence_url']}")
    if out["documents"]:
        print("\nInput documents for this meeting (filed before it):")
        for d in out["documents"]:
            print(f"  - {d['label']} (filed {d['filed']}){': ' + d['url'] if d['url'] else ''}")
    print("\nEvery recommendation is a suggestion; a person makes the final call on each one sent for review.")


if __name__ == "__main__":
    main()
