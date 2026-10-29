import unittest
from unittest.mock import Mock, patch

import requests

from core.github_loader import load_github_repository


class GitHubLoaderTests(unittest.TestCase):
    def test_rejects_non_github_or_malformed_urls(self):
        invalid_urls = [
            "http://github.com/owner/repo",
            "https://example.com/owner/repo",
            "https://github.com/owner",
            "https://user@github.com/owner/repo",
            "https://github.com:444/owner/repo",
            "https://github.com/owner/repo?tab=readme",
            "https://github.com/owner/repo#readme",
        ]
        for url in invalid_urls:
            with self.subTest(url=url), patch("core.github_loader.requests.Session") as session:
                with self.assertRaises(ValueError):
                    load_github_repository(url)
                session.assert_not_called()

    @patch("core.github_loader.requests.Session")
    def test_connection_failure_has_friendly_message(self, session_factory):
        session = session_factory.return_value
        session.get.side_effect = requests.ConnectionError("RemoteDisconnected")

        with self.assertRaisesRegex(ValueError, "Could not connect to GitHub"):
            load_github_repository("https://github.com/owner/repo")

        session.get.assert_called_once()
        self.assertEqual((5, 30), session.get.call_args.kwargs["timeout"])
        self.assertIn("User-Agent", session.headers.update.call_args.args[0])

    @patch("core.github_loader.requests.Session")
    def test_404_has_friendly_message(self, session_factory):
        response = Mock(status_code=404, headers={})
        session_factory.return_value.get.return_value = response

        with self.assertRaisesRegex(ValueError, "Repository not found or not public"):
            load_github_repository("https://github.com/owner/repo")

    @patch("core.github_loader.requests.Session")
    def test_rate_limit_has_friendly_message(self, session_factory):
        response = Mock(status_code=403, headers={"X-RateLimit-Remaining": "0"})
        session_factory.return_value.get.return_value = response

        with self.assertRaisesRegex(ValueError, "rate limit reached"):
            load_github_repository("https://github.com/owner/repo")


if __name__ == "__main__":
    unittest.main()
