SECRET_KEY = "django-http-inspector-tests"
DEBUG = True
ROOT_URLCONF = "tests.urls"
ALLOWED_HOSTS = ["*"]
INSTALLED_APPS = ["django.contrib.contenttypes", "django_http_inspector"]
MIDDLEWARE = []
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]
DJANGO_HTTP_INSPECTOR = {"ENABLED": True, "CAPTURE_MAX_BYTES": 16, "MAX_RECORDS": 100}
