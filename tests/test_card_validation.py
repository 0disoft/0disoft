"""Offline regression checks for publishing malformed, stale or wrong-scope cards."""

from datetime import date
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_card", ROOT / ".github/scripts/validate_card.py")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class CardValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.card = Path(self.directory.name) / "card.svg"
        # Synthetic fixture stays independent of live scores and collection dates.
        self.content = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="420" height="304" data-layout="compact">'
            + '<text><tspan class="profile-score">66</tspan></text>'
            + '<g aria-label="Public + Private Projects · 30 reviewed"/>'
            + '<g aria-label="Generated 2026-10-22 · v0.6.0"/>'
            + '<text class="footer">2026-10-22</text>'
            + '<!--' + 'padding' * 500 + '--></svg>'
        )

    def check_card(self, content=None, since="2026-10-22", today=date(2026, 10, 22), scope="Public + Private Projects"):
        self.card.write_text(content if content is not None else self.content, encoding="utf-8")
        return VALIDATOR.validate_card(self.card, scope, since, today)

    def test_current_private_and_public_cards(self):
        self.check_card()
        self.check_card(self.content.replace("Public + Private Projects", "Public GitHub projects").replace('height="304"', 'height="280"'), scope="Public GitHub")

    def test_utc_midnight_during_generation(self):
        self.check_card(today=date(2026, 10, 23))
        self.check_card(self.content.replace("2026-10-22", "2026-10-23"), today=date(2026, 10, 23))

    def test_stale_future_and_invalid_dates(self):
        for stamp in ("2026-10-21", "2026-10-23", "2026-02-30"):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                self.check_card(self.content.replace("2026-10-22", stamp))

    def test_malformed_xml_even_with_expected_markers(self):
        with self.assertRaises(ET.ParseError):
            self.check_card(self.content.replace("</svg>", ""))

    def test_wrong_scope_namespace_layout_and_missing_score(self):
        for content in (
            self.content.replace("Public + Private Projects", "Public GitHub"),
            self.content.replace("http://www.w3.org/2000/svg", "urn:not-svg"),
            self.content.replace('width="420"', 'width="760"'),
            self.content.replace('data-layout="compact"', 'data-layout="detailed"'),
            self.content.replace('<tspan class="profile-score">66</tspan>', "", 1),
            self.content.replace('<tspan class="profile-score">66</tspan>', '<tspan class="profile-score">101</tspan>'),
            self.content.replace('class="footer"', 'class="caption"'),
        ):
            with self.subTest(content=content[:100]), self.assertRaises(ValueError):
                self.check_card(content)

    def test_missing_or_truncated_file(self):
        with self.assertRaises(OSError):
            VALIDATOR.validate_card(self.card, "Public GitHub", "2026-10-22", date(2026, 10, 22))
        with self.assertRaises(ValueError):
            self.check_card("<svg/>")


class RecoveryNoticeTests(unittest.TestCase):
    def run_recovery(self, mode):
        bash = str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe") if os.name == "nt" else shutil.which("bash")
        if not bash or not Path(bash).is_file():
            self.skipTest("Bash is required for recovery script checks")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "gh.log"
            environment = dict(os.environ, GITHUB_REPOSITORY="test/profile", GITHUB_SERVER_URL="https://github.com", GITHUB_RUN_ID="123", GH_TEST_MODE=mode, GH_TEST_LOG=log.as_posix())
            # No GitHub requests: export a shell function in place of the gh CLI.
            mock = r'''
            gh() {
              printf '%s\n' "$*" >> "$GH_TEST_LOG"
              if [ "$2" = list ]; then
                case "$GH_TEST_MODE" in
                  query-failure) return 9 ;;
                  empty) return 0 ;;
                  *) printf '12\n13\n' ;;
                esac
              elif [ "$GH_TEST_MODE" = close-failure ]; then
                return 8
              fi
            }
            export -f gh
            bash .github/scripts/close_degraded_issues.sh
            '''
            result = subprocess.run([bash, "-c", mock], cwd=ROOT, env=environment, capture_output=True, text=True)
            return result, log.read_text(encoding="utf-8")

    def test_closes_each_matching_notice_with_recovery_link(self):
        result, log = self.run_recovery("success")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("issue close 12 --repo test/profile", log)
        self.assertIn("issue close 13 --repo test/profile", log)
        self.assertIn("https://github.com/test/profile/actions/runs/123", log)
        self.assertIn("--author github-actions[bot]", log)

    def test_no_open_notice_is_a_noop(self):
        result, log = self.run_recovery("empty")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("issue close", log)

    def test_query_failure_does_not_close_anything(self):
        result, log = self.run_recovery("query-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("issue close", log)

    def test_close_failure_is_reported(self):
        result, log = self.run_recovery("close-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("issue close 13", log)


if __name__ == "__main__":
    unittest.main()
