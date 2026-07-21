# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""``osclient`` entrypoint: dispatches to its subcommands."""

import logging
from argparse import ArgumentParser

from osclient.cli import query, triage_cmd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    parser = ArgumentParser(prog="osclient", description="Query an OpenSearch cluster.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    query.add_subparser(subparsers)
    triage_cmd.add_subparser(subparsers)

    args = parser.parse_args()
    if args.subcommand == query.NAME:
        query.run(args)
    elif args.subcommand == triage_cmd.NAME:
        triage_cmd.run(args)


if __name__ == "__main__":
    main()
