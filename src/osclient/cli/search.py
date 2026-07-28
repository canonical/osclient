# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""``osclient search``: find the newest documents matching exact FIELD=VALUE terms.

A convenience term-lookup (not a query language): each FIELD=VALUE is an exact
match, all ANDed, and the newest ``--count`` matches are returned most-recent
first. ``--count-only`` prints just the number of matches instead.
"""

import logging
import sys
from argparse import Namespace, _SubParsersAction
from typing import Any

from osclient.cli.io import (
    add_format_argument,
    add_time_range_arguments,
    emit,
    time_range_filter,
)
from osclient.client import OpensearchClient

NAME = "search"


def add_subparser(subparsers: _SubParsersAction) -> None:
    """Register the ``search`` subcommand."""
    parser = subparsers.add_parser(
        NAME, help="find the newest documents matching exact FIELD=VALUE terms"
    )
    parser.add_argument(
        "terms",
        nargs="+",
        metavar="FIELD=VALUE",
        help="exact field=value term filters, ANDed together",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="number of most-recent documents to return (default: 1)",
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="print only the number of matching documents (via _count)",
    )
    add_time_range_arguments(parser)
    add_format_argument(parser)


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


def run(args: Namespace, client: OpensearchClient) -> None:
    """Run the term search against the client."""
    terms: list[tuple[str, list[str]]] = []
    for token in args.terms:
        if "=" not in token:
            logging.error(f"search term must be FIELD=VALUE: {token!r}")
            sys.exit(2)
        field, value = token.split("=", 1)
        terms.append((field, [value]))

    body = build_term_search(terms, size=args.count)
    time_filter = time_range_filter(args)
    if time_filter is not None:
        body["query"]["bool"]["filter"].append(time_filter)

    if args.count_only:
        emit(client.count(body["query"]), "Count", args.format)
    else:
        emit(client.search(body), "Search", args.format)
