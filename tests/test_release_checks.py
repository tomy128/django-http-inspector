import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_release.py"
SPEC = importlib.util.spec_from_file_location("check_release", SCRIPT_PATH)
check_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_release)


class ReleaseChecksTests(SimpleTestCase):
    def write_project(self, root, version="0.1.5"):
        project = Path(root) / "pyproject.toml"
        project.write_text(f'[project]\nname = "example"\nversion = "{version}"\n')
        return project

    def write_dist(self, root, version="0.1.5"):
        dist = Path(root) / "dist"
        dist.mkdir()
        for name in check_release.expected_distribution_names(version):
            (dist / name).write_bytes(b"package")
        return dist

    def test_tag_must_exactly_match_project_version(self):
        with TemporaryDirectory() as directory:
            project = self.write_project(directory)
            self.assertEqual(check_release.validate_tag(project, "tag", "v0.1.5"), "0.1.5")
            for ref_type, ref_name in (("branch", "v0.1.5"), ("tag", "0.1.5"), ("tag", "v0.1.6")):
                with self.subTest(ref_type=ref_type, ref_name=ref_name):
                    with self.assertRaises(ValueError):
                        check_release.validate_tag(project, ref_type, ref_name)

    def test_dist_requires_exact_regular_files(self):
        with TemporaryDirectory() as directory:
            dist = self.write_dist(directory)
            check_release.validate_dist(dist, "0.1.5")
            (dist / "extra.txt").write_text("unexpected")
            with self.assertRaises(ValueError):
                check_release.validate_dist(dist, "0.1.5")

    def test_dist_rejects_symlink(self):
        with TemporaryDirectory() as directory:
            dist = self.write_dist(directory)
            wheel = dist / "django_http_inspector-0.1.5-py3-none-any.whl"
            wheel.unlink()
            wheel.symlink_to(dist / "django_http_inspector-0.1.5.tar.gz")
            with self.assertRaises(ValueError):
                check_release.validate_dist(dist, "0.1.5")

    def test_artifact_requires_checksum_and_exact_dist(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_dist(root)
            (root / "SHA256SUMS").write_text("checksums")
            check_release.validate_artifact(root, "0.1.5")
            (root / "extra").mkdir()
            with self.assertRaises(ValueError):
                check_release.validate_artifact(root, "0.1.5")
