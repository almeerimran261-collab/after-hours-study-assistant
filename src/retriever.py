import os
import re
from functools import lru_cache

from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sentence_transformers.cross_encoder import CrossEncoder

from src import config
from src.config import TOP_K
from src.embeddings import embed_texts

_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)
BM25_CANDIDATE_K = getattr(config, "BM25_CANDIDATE_K", 20)
RRF_K = getattr(config, "RRF_K", 60)
RERANKER_MODEL_NAME = getattr(
    config, "RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2"
)


def _tokenize(text: str) -> list[str]:
    """Apply consistent, simple tokenization to document and query text."""
    return _TOKEN_PATTERN.findall(text.casefold())


@lru_cache(maxsize=1)
def load_reranker() -> CrossEncoder:
    """Load the small cross-encoder once and keep inference on CPU."""
    cache_folder = (
        os.environ.get("SENTENCE_TRANSFORMERS_HOME")
        or os.environ.get("HF_HOME")
    )
    return CrossEncoder(
        RERANKER_MODEL_NAME,
        device="cpu",
        cache_folder=cache_folder,
    )


def retrieve_chunks(
    question: str,
    model: SentenceTransformer,
    collection,
    top_k: int = TOP_K,
    reranker: CrossEncoder | None = None,
) -> list[dict]:
    """Retrieve with vector+BM25, fuse with RRF, rerank, and preserve citations.

    The cross-encoder scores the top 20 RRF candidates. Only the final top_k
    passages are returned to the answer generator.
    """
    total = collection.count()
    if total == 0:
        raise ValueError("The vector index is empty. Run the ingest command first.")

    candidate_k = min(BM25_CANDIDATE_K, total)
    query_vector = embed_texts(model, [question])[0].tolist()
    vector_result = collection.query(
        query_embeddings=[query_vector],
        n_results=candidate_k,
        include=["documents", "metadatas", "distances"],
    )

    hits_by_id: dict[str, dict] = {}
    for rank, (doc_id, text, metadata, distance) in enumerate(
        zip(
            vector_result["ids"][0],
            vector_result["documents"][0],
            vector_result["metadatas"][0],
            vector_result["distances"][0],
        ),
        start=1,
    ):
        hits_by_id[doc_id] = {
            "id": doc_id,
            "text": text,
            "source": metadata["source"],
            "page": int(metadata["page"]),
            "content_type": metadata.get("content_type", "page"),
            "location_type": metadata.get("location_type", "page"),
            "slide": (
                int(metadata["slide"])
                if metadata.get("slide") is not None
                else None
                ),
            "distance": float(distance),
            "vector_rank": rank,
            "bm25_rank": None,
            "rrf_score": 1.0 / (RRF_K + rank),
        }

    # Rebuild BM25 from the current Chroma contents so a re-ingestion is
    # reflected immediately. This is inexpensive for the current course-note
    # collection; a persistent lexical index can be added if the corpus grows.
    corpus_result = collection.get(include=["documents", "metadatas"])
    corpus_ids = corpus_result["ids"]
    corpus_texts = corpus_result["documents"]
    corpus_metadatas = corpus_result["metadatas"]
    tokenized_corpus = [_tokenize(text or "") for text in corpus_texts]
    query_tokens = _tokenize(question)

    if query_tokens and any(tokenized_corpus):
        bm25 = BM25Okapi(tokenized_corpus)
        bm25_scores = bm25.get_scores(query_tokens)
        bm25_order = sorted(
            (index for index, score in enumerate(bm25_scores) if score > 0),
            key=lambda index: (-float(bm25_scores[index]), index),
        )[:candidate_k]

        for rank, corpus_index in enumerate(bm25_order, start=1):
            doc_id = corpus_ids[corpus_index]
            if doc_id not in hits_by_id:
                metadata = corpus_metadatas[corpus_index]
                hits_by_id[doc_id] = {
                    "id": doc_id,
                    "text": corpus_texts[corpus_index],
                    "source": metadata["source"],
                    "page": int(metadata["page"]),
                    "content_type": metadata.get("content_type", "page"),
                    # The candidate was found by BM25, not in vector top-k.
                    "location_type": metadata.get("location_type", "page"),
                    "slide": (
                        int(metadata["slide"])
                        if metadata.get("slide") is not None
                        else None
                    ),

                    "distance": float("inf"),
                    "vector_rank": None,
                    "bm25_rank": rank,
                    "rrf_score": 1.0 / (RRF_K + rank),
                }
            else:
                hit = hits_by_id[doc_id]
                hit["bm25_rank"] = rank
                hit["rrf_score"] += 1.0 / (RRF_K + rank)

    fused = sorted(
        hits_by_id.values(),
        key=lambda hit: (-hit["rrf_score"], hit["distance"], hit["id"]),
    )
    candidate_pool = fused[: min(BM25_CANDIDATE_K, len(fused))]
    if not candidate_pool:
        return []

    active_reranker = reranker if reranker is not None else load_reranker()
    pairs = [(question, hit["text"]) for hit in candidate_pool]
    scores = active_reranker.predict(pairs, batch_size=16)

    # Keep each ranking as a rank, rather than adding raw scores with
    # incompatible scales. The second RRF step balances hybrid relevance with
    # the cross-encoder's pairwise ordering.
    for hybrid_rank, hit in enumerate(candidate_pool, start=1):
        hit["hybrid_rank"] = hybrid_rank
    for hit, score in zip(candidate_pool, scores):
        score_value = score.item() if hasattr(score, "item") else score
        if isinstance(score_value, (list, tuple)):
            score_value = score_value[0]
        hit["rerank_score"] = float(score_value)

    cross_encoder_order = sorted(
        candidate_pool,
        key=lambda hit: (-hit["rerank_score"], hit["id"]),
    )
    for rerank_rank, hit in enumerate(cross_encoder_order, start=1):
        hit["rerank_rank"] = rerank_rank
        hit["rank_fusion_score"] = (
            1.0 / (RRF_K + hit["hybrid_rank"])
            + 1.0 / (RRF_K + rerank_rank)
        )

    balanced_order = sorted(
        candidate_pool,
        key=lambda hit: (-hit["rank_fusion_score"], -hit["rrf_score"], hit["id"]),
    )
    return balanced_order[: min(top_k, len(balanced_order))]
