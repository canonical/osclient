# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for osclient.cli.search helpers."""

from osclient.cli import search
from osclient.client import OpensearchClient
from osclient.result import OpensearchResult, Success


class _Transport:
    """Returns a preset result for any request."""

    def __init__(self, result: OpensearchResult) -> None:
        self._result = result

    def request(self, *_: object, **__: object) -> OpensearchResult:
        return self._result


def test_unmapped_fields_returns_the_fields_absent_from_the_mapping() -> None:
    # field_mapping returns {index: {"mappings": {field: {...}}}}; empty = unmapped.
    mapped = OpensearchClient(
        _Transport(Success({"idx": {"mappings": {"f": {"full_name": "f"}}}}))
    )
    assert search._unmapped_fields(mapped, ["f"], index=None) == []
    unmapped = OpensearchClient(_Transport(Success({"idx": {"mappings": {}}})))
    assert search._unmapped_fields(unmapped, ["f"], index=None) == ["f"]
