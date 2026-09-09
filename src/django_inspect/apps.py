from django.apps import AppConfig


class DjangoInspectConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_inspect"
    verbose_name = "Django Inspect"
