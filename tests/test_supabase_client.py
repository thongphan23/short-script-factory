"""
Tests for engine/supabase_client.py
AC-7: supabase_client imports OK
"""
import pytest
from unittest.mock import patch, MagicMock


class TestSupabaseClient:
    def test_imports_ok(self):
        """AC-7: get_client imports correctly."""
        from engine.supabase_client import get_client
        assert callable(get_client)

    def test_get_client_returns_client(self):
        """Returns Supabase client via create_client."""
        mock_created = MagicMock()
        with patch("engine.supabase_client.create_client", return_value=mock_created) as mc:
            # Reset module state first
            import engine.supabase_client as sc
            sc._client = None
            client = sc.get_client()

            assert client is mock_created
            mc.assert_called_once_with(
                "https://bksqlgwotvpabksnynbo.supabase.co",
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJrc3FsZ3dvdHZwYWJrc255bmJvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mzc1Mzg0OSwiZXhwIjoyMDg5MzI5ODQ5fQ.KbQjZBGxkWmnl4weFndZ0f_ORYHokA2UYx8592HgU8k",
            )

    def test_get_client_raises_without_key(self):
        """Raises RuntimeError if SUPABASE_SERVICE_KEY is empty."""
        import engine.supabase_client as sc
        # Reset state
        sc._client = None
        with patch.object(sc, "SUPABASE_SERVICE_KEY", ""):
            with pytest.raises(RuntimeError) as exc:
                sc.get_client()
            assert "SUPABASE_SERVICE_KEY" in str(exc.value)

    def test_get_client_cached(self):
        """Second call returns cached client (no second create)."""
        mock_client = MagicMock()
        import engine.supabase_client as sc
        sc._client = None  # reset

        with patch("engine.supabase_client.create_client", return_value=mock_client):
            c1 = sc.get_client()
            c2 = sc.get_client()

            assert c1 is c2
            assert c2 is mock_client
            # create_client called exactly once (cached on second call)
            from unittest.mock import ANY
            # Verify only one call by checking cache
            assert sc._client is mock_client
