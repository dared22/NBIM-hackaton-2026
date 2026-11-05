"""Validate the saved, labelled-free five-meeting pilot and offline replay."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evidence import TextOnly

PILOT = ROOT / 'data/evidence/pilot-v1'


class SavedPilotTest(unittest.TestCase):
    def test_saved_sources_and_annotated_values(self):
        packets = [json.loads(line) for line in (PILOT / 'accepted/evidence.jsonl').read_text().splitlines()]
        self.assertEqual(len(packets), 20)
        self.assertEqual(len({p['proposal']['meeting_id'] for p in packets}), 5)
        expectations = json.loads((PILOT / 'expected.json').read_text())['expected']
        recovered = 0
        texts = {}
        outside_counts = 0
        for packet in packets:
            p, c = packet['proposal'], packet['company_evidence']
            self.assertEqual(c['status'], 'verified')
            self.assertLessEqual(len(packet['policy']['sections']), 3)
            for doc in c['documents']:
                self.assertLess(doc['filing_date'], p['meeting_date'])
                path = ROOT / 'data/evidence/_cache/sec' / (doc['accession'].replace('-', '') + '_' + doc['url'].split('/')[-1])
                raw = path.read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), doc['sha256'])
                parser = TextOnly(); parser.feed(raw.decode('utf-8', errors='replace'))
                texts[doc['sha256']] = parser.text()
            for field, fact in {**c['shared'], **c['nominee']['facts']}.items():
                for source in fact['sources']:
                    self.assertEqual(texts[source['sha256']][source['start']:source['end']], source['quote'])
                if fact['status'] == 'known':
                    self.assertTrue(fact['sources'])
                    key = f"{p['meeting_id']}/{p['item_no']}/{field}"
                    if key in expectations:
                        self.assertEqual(fact['value'], expectations[key], key)
                        recovered += 1
                    if field in {'board_count_min', 'chair_count_min'}:
                        outside_counts += 1
        self.assertGreaterEqual(recovered, 15)
        self.assertGreater(outside_counts, 0)

    def test_offline_replay_needs_no_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as output:
            subprocess.run([sys.executable, str(ROOT / 'src/evidence.py'), '--inputs',
                str(PILOT / 'inputs.csv'), '--year', '2025', '--offline', '--output-dir', output],
                cwd=ROOT, check=True, capture_output=True)
            summary = json.loads((Path(output) / 'summary.json').read_text())
            self.assertEqual(summary['model_calls'], 0)
            self.assertEqual(summary['proposals'], 20)
            def comparable(path):
                result = [json.loads(line) for line in path.read_text().splitlines()]
                for packet in result:
                    packet['company_evidence'].pop('provenance')
                return result
            self.assertEqual(comparable(Path(output) / 'evidence.jsonl'),
                             comparable(PILOT / 'accepted/evidence.jsonl'))


if __name__ == '__main__':
    unittest.main()
