"""Plain reasons for a recommendation, built in code from checkable facts. No model writes them.

For each proposal:
    reasons         what NBIM did on this item before (with NBIM's own published rationale),
                    the company facts that bear on it (with the filing and, for US proxies, a
                    quote checked against the text), and why the decision rule went the way it did
    guideline_text  the cited guideline in its own words, with edition, page and whether it needs judgement
    evidence_url    a link to the main filing behind the facts

Everything comes from what the pipeline already used: earlier meetings only (prior_votes) and
filings dated before the meeting (company_facts). The row's own vote and rationale are never read.
"""

from functools import lru_cache
from urllib.parse import quote as url_quote

from director_rules import deciding_rule, describe
from jev_mvp import prior_votes

QUOTE_CHARS = 220
SUPPORT_NOTE = 80.0      # last year's support below this is worth showing
PAY_SUPPORT_NOTE = 70.0
STRICT_PAY = 25e6        # NBIM reviews CEO pay of 25 million dollars or more more strictly (GVG 3.3)
PRINCIPLE = ("Voting principle (not a numbered guideline): NBIM's starting point is to support the board, unless "
             "the board is not operating effectively or shareholder rights are not protected.")


def short(text, n=QUOTE_CHARS):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


@lru_cache(maxsize=None)
def edition_rules(edition):
    """Every rule in one edition by id: a citation from code can name a rule outside the proposal type's candidates."""
    from jev_mvp import load_guideline_versions
    for _, year, by_section in load_guideline_versions():
        if year == str(edition):
            return {r["id"]: r for section in by_section.values() for r in section}
    return {}


def guideline_text(citation, rules, edition):
    """The cited rule in its own words: 'GVG 1.3.1 (2025 edition, page 6): "…"'."""
    if citation == "P.1":
        return PRINCIPLE
    rule = next((r for r in rules if r["id"] == citation), None) or edition_rules(edition).get(citation)
    if rule is None:
        return ""
    where = f"{edition} edition" + (f", page {rule['side']}" if rule.get("side") else "")
    judgement = ", needs judgement" if rule["avledet"].get("skjonn") else ""
    return f"GVG {citation} ({where}{judgement}): \"{rule['tekst']}\""


PASSAGE_CHARS = 1500  # the longest passage shown on hover


def note(notes, text, passage, source, url=""):
    """Record the passage a reason line rests on (shown on hover in the dashboard)."""
    if notes is not None and passage:
        notes[text] = {"passage": " ".join(str(passage).split())[:PASSAGE_CHARS], "source": source, "url": url}


def text_link(url, quote):
    """A link that opens the document at the quoted sentence (a text fragment; Chrome, Edge and Safari support it)."""
    words = " ".join(str(quote).split()).split(" ")[:8]
    return f"{url}#:~:text={url_quote(' '.join(words))}" if url and words else url


def history_reasons(row, history_index, notes=None):
    """What NBIM did before at this company: same item first, then same proposal type.
    notes: optional dict that receives the passage behind each line (NBIM's own rationale)."""
    past = prior_votes(row, history_index)
    same, counts = past["same_item"], past["counts"]
    out = []
    mot = [p for p in same if p["nbim_vote"] == "MOT"]
    if mot:
        p = mot[-1]
        why = f": \"{short(p['nbim_rationale'])}\"" if p["nbim_rationale"] else ""
        section = f" ({p['nbim_guideline_section']})" if p["nbim_guideline_section"] else ""
        out.append(f"NBIM voted MOT on this same item on {p['meeting_date']}{section}{why}")
        note(notes, out[-1], p["nbim_rationale"], f"NBIMs publiserte begrunnelse, {p['meeting_date']}")
        if counts["same_item_votes"] > counts["same_item_mot"]:
            out.append(f"NBIM opposed it at {counts['same_item_mot']} of {counts['same_item_votes']} earlier meetings")
    elif same:
        out.append(f"NBIM supported this same item at all {counts['same_item_votes']} earlier meetings, last on {same[-1]['meeting_date']}")
    others = past["other_mot_votes_same_type"]
    if others:
        p = others[-1]
        section = f" ({p['nbim_guideline_section']})" if p["nbim_guideline_section"] else ""
        out.append(f"NBIM voted MOT on another {row['proposal_type'].lower().replace('_', ' ')} item here on "
                   f"{p['meeting_date']}{section}: \"{short(p['proposal'], 80)}\"")
        note(notes, out[-1], f"Forslag: {p['proposal']}" + (f" — NBIMs begrunnelse: {p['nbim_rationale']}" if p["nbim_rationale"] else ""),
             f"NBIMs stemme, {p['meeting_date']}")
    if not counts["company_votes"]:
        out.append("no earlier NBIM votes at this company in the data")
    elif not same and not others:
        out.append(f"no earlier NBIM vote on this item; NBIM opposed {counts['company_mot']} of {counts['company_votes']} "
                   f"earlier proposals at this company")
    return out


def _quoted(nominee, field):
    """A proxy quote, only when the reader's quote was found in the document."""
    if nominee.get(f"{field}_verified") == "1" and nominee.get(f"{field}_quote"):
        return f" (proxy: \"{short(nominee[f'{field}_quote'], 160)}\")"
    return ""


def _vote_line(known, row, pick):
    """The 8-K line behind last year's support figure: the lowest-support line that `pick` accepts."""
    lines = [v for v in known.last_votes(row) if pick(v)]
    return min(lines, key=lambda v: float(v["support"])) if lines else None


def fact_reasons(row, known, notes=None):
    """(reasons, evidence_url) from company facts filed before the meeting.
    notes: optional dict that receives the passage behind each line (a proxy quote checked against the text,
    or the 8-K text around a vote result)."""
    us = known.us_director(row)
    if us and us["found"]:
        n, b = us["nominee_row"], us["board_row"]
        out, passages = [], []
        url, filed = us["proxy_url"], b["proxy_filed"]

        def proxy_quote(row_, field):
            ok = row_.get(f"{field}_verified") == "1" and row_.get(f"{field}_quote")
            return (row_[f"{field}_quote"], f"Proxy (DEF 14A) levert {filed}", text_link(url, row_[f"{field}_quote"])) if ok else None

        if us["ceo"] and us["board_chair"]:
            out.append("the nominee is both CEO and board chair" + _quoted(n, "board_chair"))
            passages.append(proxy_quote(n, "board_chair") or proxy_quote(n, "ceo"))
        elif us["executive"]:
            out.append("the nominee is an executive of the company" + _quoted(n, "executive"))
            passages.append(proxy_quote(n, "executive"))
        if us["independent"] == "no" and not us["executive"]:
            out.append("the nominee is not independent" + _quoted(n, "independent"))
            passages.append(proxy_quote(n, "independent"))
        if us["under_75pct"]:
            out.append("the nominee attended less than 75% of board meetings" + _quoted(n, "attended_under_75_pct"))
            passages.append(proxy_quote(n, "attended_under_75_pct"))
        if us["independent_share"] is not None and us["independent_share"] < 0.5:
            out.append(f"only {b['independent_directors']} of {b['board_size']} directors are independent")
            passages.append(proxy_quote(b, "independent_directors"))
        if us["controlled"]:
            out.append("the company is a controlled company")
            passages.append(proxy_quote(b, "controlled_company"))
        if us["last_support"] is not None and us["last_support"] < SUPPORT_NOTE:
            out.append(f"the nominee got {us['last_support']:.1f}% support at last year's meeting (8-K filed {us['last_votes_filed']})")
            from company_facts import name_tokens
            wanted = name_tokens(row["proposal_text"])
            line = _vote_line(known, row, lambda v: len(wanted & name_tokens(v["label"])) >= 2)
            passages.append((f"{line['label']}: {line['support']} % for — fra 8-K: …{line['context']}", f"8-K levert {line['filed']}", line["url"])
                            if line else None)
        if not out:
            out.append(f"the proxy shows the nominee as {'independent' if us['independent'] == 'yes' else 'of unknown independence'}, "
                       f"not an executive, attendance not flagged")
            passages.append(proxy_quote(n, "independent"))
        out = [f"{x}; proxy filed {b['proxy_filed']}" if i == 0 else x for i, x in enumerate(out)]
        for text, found in zip(out, passages):
            if found:
                note(notes, text, *found)
        return out, us["proxy_url"]
    pay = known.us_pay(row)
    if pay and pay["found"]:
        out = []
        if pay["ceo_pay"]:
            strict = ", at or above the level NBIM reviews more strictly" if pay["ceo_pay"] >= STRICT_PAY else ""
            out.append(f"CEO total pay ${pay['ceo_pay'] / 1e6:.1f} million{strict} ({pay['ceo_pay_source']})")
        if pay["last_pay_support"] is not None:
            low = ", which is low" if pay["last_pay_support"] < PAY_SUPPORT_NOTE else ""
            out.append(f"last year's pay vote got {pay['last_pay_support']:.1f}% support{low} (8-K filed {pay['last_votes_filed']})")
            from company_facts import is_pay_vote
            line = _vote_line(known, row, is_pay_vote)
            if line:
                note(notes, out[-1], f"{line['label']}: {line['support']} % for — fra 8-K: …{line['context']}",
                     f"8-K levert {line['filed']}", line["url"])
        if pay["majority_shareholder_proposal"]:
            out.append("a shareholder proposal got majority support at last year's meeting")
        return out, pay["ceo_pay_url"] or pay["last_votes_url"]
    jp = known.japan.for_row(row)
    if jp and jp["found"]:
        from japan_facts import nominee_group
        role = nominee_group(jp)
        out = [f"EDINET annual report {jp['report_doc_id']} submitted {jp['report_submitted']}"
               + (f": the nominee is a {role}" + (f", title \"{jp['nominee_title']}\"" if jp["nominee_title"] else "")
                  if role else ": the nominee was not matched to a director in the report"),
               f"{jp['independent']} of {jp['board_size']} directors are independent"
               + (" (board as proposed for this meeting)" if jp["proposed_board"] else "")]
        if jp["nominee_last_support"] is not None:
            out.append(f"the nominee got {jp['nominee_last_support']:.1f}% support at last year's meeting")
        return out, ""
    kr = known.korea_director(row)
    if kr and kr["found"]:
        out = [f"DART report filed {kr['filed']}: {kr['outside']} of {kr['board_size']} registered directors are outside directors"
               + ("; the CEO also chairs the board" if kr["ceo_chairs_board"] else ""),
               f"the ballot describes the nominee as {kr['nominee_role']}"]
        return out, kr["url"]
    return [], ""


def decision_reasons(row, decision, signals=(), instruction_found=False, notes=None, edition=""):
    """Why the decision rule went this way. signals: director rules that fired (director_rules.rule_states).
    notes: optional dict that receives the guideline's own words behind each rule line."""
    out = describe(signals)
    for text, signal in zip(list(out), signals):
        rule = edition_rules(edition).get(signal[0]) if edition else None
        if rule:
            note(notes, text, f"GVG {signal[0]}: {rule['tekst']}",
                 f"NBIMs stemmeretningslinjer, {edition}-utgaven" + (f", side {rule['side']}" if rule.get("side") else ""))
    rule_mot = deciding_rule(signals)
    board = row["mgmt_rec"]
    if decision["vote"] != board and decision["vote"] != "AVSTÅ":
        if board == "MOT":
            who = "the triage model expects" if decision["p_mot"] == "" else "Jev and the triage model both expect"
            out.append(f"the board recommends MOT, but {who} NBIM to support the proposal")
        elif not rule_mot:
            if decision["p_mot"] == "":
                out.append(f"the triage model ({float(decision['p_model']):.2f}) is at or above its flag for MOT")
            else:
                out.append(f"Jev (p(MOT) {float(decision['p_mot']):.2f}) and the triage model ({float(decision['p_model']):.2f}) both point to MOT")
    if decision["vote"] == "AVSTÅ":
        out.append("Jev's first choice is to abstain")
    if decision["vote"] != "FOR" and not decision["citation"]:
        out.append("no guideline fits the recommendation: a person decides")
    if instruction_found:
        out.append("the text contains an instruction to the reader; it was removed before Jev read it and the proposal goes to a person")
    return out


def explain(row, decision, rules, edition, history_index, known, signals=(), instruction_found=False, differ=None):
    """differ: against_board.Signals, for the record behind a FOR on a board MOT or an abstention."""
    notes = {}
    facts, url = fact_reasons(row, known, notes)
    reasons = decision_reasons(row, decision, signals, instruction_found, notes, edition)
    if differ is not None:
        for fired, why in (differ.support(row), differ.abstain(row)):
            if fired and decision["vote"] in ("FOR", "AVSTÅ") and decision["vote"] != row["mgmt_rec"]:
                reasons.append(why)
    reasons += history_reasons(row, history_index, notes) + facts
    notice = notice_excerpt(row, known)
    if notice:
        line = f"relevant passages in the notice of meeting (DEF 14A filed {notice['filed']}), found by keywords for this proposal type"
        reasons.append(line)
        note(notes, line, notice["excerpt"], f"Innkalling (DEF 14A) levert {notice['filed']}", notice["source_url"])
    quoted = guideline_text(decision["citation"], rules, edition)
    source = decision.get("citation_source", "")
    if quoted and source and source != "voting principle":
        quoted += f" [cited from: {source}]"
    return {
        "reasons": " | ".join(reasons),
        "guideline_text": quoted,
        "evidence_url": url,
        # The passage behind a reason line, by its text, where one exists (shown on hover in the dashboard).
        "passages": notes,
    }


def notice_excerpt(row, known):
    """Sentences from the downloaded notice of meeting (DEF 14A) that match this proposal: the nominee's name, or
    keywords for its type. Only US meetings with a filing before the meeting date (jev_mvp.def14a_excerpt)."""
    link = getattr(known, "def14a", {}).get(row["meeting_id"])
    if not link:
        return None
    from jev_mvp import def14a_excerpt
    return def14a_excerpt(row, {row["meeting_id"]: link})
