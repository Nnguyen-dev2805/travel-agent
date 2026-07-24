"""Data Ingestion & Vector Indexing Pipeline Script."""

import logging
from pathlib import Path
from backend.rag.chunking import load_jsonl_dataset, DocumentChunker
from backend.rag.embedding import VectorEmbedder
from backend.rag.retrieval import ChromaVectorStore

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("travel_agent_indexing")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_PATH = ROOT_DIR / "data" / "vietnam-travel.jsonl"


def run_indexing_pipeline():
    """Execute full offline indexing pipeline: JSONL -> Chunks -> Embeddings -> ChromaDB."""
    logger.info("=== STARTING RAG VECTOR INDEXING PIPELINE ===")

    # 1. Load raw dataset
    logger.info(f"Step 1: Loading raw articles from {DATASET_PATH}...")
    documents = load_jsonl_dataset(DATASET_PATH)
    logger.info(f"Loaded {len(documents)} raw travel documents.")

    # 2. Chunk documents
    logger.info("Step 2: Splitting documents into text chunks...")
    chunker = DocumentChunker(chunk_size=1000, chunk_overlap=150)
    chunks = chunker.chunk_documents(documents)
    logger.info(f"Generated {len(chunks)} total text chunks.")

    # 3. Generate Embeddings
    logger.info("Step 3: Generating 1024-dim dense vectors...")
    embedder = VectorEmbedder(model_name="BAAI/bge-m3")
    texts = [chunk.text for chunk in chunks]
    embeddings = embedder.embed_texts(texts)
    logger.info(f"Generated {len(embeddings)} vector embeddings.")

    # 4. Upsert into ChromaDB
    logger.info("Step 4: Upserting vectors into ChromaDB...")
    vector_store = ChromaVectorStore()
    total_added = vector_store.add_chunks(chunks, embeddings)

    logger.info(f"=== INDEXING COMPLETE! Total vectors in ChromaDB: {vector_store.count()} ===")
    return total_added


if __name__ == "__main__":
    run_indexing_pipeline()
