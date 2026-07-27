# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""CLI IO: resolve input arguments and render output."""

import csv
import json
import logging
import sys
from argparse import ArgumentParser
from io import StringIO
from typing import Any

import yaml

FORMATS = ("yaml", "json", "csv", "tsv")
DEFAULT_FORMAT = "yaml"


def add_format_argument(parser: ArgumentParser) -> None:
    """Add the shared ``--format`` option (yaml/json/csv/tsv, default yaml)."""
    parser.add_argument(
        "--format",
        choices=FORMATS,
        default=DEFAULT_FORMAT,
        help="output format for data printed to stdout (default: yaml)",
    )


def resolve_source(value: str) -> str:
    """Resolve a CLI text argument that may name where to read the text from.

    One convention, shared by the query modes and triage's ``--where``:

        <text>   the value is the text itself
        -        read the text from stdin
        @PATH    read the text from the file at PATH

    Stdin and file contents are stripped of surrounding whitespace; a literal
    value is returned unchanged. On an unreadable ``@PATH`` this logs an
    instructive error and exits, rather than letting an OSError traceback reach
    the user.
    """
    if value == "-":
        return sys.stdin.read().strip()
    if value.startswith("@"):
        path = value[1:]
        try:
            with open(path, mode="r", encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError as error:
            logging.error(f"could not read file {path!r}: {error}")
            sys.exit(2)
    return value


def _flatten(record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested objects into dotted keys; leave list/scalar values intact."""
    flat: dict[str, Any] = {}
    for key, value in record.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, dotted))
        else:
            flat[dotted] = value
    return flat


def _cell(value: Any) -> str:
    """Render a single flattened value for a csv/tsv cell."""
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, default=str)
    return str(value)


def _delimited(data: Any, delimiter: str) -> str:
    """Render data as delimited text: one row per record, dotted union columns."""
    records = data if isinstance(data, list) else [data]
    flat_rows: list[dict[str, Any]] = []
    columns: dict[str, None] = {}
    for record in records:
        row = record if isinstance(record, dict) else {"value": record}
        flat = _flatten(row)
        flat_rows.append(flat)
        for column in flat:
            columns.setdefault(column, None)

    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerow(list(columns))
    for flat in flat_rows:
        writer.writerow([_cell(flat.get(column)) for column in columns])
    return buffer.getvalue().rstrip("\n")


def render(data: Any, fmt: str) -> str:
    """Render data in the chosen format, without a trailing newline."""
    if fmt == "yaml":
        return yaml.dump(data, indent=2, sort_keys=False).rstrip("\n")
    if fmt == "json":
        return json.dumps(data, indent=2, default=str)
    if fmt == "csv":
        return _delimited(data, ",")
    if fmt == "tsv":
        return _delimited(data, "\t")
    raise ValueError(f"unknown format: {fmt!r}")
