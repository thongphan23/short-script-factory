#!/usr/bin/env python3
"""
Short Script Factory — Worker Daemon

Polls tpe_script_topics WHERE status='queued' AND auto_mode=true
every POLL_INTERVAL seconds.

For each queued topic:
  1. status → 'generating' (FOR UPDATE SKIP LOCKED)
  2. Get brain2 context
  3. Get forge context (if source_ref)
  4. generate_script()
  5. Insert into tpe_scripts (status='draft')
  6. score_script()
  7. If QA >= 75: topic status='approved', script status='qa_pass'
  8. If QA < 75 AND revision_count < 3: retry with feedback
  9. If QA < 75 AND revision_count >= 3: topic='error', script='error'
  10. If auto_mode AND QA pass: auto-dispatch

Graceful shutdown: SIGTERM/SIGINT → stop polling, finish current item.
"""
from __future__ import annotations

import logging
import os
import signal
import time
import uuid
from datetime import datetime, timezone

from engine.config import SUPABASE_URL, SUPABASE_SERVICE_KEY  # noqa: E402
from engine.db import get_pg_conn  # noqa: E402

_logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
POLL_INTERVAL: int = int(os.getenv("WORKER_POLL_INTERVAL", "30"))
MAX_REVISIONS: int = 3


# ── Supabase helpers ──────────────────────────────────────────────────────────
def _supabase_client():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# ── Pick next queued topic (atomic) ──────────────────────────────────────────
def _pick_topic(conn) -> dict | None:
    """
    Pick next queued topic using FOR UPDATE SKIP LOCKED.
    Returns topic dict or None.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, topic, source, source_ref, channel, target_factory,
               brain2_context, forge_context, auto_mode
        FROM tpe_script_topics
        WHERE status = 'queued'
          AND auto_mode = true
        ORDER BY priority DESC, created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
        """,
    )
    row = cur.fetchone()
    if not row:
        return None
    cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))


# ── Single-topic processor ───────────────────────────────────────────────────
def process_topic(topic: dict, dry_run: bool = False) -> bool:
    """
    Process one topic: generate → QA → optionally dispatch.

    Returns True on success, False on failure.
    """
    topic_id = topic["id"]
    topic_name = topic["topic"][:80]

    _logger.info("Processing topic [%s]: %s", topic_id, topic_name)

    if dry_run:
        _logger.info("[DRY RUN] Would generate script for: %s", topic_name)
        return True

    from engine.script_writer import generate_script
    from engine.script_qa import score_script
    from engine.dispatcher import dispatch as _dispatch  # noqa: F401 — for testability

    # ── Brain2 context ──────────────────────────────────────────────────────
    brain2_ctx = ""
    try:
        from engine.brain2_client import get_context_for_topic
        brain2_ctx = get_context_for_topic(topic["topic"])
        _logger.info("Brain2 context: %d chars", len(brain2_ctx))
    except Exception as exc:
        _logger.warning("Brain2 RAG failed: %s", exc)

    # ── QA feedback from previous attempt (for retry) ─────────────────────
    qa_feedback: list[str] = []
    prev_qa_feedback = topic.get("prev_qa_feedback")
    if prev_qa_feedback:
        qa_feedback = prev_qa_feedback if isinstance(prev_qa_feedback, list) else []
        _logger.info("Retrying with %d QA feedback items", len(qa_feedback))
        for fb in qa_feedback:
            _logger.debug("  → %s", fb)

    # ── Forge context ──────────────────────────────────────────────────────
    forge_ctx = ""
    if topic.get("source_ref"):
        try:
            from engine.forge_client import get_forge_article_context
            forge_ctx = get_forge_article_context([topic["source_ref"]])
        except Exception as exc:
            _logger.warning("Forge context failed: %s", exc)

    # ── Generate ────────────────────────────────────────────────────────────
    try:
        script_json = generate_script(
            topic=topic["topic"],
            channel=topic["channel"],
            target_factory=topic["target_factory"],
            brain2_context=brain2_ctx,
            forge_context=forge_ctx,
            qa_feedback=qa_feedback,
        )
    except Exception as exc:
        _logger.error("Script generation failed: %s", exc)
        _update_topic_status(topic_id, conn=None, status="error")
        return False

    # ── Insert script + QA ──────────────────────────────────────────────────
    client = _supabase_client()
    revision_count = 0

    script_row = client.table("tpe_scripts").insert({
        "topic_id": str(topic_id),
        "script_json": script_json,
        "target_factory": topic["target_factory"],
        "channel": topic["channel"],
        "status": "draft",
        "revision_count": revision_count,
    }).execute().data[0]
    script_id = script_row["id"]

    qa_result = score_script(
        script_json,
        channel=topic["channel"],
        target_factory=topic["target_factory"],
        brain2_context=brain2_ctx,
    )

    # ── Update based on QA ──────────────────────────────────────────────────
    if qa_result.passed:
        _logger.info(
            "Topic [%s] QA PASS: %d/100 → approving",
            topic_id, qa_result.score,
        )
        client.table("tpe_scripts").update({
            "qa_score": qa_result.score,
            "qa_details": qa_result.details,
            "qa_feedback": qa_result.feedback,
            "status": "qa_pass",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", script_id).execute()

        client.table("tpe_script_topics").update({
            "status": "approved",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", str(topic_id)).execute()

        # ── Auto-dispatch ───────────────────────────────────────────────────
        if topic.get("auto_mode"):
            try:
                _logger.info("Auto-dispatching script %s", script_id)
                _dispatch(uuid.UUID(script_id))
            except Exception as exc:
                _logger.error("Auto-dispatch failed: %s", exc)

    elif revision_count < MAX_REVISIONS:
        _logger.info(
            "Topic [%s] QA FAIL (%d/100), revision %d < %d — will retry",
            topic_id, qa_result.score, revision_count + 1, MAX_REVISIONS,
        )
        client.table("tpe_scripts").update({
            "qa_score": qa_result.score,
            "qa_details": qa_result.details,
            "qa_feedback": qa_result.feedback,
            "revision_count": revision_count + 1,
            "status": "draft",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", script_id).execute()
        client.table("tpe_script_topics").update({
            "status": "queued",  # back to queue for retry
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", str(topic_id)).execute()
    else:
        _logger.error(
            "Topic [%s] QA FAIL (%d/100), max revisions reached → error",
            topic_id, qa_result.score,
        )
        client.table("tpe_scripts").update({
            "qa_score": qa_result.score,
            "qa_details": qa_result.details,
            "qa_feedback": qa_result.feedback,
            "status": "error",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", script_id).execute()
        client.table("tpe_script_topics").update({
            "status": "error",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", str(topic_id)).execute()

    return True


def _update_topic_status(topic_id: str, conn, status: str):
    if conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tpe_script_topics SET status=%s, updated_at=NOW() WHERE id=%s",
            (status, topic_id),
        )
        conn.commit()


# ── Heartbeat ────────────────────────────────────────────────────────────────
def _heartbeat(conn, worker_name: str = "default"):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tpe_settings (key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """,
        (f"worker_last_seen:{worker_name}", datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


# ── Daemon loop ──────────────────────────────────────────────────────────────
def run_daemon(once: bool = False, dry_run: bool = False) -> None:
    """Main polling loop. Runs until SIGTERM/SIGINT or --once."""
    _logger.info(
        "Worker starting: once=%s dry_run=%s poll_interval=%ds",
        once, dry_run, POLL_INTERVAL,
    )

    running = True

    def _signal_handler(signum, _frame):
        nonlocal running
        sig_name = signal.Signals(signum).name
        _logger.info("Received %s — graceful shutdown", sig_name)
        running = False

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    while running:
        conn = get_pg_conn()
        conn.autocommit = True
        processed = 0

        try:
            # Heartbeat
            _heartbeat(conn)

            # Pick and process next topic
            topic = _pick_topic(conn)
            if topic:
                try:
                    process_topic(topic, dry_run=dry_run)
                    processed += 1
                except Exception as exc:
                    _logger.error("process_topic failed: %s", exc)
                    # Roll back topic status on crash
                    try:
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE tpe_script_topics SET status='error', updated_at=NOW() WHERE id=%s",
                            (str(topic["id"]),),
                        )
                        conn.commit()
                    except Exception:
                        pass
            else:
                _logger.debug("No queued topics (poll_interval=%ds)", POLL_INTERVAL)

        finally:
            conn.close()

        if once or not running:
            break

        if processed == 0:
            time.sleep(POLL_INTERVAL)

    _logger.info("Worker stopped cleanly.")


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    p = argparse.ArgumentParser(description="Short Script Factory Worker")
    p.add_argument("--once", action="store_true", help="Run 1 cycle then exit")
    p.add_argument("--dry-run", action="store_true", help="Poll + log, don't execute")
    args = p.parse_args()

    if args.dry_run:
        args.once = True

    run_daemon(once=args.once, dry_run=args.dry_run)
