#!/usr/bin/env python3
"""Validate release tags and immutable distribution artifact layouts."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10 local maintenance environments.
    tomllib = None


def project_version(project_file: Path) -> str:
    if tomllib is not None:
        with project_file.open("rb") as handle:
            return tomllib.load(handle)["project"]["version"]

    in_project = False
    for line in project_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if in_project:
            match = re.fullmatch(r'version\s*=\s*(["\'])([^"\']+)\1\s*', stripped)
            if match:
                return match.group(2)
    raise ValueError("missing a quoted [project].version")


def expected_distribution_names(version: str) -> set[str]:
    base = f"django_http_inspector-{version}"
    return {f"{base}.tar.gz", f"{base}-py3-none-any.whl"}


def validate_tag(project_file: Path, ref_type: str, ref_name: str) -> str:
    version = project_version(project_file)
    expected_tag = f"v{version}"
    if ref_type != "tag":
        raise ValueError(f"release ref must be a tag, got {ref_type!r}")
    if ref_name != expected_tag:
        raise ValueError(f"release tag {ref_name!r} must exactly match {expected_tag!r}")
    return version


def _require_plain_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected a regular file: {path}")


def validate_dist(dist_dir: Path, version: str) -> None:
    if dist_dir.is_symlink() or not dist_dir.is_dir():
        raise ValueError(f"expected a directory: {dist_dir}")
    entries = list(dist_dir.iterdir())
    names = {entry.name for entry in entries}
    expected = expected_distribution_names(version)
    if names != expected:
        raise ValueError(f"distribution files must be exactly {sorted(expected)}, got {sorted(names)}")
    for entry in entries:
        _require_plain_file(entry)


def validate_artifact(artifact_dir: Path, version: str) -> None:
    if artifact_dir.is_symlink() or not artifact_dir.is_dir():
        raise ValueError(f"expected a directory: {artifact_dir}")
    entries = {entry.name: entry for entry in artifact_dir.iterdir()}
    if set(entries) != {"SHA256SUMS", "dist"}:
        raise ValueError(
            "artifact root must contain exactly SHA256SUMS and dist, "
            f"got {sorted(entries)}"
        )
    _require_plain_file(entries["SHA256SUMS"])
    validate_dist(entries["dist"], version)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    tag = subparsers.add_parser("tag")
    tag.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    tag.add_argument("--ref-type", default=os.environ.get("GITHUB_REF_TYPE", ""))
    tag.add_argument("--ref-name", default=os.environ.get("GITHUB_REF_NAME", ""))

    dist = subparsers.add_parser("dist")
    dist.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    dist.add_argument("--path", type=Path, default=Path("dist"))

    artifact = subparsers.add_parser("artifact")
    artifact.add_argument("--version", required=True)
    artifact.add_argument("--path", type=Path, default=Path("release-artifact"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "tag":
            validate_tag(args.project, args.ref_type, args.ref_name)
        elif args.command == "dist":
            validate_dist(args.path, project_version(args.project))
        else:
            validate_artifact(args.path, args.version)
    except (KeyError, OSError, ValueError) as exc:
        print(f"release validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
