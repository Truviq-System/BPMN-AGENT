
import uuid
from pinecone import Pinecone

# ── Config ────────────────────────────────────────────────────────────────────
PINECONE_API_KEY = "pcsk_7Xg1GY_AWnoGBm9ChbQyGxpZ8Bg11TaeycQ8fXNaL3SXRdHDAgpjhoRPrbGBMhbeEX1SiT"
PINECONE_REGION  = "us-east-1"
INDEX_NAME       = "bpmngenrator"
EMBED_MODEL      = "multilingual-e5-large"
EMBED_DIM        = 1024
NAMESPACE        = "bpmn"
# ─────────────────────────────────────────────────────────────────────────────

_pc    = None
_index = None


def _client() -> Pinecone:
    global _pc
    if _pc is None:
        _pc = Pinecone(api_key=PINECONE_API_KEY)
    return _pc


def _get_index():
    global _index
    if _index is not None:
        return _index

    pc = _client()
    print(f"[Pinecone] Using existing index '{INDEX_NAME}'")

    _index = pc.Index(INDEX_NAME)
    return _index


# ── Public helpers ────────────────────────────────────────────────────────────

def embed(texts: list[str], input_type: str = "passage") -> list[list[float]]:
    """Return embedding vectors for the given texts."""
    pc = _client()
    result = pc.inference.embed(
        model=EMBED_MODEL,
        inputs=texts,
        parameters={"input_type": input_type, "truncate": "END"},
    )
    return [r["values"] for r in result]


def upsert_documents(documents: list[dict]) -> int:

    if not documents:
        return 0

    texts          = [d["description"] for d in documents]
    vectors_values = embed(texts, input_type="passage")

    vectors = []
    for doc, values in zip(documents, vectors_values):
        vectors.append({
            "id": doc.get("id") or uuid.uuid4().hex,
            "values": values,
            "metadata": {
                "doc_type":     doc.get("doc_type", "bpmn"),
                "pattern_name": doc.get("pattern_name", ""),
                "domain":       doc.get("domain", "general"),
                "description":  doc.get("description", ""),
                "content":      (doc.get("content") or "")[:400],  # 400 chars is enough; saves retrieval tokens
                "tags":         ",".join(doc.get("tags") or []),
            },
        })

    idx = _get_index()
    idx.upsert(vectors=vectors, namespace=NAMESPACE)
    print(f"[Pinecone] Upserted {len(vectors)} vectors (doc_type spread: "
          f"{set(d.get('doc_type','?') for d in documents)})")
    return len(vectors)


def query_similar(
    query_text: str,
    doc_type: str,
    top_k: int = 5,
) -> list[dict]:
    """Return top_k most similar documents filtered by doc_type."""
    query_vec = embed([query_text], input_type="query")[0]
    idx = _get_index()

    results = idx.query(
        vector=query_vec,
        top_k=top_k,
        namespace=NAMESPACE,
        include_metadata=True,
        filter={"doc_type": {"$eq": doc_type}},
    )

    hits = []
    for match in results.get("matches", []):
        meta = match.get("metadata", {})
        hits.append({
            "id":           match["id"],
            "score":        round(match["score"], 4),
            "doc_type":     meta.get("doc_type", ""),
            "pattern_name": meta.get("pattern_name", ""),
            "domain":       meta.get("domain", ""),
            "description":  meta.get("description", ""),
            "content":      meta.get("content", ""),
            "tags":         meta.get("tags", ""),
        })
    return hits


def index_stats() -> dict:
    """Return basic stats about the index."""
    try:
        idx   = _get_index()
        stats = idx.describe_index_stats()
        ns    = stats.get("namespaces", {}).get(NAMESPACE, {})
        return {
            "index":           INDEX_NAME,
            "total_vectors":   stats.get("total_vector_count", 0),
            "namespace_count": ns.get("vector_count", 0),
            "dimension":       stats.get("dimension", EMBED_DIM),
        }
    except Exception as e:
        return {"error": str(e)}
