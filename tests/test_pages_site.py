from pathlib import Path
import subprocess
import textwrap


def test_pages_workflow_deploys_browser_app_index():
    workflow = Path('.github/workflows/deploy-pages.yml').read_text(encoding='utf-8')
    index = Path('web/index.html')

    assert index.exists()
    assert 'cp web/index.html site/index.html' in workflow
    html = index.read_text(encoding='utf-8')
    assert 'id="run"' in html
    assert 'function optimize(lines)' in html


def test_pages_parser_accepts_user_markdown_table_rows():
    node_script = textwrap.dedent(
        """
        const fs = require('node:fs');
        const vm = require('node:vm');

        const html = fs.readFileSync('web/index.html', 'utf8');
        const script = html.match(/<script>([\\s\\S]*)<\\/script>/)[1];

        const element = { addEventListener: () => {}, value: '', textContent: '', className: '', innerHTML: '' };
        const context = {
          document: { getElementById: () => element },
          console,
          Math,
          Number,
          JSON,
          Array,
          Object,
          String,
          RegExp,
        };
        vm.createContext(context);
        vm.runInContext(script, context);

        const lines = [
          '.',
          '| Chord | Frequency | weight|',
          '|---|---|---|',
          '| A | 12 |  |',
          '| A7 | 1 |  |',
          '| AM7 | 4 |  |',
          '| Am7 | 1 |  |',
          '| B | 3 |  |',
          '| B7 | 6 |  |',
          '| Bb | 1 |  |',
          '| BM7 | 1 |  |',
          '| Bm | 3 |  |',
          '| Bm7 | 1 |  |',
          '| C# | 1 |  |',
          '| C#7 | 4 |  |',
          '| C#m | 5 |  |',
          '| C#m7 | 3 |  |',
          '| C#sus2 | 3 |  |',
          '| C#sus4 | 1 |  |',
          '| D | 3 |  |',
          '| DM7 | 3 |  |',
          '| E | 7 |  |',
          '| E7 | 8 |  |',
          '| Eb | 2 |  |',
          '| Eb7 | 9 |  |',
          '| F# | 1 |  |',
          '| F#7 | 2 |  |',
          '| F#m | 6 |  |',
          '| F#m7 | 2 |  |',
          '| F#sus2 | 4 |  |',
          '| F7 | 1 |  |',
          '| Faug | 1 |  |',
          '| Fdim | 1 |  |',
          '| FM7 | 1 |  |',
          '| G | 1 |  |',
          '| G7 | 1 |  |',
          '| G# | 1 |  |',
          '| G#m | 10 |  |',
          '| G#m7 | 1 |  |',
          '| GM7 | 1 |  |',
        ];

        const out = context.optimize(lines);
        if (out.invalid.length !== 0) throw new Error(`invalid=${out.invalid.length}`);
        if (!out.ranked || out.ranked.length !== 348) throw new Error(`ranked=${out.ranked ? out.ranked.length : -1}`);
        """
    )
    subprocess.run(["node", "-e", node_script], check=True)


def test_pages_analysis_reacts_to_chord_weight_changes():
    node_script = textwrap.dedent(
        """
        const fs = require('node:fs');
        const vm = require('node:vm');

        const html = fs.readFileSync('web/index.html', 'utf8');
        const script = html.match(/<script>([\s\S]*)<\/script>/)[1];

        const element = { addEventListener: () => {}, value: '', textContent: '', className: '', innerHTML: '', selectedOptions: [], options: [] };
        const context = {
          document: { getElementById: () => element },
          console,
          Math,
          Number,
          JSON,
          Array,
          Object,
          String,
          RegExp,
        };
        vm.createContext(context);
        vm.runInContext(script, context);

        const common = ['Cmaj7,1,1.0', 'G7,1,1.0'];
        const lowWeight = context.optimize(common.map((line, idx) => idx === 0 ? 'Cmaj7,1,0.1' : line));
        const highWeight = context.optimize(common.map((line, idx) => idx === 0 ? 'Cmaj7,1,10.0' : line));

        const firstLow = lowWeight.ranked[0];
        const firstHigh = highWeight.ranked[0];
        const lowKey = `${firstLow.family}__${firstLow.center}`;
        const highKey = `${firstHigh.family}__${firstHigh.center}`;

        const lowAnalysis = context.analyzeCandidate(lowWeight.chords, lowWeight.intervalMap, lowWeight.pitchMaps[lowKey]);
        const highAnalysis = context.analyzeCandidate(highWeight.chords, highWeight.intervalMap, highWeight.pitchMaps[highKey]);

        const lowCmaj7 = lowAnalysis.perChord.find(row => row.symbol === 'Cmaj7');
        const highCmaj7 = highAnalysis.perChord.find(row => row.symbol === 'Cmaj7');
        if (!lowCmaj7 || !highCmaj7) throw new Error('missing chord analysis row');

        if (highCmaj7.weightedMae <= lowCmaj7.weightedMae) {
          throw new Error(`weightedMae did not increase: low=${lowCmaj7.weightedMae}, high=${highCmaj7.weightedMae}`);
        }
      """
    )
    subprocess.run(["node", "-e", node_script], check=True)


def test_interval_breakdown_uses_quantile_error_bands_for_current_view():
    node_script = textwrap.dedent(
        """
        const fs = require('node:fs');
        const vm = require('node:vm');

        const html = fs.readFileSync('web/index.html', 'utf8');
        const script = html.match(/<script>([\\s\\S]*)<\\/script>/)[1];

        const elements = {};
        const ensure = (id) => {
          if (!elements[id]) {
            elements[id] = { addEventListener: () => {}, value: '', textContent: '', className: '', innerHTML: '', selectedOptions: [], options: [] };
          }
          return elements[id];
        };

        const context = {
          document: { getElementById: ensure },
          console,
          Math,
          Number,
          JSON,
          Array,
          Object,
          String,
          RegExp,
        };
        vm.createContext(context);
        vm.runInContext(script, context);

        vm.runInContext(`
          const optimized = optimize(['Cmaj7,3,1.0', 'G7,2,1.0', 'Am7,1,1.0']);
          appState.ranked = optimized.ranked;
          appState.invalid = optimized.invalid;
          appState.chords = optimized.chords;
          appState.intervalMap = optimized.intervalMap;
          appState.pitchMaps = optimized.pitchMaps;
          appState.selectedAnalyses = {};

          const center = optimized.ranked[0].center;
          const best = optimized.ranked[0];
          document.getElementById('selected-family').value = best.family;
          document.getElementById('selected-center').value = center;
          document.getElementById('selected-chord').value = optimized.chords[0].symbol;
          document.getElementById('selected-comparisons').selectedOptions = [
            { value: best.family + '__' + center },
            { value: '12-TET baseline__' + center },
          ];
          renderCandidateDiagnostics();
          globalThis.__intervalBreakdownHtml = document.getElementById('interval-breakdown').innerHTML;
        `, context);

        const out = context.__intervalBreakdownHtml;
        if (!out.includes('Relative error bands (current view): low/mid/high')) throw new Error('missing legend');
        if (!out.includes('error-low')) throw new Error('missing low band');
        if (!out.includes('error-mid')) throw new Error('missing mid band');
        if (!out.includes('error-high')) throw new Error('missing high band');
      """
    )
    subprocess.run(["node", "-e", node_script], check=True)
