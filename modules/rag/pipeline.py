from .pinecone_client import query_similar

SCORE_THRESHOLD = 0.68   # minimum cosine similarity to rectly.
# For test / springboot: input is raw XML which embeds poorly, so use a fixed
# intent-based query that maps well to the stored best-practice documents.include a hit

# ── Section headers injected into the prompt per context type ─────────────────
_SECTION_HEADERS = {
    "bpmn":        "### Retrieved BPMN Patterns (use as domain reference)",
    "test":        "### Retrieved Test Patterns (use as QA best-practice reference)",
    "springboot":  "### Retrieved Implementation Patterns (use as architecture reference)",
    "react":       "### Retrieved Frontend Patterns (use as React/UI best-practice reference)",
}

# ── Semantic queries per context type ─────────────────────────────────────────
# For bpmn: user description is already semantic — use it di
_SEMANTIC_QUERIES = {
    "test":       "Camunda BPMN process test case generation flow testing validation best practices",
    "springboot": "Camunda 8 Spring Boot implementation job worker Zeebe client configuration setup",
    "react":      "React frontend Camunda process user task forms CRUD dashboard TanStack Query Axios REST API integration",
}


# ── Context formatter ─────────────────────────────────────────────────────────

def _format_context(hits: list[dict], context_type: str) -> str:
    """Format Pinecone hits into a prompt-friendly block."""
    if not hits:
        return ""

    header = _SECTION_HEADERS.get(context_type, "### Retrieved Patterns")
    lines  = [header, ""]

    for i, h in enumerate(hits, 1):
        lines.append(
            f"**{i}. {h['pattern_name']}**  "
            f"(domain: {h['domain']}, relevance: {h['score']})"
        )
        lines.append(f"_{h['description']}_")
        if h.get("content"):
            lines.append(h["content"])
        if h.get("tags"):
            lines.append(f"Tags: {h['tags']}")
        lines.append("")   # blank line between items

    return "\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────

def run(content: str, context_type: str = "bpmn") -> tuple[str, dict]:
    """
    Run the RAG pipeline — always retrieves from Pinecone on every query.

    Parameters
    ----------
    content      : str — user description (for bpmn) OR BPMN XML (for test/springboot)
    context_type : str — "bpmn" | "test" | "springboot"

    Returns
    -------
    context : str   — augmentation block to inject into the generation prompt
    meta    : dict  — pipeline metadata for logging / frontend display
    """
    meta = {
        "rag_used":     False,
        "context_type": context_type,
        "reasoning":    "Always retrieve best-practice material.",
        "chunks_found": 0,
        "chunks_used":  0,
        "search_query": None,
    }

    # For test/springboot the input is BPMN XML — use a fixed semantic intent
    # query so the embedding model retrieves the most relevant best-practice
    # documents. For bpmn the user's plain description is used directly.
    query_text = _SEMANTIC_QUERIES.get(context_type, content)
    meta["search_query"] = query_text

    # ── Step 1: Query Pinecone via semantic embeddings — always runs ──────────
    try:
        print(f"[RAG/{context_type}] Querying Pinecone (doc_type={context_type}): "
              f"'{query_text[:120]}'")
        hits = query_similar(
            query_text,
            doc_type=context_type,
            top_k=5,
        )
        meta["chunks_found"] = len(hits)

        hits = [h for h in hits if h["score"] >= SCORE_THRESHOLD]
        meta["chunks_used"] = len(hits)

        print(f"[RAG/{context_type}] {meta['chunks_found']} hits → "
              f"{meta['chunks_used']} above threshold {SCORE_THRESHOLD}")

        if not hits:
            print(f"[RAG/{context_type}] No patterns above threshold — generating directly.")
            return "", meta

    except Exception as e:
        print(f"[RAG/{context_type}] Pinecone query failed: {e} — fallback to direct.")
        meta["reasoning"] += f" (retrieval failed: {e})"
        return "", meta

    # ── Step 2: Format context block ──────────────────────────────────────────
    context = _format_context(hits, context_type)
    meta["rag_used"] = True
    print(f"[RAG/{context_type}] Context built ({len(context)} chars).")
    return context, meta
