"""Połączenie z bazą grafową Neo4j.

Klasa `Neo4jConnection` opakowuje oficjalny sterownik `neo4j` i udostępnia prostą
metodę `query()` zwracającą listę słowników. Parametry połączenia czytane są ze
zmiennych środowiskowych (plik `.env`).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()  # wczytuje zmienne z pliku .env (jeśli istnieje)


class Neo4jConnection:
    """Cienki adapter na sterownik Neo4j (wzorzec: jeden driver na aplikację)."""

    def __init__(self, uri: str | None = None, user: str | None = None,
                 password: str | None = None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password123")
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self) -> None:
        """Zamyka pulę połączeń sterownika."""
        if self._driver is not None:
            self._driver.close()

    def verify(self) -> None:
        """Sprawdza łączność z bazą (rzuca wyjątek, gdy brak połączenia)."""
        self._driver.verify_connectivity()

    def query(self, cypher: str, **params) -> list[dict]:
        """Wykonuje zapytanie Cypher i zwraca wyniki jako listę słowników."""
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]


# Pojedyncza, współdzielona instancja używana przez aplikację Flask.
def get_connection() -> Neo4jConnection:
    """Zwraca nowe połączenie (lub współdzieloną instancję) z Neo4j."""
    return Neo4jConnection()
