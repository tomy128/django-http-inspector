# Releasing to PyPI and GitHub

The distribution name is `django-http-inspector`; the import package is `django_http_inspector`. Releases are created automatically from immutable `v<version>` tags by `.github/workflows/release.yml`.

## One-time repository setup

### 1. Create the GitHub Environment

In `tomy128/django-http-inspector`, open **Settings → Environments → New environment** and create an environment named exactly `pypi`.

- Do not configure required reviewers or a wait timer; releases are intentionally automatic.
- Under deployment branches and tags, restrict deployments to tags matching `v*`.
- Do not add a PyPI token or other publishing secret.

### 2. Configure PyPI Trusted Publishing

On the PyPI project `django-http-inspector`, add a GitHub Trusted Publisher with these exact values:

```text
Owner:        tomy128
Repository:   django-http-inspector
Workflow:     release.yml
Environment:  pypi
```

The Workflow uses short-lived OIDC credentials. It does not need `PYPI_API_TOKEN`, a repository secret, or `.pypirc` credentials.

### 3. Protect release tags

Recommended: create a GitHub Repository Ruleset targeting tags matching `v*`. Restrict tag creation, updates, and deletion to repository maintainers. Anyone who can modify the release Workflow and create a matching tag can initiate a PyPI release.

## Publishing a version

Prepare and merge a normal commit that updates both version declarations and the Changelog:

```text
pyproject.toml                         version = "0.1.6"
src/django_http_inspector/__init__.py  __version__ = "0.1.6"
CHANGELOG.md                           0.1.6 entry
```

Run the local checks before tagging:

```bash
python tests/runtests.py
python scripts/check_release.py tag --ref-type tag --ref-name v0.1.6
# Ensure dist/ is empty before building.
python -m build
python -m twine check dist/*
python scripts/check_release.py dist
```

Push the release commit before its tag, then create the tag on that exact commit:

```bash
git push origin master
git tag v0.1.6
git push origin v0.1.6
```

Do not move or reuse a pushed release tag. Wait for the **Release** Workflow Run to finish, then verify both the PyPI project and GitHub Release page. Different version tags may run independently; each uses its own artifact.

## What the Workflow verifies

The Build Job has read-only repository access and performs the irreversible-release gate:

1. The ref is a tag and exactly equals `v` plus `pyproject.toml` version.
2. The complete Django test suite passes.
3. Build and Twine metadata checks pass.
4. `dist/` contains exactly one expected wheel and one expected source archive.
5. The wheel installs in a fresh environment and includes the public import, templates, and static resources.
6. SHA-256 checksums are generated and the distribution files are uploaded once as a GitHub Actions artifact.

The PyPI Job downloads and verifies that artifact, then publishes with Trusted Publishing. Only that Job receives `id-token: write`. After PyPI succeeds, the GitHub Release Job downloads and verifies the same artifact and creates generated release notes with the wheel, source archive, and `SHA256SUMS` attached.

## Failure recovery

PyPI releases and uploaded files are immutable. Never solve a failed release by moving a pushed tag, enabling `skip-existing`, or rebuilding files for the same Workflow Run.

- **Build failed:** fix the source, increment the version, commit it, and create a new tag.
- **PyPI failed before uploading any file:** fix the Environment, Trusted Publisher, OIDC, or temporary service issue, then rerun only the failed `publish-pypi` Job in the same Workflow Run. GitHub will subsequently run the skipped Release Job using the original artifact.
- **PyPI uploaded only part of the distribution:** do not rerun the complete upload and do not use a long-lived token to patch it. Confirm the state on PyPI, increment the version, and release again.
- **PyPI succeeded but GitHub Release failed:** rerun only `publish-github-release` in the same Workflow Run. If necessary, download that Run's `python-package-distributions` artifact, verify `SHA256SUMS`, and manually create the GitHub Release from those exact files.

Artifacts are retained for 14 days, so investigate a partial failure promptly.

## Manual diagnostics

The Workflow is the production publishing path. These commands are for local package diagnosis only and must not be used to upload a production version:

```bash
python -m build
python -m twine check dist/*
python scripts/check_release.py dist
```

The expected files for `0.1.6` are:

```text
dist/django_http_inspector-0.1.6.tar.gz
dist/django_http_inspector-0.1.6-py3-none-any.whl
```
