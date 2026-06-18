# 🕸️ Celebrity–Drug Network

Projekt zaliczeniowy z **baz danych grafowych** (Neo4j). Aplikacja buduje graf
celebrytów, substancji (przyczyn śmierci związanych z używkami) oraz ich relacji
społecznych. **Wszystkie dane pochodzą automatycznie z Wikidata.**

Funkcjonalności:
- 📋 lista celebrytów i substancji,
- ☠️ ranking „najgroźniejszych” substancji (wg liczby zgonów),
- 🧍 ego-sieć wokół wybranej osoby (promień 1 lub 2),
- 🔗 najkrótsza ścieżka między dwoma celebrytami (np. *Elvis Presley → Lisa Marie
  Presley → Michael Jackson*),
- 🌐 wizualizacja całego grafu (biblioteka `vis-network`).

---

## 1. Wymagania wstępne

| Narzędzie | Wersja | Uwagi |
|-----------|--------|-------|
| Python    | 3.10+  | testowane na 3.14 |
| Docker    | dowolna aktualna | **Docker Desktop musi być uruchomiony** |
| Przeglądarka | dowolna | do otwarcia frontendu |

> ℹ️ Nie jest wymagane konto ani klucz API Wikidata — używany jest publiczny
> punkt dostępu.

---

## 2. Uruchomienie krok po kroku

### 2.1. Baza Neo4j (Docker)
Uruchom Docker Desktop, a następnie:

```bash
docker run -d --name neo4j-celeb \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password123 \
  neo4j:5
```

- Bolt (sterownik): `bolt://localhost:7687`
- Neo4j Browser (GUI): http://localhost:7474 (login `neo4j` / `password123`)

### 2.2. Środowisko Pythona

```bash
python -m venv .venv
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

### 2.3. Dane (Wikidata → CSV)
Pliki CSV są **dołączone do repozytorium** (`data/`), więc ten krok można
pominąć. Aby pobrać dane na nowo:

```bash
python extract_data.py            # lista startowa + MediaWiki API (domyślnie)
python extract_data.py --discover # alternatywnie: automatyczne odkrycie przez SPARQL
```

### 2.4. Załadowanie danych do Neo4j

```bash
python load_data.py --reset       # --reset czyści bazę przed importem
```

### 2.5. Uruchomienie aplikacji

```bash
python app.py
```

Otwórz **http://localhost:5000**.

---

## 3. Struktura projektu

```
bazy_projekt2/
├── app.py            # Flask: trasy REST + serwowanie frontendu
├── services.py       # CelebrityService – logika (Cypher -> JSON dla frontendu)
├── db.py             # Neo4jConnection – adapter sterownika Neo4j
├── queries.py        # wszystkie zapytania Cypher (stałe)
├── extract_data.py   # pobieranie danych z Wikidata do CSV
├── load_data.py      # import CSV -> Neo4j (constraints + UNWIND/MERGE)
├── data/             # wygenerowane pliki CSV (wersjonowane)
├── templates/index.html
├── static/{style.css, app.js}
├── requirements.txt
├── .env.example
├── README.md
└── docs/             # dokumentacja + diagramy UML (Mermaid)
```

---

## 4. REST API

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| GET | `/api/celebrities` | lista celebrytów |
| GET | `/api/causes` | lista przyczyn śmierci (z flagą `is_drug`) |
| GET | `/api/dangerous` | ranking substancji (tylko `is_drug`) wg liczby zgonów |
| GET | `/api/network/<id>?depth=1\|2` | ego-sieć wokół celebryty |
| GET | `/api/path?from=<id>&to=<id>` | najkrótsza ścieżka |
| GET | `/api/graph` | cały graf (wizualizacja) |
| GET | `/api/stats` | statystyki grafu |

`<id>` to identyfikator Wikidata, np. `Q303` (Elvis Presley).

Szczegóły modelu grafu, zapytań Cypher i diagramów UML znajdują się w
[`docs/dokumentacja.md`](docs/dokumentacja.md).

---

## 5. Najczęstsze problemy

- **`Nie można połączyć się z Neo4j`** – sprawdź, czy kontener działa
  (`docker ps`) i czy hasło w `.env` zgadza się z `NEO4J_AUTH`.
- **`extract_data.py` zwraca błędy 429/timeout** – publiczny serwis SPARQL bywa
  przeciążony; tryb domyślny (lista startowa) korzysta ze stabilnego MediaWiki API.
- **Pusta wizualizacja** – upewnij się, że wykonano `python load_data.py`.
