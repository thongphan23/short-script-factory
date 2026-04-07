"""
Dispatcher — routes approved scripts to Video Factory or Doodle Factory.

dispatch_to_video_factory():
  → INSERT into tpe_videos (status='approved')
  → Video Factory Worker picks it up automatically

dispatch_to_doodle_factory():
  → Write script JSON to output/scripts/{slug}_{channel}.json
  → (Future: trigger factory run.py via subprocess)

dispatch():
  → Read script from tpe_scripts by ID
  → Route based on target_factory
  → Update tpe_scripts + tpe_script_topics status
"""
import json
import logging
import re
import uuid
from pathlib import Path
from datetime import datetime, timezone
from supabase import Client
from engine.supabase_client import get_client
from engine.config import OUTPUT_SCRIPTS_DIR

_logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert topic string to safe filesystem slug."""
    # Remove Vietnamese diacritics approximation
    slug = text.lower()
    slug = re.sub(r"[^\w\s]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = slug[:80].strip("-")
    return slug or "script"


# ── Insert into Video Factory queue ─────────────────────────────────────────
def dispatch_to_video_factory(
    script_id: uuid.UUID,
    script_json: dict,
    topic: str,
    channel: str,
) -> uuid.UUID:
    """
    Insert a new row into tpe_videos so Video Factory Worker processes it.

    Args:
        script_id:    Original tpe_scripts.id.
        script_json: Parsed slide_plan dict.
        topic:        Video topic string.
        channel:      Content channel.

    Returns:
        UUID of the newly created tpe_videos row.
    """
    client: Client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    row = {
        "topic": topic,
        "channel": channel,
        "script_json": script_json,
        "structure": script_json.get("scenes", []),
        "status": "approved",
        "source": "script_factory",
        "source_script_id": str(script_id),
        "created_at": now,
        "updated_at": now,
    }

    result = client.table("tpe_videos").insert(row).execute()
    if not result.data:
        raise RuntimeError("Failed to insert into tpe_videos")

    video_id = result.data[0]["id"]
    _logger.info(
        "dispatch_to_video_factory: script=%s → tpe_videos.id=%s",
        script_id, video_id,
    )
    return uuid.UUID(video_id)


# ── Write to Doodle Factory output ───────────────────────────────────────────
def dispatch_to_doodle_factory(
    script_id: uuid.UUID,
    script_json: dict,
    channel: str,
) -> Path:
    """
    Write script JSON to output/scripts/ for Doodle Factory to pick up.

    Args:
        script_id:    Original tpe_scripts.id.
        script_json:  Parsed doodle_script dict.
        channel:      Content channel.

    Returns:
        Path to the written file.
    """
    OUTPUT_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    topic_slug = _slugify(script_json.get("metadata", {}).get("topic", "") or str(script_id))
    filename = f"{topic_slug}_{channel}_{script_id}.json"
    filepath = OUTPUT_SCRIPTS_DIR / filename

    # Add metadata
    out = {
        "source": "short_script_factory",
        "source_script_id": str(script_id),
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        **script_json,
    }

    filepath.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _logger.info("dispatch_to_doodle_factory: wrote %s (%d bytes)", filepath, filepath.stat().st_size)
    return filepath


# ── Main dispatch ────────────────────────────────────────────────────────────
def dispatch(script_id: uuid.UUID) -> str:
    """
    Full dispatch flow:
      1. Read script from tpe_scripts
      2. Route to appropriate factory
      3. Update tpe_scripts: status='dispatched', dispatched_to_*
      4. Update tpe_script_topics: status='dispatched'

    Returns:
        Human-readable summary of dispatch result.

    Raises:
        ValueError: If script not found or already dispatched.
    """
    client: Client = get_client()

    # ── Read script ──────────────────────────────────────────────────────────
    result = client.table("tpe_scripts").select("*").eq("id", str(script_id)).execute()
    if not result.data:
        raise ValueError(f"Script not found: {script_id}")

    script_row = result.data[0]
    status = script_row["status"]
    if status == "dispatched":
        raise ValueError(f"Script already dispatched: {script_id}")

    script_json: dict = script_row["script_json"]
    target_factory = script_row["target_factory"]
    channel = script_row["channel"]
    topic_id = script_row.get("topic_id")

    # ── Route ─────────────────────────────────────────────────────────────────
    if target_factory == "video":
        video_uuid = dispatch_to_video_factory(script_id, script_json, script_row.get("topic", ""), channel)
        dispatched_ref = str(video_uuid)
    else:
        filepath = dispatch_to_doodle_factory(script_id, script_json, channel)
        dispatched_ref = str(filepath)

    now = datetime.now(timezone.utc)

    # ── Update tpe_scripts ──────────────────────────────────────────────────
    client.table("tpe_scripts").update({
        "status": "dispatched",
        "dispatched_to_table": "tpe_videos" if target_factory == "video" else "file",
        "dispatched_to_id": dispatched_ref,
        "dispatched_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }).eq("id", str(script_id)).execute()

    # ── Update tpe_script_topics ────────────────────────────────────────────
    if topic_id:
        client.table("tpe_script_topics").update({
            "status": "dispatched",
            "updated_at": now.isoformat(),
        }).eq("id", topic_id).execute()

    _logger.info("dispatch complete: script=%s → %s", script_id, dispatched_ref)
    return (
        f"Dispatched script {script_id} to {target_factory} "
        f"(ref: {dispatched_ref[:40]}...)"
    )
