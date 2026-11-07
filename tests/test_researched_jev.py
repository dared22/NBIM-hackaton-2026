"""Leakage boundaries and the independent researched Jev workflow."""

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src import data as paths
from src.evidence import research_policy as policy
from src.evidence import research_sources as sources
from src.evidence import researched_jev as jev


def row(**changes):
    return {
        "meeting_id": "m",
        "item_no": "1",
        "company_id": "c",
        "company": "Example plc",
        "meeting_date": "2026-05-20",
        "proposal_text": "Ratify auditor Audit LLP",
        "proposal_type": "AUDITOR",
        "country": "United States",
        "market": "DM",
        "proponent": "Management",
        "mgmt_rec": "FOR",
        "nbim_vote": "MOT",
        "against_board": "1.0",
        "rationale_text": "SECRET",
        "rationale_section": "SECRET",
        **changes,
    }


def document(text="Audit LLP: non-audit fees were 60% in each of the prior two years."):
    return sources.source_record(
        "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/proxy.htm",
        text,
        "2026-04-01",
        {"kind": "sec_filing", "filed": "2026-04-01", "accession": "0000000001-26-000001"},
    )


class FakeJev:
    def __init__(self):
        self.requests = []

    def ask(self, body):
        self.requests.append(body)
        answers = {}
        for name, q in body["questions"].items():
            choice = "MOT" if name == "vote" else "unknown"
            answers[name] = {
                "choice": choice,
                "probabilities": {v: float(v == choice) for v in q["criteria"]},
            }
        return {"model": "fixture", "answers": answers}


class ResearchTests(unittest.TestCase):
    def test_full_policy_is_batched_without_losing_answers(self):
        with tempfile.TemporaryDirectory() as folder:
            client = jev.Jev(Path(folder))
            body = jev.qa_request(
                row(proposal_type="OTHER_MGMT"), policy.policy_for("2026-05-20"), []
            )
            fake = FakeJev()
            with (
                patch.object(jev.rc, "api_key", return_value="test-token"),
                patch.object(
                    jev, "call_model", side_effect=lambda b, *_args, **_kwargs: fake.ask(b)
                ),
            ):
                response = client.ask(body)
            self.assertEqual(len(response["answers"]), 76)
            self.assertEqual(len(fake.requests), 5)
            self.assertTrue(all(len(b["questions"]) <= 16 for b in fake.requests))

    def test_archive_redirect_cannot_substitute_a_future_capture(self):
        cdx = [["timestamp"], ["20260401120000"]]
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.geturl.return_value = (
            "https://web.archive.org/web/20270101000000id_/https://issuer.test/"
        )
        with (
            patch.object(sources, "get", return_value=(200, json.dumps(cdx).encode())),
            patch.object(sources, "urlopen", return_value=response),
        ):
            self.assertIsNone(sources.Researcher().archived("https://issuer.test/", "2026-05-20"))
        response.read.assert_not_called()

    def test_html_extraction_does_not_follow_links(self):
        self.assertEqual(
            sources.document_text(b"<p>Known fact</p><script>bad()</script>"), "Known fact"
        )

    def test_quoted_dotenv_key_is_normalized_and_answers_are_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            client = jev.Jev(Path(folder))
            body = jev.prediction_request(row(), None, {}, [])
            response = FakeJev().ask(body)
            with (
                patch.object(jev.rc, "api_key", return_value='"test-token"'),
                patch.object(jev, "call_model", return_value=response) as call,
            ):
                self.assertEqual(client.ask(body), client.ask(body))
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[1], "test-token")

    def test_all_proposal_types_have_explicit_mapping(self):
        with open(paths.VOTES) as handle:
            kinds = {r["proposal_type"] for r in csv.DictReader(handle)}
        self.assertEqual(kinds, set(policy.TYPE_SECTIONS))
        edition = policy.policy_for("2026-01-01")
        directors = policy.questions_for("DIRECTOR_ELECTION", edition)
        self.assertIn("1.2.1", directors)  # Not limited to the old top three sections.
        self.assertIn("2.3.1", directors)
        self.assertIn("5.1.4", directors)
        self.assertIn("founder", directors["1.3.1"]["question"])
        self.assertIn("limited period", directors["1.3.1"]["question"])
        for kind in ("SHP_OTHER", "OTHER_MGMT", "ARTICLES"):
            self.assertEqual(len(policy.questions_for(kind, edition)), 76)
        for kind in ("DIVIDEND", "SAY_ON_PAY_FREQ"):
            self.assertEqual(set(policy.questions_for(kind, edition)), set(policy.CROSS_CUTTING))
        auditor = policy.questions_for("AUDITOR", edition)["5.1.1"]["question"]
        self.assertIn("50 percent", auditor)
        self.assertIn("two consecutive years", auditor)

    def test_policy_cutoff_and_hash(self):
        self.assertIsNone(policy.policy_for("2025-02-17"))
        self.assertIsNotNone(policy.policy_for("2025-02-18"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "editions.json"
            entry = json.loads(policy.MANIFEST.read_text())[0]
            path.write_text(json.dumps([{**entry, "sha256": "wrong"}]))
            with self.assertRaises(ValueError):
                policy.policy_for("2026-01-01", path)

    def test_future_undated_mutable_and_modified_sources_fail(self):
        doc = document()
        self.assertTrue(sources.admitted(doc, "2026-05-20"))
        for change in (
            {"available_on": "2026-05-20"},
            {"available_on": "2026-05-21"},
            {"available_on": ""},
            {"text": "changed since fetching"},
            {"proof": {"kind": "page_date", "published": "2020-01-01"}},
        ):
            self.assertFalse(sources.admitted({**doc, **change}, "2026-05-20"))
        url = "https://issuer.test/governance"
        archive = sources.source_record(
            url,
            "Historic board",
            "2026-04-01",
            {"kind": "archive", "timestamp": "20260401120000"},
            snapshot_url=f"https://web.archive.org/web/20260401120000id_/{url}",
        )
        self.assertTrue(sources.admitted(archive, "2026-05-20"))
        self.assertFalse(sources.admitted({**archive, "snapshot_url": url}, "2026-05-20"))

    def test_current_or_future_labels_cannot_change_requests(self):
        first, second = FakeJev(), FakeJev()
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            original = row()
            changed = row(nbim_vote="FOR", against_board="0.0", rationale_text="OTHER SECRET")
            future = row(meeting_id="future", meeting_date="2027-01-01")
            a = jev.predict(original, [document()], [original, future], first, cache)
            b = jev.predict(
                changed, [document()], [changed, {**future, "nbim_vote": "FOR"}], second, cache
            )
            self.assertEqual(first.requests, second.requests)
            self.assertEqual(a["key"], b["key"])
        self.assertEqual(len(first.requests), 2)
        self.assertNotIn("SECRET", json.dumps(first.requests))
        self.assertNotIn("Example plc", json.dumps(first.requests))
        self.assertIn("guideline_answers", first.requests[1]["state"])

    def test_target_votes_are_excluded_even_when_published_before_cutoff(self):
        doc = document("Norges Bank voted AGAINST this proposal.")
        self.assertEqual(jev.excerpts(row(), [doc], {}), [])

    def test_history_requires_proof_and_excludes_same_day(self):
        past = row(meeting_id="past", meeting_date="2025-05-20")
        same_day = row(meeting_id="same_day")
        quote = (
            f"{past['company']} {past['proposal_text']} {past['meeting_date']} {past['nbim_vote']}"
        )
        doc = document(quote)
        proof = {"vote_key": "past-1", "document": doc, "quote": quote}
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            self.assertEqual(sources.earlier_votes(row(), [past, same_day], cache), ([], 1))
            sources.append(cache / "history_publications.jsonl", proof)
            votes, omitted = sources.earlier_votes(row(), [past, same_day], cache)
            self.assertEqual(len(votes), 1)
            self.assertEqual(omitted, 0)

    def test_missing_documents_keep_tentative_prediction_and_unknown_answers(self):
        with tempfile.TemporaryDirectory() as folder:
            result = jev.predict(row(), [], [row()], FakeJev(), Path(folder))
        self.assertEqual(result["prediction"]["choice"], "MOT")
        self.assertIn("no verified company documents", result["flags"])
        self.assertTrue(all(a["choice"] == "unknown" for a in result["qa"].values()))

    def test_invalid_model_response_is_rejected(self):
        questions = {"vote": {"criteria": {"FOR": "", "MOT": ""}}}
        for response in (
            {},
            {"answers": {"vote": {"choice": "FOR", "probabilities": {"FOR": 1, "MOT": 1}}}},
        ):
            with self.assertRaises(ValueError):
                jev.parse_choices(response, questions)

    def test_sampling_ignores_answers_and_keeps_whole_meetings(self):
        rows = [row(meeting_id=str(i), item_no=str(j)) for i in range(20) for j in range(3)]
        a = sources.sample_meetings(rows, 2026, 10)
        b = sources.sample_meetings([{**r, "nbim_vote": "FOR"} for r in rows], 2026, 10)
        self.assertEqual([m[0]["meeting_id"] for m in a], [m[0]["meeting_id"] for m in b])
        self.assertTrue(all(len(m) == 3 for m in a))

    def test_refresh_has_five_search_ceiling(self):
        researcher = sources.Researcher()
        with tempfile.TemporaryDirectory() as folder:
            researcher.cache = Path(folder)
            rows = [row(country="Japan", proposal_type=str(i)) for i in range(10)]
            with patch.object(researcher, "search", return_value=[]) as search:
                researcher.meeting(rows)
            self.assertEqual(search.call_count, 5)

    def test_offline_comparison_joins_labels_only_after_prediction(self):
        with tempfile.TemporaryDirectory() as folder:
            cache, output = Path(folder) / "cache", Path(folder) / "output"
            record = jev.predict(row(), [document()], [row()], FakeJev(), cache)
            sources.append(cache / "predictions_2026.jsonl", record)
            votes = Path(folder) / "votes.csv"
            with votes.open("w") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row()))
                writer.writeheader()
                writer.writerow(row())
            with (
                patch.object(paths, "VOTES", str(votes)),
                patch.object(jev, "call_model", side_effect=AssertionError("network")),
                patch.object(sources, "get", side_effect=AssertionError("network")),
            ):
                summary = jev.compare(2026, output, cache)
            self.assertEqual(summary["researched"]["n"], 1)
            self.assertEqual(summary["researched"]["recall"], 1)
            self.assertTrue((output / "qa_jev_2026.jsonl").exists())

    def test_refresh_cli_dispatch(self):
        import run

        with patch.object(jev, "refresh") as refresh:
            run.refresh_source("researched-jev", ["--year", "2025", "--limit-meetings", "2"])
        refresh.assert_called_once_with(2025, 2)


if __name__ == "__main__":
    unittest.main()
