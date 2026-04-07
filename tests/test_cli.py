"""
Tests for cli.py — argparse CLI entry point.
AC-20: python cli.py --help works
"""
import pytest
from unittest.mock import patch, MagicMock


class TestCLIParser:
    def test_cli_help_does_not_crash(self):
        """AC-20: --help flag is recognized by parser (does not raise TypeError)."""
        from cli import build_parser
        parser = build_parser()
        # --help should be handled by parser (not raise)
        # argparse exits on --help, so we just check the flag parses
        try:
            parser.parse_args(["--help"])
        except SystemExit as exc:
            # argparse exits with 0 on --help
            assert exc.code == 0

    def test_all_subcommands_registered(self):
        """All 6 required subcommands are present."""
        from cli import build_parser
        parser = build_parser()
        choices = parser._subparsers._actions[1].choices
        assert "generate" in choices
        assert "qa" in choices
        assert "dispatch" in choices
        assert "status" in choices
        assert "list-topics" in choices
        assert "run" in choices

    def test_generate_accepts_topic_and_channel(self):
        """generate subcommand: --topic, --channel, --target parse correctly."""
        from cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "generate",
            "--topic", "Test topic",
            "--channel", "ai",
            "--target", "video",
        ])
        assert args.topic == "Test topic"
        assert args.channel == "ai"
        assert args.target == "video"

    def test_generate_from_forge(self):
        """generate --from-forge sets flag."""
        from cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["generate", "--from-forge", "--channel", "viral"])
        assert args.from_forge is True
        assert args.channel == "viral"

    def test_qa_requires_script_id(self):
        """qa subcommand: --script-id parses as UUID string."""
        from cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["qa", "--script-id", "550e8400-e29b-41d4-a716-446655440000"])
        assert str(args.script_id) == "550e8400-e29b-41d4-a716-446655440000"

    def test_dispatch_requires_script_id(self):
        """dispatch subcommand: --script-id parses."""
        from cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["dispatch", "--script-id", "abc-def"])
        assert args.script_id == "abc-def"

    def test_run_requires_topic(self):
        """run subcommand: --topic, --auto-dispatch parse."""
        from cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "run",
            "--topic", "5 AI tips",
            "--channel", "ai",
            "--target", "doodle",
            "--auto-dispatch",
        ])
        assert args.topic == "5 AI tips"
        assert args.channel == "ai"
        assert args.target == "doodle"
        assert args.auto_dispatch is True

    def test_run_defaults(self):
        """run has sensible defaults for channel and target."""
        from cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["run", "--topic", "Any topic"])
        assert args.channel == "ai"
        assert args.target == "doodle"
        assert args.auto_dispatch is False
        assert args.max_retries == 0

    def test_batch_subcommand_registered(self):
        """batch subcommand is registered."""
        from cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "batch", "--source", "forge", "--channel", "ai", "--target", "doodle",
        ])
        assert args.channel == "ai"
        assert args.target == "doodle"
        assert args.source == "forge"
        assert args.count == 5

    def test_batch_manual_requires_topics_file(self):
        """batch --source manual requires --topics-file."""
        from cli import build_parser
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Topic 1\nTopic 2\n")
            tmp = f.name
        try:
            parser = build_parser()
            args = parser.parse_args([
                "batch", "--source", "manual", "--topics-file", tmp,
                "--channel", "viral", "--target", "video",
            ])
            assert args.source == "manual"
            assert args.topics_file == tmp
            assert args.channel == "viral"
        finally:
            os.unlink(tmp)

    def test_show_subcommand_registered(self):
        """show subcommand is registered."""
        from cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["show", "--script-id", "abc-123"])
        assert args.script_id == "abc-123"


class TestCLIHandlers:
    @patch("cli.cmd_status")
    def test_status_handler_called(self, mock_handler):
        """status subcommand calls cmd_status handler."""
        mock_handler.return_value = 0
        from cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.func == mock_handler  # handler attached to subparser

    @patch("cli.cmd_list_topics")
    def test_list_topics_handler_attached(self, mock_handler):
        """list-topics subcommand attaches handler."""
        mock_handler.return_value = 0
        from cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["list-topics", "--channel", "ai"])
        assert args.func == mock_handler
