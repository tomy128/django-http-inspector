from pathlib import Path
import re

from django.test import SimpleTestCase


WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"


class ReleaseWorkflowContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workflow = WORKFLOW_PATH.read_text()

    def test_only_version_tags_trigger_release(self):
        self.assertIn('tags:\n      - "v*"', self.workflow)
        self.assertNotIn("pull_request:", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s+branches:")
        self.assertNotIn("concurrency:", self.workflow)

    def test_build_precedes_both_publish_jobs(self):
        self.assertRegex(self.workflow, r"publish-pypi:[\s\S]+?needs: build")
        self.assertRegex(
            self.workflow,
            r"publish-github-release:[\s\S]+?needs:\n\s+- build\n\s+- publish-pypi",
        )
        self.assertEqual(self.workflow.count("actions/upload-artifact@"), 1)
        self.assertEqual(self.workflow.count("actions/download-artifact@"), 2)

    def test_external_actions_are_pinned_to_full_sha(self):
        uses = re.findall(r"uses:\s+([^\s#]+)", self.workflow)
        self.assertEqual(len(uses), 6)
        for action in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r"@[0-9a-f]{40}$")

    def test_tag_and_artifact_validation_are_part_of_release(self):
        self.assertIn("python scripts/check_release.py tag", self.workflow)
        self.assertIn("python scripts/check_release.py dist", self.workflow)
        self.assertEqual(self.workflow.count("sha256sum --check SHA256SUMS"), 2)
        self.assertEqual(self.workflow.count("working-directory: release-artifact"), 2)
        self.assertIn("packages-dir: release-artifact/dist/", self.workflow)

    def test_permissions_are_minimal_and_credentials_are_not_persisted(self):
        self.assertIn("permissions: {}", self.workflow)
        self.assertIn("persist-credentials: false", self.workflow)
        self.assertEqual(self.workflow.count("id-token: write"), 1)
        self.assertEqual(self.workflow.count("contents: write"), 1)
        self.assertIn("contents: read", self.workflow)
        for forbidden in ("password:", "username:", "secrets.", "skip-existing"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.workflow)

    def test_pypi_environment_and_release_assets_are_explicit(self):
        self.assertIn("name: pypi", self.workflow)
        self.assertIn("https://pypi.org/p/django-http-inspector", self.workflow)
        self.assertIn('gh release create "$GITHUB_REF_NAME"', self.workflow)
        self.assertIn('--repo "$GITHUB_REPOSITORY"', self.workflow)
        self.assertEqual(self.workflow.count("actions/checkout@"), 1)
        self.assertIn("release-artifact/SHA256SUMS", self.workflow)
        self.assertIn("--verify-tag", self.workflow)
