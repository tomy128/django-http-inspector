"""Public API for django-http-inspector."""

from .wrapper.wsgi import InspectorWSGI

__all__ = ["InspectorWSGI"]
__version__ = "0.1.6"
