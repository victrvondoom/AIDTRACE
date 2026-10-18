"""Thin FalkorDB wrapper for the consumer graphs. One instance addresses exactly one named graph."""
from falkordb import FalkorDB


class GraphStore:
    def __init__(self, url: str, graph_name: str):
        self.url = url
        self.graph_name = graph_name
        self._db = FalkorDB.from_url(url)
        self._graph = self._db.select_graph(graph_name)

    def query(self, cypher: str, params: dict | None = None) -> list:
        return self._graph.query(cypher, params or {}).result_set

    def ping(self) -> bool:
        try:
            self._db.connection.ping()
            return True
        except Exception:
            return False

    def reset_synthetic_graph(self) -> None:
        """Drop ONLY this synthetic consumer graph (callers guard the name prefix)."""
        try:
            self._graph.delete()
        except Exception:
            pass  # graph does not exist yet
