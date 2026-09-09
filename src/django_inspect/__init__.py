"""Public API for django-inspect."""

from .wrapper.wsgi import InspectorWSGI

__all__ = ["InspectorWSGI"]
__version__ = "0.1.0"
