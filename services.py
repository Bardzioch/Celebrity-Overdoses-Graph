"""Warstwa logiki biznesowej (serwis) operująca na bazie grafowej.

`CelebrityService` tłumaczy żądania kontrolera (Flask) na zapytania Cypher z
modułu `queries` i formatuje wyniki do postaci wygodnej dla frontendu
(biblioteka vis-network oczekuje list `nodes` i `edges`).
"""
from __future__ import annotations

from db import Neo4jConnection
import queries

# Etykiety relacji w języku polskim (dla czytelnego opisu ścieżek/krawędzi).
REL_LABELS_PL = {
    "DIED_FROM": "zmarł(a) od",
    "SPOUSE": "małżeństwo",
    "PARTNER": "partner",
    "RELATIVE": "krewny",
}


def _edges_to_graph(rows: list[dict]) -> dict:
    """Zamienia wiersze (a_*, b_*, rel_type) na strukturę {nodes, edges}.

    Węzły są deduplikowane po `id`; krawędzie zachowują typ relacji.
    """
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for r in rows:
        for prefix in ("a", "b"):
            nid = r[f"{prefix}_id"]
            if nid not in nodes:
                nodes[nid] = {
                    "id": nid,
                    "label": r[f"{prefix}_name"],
                    "group": r[f"{prefix}_label"],  # Celebrity / Cause
                }
        edges.append({
            "from": r["a_id"],
            "to": r["b_id"],
            "type": r["rel_type"],
            "label": REL_LABELS_PL.get(r["rel_type"], r["rel_type"]),
        })
    return {"nodes": list(nodes.values()), "edges": edges}


class CelebrityService:
    """Operacje wysokiego poziomu na grafie celebrytów i substancji."""

    def __init__(self, conn: Neo4jConnection):
        self.conn = conn

    # --- proste listy ---
    def get_celebrities(self) -> list[dict]:
        """Zwraca listę wszystkich celebrytów (posortowaną po nazwie)."""
        return self.conn.query(queries.GET_CELEBRITIES)

    def get_causes(self) -> list[dict]:
        """Zwraca listę wszystkich przyczyn śmierci (z flagą is_drug)."""
        return self.conn.query(queries.GET_CAUSES)

    def dangerous_substances(self) -> list[dict]:
        """Zwraca ranking substancji wg liczby zgonów (DIED_FROM)."""
        return self.conn.query(queries.DANGEROUS_SUBSTANCES)

    def stats(self) -> dict:
        """Zwraca podstawowe statystyki grafu (liczność węzłów/relacji)."""
        rows = self.conn.query(queries.STATS)
        return rows[0] if rows else {}

    # --- grafy ---
    def ego_network(self, celebrity_id: str, depth: int = 1) -> dict:
        """Zwraca ego-sieć (węzły+krawędzie) wokół wskazanego celebryty."""
        depth = 2 if int(depth) >= 2 else 1  # walidacja: tylko 1 lub 2
        cypher = queries.NETWORK_TEMPLATE.format(depth=depth)
        rows = self.conn.query(cypher, id=celebrity_id)
        return _edges_to_graph(rows)

    def full_graph(self) -> dict:
        """Zwraca cały graf w formacie dla vis-network."""
        rows = self.conn.query(queries.FULL_GRAPH)
        return _edges_to_graph(rows)

    # --- ścieżki ---
    def find_path(self, from_id: str, to_id: str) -> dict:
        """Znajduje najkrótszą ścieżkę między dwoma celebrytami.

        Zwraca słownik z: listą węzłów, listą typów relacji, czytelnymi krokami
        oraz strukturą {nodes, edges} do wizualizacji. Gdy ścieżki brak –
        `found: False`.
        """
        rows = self.conn.query(queries.SHORTEST_PATH, from_id=from_id, to_id=to_id)
        if not rows or not rows[0].get("nodes"):
            return {"found": False, "nodes": [], "edges": [], "steps": []}

        path_nodes = rows[0]["nodes"]
        rels = rows[0]["rels"]

        # Czytelne kroki tekstowe: A --(relacja)--> B
        steps = []
        for i, rel in enumerate(rels):
            steps.append({
                "from": path_nodes[i]["name"],
                "to": path_nodes[i + 1]["name"],
                "type": rel,
                "label": REL_LABELS_PL.get(rel, rel),
            })

        # Struktura graficzna ścieżki.
        nodes = [{"id": n["id"], "label": n["name"], "group": n["label"]}
                 for n in path_nodes]
        edges = []
        for i, rel in enumerate(rels):
            edges.append({
                "from": path_nodes[i]["id"],
                "to": path_nodes[i + 1]["id"],
                "type": rel,
                "label": REL_LABELS_PL.get(rel, rel),
            })
        return {
            "found": True,
            "length": len(rels),
            "nodes": nodes,
            "edges": edges,
            "steps": steps,
        }
