from musical_tuning.optimizer import InputAdapter, ChordDecoder, MusicalTuningOptimizer, TemperamentRegistry


def test_input_adapter_parses_all_supported_formats():
    lines = [
        "Am7,24,1.0",
        "Am7 | 24 | 1.0",
        "symbol=Am7 frequency=24 weight=1.0",
        '{"symbol":"Am7","frequency":24,"weight":1.0}',
        "24x Am7 @1.0",
        "not valid",
    ]
    parsed, invalid = InputAdapter().parse_lines(lines)

    assert len(parsed) == 5
    assert invalid == ["not valid"]


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
