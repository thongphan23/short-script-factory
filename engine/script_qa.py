"""
Script QA — scores generated scripts across 5 dimensions.

AUTO-FAIL: ":" or "—" in any narration field → score = 0, passed = False.
PASS threshold: ≥ 75/100.
"""
import logging
import json
import re
import httpx
from engine.config import VERTEX_API_KEY, VERTEX_BASE_URL, MODEL_QA, SUPABASE_ANON_KEY, SUPABASE_URL

_logger = logging.getLogger(__name__)

# ── QA Result dataclass ──────────────────────────────────────────────────────
class QAResult:
    """
    Attributes:
        score:      Integer 0–100.
        details:    Dict with per-dimension breakdown.
        feedback:   List of human-readable improvement suggestions.
        passed:     True if score >= 75 and not auto-failed.
    """
    def __init__(
        self,
        score: int,
        details: dict,
        feedback: list[str],
        passed: bool,
    ):
        self.score = score
        self.details = details
        self.feedback = feedback
        self.passed = passed

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "details": self.details,
            "feedback": self.feedback,
            "passed": self.passed,
        }


# ── AUTO-FAIL checks ─────────────────────────────────────────────────────────
_COLON_RE = re.compile(r":")
_EMDASH_RE = re.compile(r"\u2014")   # em-dash "—"


def _collect_narrations(script: dict) -> list[tuple[int, str]]:
    """Yield (scene_id, narration_text) for all scenes in any schema."""
    scenes = script.get("scenes") or []
    results = []
    for scene in scenes:
        sid = scene.get("id", 0)
        narration = scene.get("narration", "")
        if narration:
            results.append((sid, narration))
    return results


def _auto_fail(script: dict) -> bool:
    """
    Check narration fields for AUTO-FAIL violations.
    Returns True if auto-fail triggered (":" or "—" in narration).
    """
    for _, narration in _collect_narrations(script):
        if _EMDASH_RE.search(narration):
            _logger.warning("AUTO-FAIL: em-dash found in scene %s", narration[:60])
            return True
        if _COLON_RE.search(narration):
            _logger.warning("AUTO-FAIL: colon found in scene %s", narration[:60])
            return True
    return False


# ── Scoring helpers ──────────────────────────────────────────────────────────
def _score_structure(script: dict, target_factory: str) -> tuple[int, str]:
    """Dimension 1: JSON schema valid + scene count + duration in range."""
    score = 0
    notes: list[str] = []

    scenes = script.get("scenes") or []
    if target_factory == "doodle":
        ok = 15 <= len(scenes) <= 35
        score += 10 if ok else 0
        notes.append(f"{'OK' if ok else 'FAIL'}: {len(scenes)} scenes (want 15–35)")

        dur = script.get("metadata", {}).get("estimated_duration_sec", 0)
        ok2 = 120 <= dur <= 280
        score += 10 if ok2 else 0
        notes.append(f"{'OK' if ok2 else 'FAIL'}: duration {dur}s (want 120–280s)")
    else:  # video
        ok = 5 <= len(scenes) <= 8
        score += 10 if ok else 0
        notes.append(f"{'OK' if ok else 'FAIL'}: {len(scenes)} scenes (want 5–8)")

        dur = script.get("totalDurationTarget", 0)
        ok2 = 60 <= dur <= 120
        score += 10 if ok2 else 0
        notes.append(f"{'OK' if ok2 else 'FAIL'}: duration {dur}s (want 60–120s)")

    return score, "; ".join(notes)


def _score_voice_dna(script: dict) -> tuple[int, list[str]]:
    """
    Dimension 2: Voice DNA compliance.
    +5 if uses "tui", +5 if uses "anh em", +5 if no ":", +5 if no em-dash.
    (Colons/em-dashes already caught by auto-fail so just flag here.)
    """
    score = 0
    narrations = [n for _, n in _collect_narrations(script)]
    full = " ".join(narrations)

    if "tui" in full.lower():
        score += 5
    if re.search(r"anh\s*em", full.lower()):
        score += 5
    # No ":" is already checked by auto-fail; just confirm
    has_colon = any(":" in n for n in narrations)
    if not has_colon:
        score += 5
    has_emdash = any(_EMDASH_RE.search(n) for n in narrations)
    if not has_emdash:
        score += 5

    return score, []


def _score_hook(script: dict) -> tuple[int, str]:
    """Dimension 3: Hook quality."""
    score = 0
    notes: list[str] = []

    scenes = script.get("scenes", [])
    if not scenes:
        return 0, "No scenes"

    first_narration = scenes[0].get("narration", "")
    word_count = len(first_narration.split())

    if word_count <= 25:
        score += 7
        notes.append(f"OK: first scene {word_count} words (≤25)")
    else:
        notes.append(f"TOO LONG: first scene {word_count} words (>25)")

    # Hook keywords / contrarian patterns
    full_text = json.dumps(script)
    strong_hooks = [
        "sai", "90", "99", "100", "phần trăm", "%",
        "không hề", "chưa", "tại sao", "làm thế nào",
        "tui phát hiện", "tui khám phá", "anh em ơi",
    ]
    hook_hits = sum(1 for kw in strong_hooks if kw.lower() in full_text.lower())
    if hook_hits >= 1:
        score += 7
        notes.append(f"OK: {hook_hits} strong hook signals found")
    else:
        notes.append("WEAK: no strong hook signals")

    # Not generic
    generic_words = ["bài viết", "bạn nên", "bạn cần", "rất hay", "cực kỳ"]
    is_generic = any(gw.lower() in full_text.lower() for gw in generic_words)
    score += 6 if not is_generic else 0
    notes.append(f"{'NOT GENERIC' if not is_generic else 'GENERIC'}")

    return score, " | ".join(notes)


def _score_content_depth(script: dict, brain2_context: str = "") -> tuple[int, str]:
    """Dimension 4: Content depth + actionable steps."""
    score = 0
    notes: list[str] = []

    full_text = json.dumps(script)

    has_reference = bool(brain2_context) or any(
        kw in full_text.lower()
        for kw in ["ví dụ", "thực tế", "case study", "cụ thể", "tui", "thật"]
    )
    if has_reference:
        score += 7
        notes.append("OK: specific reference or context found")
    else:
        notes.append("WEAK: generic content without examples")

    is_actionable = any(
        kw in full_text.lower()
        for kw in ["bước", "cách", "làm thế", "áp dụng", "thực hiện", "action"]
    )
    score += 7 if is_actionable else 0
    notes.append(f"{'OK' if is_actionable else 'MISSING'}: actionable steps")

    not_generic = not any(
        gw in full_text.lower() for gw in ["lý thuyết", "theo như", "nói chung"]
    )
    score += 6 if not_generic else 0
    notes.append(f"{'SPECIFIC' if not_generic else 'TOO THEORETICAL'}")

    return score, " | ".join(notes)


def _score_format_compliance(script: dict, target_factory: str) -> tuple[int, list[str]]:
    """Dimension 5: Format-specific rules."""
    score = 0
    errors: list[str] = []

    scenes = script.get("scenes", [])
    if not scenes:
        return 0, ["No scenes"]

    if target_factory == "doodle":
        # visual_prompt prefix check
        for i, scene in enumerate(scenes, 1):
            vp = scene.get("visual_prompt", "")
            if vp and not vp.startswith("minimalist white line art"):
                errors.append(f"Scene {i}: visual_prompt bad prefix")
            else:
                score += 2  # up to 10 pts for visual prompts

        # motion_prompt check (verb + subject)
        for i, scene in enumerate(scenes, 1):
            mp = scene.get("motion_prompt", "")
            if not mp:
                errors.append(f"Scene {i}: missing motion_prompt")
            elif not re.search(r"^\w+\s+\w+", mp):
                errors.append(f"Scene {i}: motion_prompt lacks verb+subject")
            else:
                score += (5 * len(scenes) // 35)  # scale

        score = min(score, 15)  # cap at 15

    else:  # video
        # First scene: dramatic_number layout
        first_layout = scenes[0].get("visual_strategy", {}).get("layout", "")
        if first_layout == "dramatic_number":
            score += 5
        else:
            errors.append(f"Scene 1: layout should be 'dramatic_number', got '{first_layout}'")

        # Last scene: brand_closing
        last_layout = scenes[-1].get("visual_strategy", {}).get("layout", "")
        if last_layout == "brand_closing":
            score += 5
        else:
            errors.append(f"Scene {len(scenes)}: layout should be 'brand_closing', got '{last_layout}'")

        # Valid layouts check
        valid_layouts = {
            "dramatic_number", "card_list", "pareto_chart",
            "bar_compare", "quote_card", "timeline_steps",
            "split_contrast", "icon_grid", "brand_closing",
        }
        for i, scene in enumerate(scenes, 1):
            layout = scene.get("visual_strategy", {}).get("layout", "")
            if layout and layout not in valid_layouts:
                errors.append(f"Scene {i}: invalid layout '{layout}'")

        score = min(score, 10)

    return score, errors


# ── LLM-assisted QA (Gemini flash for detailed scoring) ─────────────────────
def _llm_assist_score(script: dict, channel: str, target_factory: str) -> dict:
    """
    Use Gemini flash to give a second opinion on scoring.
    Falls back gracefully on error.
    """
    system = (
        "Bạn là chuyên gia QA cho kịch bản video Thông Phan.\n"
        "Chấm điểm script JSON theo 5 tiêu chí:\n"
        "1. Structure (schema đúng, số scenes hợp lệ, duration đúng)\n"
        "2. Voice DNA (dùng tui, anh em, không :, không —)\n"
        "3. Hook Quality (scene đầu ≤25 từ, có yếu tố gây sốc/câu hỏi)\n"
        "4. Content Depth (có ví dụ cụ thể, actionable)\n"
        "5. Format Compliance (đúng format doodle/video)\n"
        "Trả lời PURE JSON: {\"score\": N, \"feedback\": [\"...\", ...]}"
    )
    user = (
        f"Channel: {channel}\n"
        f"Target: {target_factory}\n"
        f"Script:\n{json.dumps(script, ensure_ascii=False, indent=2)[:3000]}"
    )
    try:
        resp = httpx.post(
            f"{VERTEX_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {VERTEX_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL_QA,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": 512,
            },
            timeout=20.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            # Extract JSON from response
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group(0))
    except Exception as exc:
        _logger.warning("LLM assist QA failed: %s", exc)
    return {}


# ── Main API ─────────────────────────────────────────────────────────────────
def score_script(
    script: dict,
    channel: str,
    target_factory: str,
    brain2_context: str = "",
) -> QAResult:
    """
    Score a generated script across 5 dimensions.

    Args:
        script:          Parsed script dict.
        channel:         'ai', 'viral', or 'tuhoc'.
        target_factory:  'doodle' or 'video'.
        brain2_context:  Optional Brain2 context string (for depth scoring).

    Returns:
        QAResult with score (0–100), details, feedback, and passed flag.
    """
    _logger.info("score_script: channel=%r target=%r", channel, target_factory)

    # ── AUTO-FAIL ───────────────────────────────────────────────────────────
    if _auto_fail(script):
        result = QAResult(
            score=0,
            details={"auto_fail": "':' or '—' found in narration"},
            feedback=[
                "AUTO-FAIL: Dấu ':' hoặc '—' trong narration. Sửa ngay."
            ],
            passed=False,
        )
        _logger.warning("Script auto-failed: score=0")
        return result

    # ── Dimension scoring ───────────────────────────────────────────────────
    s_struct, s_struct_n = _score_structure(script, target_factory)
    s_voice, s_voice_n = _score_voice_dna(script)
    s_hook, s_hook_n = _score_hook(script)
    s_depth, s_depth_n = _score_content_depth(script, brain2_context)
    s_format, s_format_e = _score_format_compliance(script, target_factory)

    total = s_struct + s_voice + s_hook + s_depth + s_format

    details = {
        "structure": {"score": s_struct, "notes": s_struct_n},
        "voice_dna": {"score": s_voice, "notes": s_voice_n},
        "hook": {"score": s_hook, "notes": s_hook_n},
        "depth": {"score": s_depth, "notes": s_depth_n},
        "format": {"score": s_format, "errors": s_format_e},
    }

    feedback: list[str] = []
    if total < 75:
        feedback.append(f"Tổng điểm {total}/100 — dưới ngưỡng 75. Cần cải thiện.")
    if s_voice < 15:
        feedback.append("Voice DNA yếu: kiểm tra 'tui', 'anh em', dấu ':', '—'.")
    if s_hook < 10:
        feedback.append("Hook yếu: scene đầu cần ≤25 từ + yếu tố gây sốc.")
    if s_depth < 10:
        feedback.append("Nội dung nông: thêm ví dụ cụ thể và actionable steps.")
    if s_format < 10:
        feedback.append("Format chưa đúng: kiểm tra visual_prompt prefix hoặc layout cuối.")
    if feedback and not s_format_e:
        pass  # no additional LLM feedback needed

    # ── LLM assist ──────────────────────────────────────────────────────────
    llm_feedback = _llm_assist_score(script, channel, target_factory)
    if llm_feedback:
        llm_score = llm_feedback.get("score") or 0
        if abs(llm_score - total) > 20:
            avg = (total + llm_score) // 2
            total = avg
            feedback.extend(llm_feedback.get("feedback", []))

    passed = total >= 75

    _logger.info(
        "score_script: total=%d (%s) | s=%d v=%d h=%d d=%d f=%d",
        total, "PASS" if passed else "FAIL",
        s_struct, s_voice, s_hook, s_depth, s_format,
    )
    return QAResult(score=total, details=details, feedback=feedback, passed=passed)
