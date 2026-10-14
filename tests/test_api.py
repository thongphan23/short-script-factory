"""
Tests for api.py — FastAPI endpoints for Dashboard integration.
AC-56, AC-59, AC-60, AC-65
"""
import pytest
from unittest.mock import patch, MagicMock


class TestAPIImports:
    def test_api_imports_ok(self):
        """AC-56: api module imports without crash."""
        from api import app
        assert app is not None


class TestStatusEndpoint:
    def test_status_returns_topics_and_scripts(self):
        """GET /api/status returns topics, scripts, and metrics."""
        from fastapi.testclient import TestClient
        from api import app

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            count=3, data=[]
        )
        mock_client.table.return_value.select.return_value.gt.return_value.execute.return_value = MagicMock(
            data=[]
        )

        with patch("engine.metrics.get_stats_summary", return_value={"total": 0, "avg_qa": 0, "pass_rate": 0, "by_channel": {}}):
            with patch("engine.supabase_client.get_client", return_value=mock_client):
                client = TestClient(app)
                resp = client.get("/api/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "topics" in data
        assert "scripts" in data
        assert "metrics" in data


class TestListScriptsEndpoint:
    def test_list_scripts_returns_data(self):
        """GET /api/scripts returns list of scripts."""
        from fastapi.testclient import TestClient
        from api import app

        mock_scripts = [
            {"id": "s1", "script_json": {"title": "Test"}, "status": "qa_pass", "channel": "ai"},
        ]
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=mock_scripts,
        )

        with patch("engine.supabase_client.get_client", return_value=mock_client):
            client = TestClient(app)
            resp = client.get("/api/scripts")

        assert resp.status_code == 200
        data = resp.json()
        assert "scripts" in data
        assert data["total"] == 1

    def test_list_scripts_with_channel_filter(self):
        """GET /api/scripts?channel=ai filters correctly."""
        from fastapi.testclient import TestClient
        from api import app

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[],
        )

        with patch("engine.supabase_client.get_client", return_value=mock_client):
            client = TestClient(app)
            resp = client.get("/api/scripts?channel=ai&limit=5")

        assert resp.status_code == 200


class TestGenerateEndpoint:
    def test_generate_queues_topic(self):
        """POST /api/generate queues a topic and returns topic_id."""
        from fastapi.testclient import TestClient
        from api import app

        mock_row = {"id": "t-123", "topic": "Test Topic", "status": "queued"}
        mock_client = MagicMock()
        mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[mock_row])

        with patch("engine.supabase_client.get_client", return_value=mock_client):
            client = TestClient(app)
            resp = client.post("/api/generate", json={
                "topic": "Test Topic",
                "channel": "ai",
                "target_factory": "doodle",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["topic_id"] == "t-123"


class TestQueueEndpoint:
    def test_queue_multiple_topics(self):
        """POST /api/queue queues multiple topics."""
        from fastapi.testclient import TestClient
        from api import app

        mock_row = {"id": "t-1"}
        mock_client = MagicMock()
        mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[mock_row])

        with patch("engine.supabase_client.get_client", return_value=mock_client):
            client = TestClient(app)
            resp = client.post("/api/queue", json={
                "topics": ["Topic A", "Topic B"],
                "channel": "ai",
                "target_factory": "doodle",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Queued 2 topics"
        assert len(data["topic_ids"]) == 2


class TestSuggestionsEndpoint:
    def test_suggestions_returns_list(self):
        """GET /api/suggestions returns topic list."""
        from fastapi.testclient import TestClient
        from api import app

        mock_topics = [
            {"suggested_topic": "AI Tips", "source": "brain2", "score": 85, "context_preview": ""},
        ]
        with patch("engine.topic_engine.suggest_topics", return_value=mock_topics):
            client = TestClient(app)
            resp = client.get("/api/suggestions?channel=ai&count=5")

        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) == 1

    def test_suggestions_empty_channel(self):
        """Returns empty list when no suggestions available."""
        from fastapi.testclient import TestClient
        from api import app

        with patch("engine.topic_engine.suggest_topics", return_value=[]):
            client = TestClient(app)
            resp = client.get("/api/suggestions?channel=viral")

        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []


class TestDispatchEndpoint:
    def test_dispatch_script_success(self):
        """POST /api/dispatch/:id dispatches script and returns target."""
        from fastapi.testclient import TestClient
        from api import app

        with patch("engine.dispatcher.dispatch", return_value="doodle-factory"):
            client = TestClient(app)
            resp = client.post("/api/dispatch/550e8400-e29b-41d4-a716-446655440000")

        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data

    def test_dispatch_script_invalid_uuid(self):
        """POST /api/dispatch/:id with invalid UUID returns 400."""
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        resp = client.post("/api/dispatch/not-a-uuid")
        assert resp.status_code == 400


class TestRejectEndpoint:
    def test_reject_script_success(self):
        """PATCH /api/scripts/:id/reject updates status to rejected."""
        from fastapi.testclient import TestClient
        from api import app

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "s1"}],
        )

        with patch("engine.supabase_client.get_client", return_value=mock_client):
            client = TestClient(app)
            resp = client.patch("/api/scripts/s1/reject")

        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Script rejected"
        assert data["script_id"] == "s1"

    def test_reject_script_not_found(self):
        """PATCH /api/scripts/:id/reject returns 404 when script missing."""
        from fastapi.testclient import TestClient
        from api import app

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with patch("engine.supabase_client.get_client", return_value=mock_client):
            client = TestClient(app)
            resp = client.patch("/api/scripts/nonexistent-id/reject")

        assert resp.status_code == 404


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        """GET /health returns ok status."""
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_api_health_returns_provider_info(self):
        """GET /api/health returns Brain2 backend."""
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        resp = client.get("/api/health")

        assert resp.status_code == 200
        data = resp.json()
        assert "api" in data
        assert data["brain2_backend"] == "local-bge-m3"
        assert "version" in data


class TestTopicsEndpoint:
    def test_list_topics_returns_data(self):
        """GET /api/topics returns topic list."""
        from fastapi.testclient import TestClient
        from api import app

        mock_topics = [
            {"id": "t1", "topic": "AI Tips", "status": "queued", "channel": "ai"},
        ]
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=mock_topics,
        )

        with patch("engine.supabase_client.get_client", return_value=mock_client):
            client = TestClient(app)
            resp = client.get("/api/topics")

        assert resp.status_code == 200
        data = resp.json()
        assert "topics" in data
        assert data["total"] == 1

    def test_list_topics_with_channel_filter(self):
        """GET /api/topics?channel=ai filters correctly."""
        from fastapi.testclient import TestClient
        from api import app

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[],
        )

        with patch("engine.supabase_client.get_client", return_value=mock_client):
            client = TestClient(app)
            resp = client.get("/api/topics?channel=ai&limit=5")

        assert resp.status_code == 200


class TestApproveEndpoint:
    def test_approve_script_success(self):
        """PATCH /api/scripts/:id/approve updates status to approved."""
        from fastapi.testclient import TestClient
        from api import app

        mock_client = MagicMock()
        # Select returns existing row
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "s1"}],
        )
        # Update succeeds (no return needed for update)

        with patch("engine.supabase_client.get_client", return_value=mock_client):
            client = TestClient(app)
            resp = client.patch("/api/scripts/s1/approve")

        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Script approved"
        assert data["script_id"] == "s1"

    def test_approve_script_not_found(self):
        """PATCH /api/scripts/:id/approve returns 404 when script missing."""
        from fastapi.testclient import TestClient
        from api import app

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[],
        )

        with patch("engine.supabase_client.get_client", return_value=mock_client):
            client = TestClient(app)
            resp = client.patch("/api/scripts/nonexistent-id/approve")

        assert resp.status_code == 404