# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for osclient.client.OpensearchClient.

The client is transport-agnostic, so these run it over a fake transport that
records the request it received and returns a preset result. The functional tests
exercise the happy path against a real cluster; these pin down request building,
index targeting, and response processing.
"""

from typing import Any, Callable

from osclient.client import DEFAULT_INDEX, OpensearchClient
from osclient.result import Failure, OpensearchResult, Success


class FakeTransport:
    """Records the request() it receives and returns a preset result."""

    def __init__(self, result: OpensearchResult[Any]) -> None:
        self.result = result
        self.calls: list[tuple[str, str, Any, int]] = []

    def request(
        self, method: str, path: str, body: Any = None, timeout: int = 30
    ) -> OpensearchResult[Any]:
        self.calls.append((method, path, body, timeout))
        return self.result


def test_request_delegates_to_the_transport() -> None:
    transport = FakeTransport(Success({"x": 1}))
    res = OpensearchClient(transport).request("PUT", "idx", {"b": 2}, timeout=99)
    assert res.data == {"x": 1}
    assert transport.calls == [("PUT", "idx", {"b": 2}, 99)]


def test_helpers_build_the_expected_request() -> None:
    doc = {"name": "a"}
    script = {"source": "s"}
    # (call, method, path, expected body or None to skip the body check)
    cases: list[tuple[Callable[[OpensearchClient], object], str, str, Any]] = [
        (lambda c: c.field_mapping("f", index="i"), "GET", "i/_mapping/field/f", None),
        (lambda c: c.create_index({"m": 1}, index="i"), "PUT", "i", {"m": 1}),
        (lambda c: c.index_document(doc, index="i", refresh=True), "POST", "i/_doc?refresh=true", doc),
        (lambda c: c.index_document(doc, index="i", doc_id="42"), "PUT", "i/_doc/42", doc),
        (lambda c: c.reindex("s", "d", script=script, wait_for_completion=False, refresh=True),
         "POST", "_reindex?wait_for_completion=false&refresh=true",
         {"source": {"index": "s"}, "dest": {"index": "d"}, "script": script}),
        (lambda c: c.update_by_query({"q": 1}, index="i", conflicts="proceed"),
         "POST", "i/_update_by_query?conflicts=proceed&wait_for_completion=true&refresh=false",
         {"query": {"q": 1}}),
    ]
    for call, method, path, body in cases:
        transport = FakeTransport(Success({}))
        call(OpensearchClient(transport))
        got_method, got_path, got_body, _ = transport.calls[0]
        assert (got_method, got_path) == (method, path)
        if body is not None:
            assert got_body == body


def test_default_index_is_used_and_can_be_overridden() -> None:
    assert OpensearchClient(FakeTransport(Success({}))).default_index == DEFAULT_INDEX == "*"
    transport = FakeTransport(Success({"hits": {"hits": []}}))
    client = OpensearchClient(transport, default_index="logs-*")
    client.search({"q": 1})
    client.search({"q": 1}, index="other-*")
    assert transport.calls[0][1] == "logs-*/_search"
    assert transport.calls[1][1] == "other-*/_search"


def test_search_extracts_each_hit_source() -> None:
    hits = {"hits": {"hits": [{"_source": {"a": 1}}, {"_source": {"a": 2}}]}}
    res = OpensearchClient(FakeTransport(Success(hits))).search({"q": 1})
    assert res.data == [{"a": 1}, {"a": 2}]


def test_version_helpers_process_cat_output() -> None:
    nodes = [{"version": "2.19.1"}, {"version": "2.19.1"}, {"version": "2.18.0"}]
    assert OpensearchClient(FakeTransport(Success(nodes))).opensearch_version().data == [
        "2.18.0",
        "2.19.1",
    ]
    plugins = [{"component": "sql", "version": "1"}, {"component": "sec", "version": "2"}]
    assert OpensearchClient(FakeTransport(Success(plugins))).plugin_versions().data == {
        "sql": "1",
        "sec": "2",
    }


def test_read_helpers_propagate_a_failed_request() -> None:
    res = OpensearchClient(FakeTransport(Failure("500 boom"))).search({"q": 1})
    assert not res
    assert "500" in res.reason
