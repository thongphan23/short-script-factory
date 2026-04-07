"""
Forge Engine integration — reads data from shared Supabase project.
Queries content_queue, forge_articles, daily_insights (read-only).
"""
import logging
from datetime import date
from supabase import Client
from engine.supabase_client import get_client

_logger = logging.getLogger(__name__)


def get_forge_suggestions(channel: str, limit: int = 10) -> list[dict]:
    """
    Fetch top scored content_queue entries for a given channel.

    Args:
        channel: Content type — 'ai', 'viral', or 'tuhoc'.
        limit: Max number of topics to return.

    Returns:
        List of dicts with keys: id, suggested_topic, suggested_hook,
        brain2_concepts, total_score.
    """
    client: Client = get_client()
    result = (
        client.table("content_queue")
        .select("id, suggested_topic, suggested_hook, brain2_concepts, total_score")
        .eq("status", "queued")
        .eq("content_type", channel)
        .order("total_score", desc=True)
        .limit(limit)
        .execute()
    )
    items = result.data or []
    _logger.info("Forge suggestions for channel=%r → %d items", channel, len(items))
    return items


def get_forge_article_context(article_ids: list) -> str:
    """
    Fetch context from forge_articles by their IDs.

    Args:
        article_ids: List of UUID strings.

    Returns:
        Concatenated "title_vi — summary_vi" strings, or empty string.
    """
    if not article_ids:
        return ""

    client: Client = get_client()
    result = (
        client.table("forge_articles")
        .select("title_vi, summary_vi, source_category")
        .in_("id", article_ids)
        .execute()
    )
    lines = []
    for row in (result.data or []):
        title = row.get("title_vi") or ""
        summary = row.get("summary_vi") or ""
        if title or summary:
            lines.append(f"## {title}\n{summary}")
    ctx = "\n\n".join(lines)
    _logger.info("Forge article context: %d chars from %d articles", len(ctx), len(article_ids))
    return ctx


def get_trending_insights() -> dict | None:
    """
    Fetch today's daily_insights row.

    Returns:
        Dict with highlight_summary, key_trends, etc., or None if not found.
    """
    client: Client = get_client()
    today = date.today().isoformat()
    result = (
        client.table("daily_insights")
        .select("*")
        .eq("insight_date", today)
        .single()
        .execute()
    )
    if result.data:
        _logger.info("Trending insights found for %s", today)
        return result.data
    _logger.info("No trending insights for %s", today)
    return None
