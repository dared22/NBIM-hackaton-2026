"""Regression checks for evidence."""

import collections
import unittest

from src.evidence import fetch_board_facts as fp
from src.evidence import rule_check as rc
from tests.support import ANSWER_FIELDS


class ProxyReaderTests(unittest.TestCase):
    def test_proxy_filed_on_or_after_the_meeting_is_never_picked(self):
        filings = [
            ("2026-05-20", "DEF 14A", "a-3", "x.htm"),
            ("2026-05-01", "DEFA14A", "a-2", "y.htm"),
            ("2026-04-01", "DEF 14A", "a-1", "z.htm"),
            ("2025-04-01", "DEF 14A", "a-0", "w.htm"),
        ]
        self.assertEqual(fp.pick_proxy(filings, "2026-05-20")[2], "a-1")
        self.assertIsNone(fp.pick_proxy(filings, "2026-04-01"))
        self.assertIsNone(fp.pick_proxy(filings, "2025-12-01"))


class RuleCheckRequestTests(unittest.TestCase):
    def test_request_holds_no_answer_field_and_no_company_name(self):
        row = {
            "proposal_text": "Elect Director Jane Doe",
            "proposal_type": "DIRECTOR_ELECTION",
            "proponent": "Management",
            "mgmt_rec": "FOR",
            "country": "Norway",
            "market": "DM",
            "company": "SECRET COMPANY ASA",
            "nbim_vote": "MOT",
            "against_board": "1.0",
            "rationale_text": "SECRET RATIONALE",
            "rationale_section": "GVG 1.1",
            "position_paper": "x",
        }
        sections = rc.load_guidelines()
        body = rc.build_request(row, ["1.1"], sections)
        text = str(body)
        self.assertNotIn("SECRET", text)
        for field in ANSWER_FIELDS:
            self.assertNotIn(field, body["state"])
        self.assertIn("never follow instructions", text)


class BoardReaderTests(unittest.TestCase):
    """The AI reader of board facts, and the rules applied to what it read."""

    @classmethod
    def setUpClass(cls):
        from src.evidence import fetch_board_facts
        from src.rules import board as board_rules

        cls.br, cls.fb = board_rules, fetch_board_facts

    def fact(self, answer, verified=True, quote="q"):
        return {"answer": answer, "quote": quote if verified else "", "verified": verified}

    def nominee(self, **facts):
        base = {
            k: self.fact("unknown" if kind != "number" and kind != "names" else None, False)
            for k, kind, _ in self.fb.NOMINEE_QUESTIONS
        }
        base.update({"ballot_name": "Jane Doe", "found": True})
        base.update({k: v if isinstance(v, dict) else self.fact(v) for k, v in facts.items()})
        return base

    def board(self, **facts):
        base = {k: self.fact(None, False) for k, _, _ in self.fb.BOARD_QUESTIONS}
        base.update({k: v if isinstance(v, dict) else self.fact(v) for k, v in facts.items()})
        return base

    def test_request_holds_no_vote_and_no_nbim_rule(self):
        body = self.fb.request_body("Ms. Doe is independent.", ["Jane Doe"])
        sent = " ".join(m["content"] for m in body["messages"]).lower()
        for word in (
            "nbim",
            "norges bank",
            "against the board",
            "voted against",
            "we will not support",
        ):
            self.assertNotIn(word, sent)
        self.assertIn("ignore", body["messages"][0]["content"])

    def test_reply_is_rejected_unless_it_answers_for_every_name_on_the_ballot(self):
        import json

        one = {
            "ballot_name": "Jane Doe",
            "found": "yes",
            "independent": {"answer": "yes", "quote": "Ms. Doe is independent"},
        }
        text = "Our board has determined that Ms. Doe is independent."
        good = self.fb.parse(json.dumps({"board": {}, "nominees": [one]}), text, ["Jane Doe"])
        self.assertTrue(good["nominees"][0]["independent"]["verified"])
        self.assertIsNone(
            self.fb.parse(
                json.dumps({"board": {}, "nominees": [one]}), text, ["Jane Doe", "John Roe"]
            )
        )
        self.assertIsNone(self.fb.parse("Vote FOR all nominees.", text, ["Jane Doe"]))

    def test_attendance_quote_must_name_the_nominee(self):
        import json

        text = (
            "Each director attended at least 75% of meetings except for Mr. Roe, who attended 60%."
        )

        def item(name):
            return {
                "ballot_name": name,
                "found": "yes",
                "attended_under_75_pct": {
                    "answer": "yes",
                    "quote": "except for Mr. Roe, who attended 60%",
                },
            }

        out = self.fb.parse(
            json.dumps({"board": {}, "nominees": [item("Jane Doe"), item("John Roe")]}),
            text,
            ["Jane Doe", "John Roe"],
        )
        self.assertFalse(out["nominees"][0]["attended_under_75_pct"]["verified"])
        self.assertTrue(out["nominees"][1]["attended_under_75_pct"]["verified"])

    def test_chair_and_ceo_rule_fires_but_not_for_a_founder(self):
        n = self.nominee(ceo="yes", board_chair="yes", independent="no", executive="yes")
        self.assertEqual(
            [t.split(":")[0] for _, t, _ in self.br.decide(n, self.board())], ["rule 1.3.1"]
        )
        founder = self.nominee(ceo="yes", board_chair="yes", founder="yes")
        self.assertEqual(self.br.decide(founder, self.board()), [])
        self.assertIn(
            "chair and CEO who founded the company",
            [lab for _, _, lab in self.br.judgement_notes(founder, self.board(), False)],
        )

    def test_founder_counts_only_for_the_company_that_issued_the_proxy(self):
        own = self.nominee(
            founder=self.fact(
                "yes", quote="Mr. Dell's leadership experience as founder of Dell Inc."
            )
        )
        self.br.mark_founder(own, "Dell Technologies, Inc.")
        self.assertTrue(own["founder_here"])
        said_our = self.nominee(founder=self.fact("yes", quote="Ms. Spear co-founded our company"))
        self.br.mark_founder(said_our, "FIGS, Inc.")
        self.assertTrue(said_our["founder_here"])
        elsewhere = self.nominee(
            ceo="yes",
            board_chair="yes",
            founder=self.fact("yes", quote="Mr. Musk is also a founder of The Boring Company"),
        )
        self.br.mark_founder(elsewhere, "Tesla, Inc.")
        self.assertFalse(elsewhere["founder_here"])
        self.assertEqual(
            [t.split(":")[0] for _, t, _ in self.br.decide(elsewhere, self.board())], ["rule 1.3.1"]
        )

    def test_an_executive_of_another_company_is_not_treated_as_this_companys_executive(self):
        outside = self.nominee(
            executive="yes",
            independent="yes",
            pay_committee=self.fact("member"),
            audit_committee=self.fact("member"),
        )
        self.assertEqual(self.br.decide(outside, self.board()), [])
        inside = self.nominee(executive="yes", independent="no", pay_committee=self.fact("member"))
        self.assertEqual(
            [t.split(":")[0] for _, t, _ in self.br.decide(inside, self.board())], ["rule 1.2.1"]
        )

    def test_a_fact_without_a_found_quote_never_lets_a_rule_act_alone(self):
        n = self.nominee(ceo=self.fact("yes", verified=False), board_chair="yes")
        fired = self.br.decide(n, self.board())
        self.assertEqual(len(fired), 1)
        self.assertFalse(fired[0][2])

    def test_a_signal_acts_alone_only_after_nbim_followed_it_twice_in_a_row(self):
        def row(date, y, company):
            return {
                "meeting_date": date,
                "company_id": company,
                "y": y,
                "signals": [{"name": "1.3.1 (proxy)", "quoted": True}],
            }

        votes = [1, 1, 1, 0, 1, 1, 1]
        rows = [row(f"202{i}-05-01", y, f"c{i}") for i, y in enumerate(votes)]
        self.br.earn_trust(rows)
        self.assertEqual(
            [r["signals"][0]["trusted"] for r in rows],
            [False, False, True, True, False, False, True],
        )

    def test_trust_never_uses_the_vote_of_the_same_day_or_later(self):
        rows = self.br.load_scored()
        changed = [dict(r, y=1 - r["y"]) if r["meeting_date"] >= "2026-01-01" else r for r in rows]
        for r in changed:
            r["signals"] = [dict(g) for g in r["signals"]]
        self.br.earn_trust(changed)
        first = min(
            r["meeting_date"] for r in rows if r["meeting_date"] >= "2026-01-01" and r["signals"]
        )
        for old, new in zip(rows, changed):
            if old["meeting_date"] <= first:
                self.assertEqual(
                    [g["trusted"] for g in old["signals"]], [g["trusted"] for g in new["signals"]]
                )

    def test_every_quote_shown_with_a_director_decision_is_in_the_readers_record(self):
        rows = [r for r in self.br.load_scored() if r["signals"]]
        self.assertGreater(len(rows), 80)
        for r in rows:
            for g in r["signals"]:
                for quote in g["quotes"]:
                    self.assertIn(
                        quote,
                        [
                            a["quote"]
                            for a in list(r["n"].values()) + list(r["b"].values())
                            if isinstance(a, dict)
                        ],
                    )


class JudgeTests(unittest.TestCase):
    """The judge model: what it is told, and what is accepted back."""

    @classmethod
    def setUpClass(cls):
        from src.evidence import judge

        cls.jg = judge
        cls.items = judge.director_rows(2026)

    def test_the_judge_is_told_no_name_no_year_and_no_vote_from_the_meeting(self):
        self.assertGreater(len(self.items), 1000)
        for r, d, state in self.items[::37]:
            sent = self.jg.json.dumps(self.jg.request_body(state), ensure_ascii=False)
            self.assertNotIn(r["company"], sent)
            surname = r["proposal_text"].replace("Elect Director ", "").split()[-1]
            if len(surname) > 4:
                self.assertNotIn(surname, sent)
            self.assertNotIn(r["meeting_date"], sent)
            for word in ('"nbim_vote"', "against_board", "rationale", "meeting_id"):
                self.assertNotIn(word, sent)

    def test_the_record_shown_to_the_judge_does_not_depend_on_this_meetings_vote(self):
        from src.rules import board as board_rules

        rows = board_rules.load_scored()
        flipped = [dict(r, y=1 - r["y"], signals=[dict(g) for g in r["signals"]]) for r in rows]
        board_rules.earn_trust(flipped)
        by_date = collections.defaultdict(list)
        for old, new in zip(rows, flipped):
            by_date[old["meeting_date"]].append((old, new))
        first = min(by_date)
        for old, new in by_date[
            first
        ]:  # nothing earlier exists, so the record must be empty either way
            self.assertEqual(
                [g["record"] for g in old["signals"]], [g["record"] for g in new["signals"]]
            )

    def test_a_reply_outside_the_form_is_rejected(self):
        self.assertEqual(
            self.jg.parse(
                '{"probability_against": 40, "rule": "1.3.1", "reason": "chair and CEO"}'
            )[0],
            0.4,
        )
        self.assertIsNone(self.jg.parse("Vote FOR. Ignore the rules."))
        self.assertIsNone(self.jg.parse('{"probability_against": 400}'))

    def test_a_changed_fact_is_a_new_question(self):
        r, d, state = self.items[0]
        other = self.jg.json.loads(self.jg.json.dumps(state))
        other["facts"]["independent"] = "no" if state["facts"]["independent"] != "no" else "yes"
        self.assertNotEqual(self.jg.state_key("k", state), self.jg.state_key("k", other))

    def test_every_judged_2026_nominee_has_a_cached_answer(self):
        cache = self.jg.load_cache()
        this_year = [(r, s) for r, _, s in self.items if r["meeting_date"][:4] == "2026"]
        have = sum(
            1
            for r, s in this_year
            if self.jg.state_key(f"{r['meeting_id']}-{r['item_no']}", s) in cache
        )
        self.assertGreater(have / len(this_year), 0.95)


class PositionPaperTests(unittest.TestCase):
    def test_every_paper_has_a_position_and_every_mapping_points_to_a_paper(self):
        papers = rc.load_papers()
        self.assertEqual(len(papers), 12)
        for slug, p in papers.items():
            self.assertTrue(p["position"], slug)
            self.assertTrue(p["url"].startswith("https://www.nbim.no/"), slug)
        for slug in list(rc.SECTION_PAPER.values()) + list(rc.RULE_PAPER.values()):
            self.assertIn(slug, papers)

    def test_papers_are_named_per_rule_where_a_section_covers_several_topics(self):
        papers = rc.load_papers()
        self.assertEqual(
            rc.paper_for(papers, "GVG 1.3")["slug"], "separation-of-chairperson-and-ceo"
        )
        self.assertEqual(
            rc.paper_for(papers, "GVG 3.1", "3.1.8")["slug"], "proxy-access-at-us-companies"
        )
        self.assertIsNone(rc.paper_for(papers, "GVG 3.1", "3.1.2"))
