"""
Brain2 vault search via direct psycopg2 + OpenRouter embeddings.

Uses OpenRouter (text-embedding-3-small) → OpenAI-compatible.
Queries vault_embeddings with cosine similarity via direct PostgreSQL connection.
Credentials sourced from engine.config → engine.db — never hardcoded.
"""
import logging
import httpx
from engine.config import OPENROUTER_API_KEY
from engine.db import get_pg_conn

_logger = logging.getLogger(__name__)

# ── Embedding via OpenRouter ──────────────────────────────────────────────────
def _get_embedding(text: str) -> list[float]:
    """
    Get text embedding via OpenRouter (text-embedding-3-small).
    Returns 1536-dim vector.
    Raises httpx.HTTPStatusError on failure.
    """
    r = httpx.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "openai/text-embedding-3-small",
            "input": text,
        },
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


# ── Core search ───────────────────────────────────────────────────────────────
def search_vault(query: str, match_count: int = 5) -> list[dict]:
    """
    Perform semantic search against Brain2 vault chunks.

    Uses OpenRouter for embedding, direct psycopg2 for pgvector search.
    Cosine similarity = 1 - (<=> operator).

    Args:
        query:       Text query to search for.
        match_count: Number of top matches to return (default 5).

    Returns:
        List of dicts with keys: title, content, similarity.
        Returns empty list on failure.
    """
    if not OPENROUTER_API_KEY:
        _logger.warning("OPENROUTER_API_KEY not set — skipping vault search")
        return []

    try:
        embedding = _get_embedding(query)
    except Exception as exc:
        _logger.error("Failed to get embedding for query %r: %s", query, exc)
        return []

    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COALESCE(ve.metadata->>'title', ve.file_path, '') AS title,
                ve.file_path,
                ve.content,
                ROUND((1 - (ve.embedding <=> %(emb)s::vector))::numeric, 4)
                    AS cosine_similarity
            FROM vault_embeddings ve
            WHERE 1 - (ve.embedding <=> %(emb)s::vector) > 0.20
            ORDER BY ve.embedding <=> %(emb)s::vector
            LIMIT %(limit)s
            """,
            {"emb": embedding, "limit": match_count},
        )
        rows = cur.fetchall()
        results = [
            {
                "title": str(row[0]) if row[0] else "",
                "file_path": str(row[1]) if row[1] else "",
                "content": str(row[2]) if row[2] else "",
                "similarity": float(row[3]) if row[3] is not None else 0.0,
            }
            for row in rows
        ]
        _logger.info("Vault search: query=%r → %d matches", query, len(results))
        return results
    except Exception as exc:
        _logger.error("Vault search DB error: %s", exc)
        return []


def get_context_for_topic(topic: str) -> str:
    """
    Build a rich context string for a given topic by searching Brain2 vault.

    Args:
        topic: The video/script topic.

    Returns:
        Concatenated context string (title + content of top chunks),
        or empty string if nothing found.
    """
    chunks = search_vault(topic, match_count=5)
    if not chunks:
        _logger.info("No Brain2 context found for topic: %r", topic)
        return ""

    lines = []
    for chunk in chunks:
        title = chunk.get("title", "")
        content = chunk.get("content", "")
        if content:
            lines.append(f"## {title}\n{content[:600]}")
    ctx = "\n\n".join(lines)
    _logger.info("Brain2 context built: %d chars from %d chunks", len(ctx), len(chunks))
    return ctx
