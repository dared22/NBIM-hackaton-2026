import io
import json
import unittest
import zipfile
from unittest.mock import patch

import hent_npx


PRIMARY = b"""<edgarSubmission xmlns="http://www.sec.gov/edgar/npx">
<formData><coverPage><reportInfo>
<reportType>INSTITUTIONAL MANAGER NOTICE REPORT</reportType>
<noticeExplanation>REPORTING PERSON DID NOT EXERCISE VOTING</noticeExplanation>
</reportInfo></coverPage></formData></edgarSubmission>"""

VOTES = b"""<proxyVoteTable xmlns="http://www.sec.gov/edgar/document/npxproxy/informationtable">
<proxyTable>
  <issuerName>Example Inc.</issuerName><cusip>001234567</cusip>
  <meetingDate>06/04/2026</meetingDate><voteDescription>Approve compensation</voteDescription>
  <voteCategories>
    <voteCategory><categoryType>Compensation</categoryType></voteCategory>
    <voteCategory><categoryType>Other</categoryType></voteCategory>
  </voteCategories>
  <sharesVoted>100</sharesVoted>
  <vote>
    <voteRecord><howVoted>FOR</howVoted><sharesVoted>70</sharesVoted></voteRecord>
    <voteRecord><howVoted>AGAINST</howVoted><sharesVoted>30</sharesVoted></voteRecord>
  </vote>
</proxyTable>
<proxyTable>
  <issuerName>Unvoted Inc.</issuerName><voteDescription>No vote cast</voteDescription>
  <sharesVoted>0</sharesVoted>
</proxyTable>
</proxyVoteTable>"""


class NpxTests(unittest.TestCase):
    def test_parse_preserves_split_votes_without_duplicate_ancestor_rows(self):
        rows = hent_npx.parse(VOTES)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["stemme"] for row in rows], ["FOR", "AGAINST"])
        self.assertEqual([row["aksjer"] for row in rows], ["70", "30"])
        self.assertEqual(rows[0]["utsteder"], "Example Inc.")
        self.assertEqual(rows[0]["cusip"], "001234567")
        self.assertEqual(rows[0]["kategori"], "Compensation; Other")

    def test_parse_supports_xml_without_namespace(self):
        xml = VOTES.replace(
            b' xmlns="http://www.sec.gov/edgar/document/npxproxy/informationtable"', b""
        )
        self.assertEqual(len(hent_npx.parse(xml)), 2)

    def test_download_uses_raw_xml_and_all_voting_attachments(self):
        base = "https://www.sec.gov/Archives/edgar/data/123/456"
        index = {"directory": {"item": [
            {"name": "primary_doc.xml"},
            {"name": "BRDWLB_2026.xml"},
            {"name": "more_votes.xml"},
        ]}}
        responses = {
            f"{base}/primary_doc.xml": PRIMARY,
            f"{base}/index.json": json.dumps(index).encode(),
            f"{base}/BRDWLB_2026.xml": VOTES,
            f"{base}/more_votes.xml": VOTES,
        }
        with patch.object(hent_npx, "hent", side_effect=responses.__getitem__):
            xml = hent_npx.hent_xml("123", "456", "xslN-PX_X01/primary_doc.xml")
        self.assertEqual(len(hent_npx.parse(xml)), 4)

    def test_download_reads_voting_xml_from_zip(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("cover.xml", PRIMARY)
            archive.writestr("votes.xml", VOTES)
        base = "https://www.sec.gov/Archives/edgar/data/123/456"
        responses = {
            f"{base}/primary_doc.xml": PRIMARY,
            f"{base}/index.json": json.dumps({"directory": {"item": [
                {"name": "primary_doc.xml"}, {"name": "votes.zip"},
            ]}}).encode(),
            f"{base}/votes.zip": buffer.getvalue(),
        }
        with patch.object(hent_npx, "hent", side_effect=responses.__getitem__):
            xml = hent_npx.hent_xml("123", "456", "xslN-PX_X01/primary_doc.xml")
        self.assertEqual(len(hent_npx.parse(xml)), 2)

    def test_notice_without_votes_reports_reason(self):
        with patch.object(hent_npx, "hent", side_effect=[
            PRIMARY,
            json.dumps({"directory": {"item": [{"name": "primary_doc.xml"}]}}).encode(),
        ]):
            with self.assertRaisesRegex(SystemExit, "DID NOT EXERCISE VOTING"):
                hent_npx.hent_xml("123", "456", "xslN-PX_X01/primary_doc.xml")


if __name__ == "__main__":
    unittest.main()
