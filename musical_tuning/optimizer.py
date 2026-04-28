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
                        target_adjust_cents=(
                            -weight_engine.dominant_seventh_third_adjust_cents
                            if (("b7" in factors and "3" in factors) and {factors[i], factors[j]} == {"3", "b7"})
                            else 0.0
                        ),
                        root_dissonant=weight_engine.is_root_dissonance(factors[i], factors[j], span),
                    )
                )
        return tuple(out)


class WeightEngine:
    def __init__(
        self,
        tritone: float = 0.1,
        seconds_sevenths: float = 0.15,
        thirds_sixths: float = 1.0,
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
        weight = 1.0
        lf = left_factor.lstrip("b#")
        rf = right_factor.lstrip("b#")

        if "1" in {lf, rf} and ({lf, rf} & {"3", "5"}):
            weight *= 1.5

        span_class = span % 12

        if span_class == 6:
            weight *= self.tritone
        elif span_class in {1, 2, 10, 11}:
            weight *= self.seconds_sevenths
        elif span_class in {3, 4, 8, 9}:
            weight *= self.thirds_sixths
        elif span_class in {5, 7}:
            weight *= self.fourth_fifth
        else:
            weight *= self.fourth_fifth

        return weight

    def is_root_dissonance(self, left_factor: str, right_factor: str, span: int) -> bool:
        lf = left_factor.lstrip("b#")
        rf = right_factor.lstrip("b#")
        if "1" not in {lf, rf}:
            return False
        return (lf in {"2", "7"} or rf in {"2", "7"}) or span % 12 == 6

    def chord_multiplier(self, intervals: tuple[IntervalPair, ...]) -> float:
        if any(pair.root_dissonant for pair in intervals):
            return self.root_dissonant_chord_multiplier
        return 1.0


class TemperamentRegistry:
    _CENTERS = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
    _BASE_PITCH_MAPS = {
        "12-tone equal temperament": (0.000, 100.000, 200.000, 300.000, 400.000, 500.000, 600.000, 700.000, 800.000, 900.000, 1000.000, 1100.000),
        "Pythagorean": (0.000, 113.685, 203.910, 294.135, 407.820, 498.045, 611.730, 701.955, 815.640, 905.865, 996.090, 1109.775),
        "Ramis de Pareja (1482)": (0.000, 92.179, 182.404, 294.135, 386.314, 498.045, 590.224, 701.955, 792.180, 884.359, 996.090, 1088.269),
        "Agricola (1539)": (0.000, 92.179, 203.910, 296.089, 407.820, 498.045, 590.224, 701.955, 794.134, 905.865, 996.090, 1109.775),
        "De Caus (1615)": (0.000, 70.672, 182.404, 274.582, 386.314, 498.045, 568.717, 701.955, 772.627, 884.359, 996.090, 1088.269),
        "1/2-comma meantone": (0.000, 38.413, 182.404, 326.394, 364.807, 508.798, 547.211, 691.202, 729.615, 873.606, 1017.596, 1056.009),
        "1/3-comma meantone (Salinas)": (0.000, 63.504, 189.572, 315.641, 379.145, 505.214, 568.717, 694.786, 758.290, 884.359, 1010.428, 1073.931),
        "2/7-comma meantone (Zarlino 1558)": (0.000, 70.672, 191.621, 312.569, 383.241, 504.190, 574.862, 695.810, 766.483, 887.431, 1008.379, 1079.052),
        "1/4-comma meantone (Aaron 1523)": (0.000, 76.049, 193.157, 310.265, 386.314, 503.422, 579.471, 696.578, 772.627, 889.735, 1006.843, 1082.892),
        "Artusi I (1603)": (0.000, 96.578, 193.157, 289.735, 386.314, 503.422, 600.000, 696.578, 793.157, 889.735, 986.314, 1082.892),
        "1/5-comma meantone": (0.000, 83.576, 195.307, 307.039, 390.615, 502.346, 585.922, 697.654, 781.230, 892.961, 1004.693, 1088.269),
        "1/6-comma meantone (Salinas)": (0.000, 88.594, 196.741, 304.888, 393.482, 501.629, 590.224, 698.371, 786.965, 895.112, 1003.259, 1091.853),
        "1/8-comma meantone": (0.000, 94.867, 198.533, 302.200, 397.067, 500.733, 595.600, 699.267, 794.134, 897.800, 1001.467, 1096.334),
        "Chaumont (1695, 1st interpretation)": (0.000, 76.049, 193.157, 290.909, 386.314, 503.422, 579.471, 696.578, 772.627, 889.735, 997.165, 1082.892),
        "Couperin modified meantone": (0.000, 76.049, 193.157, 289.736, 386.314, 503.422, 579.471, 696.578, 772.627, 889.735, 996.579, 1082.892),
        "Corrette modified 1/4-comma meantone": (0.000, 76.049, 193.157, 288.758, 386.314, 503.422, 579.471, 696.578, 783.381, 889.735, 996.090, 1082.892),
        "Rameau modified meantone (1725)": (0.000, 86.802, 193.157, 297.800, 386.314, 503.422, 584.847, 696.578, 788.757, 889.735, 1006.843, 1082.892),
        "Werckmeister III (1681)": (0.000, 90.225, 192.180, 294.135, 390.225, 498.045, 588.270, 696.090, 792.180, 888.270, 996.090, 1092.180),
        "Werckmeister IV": (0.000, 82.405, 196.090, 294.135, 392.180, 498.045, 588.270, 694.135, 784.360, 890.225, 1003.910, 1086.315),
        "Werckmeister V": (0.000, 96.090, 203.910, 300.000, 396.090, 503.910, 600.000, 701.955, 792.180, 900.000, 1001.955, 1098.045),
        "Werckmeister VI": (0.000, 90.661, 186.334, 298.065, 395.169, 498.045, 594.923, 697.544, 792.616, 893.214, 1000.020, 1097.124),
        "Kirnberger II (1774)": (0.000, 92.179, 203.910, 294.135, 386.314, 498.045, 590.224, 701.955, 794.134, 895.078, 996.090, 1088.269),
        "Kirnberger III (1744)": (0.000, 92.179, 193.157, 294.135, 386.314, 498.045, 590.224, 696.578, 794.134, 889.735, 996.090, 1088.269),
        "Vallotti": (0.000, 94.135, 196.090, 298.045, 392.180, 501.955, 592.180, 698.045, 796.090, 894.135, 1000.000, 1090.225),
        "Vallotti 1/6-comma variant": (0.000, 95.763, 196.741, 299.673, 393.482, 501.629, 593.808, 698.371, 797.718, 895.112, 1001.628, 1091.853),
        "Young no. 2 (1799)": (0.000, 94.135, 196.090, 298.045, 392.180, 500.000, 592.180, 698.045, 796.090, 894.135, 1000.000, 1092.180),
        "Young no. 1 (1800)": (0.000, 93.856, 195.844, 297.791, 391.689, 499.870, 591.931, 697.926, 795.829, 893.733, 999.756, 1091.821),
        "Neidhardt f3 / Marpurg F": (0.000, 101.955, 200.000, 301.955, 400.000, 501.955, 600.000, 701.955, 800.000, 901.955, 1000.000, 1101.955),
        "Neidhardt f6": (0.000, 100.000, 196.090, 300.000, 400.000, 496.090, 600.000, 700.000, 796.090, 900.000, 1000.000, 1096.090),
        "Neidhardt sample no. 2 (1732)": (0.000, 90.225, 194.135, 294.135, 386.315, 496.090, 590.225, 698.045, 792.180, 890.225, 994.135, 1088.270),
        "Sorge II (1744)": (0.000, 98.045, 196.090, 301.955, 396.090, 501.955, 598.045, 698.045, 800.000, 896.090, 1001.955, 1098.045),
        "Temperament ordinaire II": (0.000, 86.000, 196.000, 292.000, 392.000, 498.000, 588.000, 698.000, 788.000, 894.000, 996.000, 1092.000),
        "Marpurg temperament no. 2": (0.000, 96.090, 194.135, 297.067, 400.000, 496.090, 594.135, 697.067, 800.000, 896.090, 994.135, 1097.068),
        "Broadwood's Best (1885)": (0.000, 96.000, 198.000, 298.000, 393.000, 500.000, 595.000, 700.000, 797.000, 895.000, 999.000, 1094.000),
    }

    def candidates(self) -> list[tuple[str, str, tuple[float, ...]]]:
        out: list[tuple[str, str, tuple[float, ...]]] = []
        for family, base_map in self._BASE_PITCH_MAPS.items():
            for center_index, center in enumerate(self._CENTERS):
                shifted = tuple(base_map[(pc - center_index) % 12] for pc in range(12))
                out.append((family, center, shifted))
        return out


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
