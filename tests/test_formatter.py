"""
Tests for engine/formatter.py
AC-41
"""
from engine.formatter import format_script_for_review


class TestFormatDoodle:
    def test_format_doodle_has_scenes(self):
        """Format A: output contains scene entries."""
        script = {
            "metadata": {"topic": "Test Topic", "estimated_duration_sec": 180},
            "scenes": [
                {"id": 1, "narration": "Anh em oi", "visual_prompt": "minimalist white line art...", "motion_prompt": "person typing", "duration_sec": 8},
                {"id": 2, "narration": "Day la buoc 2", "visual_prompt": "minimalist white line art...", "motion_prompt": "hand drawing", "duration_sec": 9},
            ],
            "full_narration": "Anh em oi. Day la buoc 2.",
        }
        out = format_script_for_review(script, target_factory="doodle")
        assert "Test Topic" in out
        assert "[Scene 1]" in out
        assert "[Scene 2]" in out
        assert "FULL NARRATION" in out

    def test_format_video_has_layout(self):
        """Format B: output contains video scene entries."""
        script = {
            "title": "Test Video",
            "totalDurationTarget": 90,
            "scenes": [
                {"id": 1, "type": "hook", "visual_strategy": {"layout": "dramatic_number"}, "durationSec": 8, "narration": "Anh em oi"},
            ],
        }
        out = format_script_for_review(script, target_factory="video")
        assert "Test Video" in out
        assert "[Scene 1]" in out
        assert "dramatic_number" in out

    def test_format_empty_script(self):
        """Handles empty scenes gracefully."""
        script = {"metadata": {}, "scenes": []}
        out = format_script_for_review(script, target_factory="doodle")
        assert isinstance(out, str)
        assert "0 scenes" in out or "" == out.strip()


class TestFormatImports:
    def test_format_script_for_review_importable(self):
        """formatter module imports cleanly."""
        from engine.formatter import format_script_for_review
        assert callable(format_script_for_review)
