# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""``osclient index``: index-level operations (mapping, bulk ingest)."""

import json
import logging
import sys
from argparse import Namespace, _SubParsersAction
from typing import Any

import yaml

from osclient.cli.io import add_format_argument, emit, render, resolve_source
from osclient.client import OpensearchClient

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

    bulk = operations.add_parser(
        "bulk",
        help="index many documents read from a source (json, jsonl, or yaml)",
        epilog="SOURCE is the documents: '@PATH' reads a file, '-' reads stdin, or "
        "give the text literally.",
    )
    bulk.add_argument(
        "source",
        metavar="SOURCE",
        help="the documents to index ('@PATH' for a file, '-' for stdin, or literal)",
    )
    bulk.add_argument(
        "--index", required=True, help="the index to write the documents to"
    )
    bulk.add_argument(
        "--input-format",
        required=True,
        choices=("json", "jsonl", "yaml"),
        help="how to read SOURCE: a json array, one json object per line (jsonl), "
        "or a yaml sequence",
    )
    add_format_argument(bulk)


def _load_documents(text: str, input_format: str) -> list[dict[str, Any]]:
    """Parse the source text into a list of documents, or exit with an error.

    ``json`` is one array (or a single object), ``jsonl`` is one object per line,
    and ``yaml`` is a sequence (or a single mapping).
    """
    try:
        if input_format == "jsonl":
            documents = [json.loads(line) for line in text.splitlines() if line.strip()]
        elif input_format == "json":
            documents = json.loads(text)
        else:
            documents = yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        logging.error(f"could not parse {input_format} documents: {error}")
        sys.exit(2)

    if documents is None:
        documents = []
    if isinstance(documents, dict):
        documents = [documents]
    if not isinstance(documents, list) or not all(
        isinstance(document, dict) for document in documents
    ):
        logging.error(f"{input_format} input must be a list of objects (or one object)")
        sys.exit(2)
    return documents


def run(args: Namespace, client: OpensearchClient) -> None:
    """Run the chosen operation against the client."""
    if args.operation == "mapping":
        emit(
            client.field_mapping(args.field, index=args.index),
            "Field mapping",
            args.format,
        )
    elif args.operation == "bulk":
        documents = _load_documents(resolve_source(args.source), args.input_format)
        result = client.bulk(documents, index=args.index)
        # Print the summary either way (its failures list is the useful part), then
        # exit non-zero if any document failed.
        print(render(result.data, args.format))
        if not result:
            logging.error(result.reason)
            sys.exit(1)
