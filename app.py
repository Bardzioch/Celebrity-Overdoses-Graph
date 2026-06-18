"""Aplikacja Flask – REST API + prosty frontend dla grafu Celebrity-Drug Network.

Uruchomienie:
    python app.py
Następnie otwórz http://localhost:5000 w przeglądarce.
"""
from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from db import Neo4jConnection
from services import CelebrityService

app = Flask(__name__)

# Jedno połączenie z bazą na proces aplikacji (sterownik ma własną pulę).
_conn = Neo4jConnection()
service = CelebrityService(_conn)


@app.route("/")
def index():
    """Strona główna (SPA z wizualizacją grafu)."""
    return render_template("index.html")


@app.route("/api/celebrities")
def api_celebrities():
    """Lista wszystkich celebrytów."""
    return jsonify(service.get_celebrities())


@app.route("/api/causes")
def api_causes():
    """Lista wszystkich przyczyn śmierci (z flagą is_drug)."""
    return jsonify(service.get_causes())


@app.route("/api/dangerous")
def api_dangerous():
    """Ranking substancji wg liczby zgonów (relacja DIED_FROM)."""
    return jsonify(service.dangerous_substances())


@app.route("/api/network/<path:celebrity_id>")
def api_network(celebrity_id: str):
    """Ego-sieć wokół celebryty. Parametr zapytania: ?depth=1|2."""
    depth = request.args.get("depth", default=1, type=int)
    return jsonify(service.ego_network(celebrity_id, depth))


@app.route("/api/path")
def api_path():
    """Najkrótsza ścieżka między dwoma celebrytami: ?from=<id>&to=<id>."""
    from_id = request.args.get("from")
    to_id = request.args.get("to")
    if not from_id or not to_id:
        return jsonify({"error": "Wymagane parametry: from, to"}), 400
    return jsonify(service.find_path(from_id, to_id))


@app.route("/api/graph")
def api_graph():
    """Pełny graf (do wizualizacji startowej)."""
    return jsonify(service.full_graph())


@app.route("/api/stats")
def api_stats():
    """Podstawowe statystyki grafu."""
    return jsonify(service.stats())


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
