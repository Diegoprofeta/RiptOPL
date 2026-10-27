"""Test publication authorization and first-release/existing-tag transitions."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import publish_editions as publisher


class PublicationTests(unittest.TestCase):
    def test_concise_notes_for_all_three_editions(self):
        sha = "a" * 40
        history = "b" * 40 + "\x00Fix [launch] <edge>"
        for options in publisher.EDITIONS.values():
            with patch.object(publisher, "git", return_value=history) as git:
                body = publisher.release_notes(options, sha, "v1.8.0")
            git.assert_called_once_with("log", "--no-merges", "-10", "--format=%H%x00%s", sha, "--")
            self.assertIn("## Changes\n\n", body)
            self.assertIn(r"Fix \[launch\] \<edge\>", body)
            self.assertIn("/commit/" + "b" * 40, body)
            self.assertIn("/commits/" + sha, body)
            self.assertIn(f"/releases/download/{options['tag']}/RIPTOPL-{options['title']}.zip", body)
            elf = "RIPTOPL-RA.ELF" if options["ra"] else "RIPTOPL.ELF"
            psu = "APP_RIPTOPL-RA.psu" if options["ra"] else "APP_RIPTOPL.psu"
            self.assertIn(f"/{elf})", body)
            self.assertIn(f"/{psu})", body)
            self.assertIn(f"/releases/download/{options['tag']}/RIPTOPL-LANGS.zip)", body)
            self.assertEqual(6 if options["tag"] == "rolling-korium" else 4, sum(line.startswith("- [") for line in body.split("## Downloads\n\n", 1)[1].splitlines()))
            self.assertIn("Included build: v1.8.0 ", body)
            self.assertNotIn("Release compiler", body)
            self.assertNotIn("Imported production documentation", body)
            self.assertLess(len(body), 1800)

    def test_notes_refuse_empty_history(self):
        with patch.object(publisher, "git", return_value=""), self.assertRaises(ValueError):
            publisher.release_notes(publisher.EDITIONS["korium"], "a" * 40, "v1")

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

    def test_only_incebtion_is_designated_latest(self):
        self.assertEqual(set(publisher.EDITIONS), {"korium", "ra", "incebtion"})
        for edition in publisher.EDITIONS:
            expected = "--latest=true" if edition == "incebtion" else "--latest=false"
            self.assertEqual(publisher.latest_release_arg(edition), expected)

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

    def test_draft_release_resolution_uses_release_view_json(self):
        source = (ROOT / "tools" / "publish_editions.py").read_text(encoding="utf-8")
        self.assertIn('gh("release", "view", tag, "--repo", repo, "--json", "id,assets")', source)
        self.assertNotIn('repos/{repo}/releases/tags/{tag}', source)


    def test_gh_retries_transient_failures_then_gives_up(self):
        calls = []

        def flaky(command, text):
            calls.append(command)
            if len(calls) < 3:
                raise subprocess.CalledProcessError(1, command)
            return "ok\n"

        with patch.object(publisher.subprocess, "check_output", side_effect=flaky), \
                patch.object(publisher.time, "sleep") as sleep:
            self.assertEqual(publisher.gh("release", "view", "rolling-ra"), "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], list(publisher.RETRY_DELAYS))
        with patch.object(publisher.subprocess, "check_output", side_effect=subprocess.CalledProcessError(1, "gh")), \
                patch.object(publisher.time, "sleep"), self.assertRaises(subprocess.CalledProcessError):
            publisher.gh("release", "upload", "rolling-ra", "x")

    def release(self, folder, names):
        assets = []
        for name in names:
            (folder / name).write_bytes(name.encode())
            assets.append(str(folder / name))
        return assets

    def test_failed_upload_to_a_published_channel_restores_every_clobbered_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            assets = self.release(folder, ["RIPTOPL-RA.ELF", "APP_RIPTOPL-RA.psu", "RIPTOPL-RA.zip"])
            calls = []

            def fake(*args):
                calls.append(args)
                if args[:2] == ("release", "view"):
                    return json.dumps(dict(assets=[{"name": "RIPTOPL-RA.ELF"}, {"name": "RIPTOPL-RA.zip"}, {"name": "old.txt"}]))
                if args[:2] == ("release", "download"):
                    (Path(args[args.index("--dir") + 1]) / args[args.index("--pattern") + 1]).write_bytes(b"old")
                elif args[:2] == ("release", "upload") and str(folder) in args[-1]:
                    raise subprocess.CalledProcessError(1, "gh")
                return ""

            with patch.object(publisher, "gh", side_effect=fake), self.assertRaises(subprocess.CalledProcessError):
                publisher.upload_verified("owner/repo", "rolling-ra", "a" * 40, "RA", Path("notes"), assets, True)
            restore = calls[-1]
            self.assertEqual(restore[:5], ("release", "upload", "rolling-ra", "--repo", "owner/repo"))
            self.assertEqual(sorted(Path(name).name for name in restore[6:]), ["RIPTOPL-RA.ELF", "RIPTOPL-RA.zip"])
            self.assertFalse(any(call[:2] in (("release", "edit"), ("release", "create")) for call in calls))

    def test_unretained_asset_restores_and_new_drafts_need_no_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            assets = self.release(folder, ["RIPTOPL-RA.ELF"])
            good = dict(name="RIPTOPL-RA.ELF", size=len(b"RIPTOPL-RA.ELF"),
                        digest="sha256:" + hashlib.sha256(b"RIPTOPL-RA.ELF").hexdigest())
            for remote, exists, restored in ((dict(good, size=1), True, True), (good, True, False),
                                             (dict(good, digest="sha256:0"), False, False)):
                calls = []

                def fake(*args):
                    calls.append(args)
                    if args[:2] == ("release", "view"):
                        return json.dumps(dict(id=1, assets=[remote]))
                    if args[:2] == ("release", "download"):
                        (Path(args[args.index("--dir") + 1]) / "RIPTOPL-RA.ELF").write_bytes(b"old")
                    return ""

                with patch.object(publisher, "gh", side_effect=fake):
                    if remote is good:
                        publisher.upload_verified("owner/repo", "rolling-ra", "a" * 40, "RA", Path("notes"), assets, exists)
                    else:
                        with self.assertRaisesRegex(ValueError, "did not retain"):
                            publisher.upload_verified("owner/repo", "rolling-ra", "a" * 40, "RA", Path("notes"), assets, exists)
                restores = [c for c in calls if c[:2] == ("release", "upload") and str(folder) not in c[-1]]
                self.assertEqual(bool(restores), restored)
                if not exists:
                    self.assertIn("--draft", next(c for c in calls if c[:2] == ("release", "create")))

    def test_ra_kit_ships_the_mbedtls_licence_and_ordinary_kits_refuse_it(self):
        package = (ROOT / "tools/package_edition.py").read_text(encoding="utf-8")
        app = (ROOT / ".github/scripts/package_release_app.py").read_text(encoding="utf-8")
        self.assertIn('shutil.copyfile(ROOT / "third_party/mbedtls/LICENSE", kit / "LICENSE-MBEDTLS.txt")', package)
        self.assertIn('required.add("LICENSE-MBEDTLS.txt")', app)
        self.assertIn('elif "LICENSE-MBEDTLS.txt" in all_names:', app)

if __name__ == "__main__":
    unittest.main()
