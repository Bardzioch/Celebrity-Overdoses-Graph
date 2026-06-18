/* Frontend logiki SPA: pobiera dane z REST API i rysuje graf (vis-network). */

const COLORS = {
  Celebrity: { background: "#ff5470", border: "#c0314c" },
  Cause: { background: "#4ea8de", border: "#2f73a0" },
};

let network = null;
const netContainer = document.getElementById("network");

/** Pomocniczo: GET JSON z obsługą błędów. */
async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Rysuje graf {nodes, edges} w kontenerze vis-network. */
function drawGraph(data) {
  if (!data.nodes || data.nodes.length === 0) {
    netContainer.innerHTML =
      '<p class="muted" style="padding:1rem">Brak danych do wyświetlenia.</p>';
    return;
  }
  const nodes = data.nodes.map((n) => ({
    id: n.id,
    label: n.label,
    color: COLORS[n.group] || COLORS.Celebrity,
    shape: n.group === "Cause" ? "diamond" : "dot",
    size: n.group === "Cause" ? 18 : 14,
  }));
  const edges = data.edges.map((e) => ({
    from: e.from,
    to: e.to,
    label: e.label,
    arrows: e.type === "DIED_FROM" ? "to" : undefined,
    color: { color: "#5a6080", highlight: "#ff5470" },
    font: { color: "#9aa0b5", size: 10, strokeWidth: 0 },
  }));

  const visData = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
  const options = {
    nodes: { font: { color: "#e8e9f0", size: 13 }, borderWidth: 2 },
    edges: { smooth: { type: "dynamic" } },
    physics: { stabilization: true, barnesHut: { gravitationalConstant: -8000 } },
    interaction: { hover: true, tooltipDelay: 120 },
  };
  network = new vis.Network(netContainer, visData, options);
}

/** Wypełnia dwa selecty ścieżki listą celebrytów. */
function fillSelectors(celebrities) {
  const optionsHtml = celebrities
    .map((c) => `<option value="${c.id}">${c.name}</option>`) // id = QID
    .join("");
  ["path-from", "path-to"].forEach((id) => {
    document.getElementById(id).innerHTML = optionsHtml;
  });
  // Domyślnie ustaw różne osoby w polach ścieżki, jeśli to możliwe.
  const toSel = document.getElementById("path-to");
  if (celebrities.length > 1) toSel.selectedIndex = 1;
}

/** Renderuje statystyki grafu w nagłówku. */
function renderStats(stats) {
  const el = document.getElementById("stats");
  el.innerHTML =
    `<span>👤 Celebryci: ${stats.celebrities ?? "?"}</span>` +
    `<span>💀 Przyczyny śmierci: ${stats.causes ?? "?"}</span>` +
    `<span>🔗 Relacje: ${stats.relationships ?? "?"}</span>`;
}

/* --- Obsługa przycisków --- */

document.getElementById("btn-path").addEventListener("click", async () => {
  const from = document.getElementById("path-from").value;
  const to = document.getElementById("path-to").value;
  const box = document.getElementById("path-result");
  if (from === to) {
    box.innerHTML = '<p class="muted">Wybierz dwie różne osoby.</p>';
    return;
  }
  box.innerHTML = "Szukam…";
  try {
    const res = await getJSON(`/api/path?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
    if (!res.found) {
      box.innerHTML = '<p class="muted">Nie znaleziono ścieżki między tymi osobami.</p>';
      drawGraph({ nodes: [], edges: [] });
      return;
    }
    const items = res.steps
      .map((s) => `<li>${s.from} <span class="rel">— ${s.label} →</span> ${s.to}</li>`)
      .join("");
    box.innerHTML = `<p>Długość ścieżki: <b>${res.length}</b></p><ul class="steps">${items}</ul>`;
    drawGraph(res);
  } catch (e) {
    box.innerHTML = `<p class="muted">Błąd: ${e.message}</p>`;
  }
});

document.getElementById("btn-dangerous").addEventListener("click", async () => {
  const box = document.getElementById("dangerous-result");
  box.innerHTML = "Ładuję…";
  const rows = await getJSON("/api/dangerous");
  if (!rows.length) {
    box.innerHTML = '<p class="muted">Brak danych.</p>';
    return;
  }
  const trs = rows
    .map(
      (r, i) =>
        `<tr><td>${i + 1}</td><td>${r.name}</td><td>${r.category}</td><td>${r.deaths}</td></tr>`
    )
    .join("");
  box.innerHTML =
    `<table><thead><tr><th>#</th><th>Substancja</th><th>Kategoria</th><th>Zgony</th></tr></thead>` +
    `<tbody>${trs}</tbody></table>`;
});

document.getElementById("btn-full").addEventListener("click", async () => {
  const data = await getJSON("/api/graph");
  drawGraph(data);
});

/* --- Inicjalizacja --- */
(async function init() {
  try {
    const [celebrities, stats, graph] = await Promise.all([
      getJSON("/api/celebrities"),
      getJSON("/api/stats"),
      getJSON("/api/graph"),
    ]);
    fillSelectors(celebrities);
    renderStats(stats);
    drawGraph(graph);
  } catch (e) {
    netContainer.innerHTML =
      `<p class="muted" style="padding:1rem">Nie udało się połączyć z API: ${e.message}.<br>` +
      `Czy baza Neo4j jest uruchomiona i dane załadowane?</p>`;
  }
})();
