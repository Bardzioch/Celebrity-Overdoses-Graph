"""Pobieranie danych o celebrytach i substancjach z Wikidata do plików CSV.

Skrypt buduje zbiór danych dla grafu "Celebrity-Drug Network":
  * węzły Celebrity  -> data/celebrities.csv
  * węzły Cause      -> data/causes.csv       (przyczyny śmierci; flaga is_drug)
  * relacje DIED_FROM -> data/died_from.csv
  * relacje społeczne -> data/social.csv      (SPOUSE / PARTNER / RELATIVE)

Dane pochodzą wyłącznie z Wikidata. Wykorzystywane są dwa, niezależne punkty
dostępu Wikidaty:

1. **Wikidata Query Service (WDQS, SPARQL)** – służy do *odkrycia* listy osób,
   które zmarły wskutek przedawkowania (`wdt:P509 wd:Q3505294`).  W momencie
   pisania projektu WDQS był objęty agresywnym limitem (1 zapytanie /
   min, HTTP 429), dlatego funkcja `discover_via_sparql()` jest "best-effort".

2. **MediaWiki API** (`https://www.wikidata.org/w/api.php`) – stabilny, nielimitowany
   punkt dostępu używany do *wzbogacenia* każdej osoby (rok urodzenia/śmierci,
   przyczyna śmierci, relacje społeczne).  Gdy WDQS nie odpowiada, lista osób jest
   pobierana po nazwach z wbudowanej listy `SEED_NAMES` (rozwiązywanej do QID przez
   `wbsearchentities`), a wszystkie *fakty* i tak pochodzą automatycznie z Wikidata.

Użycie:
    python extract_data.py            # odkrycie (SPARQL) -> wzbogacenie (API)
    python extract_data.py --seed     # pomiń SPARQL, użyj listy startowej + API
    python extract_data.py --offline  # nic nie pobieraj (zostaw istniejące CSV)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# --- Konfiguracja ----------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
USER_AGENT = (
    "CelebDrugNetwork/1.0 (educational university project; ochmanwojtek@gmail.com)"
)
WDQS_ENDPOINT = "https://query.wikidata.org/sparql"
API_ENDPOINT = "https://www.wikidata.org/w/api.php"

DRUG_OVERDOSE_QID = "Q3505252"  # "drug overdose" – przyczyna śmierci (P509)
HUMAN_QID = "Q5"                # "człowiek" (P31) – do weryfikacji encji
TARGET_COUNT = 30               # ile osób chcemy w grafie (rdzeń sieci)

# Właściwości Wikidata używane do relacji społecznych (osoba -> osoba).
SOCIAL_PROPERTIES = {
    "P26": "SPOUSE",     # małżonek/małżonka
    "P451": "PARTNER",   # partner (związek nieformalny)
    "P3373": "RELATIVE", # rodzeństwo
    "P40": "RELATIVE",   # dziecko
    "P22": "RELATIVE",   # ojciec
    "P25": "RELATIVE",   # matka
}

# Lista startowa – znani artyści, których śmierć wiązała się z substancjami.
# Używana tylko do *odkrycia* QID (gdy WDQS nie działa); wszystkie dane o tych
# osobach i tak są pobierane automatycznie z Wikidata przez MediaWiki API.
SEED_NAMES = [
    "Amy Winehouse", "Whitney Houston", "Michael Jackson",
    "Mac Miller", "Tom Petty", "Heath Ledger", "Janis Joplin", "Jimi Hendrix",
    "Jim Morrison", "Elvis Presley", "Philip Seymour Hoffman", "River Phoenix",
    "Chris Farley", "John Belushi", "Cory Monteith", "Anna Nicole Smith",
    "Brittany Murphy", "Dee Dee Ramone", "Sid Vicious", "Lil Peep", "Juice Wrld",
    "Scott Weiland", "Layne Staley", "Judy Garland", "Marilyn Monroe",
    "Bobbi Kristina Brown", "Keith Moon", "Gram Parsons", "Frankie Lymon",
    "Pimp C", "Nick Drake", "Prince Rogers Nelson",
]

# Mapowanie etykiety przyczyny/substancji na czytelną kategorię (po polsku).
# Dopasowanie po fragmencie nazwy => odporne i w pełni automatyczne.
CATEGORY_RULES = [
    (("alcohol", "ethanol"), "alkohol"),
    (("heroin", "opioid", "fentanyl", "oxycodone", "oxycontin", "methadone",
      "morphine", "codeine", "hydrocodone", "tramadol"), "opioid"),
    (("cocaine", "amphetamine", "methamphetamine", "mdma", "ecstasy",
      "stimulant"), "stymulant"),
    (("barbiturate", "benzodiazepine", "diazepam", "secobarbital",
      "phenobarbital", "depressant"), "depresant"),
    (("propofol", "anaesthetic", "anesthetic", "ketamine"), "anestetyk"),
    (("overdose", "intoxication", "poisoning", "toxicity"), "przedawkowanie (ogólne)"),
]

# Kategorie uznawane za „narkotykowe" (substancje) – używane do flagi is_drug
# oraz do rankingu najgroźniejszych substancji.
DRUG_CATEGORIES = {"alkohol", "opioid", "stymulant", "depresant", "anestetyk",
                   "przedawkowanie (ogólne)"}


# --- Pomocnicze HTTP -------------------------------------------------------

def http_get_json(url: str, retries: int = 4, pace: float = 0.0) -> dict:
    """Pobiera JSON z podanego URL z ponawianiem przy 429/5xx (backoff)."""
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
            if pace:
                time.sleep(pace)
            return data
        except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
            last_err = exc
            if exc.code in (429, 500, 502, 503, 504):
                wait = min(65, 5 * (attempt + 1) ** 2)
                print(f"   ! HTTP {exc.code}, ponawiam za {wait}s "
                      f"(próba {attempt + 1}/{retries})", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except Exception as exc:  # noqa: BLE001 - sieć bywa zawodna
            last_err = exc
            time.sleep(3)
    raise RuntimeError(f"Nie udało się pobrać {url}: {last_err}")


def api_get(params: dict) -> dict:
    """Wywołuje MediaWiki API Wikidaty z podanymi parametrami."""
    params = {**params, "format": "json"}
    url = API_ENDPOINT + "?" + urllib.parse.urlencode(params)
    return http_get_json(url)


# --- Odkrywanie listy osób -------------------------------------------------

def discover_via_sparql(limit: int = TARGET_COUNT) -> list[str]:
    """Zwraca QID-y osób zmarłych wskutek przedawkowania (najbardziej znane).

    Sortowanie po liczbie wersji językowych Wikipedii (miara rozpoznawalności).
    Zwraca [] jeśli WDQS nie odpowiada (awaria / limit) – wywołujący użyje listy
    startowej.
    """
    query = f"""
SELECT ?p (COUNT(DISTINCT ?site) AS ?sites) WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P509 wd:{DRUG_OVERDOSE_QID} .
  OPTIONAL {{ ?site schema:about ?p ; schema:isPartOf/wikibase:wikiGroup "wikipedia" . }}
}}
GROUP BY ?p
ORDER BY DESC(?sites)
LIMIT {limit}
"""
    url = WDQS_ENDPOINT + "?" + urllib.parse.urlencode(
        {"query": query, "format": "json"})
    try:
        data = http_get_json(url, retries=2)
    except Exception as exc:  # noqa: BLE001
        print(f"   ! WDQS niedostępny ({exc}). Używam listy startowej.",
              file=sys.stderr)
        return []
    qids = []
    for row in data["results"]["bindings"]:
        uri = row["p"]["value"]            # http://www.wikidata.org/entity/Q...
        qids.append(uri.rsplit("/", 1)[-1])
    return qids


def resolve_seed_names(names: list[str]) -> tuple[list[str], dict[str, str]]:
    """Zamienia nazwy z listy startowej na QID (wybiera pierwszego *człowieka*).

    Dla każdej nazwy pobiera do 5 kandydatów (wbsearchentities), a następnie
    wybiera pierwszego, który jest instancją człowieka (P31 = Q5) – dzięki temu
    np. „Frankie Lymon” trafia na osobę, a nie na zespół. Zwraca też mapę
    QID -> etykieta z wyszukiwarki (zapasowa nazwa, gdy encja nie ma etykiety EN).
    """
    candidates: dict[str, list[tuple[str, str]]] = {}
    all_qids: list[str] = []
    for name in names:
        try:
            data = api_get({"action": "wbsearchentities", "search": name,
                            "language": "en", "limit": 5})
            hits = [(h["id"], h.get("label", name)) for h in data.get("search", [])]
        except Exception as exc:  # noqa: BLE001
            print(f"   - błąd dla '{name}': {exc}", file=sys.stderr)
            hits = []
        candidates[name] = hits
        all_qids += [q for q, _ in hits]

    ents = fetch_entities(list(dict.fromkeys(all_qids)))

    qids: list[str] = []
    name_hints: dict[str, str] = {}
    for name, hits in candidates.items():
        pick = None
        for qid, label in hits:
            claims = ents.get(qid, {}).get("claims", {})
            if HUMAN_QID in _claim_item_ids(claims, "P31"):
                pick = (qid, label)
                break
        if pick is None and hits:      # brak człowieka – weź pierwszy wynik
            pick = hits[0]
        if pick:
            qids.append(pick[0])
            name_hints[pick[0]] = pick[1]
            print(f"   + {name} -> {pick[0]}")
        else:
            print(f"   - brak wyniku dla '{name}'", file=sys.stderr)
    return qids, name_hints


# --- Wzbogacanie danych ----------------------------------------------------

def _claim_item_ids(claims: dict, pid: str) -> list[str]:
    """Zwraca listę QID-ów z claimów o właściwości `pid` (wartości typu item)."""
    out = []
    for c in claims.get(pid, []):
        try:
            dv = c["mainsnak"]["datavalue"]["value"]
            if isinstance(dv, dict) and dv.get("entity-type") == "item":
                out.append(dv["id"])
        except (KeyError, TypeError):
            continue
    return out


def _claim_year(claims: dict, pid: str):
    """Wyciąga rok (int) z pierwszego claimu typu time, np. P569/P570."""
    for c in claims.get(pid, []):
        try:
            t = c["mainsnak"]["datavalue"]["value"]["time"]  # '+1983-09-14T..'
            sign = -1 if t.startswith("-") else 1
            year = int(t.lstrip("+-").split("-", 1)[0])
            return sign * year
        except (KeyError, TypeError, ValueError):
            continue
    return None


def fetch_entities(qids: list[str]) -> dict:
    """Pobiera encje (claims + etykiety EN) dla listy QID, partiami po 50."""
    entities: dict = {}
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        data = api_get({"action": "wbgetentities", "ids": "|".join(batch),
                        "props": "claims|labels", "languages": "en"})
        entities.update(data.get("entities", {}))
    return entities


def label_of(entities: dict, qid: str) -> str | None:
    """Zwraca angielską etykietę encji (lub None, jeśli brak)."""
    ent = entities.get(qid)
    if not ent or "labels" not in ent:
        return None
    return ent["labels"].get("en", {}).get("value")


def categorize(label: str) -> str:
    """Przypisuje kategorię przyczyny śmierci na podstawie jej nazwy."""
    low = label.lower()
    for needles, category in CATEGORY_RULES:
        if any(n in low for n in needles):
            return category
    return "inna przyczyna"


def is_drug(label: str) -> bool:
    """Czy dana przyczyna śmierci jest związana z substancją/przedawkowaniem.

    Nie odfiltrowuje przyczyn (wszystkie są węzłami :Cause), lecz oznacza, które
    z nich liczą się do rankingu „najgroźniejszych substancji" (np. zawał czy
    utonięcie -> False, heroina/przedawkowanie -> True).
    """
    return categorize(label) in DRUG_CATEGORIES


# --- Budowa zbioru danych --------------------------------------------------

def _is_human(entities: dict, qid: str) -> bool:
    """Czy encja jest instancją człowieka (P31 = Q5)."""
    claims = entities.get(qid, {}).get("claims", {})
    return HUMAN_QID in _claim_item_ids(claims, "P31")


def build_dataset(core_qids: list[str], name_hints: dict[str, str] | None = None):
    """Buduje wiersze CSV: rdzeń (ofiary przedawkowań) + 1 skok relacji.

    Sieć społeczna ofiar przedawkowań jest rzadka, dlatego rozszerzamy graf o
    sąsiadów połączonych przez małżeństwo (P26) lub związek (P451). Sąsiedzi
    stają się dodatkowymi węzłami :Celebrity (łącznikami), dzięki czemu powstają
    ciekawe ścieżki, np. Elvis Presley → córka Lisa Marie Presley → mąż Michael
    Jackson. Substancje (DIED_FROM) tworzymy tylko dla rdzenia.
    """
    name_hints = name_hints or {}
    core_entities = fetch_entities(core_qids)
    core_set = set(core_qids)

    # 1) Rozszerzenie o sąsiadów (małżonkowie / partnerzy osób z rdzenia).
    neighbor_qids: set[str] = set()
    for qid in core_qids:
        claims = core_entities.get(qid, {}).get("claims", {})
        for pid in ("P26", "P451"):
            for other in _claim_item_ids(claims, pid):
                if other not in core_set:
                    neighbor_qids.add(other)
    neighbor_entities = fetch_entities(sorted(neighbor_qids))
    people = {**neighbor_entities, **core_entities}

    # Pełny zbiór osób = rdzeń + sąsiedzi będący ludźmi.
    person_qids = list(core_qids) + [q for q in sorted(neighbor_qids)
                                     if _is_human(people, q) and q not in core_set]
    person_set = set(person_qids)

    # 2) Węzły Celebrity (z zapasową nazwą, gdy brak etykiety EN).
    celebrities = []
    for qid in person_qids:
        claims = people.get(qid, {}).get("claims", {})
        name = label_of(people, qid) or name_hints.get(qid) or qid
        celebrities.append({
            "id": qid,
            "name": name,
            "birth_year": _claim_year(claims, "P569") or "",
            "death_year": _claim_year(claims, "P570") or "",
        })

    # 3) Przyczyny śmierci (:Cause) + DIED_FROM (tylko rdzeń, WSZYSTKIE przyczyny).
    # Każda przyczyna otrzymuje flagę is_drug (czy to substancja narkotykowa) –
    # dzięki temu np. Michael Jackson (zawał) też łączy się z węzłem przyczyny,
    # a ranking „najgroźniejszych substancji" filtruje tylko is_drug = True.
    cause_qids: set[str] = set()
    raw_died: list[tuple[str, str]] = []
    for qid in core_qids:
        claims = core_entities.get(qid, {}).get("claims", {})
        for cause in _claim_item_ids(claims, "P509"):
            cause_qids.add(cause)
            raw_died.append((qid, cause))

    cause_entities = fetch_entities(sorted(cause_qids))
    causes = []
    for cqid in sorted(cause_qids):
        label = label_of(cause_entities, cqid) or cqid
        causes.append({"id": cqid, "name": label,
                       "category": categorize(label),
                       "is_drug": is_drug(label)})
    died_from = [{"celebrity_id": p, "cause_id": c} for p, c in raw_died]

    # 4) Relacje społeczne wśród całego zbioru osób (deduplikacja par).
    seen = set()
    social = []
    for qid in person_qids:
        claims = people.get(qid, {}).get("claims", {})
        for pid, rel_type in SOCIAL_PROPERTIES.items():
            for other in _claim_item_ids(claims, pid):
                if other in person_set and other != qid:
                    key = (rel_type, *sorted((qid, other)))
                    if key in seen:
                        continue
                    seen.add(key)
                    social.append({"source_id": qid, "target_id": other,
                                   "type": rel_type})

    return celebrities, causes, died_from, social


# --- Zapis CSV -------------------------------------------------------------

def write_csv(filename: str, rows: list[dict], fieldnames: list[str]):
    """Zapisuje listę słowników do pliku CSV w katalogu data/."""
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"   zapisano {len(rows):>3} wierszy -> data/{filename}")


def main():
    parser = argparse.ArgumentParser(description="Ekstrakcja danych z Wikidata.")
    parser.add_argument("--discover", action="store_true",
                        help="użyj SPARQL (WDQS) do automatycznego odkrycia listy "
                             "osób; bez tej flagi używana jest lista startowa, "
                             "która daje bogatszy i stabilniejszy zbiór danych")
    parser.add_argument("--offline", action="store_true",
                        help="nie pobieraj nic z sieci (zostaw istniejące CSV)")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)

    if args.offline:
        print("Tryb offline – pozostawiam istniejące pliki CSV bez zmian.")
        return

    print("== Krok 1/3: odkrywanie listy osób (rdzeń) ==")
    qids: list[str] = []
    name_hints: dict[str, str] = {}
    if args.discover:
        print("   Tryb --discover: odpytuję WDQS (SPARQL).")
        qids = discover_via_sparql()
    if not qids:
        print("   Używam wbudowanej listy startowej (resolve przez API).")
        qids, name_hints = resolve_seed_names(SEED_NAMES)
    # Usuń duplikaty zachowując kolejność.
    qids = list(dict.fromkeys(qids))
    print(f"   liczba osób w rdzeniu: {len(qids)}")

    print("== Krok 2/3: wzbogacanie + rozszerzenie o sąsiadów (MediaWiki API) ==")
    celebrities, causes, died_from, social = build_dataset(qids, name_hints)
    print(f"   węzłów Celebrity (z sąsiadami): {len(celebrities)}")

    print("== Krok 3/3: zapis plików CSV ==")
    write_csv("celebrities.csv", celebrities,
              ["id", "name", "birth_year", "death_year"])
    write_csv("causes.csv", causes, ["id", "name", "category", "is_drug"])
    write_csv("died_from.csv", died_from, ["celebrity_id", "cause_id"])
    write_csv("social.csv", social, ["source_id", "target_id", "type"])
    print("Gotowe.")


if __name__ == "__main__":
    main()
