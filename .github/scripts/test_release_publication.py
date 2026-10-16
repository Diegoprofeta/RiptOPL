"""Test publication authorization and first-release/existing-tag transitions."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import publish_editions as publisher


class PublicationTests(unittest.TestCase):
    def test_only_matching_integration_push_or_dispatch_can_publish(self):
        environment = {
            "GITHUB_REPOSITORY": "NathanNeurotic/RiptOPL",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/heads/rebuild/main",
            "GITHUB_SHA": "abc123",
        }
        for event in ("push", "workflow_dispatch"):
            self.assertTrue(publisher.publication_allowed(dict(environment, GITHUB_EVENT_NAME=event), "abc123"))
        for key, value in (
            ("GITHUB_REPOSITORY", "someone/RiptOPL"),
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_EVENT_NAME", "pull_request_target"),
            ("GITHUB_REF", "refs/heads/main"),
            ("GITHUB_SHA", "different"),
        ):
            self.assertFalse(publisher.publication_allowed(dict(environment, **{key: value}), "abc123"))
        self.assertFalse(publisher.publication_allowed({}, "abc123"))

    def test_first_draft_release_creates_missing_tag(self):
        result = subprocess.CompletedProcess([], 1, "", "gh: Not Found (HTTP 404)")
        with patch.object(publisher.subprocess, "run", return_value=result), patch.object(publisher, "gh") as gh:
            publisher.update_tag("owner/repo", "rolling-ra", "commit")
        gh.assert_called_once_with("api", "repos/owner/repo/git/refs", "-X", "POST", "-f",
                                   "ref=refs/tags/rolling-ra", "-f", "sha=commit")

    def test_existing_tag_moves_and_api_errors_do_not_create_tags(self):
        with patch.object(publisher.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "{}", "")), patch.object(publisher, "gh") as gh:
            publisher.update_tag("owner/repo", "rolling-korium", "commit")
        gh.assert_called_once_with("api", "repos/owner/repo/git/refs/tags/rolling-korium", "-X", "PATCH",
                                   "-f", "sha=commit", "-F", "force=true")
        for error in ("HTTP 401", "HTTP 403", "HTTP 500", "connection failed"):
            with patch.object(publisher.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", error)), patch.object(publisher, "gh") as gh:
                with self.assertRaises(RuntimeError):
                    publisher.update_tag("owner/repo", "rolling-ra", "commit")
                gh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
