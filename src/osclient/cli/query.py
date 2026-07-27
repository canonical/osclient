# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""``osclient query``: run a query in a chosen language against the cluster.

One verb per invocation, each printing its result as YAML by default:
  query sql <query>   run an OpenSearch SQL query (--explain shows the plan)
  query ppl <query>   run an OpenSearch PPL query (--explain shows the plan)
  query dsl <query>   run a raw query DSL (--count-only returns just the count)

Each <query> may be given literally, as ``-`` to read it from stdin, or as
``@PATH`` to read it from a file.

Connection is read from the OPENSEARCH_* environment variables (see
osclient.config) so the password never lands in shell history.
"""

import json
import logging
import sys
from argparse import Namespace, _SubParsersAction
from typing import Any

from osclient.cli.io import add_format_argument, emit, resolve_source
from osclient.client import OpensearchClient
from osclient.config import client_from_env

NAME = "query"

_SOURCE_EPILOG = (
    "The <query> may be given literally, as '-' to read it from stdin, or as "
    "'@PATH' to read it from a file."
)


def add_subparser(subparsers: _SubParsersAction) -> None:
    """Register ``query`` and its sql/ppl/dsl language verbs."""
    parser = subparsers.add_parser(NAME, help="run a query (SQL, PPL, or raw DSL)")
    languages = parser.add_subparsers(dest="language", required=True)

    sql = languages.add_parser(
        "sql", help="run an OpenSearch SQL query", epilog=_SOURCE_EPILOG
    )
    sql.add_argument("query", help="the SQL query (or '-' / '@PATH')")
    sql.add_argument(
        "--explain",
        action="store_true",
        help="print the execution plan (the pushed-down DSL) instead of running it",
    )
    add_format_argument(sql)

    ppl = languages.add_parser(
        "ppl", help="run an OpenSearch PPL query (v2 engine)", epilog=_SOURCE_EPILOG
    )
    ppl.add_argument("query", help="the PPL query (or '-' / '@PATH')")
    ppl.add_argument(
        "--explain",
        action="store_true",
        help="print the execution plan (the pushed-down DSL) instead of running it",
    )
    add_format_argument(ppl)

    dsl = languages.add_parser(
        "dsl",
        help="run a raw query DSL (a query object or full search body)",
        epilog=_SOURCE_EPILOG,
    )
    dsl.add_argument("query", help="the query DSL as JSON (or '-' / '@PATH')")
    dsl.add_argument(
        "--count-only",
        action="store_true",
        help="route to _count and print only the number of matching documents",
    )
    add_format_argument(dsl)


def _parse_dsl(text: str) -> dict[str, Any]:
    """Parse dsl text into a JSON object, or log an instructive error and exit 2."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        logging.error(f"query dsl is not valid JSON: {error}")
        sys.exit(2)
    if not isinstance(parsed, dict):
        logging.error(
            "query dsl must be a JSON object: a bare query object or a full search body"
        )
        sys.exit(2)
    return parsed


def _search_body_from_dsl(parsed: dict[str, Any]) -> dict[str, Any]:
    """A _search body from parsed DSL: used as-is if it already has a top-level
    ``query``, otherwise wrapped so the object is treated as the query."""
    return parsed if "query" in parsed else {"query": parsed}


def _query_from_dsl(parsed: dict[str, Any]) -> dict[str, Any]:
    """The bare query DSL for _count: the ``query`` of a full body, else the object itself."""
    return parsed["query"] if "query" in parsed else parsed


def _run_sql(client: OpensearchClient, args: Namespace) -> None:
    text = resolve_source(args.query)
    if args.explain:
        emit(client.explain(text), "Explain", args.format)
    else:
        emit(client.sql(text), "SQL query", args.format)


def _run_ppl(client: OpensearchClient, args: Namespace) -> None:
    text = resolve_source(args.query)
    if args.explain:
        emit(client.explain(text, query_type="ppl"), "PPL explain", args.format)
    else:
        emit(client.ppl(text), "PPL query", args.format)


def _run_dsl(client: OpensearchClient, args: Namespace) -> None:
    parsed = _parse_dsl(resolve_source(args.query))
    if args.count_only:
        emit(client.count(_query_from_dsl(parsed)), "Count", args.format)
    else:
        emit(client.search(_search_body_from_dsl(parsed)), "DSL query", args.format)


def run(args: Namespace) -> None:
    """Build the client from the environment and run the chosen language verb."""
    client = client_from_env()
    if client is None:
        sys.exit(2)
    if args.language == "sql":
        _run_sql(client, args)
    elif args.language == "ppl":
        _run_ppl(client, args)
    elif args.language == "dsl":
        _run_dsl(client, args)
