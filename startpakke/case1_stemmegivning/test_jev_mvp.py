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


def answers(vote="MOT", p_mot=0.7, confidence=0.8, reason=None):
    probs = {"FOR": 1 - p_mot, "MOT": p_mot, "AVSTÅ": 0.0}
    out = {"vote": {"choice": vote, "probabilities": probs, "confidence": confidence}}
    if reason:
        out["reason"] = {"probabilities": reason}
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
    assert [p["meeting_date"] for p in past["same_item"]] == ["2025-05-01"]
    assert past["counts"]["company_votes"] == 1
    assert "LEAK" not in json.dumps(past)


def director(name, date, vote):
    return row(proposal_type="DIRECTOR_ELECTION", proposal_text=f"Elect Director {name}", meeting_date=date, nbim_vote=vote)


def test_history_finds_the_nominee_behind_other_rows():
    others = [director(f"Other{i} Person", "2025-05-01", "FOR") for i in range(6)]
    index = m.build_history_index([director("Ann Berg", "2024-05-01", "MOT"), *others])
    past = m.prior_votes(director("Berg, Ann", "2026-05-01", "FOR"), index)
    assert [p["nbim_vote"] for p in past["same_item"]] == ["MOT"]
    assert past["counts"]["same_item_mot"] == 1 and past["counts"]["last_meeting_mot"] == 0


def test_history_keeps_older_mot_votes_on_other_items():
    others = [director(f"Person X{chr(97 + i)}", "2025-05-01", "FOR") for i in range(6)]
    index = m.build_history_index([director("Cara Dahl", "2023-05-01", "MOT"), *others])
    past = m.prior_votes(director("Ann Berg", "2026-05-01", "FOR"), index)
    assert [p["meeting_date"] for p in past["other_mot_votes_same_type"]] == ["2023-05-01"]
    assert past["counts"]["same_type_mot"] == 1


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


def test_mot_cites_the_highest_rated_rule_and_is_automatic():
    d = m.decide(answers(reason={"3.3.6": 0.6, "3.3.4": 0.3, m.NO_RULE: 0.1}), RULES, "FOR", "rules")
    assert (d["vote"], d["citation"], d["cited_section"], d["route"]) == ("MOT", "3.3.6", "3.3", "automatic")


def test_mot_without_a_rule_goes_to_review():
    d = m.decide(answers(reason={"3.3.6": 0.2, m.NO_RULE: 0.8}), RULES, "FOR", "rules")
    assert d["route"] == "human_review" and "no_citation" in d["review_reason"]


def test_following_the_board_cites_the_voting_principle():
    d = m.decide(answers(vote="FOR", p_mot=0.1), RULES, "FOR", "rules")
    assert (d["citation"], d["route"]) == ("P.1", "automatic")


def band(p):
    return {"p_model": p, "low": 0.1, "flag": 0.5, "high": 0.8}


GOOD_REASON = {"3.3.6": 0.9, m.NO_RULE: 0.1}


def test_score_above_high_is_an_automatic_mot():
    d = m.decide(answers(reason=GOOD_REASON), RULES, "FOR", "rules", triage=band(0.9))
    assert (d["vote"], d["route"]) == ("MOT", "automatic")


def test_score_inside_the_band_goes_to_review_with_a_suggestion():
    flagged = m.decide(answers(vote="FOR", p_mot=0.1, reason=GOOD_REASON), RULES, "FOR", "rules", triage=band(0.6))
    unflagged = m.decide(answers(vote="MOT", reason=GOOD_REASON), RULES, "FOR", "rules", triage=band(0.3))
    assert (flagged["vote"], flagged["jev_vote"], flagged["route"]) == ("MOT", "FOR", "human_review")
    assert (unflagged["vote"], unflagged["jev_vote"], unflagged["route"]) == ("FOR", "MOT", "human_review")
    assert "review_band" in flagged["review_reason"]


def test_score_below_low_follows_the_board():
    d = m.decide(answers(vote="FOR", p_mot=0.1), RULES, "FOR", "rules", triage=band(0.01))
    assert (d["vote"], d["citation"], d["route"]) == ("FOR", "P.1", "automatic")


def test_reason_options_exclude_rules_that_cannot_explain_departing_from_the_board():
    rules = m.load_guidelines()["5.3"]
    assert all(r["avledet"]["handling"] == "MOT" for r in m.reason_options(rules, "FOR"))
    assert len(m.reason_options(rules, "MOT")) == len(rules)
    questions = m.build_questions([r for r in rules if r["avledet"]["handling"] == "FOR"], "rules", "FOR")
    assert "reason" not in questions


def test_threshold_overrides_the_top_choice_both_ways():
    assert m.decide(answers(vote="FOR", p_mot=0.3), RULES, "FOR", "proposal", mot_threshold=0.2)["vote"] == "MOT"
    assert m.decide(answers(vote="MOT", p_mot=0.6), RULES, "FOR", "proposal", mot_threshold=0.8)["vote"] == "FOR"


def test_mot_metrics():
    r = m.mot_metrics([True, True, False, False], [True, False, True, False])
    assert (r["tp"], r["fp"], r["fn"]) == (1, 1, 1)
    assert r["precision"] == r["recall"] == 0.5


VERSIONS = m.load_guideline_versions()


def test_guidelines_follow_the_meeting_date():
    assert [v[1] for v in VERSIONS] == ["2016", "2020", "2023", "2024", "2025"]
    for date, year in (("2019-06-01", "2016"), ("2020-03-31", "2016"), ("2020-04-01", "2020"), ("2023-03-31", "2020"),
                       ("2023-04-01", "2023"), ("2024-03-31", "2023"), ("2024-04-01", "2024"), ("2025-03-31", "2024"),
                       ("2025-04-01", "2025"), ("2026-05-01", "2025")):
        assert m.guidelines_for(date, VERSIONS)[0] == year


def test_rules_added_later_are_not_used_on_earlier_meetings():
    def ids(date, section):
        return {r["id"] for r in m.guidelines_for(date, VERSIONS)[1].get(section, [])}
    assert "3.2.9" not in ids("2021-05-01", "3.2") and "3.2.9" in ids("2024-05-01", "3.2")
    assert "5.3.5" not in ids("2024-05-01", "5.3") and "5.3.5" in ids("2025-05-01", "5.3")
    assert "3.3.8" not in ids("2021-05-01", "3.3") and "3.3.8" in ids("2024-05-01", "3.3")
    assert "2.3.2" not in ids("2023-05-01", "2.3") and "2.3.2" in ids("2024-05-01", "2.3")


def test_every_proposal_type_has_candidate_rules_in_each_edition():
    types = {r["proposal_type"] for r in m.load_votes()}
    assert types <= set(m.TYPE_TO_SECTIONS)
    for _, year, sections in VERSIONS:
        for t in types:
            assert m.candidate_rules(t, sections), (year, t)


def test_rule_ids_are_unique_within_an_edition():
    for path in m.HERE.glob("retningslinjer_*.json"):
        ids = [r["id"] for r in json.loads(path.read_text(encoding="utf-8"))["regler"]]
        assert len(ids) == len(set(ids)), path


def voted(meeting_id, date, vote):
    return row(meeting_id=meeting_id, meeting_date=date, nbim_vote=vote, year=date[:4], rationale_text="")


def test_triage_features_ignore_same_day_and_future_votes():
    from triage_model import FEATURES, build_features
    col = FEATURES.index("company_mot")
    rows = [voted("a", "2024-05-01", "MOT"), voted("b", "2025-05-01", "FOR"), voted("c", "2025-05-01", "MOT"), voted("d", "2026-05-01", "FOR")]
    X = build_features(rows)
    assert list(X[:, col]) == [0, 1, 1, 2]
    changed = build_features(rows[:-1] + [voted("d", "2026-05-01", "MOT")])
    assert (changed[:3] == X[:3]).all()


def test_enriched_sample_keeps_whole_meetings():
    rows = [row(meeting_id=str(i // 2), item_no=str(i), nbim_vote="MOT" if i == 7 else "FOR") for i in range(20)]
    picked = m.select_rows(rows, 2026, n=4, enrich=True)
    assert "3" in {r["meeting_id"] for r in picked}
    assert all(sum(r["meeting_id"] == x["meeting_id"] for r in picked) == 2 for x in picked)
