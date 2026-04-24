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
