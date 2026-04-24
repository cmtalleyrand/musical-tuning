from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .optimizer import MusicalTuningOptimizer


@dataclass(frozen=True)
class OptimizationStats:
    input_lines: int
    valid_chords: int
    invalid_lines: int
    candidate_count: int
    best_family: str
    best_center: str
    best_final_score_cents: float
    mean_final_score_cents: float


def build_statistics(ranked: list[dict[str, Any]], invalid: list[str], input_lines: int) -> OptimizationStats:
    candidate_count = len(ranked)
    valid_chords = max(input_lines - len(invalid), 0)

    if ranked:
        best = ranked[0]
        mean_score = sum(float(record["final_score_cents"]) for record in ranked) / candidate_count
        return OptimizationStats(
            input_lines=input_lines,
            valid_chords=valid_chords,
            invalid_lines=len(invalid),
            candidate_count=candidate_count,
            best_family=str(best["family"]),
            best_center=str(best["center"]),
            best_final_score_cents=float(best["final_score_cents"]),
            mean_final_score_cents=mean_score,
        )

    return OptimizationStats(
        input_lines=input_lines,
        valid_chords=valid_chords,
        invalid_lines=len(invalid),
        candidate_count=0,
        best_family="-",
        best_center="-",
        best_final_score_cents=0.0,
        mean_final_score_cents=0.0,
    )


def _html() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Musical Tuning Optimizer</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0f1220;
      --card: #161b2e;
      --card-2: #1d2340;
      --text: #e8ebff;
      --muted: #b5bfdc;
      --accent: #6ea8fe;
      --ok: #62d6a6;
      --warn: #ffcc66;
    }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      background: radial-gradient(circle at 20% 0%, #1f2a4a 0%, var(--bg) 45%);
      color: var(--text);
    }
    .container { max-width: 1100px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 6px; font-size: 2rem; }
    .subtitle { margin: 0 0 24px; color: var(--muted); }
    .grid { display: grid; gap: 16px; }
    .layout { grid-template-columns: 1.2fr 1fr; }
    .card { background: linear-gradient(160deg, var(--card), var(--card-2)); border: 1px solid #2f3a66; border-radius: 14px; padding: 16px; box-shadow: 0 8px 24px rgba(0,0,0,.28); }
    textarea { width: 100%; min-height: 220px; background: #0f1530; border: 1px solid #384575; border-radius: 10px; color: var(--text); padding: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    button { background: linear-gradient(120deg, #4a78f5, var(--accent)); border: none; color: #081023; font-weight: 700; border-radius: 10px; padding: 10px 16px; cursor: pointer; }
    .stats { grid-template-columns: repeat(4, minmax(120px, 1fr)); }
    .stat { background: #0e1430; border: 1px solid #334170; border-radius: 10px; padding: 12px; }
    .label { color: var(--muted); font-size: .8rem; }
    .value { font-size: 1.2rem; font-weight: 700; margin-top: 6px; }
    table { width: 100%; border-collapse: collapse; font-size: .92rem; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid #2d365f; }
    th { color: var(--muted); font-weight: 600; }
    .pill { display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: .8rem; }
    .ok { background: rgba(98,214,166,.16); color: var(--ok); }
    .warn { background: rgba(255,204,102,.18); color: var(--warn); }
    @media (max-width: 960px) { .layout { grid-template-columns: 1fr; } .stats { grid-template-columns: repeat(2, minmax(120px, 1fr)); } }
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>Musical Tuning Optimizer</h1>
    <p class=\"subtitle\">Evaluate 29 historical families × 12 tonal centers and inspect ranking diagnostics.</p>

    <div class=\"grid layout\">
      <section class=\"card\">
        <h2>Chord inventory input</h2>
        <p class=\"subtitle\">Use one line per chord. Supported examples: <code>Am7,24,1.0</code>, <code>24x D/F# @0.8</code>.</p>
        <textarea id=\"input\">Am7,24,1.0\nD/F#,12,0.7\nGsus4add9,9,0.8</textarea>
        <div style=\"margin-top:12px; display:flex; gap:10px; align-items:center;\">
          <button id=\"run\">Optimize</button>
          <span id=\"status\" class=\"pill ok\">Ready</span>
        </div>
      </section>

      <section class=\"card\">
        <h2>Informative statistics</h2>
        <div class=\"grid stats\" id=\"stats\"></div>
        <h3 style=\"margin-top: 16px;\">Top contributors (best candidate)</h3>
        <div id=\"contributors\" class=\"subtitle\">Run optimization to view interval and chord contributors.</div>
      </section>
    </div>

    <section class=\"card\" style=\"margin-top:16px;\">
      <h2>Top ranked temperaments</h2>
      <table>
        <thead><tr><th>#</th><th>Family</th><th>Center</th><th>WMAE</th><th>WRMSE</th><th>Final</th></tr></thead>
        <tbody id=\"rows\"></tbody>
      </table>
      <p id=\"invalid\" class=\"subtitle\"></p>
    </section>
  </div>
<script>
const run = document.getElementById('run');
const input = document.getElementById('input');
const statusEl = document.getElementById('status');

function renderStats(stats) {
  const items = [
    ['Input lines', stats.input_lines],
    ['Valid chords', stats.valid_chords],
    ['Invalid lines', stats.invalid_lines],
    ['Candidates', stats.candidate_count],
    ['Best family', stats.best_family],
    ['Best center', stats.best_center],
    ['Best final (cents)', stats.best_final_score_cents.toFixed(3)],
    ['Mean final (cents)', stats.mean_final_score_cents.toFixed(3)],
  ];
  document.getElementById('stats').innerHTML = items.map(([k,v]) => `<div class=\"stat\"><div class=\"label\">${k}</div><div class=\"value\">${v}</div></div>`).join('');
}

function renderTable(ranked) {
  document.getElementById('rows').innerHTML = ranked.slice(0, 12).map((r, idx) => `<tr><td>${idx + 1}</td><td>${r.family}</td><td>${r.center}</td><td>${Number(r.wmae_cents).toFixed(3)}</td><td>${Number(r.wrmse_cents).toFixed(3)}</td><td><strong>${Number(r.final_score_cents).toFixed(3)}</strong></td></tr>`).join('');
}

function renderContributors(best) {
  if (!best) {
    document.getElementById('contributors').textContent = 'No contributor data available.';
    return;
  }
  const chords = (best.top_chord_contributors || []).map(([name,val]) => `${name} (${Number(val).toFixed(3)})`).join(', ');
  const intervals = (best.top_interval_contributors || []).map(([name,val]) => `${name} (${Number(val).toFixed(3)})`).join(', ');
  document.getElementById('contributors').innerHTML = `<div><strong>Chord impact:</strong> ${chords || '-'}</div><div style=\"margin-top:8px;\"><strong>Interval impact:</strong> ${intervals || '-'}</div>`;
}

run.addEventListener('click', async () => {
  statusEl.textContent = 'Computing';
  statusEl.className = 'pill warn';
  const lines = input.value.split(/\r?\n/);
  const response = await fetch('/api/optimize', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ lines }) });
  const data = await response.json();
  renderStats(data.stats);
  renderTable(data.ranked);
  renderContributors(data.ranked[0]);
  const invalid = data.invalid.length ? `Invalid lines (${data.invalid.length}): ${data.invalid.join(' | ')}` : 'No invalid lines.';
  document.getElementById('invalid').textContent = invalid;
  statusEl.textContent = 'Done';
  statusEl.className = 'pill ok';
});
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    optimizer = MusicalTuningOptimizer()

    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        body = _html().encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/api/optimize":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(content_length)
        data = json.loads(payload.decode("utf-8"))
        lines = [str(line) for line in data.get("lines", [])]
        ranked, invalid = self.optimizer.optimize_from_lines(lines)
        stats = build_statistics(ranked, invalid, len(lines))

        response = {
            "ranked": ranked,
            "invalid": invalid,
            "stats": {
                "input_lines": stats.input_lines,
                "valid_chords": stats.valid_chords,
                "invalid_lines": stats.invalid_lines,
                "candidate_count": stats.candidate_count,
                "best_family": stats.best_family,
                "best_center": stats.best_center,
                "best_final_score_cents": stats.best_final_score_cents,
                "mean_final_score_cents": stats.mean_final_score_cents,
            },
        }

        body = json.dumps(response).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"Musical Tuning Optimizer running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
