"""
tests/conftest.py — Pytest configuration and shared fixtures.
"""
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def clean_test_outputs():
    """
    Auto-cleanup test artifacts after each test.
    Runs after every test to prevent test-*.json files from polluting output/.
    """
    yield
    output_dir = Path(__file__).parent.parent / "output" / "scripts"
    for f in output_dir.glob("test-*.json"):
        try:
            f.unlink()
        except OSError:
            pass  # ignore if already gone
