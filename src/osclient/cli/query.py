# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""``osclient query`` subcommand: read-only queries against the cluster.

One mode per invocation, each printing its result as YAML:
  --sql                     run an OpenSearch SQL query
  --ppl                     run an OpenSearch PPL query
  --explain                 show an SQL query's execution plan
  --versions                show OpenSearch and installed-plugin versions
  --mapping FIELD           show the index mapping for FIELD (wildcards allowed)
  --search FIELD=VALUE ...  the newest --count docs matching all FIELD=VALUE pairs

Connection is read from the OPENSEARCH_* environment variables (see
osclient.config) so the password never lands in shell history.
"""

import logging
import sys
from argparse import Namespace, _SubParsersAction
from typing import Any

from osclient.cli.io import add_format_argument, render, resolve_source
from osclient.client import OpensearchClient
from osclient.config import client_from_env
from osclient.result import OpensearchResult

NAME = "query"


def add_subparser(subparsers: _SubParsersAction) -> None:
    """Register the ``query`` subcommand and its mutually-exclusive modes."""
    parser = subparsers.add_parser(
        NAME,
        help="run a read-only query against the cluster",
        epilog="A --sql/--ppl/--explain value may be given literally, as '-' to "
        "read the query from stdin, or as '@PATH' to read it from a file.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--sql",
        help="run this SQL query against the cluster, print the rows as YAML, and exit",
    )
    mode.add_argument(
        "--ppl",
        help="run this PPL query (always the v2 engine), print the rows as YAML, and exit",
    )
    mode.add_argument(
        "--explain",
        metavar="SQL",
        help="print the SQL query's execution plan (the pushed-down DSL) as YAML, and exit",
    )
    mode.add_argument(
        "--versions",
        action="store_true",
        help="print OpenSearch and plugin versions (incl. opensearch-sql) as YAML, and exit",
    )
    mode.add_argument(
        "--mapping",
        metavar="FIELD",
        help="print the index mapping for FIELD (comma-separated / wildcards allowed) "
        "as YAML, and exit; empty means the field is unmapped and unqueryable",
    )
    mode.add_argument(
        "--search",
        nargs="+",
        metavar="FIELD=VALUE",
        help="term-search for the newest --count documents matching all FIELD=VALUE "
        "pairs; print each _source as YAML, and exit",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="number of most-recent results to return in --search mode (default: 1)",
    )
    add_format_argument(parser)


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


def build_term_search(terms: list[tuple[str, list[str]]], size: int) -> dict[str, Any]:
    """Build an OpenSearch _search body that ANDs the given term filters.

    A single value becomes a ``term`` filter; several become a ``terms`` filter.
    These match exact (keyword) field values, mirroring a dashboard filter.

    Results are sorted by ``@timestamp`` descending so we always get the most
    recent ``size`` documents. ``unmapped_type`` keeps the sort from erroring on
    an index in the pattern that lacks the field.
    """
    filters: list[dict[str, Any]] = []
    for field, values in terms:
        if len(values) == 1:
            filters.append({"term": {field: values[0]}})
        else:
            filters.append({"terms": {field: values}})
    return {
        "size": size,
        "sort": [{"@timestamp": {"order": "desc", "unmapped_type": "date"}}],
        "query": {"bool": {"filter": filters}},
    }


def _emit(res: OpensearchResult[Any], label: str, fmt: str) -> None:
    """Print a result's data in the chosen format, or log its reason and exit 1."""
    if not res.ok:
        logging.error(f"{label} failed: {res.reason}")
        sys.exit(1)
    print(render(res.data, fmt))


def run(args: Namespace) -> None:
    """Build the client from the environment and run the chosen query mode."""
    client = client_from_env()
    if client is None:
        sys.exit(2)

    if args.sql:
        _emit(client.sql(resolve_source(args.sql)), "SQL query", args.format)
        return
    if args.ppl:
        _emit(client.ppl(resolve_source(args.ppl)), "PPL query", args.format)
        return
    if args.explain:
        _emit(client.explain(resolve_source(args.explain)), "Explain", args.format)
        return
    if args.versions:
        print(render(get_versions(client), args.format))
        return
    if args.mapping:
        _emit(client.field_mapping(args.mapping), "Field mapping", args.format)
        return

    terms: list[tuple[str, list[str]]] = []
    for token in args.search:
        if "=" not in token:
            logging.error(f"--search term must be FIELD=VALUE: {token!r}")
            sys.exit(2)
        field, value = token.split("=", 1)
        terms.append((field, [value]))
    _emit(
        client.search(build_term_search(terms, size=args.count)), "Search", args.format
    )
