# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""``osclient cluster``: cluster-level inspection."""

import sys
from argparse import Namespace, _SubParsersAction
from typing import Any

from osclient.cli.io import add_format_argument, render
from osclient.client import OpensearchClient
from osclient.config import client_from_env

NAME = "cluster"


def add_subparser(subparsers: _SubParsersAction) -> None:
    """Register ``cluster`` and its inspection verbs."""
    parser = subparsers.add_parser(NAME, help="cluster-level inspection")
    operations = parser.add_subparsers(dest="operation", required=True)

    versions = operations.add_parser(
        "versions", help="show OpenSearch and installed-plugin versions"
    )
    add_format_argument(versions)


def get_versions(client: OpensearchClient) -> dict[str, Any]:
    """Collect OpenSearch and installed-plugin versions.

    SQL and PPL are both provided by the single ``opensearch-sql`` plugin, so its
    version covers both. Each lookup is independent: if one fails its error is
    recorded and the other is still returned.
    """
    versions: dict[str, Any] = {}
    opensearch = client.opensearch_version()
    versions["opensearch"] = (
        opensearch.data if opensearch.ok else {"error": opensearch.reason}
    )
    plugins = client.plugin_versions()
    versions["plugins"] = plugins.data if plugins.ok else {"error": plugins.reason}
    return versions


def run(args: Namespace) -> None:
    """Build the client from the environment and run the chosen operation."""
    client = client_from_env()
    if client is None:
        sys.exit(2)
    if args.operation == "versions":
        print(render(get_versions(client), args.format))
