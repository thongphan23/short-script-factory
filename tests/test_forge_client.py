"""
Tests for engine/forge_client.py
AC-3: forge_client imports OK
AC-16: reads content_queue
"""
import pytest
from unittest.mock import patch, MagicMock


class TestForgeClient:
    @patch("engine.forge_client.get_client")
    def test_get_forge_suggestions_returns_list(self, mock_get_client):
        """Returns scored topics from content_queue."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data=[
                {"id": "1", "suggested_topic": "AI tips", "total_score": 90},
                {"id": "2", "suggested_topic": "ChatGPT hacks", "total_score": 85},
            ]
        )
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        from engine.forge_client import get_forge_suggestions
        result = get_forge_suggestions(channel="ai", limit=5)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["suggested_topic"] == "AI tips"
        mock_table.eq.assert_any_call("status", "queued")
        mock_table.eq.assert_any_call("content_type", "ai")

    @patch("engine.forge_client.get_client")
    def test_get_forge_suggestions_empty_channel(self, mock_get_client):
        """Returns empty list when no data."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        from engine.forge_client import get_forge_suggestions
        result = get_forge_suggestions("tuhoc")
        assert result == []

    @patch("engine.forge_client.get_client")
    def test_get_forge_article_context(self, mock_get_client):
        """Fetches article summaries and returns concatenated string."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data=[
                {"title_vi": "Gemini 2.0 Review", "summary_vi": "Google AI launched...", "source_category": "rss"},
            ]
        )
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        from engine.forge_client import get_forge_article_context
        ctx = get_forge_article_context(["uuid-1", "uuid-2"])
        assert "Gemini 2.0 Review" in ctx
        assert "Google AI launched" in ctx

    @patch("engine.forge_client.get_client")
    def test_get_forge_article_context_empty_ids(self, mock_get_client):
        """Returns empty string for empty article_ids."""
        from engine.forge_client import get_forge_article_context
        result = get_forge_article_context([])
        assert result == ""
        mock_get_client.assert_not_called()

    @patch("engine.forge_client.get_client")
    @patch("engine.forge_client.date")
    def test_get_trending_insights_returns_dict(self, mock_date, mock_get_client):
        """Returns today's insights row."""
        mock_date.today.return_value.isoformat.return_value = "2026-04-07"
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data={"insight_date": "2026-04-07", "highlight_summary": "AI trends..."}
        )
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        from engine.forge_client import get_trending_insights
        result = get_trending_insights()
        assert result is not None
        assert "highlight_summary" in result

    @patch("engine.forge_client.get_client")
    @patch("engine.forge_client.date")
    def test_get_trending_insights_returns_none(self, mock_date, mock_get_client):
        """Returns None when no insights for today."""
        mock_date.today.return_value.isoformat.return_value = "2025-01-01"
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)
        mock_client.table.return_value = mock_table
        mock_get_client.return_value = mock_client

        from engine.forge_client import get_trending_insights
        result = get_trending_insights()
        assert result is None

    def test_imports_ok(self):
        """AC-3 + AC-16: functions import + query pattern verified."""
        from engine.forge_client import get_forge_suggestions, get_trending_insights
        assert callable(get_forge_suggestions)
        assert callable(get_trending_insights)
