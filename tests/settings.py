from pathlib import Path
import tempfile

SECRET_KEY = "django-http-inspector-tests"
DEBUG = True
ROOT_URLCONF = "tests.urls"
ALLOWED_HOSTS = ["*"]
BASE_DIR = Path(tempfile.mkdtemp(prefix="django-http-inspector-tests-"))
INSTALLED_APPS = []
MIDDLEWARE = []
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TEMPLATES = []
DJANGO_HTTP_INSPECTOR = {
    "ENABLED": True,
    "CAPTURE_MAX_BYTES": 16,
    "MAX_RECORDS": 100,
    "SQLITE_PATH": BASE_DIR / "inspector.sqlite3",
}
