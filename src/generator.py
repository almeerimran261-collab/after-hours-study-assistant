import re

from src import config
from src.citation_sequences import numeric_citation_mismatches, repair_unique_numeric_citation
from src.model_provider import complete

# CrossEncoder scores are raw relevance scores, not probabilities. The 0.0
# experiment falsely refused three answerable benchmark questions. A provisional
# -2.0 cutoff avoids those false refusals on this 30-question set; this is still
# only one guardrail, with grounded prompting and citation validation retained.
# Add MIN_RERANK_SCORE to config.py to override it without editing this file.
MIN_RERANK_SCORE = float(getattr(config, "MIN_RERANK_SCORE", -2.0))
# Compatibility fallback for results created before Phase 4B added rerank_score.
MAX_COSINE_DISTANCE = 0.35
REFUSAL = "I couldn't find this in the uploaded documents."
CITATION_PATTERN = re.compile(
    r"\[(?:citation:\s*)?([^,\[\]]+),\s*(p\.?|page|slide)\s*(\d+)\]",
    re.IGNORECASE,
)


THINK_PATTERN = re.compile(r"<think>.*?(?:</think>|$)", re.IGNORECASE | re.DOTALL)
CLOSING_THINK_PATTERN = re.compile(r"\A.*?</think\s*>", re.IGNORECASE | re.DOTALL)


def _remove_think_trace(answer: str) -> str:
    """Remove reasoning text, including Qwen output that only has </think>."""
    if re.search(r"</think\s*>", answer, re.IGNORECASE):
        answer = CLOSING_THINK_PATTERN.sub("", answer, count=1)
    else:
        answer = THINK_PATTERN.sub("", answer)
    return answer.strip()


def _clean_and_validate_answer_with_reason(
    answer: str, retrieved_chunks: list[dict]
) -> tuple[str, str]:
    """Validate an answer and return a concise diagnostic code."""
    answer = _remove_think_trace(answer)

    if REFUSAL.casefold() in answer.casefold():
        return REFUSAL, "model_refusal"

    def citation_location(label: str) -> str:
        normalized = label.casefold().strip().rstrip(".")
        return "slide" if normalized == "slide" else "page"

    citations = [
        (
            match.group(1).strip(),
            citation_location(match.group(2)),
            int(match.group(3)),
        )
        for match in CITATION_PATTERN.finditer(answer)
    ]

    allowed_citations = {
        (
            str(hit["source"]).strip(),
            "slide" if hit.get("location_type") == "slide" else "page",
            int(hit["slide"])
            if hit.get("location_type") == "slide"
            else int(hit["page"]),
        )
        for hit in retrieved_chunks
    }

    if not citations:
        return REFUSAL, "missing_citation"

    if any(citation not in allowed_citations for citation in citations):
        return REFUSAL, "citation_not_in_retrieved_context"

    if numeric_citation_mismatches(answer, retrieved_chunks, CITATION_PATTERN):
        return REFUSAL, "citation_numeric_sequence_mismatch"

    def normalize_citation(match: re.Match) -> str:
        source = match.group(1).strip()
        location = citation_location(match.group(2))
        number = int(match.group(3))
        label = "slide" if location == "slide" else "p."
        return f"[{source}, {label} {number}]"

    answer = CITATION_PATTERN.sub(normalize_citation, answer)
    return answer, "answered_with_validated_citation"



def _clean_and_validate_answer(answer: str, retrieved_chunks: list[dict]) -> str:
    """Backwards-compatible answer-only validator."""
    return _clean_and_validate_answer_with_reason(answer, retrieved_chunks)[0]


def generate_answer(
    question: str,
    retrieved_chunks: list[dict],
    *,
    return_diagnostics: bool = False,
) -> str | tuple[str, str, str]:
    """Answer only from retrieved PDF passages, with validated page citations."""
    def finish(
        answer: str, reason: str, safe_model_response: str = ""
    ) -> str | tuple[str, str, str]:
        return (
            (answer, reason, safe_model_response)
            if return_diagnostics
            else answer
        )

    if not retrieved_chunks:
        return finish(REFUSAL, "no_retrieved_context")

    reranker_scores = [
        float(hit["rerank_score"])
        for hit in retrieved_chunks
        if hit.get("rerank_score") is not None
    ]
    if reranker_scores:
        if max(reranker_scores) < MIN_RERANK_SCORE:
            return finish(REFUSAL, "reranker_threshold")
    else:
        best_distance = min(
            float(hit.get("distance", float("inf"))) for hit in retrieved_chunks
        )
        if best_distance > MAX_COSINE_DISTANCE:
            return finish(REFUSAL, "cosine_distance_threshold")

    context_parts = []

    for hit in retrieved_chunks:
        if hit.get("location_type") == "slide":
            location = f"slide {int(hit['slide'])}"
        else:
            location = f"p. {int(hit['page'])}"

        context_parts.append(
            f"[{hit['source']}, {location}]\n{hit['text']}"
        )

    context = "\n\n".join(context_parts)

    system_prompt = (
        "You are a concise study assistant. Answer using only the supplied passages. "
        "Match passages by meaning, not only by identical wording; a question may "
        "paraphrase a passage. Keep different operations and cases distinct. "
        "For a question asking for additional or other items, include every item "
        "listed in the directly relevant passage; do not leave out listed items. "
        "If a passage directly supports an answer, answer from it rather than "
        "refusing. If the passages do not support the answer, reply exactly: "
        f"{REFUSAL} "
        "For every answer, copy the citation attached to the supporting passage. "
        "Use [filename.pdf, p. 12] for a PDF page or "
        "[filename.pptx, slide 12] for a PowerPoint slide. "
        "Never invent or change a location number. Do not add outside facts "
        "or a preamble."
    )


    user_prompt = f"PDF passages:\n{context}\n\nQuestion: {question}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    answer = complete(messages, retrieved_chunks)
    if not answer:
        return finish(REFUSAL, "empty_model_response")
    # Never include hidden think-trace text in diagnostics or project logs.
    safe_model_response = _remove_think_trace(answer)
    validated_answer, reason = _clean_and_validate_answer_with_reason(
        safe_model_response, retrieved_chunks
    )
    if reason == "citation_numeric_sequence_mismatch":
        corrected = repair_unique_numeric_citation(
            safe_model_response, retrieved_chunks, CITATION_PATTERN,
        )
        if corrected is not None:
            # The body is immutable; only a uniquely supported label can change.
            # Revalidate it before display. No second generation request is made.
            validated_answer, reason = _clean_and_validate_answer_with_reason(
                corrected, retrieved_chunks,
            )
    return finish(validated_answer, reason, safe_model_response)
