from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from django_http_inspector.config import load_config


class ConfigTests(SimpleTestCase):
    def test_allow_remote_is_strict_boolean(self):
        self.assertFalse(load_config().allow_remote)
        for value in (True, False):
            with self.subTest(value=value), override_settings(DJANGO_HTTP_INSPECTOR={"ALLOW_REMOTE": value}):
                self.assertIs(load_config().allow_remote, value)
        for value in ("true", "false", 1, 0, None):
            with self.subTest(value=value), override_settings(DJANGO_HTTP_INSPECTOR={"ALLOW_REMOTE": value}):
                with self.assertRaisesMessage(Exception, "must be a boolean"):
                    load_config()

    def test_path_boundary(self):
        config = load_config()
        self.assertTrue(config.is_inspector_path("/__inspect"))
        self.assertTrue(config.is_inspector_path("/__inspect/requests/1"))
        self.assertFalse(config.is_inspector_path("/__inspector"))

    def test_default_excludes_chrome_devtools_probe(self):
        config = load_config()
        self.assertTrue(config.is_excluded_path("/.well-known/appspecific/com.chrome.devtools.json"))

    @override_settings(DJANGO_HTTP_INSPECTOR={"EXCLUDE_PATHS": []})
    def test_explicit_empty_excludes_replace_defaults(self):
        self.assertFalse(load_config().is_excluded_path("/.well-known/appspecific/com.chrome.devtools.json"))

    @override_settings(DJANGO_HTTP_INSPECTOR={"PATH": "inspect"})
    def test_invalid_path_fails(self):
        with self.assertRaisesMessage(Exception, "must start"):
            load_config()

    @override_settings(DJANGO_HTTP_INSPECTOR={"INSPECTOR_ALLOWED_CLIENT_CIDRS": ["10.0.0.0/8"]})
    def test_non_loopback_access_requires_future_auth_support(self):
        with self.assertRaisesMessage(Exception, "loopback-only"):
            load_config()

    @override_settings(DJANGO_HTTP_INSPECTOR={
        "ALLOW_REMOTE": True,
        "INSPECTOR_ALLOWED_CLIENT_CIDRS": ["10.0.0.0/8"],
        "INSPECTOR_ALLOWED_HOSTS": ["internal.test"],
    })
    def test_remote_mode_keeps_valid_advanced_config_but_skips_loopback_requirement(self):
        config = load_config()
        self.assertTrue(config.allow_remote)
        self.assertEqual(config.inspector_allowed_client_cidrs, ("10.0.0.0/8",))
        self.assertEqual(config.inspector_allowed_hosts, ("internal.test",))

    @override_settings(DJANGO_HTTP_INSPECTOR={
        "INSPECTOR_ALLOWED_CLIENT_CIDRS": (item for item in ["127.0.0.0/8"]),
        "INSPECTOR_ALLOWED_HOSTS": (item for item in ["localhost"]),
    })
    def test_existing_iterable_advanced_config_remains_supported(self):
        config = load_config()
        self.assertEqual(config.inspector_allowed_client_cidrs, ("127.0.0.0/8",))
        self.assertEqual(config.inspector_allowed_hosts, ("localhost",))

    def test_relative_sqlite_path_is_resolved_from_base_dir(self):
        with TemporaryDirectory() as directory, override_settings(
            BASE_DIR=Path(directory), DJANGO_HTTP_INSPECTOR={"SQLITE_PATH": "runtime/inspect.sqlite3"}
        ):
            self.assertEqual(load_config().sqlite_path, (Path(directory) / "runtime/inspect.sqlite3").resolve())

    def test_directory_sqlite_path_is_rejected(self):
        with TemporaryDirectory() as directory, override_settings(
            DJANGO_HTTP_INSPECTOR={"SQLITE_PATH": directory}
        ):
            with self.assertRaisesMessage(Exception, "must be a file"):
                load_config()
