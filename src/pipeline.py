"""pipeline: NBIM voting decision support."""

import re

from src.data import Decision
from src.evidence import rule_check as rc
from src.models import combined as cm
from src.models import history as bm
from src.models.scoring import best_f1_threshold
from src.rules import board as br
from src.rules import guardrails as rb
from src.rules import policy

YEAR = 2026

RULE_ID = re.compile(r"\brule (\d+\.\d+(?:-AT)?\.\d+)")
GVG_ID = re.compile(r"GVG (\d+\.\d+(?:-AT)?(?:\.\d+)?)")


def opposite(vote):
    return {"FOR": "MOT", "MOT": "FOR"}.get(vote, "")


def decide(board, band, flags):
    """Suggested vote and who decides. `flags` are reasons a person must look."""
    if not board:
        flags = flags + ["the board's recommendation is missing"]
    if band == "send to human":
        flags = ["the model is unsure"] + flags
    vote = opposite(board) if band == "likely AGAINST board" and board else board
    return vote, ("human review" if flags else "automatic"), "; ".join(flags)


def general_decisions(rows=None, state=None):
    """All proposal types from NBIM's published votes: history model plus NBIM's written rules.

    `rows` can be passed in to score altered proposals (the resistance check in tests).
    """
    state = cm.RunState() if state is None else state
    rows = bm.read_votes(rc.VOTES) if rows is None else rows

    # Guardrail, part 2: if a proposal's text is an item this company has voted on
    # before plus extra words, the known item is used for the history lookup.
    def year(r):
        return int(r["meeting_date"][:4])

    rb.restore_known_items(
        [r for r in rows if year(r) == YEAR], [r for r in rows if year(r) < YEAR]
    )
    sections = rc.load_guidelines()
    cand = rc.candidate_sections(rows, sections)
    _, val, _, _ = bm.run_year(rows, YEAR - 1)
    train, test, w, _ = bm.run_year(rows, YEAR)
    known_companies = {r["company_id"] for r in train}
    vocabulary = rb.ballot_vocabulary(r["proposal_text"] for r in train)
    # The combined model: the history model's probability, main's rules, and the two scores exported
    # from Marie's pipeline (Jev and her second model), weighted by a fit on earlier years.
    combo_fit, combo_level = cm.fitted(YEAR, state)
    components = cm.load_components(YEAR)
    abstain = policy.abstain_markets(train)
    papers = rc.load_papers()
    citations = rc.load_citations()
    cache = rc.load_cache()
    rc.attach_scores(val, cand, sections, cache)
    rc.attach_scores(test, cand, sections, cache)
    directors = {(r["meeting_id"], r["item_no"]): r for r in br.load_scored()}
    worded = {(r["meeting_id"], r["item_no"]): r for r in policy.load_scored() if r["rules"]}
    scored = [r for r in val if r["rule_p"] is not None]
    rule_thr = (
        best_f1_threshold([r["rule_p"] for r in scored], [r["y"] for r in scored])
        if scored
        else 1.0
    )
    out = []
    for r in test:
        hits = rb.guard_patterns(r["proposal_text"])
        flags = ["security flag: " + ", ".join(hits)] if hits else []
        if r["company_id"] not in known_companies:
            flags.append("low information: no earlier votes at this company")
        key = (r["meeting_id"], r["item_no"])
        comp = components.get(key)
        prob, band, model, reasons, guide = (
            r["p"],
            r["band"],
            "vote history",
            bm.reasons(w, r["x"]),
            None,
        )
        if comp:
            judged = cm.judge_answer(r, directors.get(key), state)
            prob = cm.score(
                combo_fit,
                cm.inputs_for(
                    r, comp, directors.get(key), worded.get(key), judged["p"] if judged else None
                ),
            )
            band = (
                "likely AGAINST board"
                if prob >= combo_level
                else "likely WITH board"
                if prob < cm.LOW
                else "send to human"
            )
            model = "combined model: vote history, Jev and a second model"
            if judged:
                model = "combined model: vote history and a judge model weighing the proxy facts"
                if judged["p"] >= 0.2:
                    reasons += (
                        f" | the judge model puts this at {judged['p']:.0%}: {judged['reason']}"
                    )
            if comp["jev_vote"] != r["mgmt_rec"] and r["mgmt_rec"]:
                reasons += f" | the Jev decision model recommends {comp['jev_vote']}" + (
                    f", citing GVG {comp['jev_cited_section']}" if comp["jev_cited_section"] else ""
                )
        if hits:
            band = "send to human"
        d = directors.get(key) if directors.get(key, {}).get("rules") else worded.get(key)
        if d and d["rules"]:
            active = [(c, t) for c, t in d["rules"] if d["rule_state"][c] == "active"]
            model = (
                "NBIM rule + facts from the proxy and SEC filings"
                if key in directors and directors[key]["rules"]
                else "NBIM rule + proposal wording"
            )
            reasons = " | ".join(t for _, t in d["rules"])
            guide = ", ".join(dict.fromkeys(c for c, _ in d["rules"]))
            if active and not hits:
                band = "likely AGAINST board"
                # A written rule with its fact does not depend on the company's vote history.
                flags = [f for f in flags if not f.startswith("low information")]
            elif d.get("hold_reason"):
                flags.append(
                    "a rule applies but the tool does not act on it alone: " + d["hold_reason"]
                )
            else:
                flags.append(
                    "rule suspended: NBIM supported the board the last two times "
                    + ", ".join(c for c, _ in d["rules"])
                    + " applied"
                )
        # Guardrail, part 3: wording that does not read like a ballot item brings in a person, whatever
        # the models say. The suggestion is kept; the person decides.
        odd = rb.unusual_wording(r["proposal_text"], vocabulary)
        if odd and not hits:
            flags.append(
                "security flag: the wording does not read like a ballot item (words no earlier ballot used: "
                + ", ".join(odd[:6])
                + ")"
            )
        # Guardrail, part 4: the proxy the AI reader read speaks to an automated reader. The facts read
        # from it are shown, and a person decides.
        if directors.get(key, {}).get("proxy_alert"):
            flags.append(
                'security flag: the proxy statement holds wording addressed to an automated reader ("'
                + directors[key]["proxy_alert"][:120]
                + '")'
            )
        # The tool acts alone on "against" only when the suggestion rests on something a person can
        # check: a rule with its fact or NBIM's own against-vote on the item last time.
        if (
            comp
            and band == "likely AGAINST board"
            and not (d and d["rules"])
            and r["prev_same_item"] != 1
        ):
            flags.append(
                "the models suggest a vote against the board, but no rule, fact or earlier "
                "against-vote on this item backs it"
            )
        # Japan and Korea: a company fact NBIM often acts on brings in a person, unless the tool
        # is already acting alone on "against".
        fact = policy.signal_for(r, state.facts)
        if fact:
            reasons += " | " + fact[1]
            if not (band == "likely AGAINST board" and not flags):
                flags.append("a company fact applies that NBIM often acts on (see the reasons)")
        vote, who, why = decide(r["mgmt_rec"], band, flags)
        market = (r["country"], r["proposal_type"])
        if vote == "MOT" and band == "likely AGAINST board" and market in abstain:
            # In a few markets NBIM casts its against-votes as abstentions (learned from earlier years).
            vote = "AVSTÅ"
            reasons += (
                f" | in {r['country']} NBIM cast {abstain[market][0]} of its {abstain[market][1]} earlier "
                f"against-votes on this proposal type as abstentions"
            )
        if guide:
            pass
        elif fact and fact[0]:
            guide = f"{fact[0]} (NBIM's usual stated reason for against-votes on directors in this market)"
        elif r["rule_p"] is not None and r["rule_p"] >= rule_thr:
            guide = f"GVG {r['rule_section']} (rule check, probability {r['rule_p']:.2f})"
        elif (
            comp
            and comp["jev_cited_section"]
            and comp["jev_vote"] != r["mgmt_rec"]
            and band != "likely WITH board"
        ):
            guide = f"GVG {comp['jev_cited_section']} (named by the Jev decision model)"
        elif band != "likely WITH board" and r["candidates"]:
            guide = f"GVG {r['candidates'][0]} (NBIM's most common stated reason for this proposal type before 2025)"
        else:
            guide = ""
        evidence = ""
        if d and d["rules"] and "f" in d:
            evidence = d.get("evidence_url") or (
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={d['f']['person_cik']}&type=4"
                if d["f"] and d["f"].get("matched")
                else ""
            )
        # The words of the guideline and the page they are on. A rule that fired is quoted
        # itself; otherwise the cited section's introduction is quoted.
        quoted = rc.quote(
            (RULE_ID.findall(reasons) if d and d["rules"] else []) or GVG_ID.findall(guide),
            citations,
        )
        if guide:
            rule_id = d["rule"][0] if d and d["rules"] and d.get("rule") else ""
            paper = rc.paper_for(papers, guide.split(" (")[0].split(",")[0], rule_id)
            if paper:
                guide += f"; position paper: {paper['title']} ({paper['url']})"
        out.append(
            Decision(
                "NBIM votes, all proposal types",
                f"{r['meeting_id']}-{r['item_no']}",
                r["meeting_date"],
                r["company"],
                r["proposal_text"],
                r["mgmt_rec"],
                vote,
                f"{prob:.3f}",
                band,
                who,
                why,
                model,
                reasons,
                guide,
                quoted,
                evidence,
                r["y"],
                r["nbim_vote"],
            )
        )
    return out
