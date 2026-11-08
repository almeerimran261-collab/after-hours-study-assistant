from hashlib import sha256

import chromadb
from langchain_core.documents import Document
from sentence_transformers import SentenceTransformer

from src.config import COLLECTION_NAME, DATABASE_DIR
from src.embeddings import embed_texts


def get_collection():
    """Open the local Chroma collection, creating it if needed."""
    client = chromadb.PersistentClient(path=str(DATABASE_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def rebuild_index(
    chunks: list[Document], model: SentenceTransformer, batch_size: int = 64
) -> int:
    """Replace the current local index with vectors for the supplied chunks."""
    collection = get_collection()

    # Rebuild from scratch so repeated runs do not leave duplicate or stale chunks.
    existing_ids = collection.get(include=["metadatas"])["ids"]
    if existing_ids:
        collection.delete(ids=existing_ids)

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [chunk.page_content for chunk in batch]
        vectors = embed_texts(model, texts)
        ids = []
        metadatas = []
        for chunk in batch:
            identity = (
                f"{chunk.metadata['source']}|{chunk.metadata['page']}|"
                f"{chunk.metadata['chunk_index']}|{chunk.page_content}"
            )
            ids.append(sha256(identity.encode("utf-8")).hexdigest())
            metadata = {
                "source": str(chunk.metadata["source"]),
                "page": int(chunk.metadata["page"]),
                "chunk_index": int(chunk.metadata["chunk_index"]),
                "start_index": int(chunk.metadata.get("start_index", 0)),
                "content_type": str(chunk.metadata.get("content_type", "page")),
                "location_type": str(
                    chunk.metadata.get("location_type", "page")
                ),
            }

            slide_number = chunk.metadata.get("slide")
            if slide_number is not None:
                metadata["slide"] = int(slide_number)

            extraction_method = chunk.metadata.get("extraction_method")
            if extraction_method is not None:
                metadata["extraction_method"] = str(extraction_method)

            metadatas.append(metadata)


        collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=vectors.tolist(),
        )

    return collection.count()
