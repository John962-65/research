from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "web" / "app.js"


def _javascript_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    body_marker = source.index(") {", start)
    brace = body_marker + 2
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated JavaScript function: {name}")


def _run_node(script: str) -> None:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)


class WebFrontendSafetyTest(unittest.TestCase):
    def test_academic_markdown_never_trusts_raw_html_prefixes(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        functions = "\n".join(
            _javascript_function(app, name)
            for name in ["escapeHtml", "formatInline", "renderTable", "formatAcademicMarkdown"]
        )
        _run_node(
            functions
            + r"""
const attack = '<pre><img src=x onerror="fetch(\'/api/runs/victim/cancel\',{method:\'POST\'})">';
const rendered = formatAcademicMarkdown(attack, 'artifact.md');
if (rendered.includes('<img')) throw new Error(`raw img survived: ${rendered}`);
if (!rendered.includes('&lt;pre&gt;')) throw new Error(`raw pre was not escaped: ${rendered}`);
const code = formatAcademicMarkdown('```html\n<img onerror="boom">\n```', 'artifact.md');
if (!code.includes('<pre><code>') || code.includes('<img')) throw new Error(`code block unsafe: ${code}`);
const table = formatAcademicMarkdown('| Key | Value |\n| --- | --- |\n| safe | **yes** |', 'artifact.md');
if (!table.includes('<table>') || !table.includes('<strong>yes</strong>')) throw new Error(`table rendering regressed: ${table}`);
"""
        )

    def test_run_actions_submit_only_notes_or_explicit_config_differences(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        action_function = _javascript_function(app, "payloadForCurrentRunAction")
        fields_start = app.index("const RUN_ACTION_CONFIG_FIELDS")
        fields_end = app.index("const state =", fields_start)
        field_constants = app[fields_start:fields_end]
        _run_node(
            field_constants
            + "\n"
            + r"""
let currentPayload = {
  review_notes: 'checked', paper_grade_enabled: true,
  execution_mode: 'benchmark', literature_provider: 'online',
  llm_api_key: '', semantic_scholar_api_key: '', openalex_api_key: '', literature_contact_email: ''
};
function payloadForRunAction() { return {...currentPayload}; }
const state = {
  currentRun: {id: 'run-1', worker_active: false},
  formConfigRunId: 'run-1',
  runActionBaseline: {
    paper_grade_enabled: true, execution_mode: 'benchmark', literature_provider: 'online'
  }
};
"""
            + action_function
            + r"""
let payload = payloadForCurrentRunAction();
if (JSON.stringify(payload) !== JSON.stringify({review_notes: 'checked'})) {
  throw new Error(`unchanged config leaked into action: ${JSON.stringify(payload)}`);
}
currentPayload.paper_grade_enabled = false;
payload = payloadForCurrentRunAction();
if (payload.paper_grade_enabled !== false) throw new Error('explicit Paper-Grade downgrade was lost');
state.currentRun.worker_active = true;
currentPayload.execution_mode = 'simulated';
payload = payloadForCurrentRunAction();
if (Object.keys(payload).join(',') !== 'review_notes') throw new Error(`active approval mutated config: ${JSON.stringify(payload)}`);
"""
        )

    def test_polling_requests_and_accessibility_contracts_are_bounded(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("/api/runs?view=summary", app)
        self.assertIn("run.worker_active === true || run.status === 'cancelling'", app)
        self.assertIn("state.pollInFlight", app)
        self.assertIn("window.setTimeout(pollRunsOnce, 4000)", app)
        self.assertNotIn("setInterval(", app)
        self.assertGreaterEqual(app.count("new AbortController()"), 4)
        self.assertIn("if (!response.ok) throw new Error", app)
        self.assertIn("payload.llm_timeout_seconds = 8", app)
        self.assertIn('aria-live="polite"', index)
        self.assertIn('aria-selected="true"', index)
        self.assertIn('aria-pressed="true"', index)
        self.assertNotIn('class="artifact-viewer" aria-live=', index)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", styles)
        self.assertIn("overflow-x: auto;", styles)


if __name__ == "__main__":
    unittest.main()
