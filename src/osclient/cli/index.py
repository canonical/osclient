# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""``osclient index``: index-level operations (mapping, bulk, lifecycle)."""

import json
import logging
import sys
from argparse import Namespace, _SubParsersAction
from typing import Any

import yaml

from osclient.cli.diagnostics import diagnose
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

    refresh = operations.add_parser(
        "refresh", help="refresh an index so recent writes become searchable"
    )
    refresh.add_argument(
        "--index", required=True, help="the index (or pattern) to refresh"
    )
    add_format_argument(refresh)

    exists = operations.add_parser("exists", help="report whether an index exists")
    exists.add_argument("--index", required=True, help="the index to test")
    add_format_argument(exists)

    delete = operations.add_parser(
        "delete",
        help="delete one index (--index) or every index matching a pattern "
        "(--pattern); dry-run unless --apply",
    )
    target = delete.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--index", help="a single index to delete (must not contain a wildcard)"
    )
    target.add_argument(
        "--pattern", help="delete every index matching this wildcard pattern"
    )
    delete.add_argument(
        "--apply",
        action="store_true",
        help="actually delete; without it, only report what would be deleted",
    )
    add_format_argument(delete)

    listing = operations.add_parser("list", help="list indices matching a pattern")
    listing.add_argument(
        "--pattern", default="*", help="index-name pattern to list (default: all)"
    )
    add_format_argument(listing)


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


def _delete_one(args: Namespace, client: OpensearchClient) -> None:
    """Delete one concrete index; a wildcard here is a mistake (use --pattern)."""
    if "*" in args.index:
        logging.error(
            f"--index {args.index!r} looks like a pattern; use --pattern to delete "
            "several indices at once."
        )
        sys.exit(2)
    if not args.apply:
        # Dry run: name the target and its document count, as a safety readout.
        count = client.count({"match_all": {}}, index=args.index)
        summary = {
            "index": args.index,
            "dry_run": True,
            "documents": count.data if count else None,
        }
        print(render(summary, args.format))
        return
    emit(diagnose(client.delete_index(args.index)), "Delete", args.format)


def _delete_pattern(args: Namespace, client: OpensearchClient) -> None:
    """Delete every index matching a pattern, resolving it to concrete names first.

    Resolving up front means the dry run shows the exact blast radius, and each
    delete targets a concrete name (never a wildcard the cluster might refuse).
    """
    listed = client.list_indices(args.pattern)
    if not listed:
        logging.error(f"could not list indices for {args.pattern!r}: {listed.reason}")
        sys.exit(1)
    names = listed.data
    if not args.apply:
        print(
            render(
                {"pattern": args.pattern, "matches": names, "dry_run": True},
                args.format,
            )
        )
        return
    failures: list[dict[str, Any]] = []
    for name in names:
        res = client.delete_index(name)
        if not res:
            failures.append({"index": name, "reason": res.reason})
    summary: dict[str, Any] = {
        "pattern": args.pattern,
        "deleted": len(names) - len(failures),
        "failed": len(failures),
    }
    if failures:
        summary["failures"] = failures
    print(render(summary, args.format))
    if failures:
        sys.exit(1)


def _run_delete(args: Namespace, client: OpensearchClient) -> None:
    """Delete a single index (--index) or a pattern of indices (--pattern)."""
    if args.index is not None:
        _delete_one(args, client)
    else:
        _delete_pattern(args, client)


def run(args: Namespace, client: OpensearchClient) -> None:
    """Run the chosen operation against the client."""
    if args.operation == "mapping":
        result = client.field_mapping(args.field, index=args.index)
        emit(diagnose(result), "Field mapping", args.format)
    elif args.operation == "bulk":
        documents = _load_documents(resolve_source(args.source), args.input_format)
        result = client.bulk(documents, index=args.index)
        # Print the summary either way (its failures list is the useful part), then
        # exit non-zero if any document failed.
        print(render(result.data, args.format))
        if not result:
            logging.error(result.reason)
            sys.exit(1)
    elif args.operation == "refresh":
        emit(diagnose(client.refresh(index=args.index)), "Refresh", args.format)
    elif args.operation == "exists":
        emit(diagnose(client.index_exists(args.index)), "Exists", args.format)
    elif args.operation == "delete":
        _run_delete(args, client)
    elif args.operation == "list":
        emit(diagnose(client.list_indices(args.pattern)), "List", args.format)
