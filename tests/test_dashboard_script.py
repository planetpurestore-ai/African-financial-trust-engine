from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess

import pytest


class InlineScriptCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_script = False
        self.external_script = False
        self.current = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            self.in_script = True
            self.external_script = any(k.lower() == "src" for k, _ in attrs)
            self.current = []

    def handle_data(self, data):
        if self.in_script and not self.external_script:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.in_script:
            if not self.external_script:
                self.scripts.append("".join(self.current))
            self.in_script = False
            self.external_script = False
            self.current = []


def test_dashboard_inline_javascript_parses():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; JavaScript syntax check runs in GitHub Actions")
    dashboard = Path(__file__).resolve().parents[1] / "app" / "dashboard_operational.html"
    parser = InlineScriptCollector()
    parser.feed(dashboard.read_text(encoding="utf-8"))
    assert parser.scripts, "Expected inline dashboard JavaScript"
    for script in parser.scripts:
        result = subprocess.run([node, "--check"], input=script, text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stderr