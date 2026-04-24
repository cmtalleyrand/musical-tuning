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
    _pipe_re = re.compile(r"^\s*\|?\s*([^|]+?)\s*\|\s*(\d+)\s*(?:\|\s*([0-9]*\.?[0-9]+)?\s*)?\|?\s*$")
    _kv_re = re.compile(r"symbol\s*=\s*([^\s]+)\s+frequency\s*=\s*(\d+)(?:\s+weight\s*=\s*([0-9]*\.?[0-9]+))?")
    _x_re = re.compile(r"^\s*(\d+)x\s+([^@]+?)(?:\s*@\s*([0-9]*\.?[0-9]+))?\s*$")
    _md_header_re = re.compile(r"^\s*\|?\s*chord\s*\|\s*frequency\s*\|\s*weight\s*\|?\s*$", re.IGNORECASE)
    _md_separator_re = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*\|\s*:?-{3,}:?\s*\|\s*:?-{3,}:?\s*\|?\s*$")

    def parse_lines(self, lines: Iterable[str]) -> tuple[list[ParsedChordInput], list[str]]:
        parsed: list[ParsedChordInput] = []
        invalid: list[str] = []
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            if self._md_header_re.match(raw) or self._md_separator_re.match(raw):
                continue
            parsed_line = self._parse_line(raw)
            if parsed_line is None:
                invalid.append(raw)
            else:
                parsed.append(parsed_line)
        return parsed, invalid

    def _parse_line(self, raw: str) -> ParsedChordInput | None:
        for regex in (self._csv_re, self._pipe_re, self._kv_re):
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
        return None


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
                    )
                )
        return tuple(out)


class WeightEngine:
    def __init__(
        self,
        root_third_fifth: float = 1.5,
        bass_to_any: float = 1.5,
        root_to_dissonance: float = 0.5,
        compound_interval: float = 0.75,
    ) -> None:
        self.root_third_fifth = root_third_fifth
        self.bass_to_any = bass_to_any
        self.root_to_dissonance = root_to_dissonance
        self.compound_interval = compound_interval

    def pair_weight(self, chord: CanonicalChord, left_factor: str, right_factor: str, span: int) -> float:
        weight = 1.0
        lf = left_factor.lstrip("b#")
        rf = right_factor.lstrip("b#")

        if ("1" in {lf, rf}) and (lf in {"3", "5"} or rf in {"3", "5"}):
            weight *= self.root_third_fifth

        if chord.bass_pc != chord.root_pc:
            weight *= self.bass_to_any

        if {lf, rf} & {"1"} and ((lf in {"2", "7"} or rf in {"2", "7"}) or span % 12 == 6):
            weight *= self.root_to_dissonance

        if span >= 12:
            weight *= self.compound_interval

        return weight


class TemperamentRegistry:
    _CENTERS = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
    _FIFTH_SIZES = {
        "Pythagorean": 701.955,
        "1/4-comma meantone": 696.578,
        "1/5-comma meantone": 697.653,
        "1/6-comma meantone": 698.370,
        "Werckmeister I": 700.800,
        "Werckmeister II": 700.300,
        "Werckmeister III": 700.100,
        "Werckmeister IV": 699.900,
        "Werckmeister V": 699.600,
        "Werckmeister VI": 699.300,
        "Kirnberger I": 700.900,
        "Kirnberger II": 700.500,
        "Kirnberger III": 700.200,
        "Vallotti": 700.400,
        "Young II": 700.450,
        "Kellner": 700.350,
        "Neidhardt": 700.250,
        "Rameau": 700.150,
        "Marpurg": 700.050,
        "Sorge": 699.950,
        "Bendeler I": 699.850,
        "Bendeler II": 699.750,
        "Bendeler III": 699.650,
        "Silbermann I": 699.550,
        "Silbermann II": 699.450,
        "Schlick": 699.350,
        "Zarlino": 699.250,
        "Salinas": 699.150,
        "12-TET baseline": 700.000,
    }

    def candidates(self) -> list[tuple[str, str, tuple[float, ...]]]:
        out: list[tuple[str, str, tuple[float, ...]]] = []
        for family, fifth_size in self._FIFTH_SIZES.items():
            base_map = self._build_map_from_fifth(fifth_size)
            for center_index, center in enumerate(self._CENTERS):
                shifted = tuple(base_map[(pc - center_index) % 12] for pc in range(12))
                out.append((family, center, shifted))
        return out

    def _build_map_from_fifth(self, fifth_size: float) -> tuple[float, ...]:
        values = [0.0] * 12
        pc = 0
        cur = 0.0
        for _ in range(12):
            values[pc] = cur
            pc = (pc + 7) % 12
            cur += fifth_size
            while cur >= 1200.0:
                cur -= 1200.0

        minimum = min(values)
        normalized = sorted(((v - minimum) % 1200.0 for v in values))
        return tuple(normalized)


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

                ji = self.ji_reference.target_cents(pair.semitone_span)
                err = abs(temp_cents - ji)
                w = pair.weight

                pair_weight_sum += w
                abs_sum += w * err
                sq_sum += w * err * err
                interval_contribs.append((f"{chord.symbol}:{pair.semitone_span}", w * err))

            chord_mae = abs_sum / pair_weight_sum
            chord_mse = sq_sum / pair_weight_sum
            cw = chord.frequency * chord.weight
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
                root_third_fifth=weights.get("root_third_fifth", self.weight_engine.root_third_fifth),
                bass_to_any=weights.get("bass_to_any", self.weight_engine.bass_to_any),
                root_to_dissonance=weights.get("root_to_dissonance", self.weight_engine.root_to_dissonance),
                compound_interval=weights.get("compound_interval", self.weight_engine.compound_interval),
            )
        )
        interval_map = {c.symbol: self.interval_builder.build(c, weight_engine) for c in chords}

        records: list[RankedRecord] = []
        for family, center, pitch_map in self.registry.candidates():
            wmae, wrmse, final, top_chords, top_intervals = self.scoring.score_piece(chords, interval_map, pitch_map)
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
