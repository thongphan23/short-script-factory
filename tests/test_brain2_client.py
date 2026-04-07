"""
Tests for engine/brain2_client.py
OpenRouter embedding + psycopg2 architecture.
AC-2, AC-19, AC-27, AC-28, AC-31
"""
from unittest.mock import patch, MagicMock
import importlib


class TestBrain2ClientImports:
    def test_imports_ok(self):
        """AC-2: brain2_client functions import correctly."""
        from engine.brain2_client import search_vault, get_context_for_topic
        assert callable(search_vault)
        assert callable(get_context_for_topic)


class TestSearchVault:
    def test_search_vault_returns_mapped_results(self):
        """search_vault: OpenRouter → psycopg2 → returns [{title, content, similarity}]."""
        mock_pg_result = [
            ("AI Productivity", "01-Atomic/ai-prod.md", "Power law in work...", 0.85),
            ("Content Creation", "01-Atomic/content.md", "Creating content...", 0.72),
        ]
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = mock_pg_result
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        mock_emb_response = MagicMock()
        mock_emb_response.json.return_value = {"data": [{"embedding": [0.1] * 1536}]}
        mock_emb_response.raise_for_status = MagicMock()

        # Always reload first so module is fresh before patching
        import engine.brain2_client as bc
        importlib.reload(bc)

        with patch("engine.brain2_client.httpx.post", return_value=mock_emb_response):
            with patch("engine.db.get_pg_conn", return_value=mock_conn):
                with patch("engine.brain2_client.OPENROUTER_API_KEY", "mock-key"):
                    import engine.brain2_client as bc
                    importlib.reload(bc)
                    result = bc.search_vault("AI productivity", match_count=5)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["title"] == "AI Productivity"
        assert result[0]["content"] == "Power law in work..."
        assert result[0]["similarity"] == 0.85
        assert result[1]["content"] == "Creating content..."

    def test_search_vault_empty_when_no_key(self):
        """Returns [] when OPENROUTER_API_KEY is empty."""
        import engine.brain2_client as bc
        importlib.reload(bc)
        with patch.object(bc, "OPENROUTER_API_KEY", ""):
            result = bc.search_vault("test")
            assert result == []

    def test_search_vault_handles_embedding_error(self):
        """Returns [] when OpenRouter embedding call fails."""
        import engine.brain2_client as bc
        importlib.reload(bc)
        with patch("engine.brain2_client.httpx.post") as mock_http:
            mock_http.side_effect = Exception("HTTP error")
            result = bc.search_vault("test")
            assert result == []

    def test_search_vault_handles_db_error(self):
        """Returns [] when psycopg2 query fails."""
        import engine.brain2_client as bc
        importlib.reload(bc)
        with patch("engine.brain2_client.httpx.post") as mock_http:
            mock_emb = MagicMock()
            mock_emb.json.return_value = {"data": [{"embedding": [0.1] * 1536}]}
            mock_emb.raise_for_status = MagicMock()
            mock_http.return_value = mock_emb
            with patch("engine.db.get_pg_conn", side_effect=Exception("DB connection failed")):
                import engine.brain2_client as bc
                importlib.reload(bc)
                result = bc.search_vault("test")
                assert result == []

    def test_get_context_for_topic_builds_string(self):
        """Returns concatenated context: '## Title\\ncontent...'."""
        mock_pg_result = [
            ("Cognitive Tools", "01-Atomic/ai-tools.md",
             "AI agents chuyên biệt giúp tăng productivity...", 0.88),
        ]
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = mock_pg_result
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        mock_emb_response = MagicMock()
        mock_emb_response.json.return_value = {"data": [{"embedding": [0.1] * 1536}]}
        mock_emb_response.raise_for_status = MagicMock()

        import engine.brain2_client as bc
        importlib.reload(bc)

        with patch("engine.brain2_client.httpx.post", return_value=mock_emb_response):
            with patch("engine.db.get_pg_conn", return_value=mock_conn):
                with patch("engine.brain2_client.OPENROUTER_API_KEY", "mock-key"):
                    import engine.brain2_client as bc
                    importlib.reload(bc)
                    ctx = bc.get_context_for_topic("AI tools for office")

        assert isinstance(ctx, str)
        assert "## Cognitive Tools" in ctx
        assert "AI agents chuyên biệt" in ctx

    def test_get_context_for_topic_empty_when_no_results(self):
        """Returns empty string when vault has no matches."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        mock_emb_response = MagicMock()
        mock_emb_response.json.return_value = {"data": [{"embedding": [0.1] * 1536}]}
        mock_emb_response.raise_for_status = MagicMock()

        import engine.brain2_client as bc
        importlib.reload(bc)

        with patch("engine.brain2_client.httpx.post", return_value=mock_emb_response):
            with patch("engine.db.get_pg_conn", return_value=mock_conn):
                with patch("engine.brain2_client.OPENROUTER_API_KEY", "mock-key"):
                    import engine.brain2_client as bc
                    importlib.reload(bc)
                    ctx = bc.get_context_for_topic("xyz completely unknown")
                    assert ctx == ""


class TestBrain2ClientArchitecture:
    def test_uses_openrouter_for_embedding(self):
        """AC-27: _get_embedding calls OpenRouter."""
        import engine.brain2_client as bc
        import inspect
        src = inspect.getsource(bc._get_embedding)
        assert "openrouter" in src.lower()

    def test_uses_psycopg2_for_db(self):
        """AC-28: search_vault uses psycopg2 cursor."""
        import engine.brain2_client as bc
        import inspect
        src = inspect.getsource(bc.search_vault)
        assert "cursor" in src or "psycopg" in src.lower()

    def test_uses_engine_db_for_connection(self):
        """AC-32: search_vault uses engine.db.get_pg_conn."""
        import engine.brain2_client as bc
        import inspect
        src = inspect.getsource(bc.search_vault)
        assert "get_pg_conn" in src
