# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""``osclient`` entrypoint: dispatches to its subcommands."""

import logging
from argparse import ArgumentParser

from osclient.cli import cluster, index, query, search, triage_cmd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Each command module exposes NAME, add_subparser(subparsers) and run(args).
_COMMANDS = (query, search, index, cluster, triage_cmd)


def main() -> None:
    parser = ArgumentParser(prog="osclient", description="Query an OpenSearch cluster.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    for command in _COMMANDS:
        command.add_subparser(subparsers)

    args = parser.parse_args()
    for command in _COMMANDS:
        if args.subcommand == command.NAME:
            command.run(args)
            return


if __name__ == "__main__":
    main()
