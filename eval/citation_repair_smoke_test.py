"""Regression check for citation-only repair; no Ollama/Groq requests.

A known draft is supplied deliberately. The check proves that unique numeric
support corrects the label without changing any answer text or calling a model
again. It does not measure initial-model answer accuracy or general grounding.
"""
from unittest.mock import patch

from src import config, generator


def main():
    if config.DEMO_MODE:
        raise SystemExit("Run this local regression check with RAG_MODE=local.")
    source = "citation_demo.pptx"
    hits = [
        {"source": source, "page": 29, "slide": 29, "location_type": "slide",
         "text": "Task 2. Insert the registration IDs in this order: "
                 "40, 20, 60, 10, 30, 50, 70, 5. Fill each level from left to right.",
         "rerank_score": 5.0},
        {"source": source, "page": 30, "slide": 30, "location_type": "slide",
         "text": "Task 4. The root is 100. The other values are "
                 "50, 150, 25, 75, 125, 175. All leaves are at the same level.",
         "rerank_score": 3.0},
    ]
    draft = ("The registration IDs are 40, 20, 60, 10, 30, 50, 70, 5. "
             f"[{source}, slide 30]")
    expected = draft.replace(f"[{source}, slide 30]", f"[{source}, slide 29]")
    print("Citation-only repair regression check; no model/API requests.", flush=True)
    print("The check supplies the original answer with the wrong citation.", flush=True)
    with patch.object(generator, "complete", side_effect=[
        draft, AssertionError("Citation repair must not make a second generation request."),
    ]) as complete:
        answer, reason, safe = generator.generate_answer(
            "In Task 2, what is the insertion order of the registration IDs?",
            hits, return_diagnostics=True,
        )
    print(f"\nAnswer: {answer}")
    print(f"Diagnostic: {reason}")
    print("Model/API repair requests: 0")
    passed = (complete.call_count == 1 and answer == expected
              and reason == "answered_with_validated_citation" and safe == draft
              and generator.CITATION_PATTERN.sub("", answer)
              == generator.CITATION_PATTERN.sub("", draft))
    if not passed:
        raise SystemExit("CHECK FAILED: share this output; citation-only repair needs review.")
    print("PASS: only slide 30 changed to slide 29; the answer text and 60 stayed unchanged.")


if __name__ == "__main__":
    main()
