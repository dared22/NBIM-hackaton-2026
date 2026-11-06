"""The existing dashboard renders predictions and empty selections."""

import unittest
from pathlib import Path
from unittest.mock import patch

from src import data as paths
from tests.support import get_outputs

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install the dashboard extra to test Streamlit")
class DashboardTests(unittest.TestCase):
    def test_datasets_filters_navigation_and_download(self):
        with patch.object(paths, "OUTPUTS", str(get_outputs())):
            app = AppTest.from_file(str(Path(paths.ROOT) / "src/dashboard.py")).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.metric[0].value, "1 539")
            self.assertTrue(len(app.get("download_button")))
            app.button(key="nav_next").click().run(timeout=30)
            self.assertEqual(app.session_state["nav_pos"], 1)
            app.text_input[0].set_value("__company_not_present__").run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.metric[0].value, "0")
            app.text_input[0].set_value("").run(timeout=30)
            self.assertEqual(app.metric[0].value, "1 539")

    def test_missing_outputs_displays_startup_instruction(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder, patch.object(paths, "OUTPUTS", folder):
            app = AppTest.from_file(str(Path(paths.ROOT) / "src/dashboard.py")).run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertIn("python run.py predict", app.warning[0].value)
