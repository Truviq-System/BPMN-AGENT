from .pinecone_client import query_similar

SCORE_THRESHOLD = 0.65
TOP_K           = 5   # fetch 5 from Pinecone, keep top 3 after re-ranking

# Fixed semantic queries — more precise than passing raw user content
_SEMANTIC_QUERIES = {
    "test":       "Camunda BPMN testing strategy unit integration testing Zeebe process validation best practices",
    "springboot": "Camunda 8 Zeebe job worker Spring Boot configuration best practices official documentation",
    "react":      "React workflow frontend forms validation API integration TanStack Query patterns",
}


def _rerank(hits: list[dict]) -> list[dict]:
    for h in hits:
        h["final_score"] = 0.6 * h.get("score", 0) + 0.4 * h.get("confidence", 0.5)
    return sorted(hits, key=lambda x: x["final_score"], reverse=True)


def _format_context(hits: list[dict]) -> str:
    """Compact format — one line per pattern with name, score, description, content.
    Strips verbose markdown headers to reduce injected tokens."""
    lines = []
    for i, h in enumerate(hits, 1):
        name    = h.get("pattern_name", "Pattern")
        score   = round(h.get("final_score", 0), 2)
        desc    = h.get("description", "").strip()
        content = (h.get("content", "") or "").strip()[:400]   # cap at 400 chars (was 800)
        parts   = [f"{i}. {name} ({score})"]
        if desc:    parts.append(desc)
        if content: parts.append(content)
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def run(content: str, context_type: str = "bpmn") -> tuple[str, dict]:
    meta = {
        "rag_used":     False,
        "context_type": context_type,
        "chunks_found": 0,
        "chunks_used":  0,
        "search_query": None,
    }

    query_text = _SEMANTIC_QUERIES.get(context_type, content[:500])
    meta["search_query"] = query_text

    try:
        print(f"[RAG/{context_type}] query: {query_text[:80]}")
        hits = query_similar(query_text, doc_type=context_type, top_k=TOP_K)
        meta["chunks_found"] = len(hits)

        hits = [h for h in hits if h.get("score", 0) >= SCORE_THRESHOLD]
        hits = _rerank(hits)[:3]   # keep top 3 after re-ranking
        meta["chunks_used"] = len(hits)

        print(f"[RAG/{context_type}] {meta['chunks_found']} found → {meta['chunks_used']} used")

        if not hits:
            return "", meta

    except Exception as e:
        print(f"[RAG/{context_type}] Error: {e}")
        return "", meta

    context = _format_context(hits)
    meta["rag_used"] = True
    print(f"[RAG/{context_type}] context: {len(context)} chars")
    return context, meta
