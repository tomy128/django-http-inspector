# Releasing to PyPI

The distribution name is `django-http-inspector`; the Python import package is `django_http_inspector`. The older `django-inspect` distribution and `django_inspect` import package belong to a different project.

PyPI names are first-come, first-served. A currently missing project page does not reserve the name, so publish promptly after the final check.

## Prerequisites

1. Create and verify a PyPI account.
2. Enable two-factor authentication.
3. Install release tools in an isolated environment:

   ```bash
   python -m pip install --upgrade build twine
   ```

4. For a manual first release, create an account-scoped API token. After the project exists, replace it with a project-scoped token. Use `__token__` as the username when prompted.

Never commit a token or `.pypirc` containing credentials.

## Build and validate

Run from the repository root on a clean commit:

```bash
python tests/runtests.py
DJANGO_SETTINGS_MODULE=tests.settings python -m django makemigrations django_http_inspector --check --dry-run
python -m build
python -m twine check dist/*
```

The release must contain exactly one source archive and one universal wheel for the selected version:

```text
dist/django_http_inspector-0.1.0.tar.gz
dist/django_http_inspector-0.1.0-py3-none-any.whl
```

Install the wheel into a fresh virtual environment and verify the public import before upload:

```bash
python -m venv /tmp/django-http-inspector-release-check
/tmp/django-http-inspector-release-check/bin/python -m pip install dist/django_http_inspector-0.1.0-py3-none-any.whl
/tmp/django-http-inspector-release-check/bin/python -c "from django_http_inspector import InspectorWSGI; print(InspectorWSGI)"
```

## Optional TestPyPI rehearsal

TestPyPI has separate accounts and project names:

```bash
python -m twine upload --repository testpypi dist/*
```

Because Django comes from the main index, test installation normally needs both indexes:

```bash
python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  django-http-inspector==0.1.0
```

## Production upload

Review the filenames and version one last time, then run:

```bash
python -m twine upload \
  dist/django_http_inspector-0.1.0.tar.gz \
  dist/django_http_inspector-0.1.0-py3-none-any.whl
```

PyPI releases are immutable: the same version cannot be uploaded again. Any correction requires a new version and a clean rebuild.

After upload, verify from a fresh environment:

```bash
python -m pip install django-http-inspector==0.1.0
python -c "from django_http_inspector import InspectorWSGI; print(InspectorWSGI)"
```

For later automated releases, prefer PyPI Trusted Publishing with short-lived OIDC credentials instead of storing a long-lived token in CI.
