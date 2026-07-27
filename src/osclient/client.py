# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The high-level OpenSearch client (transport-agnostic)."""

from typing import Any

from osclient.jdbc import rows_from_sql_response
from osclient.result import OpensearchResult, Success
from osclient.transport import REQUEST_TIMEOUT, Transport

DEFAULT_INDEX = "*"


def _query_string(params: dict[str, Any]) -> str:
    """Render params as a URL query string (bools lowercased)."""
    parts = []
    for key, value in params.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        parts.append(f"{key}={value}")
    return "?" + "&".join(parts) if parts else ""


class OpensearchClient:
    """Query and administer an OpenSearch cluster over a transport.

    Every operation funnels through the one :meth:`request` primitive (delegated
    to the transport). The named helpers build on it, and each returns an
    :class:`~osclient.result.OpensearchResult`.

    Index-scoped helpers (``search``, ``count``, ``create_index``, ...) target
    :attr:`default_index` unless an explicit ``index`` argument is given.
    """

    def __init__(
        self, transport: Transport, default_index: str = DEFAULT_INDEX
    ) -> None:
        """Initialize the client.

        Args:
            transport (Transport): how requests reach the cluster (direct, proxy,
                probe, or failover).
            default_index (str): the index pattern index-scoped helpers target when
                no explicit ``index`` is passed, e.g. ``logs-*``.
        """
        self._transport = transport
        self.default_index = default_index

    # -- core -------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: int = REQUEST_TIMEOUT,
    ) -> OpensearchResult[Any]:
        """Send an arbitrary request to the cluster.

        Args:
            method (str): the HTTP method, e.g. ``GET``, ``POST`` or ``PUT``.
            path (str): the OpenSearch path (no leading slash), query string
                allowed, e.g. ``my-index/_search``.
            body (dict[str, Any] | None): optional JSON request body.
            timeout (int): request timeout in seconds; override for operations that
                can run longer than a search.
        """
        return self._transport.request(method, path, body, timeout)

    def get(self, path: str) -> OpensearchResult[Any]:
        """GET an arbitrary OpenSearch path, e.g. ``_cat/plugins?format=json``."""
        return self.request("GET", path)

    # -- reads ------------------------------------------------------------

    def search_raw(
        self, query: dict[str, Any], index: str | None = None
    ) -> OpensearchResult[dict[str, Any]]:
        """Run a search and return the full response (hits, aggregations, ...)."""
        return self.request("POST", f"{index or self.default_index}/_search", query)

    def search(
        self, query: dict[str, Any], index: str | None = None
    ) -> OpensearchResult:
        """Run a search against the index, returning each hit's ``_source``."""
        res = self.search_raw(query, index)
        if not res:
            return res
        hits = res.data.get("hits", {}).get("hits", [])
        return Success([hit.get("_source", {}) for hit in hits])

    def count(
        self, query: dict[str, Any], index: str | None = None
    ) -> OpensearchResult[int]:
        """Count documents matching a DSL query via the ``_count`` API."""
        res = self.request(
            "POST", f"{index or self.default_index}/_count", {"query": query}
        )
        if not res:
            return res
        return Success(res.data.get("count", 0))

    def sql_raw(self, sql_query: str) -> OpensearchResult[dict[str, Any]]:
        """Run a SQL query and return the raw jdbc response (schema + datarows)."""
        return self.request("POST", "_plugins/_sql", {"query": sql_query})

    def sql(self, sql_query: str) -> OpensearchResult:
        """Run a SQL query against the index, returning the rows as dicts."""
        res = self.sql_raw(sql_query)
        if not res:
            return res
        return Success(rows_from_sql_response(res.data))

    def ppl(self, ppl_query: str) -> OpensearchResult[list[dict[str, Any]]]:
        """Run a PPL query against the index, returning the rows as dicts."""
        res = self.request("POST", "_plugins/_ppl", {"query": ppl_query})
        if not res:
            return res
        return Success(rows_from_sql_response(res.data))

    def explain(
        self, query: str, query_type: str = "sql"
    ) -> OpensearchResult[dict[str, Any]]:
        """Return the SQL execution plan (the pushed-down query DSL), unexecuted.

        query_type must be one of: sql, ppl.
        """
        return self.request("POST", f"_plugins/{query_type}/_explain", {"query": query})

    def get_mapping(self, index: str | None = None) -> OpensearchResult[dict[str, Any]]:
        """Return the full mapping for the index (or pattern)."""
        return self.request("GET", f"{index or self.default_index}/_mapping")

    def field_mapping(
        self, field: str, index: str | None = None
    ) -> OpensearchResult[Any]:
        """Return the mapping for one or more fields (wildcards allowed) on the index.

        An empty ``mappings`` for an index means the field is not mapped there, and
        so cannot be resolved by SQL or a term filter even when it appears in a
        document's ``_source``.
        """
        return self.request(
            "GET", f"{index or self.default_index}/_mapping/field/{field}"
        )

    def opensearch_version(self) -> OpensearchResult[list[str]]:
        """Return the distinct OpenSearch versions running across the cluster's nodes."""
        res = self.get("_cat/nodes?h=version&format=json")
        if not res:
            return res
        return Success(sorted({node.get("version") for node in res.data}))

    def plugin_versions(self) -> OpensearchResult[dict[str, str]]:
        """Return the installed plugins mapped to their versions."""
        res = self.get("_cat/plugins?h=component,version&format=json")
        if not res:
            return res
        return Success({p.get("component"): p.get("version") for p in res.data})

    # -- writes / admin ---------------------------------------------------

    def index_document(
        self,
        document: dict[str, Any],
        index: str | None = None,
        *,
        doc_id: str | None = None,
        refresh: bool = False,
    ) -> OpensearchResult[dict[str, Any]]:
        """Index a single document.

        Without ``doc_id`` OpenSearch assigns one (``POST <index>/_doc``); with it
        the document is created or replaced at that id (``PUT <index>/_doc/<id>``).
        ``refresh=True`` makes the document immediately searchable.
        """
        idx = index or self.default_index
        if doc_id is not None:
            method, path = "PUT", f"{idx}/_doc/{doc_id}"
        else:
            method, path = "POST", f"{idx}/_doc"
        if refresh:
            path += "?refresh=true"
        return self.request(method, path, document)

    def create_index(
        self, body: dict[str, Any], index: str | None = None
    ) -> OpensearchResult[dict[str, Any]]:
        """Create an index with the given settings/mappings body (``PUT <index>``)."""
        return self.request("PUT", index or self.default_index, body)

    def reindex(
        self,
        source: str,
        dest: str,
        *,
        script: dict[str, Any] | None = None,
        wait_for_completion: bool = True,
        refresh: bool = False,
        timeout: int = REQUEST_TIMEOUT,
    ) -> OpensearchResult[dict[str, Any]]:
        """Copy documents from ``source`` into ``dest`` (``POST _reindex``).

        ``script`` optionally transforms each document as it is copied. With
        ``wait_for_completion=False`` the call returns a task id to poll (see
        :meth:`get_task`). For advanced options (a source query, a destination
        pipeline, ...) build the request with :meth:`request` directly.
        """
        body: dict[str, Any] = {"source": {"index": source}, "dest": {"index": dest}}
        if script is not None:
            body["script"] = script
        path = "_reindex" + _query_string(
            {"wait_for_completion": wait_for_completion, "refresh": refresh}
        )
        return self.request("POST", path, body, timeout)

    def update_by_query(
        self,
        query: dict[str, Any],
        index: str | None = None,
        *,
        script: dict[str, Any] | None = None,
        conflicts: str | None = None,
        wait_for_completion: bool = True,
        refresh: bool = False,
        timeout: int = REQUEST_TIMEOUT,
    ) -> OpensearchResult[dict[str, Any]]:
        """Update documents matching ``query`` in place (``POST _update_by_query``).

        ``script`` transforms each matched document. With
        ``wait_for_completion=False`` the call returns a task id to poll (see
        :meth:`get_task`). ``conflicts="proceed"`` continues past version conflicts
        instead of aborting.
        """
        body: dict[str, Any] = {"query": query}
        if script is not None:
            body["script"] = script
        params: dict[str, Any] = {}
        if conflicts is not None:
            params["conflicts"] = conflicts
        params["wait_for_completion"] = wait_for_completion
        params["refresh"] = refresh
        path = f"{index or self.default_index}/_update_by_query" + _query_string(params)
        return self.request("POST", path, body, timeout)

    def get_task(self, task_id: str) -> OpensearchResult[dict[str, Any]]:
        """Return a task document by id (``GET _tasks/<task_id>``)."""
        return self.request("GET", f"_tasks/{task_id}")
