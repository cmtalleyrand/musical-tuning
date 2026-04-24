# Musical Tuning Optimizer

## Project Plan

### Objective
Build an application that ranks historical tuning systems for a piece using chord inventories, interval structure, and weighted distance to 5-limit just intonation.

### Input Model
Each chord entry uses three fields:
- `symbol`: chord symbol (`Am7`, `D/F#`, `Gsus4add9`)
- `frequency`: occurrence count in the piece
- `weight`: user-selected chord importance multiplier

### Text Input Formats
The parser supports these equivalent line formats:
1. `Am7,24,1.0`
2. `Am7 | freq=24 | weight=1.0`
3. `symbol=Am7 frequency=24 weight=1.0`
4. `{"symbol":"Am7","frequency":24,"weight":1.0}`
5. `24x Am7 @1.0`

A single-pass tokenizer gives `O(L)` parsing cost per line where `L` is line length.

## Chord and Interval Data Model

### Canonical chord record
Each parsed chord maps to:
- `root_pc`
- `bass_pc`
- `factors` (ordered factor labels, e.g. `[1,b3,5,b7,9]`)
- `factor_semitones` (e.g. `[0,3,7,10,14]`)
- `frequency`
- `weight`

This representation preserves factor identity such as `2` and `9` for weight control.

### Interval generation rule
For a chord with `n` factors:
1. order factors by semitone height from root,
2. generate interval pairs `(i, j)` for all `i < j`.

Pair generation uses `n(n-1)/2` edges, which is `O(n^2)` per chord.

## Weighting Model
All weights are configurable by the user.

Default multipliers:
- root to third/fifth: `1.5`
- bass to any other note: `1.5`
- root to dissonance (2nd, tritone, 7th): `0.5`
- compound interval: `0.75`
- factor-specific map includes independent controls for `2`, `9`, `11`, `13`, and sevenths

Final interval-pair weight is the product of active multipliers, computed in `O(1)` using direct lookup.

## Temperament Catalogue
Evaluate each family across 12 centers (`C` through `B`).

Families:
- Pythagorean
- 1/4-comma meantone
- 1/5-comma meantone
- 1/6-comma meantone
- Werckmeister I, II, III, IV, V, VI
- Kirnberger I, II, III
- Vallotti
- Young II
- Kellner
- Neidhardt
- Rameau
- Marpurg
- Sorge
- Bendeler I, II, III
- Silbermann I, II
- Schlick
- Zarlino
- Salinas
- 12-TET baseline

Candidate count equals `12 × F` where `F` is family count.

## Scoring
For each interval pair in each candidate:
- cent error: `e = |temp_cents - ji_cents|`
- squared cent error: `e²`

For each chord:
- weighted mean absolute cent error
- weighted mean squared cent error

For piece-level aggregation:
- chord contribution weight: `Wc = frequency × weight`
- piece WMAE: weighted average of chord MAE
- piece WRMSE: square root of weighted average chord MSE
- final score: `(WMAE + WRMSE) / 2`

Lower final score ranks higher.

Total runtime is `O(C × P × T)`:
- `C`: chord entries
- `P`: average interval pairs per chord
- `T`: tuning candidates

## Architecture
1. `InputAdapter` — text parsing and normalization
2. `ChordDecoder` — root, bass, factors, semitone factors
3. `IntervalBuilder` — ordered pair graph (`i < j`)
4. `WeightEngine` — user-configured multipliers
5. `TemperamentRegistry` — cent tables by family and center
6. `JIReference` — 5-limit cent targets
7. `ScoringEngine` — pair, chord, piece metrics
8. `Ranker` — candidate ordering and tie-breaks
9. `Reporter` — ranking and diagnostics

Each stage consumes immutable upstream output, providing deterministic behavior and stable complexity.

## Milestones
### Milestone 1 — Core parser and chord decoder
Deliver multi-format parser and canonical chord records.

### Milestone 2 — Interval and weight engine
Deliver ordered interval graph and configurable weighting.

### Milestone 3 — Temperament registry
Deliver family definitions and 12-center transposition generation.

### Milestone 4 — Scoring and ranking
Deliver complete candidate evaluation and ranking.

### Milestone 5 — Diagnostics and output
Deliver per-chord and per-interval contribution report.

### Milestone 6 — Verification
Deliver fixture-based checks for parser, interval generation, and ranking consistency.

## Output Schema
Each ranked record includes:
- `family`
- `center`
- `wmae_cents`
- `wrmse_cents`
- `final_score_cents`
- `top_chord_contributors`
- `top_interval_contributors`
