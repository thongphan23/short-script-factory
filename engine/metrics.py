"""
Metrics tracking — records generation stats to tpe_settings table.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

_logger = logging.getLogger(__name__)


def record_generation(
    topic_id: str,
    script_id: str,
    channel: str,
    target: str,
    qa_score: int,
    passed: bool,
    duration_sec: float,
    revision: int = 0,
) -> None:
    """
    Record a generation event to the tpe_settings metrics blob.

    Appends a JSON entry to the 'metrics:generations' key in tpe_settings.
    """
    try:
        from engine.supabase_client import get_client
        client = get_client()

        # Fetch existing metrics
        row = (
            client.table("tpe_settings")
            .select("value")
            .eq("key", "metrics:generations")
            .maybe_single()
            .execute()
        )

        import json
        existing: list[dict] = []
        if row and row.data:
            try:
                existing = json.loads(row.data[0].get("value", "[]"))
            except Exception:
                existing = []

        entry = {
            "topic_id": str(topic_id),
            "script_id": str(script_id),
            "channel": channel,
            "target": target,
            "qa_score": qa_score,
            "passed": passed,
            "duration_sec": round(duration_sec, 1),
            "revision": revision,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        existing.append(entry)

        # Upsert
        client.table("tpe_settings").upsert({
            "key": "metrics:generations",
            "value": json.dumps(existing),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, onConflict="key").execute()

        _logger.info("Recorded generation metric: qa_score=%d passed=%s", qa_score, passed)
    except Exception as exc:
        _logger.warning("Failed to record metrics: %s", exc)


def get_stats_summary() -> dict:
    """
    Return a summary dict of generation statistics.

    Returns:
        dict with keys: total, avg_qa, pass_rate, by_channel, by_target.
    """
    try:
        from engine.supabase_client import get_client
        import json
        client = get_client()

        row = (
            client.table("tpe_settings")
            .select("value")
            .eq("key", "metrics:generations")
            .maybe_single()
            .execute()
        )

        if not row or not row.data:
            return {
                "total": 0,
                "avg_qa": 0.0,
                "pass_rate": 0.0,
                "by_channel": {},
                "by_target": {},
            }

        raw = row.data[0].get("value", "[]")
        generations: list[dict] = json.loads(raw)

        total = len(generations)
        if total == 0:
            return {
                "total": 0,
                "avg_qa": 0.0,
                "pass_rate": 0.0,
                "by_channel": {},
                "by_target": {},
            }

        scores = [g["qa_score"] for g in generations if g.get("qa_score", 0) > 0]
        avg_qa = round(sum(scores) / len(scores), 1) if scores else 0.0
        passed = sum(1 for g in generations if g.get("passed"))
        pass_rate = round(passed / total, 3) if total else 0.0

        by_channel: dict[str, dict] = {}
        for g in generations:
            ch = g.get("channel", "unknown")
            if ch not in by_channel:
                by_channel[ch] = {"total": 0, "passed": 0, "avg_qa": 0.0}
            by_channel[ch]["total"] += 1
            if g.get("passed"):
                by_channel[ch]["passed"] += 1

        by_target: dict[str, dict] = {}
        for g in generations:
            tg = g.get("target", "unknown")
            if tg not in by_target:
                by_target[tg] = {"total": 0, "passed": 0}
            by_target[tg]["total"] += 1
            if g.get("passed"):
                by_target[tg]["passed"] += 1

        return {
            "total": total,
            "avg_qa": avg_qa,
            "pass_rate": pass_rate,
            "by_channel": by_channel,
            "by_target": by_target,
        }
    except Exception as exc:
        _logger.warning("Failed to get stats summary: %s", exc)
        return {
            "total": 0,
            "avg_qa": 0.0,
            "pass_rate": 0.0,
            "by_channel": {},
            "by_target": {},
        }
