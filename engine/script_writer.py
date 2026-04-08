"""
Script Writer — generates video scripts via streaming LLM call.

CORE MODULE: reads voice-dna.md + script-formats.md specs at runtime.
Calls Vertex-Key LLM with streaming, parses JSON response, validates output.
Retry with exponential backoff on schema failures.
"""
import json
import logging
import re
import time
from pathlib import Path
from openai import OpenAI
from engine.config import (
    VERTEX_API_KEY,
    VERTEX_BASE_URL,
    MODEL_WRITER,
    PROJECT_ROOT,
)

_logger = logging.getLogger(__name__)

# ── Retry config ──────────────────────────────────────────────────────────────
MAX_LLM_RETRIES: int = 3
RETRY_DELAYS: list[float] = [2.0, 5.0, 10.0]  # seconds, exponential backoff

# ── LLM client (lazy init) ────────────────────────────────────────────────────
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=VERTEX_API_KEY, base_url=VERTEX_BASE_URL)
    return _client


# ── Prompt loader ────────────────────────────────────────────────────────────
def _load_system_prompt(channel: str, target_factory: str) -> str:
    """
    Load channel-specific system prompt.
    Falls back to 'ai' if channel file not found.
    Injects {target_factory} placeholder for format switching.
    """
    safe = channel.lower().strip()
    candidates = [
        PROJECT_ROOT / "prompts" / f"writer_system_{safe}.md",
        PROJECT_ROOT / "prompts" / "writer_system_ai.md",
    ]
    for path in candidates:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            # Inject target_factory into prompt body
            return content.replace("{target_factory}", target_factory)
    # Hardcoded fallback minimal prompt
    return (
        "Bạn là Thông Phan, viết kịch bản video tiếng Việt.\n"
        "Dùng 'tui', 'anh em'. Không dùng ':' hay '—' trong narration.\n"
        "{target_factory}"
    )


# ── JSON extraction ────────────────────────────────────────────────────────
def _extract_json(raw: str) -> dict:
    """
    Extract JSON object from LLM output.
    Handles ```json ... ``` code blocks and bare { ... }.
    Returns parsed dict or raises ValueError.
    """
    # Strip markdown code fences
    text = raw.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Fallback: find first { ... }
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        _logger.error("JSON parse failed: %s\nRaw: %r", exc, raw[:500])
        raise ValueError(f"Invalid JSON from LLM: {exc}") from exc


# ── Schema validation helpers ───────────────────────────────────────────────
def _validate_doodle(script: dict) -> list[str]:
    """Validate doodle_script schema. Returns list of error messages."""
    errors = []
    if "metadata" not in script:
        errors.append("Missing 'metadata'")
    if "scenes" not in script:
        errors.append("Missing 'scenes'")
    else:
        scenes = script["scenes"]
        if not (15 <= len(scenes) <= 35):
            errors.append(f"Scene count {len(scenes)} not in [15, 35]")
        for i, scene in enumerate(scenes, 1):
            if "narration" not in scene:
                errors.append(f"Scene {i}: missing 'narration'")
            if "visual_prompt" not in scene:
                errors.append(f"Scene {i}: missing 'visual_prompt'")
            vp = scene.get("visual_prompt", "")
            if vp and not vp.startswith("minimalist white line art"):
                errors.append(f"Scene {i}: visual_prompt must start with 'minimalist white line art...'")
    meta = script.get("metadata", {})
    dur = meta.get("estimated_duration_sec", 0)
    if not (120 <= dur <= 280):
        errors.append(f"Duration {dur}s not in [120, 280]")
    return errors


def _validate_video(script: dict) -> list[str]:
    """Validate slide_plan schema. Returns list of error messages."""
    errors = []
    if "scenes" not in script:
        errors.append("Missing 'scenes'")
    else:
        scenes = script["scenes"]
        if not (5 <= len(scenes) <= 8):
            errors.append(f"Scene count {len(scenes)} not in [5, 8]")
        for i, scene in enumerate(scenes, 1):
            if "narration" not in scene:
                errors.append(f"Scene {i}: missing 'narration'")
            vs = scene.get("visual_strategy", {})
            if not vs:
                errors.append(f"Scene {i}: missing 'visual_strategy'")
            else:
                layout = vs.get("layout", "")
                if not layout:
                    errors.append(f"Scene {i}: visual_strategy.layout is empty")
    total = script.get("totalDurationTarget", 0)
    if not (60 <= total <= 120):
        errors.append(f"totalDurationTarget {total}s not in [60, 120]")
    return errors


# ── Main API ────────────────────────────────────────────────────────────────
def generate_script(
    topic: str,
    channel: str,
    target_factory: str,
    brain2_context: str = "",
    forge_context: str = "",
    qa_feedback: list[str] | None = None,
) -> dict:
    """
    Generate a video script by calling the LLM with streaming.

    Args:
        topic: Video topic in Vietnamese.
        channel: Content channel ('ai', 'viral', 'tuhoc').
        target_factory: 'doodle' or 'video' (determines output format).
        brain2_context: Brain2 vault context string.
        forge_context: Forge Engine context string.
        qa_feedback: Optional QA feedback from previous attempt to inject into retry.

    Returns:
        Parsed script dict (doodle_script or slide_plan).

    Raises:
        ValueError: If JSON parse or schema validation fails.
    """
    system_prompt = _load_system_prompt(channel, target_factory)

    # ── Retry loop with exponential backoff ────────────────────────────────
    for attempt in range(MAX_LLM_RETRIES):
        user_parts = [f"# Topic\n{topic}"]
        if qa_feedback:
            user_parts.append("# QA Feedback (LẦN TRƯỚC BỊ FAIL, SỬA THEO ĐÂY)")
            for fb in qa_feedback:
                user_parts.append(f"- {fb}")
            user_parts.append("\nHÃY SỬA CÁC LỖI TRÊN. Output PURE JSON.")
        if brain2_context:
            user_parts.append(f"# Brain2 Context\n{brain2_context}")
        if forge_context:
            user_parts.append(f"# Forge Context\n{forge_context}")
        user_prompt = "\n\n".join(user_parts)

        client = _get_client()
        _logger.info(
            "generate_script: topic=%r channel=%r target=%r attempt=%d/%d",
            topic[:60], channel, target_factory, attempt + 1, MAX_LLM_RETRIES,
        )

        # ── Streaming LLM call (BẮT BUỘC — avoids CloudFlare 524) ──────
        try:
            stream = client.chat.completions.create(
                model=MODEL_WRITER,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=4096,
                stream=True,
            )

            chunks: list[str] = []
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    chunks.append(delta)

            full_text = "".join(chunks)
            _logger.info("LLM response: %d chars", len(full_text))

            # ── Parse JSON ───────────────────────────────────────────────
            script = _extract_json(full_text)

            # ── Validate schema ──────────────────────────────────────────
            if target_factory == "doodle":
                errors = _validate_doodle(script)
            else:
                errors = _validate_video(script)

            if errors:
                _logger.warning(
                    "Schema validation failed (attempt %d/%d): %s",
                    attempt + 1, MAX_LLM_RETRIES, errors,
                )
                if attempt < MAX_LLM_RETRIES - 1:
                    time.sleep(RETRY_DELAYS[attempt])
                    # Inject validation errors as next attempt's QA feedback
                    qa_feedback = [f"Schema error: {'; '.join(errors[:3])}"]
                    continue
                else:
                    raise ValueError(f"Schema validation errors: {errors}")

            _logger.info("Script generated: %d scenes", len(script.get("scenes", [])))
            return script

        except ValueError:
            # Re-raise schema errors (already handled above, or from _extract_json)
            raise
        except Exception as exc:
            _logger.warning(
                "LLM call failed (attempt %d/%d): %s",
                attempt + 1, MAX_LLM_RETRIES, exc,
            )
            if attempt < MAX_LLM_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
            else:
                _logger.error("All LLM attempts failed: %s", exc)
                raise RuntimeError(f"generate_script failed after {MAX_LLM_RETRIES} attempts: {exc}") from exc

    _logger.info("Script generated: %d scenes", len(script.get("scenes", [])))
    return script
