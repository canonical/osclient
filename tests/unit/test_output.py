# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for osclient.cli.output."""

import json

import yaml

from osclient.cli import output


def test_yaml_is_insertion_ordered_without_trailing_newline() -> None:
    rendered = output.render({"b": 1, "a": 2}, "yaml")
    assert rendered == "b: 1\na: 2"
    assert yaml.safe_load(rendered) == {"b": 1, "a": 2}


def test_json_round_trips() -> None:
    data = [{"a": 1}, {"a": 2}]
    assert json.loads(output.render(data, "json")) == data


def test_csv_flattens_nested_objects_into_dotted_columns() -> None:
    rows = [{"source": {"ip": "10.0.0.5"}, "rule": {"level": 3}}]
    assert output.render(rows, "csv") == "source.ip,rule.level\n10.0.0.5,3"


def test_csv_unions_columns_and_blanks_missing_cells() -> None:
    rows = [{"a": 1}, {"a": 2, "b": 3}]
    # 'b' first appears in the second row, so it is appended after 'a'.
    assert output.render(rows, "csv") == "a,b\n1,\n2,3"


def test_csv_json_encodes_list_cells() -> None:
    rows = [{"tags": ["x", "y"]}]
    assert output.render(rows, "csv") == 'tags\n"[""x"", ""y""]"'


def test_csv_wraps_a_single_object_as_one_row() -> None:
    assert output.render({"a": 1, "b": 2}, "csv") == "a,b\n1,2"


def test_csv_puts_bare_scalars_under_a_value_column() -> None:
    assert output.render(["7.10.2", "2.11.0"], "csv") == "value\n7.10.2\n2.11.0"


def test_tsv_uses_tabs() -> None:
    assert output.render([{"a": 1, "b": 2}], "tsv") == "a\tb\n1\t2"
