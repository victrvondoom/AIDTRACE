"""Index the preserved RESOLVE-AI-main knowledge corpora into the private worker's local stores.

Run with the WORKER's interpreter, from var/resolveai (the worker's runtime directory), with the worker stopped:

    integrations/resolveai/.venv/Scripts/python.exe scripts/ingest_resolveai_knowledge.py [--domains banking,telecom] [--max-files 400]

It reuses the worker's own services (chunking, hash/provider embeddings, vector store, source registry, knowledge graph)
and only chooses WHICH files to feed them: curated regulator/policy/FAQ text (.md/.txt). It skips synthetic cases,
pre-chunked dumps, graph exports and download reports, which are not authoritative sources. The originals under
RESOLVE-AI-main/knowledge are only read. Nothing is sent to Supabase, Qdrant or Neo4j.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get("RESOLVEAI_RUNTIME_DIR") or ROOT / "var" / "resolveai")
WORKER_SRC = ROOT / "integrations" / "resolveai" / "backend"
KNOWLEDGE = ROOT.parent / "RESOLVE-AI-main" / "knowledge"

RUNTIME.mkdir(parents=True, exist_ok=True)
os.chdir(RUNTIME)
sys.path.insert(0, str(WORKER_SRC))
os.environ.setdefault("VECTOR_STORE_BACKEND", "jsonl")
os.environ.setdefault("GRAPH_STORE_BACKEND", "jsonl")
os.environ.setdefault("CACHE_ENABLED", "false")
os.environ.setdefault("DISABLE_EXTERNAL_LLM", "true")
os.environ.setdefault("ENVIRONMENT", "development")

EXCLUDED_DIRS = {"metadata", "embeddings", "synthetic_cases", "sample_cases", "chunks", "knowledge_graph"}
EXCLUDED_NAMES = ("report", "manifest", "registry", "readme")
MAX_BYTES = 400_000
MAX_PDF_BYTES = 3_000_000
GENERATED = ("datasets/vector_embeddings", "datasets/knowledge_graph", "datasets/app_store/knowledge_sources.jsonl",
             "datasets/app_store/knowledge_chunks.jsonl")


def reset_generated_knowledge() -> None:
    """Remove only the knowledge stores this script generates, and only inside var/resolveai."""
    for rel in GENERATED:
        target = (RUNTIME / rel).resolve()
        if RUNTIME.resolve() not in target.parents:
            raise RuntimeError(f"refusing to remove outside the runtime directory: {target}")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def curated_files(domain_root: Path, include_pdfs: bool = False) -> list[Path]:
    files: list[Path] = []
    for path in sorted(domain_root.rglob("*")):
        is_pdf = path.suffix.lower() == ".pdf"
        if not path.is_file() or not (path.suffix.lower() in {".md", ".txt"} or (is_pdf and include_pdfs and "insurers" in path.parts)):
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(domain_root).parts):
            continue
        if any(token in path.stem.lower() for token in EXCLUDED_NAMES):
            continue
        if path.stat().st_size < 400 or path.stat().st_size > (MAX_PDF_BYTES if is_pdf else MAX_BYTES):
            continue
        files.append(path)
    return files


def sidecar_root(path: Path, domain_root: Path) -> Path:
    """Nearest ancestor holding a metadata/ folder (layouts differ: <domain>/metadata or <domain>/<set>/metadata)."""
    for parent in path.parents:
        if (parent / "metadata").is_dir():
            return parent
        if parent == domain_root:
            break
    return domain_root


async def ingest_domain(domain, root: Path, max_files: int, include_pdfs: bool) -> dict:
    from app.database.postgres.repositories import case_repository
    from app.knowledge_graph.neo4j.service import knowledge_graph
    from app.rag.chunking.text import chunk_text
    from app.rag.indexing.service import indexing_service
    from app.services.knowledge_ingestion import knowledge_ingestion_service as svc

    docs = chunks = 0
    for path in curated_files(root, include_pdfs)[:max_files]:
        text = svc.read_text(path)
        if not text.strip():
            continue
        document_id = str(uuid5(NAMESPACE_URL, f"{domain.value}:{path.as_posix()}"))
        metadata = svc.document_metadata(domain, sidecar_root(path, root), path)
        source = svc.source_record(domain, document_id, path, text, metadata)
        await case_repository.upsert_knowledge_source(source)
        pieces = chunk_text(text)
        await case_repository.add_knowledge_chunks(document_id, [
            {"chunk_id": str(uuid5(NAMESPACE_URL, f"{document_id}:{i}")), "chunk_index": i, "text": piece, "metadata": metadata}
            for i, piece in enumerate(pieces)
        ])
        chunks += await indexing_service.index_document_text(domain, document_id, text, metadata)
        await knowledge_graph.upsert_knowledge_document(domain=domain, document_id=document_id, title=source["title"],
                                                        source_path=str(path), metadata=metadata)
        docs += 1
    from app.rag.retrieval.factory import get_vector_store
    get_vector_store().flush()
    return {"domain": domain.value, "documents": docs, "chunks": chunks}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domains", default="")
    parser.add_argument("--max-files", type=int, default=400)
    parser.add_argument("--include-pdfs", action="store_true", help="also index insurer policy-wording PDFs (<= 3 MB each)")
    parser.add_argument("--reset", action="store_true", help="first clear the knowledge stores this script generates")
    args = parser.parse_args()
    if not KNOWLEDGE.exists():
        print(f"Knowledge folder not found: {KNOWLEDGE}")
        return 1
    from app.models.domain import Domain

    if args.reset:
        reset_generated_knowledge()
    wanted = {d.strip() for d in args.domains.split(",") if d.strip()}
    for domain in Domain:
        root = KNOWLEDGE / domain.value
        if not root.exists() or (wanted and domain.value not in wanted):
            continue
        print(await ingest_domain(domain, root, args.max_files, args.include_pdfs), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
