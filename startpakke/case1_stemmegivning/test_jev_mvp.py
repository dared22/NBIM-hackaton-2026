"""Tests for the parts of jev_mvp.py that must hold whatever Jev answers."""

import json

import jev_mvp as m


def row(**overrides):
    base = {
        "meeting_id": "1", "item_no": "1", "company_id": "c1", "company": "Acme Inc.", "ticker": "ACM",
        "country": "United States", "market": "DM", "meeting_date": "2026-05-01", "proposal_text": "Elect Director Tanaka, Kunihiko",
        "proponent": "Management", "mgmt_rec": "FOR", "nbim_vote": "CANARY_VOTE", "against_board": "CANARY_AGAINST",
        "rationale_text": "CANARY_RATIONALE", "rationale_section": "CANARY_SECTION", "position_paper": "CANARY_PAPER",
        "mgmt_rec_raw": "For", "nbim_vote_raw": "CANARY_RAW", "year": "2026", "proposal_type": "SAY_ON_PAY",
    }
    return {**base, **overrides}


RULES = m.load_guidelines()["3.3"]


def answers(vote="MOT", p_mot=0.7, confidence=0.8, evidence=0.9, rule_scores=None):
    probs = {"FOR": 1 - p_mot, "MOT": p_mot, "AVSTÅ": 0.0}
    out = {"vote": {"choice": vote, "probabilities": probs, "confidence": confidence}, "evidence_sufficient": {"noul": evidence}}
    for rule_id, score in (rule_scores or {}).items():
        out["rule_" + rule_id.replace(".", "_")] = {"noul": score}
    return out


def test_current_row_labels_never_reach_jev():
    state = m.build_state(row(), RULES, "def14a", m.build_history_index([]), {})
    assert "CANARY" not in json.dumps(state)


def test_history_excludes_same_day_and_future_meetings():
    current = row(meeting_id="now")
    earlier = row(meeting_id="old", meeting_date="2025-05-01", nbim_vote="MOT", rationale_text="old reason")
    same_day = row(meeting_id="same", meeting_date="2026-05-01", nbim_vote="MOT", rationale_text="LEAK")
    future = row(meeting_id="next", meeting_date="2027-05-01", nbim_vote="MOT", rationale_text="LEAK")
    index = m.build_history_index([current, earlier, same_day, future])
    past = m.prior_votes(current, index)
    assert [p["meeting_date"] for p in past] == ["2025-05-01"]
    assert "LEAK" not in json.dumps(past)


def test_levels_add_evidence_step_by_step():
    keys = {level: set(m.build_state(row(), RULES, level, {}, {})) for level in m.LEVELS}
    assert keys["proposal"] == {"proposal"}
    assert keys["rules"] == {"proposal", "candidate_guidelines"}
    assert "nbim_past_votes_same_issue" in keys["history"]
    assert keys["def14a"] - keys["history"] == {"company_filing"}


def test_document_filed_after_meeting_is_refused():
    links = {"1": {"filing_date": "2026-06-01", "file": "x.htm", "url": "u"}}
    try:
        m.def14a_excerpt(row(), links)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_mot_with_a_fired_rule_is_cited_and_automatic():
    d = m.decide(answers(rule_scores={"3.3.6": 0.9, "3.3.4": 0.6}), RULES, "FOR", "rules")
    assert (d["vote"], d["citation"], d["route"]) == ("MOT", "3.3.6", "automatic")


def test_mot_without_a_rule_goes_to_review():
    d = m.decide(answers(rule_scores={"3.3.6": 0.2}), RULES, "FOR", "rules")
    assert d["route"] == "human_review" and "no_citation" in d["review_reason"]


def test_missing_evidence_goes_to_review():
    d = m.decide(answers(evidence=0.1, rule_scores={"3.3.6": 0.9}), RULES, "FOR", "rules")
    assert "insufficient_evidence" in d["review_reason"]


def test_following_the_board_cites_the_voting_principle():
    d = m.decide(answers(vote="FOR", p_mot=0.1), RULES, "FOR", "rules")
    assert (d["citation"], d["route"]) == ("P.1", "automatic")


def test_threshold_overrides_the_top_choice_both_ways():
    assert m.decide(answers(vote="FOR", p_mot=0.3), RULES, "FOR", "proposal", mot_threshold=0.2)["vote"] == "MOT"
    assert m.decide(answers(vote="MOT", p_mot=0.6), RULES, "FOR", "proposal", mot_threshold=0.8)["vote"] == "FOR"


def test_mot_metrics():
    r = m.mot_metrics([True, True, False, False], [True, False, True, False])
    assert (r["tp"], r["fp"], r["fn"]) == (1, 1, 1)
    assert r["precision"] == r["recall"] == 0.5


def test_every_mapped_section_exists_in_the_guidelines():
    sections = m.load_guidelines()
    for mapped in m.TYPE_TO_SECTIONS.values():
        assert all(s in sections for s in mapped)


def test_enriched_sample_keeps_whole_meetings():
    rows = [row(meeting_id=str(i // 2), item_no=str(i), nbim_vote="MOT" if i == 7 else "FOR") for i in range(20)]
    picked = m.select_rows(rows, 2026, n=4, enrich=True)
    assert "3" in {r["meeting_id"] for r in picked}
    assert all(sum(r["meeting_id"] == x["meeting_id"] for r in picked) == 2 for x in picked)
