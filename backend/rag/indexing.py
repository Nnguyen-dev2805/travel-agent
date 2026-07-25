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
DATASET_PATH = ROOT_DIR / "data" / "vietnam-travel.jsonl"


def run_indexing_pipeline():
    """Execute full offline indexing pipeline for both Baseline and Parent-Child collections."""
    logger.info("=== STARTING RAG VECTOR INDEXING PIPELINE ===")

    # 1. Load raw dataset
    logger.info(f"Step 1: Loading raw articles from {DATASET_PATH}...")
    documents = load_jsonl_dataset(DATASET_PATH)
    logger.info(f"Loaded {len(documents)} raw travel documents.")

    embedder = VectorEmbedder(model_name="BAAI/bge-m3")

    # 2. Index Baseline Fixed-Size Collection
    logger.info("Step 2A: Indexing Baseline Fixed-Size Collection ('vietnam_travel_knowledge')...")
    baseline_chunker = DocumentChunker(chunk_size=1000, chunk_overlap=150)
    baseline_chunks = baseline_chunker.chunk_documents(documents)
    logger.info(f"Generated {len(baseline_chunks)} baseline text chunks.")
    
    baseline_texts = [chunk.text for chunk in baseline_chunks]
    baseline_embeddings = embedder.embed_texts(baseline_texts)
    
    baseline_store = ChromaVectorStore(collection_name="vietnam_travel_knowledge")
    baseline_added = baseline_store.add_chunks(baseline_chunks, baseline_embeddings)

    # 3. Index Parent-Child Semantic Collection
    logger.info("Step 2B: Indexing Parent-Child Collection ('vietnam_travel_parent_child')...")
    pc_chunker = ParentChildChunker()
    all_child_chunks = []
    
    for doc in documents:
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
