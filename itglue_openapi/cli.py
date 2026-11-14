"""Command line interface."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .constants import DEFAULT_CHANGELOG, DEFAULT_OUTPUT, RELEASE_NOTES_URL, SOURCE_URL
from .http import FetchError
from .tracker import SuspiciousSpecError, UpdateResult, update_spec


def write_github_output(path: Path, result: UpdateResult) -> None:
    values = {
        "changed": str(result.changed).lower(),
        "version": result.version,
        "tag": f"v{result.version}" if result.version else "",
        "previous_version": result.previous_version or "",
        "product_version": result.product_version,
    }
    with path.open("a", encoding="utf-8") as file:
        file.writelines(f"{key}={value}\n" for key, value in values.items())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="itglue-openapi",
        description="Convert the IT Glue developer documentation into an OpenAPI spec. "
        "The output file is only rewritten when the API documentation changed.",
    )
    parser.add_argument("--source-url", default=SOURCE_URL, help="IT Glue API documentation URL")
    parser.add_argument("--release-notes-url", default=RELEASE_NOTES_URL, help="IT Glue release notes URL")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="OpenAPI JSON file (default: %(default)s)"
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=DEFAULT_CHANGELOG,
        help="Changelog to append to (default: %(default)s)",
    )
    parser.add_argument("--no-changelog", action="store_true", help="Do not update the changelog")
    parser.add_argument(
        "--release-notes-file", type=Path, help="Write markdown release notes here when changed"
    )
    parser.add_argument(
        "--github-output", type=Path, help="Append step outputs to this file (GitHub Actions)"
    )
    parser.add_argument(
        "--product-version", help="Use this IT Glue product version instead of reading the release notes"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change without writing files"
    )
    parser.add_argument(
        "--force", action="store_true", help="Write the spec even if nothing (or too much) changed"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        result = update_spec(
            args.output,
            source_url=args.source_url,
            release_notes_url=args.release_notes_url,
            changelog=None if args.no_changelog else args.changelog,
            product_version=args.product_version,
            force=args.force,
            dry_run=args.dry_run,
        )
    except (FetchError, SuspiciousSpecError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if result.changed:
        action = "Would write" if args.dry_run else "Wrote"
        print(
            f"{action} {args.output}: version {result.version} "
            f"({result.operation_count} operations; {result.diff.summary()})."
        )
        if args.release_notes_file and not args.dry_run:
            args.release_notes_file.write_text(result.release_notes, encoding="utf-8", newline="\n")
    else:
        print(f"No API changes detected; {args.output} left untouched (version {result.version}).")

    if args.github_output:
        write_github_output(args.github_output, result)
    return 0
