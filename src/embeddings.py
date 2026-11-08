import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL_NAME


def load_embedding_model() -> SentenceTransformer:
    """Load the free BGE embedding model explicitly on CPU."""
    return SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")


def embed_texts(
    model: SentenceTransformer, texts: list[str]
) -> np.ndarray:
    """Turn text into normalized numeric vectors for cosine similarity search."""
    return model.encode(
        texts,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
