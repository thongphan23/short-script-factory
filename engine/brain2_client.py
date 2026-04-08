"""
Brain2 vault search via direct psycopg2 + multi-provider embeddings.

Embedding provider priority (when EMBEDDING_PROVIDER=auto):
  1. Vertex-Key proxy  — fast, already used for LLM calls
  2. OpenAI direct    — if OPENAI_API_KEY set
  3. OpenRouter      — last resort (key may be revoked)

Graceful degradation: when ALL providers fail → search_vault() returns [],
get_context_for_topic() returns "". Script generation continues without Brain2 context.

Credentials sourced from engine.config → engine.db — never hardcoded.
"""
import logging
import httpx
from engine.config import (
    EMBEDDING_PROVIDER,
    OPENAI_API_KEY,
    OPENROUTER_API_KEY,
    VERTEX_API_KEY,
    VERTEX_BASE_URL,
)
from engine.db import get_pg_conn

_logger = logging.getLogger(__name__)


# ── Embedding providers ────────────────────────────────────────────────────────

def _embed_via_vertex(text: str) -> list[float]:
    """Embed via Vertex-Key proxy (OpenAI-compatible /embeddings endpoint)."""
    r = httpx.post(
        f"{VERTEX_BASE_URL}/embeddings",
        headers={
            "Authorization": f"Bearer {VERTEX_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": "text-embedding-3-small", "input": text},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def _embed_via_openai(text: str) -> list[float]:
    """Embed via direct OpenAI API (if user has OPENAI_API_KEY)."""
    r = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": "text-embedding-3-small", "input": text},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def _embed_via_openrouter(text: str) -> list[float]:
    """Embed via OpenRouter (may fail if key revoked)."""
    r = httpx.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": "openai/text-embedding-3-small", "input": text},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def _build_provider_chain() -> list[tuple[str, callable]]:
    """
    Build ordered list of (name, provider_func) based on EMBEDDING_PROVIDER setting.

    When EMBEDDING_PROVIDER=auto: try all available providers in order of reliability.
    When explicit: use only that provider.
    """
    mode = EMBEDDING_PROVIDER.strip().lower()
    chain: list[tuple[str, callable]] = []

    if mode in ("auto", "vertex"):
        chain.append(("vertex", _embed_via_vertex))

    if mode in ("auto", "openai") and OPENAI_API_KEY:
        chain.append(("openai", _embed_via_openai))

    if mode in ("auto", "openrouter") and OPENROUTER_API_KEY:
        chain.append(("openrouter", _embed_via_openrouter))

    # Deduplicate in case mode=auto and user set same key twice
    seen = set()
    deduped = []
    for name, fn in chain:
        if name not in seen:
            seen.add(name)
            deduped.append((name, fn))

    return deduped


def _get_embedding(text: str) -> list[float]:
    """
    Try embedding providers in order until one succeeds.

    Priority (EMBEDDING_PROVIDER=auto):
      1. Vertex-Key  — fast, already warm
      2. OpenAI      — if OPENAI_API_KEY set
      3. OpenRouter  — last resort

    Raises RuntimeError if ALL providers fail.
    """
    chain = _build_provider_chain()
    if not chain:
        raise RuntimeError("No embedding provider configured (check .env)")

    errors: list[str] = []
    for name, provider_fn in chain:
        try:
            vector = provider_fn(text)
            _logger.debug("Embedding via %s: %ddim", name, len(vector))
            return vector
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            _logger.warning("Embedding provider %s failed: %s", name, exc)

    raise RuntimeError(f"All embedding providers failed: {'; '.join(errors)}")


# ── Core search ───────────────────────────────────────────────────────────────
def search_vault(query: str, match_count: int = 5) -> list[dict]:
    """
    Perform semantic search against Brain2 vault chunks.

    Uses multi-provider embedding + direct psycopg2 for pgvector search.
    Cosine similarity = 1 - (<=> operator).

    Graceful degradation: returns [] on any failure (no crash).

    Args:
        query:       Text query to search for.
        match_count: Number of top matches to return (default 5).

    Returns:
        List of dicts with keys: title, content, similarity.
        Returns empty list on failure.
    """
    # ── Step 1: Get embedding (with fallback) ──────────────────────────────
    try:
        embedding = _get_embedding(query)
    except RuntimeError as exc:
        _logger.warning(
            "All embedding providers offline — scripts will lack Brain2 context. "
            "Configure EMBEDDING_PROVIDER in .env. Error: %s",
            exc,
        )
        return []

    # ── Step 2: pgvector search ────────────────────────────────────────────
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
