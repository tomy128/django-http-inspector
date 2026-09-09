from django.test import SimpleTestCase, override_settings

from django_inspect.config import load_config


class ConfigTests(SimpleTestCase):
    def test_path_boundary(self):
        config = load_config()
        self.assertTrue(config.is_inspector_path("/__inspect"))
        self.assertTrue(config.is_inspector_path("/__inspect/requests/1"))
        self.assertFalse(config.is_inspector_path("/__inspector"))

    @override_settings(DJANGO_INSPECT={"PATH": "inspect"})
    def test_invalid_path_fails(self):
        with self.assertRaisesMessage(Exception, "must start"):
            load_config()

    @override_settings(DJANGO_INSPECT={"INSPECTOR_ALLOWED_CLIENT_CIDRS": ["10.0.0.0/8"]})
    def test_non_loopback_access_requires_future_auth_support(self):
        with self.assertRaisesMessage(Exception, "loopback-only"):
            load_config()
