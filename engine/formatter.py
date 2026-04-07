"""
Script formatter — pretty-print a script JSON for human review.
"""
from __future__ import annotations


def format_script_for_review(script: dict, target_factory: str) -> str:
    """
    Format script JSON into a human-readable review block.

    Args:
        script: Script dict from generate_script().
        target_factory: 'doodle' or 'video'.

    Returns:
        Formatted multi-line string for console output.
    """
    lines: list[str] = []

    if target_factory == "doodle":
        meta = script.get("metadata", {})
        scenes = script.get("scenes", [])
        duration = meta.get("estimated_duration_sec", 0)
        topic = meta.get("topic", "Untitled")
        lines.append(f"📝 {topic}")
        lines.append(f"⏱  {duration}s  |  🎬 {len(scenes)} scenes")
        lines.append("")

        for scene in scenes:
            sid = scene.get("id", "?")
            dur = scene.get("duration_sec", 0)
            narration = scene.get("narration", "")
            visual = scene.get("visual_prompt", "")
            motion = scene.get("motion_prompt", "")
            lines.append(f"[Scene {sid}] ({dur}s)")
            lines.append(f"  🎤 {narration}")
            if visual:
                lines.append(f"  🎨 {visual[:80]}...")
            if motion:
                lines.append(f"  🎬 {motion}")
            lines.append("")

    else:  # video
        title = script.get("title", "Untitled")
        total = script.get("totalDurationTarget", 0)
        scenes = script.get("scenes", [])
        lines.append(f"📝 {title}")
        lines.append(f"⏱  {total}s  |  🎬 {len(scenes)} scenes")
        lines.append("")

        for scene in scenes:
            sid = scene.get("id", "?")
            stype = scene.get("type", "")
            layout = scene.get("visual_strategy", {}).get("layout", "")
            dur = scene.get("durationSec", 0)
            narration = scene.get("narration", "")
            lines.append(f"[Scene {sid}] {stype} | {layout} | {dur}s")
            lines.append(f"  🎤 {narration}")
            lines.append("")

    # Full narration at bottom
    full_narration = script.get("full_narration", "")
    if full_narration:
        lines.append("───── FULL NARRATION ─────")
        lines.append(full_narration)

    return "\n".join(lines)
