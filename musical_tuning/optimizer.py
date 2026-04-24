from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Iterable


_NOTE_TO_PC = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "E#": 5,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
}

_BASE_DEGREE_TO_SEMITONE = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11, 8: 12, 9: 14, 10: 16, 11: 17, 12: 19, 13: 21}

_JI_BY_SEMITONE = {
    0: 0.0,
    1: 111.731,
    2: 203.910,
    3: 315.641,
    4: 386.314,
    5: 498.045,
    6: 582.512,
    7: 701.955,
    8: 813.686,
    9: 884.359,
    10: 1017.596,
    11: 1088.269,
}


@dataclass(frozen=True)
class ParsedChordInput:
    symbol: str
    frequency: int
    weight: float


@dataclass(frozen=True)
class CanonicalChord:
    symbol: str
    root_pc: int
    bass_pc: int
    factors: tuple[str, ...]
    factor_semitones: tuple[int, ...]
    frequency: int
    weight: float


@dataclass(frozen=True)
class IntervalPair:
    left_semitone: int
    right_semitone: int
    semitone_span: int
    weight: float
    target_adjust_cents: float
    root_dissonant: bool


@dataclass(frozen=True)
class RankedRecord:
    family: str
    center: str
    wmae_cents: float
    wrmse_cents: float
    final_score_cents: float
    top_chord_contributors: tuple[tuple[str, float], ...]
    top_interval_contributors: tuple[tuple[str, float], ...]


class InputAdapter:
    _csv_re = re.compile(r"^\s*([^,]+)\s*,\s*(\d+)(?:\s*,\s*([0-9]*\.?[0-9]+)?)?\s*$")
    _kv_re = re.compile(r"symbol\s*=\s*([^\s]+)\s+frequency\s*=\s*(\d+)(?:\s+weight\s*=\s*([0-9]*\.?[0-9]+))?")
    _x_re = re.compile(r"^\s*(\d+)x\s+([^@]+?)(?:\s*@\s*([0-9]*\.?[0-9]+))?\s*$")
    _md_separator_cell_re = re.compile(r"^:?-{3,}:?$")
    _generic_delimiter_re = re.compile(r"[,\t; ]+")

    def parse_lines(self, lines: Iterable[str]) -> tuple[list[ParsedChordInput], list[str]]:
        parsed: list[ParsedChordInput] = []
        invalid: list[str] = []
        table_layout: tuple[int, int, int | None] | None = None
        for line in lines:
            raw = line.strip()
            if not raw:
                table_layout = None
                continue
            if raw in {".", "…"}:
                continue

            header_layout = self._read_pipe_header_layout(raw)
            if header_layout is not None:
                table_layout = header_layout
                continue

            if self._is_pipe_separator_line(raw):
                continue

            if "|" not in raw:
                table_layout = None
            parsed_line = self._parse_line(raw, table_layout)
            if parsed_line is None:
                invalid.append(raw)
            else:
                parsed.append(parsed_line)
        return parsed, invalid

    def _parse_line(self, raw: str, table_layout: tuple[int, int, int | None] | None) -> ParsedChordInput | None:
        parsed_pipe = self._parse_pipe_row(raw, table_layout)
        if parsed_pipe is not None:
            return parsed_pipe

        for regex in (self._csv_re, self._kv_re):
            m = regex.search(raw)
            if m:
                weight_str = m.group(3)
                weight = 1.0 if weight_str is None or not weight_str.strip() else float(weight_str)
                return ParsedChordInput(symbol=m.group(1).strip(), frequency=int(m.group(2)), weight=weight)

        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                weight = 1.0 if "weight" not in data or data["weight"] in (None, "") else float(data["weight"])
                return ParsedChordInput(symbol=data["symbol"], frequency=int(data["frequency"]), weight=weight)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return None

        m = self._x_re.search(raw)
        if m:
            weight_str = m.group(3)
            weight = 1.0 if weight_str is None or not weight_str.strip() else float(weight_str)
            return ParsedChordInput(symbol=m.group(2).strip(), frequency=int(m.group(1)), weight=weight)

        generic = self._parse_generic_triplet(raw)
        if generic is not None:
            return generic
        return None

    def _parse_pipe_row(self, raw: str, table_layout: tuple[int, int, int | None] | None) -> ParsedChordInput | None:
        if "|" not in raw:
            return None

        cells = [cell.strip() for cell in raw.strip("|").split("|")]
        if len(cells) < 2 or all(cell == "" for cell in cells):
            return None

        layout = table_layout if table_layout is not None else (0, 1, 2 if len(cells) > 2 else None)
        symbol_idx, frequency_idx, weight_idx = layout
        try:
            symbol = cells[symbol_idx]
            frequency = int(cells[frequency_idx])
        except (ValueError, IndexError):
            return None

        weight_str = cells[weight_idx] if weight_idx is not None and weight_idx < len(cells) else ""
        try:
            weight = 1.0 if weight_str == "" else float(weight_str)
        except ValueError:
            return None
        return ParsedChordInput(symbol=symbol, frequency=frequency, weight=weight)

    def _read_pipe_header_layout(self, raw: str) -> tuple[int, int, int | None] | None:
        if "|" not in raw:
            return None

        cells = [cell.strip() for cell in raw.strip("|").split("|")]
        lowered = [cell.lower() for cell in cells]
        if "chord" not in lowered or "frequency" not in lowered:
            return None

        symbol_idx = lowered.index("chord")
        frequency_idx = lowered.index("frequency")
        weight_idx = lowered.index("weight") if "weight" in lowered else None
        return (symbol_idx, frequency_idx, weight_idx)

    def _is_pipe_separator_line(self, raw: str) -> bool:
        if "|" not in raw:
            return False

        cells = [cell.strip() for cell in raw.strip("|").split("|")]
        return all(self._md_separator_cell_re.match(cell) for cell in cells if cell)

    def _parse_generic_triplet(self, raw: str) -> ParsedChordInput | None:
        normalized = raw.strip()
        for left, right in (("[", "]"), ("(", ")"), ('"', '"'), ("'", "'")):
            normalized = normalized.replace(left, " ").replace(right, " ")

        parts = [p for p in self._generic_delimiter_re.split(normalized) if p]
        if len(parts) < 2 or len(parts) > 3:
            return None

        symbol = parts[0].strip()
        if not symbol:
            return None

        try:
            frequency = int(parts[1])
        except ValueError:
            return None

        weight_str = parts[2].strip() if len(parts) == 3 else ""
        try:
            weight = 1.0 if weight_str == "" else float(weight_str)
        except ValueError:
            return None
        return ParsedChordInput(symbol=symbol, frequency=frequency, weight=weight)


class ChordDecoder:
    _root_re = re.compile(r"^([A-G](?:#|b)?)(.*)$")

    def decode(self, chord: ParsedChordInput) -> CanonicalChord:
        m = self._root_re.match(chord.symbol)
        if not m:
            raise ValueError(f"Invalid chord symbol: {chord.symbol}")

        root_name, rest = m.group(1), m.group(2)
        root_pc = _NOTE_TO_PC[root_name]

        body, bass_name = (rest.split("/", 1) + [None])[:2] if "/" in rest else (rest, None)
        bass_pc = _NOTE_TO_PC[bass_name] if bass_name else root_pc

        factors = self._decode_factors(body)
        semitones = tuple(self._factor_to_semitone(factor) for factor in factors)
        return CanonicalChord(
            symbol=chord.symbol,
            root_pc=root_pc,
            bass_pc=bass_pc,
            factors=tuple(factors),
            factor_semitones=semitones,
            frequency=chord.frequency,
            weight=chord.weight,
        )

    def _decode_factors(self, body: str) -> list[str]:
        token = body.strip()
        lower = token.lower()

        triad: list[str]
        if "sus2" in lower:
            triad = ["1", "2", "5"]
        elif "sus4" in lower or lower.startswith("sus"):
            triad = ["1", "4", "5"]
        elif "dim" in lower or "o" in token:
            triad = ["1", "b3", "b5"]
        elif "aug" in lower or "+" in token:
            triad = ["1", "3", "#5"]
        elif lower.startswith("m") and not lower.startswith("maj"):
            triad = ["1", "b3", "5"]
        else:
            triad = ["1", "3", "5"]

        out = triad[:]

        if "maj7" in lower or "ma7" in lower:
            out.append("7")
        elif "7" in lower:
            out.append("b7")
        elif "6" in lower:
            out.append("6")

        for ext in ["b9", "#9", "9", "11", "#11", "b13", "13"]:
            if f"add{ext}" in lower or ext in lower:
                if ext not in [f.replace("add", "") for f in out] and ext not in out:
                    out.append(ext)

        dedup: list[str] = []
        for f in out:
            if f not in dedup:
                dedup.append(f)
        return dedup

    def _factor_to_semitone(self, factor: str) -> int:
        accidentals = 0
        idx = 0
        while idx < len(factor) and factor[idx] in "b#":
            accidentals += -1 if factor[idx] == "b" else 1
            idx += 1
        degree = int(factor[idx:])
        base = _BASE_DEGREE_TO_SEMITONE[degree]
        return base + accidentals


class IntervalBuilder:
    def build(self, chord: CanonicalChord, weight_engine: "WeightEngine") -> tuple[IntervalPair, ...]:
        ordered = sorted(enumerate(chord.factor_semitones), key=lambda x: x[1])
        factors = [chord.factors[i] for i, _ in ordered]
        semitones = [s for _, s in ordered]

        out: list[IntervalPair] = []
        for i in range(len(semitones)):
            for j in range(i + 1, len(semitones)):
                span = semitones[j] - semitones[i]
                out.append(
                    IntervalPair(
                        left_semitone=semitones[i],
                        right_semitone=semitones[j],
                        semitone_span=span,
                        weight=weight_engine.pair_weight(chord, factors[i], factors[j], span),
                        target_adjust_cents=weight_engine.target_adjust_cents(chord, factors[i], factors[j], span),
                        root_dissonant=weight_engine.is_root_dissonance(factors[i], factors[j], span),
                    )
                )
        return tuple(out)


class WeightEngine:
    def __init__(
        self,
        tritone: float = 0.1,
        seconds_sevenths: float = 0.15,
        thirds_sixths: float = 0.6,
        fourth_fifth: float = 1.0,
        root_dissonant_chord_multiplier: float = 0.8,
        dominant_seventh_third_adjust_cents: float = 15.0,
    ) -> None:
        self.tritone = tritone
        self.seconds_sevenths = seconds_sevenths
        self.thirds_sixths = thirds_sixths
        self.fourth_fifth = fourth_fifth
        self.root_dissonant_chord_multiplier = root_dissonant_chord_multiplier
        self.dominant_seventh_third_adjust_cents = dominant_seventh_third_adjust_cents

    def pair_weight(self, chord: CanonicalChord, left_factor: str, right_factor: str, span: int) -> float:
        span_class = span % 12

        if span_class == 6:
            return self.tritone
        if span_class in {1, 2, 10, 11}:
            return self.seconds_sevenths
        if span_class in {3, 4, 8, 9}:
            return self.thirds_sixths
        if span_class in {5, 7}:
            return self.fourth_fifth
        return self.fourth_fifth

    def is_root_dissonance(self, left_factor: str, right_factor: str, span: int) -> bool:
        lf = left_factor.lstrip("b#")
        rf = right_factor.lstrip("b#")
        if "1" not in {lf, rf}:
            return False

        span_class = span % 12
        return span_class in {1, 2, 6, 10, 11}

    def target_adjust_cents(self, chord: CanonicalChord, left_factor: str, right_factor: str, span: int) -> float:
        lf = left_factor.lstrip("b#")
        rf = right_factor.lstrip("b#")
        is_dominant_seventh = "3" in chord.factors and "b7" in chord.factors and "7" not in chord.factors
        if is_dominant_seventh and span % 12 in {3, 4} and {lf, rf} != {"1", "5"}:
            return self.dominant_seventh_third_adjust_cents
        return 0.0

    def chord_multiplier(self, intervals: tuple[IntervalPair, ...]) -> float:
        if any(pair.root_dissonant for pair in intervals):
            return self.root_dissonant_chord_multiplier
        return 1.0


class TemperamentRegistry:
    _CENTERS = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
    _FIFTH_CHAINS = {
        "Pythagorean": (701.955,) * 12,
        "1/4-comma meantone": (696.578,) * 12,
        "1/5-comma meantone": (697.653,) * 12,
        "1/6-comma meantone": (698.370,) * 12,
        "Werckmeister I": (701.955, 701.955, 701.955, 701.955, 701.955, 701.955, 698.500, 698.500, 698.500, 698.500, 698.500, 698.500),
        "Werckmeister II": (701.955, 701.955, 701.955, 701.955, 699.750, 699.750, 699.750, 699.750, 699.750, 699.750, 699.750, 699.750),
        "Werckmeister III": (701.955, 701.955, 701.955, 701.955, 700.000, 700.000, 700.000, 700.000, 700.000, 700.000, 700.000, 700.000),
        "Werckmeister IV": (701.955, 701.955, 701.955, 701.955, 699.600, 699.600, 699.600, 699.600, 699.600, 699.600, 699.600, 699.600),
        "Werckmeister V": (701.955, 701.955, 701.955, 699.300, 699.300, 699.300, 699.300, 699.300, 699.300, 699.300, 699.300, 699.300),
        "Werckmeister VI": (701.955, 701.955, 701.955, 698.900, 698.900, 698.900, 698.900, 698.900, 698.900, 698.900, 698.900, 698.900),
        "Kirnberger I": (701.955, 701.955, 701.955, 701.955, 701.955, 700.200, 700.200, 700.200, 700.200, 700.200, 700.200, 700.200),
        "Kirnberger II": (701.955, 701.955, 701.955, 701.955, 700.000, 700.000, 700.000, 700.000, 700.000, 700.000, 700.000, 700.000),
        "Kirnberger III": (701.955, 701.955, 701.955, 700.600, 700.600, 700.600, 700.600, 700.600, 700.600, 700.600, 700.600, 700.600),
        "Vallotti": (701.955, 701.955, 701.955, 701.955, 701.955, 701.955, 698.045, 698.045, 698.045, 698.045, 698.045, 698.045),
        "Young II": (701.955, 701.955, 701.955, 701.955, 701.300, 701.300, 699.000, 699.000, 699.000, 699.000, 699.000, 699.000),
        "Kellner": (701.955, 701.955, 701.955, 701.955, 700.500, 700.500, 699.000, 699.000, 699.000, 699.000, 699.000, 699.000),
        "Neidhardt": (701.955, 701.955, 701.955, 700.900, 700.900, 700.900, 699.000, 699.000, 699.000, 699.000, 699.000, 699.000),
        "Rameau": (701.955, 701.955, 701.955, 700.700, 700.700, 700.700, 699.200, 699.200, 699.200, 699.200, 699.200, 699.200),
        "Marpurg": (701.955, 701.955, 701.955, 700.500, 700.500, 700.500, 699.300, 699.300, 699.300, 699.300, 699.300, 699.300),
        "Sorge": (701.955, 701.955, 701.955, 700.300, 700.300, 700.300, 699.400, 699.400, 699.400, 699.400, 699.400, 699.400),
        "Bendeler I": (701.955, 701.955, 701.200, 701.200, 700.300, 700.300, 699.100, 699.100, 699.100, 699.100, 699.100, 699.100),
        "Bendeler II": (701.955, 701.955, 701.000, 701.000, 700.200, 700.200, 699.050, 699.050, 699.050, 699.050, 699.050, 699.050),
        "Bendeler III": (701.955, 701.955, 700.900, 700.900, 700.100, 700.100, 699.000, 699.000, 699.000, 699.000, 699.000, 699.000),
        "Silbermann I": (701.955, 701.955, 700.700, 700.700, 700.000, 700.000, 698.950, 698.950, 698.950, 698.950, 698.950, 698.950),
        "Silbermann II": (701.955, 701.955, 700.600, 700.600, 699.900, 699.900, 698.900, 698.900, 698.900, 698.900, 698.900, 698.900),
        "Schlick": (701.955, 701.955, 700.500, 700.500, 699.700, 699.700, 698.850, 698.850, 698.850, 698.850, 698.850, 698.850),
        "Zarlino": (701.955, 701.955, 700.300, 700.300, 699.600, 699.600, 698.800, 698.800, 698.800, 698.800, 698.800, 698.800),
        "Salinas": (701.955, 701.955, 700.200, 700.200, 699.500, 699.500, 698.750, 698.750, 698.750, 698.750, 698.750, 698.750),
        "12-TET baseline": (700.000,) * 12,
    }

    def candidates(self) -> list[tuple[str, str, tuple[float, ...]]]:
        out: list[tuple[str, str, tuple[float, ...]]] = []
        for family, fifth_chain in self._FIFTH_CHAINS.items():
            base_map = self._build_map_from_fifths(fifth_chain)
            for center_index, center in enumerate(self._CENTERS):
                shifted = tuple(base_map[(pc - center_index) % 12] for pc in range(12))
                out.append((family, center, shifted))
        return out

    def _build_map_from_fifths(self, fifth_chain: tuple[float, ...]) -> tuple[float, ...]:
        values = [0.0] * 12
        pc = 0
        cur = 0.0
        mean_adjust = sum(fifth_chain) / len(fifth_chain) - 700.0
        for fifth_size in fifth_chain:
            values[pc] = cur
            pc = (pc + 7) % 12
            cur += fifth_size - mean_adjust
            while cur >= 1200.0:
                cur -= 1200.0

        minimum = min(values)
        return tuple(((v - minimum) % 1200.0 for v in values))


class JIReference:
    def target_cents(self, semitone_span: int) -> float:
        octaves, rem = divmod(semitone_span, 12)
        return _JI_BY_SEMITONE[rem] + 1200.0 * octaves


class ScoringEngine:
    def __init__(self, ji_reference: JIReference) -> None:
        self.ji_reference = ji_reference

    def score_piece(
        self,
        chords: Iterable[CanonicalChord],
        interval_map: dict[str, tuple[IntervalPair, ...]],
        pitch_map: tuple[float, ...],
        weight_engine: WeightEngine,
    ) -> tuple[float, float, float, list[tuple[str, float]], list[tuple[str, float]]]:
        weighted_mae_sum = 0.0
        weighted_mse_sum = 0.0
        total_chord_weight = 0.0
        chord_contribs: list[tuple[str, float]] = []
        interval_contribs: list[tuple[str, float]] = []

        for chord in chords:
            intervals = interval_map[chord.symbol]
            if not intervals:
                continue

            pair_weight_sum = 0.0
            abs_sum = 0.0
            sq_sum = 0.0

            for pair in intervals:
                left_pc = (chord.root_pc + pair.left_semitone) % 12
                right_pc = (chord.root_pc + pair.right_semitone) % 12

                temp_cents = (pitch_map[right_pc] - pitch_map[left_pc]) % 1200.0
                if pair.semitone_span >= 12:
                    temp_cents += 1200.0 * (pair.semitone_span // 12)

                ji = self.ji_reference.target_cents(pair.semitone_span) + pair.target_adjust_cents
                err = abs(temp_cents - ji)
                w = pair.weight

                pair_weight_sum += w
                abs_sum += w * err
                sq_sum += w * err * err
                interval_contribs.append((f"{chord.symbol}:{pair.semitone_span}", w * err))

            chord_mae = abs_sum / pair_weight_sum
            chord_mse = sq_sum / pair_weight_sum
            cw = chord.frequency * chord.weight * weight_engine.chord_multiplier(intervals)
            weighted_mae_sum += cw * chord_mae
            weighted_mse_sum += cw * chord_mse
            total_chord_weight += cw
            chord_contribs.append((chord.symbol, cw * chord_mae))

        if total_chord_weight == 0.0:
            return 0.0, 0.0, 0.0, [], []

        wmae = weighted_mae_sum / total_chord_weight
        wrmse = math.sqrt(weighted_mse_sum / total_chord_weight)
        final = (wmae + wrmse) / 2.0
        top_chords = sorted(chord_contribs, key=lambda x: x[1], reverse=True)[:5]
        top_intervals = sorted(interval_contribs, key=lambda x: x[1], reverse=True)[:5]
        return wmae, wrmse, final, top_chords, top_intervals


class Ranker:
    def rank(self, records: list[RankedRecord]) -> list[RankedRecord]:
        return sorted(records, key=lambda r: (r.final_score_cents, r.wrmse_cents, r.wmae_cents, r.family, r.center))


class Reporter:
    def to_dicts(self, ranked: Iterable[RankedRecord]) -> list[dict[str, object]]:
        return [
            {
                "family": r.family,
                "center": r.center,
                "wmae_cents": r.wmae_cents,
                "wrmse_cents": r.wrmse_cents,
                "final_score_cents": r.final_score_cents,
                "top_chord_contributors": list(r.top_chord_contributors),
                "top_interval_contributors": list(r.top_interval_contributors),
            }
            for r in ranked
        ]


class MusicalTuningOptimizer:
    def __init__(self) -> None:
        self.input_adapter = InputAdapter()
        self.decoder = ChordDecoder()
        self.weight_engine = WeightEngine()
        self.interval_builder = IntervalBuilder()
        self.registry = TemperamentRegistry()
        self.scoring = ScoringEngine(JIReference())
        self.ranker = Ranker()
        self.reporter = Reporter()

    def optimize_from_lines(
        self,
        lines: Iterable[str],
        weights: dict[str, float] | None = None,
    ) -> tuple[list[dict[str, object]], list[str]]:
        parsed, invalid = self.input_adapter.parse_lines(lines)
        chords = [self.decoder.decode(p) for p in parsed]
        weight_engine = (
            self.weight_engine
            if weights is None
            else WeightEngine(
                tritone=weights.get("tritone", self.weight_engine.tritone),
                seconds_sevenths=weights.get("seconds_sevenths", self.weight_engine.seconds_sevenths),
                thirds_sixths=weights.get("thirds_sixths", self.weight_engine.thirds_sixths),
                fourth_fifth=weights.get("fourth_fifth", self.weight_engine.fourth_fifth),
                root_dissonant_chord_multiplier=weights.get(
                    "root_dissonant_chord_multiplier",
                    self.weight_engine.root_dissonant_chord_multiplier,
                ),
                dominant_seventh_third_adjust_cents=weights.get(
                    "dominant_seventh_third_adjust_cents",
                    self.weight_engine.dominant_seventh_third_adjust_cents,
                ),
            )
        )
        interval_map = {c.symbol: self.interval_builder.build(c, weight_engine) for c in chords}

        records: list[RankedRecord] = []
        for family, center, pitch_map in self.registry.candidates():
            wmae, wrmse, final, top_chords, top_intervals = self.scoring.score_piece(
                chords,
                interval_map,
                pitch_map,
                weight_engine,
            )
            records.append(
                RankedRecord(
                    family=family,
                    center=center,
                    wmae_cents=wmae,
                    wrmse_cents=wrmse,
                    final_score_cents=final,
                    top_chord_contributors=tuple(top_chords),
                    top_interval_contributors=tuple(top_intervals),
                )
            )

        ranked = self.ranker.rank(records)
        return self.reporter.to_dicts(ranked), invalid
