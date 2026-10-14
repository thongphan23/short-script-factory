"""
Tests for engine/brain2_client.py — chỉ mục Brain2 cục bộ (brain2_local).
AC-2, AC-50 (graceful degradation).
"""
from unittest.mock import patch

import engine.brain2_client as bc
from brain2_local import Brain2Unavailable

ROWS = [
    {"title": "AI Productivity", "file_path": "01-Atomic/ai-prod.md", "chunk_index": 0,
     "content": "Power law in work...", "namespaces": ["general"], "similarity": 0.85},
    {"title": "Content Creation", "file_path": "01-Atomic/content.md", "chunk_index": 1,
     "content": "Creating content...", "namespaces": ["general"], "similarity": 0.72},
]


class TestBrain2ClientImports:
    def test_imports_ok(self):
        """AC-2: brain2_client functions import correctly."""
        assert callable(bc.search_vault)
        assert callable(bc.get_context_for_topic)


class TestSearchVault:
    def test_search_vault_returns_mapped_results(self):
        with patch.object(bc, "search", return_value=ROWS) as mock_search:
            result = bc.search_vault("AI productivity", match_count=5)
        mock_search.assert_called_once_with("AI productivity", limit=5, min_similarity=0.20)
        assert result[0] == {"title": "AI Productivity", "file_path": "01-Atomic/ai-prod.md",
                             "content": "Power law in work...", "similarity": 0.85}
        assert len(result) == 2

    def test_search_vault_returns_empty_when_brain2_unavailable(self):
        """AC-50: Ollama tắt / node hỏng → [] thay vì crash."""
        with patch.object(bc, "search", side_effect=Brain2Unavailable("Ollama off")):
            assert bc.search_vault("test") == []

    def test_get_context_for_topic_builds_string(self):
        with patch.object(bc, "search", return_value=ROWS[:1]):
            ctx = bc.get_context_for_topic("AI tools for office")
        assert ctx.startswith("## AI Productivity\nPower law in work")

    def test_get_context_for_topic_empty_when_no_results(self):
        with patch.object(bc, "search", return_value=[]):
            assert bc.get_context_for_topic("xyz") == ""


class TestLocalIntegration:
    def test_real_local_index(self):
        """Gọi thật chỉ mục cục bộ; bỏ qua nếu Ollama không chạy."""
        import pytest
        try:
            rows = bc.search("Brain2 vault", limit=1)
        except Brain2Unavailable as exc:
            pytest.skip(f"Brain2 cục bộ không chạy: {exc}")
        assert rows and rows[0]["file_path"].endswith(".md")
