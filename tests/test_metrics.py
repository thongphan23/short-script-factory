"""
Tests for engine/metrics.py
AC-42
"""
from unittest.mock import patch, MagicMock


class TestMetrics:
    def test_record_generation_no_crash(self):
        """record_generation handles errors gracefully (doesn't raise)."""
        from engine.metrics import record_generation
        # get_client imported inside function — patch at source
        with patch("engine.supabase_client.get_client") as mock_gc:
            mock_gc.side_effect = Exception("DB error")
            record_generation(
                topic_id="t1", script_id="s1",
                channel="ai", target="doodle",
                qa_score=88, passed=True,
                duration_sec=45.0, revision=0,
            )

    def test_get_stats_summary_returns_dict(self):
        """get_stats_summary returns a dict with expected keys."""
        from engine.metrics import get_stats_summary
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None,
        )
        with patch("engine.supabase_client.get_client", return_value=mock_client):
            result = get_stats_summary()
        assert isinstance(result, dict)
        assert "total" in result
        assert "avg_qa" in result
        assert "pass_rate" in result
        assert "by_channel" in result

    def test_get_stats_summary_with_data(self):
        """get_stats_summary computes stats correctly from mock data."""
        import json
        from engine.metrics import get_stats_summary

        mock_data = json.dumps([
            {"qa_score": 88, "passed": True, "channel": "ai", "target": "doodle"},
            {"qa_score": 60, "passed": False, "channel": "ai", "target": "doodle"},
            {"qa_score": 75, "passed": True, "channel": "viral", "target": "video"},
        ])

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=[{"value": mock_data}],
        )
        with patch("engine.supabase_client.get_client", return_value=mock_client):
            result = get_stats_summary()

        assert result["total"] == 3
        assert result["avg_qa"] == round((88 + 60 + 75) / 3, 1)
        assert abs(result["pass_rate"] - 2 / 3) < 0.001  # float safe
        assert result["by_channel"]["ai"]["total"] == 2
        assert result["by_channel"]["ai"]["passed"] == 1

    def test_get_stats_summary_empty(self):
        """Empty metrics returns zeros."""
        from engine.metrics import get_stats_summary
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=[],
        )
        with patch("engine.supabase_client.get_client", return_value=mock_client):
            result = get_stats_summary()
        assert result["total"] == 0


class TestMetricsImports:
    def test_metrics_module_importable(self):
        """metrics module imports cleanly."""
        from engine.metrics import get_stats_summary, record_generation
        assert callable(get_stats_summary)
        assert callable(record_generation)
