"""Ładowanie danych z plików CSV (katalog data/) do bazy Neo4j.

Skrypt:
  1. (opcjonalnie) czyści bazę (`--reset`),
  2. tworzy ograniczenia unikalności,
  3. ładuje węzły Celebrity i Cause,
  4. tworzy relacje DIED_FROM oraz relacje społeczne (SPOUSE/PARTNER/RELATIVE).

Dane wczytywane są w Pythonie i wstawiane parametrycznie (UNWIND + MERGE), dzięki
czemu nie trzeba montować katalogu importu Neo4j w kontenerze Docker.
"""
from __future__ import annotations

import csv
import os
import sys

import db
import queries

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ALLOWED_REL_TYPES = {"SPOUSE", "PARTNER", "RELATIVE"}


def read_csv(filename: str) -> list[dict]:
    """Wczytuje plik CSV z katalogu data/ jako listę słowników."""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        print(f"   ! brak pliku {path} – pomijam", file=sys.stderr)
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def to_int(value: str):
    """Zamienia napis na int lub None (puste/niepoprawne -> None)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def main():
    reset = "--reset" in sys.argv

    celebrities = read_csv("celebrities.csv")
    causes = read_csv("causes.csv")
    died_from = read_csv("died_from.csv")
    social = read_csv("social.csv")

    # Normalizacja typów liczbowych dla lat.
    for row in celebrities:
        row["birth_year"] = to_int(row.get("birth_year"))
        row["death_year"] = to_int(row.get("death_year"))

    # Flaga is_drug zapisana w CSV jako napis "True"/"False" -> bool.
    for row in causes:
        row["is_drug"] = str(row.get("is_drug")).strip().lower() == "true"

    conn = db.get_connection()
    try:
        conn.verify()
    except Exception as exc:  # noqa: BLE001
        print(f"BŁĄD: nie można połączyć się z Neo4j ({exc}).", file=sys.stderr)
        print("Czy kontener Docker z Neo4j jest uruchomiony? Zob. README.",
              file=sys.stderr)
        sys.exit(1)

    try:
        if reset:
            print("== Czyszczenie bazy (--reset) ==")
            conn.query("MATCH (n) DETACH DELETE n")

        print("== Tworzenie ograniczeń ==")
        for ddl in queries.CONSTRAINTS:
            conn.query(ddl)

        print("== Ładowanie węzłów ==")
        conn.query(queries.LOAD_CELEBRITIES, rows=celebrities)
        print(f"   Celebrity:  {len(celebrities)}")
        conn.query(queries.LOAD_CAUSES, rows=causes)
        print(f"   Cause:      {len(causes)}")

        print("== Ładowanie relacji ==")
        conn.query(queries.LOAD_DIED_FROM, rows=died_from)
        print(f"   DIED_FROM:  {len(died_from)}")

        # Relacje społeczne – grupowane wg typu (typ z białej listy).
        by_type: dict[str, list[dict]] = {}
        for row in social:
            rel = row.get("type", "")
            if rel in ALLOWED_REL_TYPES:
                by_type.setdefault(rel, []).append(row)
        for rel_type, rows in by_type.items():
            cypher = queries.LOAD_SOCIAL_TEMPLATE.format(rel_type=rel_type)
            conn.query(cypher, rows=rows)
            print(f"   {rel_type}:  {len(rows)}")

        print("== Statystyki ==")
        stats = conn.query(queries.STATS)
        if stats:
            print(f"   {stats[0]}")
        print("Gotowe.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
