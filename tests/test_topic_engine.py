"""
Tests for engine/topic_engine.py
AC-54: topic_engine exists, AC-66: tests exist
"""
from unittest.mock import patch, MagicMock


class TestTopicEngineImports:
    def test_imports_ok(self):
        """AC-54: topic_engine functions import correctly."""
        from engine.topic_engine import suggest_topics
        assert callable(suggest_topics)


class TestSuggestTopics:
    def test_suggest_topics_returns_list(self):
        """suggest_topics returns a list of topic dicts."""
        from engine.topic_engine import suggest_topics

        with patch("engine.topic_engine.get_client") as mock_gc:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.execute.return_value = MagicMock(data=[])
            mock_gc.return_value = mock_client

            with patch("engine.topic_engine._extract_from_brain2", return_value=[]):
                with patch("engine.topic_engine._extract_from_forge", return_value=[]):
                    result = suggest_topics(channel="ai", count=5, source="brain2")

        assert isinstance(result, list)

    def test_suggest_topics_empty_channel(self):
        """Handles unknown channel gracefully (falls back to 'ai')."""
        from engine.topic_engine import suggest_topics

        with patch("engine.topic_engine.get_client") as mock_gc:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.execute.return_value = MagicMock(data=[])
            mock_gc.return_value = mock_client

            with patch("engine.topic_engine._extract_from_brain2", return_value=[]):
                result = suggest_topics(channel="unknown", count=3, source="brain2")

        assert isinstance(result, list)

    def test_suggest_topics_mixed_source(self):
        """source='mixed' combines brain2 and forge."""
        from engine.topic_engine import suggest_topics

        with patch("engine.topic_engine.get_client") as mock_gc:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.execute.return_value = MagicMock(data=[])
            mock_gc.return_value = mock_client

            with patch("engine.topic_engine._extract_from_brain2", return_value=[
                {"suggested_topic": "Brain2 Topic", "source": "brain2", "score": 80, "context_preview": ""},
            ]):
                with patch("engine.topic_engine._extract_from_forge", return_value=[
                    {"suggested_topic": "Forge Topic", "source": "forge", "score": 90, "context_preview": ""},
                ]):
                    result = suggest_topics(channel="ai", count=5, source="mixed")

        assert len(result) == 2
        topics = [t["suggested_topic"] for t in result]
        assert "Brain2 Topic" in topics
        assert "Forge Topic" in topics

    def test_suggest_topics_no_duplicate_exact_match(self):
        """Case-insensitive exact duplicate topic names are deduplicated."""
        from engine.topic_engine import _dedupe_by_exact

        topics = [
            {"suggested_topic": "AI Tips"},
            {"suggested_topic": "ai tips"},   # case-insensitive duplicate of "AI Tips"
            {"suggested_topic": "AI Tips"},  # exact duplicate of "AI Tips"
            {"suggested_topic": "Other Topic"},
        ]
        result = _dedupe_by_exact(topics)
        assert len(result) == 2
        titles = [t["suggested_topic"] for t in result]
        assert "AI Tips" in titles       # first occurrence kept
        assert "ai tips" not in titles  # case-insensitive duplicate removed
        assert "Other Topic" in titles   # not a duplicate

    def test_suggest_topics_no_duplicate_exact_match_v2(self):
        """Dedupe preserves first occurrence, removes subsequent exact matches."""
        from engine.topic_engine import _dedupe_by_exact

        topics = [
            {"suggested_topic": "Topic A"},
            {"suggested_topic": "Topic A"},  # exact duplicate
            {"suggested_topic": "Topic B"},
        ]
        result = _dedupe_by_exact(topics)
        assert len(result) == 2
        assert [t["suggested_topic"] for t in result] == ["Topic A", "Topic B"]

    def test_suggest_topics_empty_source(self):
        """source='brain2' only returns brain2 results (no forge)."""
        from engine.topic_engine import suggest_topics

        with patch("engine.topic_engine.get_client") as mock_gc:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.execute.return_value = MagicMock(data=[])
            mock_gc.return_value = mock_client

            with patch("engine.topic_engine._extract_from_brain2", return_value=[
                {"suggested_topic": "Brain2 Only", "source": "brain2", "score": 75, "context_preview": ""},
            ]):
                with patch("engine.topic_engine._extract_from_forge", return_value=[]) as mock_forge:
                    result = suggest_topics(channel="ai", count=5, source="brain2")

        assert len(result) == 1
        assert result[0]["suggested_topic"] == "Brain2 Only"
        mock_forge.assert_not_called()

    def test_rank_by_novelty_filters_existing(self):
        """Topics already in DB are filtered out."""
        from engine.topic_engine import _rank_by_novelty

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=[{"topic": "Existing Topic"}]
        )
        with patch("engine.topic_engine.get_client", return_value=mock_client):
            topics = [
                {"suggested_topic": "Existing Topic"},
                {"suggested_topic": "New Topic"},
            ]
            result = _rank_by_novelty(topics)
            assert len(result) == 1
            assert result[0]["suggested_topic"] == "New Topic"

    def test_rank_by_novelty_preserves_all_when_db_empty(self):
        """When DB has no existing topics, all are preserved."""
        from engine.topic_engine import _rank_by_novelty

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.execute.return_value = MagicMock(data=[])
        with patch("engine.topic_engine.get_client", return_value=mock_client):
            topics = [
                {"suggested_topic": "Topic A"},
                {"suggested_topic": "Topic B"},
            ]
            result = _rank_by_novelty(topics)
            assert len(result) == 2