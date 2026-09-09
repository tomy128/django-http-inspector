from functools import lru_cache
from importlib.resources import files

from django.template import Context, Engine


@lru_cache(maxsize=1)
def _engine():
    root = files("django_http_inspector").joinpath("templates", "django_http_inspector")
    templates = {
        f"django_http_inspector/{name}": root.joinpath(name).read_text(encoding="utf-8")
        for name in ("base.html", "index.html")
    }
    return Engine(
        autoescape=True,
        loaders=[("django.template.loaders.locmem.Loader", templates)],
    )


def render(name, context):
    return _engine().get_template(f"django_http_inspector/{name}").render(Context(context))
