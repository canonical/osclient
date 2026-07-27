# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""``osclient index``: index operations."""

import sys
from argparse import Namespace, _SubParsersAction

from osclient.cli.io import add_format_argument, emit
from osclient.config import client_from_env

NAME = "index"


def add_subparser(subparsers: _SubParsersAction) -> None:
    """Register ``index`` and its operation verbs."""
    parser = subparsers.add_parser(NAME, help="index-level operations")
    operations = parser.add_subparsers(dest="operation", required=True)

    mapping = operations.add_parser(
        "mapping",
        help="show the mapping for one or more fields (comma-separated / wildcards "
        "allowed); an empty result means the field is unmapped and unqueryable",
    )
    mapping.add_argument(
        "field",
        metavar="FIELD",
        help="field name(s), comma-separated, wildcards allowed",
    )
    mapping.add_argument(
        "--index",
        help="index or pattern to inspect (default: the configured OPENSEARCH_INDEX)",
    )
    add_format_argument(mapping)


def run(args: Namespace) -> None:
    """Build the client from the environment and run the chosen operation."""
    client = client_from_env()
    if client is None:
        sys.exit(2)
    if args.operation == "mapping":
        emit(
            client.field_mapping(args.field, index=args.index),
            "Field mapping",
            args.format,
        )
