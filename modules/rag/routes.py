"""
RAG management routes
  GET  /api/rag/status          — index stats
  POST /api/rag/index           — add documents (bpmn / test / springboot)
  POST /api/rag/search          — ad-hoc similarity search filtered by doc_type
"""
from flask import Blueprint, request, jsonify

from .pinecone_client import upsert_documents, query_similar, index_stats

rag_bp = Blueprint("rag", __name__, url_prefix="/api/rag")

VALID_DOC_TYPES = {"bpmn", "test", "springboot"}


@rag_bp.route('/status', methods=['GET'])
def status():
    """Return current Pinecone index stats."""
    return jsonify(index_stats())


@rag_bp.route('/index', methods=['POST'])
def index_documents():
    """
    Index one or more knowledge documents into Pinecone.

    Body (single or list):
    {
      "documents": [
        {
          "doc_type":     "bpmn" | "test" | "springboot",   ← REQUIRED
          "pattern_name": "Loan Approval Workflow",
          "domain":       "banking",
          "description":  "Multi-step loan review with credit scoring ...",
          "content":      "Best practices / code snippets / test templates ...",
          "tags":         ["loan", "approval", "banking"]    ← optional
        },
        ...
      ]
    }

    doc_type meanings:
      "bpmn"        — BPMN process patterns, enriches BPMN generation
      "test"        — QA templates / test strategies, enriches test case generation
      "springboot"  — Implementation patterns, enriches Spring Boot prompt generation
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    docs = data if isinstance(data, list) else data.get("documents", [data])
    if not docs:
        return jsonify({"error": "No documents provided"}), 400

    errors = []
    for i, doc in enumerate(docs):
        if not doc.get("description", "").strip():
            errors.append(f"Document {i}: missing 'description'")
        dt = doc.get("doc_type", "")
        if dt not in VALID_DOC_TYPES:
            errors.append(
                f"Document {i}: 'doc_type' must be one of {sorted(VALID_DOC_TYPES)}, got '{dt}'"
            )
    if errors:
        return jsonify({"error": errors}), 400

    try:
        count = upsert_documents(docs)
        return jsonify({"success": True, "indexed": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@rag_bp.route('/search', methods=['POST'])
def search():

    data     = request.get_json() or {}
    query    = data.get("query", "").strip()
    doc_type = data.get("doc_type", "bpmn")
    top_k    = int(data.get("top_k", 4))

    if not query:
        return jsonify({"error": "No query provided"}), 400
    if doc_type not in VALID_DOC_TYPES:
        return jsonify({"error": f"doc_type must be one of {sorted(VALID_DOC_TYPES)}"}), 400

    try:
        hits = query_similar(query, doc_type=doc_type, top_k=top_k)
        return jsonify({"success": True, "doc_type": doc_type, "results": hits})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
