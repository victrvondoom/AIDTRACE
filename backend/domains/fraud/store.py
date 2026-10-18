"""FalkorDB access for the fraud graphs.

Deliberately self-contained (falkordb only, no `api` package imports) so the MCP server can run as a small private
process in its own environment, away from the pins that conflict with the MCP SDK.
"""
from falkordb import FalkorDB

from domains.fraud import config


class GraphStore:
    """One instance addresses exactly one named graph."""

    def __init__(self, url: str | None = None, graph_name: str | None = None):
        self.url = url or config.FALKORDB_URL
        self.graph_name = graph_name or config.GRAPH_NAME
        self._db = FalkorDB.from_url(self.url)
        self._graph = self._db.select_graph(self.graph_name)

    def query(self, cypher: str, params: dict | None = None) -> list:
        return self._graph.query(cypher, params or {}).result_set

    def ping(self) -> bool:
        try:
            self._db.connection.ping()
            return True
        except Exception:
            return False

    def reset_synthetic_graph(self) -> None:
        """Drop ONLY this synthetic fraud graph."""
        try:
            self._graph.delete()
        except Exception:
            pass  # graph does not exist yet
