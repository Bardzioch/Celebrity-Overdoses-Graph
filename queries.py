"""Zapytania Cypher używane w projekcie (zebrane w jednym miejscu).

Trzymanie zapytań jako nazwanych stałych ułatwia ich ponowne użycie, testowanie
oraz prezentację struktury grafu na zajęciach.
"""

# --- DDL: ograniczenia (unikalność identyfikatorów) ------------------------

CONSTRAINTS = [
    "CREATE CONSTRAINT celebrity_id IF NOT EXISTS "
    "FOR (c:Celebrity) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT cause_id IF NOT EXISTS "
    "FOR (s:Cause) REQUIRE s.id IS UNIQUE",
]

# --- Ładowanie danych (UNWIND + MERGE, parametryzowane) --------------------

LOAD_CELEBRITIES = """
UNWIND $rows AS row
MERGE (c:Celebrity {id: row.id})
SET c.name = row.name,
    c.birth_year = row.birth_year,
    c.death_year = row.death_year
"""

LOAD_CAUSES = """
UNWIND $rows AS row
MERGE (s:Cause {id: row.id})
SET s.name = row.name,
    s.category = row.category,
    s.is_drug = row.is_drug
"""

LOAD_DIED_FROM = """
UNWIND $rows AS row
MATCH (c:Celebrity {id: row.celebrity_id})
MATCH (s:Cause {id: row.cause_id})
MERGE (c)-[:DIED_FROM]->(s)
"""

# Typ relacji jest podstawiany z białej listy (SPOUSE/PARTNER/RELATIVE).
LOAD_SOCIAL_TEMPLATE = """
UNWIND $rows AS row
MATCH (a:Celebrity {{id: row.source_id}})
MATCH (b:Celebrity {{id: row.target_id}})
MERGE (a)-[:{rel_type}]->(b)
"""

# --- Zapytania aplikacji (API) ---------------------------------------------

GET_CELEBRITIES = """
MATCH (c:Celebrity)
RETURN c.id AS id, c.name AS name,
       c.birth_year AS birth_year, c.death_year AS death_year
ORDER BY c.name
"""

GET_CAUSES = """
MATCH (s:Cause)
RETURN s.id AS id, s.name AS name, s.category AS category, s.is_drug AS is_drug
ORDER BY s.name
"""

# Ranking najgroźniejszych substancji wg liczby zgonów (tylko is_drug = True,
# więc np. zawał serca czy utonięcie nie zaśmiecają rankingu).
DANGEROUS_SUBSTANCES = """
MATCH (s:Cause)<-[:DIED_FROM]-(c:Celebrity)
WHERE s.is_drug
RETURN s.id AS id, s.name AS name, s.category AS category,
       count(c) AS deaths
ORDER BY deaths DESC, name
"""

# Ego-sieć: węzły i relacje w promieniu {depth} od wybranego celebryty.
# {depth} jest walidowane (1 lub 2) zanim trafi do zapytania.
NETWORK_TEMPLATE = """
MATCH p = (c:Celebrity {{id: $id}})-[*1..{depth}]-(m)
UNWIND relationships(p) AS rel
WITH DISTINCT rel, startNode(rel) AS a, endNode(rel) AS b
RETURN a.id AS a_id, labels(a)[0] AS a_label, coalesce(a.name, a.id) AS a_name,
       b.id AS b_id, labels(b)[0] AS b_label, coalesce(b.name, b.id) AS b_name,
       type(rel) AS rel_type
"""

# Najkrótsza ścieżka między dwoma celebrytami (relacje w dowolnym kierunku).
SHORTEST_PATH = """
MATCH (a:Celebrity {id: $from_id}), (b:Celebrity {id: $to_id})
MATCH p = shortestPath((a)-[*..10]-(b))
RETURN [n IN nodes(p) |
          {id: n.id, label: labels(n)[0], name: coalesce(n.name, n.id)}] AS nodes,
       [r IN relationships(p) | type(r)] AS rels
"""

# Pełny graf (wszystkie relacje) – do wizualizacji startowej.
FULL_GRAPH = """
MATCH (a)-[r]->(b)
RETURN a.id AS a_id, labels(a)[0] AS a_label, coalesce(a.name, a.id) AS a_name,
       b.id AS b_id, labels(b)[0] AS b_label, coalesce(b.name, b.id) AS b_name,
       type(r) AS rel_type
"""

# Proste statystyki grafu (liczność węzłów i relacji).
STATS = """
MATCH (c:Celebrity) WITH count(c) AS celebrities
MATCH (s:Cause) WITH celebrities, count(s) AS causes
MATCH ()-[r]->() RETURN celebrities, causes, count(r) AS relationships
"""
