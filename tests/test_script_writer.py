"""
Tests for engine/script_writer.py
AC-4: script_writer imports OK
AC-15: outputs valid JSON schema (mocked LLM)
"""
import pytest
import json
from unittest.mock import patch, MagicMock, mock_open


class TestScriptWriter:
    def test_imports_ok(self):
        """AC-4: generate_script imports correctly."""
        from engine.script_writer import generate_script, _extract_json
        assert callable(generate_script)
        assert callable(_extract_json)

    def test_extract_json_with_code_fence(self):
        """Handles ```json ... ``` wrapper."""
        from engine.script_writer import _extract_json
        raw = '```json\n{"title": "Test", "scenes": []}\n```'
        result = _extract_json(raw)
        assert result["title"] == "Test"

    def test_extract_json_bare_braces(self):
        """Handles bare { ... } without code fence."""
        from engine.script_writer import _extract_json
        raw = '{"title": "Bare", "scenes": [{"id": 1}]}'
        result = _extract_json(raw)
        assert result["title"] == "Bare"
        assert len(result["scenes"]) == 1

    def test_extract_json_extracts_from_text(self):
        """Extracts JSON from mixed text."""
        from engine.script_writer import _extract_json
        raw = 'Here is the JSON:\n{"key": "value"}\nEnd of response.'
        result = _extract_json(raw)
        assert result["key"] == "value"

    def test_extract_json_invalid_raises(self):
        """Raises ValueError on invalid JSON."""
        from engine.script_writer import _extract_json
        with pytest.raises(ValueError):
            _extract_json("not json at all !!!")

    def test_validate_doodle_valid_schema(self):
        """Passes valid doodle_script with 20 scenes."""
        from engine.script_writer import _validate_doodle
        script = {
            "metadata": {"topic": "Test", "estimated_duration_sec": 180},
            "scenes": [
                {
                    "id": i,
                    "narration": f"Scene {i} narration",
                    "visual_prompt": "minimalist white line art on pure black background, person typing",
                    "motion_prompt": "person typing",
                    "duration_sec": 9,
                }
                for i in range(1, 21)
            ],
        }
        errors = _validate_doodle(script)
        assert errors == []

    def test_validate_doodle_bad_visual_prompt_prefix(self):
        """Catches visual_prompt without correct prefix."""
        from engine.script_writer import _validate_doodle
        script = {
            "metadata": {"estimated_duration_sec": 180},
            "scenes": [
                {
                    "id": 1,
                    "narration": "Test",
                    "visual_prompt": "red background, person at desk",  # bad prefix
                    "motion_prompt": "person walking",
                    "duration_sec": 8,
                }
            ],
        }
        errors = _validate_doodle(script)
        assert any("Scene 1" in e and "visual_prompt" in e for e in errors)

    def test_validate_doodle_scene_count(self):
        """Rejects scene count outside 15–35 range."""
        from engine.script_writer import _validate_doodle
        script = {
            "metadata": {"estimated_duration_sec": 60},
            "scenes": [{"id": 1, "narration": "a", "visual_prompt": "minimalist white line art on pure black background, a", "motion_prompt": "a", "duration_sec": 5}],
        }
        errors = _validate_doodle(script)
        assert any("Scene count" in e for e in errors)

    def test_validate_doodle_duration(self):
        """Rejects duration outside 120–280s."""
        from engine.script_writer import _validate_doodle
        script = {
            "metadata": {"estimated_duration_sec": 500},
            "scenes": [
                {
                    "id": 1, "narration": "a",
                    "visual_prompt": "minimalist white line art on pure black background, a",
                    "motion_prompt": "a", "duration_sec": 8,
                }
            ],
        }
        errors = _validate_doodle(script)
        assert any("Duration" in e for e in errors)

    def test_validate_video_valid(self):
        """Passes valid slide_plan with 6 scenes."""
        from engine.script_writer import _validate_video
        script = {
            "totalDurationTarget": 90,
            "scenes": [
                {
                    "id": 1, "narration": "90% of people...",
                    "visual_strategy": {"layout": "dramatic_number"},
                },
            ] + [
                {
                    "id": i, "narration": f"Point {i}",
                    "visual_strategy": {"layout": "card_list"},
                }
                for i in range(2, 6)
            ] + [
                {
                    "id": 6, "narration": "Subscribe now",
                    "visual_strategy": {"layout": "brand_closing"},
                }
            ],
        }
        errors = _validate_video(script)
        assert errors == []

    def test_validate_video_scene_count(self):
        """Rejects video scene count outside 5–8."""
        from engine.script_writer import _validate_video
        script = {
            "totalDurationTarget": 60,
            "scenes": [
                {"id": i, "narration": f"s{i}", "visual_strategy": {"layout": "card_list"}}
                for i in range(1, 3)
            ],
        }
        errors = _validate_video(script)
        assert any("Scene count" in e for e in errors)

    def test_generate_script_streaming(self):
        """generate_script calls LLM with streaming and parses JSON."""
        import engine.script_writer as sw
        from engine.script_writer import LLMProvider

        valid_script = (
            '{"title": "AI Tips", '
            '"totalDurationTarget": 90, '
            '"scenes": ['
            '{"id": 1, "type": "hook", "narration": "90% dung sai nha.", '
            '"durationSec": 8, "props": {}, "visual_strategy": {"layout": "dramatic_number", "background": {"type": "gradient", "query": ""}, "data_viz": {"type": "none", "data": []}, "emphasis_element": "number_countup"}}, '
            '{"id": 2, "type": "card", "narration": "Tui thay ket qua khac.", '
            '"durationSec": 10, "props": {}, "visual_strategy": {"layout": "card_list", "background": {"type": "gradient", "query": ""}, "data_viz": {"type": "none", "data": []}, "emphasis_element": "typewriter"}}, '
            '{"id": 3, "type": "card", "narration": "Buoc 1 ne.", '
            '"durationSec": 10, "props": {}, "visual_strategy": {"layout": "timeline_steps", "background": {"type": "gradient", "query": ""}, "data_viz": {"type": "none", "data": []}, "emphasis_element": "fade_in"}}, '
            '{"id": 4, "type": "card", "narration": "Buoc 2 ne.", '
            '"durationSec": 10, "props": {}, "visual_strategy": {"layout": "timeline_steps", "background": {"type": "gradient", "query": ""}, "data_viz": {"type": "none", "data": []}, "emphasis_element": "fade_in"}}, '
            '{"id": 5, "type": "card", "narration": "Buoc 3 ne.", '
            '"durationSec": 10, "props": {}, "visual_strategy": {"layout": "timeline_steps", "background": {"type": "gradient", "query": ""}, "data_viz": {"type": "none", "data": []}, "emphasis_element": "fade_in"}}, '
            '{"id": 6, "type": "cta", "narration": "Dang ky kenh nha.", '
            '"durationSec": 8, "props": {}, "visual_strategy": {"layout": "brand_closing", "background": {"type": "gradient", "query": ""}, "data_viz": {"type": "none", "data": []}, "emphasis_element": "fade_in"}}'
            ']}'
        )
        mock_client = MagicMock()
        mock_stream = MagicMock()
        chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content=c))])
            for c in [valid_script[i:i+20] for i in range(0, len(valid_script), 20)]
        ]
        mock_stream.__iter__ = lambda s: iter(chunks)
        mock_client.chat.completions.create.return_value = mock_stream
        mock_provider = LLMProvider(name="mock-provider", client=mock_client, model="test")

        with patch.object(sw, "_build_llm_chain", return_value=[mock_provider]), \
             patch.object(sw, "_load_system_prompt", return_value="You are Thong Phan."):
            result = sw.generate_script(
                topic="5 AI tips",
                channel="ai",
                target_factory="video",
                brain2_context="",
                forge_context="",
            )

        assert result["title"] == "AI Tips"
        assert "scenes" in result
        assert len(result["scenes"]) == 6

    def test_generate_script_validation_fails(self):
        """Raises ValueError when LLM output fails schema validation."""
        import engine.script_writer as sw
        from engine.script_writer import LLMProvider

        mock_client = MagicMock()
        mock_stream = MagicMock()
        chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(
                content='{"title": "Bad", "scenes": [{"id": 1}]}'
            ))])
        ]
        mock_stream.__iter__ = lambda s: iter(chunks)
        mock_client.chat.completions.create.return_value = mock_stream
        mock_provider = LLMProvider(name="mock", client=mock_client, model="test")

        with patch.object(sw, "_build_llm_chain", return_value=[mock_provider]), \
             patch.object(sw, "_load_system_prompt", return_value="Prompt"):
            with pytest.raises(ValueError) as exc:
                sw.generate_script(
                    topic="Test",
                    channel="ai",
                    target_factory="video",
                )
            assert "Schema validation errors" in str(exc.value)

    def test_call_llm_with_fallback_vertex_fail_then_openrouter_succeeds(self):
        """First provider fails → fallback to second provider → success."""
        import engine.script_writer as sw
        from engine.script_writer import LLMProvider

        valid_json = '{"title": "Fallback OK", "scenes": []}'

        mock_client1 = MagicMock()
        mock_client1.chat.completions.create.side_effect = Exception("502 Bad Gateway")

        mock_client2 = MagicMock()
        mock_stream2 = MagicMock()
        chunks2 = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content=c))])
            for c in [valid_json[i:i+10] for i in range(0, len(valid_json), 10)]
        ]
        mock_stream2.__iter__ = lambda s: iter(chunks2)
        mock_client2.chat.completions.create.return_value = mock_stream2

        provider1 = LLMProvider(name="vertex-key", client=mock_client1, model="claude-4")
        provider2 = LLMProvider(name="openrouter", client=mock_client2, model="anthropic/claude-4")

        with patch.object(sw, "_build_llm_chain", return_value=[provider1, provider2]):
            result = sw._call_llm_with_fallback(
                system_prompt="sys", user_prompt="user"
            )
            assert "Fallback OK" in result

    def test_call_llm_with_fallback_all_fail_raises(self):
        """All providers fail → RuntimeError with error list."""
        import engine.script_writer as sw
        from engine.script_writer import LLMProvider

        mock_client1 = MagicMock()
        mock_client1.chat.completions.create.side_effect = Exception("502 Bad Gateway")
        mock_client2 = MagicMock()
        mock_client2.chat.completions.create.side_effect = Exception("401 Unauthorized")

        p1 = LLMProvider(name="vertex-key", client=mock_client1, model="claude")
        p2 = LLMProvider(name="openrouter", client=mock_client2, model="claude")

        with patch.object(sw, "_build_llm_chain", return_value=[p1, p2]):
            with pytest.raises(RuntimeError) as exc:
                sw._call_llm_with_fallback(system_prompt="sys", user_prompt="user")
            assert "All LLM providers failed" in str(exc.value)
            assert "502" in str(exc.value)
            assert "401" in str(exc.value)

    def test_build_llm_chain(self):
        """_build_llm_chain returns providers when keys available."""
        import engine.script_writer as sw
        import importlib
        importlib.reload(sw)

        with patch.object(sw, "VERTEX_API_KEY", "vk"), \
             patch.object(sw, "VERTEX_BASE_URL", "https://vx.com"), \
             patch.object(sw, "MODEL_WRITER", "claude-4"), \
             patch.object(sw, "OPENROUTER_API_KEY", "or-key"), \
             patch.object(sw, "OPENROUTER_API_KEY", "or-key"), \
             patch.object(sw, "MODEL_WRITER_OPENROUTER", "anthropic/claude-4"), \
             patch.object(sw, "OPENAI_API_KEY", ""):

            chain = sw._build_llm_chain()

        assert len(chain) == 2
        assert chain[0].name == "vertex-key"
        assert chain[1].name == "openrouter"

    def test_generate_script_signature_has_qa_feedback(self):
        """AC-37: generate_script accepts qa_feedback parameter."""
        import inspect
        from engine.script_writer import generate_script
        sig = inspect.signature(generate_script)
        assert "qa_feedback" in sig.parameters
