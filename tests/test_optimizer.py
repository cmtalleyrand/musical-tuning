from musical_tuning.optimizer import (
    ChordDecoder,
    InputAdapter,
    IntervalBuilder,
    MusicalTuningOptimizer,
    TemperamentRegistry,
    WeightEngine,
)
from musical_tuning.webapp import build_statistics


def test_input_adapter_parses_all_supported_formats():
    lines = [
        "Am7,24,1.0",
        "Am7,24",
        "Am7 | 24 | 1.0",
        "Am7 | 24",
        "| Am7 | 24 |  |",
        "symbol=Am7 frequency=24 weight=1.0",
        "symbol=Am7 frequency=24",
        '{"symbol":"Am7","frequency":24,"weight":1.0}',
        '{"symbol":"Am7","frequency":24}',
        "24x Am7 @1.0",
        "24x Am7",
        "Am7 24",
        "Am7\t24\t0.25",
        "[Am7] [24] [0.5]",
        "Am7;24;0.75",
        "not valid",
    ]
    parsed, invalid = InputAdapter().parse_lines(lines)

    assert len(parsed) == 15
    assert [chord.weight for chord in parsed] == [1.0] * 11 + [1.0, 0.25, 0.5, 0.75]
    assert invalid == ["not valid"]


def test_input_adapter_parses_markdown_table_and_defaults_missing_weight_to_one():
    lines = [
        ".",
        "| chord | frequency | weight |",
        "|---|---|---|",
        "| A | 12 | 1.5 |",
        "| A7 | 1 |  |",
        "| AM7 | 4 | |",
    ]
    parsed, invalid = InputAdapter().parse_lines(lines)

    assert invalid == []
    assert [chord.symbol for chord in parsed] == ["A", "A7", "AM7"]
    assert [chord.frequency for chord in parsed] == [12, 1, 4]
    assert [chord.weight for chord in parsed] == [1.5, 1.0, 1.0]


def test_input_adapter_parses_user_table_shape_with_blank_weights():
    lines = [
        ".",
        "| Chord | Frequency | weight|",
        "|---|---|---|",
        "| A | 12 |  |",
        "| A7 | 1 |  |",
        "| AM7 | 4 |  |",
        "| Am7 | 1 |  |",
        "| Bb | 1 |  |",
        "| C#sus2 | 3 |  |",
        "| G#m | 10 |  |",
    ]
    parsed, invalid = InputAdapter().parse_lines(lines)

    assert invalid == []
    assert [chord.symbol for chord in parsed] == ["A", "A7", "AM7", "Am7", "Bb", "C#sus2", "G#m"]
    assert [chord.frequency for chord in parsed] == [12, 1, 4, 1, 1, 3, 10]
    assert [chord.weight for chord in parsed] == [1.0] * 7


def test_input_adapter_parses_first_six_rows_from_user_table_exactly():
    lines = [
        ".",
        "| Chord | Frequency | weight|",
        "|---|---|---|",
        "| A | 12 |  |",
        "| A7 | 1 |  |",
        "| AM7 | 4 |  |",
        "| Am7 | 1 |  |",
        "| B | 3 |  |",
        "| B7 | 6 |  |",
    ]
    parsed, invalid = InputAdapter().parse_lines(lines)

    assert invalid == []
    assert [chord.symbol for chord in parsed] == ["A", "A7", "AM7", "Am7", "B", "B7"]
    assert [chord.frequency for chord in parsed] == [12, 1, 4, 1, 3, 6]
    assert [chord.weight for chord in parsed] == [1.0] * 6


def test_input_adapter_uses_pipe_header_column_positions():
    lines = [
        "| weight | chord | frequency | notes |",
        "|---|---|---|---|",
        "|  | A | 12 | tonic |",
        "| 0.25 | E7 | 8 | dominant |",
    ]
    parsed, invalid = InputAdapter().parse_lines(lines)

    assert invalid == []
    assert [chord.symbol for chord in parsed] == ["A", "E7"]
    assert [chord.frequency for chord in parsed] == [12, 8]
    assert [chord.weight for chord in parsed] == [1.0, 0.25]


def test_decoder_preserves_bass_and_extensions():
    chord = ChordDecoder().decode(InputAdapter().parse_lines(["Gsus4add9,3,1.2"])[0][0])

    assert chord.root_pc == 7
    assert chord.bass_pc == 7
    assert chord.factors == ("1", "4", "5", "9")
    assert chord.factor_semitones == (0, 5, 7, 14)


def test_registry_candidate_count_matches_spec():
    candidates = TemperamentRegistry().candidates()
    assert len(candidates) == 29 * 12


def test_end_to_end_optimization_returns_ranked_schema():
    optimizer = MusicalTuningOptimizer()
    ranked, invalid = optimizer.optimize_from_lines(["Am7,24,1.0", "D/F#,12,0.7", "Gsus4add9,9,0.8"])

    assert not invalid
    assert ranked
    top = ranked[0]
    assert set(top.keys()) == {
        "family",
        "center",
        "wmae_cents",
        "wrmse_cents",
        "final_score_cents",
        "top_chord_contributors",
        "top_interval_contributors",
    }


def test_empty_or_invalid_input_returns_no_crash():
    optimizer = MusicalTuningOptimizer()
    ranked, invalid = optimizer.optimize_from_lines(["bad input"])

    assert invalid == ["bad input"]
    assert ranked
    assert ranked[0]["final_score_cents"] == 0.0


def test_interval_builder_keeps_ordered_semitones_in_pairs():
    chord = ChordDecoder().decode(InputAdapter().parse_lines(["Cadd9,1,1.0"])[0][0])
    pairs = IntervalBuilder().build(chord, WeightEngine())

    spans = {pair.semitone_span for pair in pairs}
    assert 14 in spans
    pair_14 = [pair for pair in pairs if pair.semitone_span == 14][0]
    assert pair_14.left_semitone == 0
    assert pair_14.right_semitone == 14


def test_root_to_third_fifth_weight_requires_root_factor():
    chord = ChordDecoder().decode(InputAdapter().parse_lines(["Cmaj7,1,1.0"])[0][0])
    weight_engine = WeightEngine()

    no_root_weight = weight_engine.pair_weight(chord, "3", "5", span=3)
    with_root_weight = weight_engine.pair_weight(chord, "1", "3", span=4)

    assert no_root_weight == 1.0
    assert with_root_weight == 1.5


def test_build_statistics_reports_best_and_mean_scores():
    ranked = [
        {"family": "A", "center": "C", "final_score_cents": 1.0},
        {"family": "B", "center": "D", "final_score_cents": 3.0},
        {"family": "C", "center": "E", "final_score_cents": 5.0},
    ]
    stats = build_statistics(ranked, invalid=["bad"], input_lines=4)

    assert stats.input_lines == 4
    assert stats.valid_chords == 3
    assert stats.invalid_lines == 1
    assert stats.candidate_count == 3
    assert stats.best_family == "A"
    assert stats.best_center == "C"
    assert stats.best_final_score_cents == 1.0
    assert stats.mean_final_score_cents == 3.0
