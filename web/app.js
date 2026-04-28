let pyodide;

const statusEl = document.getElementById("status");
const inputEl = document.getElementById("input");
const runBtn = document.getElementById("run");
const resultsBody = document.getElementById("results");
const invalidEl = document.getElementById("invalid");
const bestSummaryEl = document.getElementById("best-summary");
const bestChordsEl = document.getElementById("best-chords");
const bestIntervalsEl = document.getElementById("best-intervals");

const initialize = async () => {
  pyodide = await loadPyodide();

  const [optimizerSource, initSource] = await Promise.all([
    fetch("./musical_tuning/optimizer.py").then((r) => r.text()),
    fetch("./musical_tuning/__init__.py").then((r) => r.text()),
  ]);

  pyodide.FS.mkdirTree("/app/musical_tuning");
  pyodide.FS.writeFile("/app/musical_tuning/optimizer.py", optimizerSource);
  pyodide.FS.writeFile("/app/musical_tuning/__init__.py", initSource);

  pyodide.runPython(`import sys\nsys.path.append('/app')`);
  pyodide.runPython("from musical_tuning import MusicalTuningOptimizer");
  statusEl.textContent = "Ready.";
};

const renderTable = (rows) => {
  resultsBody.innerHTML = "";
  rows.forEach((row, idx) => {
    const tr = document.createElement("tr");
    const values = [
      idx + 1,
      row.family,
      row.center,
      row.wmae_cents.toFixed(4),
      row.wrmse_cents.toFixed(4),
      row.final_score_cents.toFixed(4),
    ];
    values.forEach((value) => {
      const td = document.createElement("td");
      td.textContent = String(value);
      tr.appendChild(td);
    });
    resultsBody.appendChild(tr);
  });
};

const renderContributors = (target, entries, formatter) => {
  target.innerHTML = "";
  if (!entries.length) {
    const li = document.createElement("li");
    li.textContent = "None";
    target.appendChild(li);
    return;
  }

  entries.forEach((entry) => {
    const li = document.createElement("li");
    li.textContent = formatter(entry);
    target.appendChild(li);
  });
};

const renderBestCandidate = (ranked) => {
  if (!ranked.length) {
    bestSummaryEl.textContent = "No candidates returned.";
    renderContributors(bestChordsEl, [], () => "");
    renderContributors(bestIntervalsEl, [], () => "");
    return;
  }

  const best = ranked[0];
  bestSummaryEl.textContent = `Family=${best.family}, Center=${best.center}, WMAE=${best.wmae_cents.toFixed(4)}, WRMSE=${best.wrmse_cents.toFixed(4)}, Final=${best.final_score_cents.toFixed(4)}`;
  renderContributors(bestChordsEl, best.top_chord_contributors, ([name, value]) => `${name}: ${Number(value).toFixed(4)}`);
  renderContributors(bestIntervalsEl, best.top_interval_contributors, ([name, value]) => `${name}: ${Number(value).toFixed(4)}`);
};

const runOptimizer = async () => {
  if (!pyodide) {
    return;
  }

  runBtn.disabled = true;
  statusEl.textContent = "Optimizing...";

  pyodide.globals.set("input_text", inputEl.value);
  const resultJson = await pyodide.runPythonAsync(`
import json
lines = [line for line in input_text.splitlines()]
ranked, invalid = MusicalTuningOptimizer().optimize_from_lines(lines)
json.dumps({"ranked": ranked[:10], "invalid": invalid})
`);

  const parsed = JSON.parse(resultJson);
  renderTable(parsed.ranked);
  renderBestCandidate(parsed.ranked);
  invalidEl.textContent = parsed.invalid.length ? parsed.invalid.join("\n") : "None";
  statusEl.textContent = `Done. Evaluated ${parsed.ranked.length} displayed candidates.`;
  runBtn.disabled = false;
};

runBtn.addEventListener("click", runOptimizer);
initialize().catch((err) => {
  statusEl.textContent = `Failed to initialize: ${err.message}`;
});
