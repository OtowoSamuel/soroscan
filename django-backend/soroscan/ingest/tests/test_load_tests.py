"""Sanity checks for the k6 load testing framework (issue #516)."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_load_test_scripts_exist():
    assert (REPO_ROOT / "load-tests/k6/smoke.js").is_file()
    assert (REPO_ROOT / "load-tests/k6/scenarios.js").is_file()
    assert (REPO_ROOT / "load-tests/README.md").is_file()


def test_ci_workflow_exists():
    workflow = REPO_ROOT / ".github/workflows/load-tests.yml"
    assert workflow.is_file()
    content = workflow.read_text(encoding="utf-8")
    assert "k6 run load-tests/k6/smoke.js" in content
