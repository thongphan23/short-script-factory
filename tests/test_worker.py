"""
Tests for worker.py — daemon + graceful shutdown.
AC-23: Worker --once --dry-run exits cleanly
AC-24: Worker processes queued topic (mocked)
"""
from unittest.mock import patch, MagicMock
import uuid
import worker  # noqa: E402 — module under test


class TestWorkerPickTopic:
    def test_pick_topic_returns_none_when_empty(self):
        """Returns None when no queued topics."""
        import worker
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cur

        result = worker._pick_topic(mock_conn)
        assert result is None

    def test_pick_topic_returns_dict_when_topic_exists(self):
        """Returns topic dict with correct fields when FOR UPDATE SKIP LOCKED finds topic."""
        import worker
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        # Simulate real cursor.description format (list of 2-tuples from psycopg2)
        mock_cur.description = [
            ("id",), ("topic",), ("source",), ("source_ref",),
            ("channel",), ("target_factory",), ("brain2_context",),
            ("forge_context",), ("auto_mode",),
        ]
        mock_cur.fetchone.return_value = (
            str(uuid.uuid4()), "5 AI Tips", "manual",
            None, "ai", "doodle", [], None, True,
        )
        mock_conn.cursor.return_value = mock_cur

        result = worker._pick_topic(mock_conn)
        assert result is not None
        assert result["topic"] == "5 AI Tips"
        assert result["channel"] == "ai"
        assert result["auto_mode"] is True


def _make_table_mock(topic_id, script_id):
    """Build a chain-mock that handles insert + update + eq for tpe_scripts/topics."""
    def table_mock(name):
        m = MagicMock()
        m.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": topic_id if "topic" in name else script_id}],
        )
        m.update.return_value.eq.return_value.execute.return_value = MagicMock()
        return m
    return table_mock


class TestWorkerProcessTopic:
    def test_qa_pass_approved_no_dispatch(self):
        """QA pass + auto_mode=False → script qa_pass, no dispatch call."""
        topic = {
            "id": str(uuid.uuid4()),
            "topic": "Test topic",
            "source": "manual",
            "channel": "ai",
            "target_factory": "doodle",
            "auto_mode": False,
        }

        mock_gen = MagicMock(return_value={
            "scenes": [{"id": 1, "narration": "Anh em oi"}],
        })
        mock_qa_result = MagicMock(
            passed=True, score=88,
            details={}, feedback=[],
        )

        topic_id = str(uuid.uuid4())
        script_id = str(uuid.uuid4())
        mock_client = MagicMock()
        mock_client.table.side_effect = _make_table_mock(topic_id, script_id)

        # Patch at source modules — no importlib.reload needed
        with patch("engine.script_writer.generate_script", mock_gen):
            with patch("engine.script_qa.score_script", mock_qa_result):
                with patch.object(worker, "_supabase_client", return_value=mock_client):
                    with patch("engine.dispatcher.dispatch", MagicMock()) as mock_dispatch:
                        result = worker.process_topic(topic, dry_run=False)

        assert result is True
        mock_gen.assert_called_once()
        mock_dispatch.assert_not_called()  # auto_mode=False

    def test_qa_pass_auto_mode_dispatches(self):
        """QA pass + auto_mode=True → auto-dispatch called."""
        topic = {
            "id": str(uuid.uuid4()),
            "topic": "Test topic",
            "source": "manual",
            "channel": "ai",
            "target_factory": "video",
            "auto_mode": True,
        }

        mock_gen = MagicMock(return_value={"scenes": [{"id": 1}]})
        mock_qa_result = MagicMock(
            passed=True, score=85,
            details={}, feedback=[],
        )

        topic_id = str(uuid.uuid4())
        script_id = str(uuid.uuid4())
        mock_client = MagicMock()
        mock_client.table.side_effect = _make_table_mock(topic_id, script_id)
        mock_dispatch = MagicMock()

        with patch("engine.script_writer.generate_script", mock_gen):
            with patch("engine.script_qa.score_script", mock_qa_result):
                with patch.object(worker, "_supabase_client", return_value=mock_client):
                    with patch("engine.dispatcher.dispatch", mock_dispatch):
                        result = worker.process_topic(topic, dry_run=False)

        assert result is True
        mock_dispatch.assert_called_once()

    def test_qa_fail_retry_scheduled(self):
        """QA fail + revision < 3 → handled gracefully, topic status updated."""
        topic = {
            "id": str(uuid.uuid4()),
            "topic": "Test topic",
            "source": "manual",
            "channel": "ai",
            "target_factory": "doodle",
            "auto_mode": False,
        }

        mock_gen = MagicMock(return_value={"scenes": [{"id": 1}]})
        mock_qa_result = MagicMock(
            passed=False, score=60,
            details={}, feedback=["Hook yeu"],
        )

        topic_id = str(uuid.uuid4())
        script_id = str(uuid.uuid4())
        mock_client = MagicMock()
        mock_client.table.side_effect = _make_table_mock(topic_id, script_id)

        with patch("engine.script_writer.generate_script", mock_gen):
            with patch("engine.script_qa.score_script", mock_qa_result):
                with patch.object(worker, "_supabase_client", return_value=mock_client):
                    result = worker.process_topic(topic, dry_run=False)

        assert result is True  # handled gracefully


class TestWorkerGracefulShutdown:
    def test_once_dry_run_exits_cleanly(self):
        """AC-23: --once --dry-run exits with no error (no topics to process)."""
        import worker

        with patch.object(worker, "get_pg_conn", return_value=MagicMock()):
            with patch.object(worker, "_pick_topic", return_value=None):
                # Skip health server binding to avoid port conflict when worker daemon is running
                with patch.object(worker, "_start_health_server", lambda *args, **kwargs: None):
                    # Should not raise
                    worker.run_daemon(once=True, dry_run=True)

    def test_dry_run_skips_generation(self):
        """dry_run=True → process_topic returns True without calling generate_script."""
        import worker

        topic = {
            "id": str(uuid.uuid4()),
            "topic": "Dry run test",
            "source": "manual",
            "channel": "ai",
            "target_factory": "doodle",
            "auto_mode": False,
        }

        with patch("engine.script_writer.generate_script") as mock_gen:
            result = worker.process_topic(topic, dry_run=True)
            assert result is True
            mock_gen.assert_not_called()
