"""
Brain2 vault search — chỉ mục cục bộ (Ollama bge-m3), từ 2026-10-14.

Dùng chung cầu nối với MCP brain2-vault-search:
/Users/rio/Active/BRAIN2/vault-embedder/python/brain2_local.py
Không còn gọi Vertex/OpenAI/OpenRouter embeddings hay đọc bảng Supabase vault_embeddings
(bảng đó đứng yên từ 2026-08-20). Bản cũ xem git history.

Graceful degradation: Brain2 không truy xuất được → search_vault() trả [],
get_context_for_topic() trả "", và log cảnh báo BLOCKED để không bị nhầm là "không có kết quả".
"""
import logging
import os
import sys

sys.path.insert(0, os.environ.get("BRAIN2_LOCAL_DIR", "/Users/rio/Active/BRAIN2/vault-embedder/python"))
from brain2_local import Brain2Unavailable, search  # noqa: E402

_logger = logging.getLogger(__name__)
BACKEND = "local-bge-m3"


def search_vault(query: str, match_count: int = 5) -> list[dict]:
    """
    Semantic search against Brain2 vault chunks.

    Returns:
        List of dicts with keys: title, file_path, content, similarity. [] on failure.
    """
    try:
        rows = search(query, limit=match_count, min_similarity=0.20)
    except Brain2Unavailable as exc:
        _logger.warning("Brain2 BLOCKED — chạy tiếp không có Brain2: %s", exc)
        return []
    results = [
        {"title": r["title"], "file_path": r["file_path"], "content": r["content"], "similarity": round(r["similarity"], 4)}
        for r in rows
    ]
    _logger.info("Vault search: query=%r → %d matches", query, len(results))
    return results


def get_context_for_topic(topic: str) -> str:
    """
    Build a rich context string for a given topic by searching Brain2 vault.

    Returns:
        Concatenated context string (title + content of top chunks), or "" if nothing found.
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
