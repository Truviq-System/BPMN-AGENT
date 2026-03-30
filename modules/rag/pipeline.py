from .pinecone_client import query_similar

SCORE_THRESHOLD = 0.65

# ── Section headers ──────────────────────────────────────────────────────────
_SECTION_HEADERS = {
    "bpmn":        "### Retrieved BPMN Patterns (Authoritative Reference)",
    "test":        "### Retrieved Test Patterns (QA Best Practices)",
    "springboot":  "### Retrieved Implementation Patterns (Official Architecture)",
    "react":       "### Retrieved Frontend Patterns (UI Best Practices)",
}

# ── Improved semantic queries (documentation aligned) ─────────────────────────
_SEMANTIC_QUERIES = {
    "test":       "Camunda BPMN testing strategy unit integration testing Zeebe process validation best practices",
    "springboot": "Camunda 8 official documentation Zeebe job worker Spring Boot configuration best practices",
    "react":      "React frontend best practices workflow forms validation API integration TanStack Query patterns",
}

# ── Re-ranking (similarity + authority) ───────────────────────────────────────
def rerank_hits(hits: list[dict]) -> list[dict]:
    for h in hits:
        similarity = h.get("score", 0)
        authority  = h.get("confidence", 0.5)

        # Weighted scoring (tune if needed)
        h["final_score"] = (0.6 * similarity) + (0.4 * authority)

    return sorted(hits, key=lambda x: x["final_score"], reverse=True)

# ── Context formatter ─────────────────────────────────────────────────────────
def _format_context(hits: list[dict], context_type: str) -> str:
    if not hits:
        return ""

    header = _SECTION_HEADERS.get(context_type, "### Retrieved Patterns")

    lines = [
        header,
        "Use ONLY these patterns as authoritative references. Do NOT invent alternatives.",
        ""
    ]

    for i, h in enumerate(hits, 1):
        lines.append(
            f"**{i}. {h.get('pattern_name','Pattern')}** "
            f"(source: {h.get('source','unknown')}, score: {round(h.get('final_score',0),2)})"
        )

        if h.get("description"):
            lines.append(f"_{h['description']}_")

        if h.get("content"):
            lines.append(h["content"])

        if h.get("tags"):
            lines.append(f"Tags: {h['tags']}")

        lines.append("")

    return "\n".join(lines)

# ── Main RAG pipeline ─────────────────────────────────────────────────────────
def run(content: str, context_type: str = "bpmn") -> tuple[str, dict]:
    meta = {
        "rag_used":     False,
        "context_type": context_type,
        "reasoning":    "Retrieve authoritative best-practice documentation.",
        "chunks_found": 0,
        "chunks_used":  0,
        "search_query": None,
    }

    # ── Step 1: Query selection ──────────────────────────────────────────────
    query_text = _SEMANTIC_QUERIES.get(context_type, content)
    meta["search_query"] = query_text

    try:
        print(f"[RAG/{context_type}] Querying Pinecone: {query_text[:100]}")

        hits = query_similar(
            query_text,
            doc_type=context_type,
            top_k=8,
        )

        meta["chunks_found"] = len(hits)

        # ── Step 2: Threshold filter ─────────────────────────────────────────
        hits = [h for h in hits if h.get("score", 0) >= SCORE_THRESHOLD]

        # ── Step 3: Re-ranking ───────────────────────────────────────────────
        hits = rerank_hits(hits)

        # Keep top results only (token control)
        hits = hits[:3]

        meta["chunks_used"] = len(hits)

        print(f"[RAG/{context_type}] {meta['chunks_found']} → {meta['chunks_used']} after filtering")

        if not hits:
            print(f"[RAG/{context_type}] No strong matches — fallback to generation.")
            return "", meta

    except Exception as e:
        print(f"[RAG/{context_type}] Error: {e}")
        meta["reasoning"] += f" (retrieval failed: {e})"
        return "", meta

    # ── Step 5: Format context ──────────────────────────────────────────────
    context = _format_context(hits, context_type)
    meta["rag_used"] = True

    print(f"[RAG/{context_type}] Context ready ({len(context)} chars)")
    return context, meta
