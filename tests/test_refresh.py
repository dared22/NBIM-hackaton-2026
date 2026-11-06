"""Refresh commands and transports use isolated files and mocked HTTP."""

import gzip
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import run as cli
from src.data import read_records
from src.evidence import http as openrouter
from src.evidence import http as sec


class RefreshTests(unittest.TestCase):
    def test_dashboard_command_launches_the_existing_source_file(self):
        import sys

        with (
            patch.object(sys, "argv", ["run.py", "dashboard"]),
            patch.object(cli.subprocess, "call", return_value=0) as launch,
        ):
            with self.assertRaises(SystemExit) as stopped:
                cli.main()
        self.assertEqual(stopped.exception.code, 0)
        self.assertTrue(Path(launch.call_args.args[0][-1]).is_file())
        self.assertEqual(Path(launch.call_args.args[0][-1]).name, "dashboard.py")

    def test_sec_gzip_response_and_missing_document(self):
        response = Mock()
        response.headers = {"Content-Encoding": "gzip"}
        response.read.return_value = gzip.compress(b"proxy")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with (
            patch.object(sec.urllib.request, "urlopen", return_value=response),
            patch.object(sec.time, "sleep"),
        ):
            self.assertEqual(sec.get("https://example.test/proxy"), (200, b"proxy"))
        error = HTTPError("https://example.test/proxy", 404, "missing", {}, io.BytesIO())
        with (
            patch.object(sec.urllib.request, "urlopen", side_effect=error),
            patch.object(sec.time, "sleep"),
        ):
            self.assertEqual(sec.get("https://example.test/proxy"), (404, b""))

    def test_openrouter_retries_and_preserves_endpoint_and_payload(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"answers": {}}'
        error = HTTPError("https://example.test/decisions", 429, "retry", {}, io.BytesIO())
        with (
            patch.object(
                openrouter.urllib.request, "urlopen", side_effect=[error, response]
            ) as send,
            patch.object(openrouter.time, "sleep"),
        ):
            body = {"model": "example", "state": {"board_size": 10}}
            self.assertEqual(
                openrouter.call_model(
                    body, "test-key", url="https://example.test/decisions", timeout=60
                ),
                {"answers": {}},
            )
            request = send.call_args.args[0]
            self.assertEqual(request.full_url, "https://example.test/decisions")
            self.assertEqual(json.loads(request.data), body)
            self.assertEqual(send.call_count, 2)

    def test_cache_keeps_last_record_for_each_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "answers.jsonl"
            path.write_text('{"key":"a","p":0.1}\n{"key":"a","p":0.2}\n')
            self.assertEqual(
                read_records(str(path), lambda r: r["key"]), {"a": {"key": "a", "p": 0.2}}
            )

    def test_refresh_dispatch_preserves_arguments_and_restores_argv(self):
        import sys

        previous = sys.argv
        module = Mock()
        module.main.side_effect = lambda: self.assertEqual(
            sys.argv, ["board-facts", "--limit", "8"]
        )
        with patch.object(cli.importlib, "import_module", return_value=module):
            cli.refresh_source("board-facts", ["--limit", "8"])
        self.assertIs(sys.argv, previous)
        module.main.assert_called_once()


class PolicyRefreshTests(unittest.TestCase):
    def test_guidelines_refresh_saves_the_fetched_policy(self):
        from src import data as paths
        from src.evidence import policy

        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "live.json"
            saved = {"fetched": "2026-11-06", "sentences": ["We will consider this rule."] * 40}
            with (
                patch.object(policy, "fetch", return_value=saved),
                patch.object(paths, "LIVE_GUIDELINES", str(destination)),
            ):
                cli.refresh_source("guidelines", [])
            self.assertEqual(json.loads(destination.read_text()), saved)
            with (
                patch.object(policy, "fetch", return_value={"sentences": []}),
                patch.object(paths, "LIVE_GUIDELINES", str(destination)),
            ):
                with self.assertRaises(SystemExit):
                    cli.refresh_source("guidelines", [])
            self.assertEqual(json.loads(destination.read_text()), saved)
