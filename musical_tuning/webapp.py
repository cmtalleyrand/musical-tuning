from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
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
    return Path(__file__).resolve().parent.parent.joinpath("web/index.html").read_text(encoding="utf-8")


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
        raw_weights = data.get("weights", {})
        weights = {
            "root_third_fifth": float(raw_weights.get("root_third_fifth", 1.5)),
            "bass_to_any": float(raw_weights.get("bass_to_any", 1.5)),
            "root_to_dissonance": float(raw_weights.get("root_to_dissonance", 0.5)),
            "compound_interval": float(raw_weights.get("compound_interval", 0.75)),
        }
        ranked, invalid = self.optimizer.optimize_from_lines(lines, weights=weights)
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
