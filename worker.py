#!/usr/bin/env python3
"""
Short Script Factory — Worker Daemon

Polls tpe_script_topics WHERE status='queued' AND auto_mode=true
every POLL_INTERVAL seconds.

For each queued topic:
  1. status → 'generating' (FOR UPDATE SKIP LOCKED)
  2. Get brain2 context
  3. Get forge context (if source_ref)
  4. generate_script() with exponential backoff retry
  5. Insert into tpe_scripts (status='draft')
  6. score_script()
  7. If QA >= 75: topic status='approved', script status='qa_pass'
  8. If QA < 75 AND revision_count < 3: retry with feedback
  9. If QA < 75 AND revision_count >= 3: topic='error', script='error' + dead letter
  10. If auto_mode AND QA pass: auto-dispatch

Graceful shutdown: SIGTERM/SIGINT → stop polling, finish current item.

Health endpoint: http://localhost:5176 (threaded HTTP server).
Rate limiting: MAX_PER_HOUR scripts per rolling hour window.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from engine.config import SUPABASE_URL, SUPABASE_SERVICE_KEY  # noqa: E402
from engine.db import get_pg_conn  # noqa: E402

_logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
POLL_INTERVAL: int = int(os.getenv("WORKER_POLL_INTERVAL", "30"))
MAX_REVISIONS: int = 3
MAX_PER_HOUR: int = int(os.getenv("WORKER_MAX_PER_HOUR", "10"))
HEALTH_PORT: int = int(os.getenv("WORKER_HEALTH_PORT", "5176"))

# Rolling rate limiter window (deque of timestamps)
_rate_window: deque = deque()
_rate_lock = threading.Lock()


# ── Rate limiting ──────────────────────────────────────────────────────────────
def _check_rate_limit() -> bool:
    """
    Returns True if under rate limit, False if limit exceeded.
    Uses rolling one-hour window.
    """
    now = time.time()
    cutoff = now - 3600

    with _rate_lock:
        # Expire old entries
        while _rate_window and _rate_window[0] < cutoff:
            _rate_window.popleft()

        if len(_rate_window) >= MAX_PER_HOUR:
            _logger.warning(
                "Rate limit reached: %d/%d per hour — sleeping %ds",
                len(_rate_window), MAX_PER_HOUR, POLL_INTERVAL,
            )
            return False

        _rate_window.append(now)
        return True


# ── Health endpoint ────────────────────────────────────────────────────────────
class _HealthHandler(BaseHTTPRequestHandler):
    """Lightweight health check endpoint on port 5176."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        payload = '{"status": "running"}\n'.encode()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass  # Suppress default logging


def _start_health_server(port: int = HEALTH_PORT) -> None:
    server = HTTPServer(("", port), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True, name="health-server")
    t.start()
    _logger.info("Health endpoint: http://localhost:%d/", port)


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
               brain2_context, forge_context, auto_mode,
               prev_qa_feedback
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


# ── Dead letter queue ─────────────────────────────────────────────────────────
def _record_dead_letter(script_id: str, error_msg: str, score: int) -> None:
    """
    Record fatal failure into script row's qa_feedback as dead letter entry.
    Writes FATAL prefix so future debugging can identify hard failures.
    """
    client = _supabase_client()
    client.table("tpe_scripts").update({
        "status": "error",
        "qa_score": score,
        "qa_feedback": [f"FATAL_DEAD_LETTER: {str(error_msg)[:200]}"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", script_id).execute()


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

    # ── Rate limit check ──────────────────────────────────────────────────
    if not _check_rate_limit():
        _logger.info("Rate limit active — topic [%s] deferred", topic_id)
        return False

    # ── Brain2 context ────────────────────────────────────────────────────
    brain2_ctx = ""
    try:
        from engine.brain2_client import get_context_for_topic
        brain2_ctx = get_context_for_topic(topic["topic"])
        _logger.info("Brain2 context: %d chars", len(brain2_ctx))
    except Exception as exc:
        _logger.warning("Brain2 RAG failed: %s", exc)

    # ── QA feedback from previous attempt (for retry) ────────────────────
    qa_feedback: list[str] = []
    prev_qa_feedback = topic.get("prev_qa_feedback")
    if prev_qa_feedback:
        qa_feedback = prev_qa_feedback if isinstance(prev_qa_feedback, list) else []
        _logger.info("Retrying with %d QA feedback items", len(qa_feedback))
        for fb in qa_feedback:
            _logger.debug("  → %s", fb)

    # ── Forge context ─────────────────────────────────────────────────────
    forge_ctx = ""
    if topic.get("source_ref"):
        try:
            from engine.forge_client import get_forge_article_context
            forge_ctx = get_forge_article_context([topic["source_ref"]])
        except Exception as exc:
            _logger.warning("Forge context failed: %s", exc)

    # ── Generate (with retry backoff handled inside) ───────────────────────
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
        _logger.error("Script generation failed after retries: %s", exc)
        client = _supabase_client()
        # Insert dead letter record
        dead_row = client.table("tpe_scripts").insert({
            "topic_id": str(topic_id),
            "script_json": {},
            "target_factory": topic["target_factory"],
            "channel": topic["channel"],
            "status": "error",
            "revision_count": 0,
        }).execute().data[0]
        script_id = dead_row["id"]
        _record_dead_letter(script_id, str(exc), score=0)
        client.table("tpe_script_topics").update({
            "status": "error",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", str(topic_id)).execute()
        return False

    # ── Insert script + QA ────────────────────────────────────────────────
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

    # ── Update based on QA ────────────────────────────────────────────────
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

        # ── Auto-dispatch ───────────────────────────────────────────────
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
            "Topic [%s] QA FAIL (%d/100), max revisions reached → dead letter",
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


# ── Heartbeat ───────────────────────────────────────────────────────────────
def _heartbeat(conn, worker_name: str = "default", processed: int = 0, errors: int = 0) -> None:
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """
        INSERT INTO tpe_settings (key, value, updated_at)
        VALUES
            (%s, %s, %s),
            (%s, %s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
        """,
        (
            f"worker_last_seen:{worker_name}", now, now,
            f"worker_stats:{worker_name}", f'{{"processed":{processed},"errors":{errors}}}', now,
        ),
    )
    conn.commit()


# ── Daemon loop ──────────────────────────────────────────────────────────────
def run_daemon(once: bool = False, dry_run: bool = False) -> None:
    """Main polling loop. Runs until SIGTERM/SIGINT or --once."""
    _logger.info(
        "Worker starting: once=%s dry_run=%s poll_interval=%ds max_per_hour=%d",
        once, dry_run, POLL_INTERVAL, MAX_PER_HOUR,
    )

    # Start health endpoint (non-blocking)
    _start_health_server(HEALTH_PORT)

    running = True

    def _signal_handler(signum, _frame):
        nonlocal running
        sig_name = signal.Signals(signum).name
        _logger.info("Received %s — graceful shutdown", sig_name)
        running = False

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    cycle_processed = 0
    cycle_errors = 0

    while running:
        conn = get_pg_conn()
        conn.autocommit = True

        try:
            # Heartbeat
            _heartbeat(conn, processed=cycle_processed, errors=cycle_errors)

            # Pick and process next topic
            topic = _pick_topic(conn)
            if topic:
                try:
                    ok = process_topic(topic, dry_run=dry_run)
                    if ok:
                        cycle_processed += 1
                    else:
                        cycle_errors += 1
                except Exception as exc:
                    _logger.error("process_topic crashed: %s", exc)
                    cycle_errors += 1
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

        if cycle_processed == 0 and cycle_errors == 0:
            time.sleep(POLL_INTERVAL)
        # Reset counters each cycle
        cycle_processed = 0
        cycle_errors = 0

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
