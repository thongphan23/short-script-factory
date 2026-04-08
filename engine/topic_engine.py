"""
Topic suggestion engine — combines Brain2 + Forge + trending.

suggest_topics(channel, count, source):
  "brain2"  → extract from Brain2 vault recent notes
  "forge"   → get from Forge Engine content_queue
  "mixed"   → combine both, dedupe by similarity, rank by novelty

No external imports from tpe-video-factory or doodle-factory.
"""
import logging
from engine.supabase_client import get_client

_logger = logging.getLogger(__name__)

# ── Channel → search queries for Brain2 ─────────────────────────────────────
_Brain2_QUERIES: dict[str, list[str]] = {
    "ai":     ["AI productivity tools", "ChatGPT tips tricks", "AI công cụ mới", "automation workflow"],
    "viral":  ["viral content trend", "social media psychology", "attention hooks", "emotional triggers"],
    "tuhoc":  ["personal development framework", "reading notes productivity", "mental models", "habit building"],
}


def suggest_topics(
    channel: str = "ai",
    count: int = 5,
    source: str = "mixed",
) -> list[dict]:
    """
    Return ranked topic suggestions from Brain2, Forge, or both.

    Args:
        channel: Content channel ('ai', 'viral', 'tuhoc').
        count:   Number of topics to return.
        source:  'brain2' | 'forge' | 'mixed'.

    Returns:
        List of dicts: [{suggested_topic, source, score, context_preview}, ...]
    """
    topics: list[dict] = []

    if source in ("brain2", "mixed"):
        try:
            topics.extend(_extract_from_brain2(channel, count))
        except Exception as exc:
            _logger.warning("Brain2 topic extraction failed: %s", exc)

    if source in ("forge", "mixed"):
        try:
            topics.extend(_extract_from_forge(channel, count))
        except Exception as exc:
            _logger.warning("Forge topic extraction failed: %s", exc)

    # Dedupe by topic similarity (case-insensitive exact match)
    topics = _dedupe_by_exact(topics)

    # Rank by novelty (not already in tpe_script_topics)
    topics = _rank_by_novelty(topics)

    return topics[:count]


# ── Brain2 extraction ────────────────────────────────────────────────────────
def _extract_from_brain2(channel: str, count: int) -> list[dict]:
    """Scan Brain2 vault for high-similarity chunks → topic titles."""
    from engine.brain2_client import search_vault

    queries = _Brain2_QUERIES.get(channel, _Brain2_QUERIES["ai"])
    results: list[dict] = []

    for q in queries:
        chunks = search_vault(q, match_count=3)
        for chunk in chunks:
            if not chunk.get("content"):
                continue
            title = chunk.get("title", "").strip()
            if not title or len(title) < 10:
                continue
            results.append({
                "suggested_topic": title,
                "source": "brain2",
                "score": round(chunk.get("similarity", 0) * 100, 1),
                "context_preview": chunk.get("content", "")[:200],
            })

    return results


# ── Forge extraction ──────────────────────────────────────────────────────────
def _extract_from_forge(channel: str, count: int) -> list[dict]:
    """Get topic suggestions from Forge Engine's content_queue."""
    from engine.forge_client import get_forge_suggestions

    suggestions = get_forge_suggestions(channel=channel, limit=count)
    results: list[dict] = []
    for s in suggestions:
        results.append({
            "suggested_topic": s.get("suggested_topic", ""),
            "source": "forge",
            "score": s.get("total_score", 0),
            "context_preview": s.get("suggested_hook", "")[:200],
        })
    return results


# ── Deduplication ─────────────────────────────────────────────────────────────
def _dedupe_by_exact(topics: list[dict]) -> list[dict]:
    """Remove exact duplicate topic names (case-insensitive)."""
    seen: set[str] = set()
    deduped: list[dict] = []
    for t in topics:
        key = t["suggested_topic"].lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(t)
    return deduped


# ── Novelty ranking ────────────────────────────────────────────────────────────
def _rank_by_novelty(topics: list[dict]) -> list[dict]:
    """Filter out topics already in tpe_script_topics (case-insensitive)."""
    client = get_client()
    existing = client.table("tpe_script_topics").select("topic").execute().data
    existing_lower = {r["topic"].lower().strip() for r in existing if r.get("topic")}

    return [t for t in topics if t["suggested_topic"].lower().strip() not in existing_lower]