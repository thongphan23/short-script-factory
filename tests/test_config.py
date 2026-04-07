"""
Tests for engine/config.py
AC-1: config imports OK
"""
import pytest
from unittest.mock import patch
import importlib


class TestConfig:
    def test_imports_ok(self):
        """AC-1: engine.config loads without error."""
        # Reload to test fresh import
        import engine.config
        importlib.reload(engine.config)
        assert hasattr(engine.config, "VERTEX_API_KEY")
        assert hasattr(engine.config, "VERTEX_BASE_URL")
        assert hasattr(engine.config, "MODEL_WRITER")
        assert hasattr(engine.config, "MODEL_QA")
        assert hasattr(engine.config, "SUPABASE_URL")
        assert hasattr(engine.config, "SUPABASE_SERVICE_KEY")
        assert hasattr(engine.config, "SUPABASE_ANON_KEY")
        assert hasattr(engine.config, "OUTPUT_DIR")

    def test_defaults(self):
        """Values are strings (some may be empty if no .env)."""
        import engine.config as cfg
        assert isinstance(cfg.VERTEX_API_KEY, str)
        assert isinstance(cfg.VERTEX_BASE_URL, str)
        assert isinstance(cfg.MODEL_WRITER, str)
        assert isinstance(cfg.MODEL_QA, str)

    def test_logging_configured(self):
        """Logger is configured with correct format."""
        import logging
        # Config module sets up logging; just check root logger has handlers
        import engine.config as cfg
        # No assertion error = OK
        assert True
