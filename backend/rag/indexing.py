"""Data Ingestion & Vector Indexing Pipeline Script supporting Dual Collections."""

from __future__ import annotations

import logging
from pathlib import Path
from backend.rag.chunking import load_jsonl_dataset, DocumentChunker, ParentChildChunker
from backend.rag.embedding import VectorEmbedder
from backend.rag.retrieval import ChromaVectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("travel_agent_indexing")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# Standardized Dataset Paths
RAW_DATASET_PATH = ROOT_DIR / "data" / "processed" / "vietnam_travel_raw.jsonl"
CLEANED_DATASET_PATH = ROOT_DIR / "data" / "processed" / "vietnam_travel_cleaned.json"

# Legacy Fallback Paths
LEGACY_BASELINE_PATH = ROOT_DIR / "data" / "vietnam-travel.jsonl"
LEGACY_CLEANED_PATH = ROOT_DIR / "data" / "document_clean.json"


def get_input_file_paths() -> tuple[Path, Path]:
    """Resolve active raw and clean dataset file paths with legacy fallback."""
    raw_path = RAW_DATASET_PATH if RAW_DATASET_PATH.exists() else LEGACY_BASELINE_PATH
    clean_path = (
        CLEANED_DATASET_PATH
        if CLEANED_DATASET_PATH.exists()
        else (LEGACY_CLEANED_PATH if LEGACY_CLEANED_PATH.exists() else raw_path)
    )
    return raw_path, clean_path


def run_indexing_pipeline():
    """Execute full offline indexing pipeline for both Baseline and Parent-Child collections."""
    logger.info("=== STARTING RAG VECTOR INDEXING PIPELINE ===")

    raw_path, clean_path = get_input_file_paths()

    embedder = VectorEmbedder(model_name="BAAI/bge-m3")

    # 1. Index Baseline Fixed-Size Collection
    logger.info(f"Step 1: Loading baseline articles from {raw_path}...")
    baseline_docs = load_jsonl_dataset(raw_path)
    logger.info(f"Loaded {len(baseline_docs)} baseline travel documents.")

    logger.info("Step 2A: Indexing Baseline Fixed-Size Collection ('vietnam_travel_knowledge')...")
    baseline_chunker = DocumentChunker(chunk_size=1000, chunk_overlap=150)
    baseline_chunks = baseline_chunker.chunk_documents(baseline_docs)
    logger.info(f"Generated {len(baseline_chunks)} baseline text chunks.")
    
    baseline_texts = [chunk.text for chunk in baseline_chunks]
    baseline_embeddings = embedder.embed_texts(baseline_texts)
    
    baseline_store = ChromaVectorStore(collection_name="vietnam_travel_knowledge")
    baseline_added = baseline_store.add_chunks(baseline_chunks, baseline_embeddings)

    # 2. Index Parent-Child Collection from Cleaned Dataset
    logger.info(f"Step 2B: Loading structured articles for Parent-Child from {clean_path}...")
    pc_docs = load_jsonl_dataset(clean_path)
    logger.info(f"Loaded {len(pc_docs)} structured documents for Parent-Child chunking.")

    pc_chunker = ParentChildChunker()
    all_child_chunks = []
    
    for doc in pc_docs:
        _, child_chunks = pc_chunker.chunk_document(doc)
        all_child_chunks.extend(child_chunks)
        
    logger.info(f"Generated {len(all_child_chunks)} Parent-Child child chunks.")
    
    pc_retrieval_texts = [child.retrieval_text for child in all_child_chunks]
    pc_embeddings = embedder.embed_texts(pc_retrieval_texts)
    
    pc_store = ChromaVectorStore(collection_name="vietnam_travel_parent_child")
    pc_added = pc_store.add_parent_child_chunks(all_child_chunks, pc_embeddings)

    logger.info("=== INDEXING COMPLETE! ===")
    logger.info(f"Baseline Vectors Count: {baseline_store.count()}")
    logger.info(f"Parent-Child Vectors Count: {pc_store.count()}")
    
    return baseline_added + pc_added


if __name__ == "__main__":
    run_indexing_pipeline()
