from pathlib import Path


def test_pages_workflow_deploys_browser_app_index():
    workflow = Path('.github/workflows/deploy-pages.yml').read_text(encoding='utf-8')
    index = Path('web/index.html')

    assert index.exists()
    assert 'cp web/index.html site/index.html' in workflow
    html = index.read_text(encoding='utf-8')
    assert 'id="run"' in html
    assert 'function optimize(lines)' in html
