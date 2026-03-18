"""
ingest_camunda_docs.py
======================
Clones the official Camunda docs repo and ingests all relevant Markdown / MDX
files into your Pinecone index so the BPMN Agent can retrieve domain-specific
patterns at generation time.

Usage
-----
    python ingest_camunda_docs.py                      # clone + ingest all
    python ingest_camunda_docs.py --skip-clone         # re-ingest already-cloned repo
    python ingest_camunda_docs.py --dry-run            # preview chunks, no upload
    python ingest_camunda_docs.py --doc-type bpmn      # only ingest bpmn docs
    python ingest_camunda_docs.py --limit 50           # ingest first N chunks (testing)

What gets ingested
------------------
  doc_type="bpmn"        — BPMN elements, process patterns, gateways, events, subprocesses
  doc_type="test"        — Testing, QA, process validation guides
  doc_type="springboot"  — Java/Spring Boot, Zeebe client, job workers, REST API

Each Markdown file is:
  1. Split into heading-anchored chunks (H2/H3 sections)
  2. Classified into a doc_type based on path + content keywords
  3. Cleaned of MDX/JSX tags, front-matter, and code fence noise
  4. Uploaded in batches of 50 to respect Pinecone rate limits
"""

import argparse
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

# ── Pinecone client (reuse project's existing module) ─────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from modules.rag.pinecone_client import upsert_documents

# ── Config ────────────────────────────────────────────────────────────────────
REPO_URL    = "https://github.com/camunda/camunda-docs.git"
CLONE_DIR   = Path("camunda-docs")
BATCH_SIZE  = 50          # vectors per Pinecone upsert call
MAX_CHUNK   = 750         # max chars stored in 'content' field
MIN_CHUNK   = 80          # skip chunks shorter than this (likely nav/TOC noise)
DEPTH       = 1           # git clone depth (shallow — saves ~2 GB)

# ── Paths inside the repo that are worth indexing ─────────────────────────────
INCLUDE_DIRS = [
    "docs/components/modeler",
    "docs/components/zeebe",
    "docs/components/best-practices",
    "docs/apis-tools",
    "docs/components/connectors",
    "docs/guides",
]

# ── Keyword-based doc_type classifier ─────────────────────────────────────────
# Each entry: (doc_type, path_keywords, content_keywords)
_CLASSIFIERS = [
    (
        "springboot",
        ["java", "spring", "client", "sdk", "worker", "rest-api", "apis-tools"],
        ["JobWorker", "ZeebeClient", "spring-zeebe", "job worker", "REST", "Java",
         "Maven", "Gradle", "@ZeebeWorker", "processInstanceKey"],
    ),
    (
        "test",
        ["test", "quality", "validation", "qa"],
        ["test case", "unit test", "integration test", "assertion", "mock",
         "verify", "quality assurance", "scenario"],
    ),
    (
        "bpmn",
        ["bpmn", "modeler", "process", "gateway", "event", "task", "subprocess",
         "best-practice", "connector", "zeebe"],
        ["BPMN", "startEvent", "endEvent", "gateway", "serviceTask", "userTask",
         "sequenceFlow", "subprocess", "pool", "lane", "message", "timer",
         "boundary", "collaboration", "process pattern"],
    ),
]

# ── Domain keyword map ─────────────────────────────────────────────────────────
_DOMAIN_MAP = {
    "banking":       ["loan", "credit", "bank", "payment", "financial", "account"],
    "hr":            ["employee", "onboarding", "leave", "payroll", "recruitment", "hr"],
    "logistics":     ["shipment", "delivery", "warehouse", "supply", "logistics", "order"],
    "insurance":     ["claim", "policy", "underwriting", "insurance", "premium"],
    "healthcare":    ["patient", "appointment", "diagnosis", "hospital", "medical"],
    "ecommerce":     ["cart", "checkout", "order", "refund", "product", "shop"],
    "government":    ["permit", "compliance", "regulation", "government", "public"],
}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Clone
# ─────────────────────────────────────────────────────────────────────────────

def clone_repo():
    if CLONE_DIR.exists():
        print(f"[clone] '{CLONE_DIR}' already exists — pulling latest changes...")
        result = subprocess.run(
            ["git", "-C", str(CLONE_DIR), "pull", "--ff-only"],
            capture_output=True, text=True
        )
        print(f"[clone] {result.stdout.strip() or result.stderr.strip()}")
    else:
        print(f"[clone] Cloning {REPO_URL} (shallow, depth={DEPTH})...")
        result = subprocess.run(
            ["git", "clone", "--depth", str(DEPTH), REPO_URL, str(CLONE_DIR)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"[clone] ERROR: {result.stderr}")
            sys.exit(1)
        print(f"[clone] Done.")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Collect files
# ─────────────────────────────────────────────────────────────────────────────

def collect_files() -> list[Path]:
    files = []
    for rel_dir in INCLUDE_DIRS:
        target = CLONE_DIR / rel_dir
        if not target.exists():
            print(f"[collect] Skipping missing dir: {target}")
            continue
        for path in target.rglob("*.md"):
            files.append(path)
        for path in target.rglob("*.mdx"):
            files.append(path)

    print(f"[collect] Found {len(files)} Markdown files across {len(INCLUDE_DIRS)} dirs.")
    return files


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Parse & chunk
# ─────────────────────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Strip MDX/JSX components, front-matter, HTML tags, and excessive whitespace."""
    # Remove YAML front-matter
    text = re.sub(r"^---[\s\S]*?---\n", "", text, count=1)
    # Remove import/export statements (MDX)
    text = re.sub(r"^(import|export)\s+.*$", "", text, flags=re.MULTILINE)
    # Remove JSX components  <ComponentName ... />  or  <ComponentName>...</ComponentName>
    text = re.sub(r"<[A-Z][A-Za-z]*[^>]*/?>", "", text)
    text = re.sub(r"</[A-Z][A-Za-z]*>", "", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove code fences (keep content, lose the ``` markers)
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_title(raw: str, path: Path) -> str:
    """Return the first H1/H2 heading, or fall back to filename."""
    m = re.search(r"^#{1,2}\s+(.+)$", raw, flags=re.MULTILINE)
    return m.group(1).strip() if m else path.stem.replace("-", " ").title()


def chunk_file(path: Path) -> list[dict]:
    """
    Split a Markdown file into H2/H3-anchored chunks.
    Returns a list of raw chunk dicts (not yet classified).
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[chunk] Cannot read {path}: {e}")
        return []

    file_title = _extract_title(raw, path)
    cleaned    = _clean_text(raw)

    # Split on H2 (##) or H3 (###) headings
    sections = re.split(r"\n(?=#{2,3} )", cleaned)

    chunks = []
    for sec in sections:
        sec = sec.strip()
        if len(sec) < MIN_CHUNK:
            continue

        # Heading of this section
        heading_match = re.match(r"^(#{2,3})\s+(.+)", sec)
        section_title = heading_match.group(2).strip() if heading_match else file_title

        # Body text (remove the heading line itself)
        body = re.sub(r"^#{2,3}\s+.+\n?", "", sec, count=1).strip()
        if len(body) < MIN_CHUNK:
            continue

        chunks.append({
            "_path":   str(path.relative_to(CLONE_DIR)),
            "_title":  f"{file_title} — {section_title}",
            "_body":   body[:MAX_CHUNK],
        })

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Classify
# ─────────────────────────────────────────────────────────────────────────────

def _classify_doc_type(path_str: str, body: str) -> str:
    path_lower = path_str.lower()
    body_lower = body.lower()

    scores = {"bpmn": 0, "test": 0, "springboot": 0}

    for doc_type, path_kws, content_kws in _CLASSIFIERS:
        for kw in path_kws:
            if kw in path_lower:
                scores[doc_type] += 2
        for kw in content_kws:
            if kw.lower() in body_lower:
                scores[doc_type] += 1

    best = max(scores, key=lambda k: scores[k])
    # If all scores are 0 (no matches at all), default to bpmn
    return best if scores[best] > 0 else "bpmn"


def _classify_domain(body: str) -> str:
    body_lower = body.lower()
    for domain, keywords in _DOMAIN_MAP.items():
        for kw in keywords:
            if kw in body_lower:
                return domain
    return "general"


def _extract_tags(body: str, title: str) -> list[str]:
    """Pull meaningful single-word tags from title + first 200 chars of body."""
    text = (title + " " + body[:200]).lower()
    stopwords = {"the", "a", "an", "and", "or", "in", "on", "for", "to", "of",
                 "is", "are", "with", "how", "use", "using", "can", "be", "this",
                 "that", "by", "from", "as", "it", "at", "if", "when"}
    words = re.findall(r"\b[a-z][a-z\-]{3,}\b", text)
    seen, tags = set(), []
    for w in words:
        if w not in stopwords and w not in seen:
            seen.add(w)
            tags.append(w)
        if len(tags) == 8:
            break
    return tags


def build_document(chunk: dict) -> dict:
    doc_type = _classify_doc_type(chunk["_path"], chunk["_body"])
    domain   = _classify_domain(chunk["_body"])
    tags     = _extract_tags(chunk["_body"], chunk["_title"])

    return {
        "id":           uuid.uuid4().hex,
        "doc_type":     doc_type,
        "pattern_name": chunk["_title"][:120],
        "domain":       domain,
        "description":  chunk["_title"],          # used for embedding
        "content":      chunk["_body"],
        "tags":         tags,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Upload in batches
# ─────────────────────────────────────────────────────────────────────────────

def upload_batches(documents: list[dict], dry_run: bool = False):
    total   = len(documents)
    batches = [documents[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]

    print(f"\n[upload] {total} chunks → {len(batches)} batches of {BATCH_SIZE}")

    # Stats
    type_counts = {"bpmn": 0, "test": 0, "springboot": 0}
    for d in documents:
        type_counts[d["doc_type"]] = type_counts.get(d["doc_type"], 0) + 1

    print(f"[upload] doc_type breakdown: {type_counts}")

    if dry_run:
        print("\n[dry-run] First 3 chunks preview:")
        for d in documents[:3]:
            print(f"  [{d['doc_type']}] {d['pattern_name'][:80]}")
            print(f"    domain={d['domain']}  tags={d['tags']}")
            print(f"    content={d['content'][:120]}...\n")
        print("[dry-run] No data uploaded.")
        return

    uploaded = 0
    for i, batch in enumerate(batches, 1):
        try:
            count = upsert_documents(batch)
            uploaded += count
            print(f"[upload] Batch {i}/{len(batches)} — {count} vectors upserted  "
                  f"(total so far: {uploaded})")
            # Small pause to stay within Pinecone rate limits
            if i < len(batches):
                time.sleep(0.5)
        except Exception as e:
            print(f"[upload] Batch {i} FAILED: {e}")
            print("[upload] Waiting 5s before continuing...")
            time.sleep(5)

    print(f"\n[upload] Complete. {uploaded}/{total} chunks indexed into Pinecone.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest Camunda docs into Pinecone")
    parser.add_argument("--skip-clone",  action="store_true",
                        help="Skip git clone/pull (use existing camunda-docs dir)")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Parse and preview chunks without uploading")
    parser.add_argument("--doc-type",    choices=["bpmn", "test", "springboot"],
                        help="Only upload chunks of this doc_type")
    parser.add_argument("--limit",       type=int, default=0,
                        help="Max chunks to upload (0 = no limit, good for testing)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Camunda Docs → Pinecone Ingestion Pipeline")
    print("=" * 60)

    # ── 1. Clone ──────────────────────────────────────────────────────────────
    if not args.skip_clone:
        clone_repo()
    else:
        if not CLONE_DIR.exists():
            print(f"[error] --skip-clone set but '{CLONE_DIR}' does not exist. "
                  "Run without --skip-clone first.")
            sys.exit(1)
        print(f"[clone] Skipping clone — using existing '{CLONE_DIR}'.")

    # ── 2. Collect files ──────────────────────────────────────────────────────
    files = collect_files()
    if not files:
        print("[error] No Markdown files found. Check INCLUDE_DIRS.")
        sys.exit(1)

    # ── 3. Chunk all files ────────────────────────────────────────────────────
    print(f"\n[chunk] Parsing {len(files)} files...")
    raw_chunks = []
    for path in files:
        raw_chunks.extend(chunk_file(path))

    print(f"[chunk] {len(raw_chunks)} raw chunks extracted.")

    # ── 4. Build documents ────────────────────────────────────────────────────
    print("[classify] Classifying and building documents...")
    documents = [build_document(c) for c in raw_chunks]

    # ── 5. Filter by doc_type if requested ───────────────────────────────────
    if args.doc_type:
        documents = [d for d in documents if d["doc_type"] == args.doc_type]
        print(f"[filter] Filtered to doc_type='{args.doc_type}': {len(documents)} chunks")

    # ── 6. Apply limit ────────────────────────────────────────────────────────
    if args.limit > 0:
        documents = documents[:args.limit]
        print(f"[limit] Capped at {len(documents)} chunks")

    # ── 7. Upload ─────────────────────────────────────────────────────────────
    upload_batches(documents, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
