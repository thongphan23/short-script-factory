"""
Tests for engine/script_qa.py
AC-5: script_qa imports OK
AC-13: detects colon in narration as AUTO-FAIL
AC-14: detects em-dash in narration as AUTO-FAIL
"""
import pytest
from engine.script_qa import (
    score_script,
    QAResult,
    _auto_fail,
    _score_structure,
    _score_voice_dna,
    _score_hook,
    _score_content_depth,
    _score_format_compliance,
)


# ── Sample scripts ─────────────────────────────────────────────────────────
VALID_DOODLE = {
    "metadata": {"topic": "5 AI Tips", "estimated_duration_sec": 180},
    "scenes": [
        {
            "id": i,
            "narration": f"Anh em ơi, tui chia sẻ tip {i} nè. Đây là actionable advice.",
            "visual_prompt": "minimalist white line art on pure black background, person at desk",
            "motion_prompt": "person typing",
            "duration_sec": 9,
        }
        for i in range(1, 21)
    ],
}

VALID_VIDEO = {
    "title": "5 AI Tips",
    "totalDurationTarget": 90,
    "scenes": [
        {
            "id": 1, "type": "hook",
            "narration": "90% dân văn phòng dùng AI sai cách nha.",
            "durationSec": 8,
            "visual_strategy": {"layout": "dramatic_number"},
        },
        {
            "id": 2, "type": "data_card",
            "narration": "Tui đã thử và thấy kết quả khác biệt.",
            "durationSec": 12,
            "visual_strategy": {"layout": "card_list"},
        },
        {
            "id": 3, "type": "data_card",
            "narration": "Đây là bước 1, copy prompt của tui nha.",
            "durationSec": 10,
            "visual_strategy": {"layout": "timeline_steps"},
        },
        {
            "id": 4, "type": "data_card",
            "narration": "Bước 2, paste vào ChatGPT nha anh em.",
            "durationSec": 10,
            "visual_strategy": {"layout": "timeline_steps"},
        },
        {
            "id": 5, "type": "data_card",
            "narration": "Bước 3, xem kết quả rồi điều chỉnh nha.",
            "durationSec": 10,
            "visual_strategy": {"layout": "timeline_steps"},
        },
        {
            "id": 6, "type": "cta",
            "narration": "Đăng ký kênh và like video nếu thấy hữu ích nha anh em.",
            "durationSec": 8,
            "visual_strategy": {"layout": "brand_closing"},
        },
    ],
}


class TestAutoFail:
    def test_colon_causes_auto_fail(self):
        """AC-13: colon in narration triggers auto-fail."""
        script = {
            "metadata": {"estimated_duration_sec": 180},
            "scenes": [
                {
                    "id": 1,
                    "narration": "Anh em ơi, hãy nghĩ xem: 90% người dùng sai.",
                    "visual_prompt": "minimalist white line art on pure black background, a",
                    "motion_prompt": "a", "duration_sec": 8,
                }
            ],
        }
        assert _auto_fail(script) is True

    def test_emdash_causes_auto_fail(self):
        """AC-14: em-dash in narration triggers auto-fail."""
        script = {
            "metadata": {"estimated_duration_sec": 180},
            "scenes": [
                {
                    "id": 1,
                    "narration": "Đó là điều tui muốn nói\u2014và tui nói thật.",
                    "visual_prompt": "minimalist white line art on pure black background, a",
                    "motion_prompt": "a", "duration_sec": 8,
                }
            ],
        }
        assert _auto_fail(script) is True

    def test_clean_narration_no_auto_fail(self):
        """Clean narration passes auto-fail check."""
        assert _auto_fail(VALID_DOODLE) is False

    def test_colon_in_visual_prompt_not_auto_fail(self):
        """Colon only matters in narration, not visual_prompt."""
        script = {
            "metadata": {"estimated_duration_sec": 180},
            "scenes": [
                {
                    "id": 1,
                    "narration": "Anh em ơi, tip này cực kỳ hữu ích nha.",
                    "visual_prompt": "minimalist white line art on pure black background, desk:5",
                    "motion_prompt": "a", "duration_sec": 8,
                }
            ],
        }
        assert _auto_fail(script) is False


class TestScoreScript:
    def test_imports_ok(self):
        """AC-5: score_script imports correctly."""
        from engine.script_qa import score_script
        assert callable(score_script)

    @pytest.mark.parametrize("script", [VALID_DOODLE, VALID_VIDEO])
    def test_valid_script_passes(self, script):
        """Valid script scores above threshold."""
        target = "doodle" if "metadata" in script else "video"
        result = score_script(script, channel="ai", target_factory=target)
        # isinstance check uses QAResult from import at top of this file.
        # Note: test_integration.py may reload engine.script_qa, creating a new
        # QAResult class. We check by name + attributes instead of class identity.
        assert hasattr(result, "score")
        assert hasattr(result, "passed")
        assert result.score > 0
        assert result.passed is True

    def test_colon_script_auto_fails(self):
        """AC-13: script with colon returns score=0, passed=False."""
        script = {
            "metadata": {"estimated_duration_sec": 180},
            "scenes": [
                {
                    "id": 1,
                    "narration": "Anh em ơi, hãy nghĩ xem: 90% người dùng sai.",
                    "visual_prompt": "minimalist white line art on pure black background, a",
                    "motion_prompt": "a", "duration_sec": 8,
                }
            ],
        }
        result = score_script(script, channel="ai", target_factory="doodle")
        assert result.score == 0
        assert result.passed is False
        assert "AUTO-FAIL" in result.feedback[0]

    def test_emdash_script_auto_fails(self):
        """AC-14: script with em-dash returns score=0, passed=False."""
        script = {
            "metadata": {"estimated_duration_sec": 180},
            "scenes": [
                {
                    "id": 1,
                    "narration": "Điều tui muốn nói\u2014tui nói thật nha.",
                    "visual_prompt": "minimalist white line art on pure black background, a",
                    "motion_prompt": "a", "duration_sec": 8,
                }
            ],
        }
        result = score_script(script, channel="ai", target_factory="doodle")
        assert result.score == 0
        assert result.passed is False

    def test_qa_result_to_dict(self):
        """QAResult serializes to dict correctly."""
        result = QAResult(score=85, details={"structure": {"score": 20}}, feedback=["OK"], passed=True)
        d = result.to_dict()
        assert d["score"] == 85
        assert d["passed"] is True
        assert d["details"]["structure"]["score"] == 20


class TestDimensionScoring:
    def test_score_structure_doodle_pass(self):
        """Doodle with correct scene count + duration scores full."""
        score, notes = _score_structure(VALID_DOODLE, "doodle")
        assert score == 20
        assert "OK" in notes

    def test_score_structure_video_pass(self):
        """Video with correct scene count + duration scores full."""
        score, notes = _score_structure(VALID_VIDEO, "video")
        assert score == 20

    def test_score_voice_dna_tui_and_anh_em(self):
        """Scores points for tui + anh em usage."""
        score, notes = _score_voice_dna(VALID_DOODLE)
        assert score >= 10  # tui + anh em = 10

    def test_score_voice_dna_clean_no_colon_emdash(self):
        """Scores bonus for no colon/emdash."""
        score, _ = _score_voice_dna(VALID_DOODLE)
        assert score >= 15  # tui + anh em + no colon + no emdash = 20

    def test_score_hook_short_first_scene(self):
        """Short first scene (≤25 words) gets points."""
        score, notes = _score_hook(VALID_VIDEO)
        assert score >= 7  # ≤25 words + hook signal

    def test_score_hook_generic_long_fails(self):
        """Long generic first scene fails hook score."""
        script = {
            "title": "Test",
            "scenes": [
                {
                    "id": 1,
                    "narration": "This is a very generic introduction to a topic about productivity and time management that many people struggle with in their daily work routines.",
                }
            ],
        }
        score, notes = _score_hook(script)
        assert score < 15

    def test_score_content_depth_with_context(self):
        """Scores higher with Brain2 context + actionable steps."""
        script = VALID_DOODLE.copy()
        score, notes = _score_content_depth(script, brain2_context="Power law in work")
        assert score >= 10

    def test_score_content_depth_generic(self):
        """Low score for generic script without context."""
        script = {
            "title": "Generic",
            "scenes": [{"id": 1, "narration": "This is about productivity."}],
        }
        score, notes = _score_content_depth(script)
        assert score < 10

    def test_score_format_compliance_doodle(self):
        """Doodle format compliance checks visual_prompt prefix + motion_prompt."""
        score, errors = _score_format_compliance(VALID_DOODLE, "doodle")
        assert score >= 10
        assert errors == []

    def test_score_format_compliance_video(self):
        """Video format checks dramatic_number + brand_closing."""
        score, errors = _score_format_compliance(VALID_VIDEO, "video")
        assert score == 10
        assert errors == []
