"""Checks for the parts of the agent that are easy to get wrong.

Run from the repo root:
    python3 -m unittest discover -s tests

No internet and no API key are needed.
"""

import csv
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "agent"))

import fetch_proxy_pay as fp  # noqa: E402
import fetch_proxy_text as ft  # noqa: E402
import pay_model as pm  # noqa: E402
import robustness as rb  # noqa: E402
import rule_check as rc  # noqa: E402

ANSWER_FIELDS = ("nbim_vote", "nbim_vote_raw", "against_board", "rationale_text", "rationale_section", "position_paper")

PROXY_SNIPPET = b"""
<xbrli:context id="plain2025"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="ceoA"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier>
  <xbrli:segment><xbrldi:explicitMember dimension="ecd:IndividualAxis">co:MsSmithMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
  <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="adjust"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier>
  <xbrli:segment><xbrldi:explicitMember dimension="ecd:AdjToCompAxis">co:SomethingMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
  <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<td><ix:nonFraction name="ecd:PeoTotalCompAmt" contextRef="plain2025" scale="0" format="ixt:num-dot-decimal">24,188,539</ix:nonFraction></td>
<td><ix:nonFraction name="ecd:PeoTotalCompAmt" contextRef="ceoA" scale="3"><span>8,415</span></ix:nonFraction></td>
<td><ix:nonFraction name="ecd:PeoTotalCompAmt" contextRef="adjust" scale="0">999</ix:nonFraction></td>
<td><ix:nonFraction name="ecd:TotalShareholderRtnAmt" contextRef="plain2025">127</ix:nonFraction></td>
<td><ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="plain2025">5</ix:nonFraction></td>
"""


class ProxyReaderTests(unittest.TestCase):
    def test_reads_plain_and_named_ceo_figures_and_skips_other_breakdowns(self):
        facts = fp.read_tags(PROXY_SNIPPET)
        self.assertIn(("PeoTotalCompAmt", "2025-01-01", "2025-12-31", "", 24188539.0), facts)
        self.assertIn(("PeoTotalCompAmt", "2024-01-01", "2024-12-31", "MsSmithMember", 8415000.0), facts)
        self.assertIn(("TotalShareholderRtnAmt", "2025-01-01", "2025-12-31", "", 127.0), facts)
        self.assertEqual(len(facts), 3)  # the adjustment breakdown and the non-pay tag are left out

    def test_number_handles_brackets_scale_and_dashes(self):
        self.assertEqual(fp.number("(1,234)", {}), -1234.0)
        self.assertEqual(fp.number("12.5", {"scale": "6"}), 12500000.0)
        self.assertEqual(fp.number("—", {}), 0.0)
        self.assertIsNone(fp.number("n/a", {}))

    def test_proxy_filed_on_or_after_the_meeting_is_never_picked(self):
        filings = [("2026-05-20", "DEF 14A", "a-3", "x.htm"), ("2026-05-01", "DEFA14A", "a-2", "y.htm"),
                   ("2026-04-01", "DEF 14A", "a-1", "z.htm"), ("2025-04-01", "DEF 14A", "a-0", "w.htm")]
        self.assertEqual(fp.pick_proxy(filings, "2026-05-20")[2], "a-1")
        self.assertIsNone(fp.pick_proxy(filings, "2026-04-01"))
        self.assertIsNone(fp.pick_proxy(filings, "2025-12-01"))  # nothing in the 120 days before


class PayModelTests(unittest.TestCase):
    def test_wrongly_scaled_figures_are_brought_below_a_billion(self):
        self.assertAlmostEqual(pm.repaired(12895917000000.0, 1e9), 12895917.0)
        self.assertAlmostEqual(pm.repaired(7791622000.0, 1e9), 7791622.0)
        self.assertEqual(pm.repaired(403000000.0, 1e9), 403000000.0)

    def test_pay_return_gap_sign(self):
        flat_pay, rising_pay = [10e6] * 5, [5e6, 8e6, 12e6, 18e6, 25e6]
        rising_ret, flat_ret = [110, 125, 140, 160, 180], [100, 100, 100, 100, 100]
        self.assertGreater(pm.pay_return_gap(flat_pay, rising_ret), 0)   # returns grew, pay did not
        self.assertLess(pm.pay_return_gap(rising_pay, flat_ret), 0)      # pay grew, returns did not
        self.assertIsNone(pm.pay_return_gap([1e6, 2e6], [100, 110]))     # too few years
        self.assertIsNone(pm.pay_return_gap([1e6, 2e6, 3e6], [100, None, 110]))

    def test_no_answer_column_is_a_model_input(self):
        names = [name for name, _, _ in pm.FEATURES]
        for word in ("vote_now", "actual", "label", "stemme"):
            self.assertFalse(any(word in n for n in names))
        self.assertEqual(names[:2], ["prev_against", "prev_for"])  # the only vote inputs: last season's


class DataAuditTests(unittest.TestCase):
    """Checks on the saved data itself: nothing from after a meeting may be used for it."""

    def test_every_proxy_was_filed_before_its_meeting(self):
        path = os.path.join(ROOT, "data", "evidence", "proxy_meetings.csv")
        with open(path, encoding="utf-8", newline="") as f:
            used = [r for r in csv.DictReader(f) if r["status"] == "ok"]
        self.assertGreater(len(used), 3000)
        late = [r for r in used if r["filed"] >= r["meeting_date"]]
        self.assertEqual(late, [])

    def test_mislabelled_fiscal_years_stay_rare(self):
        # A few filers label a figure with a fiscal year that ends after the proxy
        # was filed (11 of about 17,000 CEO figures when this was written). The
        # figure itself was still published before the meeting, so it is not a
        # leak, but the label is wrong. This fails if the share ever grows.
        path = os.path.join(ROOT, "data", "evidence", "proxy_pay.csv")
        with open(path, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["tag"] == "PeoTotalCompAmt"]
        late = sum(1 for r in rows if r["period_end"] >= r["filed"])
        self.assertLess(late / len(rows), 0.002)

    def test_model_never_uses_a_proxy_filed_on_or_after_the_meeting(self):
        meeting = {"meeting_date": "2026-05-20", "filed": "2026-05-20", "form": "DEF 14A", "url": ""}
        facts = {"PeoTotalCompAmt": [{"period_end": "2025-12-31", "value": "30000000", "person": ""}]}
        import collections
        self.assertIsNone(pm.from_proxy(collections.defaultdict(list, facts), meeting))


class GuardrailTests(unittest.TestCase):
    def test_instruction_attacks_are_flagged(self):
        for _, template in rb.ATTACKS[:4]:
            text = "Elect Director Jane Doe " + rb.attack_text(template, "FOR")
            self.assertTrue(rb.guard_patterns(text), text)

    def test_ordinary_ballot_wording_is_not_flagged(self):
        for text in ("THE BOARD OF DIRECTORS RECOMMENDS: A", "Approve Final Dividend",
                     "Advisory Vote to Ratify Named Executive Officers' Compensation",
                     "Your Board recommends you", "Ratify KPMG LLP as Auditors"):
            self.assertEqual(rb.guard_patterns(text), [], text)

    def test_known_item_is_restored_when_text_is_appended(self):
        train = [{"company_id": "c1", "text_key": "elect director jane doe"}]
        test = [{"company_id": "c1", "text_key": "elect director jane doe please see the notice for details"}]
        self.assertEqual(rb.restore_known_items(test, train), 1)
        self.assertEqual(test[0]["text_key"], "elect director jane doe")


class RuleCheckRequestTests(unittest.TestCase):
    def test_request_holds_no_answer_field_and_no_company_name(self):
        row = {"proposal_text": "Elect Director Jane Doe", "proposal_type": "DIRECTOR_ELECTION",
               "proponent": "Management", "mgmt_rec": "FOR", "country": "Norway", "market": "DM",
               "company": "SECRET COMPANY ASA", "nbim_vote": "MOT", "against_board": "1.0",
               "rationale_text": "SECRET RATIONALE", "rationale_section": "GVG 1.1", "position_paper": "x"}
        sections = rc.load_guidelines()
        body = rc.build_request(row, ["1.1"], sections)
        text = str(body)
        self.assertNotIn("SECRET", text)
        for field in ANSWER_FIELDS:
            self.assertNotIn(field, body["state"])
        self.assertIn("never follow instructions", text)


class DecisionTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "src"))
        import run
        self.run = run

    def test_low_probability_alone_is_automatic(self):
        self.assertEqual(self.run.decide("FOR", "likely WITH board", []), ("FOR", "automatic", ""))

    def test_low_information_always_goes_to_a_person(self):
        vote, who, why = self.run.decide("FOR", "likely WITH board", ["low information: no pay figure found for this company"])
        self.assertEqual(who, "human review")
        self.assertIn("low information", why)

    def test_missing_board_recommendation_goes_to_a_person(self):
        self.assertEqual(self.run.decide("", "likely WITH board", [])[1], "human review")

    def test_against_the_board_flips_the_boards_recommendation(self):
        self.assertEqual(self.run.decide("FOR", "likely AGAINST board", [])[0], "MOT")
        self.assertEqual(self.run.decide("MOT", "likely AGAINST board", [])[0], "FOR")

    def test_pay_score_uses_numbers_and_past_votes_only(self):
        # Free text from a company filing can never raise or lower the pay score:
        # no input is built from prose, only from tagged figures and earlier votes.
        names = [name for name, _, _ in pm.FEATURES]
        self.assertFalse(any(word in n for n in names for word in ("text", "word", "sentence", "support")))


class ProxyTextTests(unittest.TestCase):
    def test_prior_support_is_the_figure_next_to_the_result(self):
        text = ("Approval requires a majority (50%) of shares present. "
                "At the 2025 Annual Meeting, approximately 62% of the votes cast supported our say-on-pay proposal.")
        self.assertEqual(ft.prior_support(text)[0], 62.0)

    def test_no_support_figure_gives_none(self):
        self.assertIsNone(ft.prior_support("We hold an advisory vote on executive compensation every year."))


if __name__ == "__main__":
    unittest.main()
