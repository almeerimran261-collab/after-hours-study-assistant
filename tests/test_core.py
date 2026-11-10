"""Offline behavior checks; model replies are simulated and HTTP is blocked."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ["RAG_MODE"] = "local"

from src import config, generator, model_provider
from src.memory import ConversationMemory
from src.public_demo import sample_records


class CoreTests(unittest.TestCase):
    def setUp(self):
        network = patch(
            "requests.sessions.Session.request",
            side_effect=AssertionError(
                "Unexpected HTTP request in an offline test"
            ),
        )
        network.start()
        self.addCleanup(network.stop)
        self.hit = {
            "source": "notes.pdf",
            "page": 2,
            "text": "LIFO means Last In, First Out.",
            "rerank_score": 5.0,
        }

    def generate(self, reply):
        with patch.object(generator, "complete", return_value=reply):
            return generator.generate_answer(
                "What does LIFO mean?",
                [self.hit],
                return_diagnostics=True,
            )

    def test_valid_cited_answer_is_returned(self):
        answer, reason, _ = self.generate(
            "LIFO means Last In, First Out. [notes.pdf, p. 2]"
        )
        self.assertIn("Last In, First Out", answer)
        self.assertEqual(reason, "answered_with_validated_citation")

    def test_uncited_answer_is_refused(self):
        answer, reason, _ = self.generate(
            "LIFO means Last In, First Out."
        )
        self.assertEqual(answer, generator.REFUSAL)
        self.assertEqual(reason, "missing_citation")

    def test_foreign_or_wrong_page_citations_are_refused(self):
        for citation in ["[other.pdf, p. 2]", "[notes.pdf, p. 99]"]:
            with self.subTest(citation=citation):
                answer, reason, _ = self.generate("LIFO. " + citation)
                self.assertEqual(answer, generator.REFUSAL)
                self.assertEqual(
                    reason, "citation_not_in_retrieved_context"
                )

    def test_slide_citation_cannot_be_replaced_with_page_citation(self):
        hit = {
            "source": "lecture.pptx",
            "page": 7,
            "slide": 7,
            "location_type": "slide",
        }
        cases = [
            ("[lecture.pptx, slide 7]", True),
            ("[lecture.pptx, p. 7]", False),
        ]
        for citation, valid in cases:
            with self.subTest(citation=citation):
                _, reason = (
                    generator._clean_and_validate_answer_with_reason(
                        "Answer " + citation, [hit]
                    )
                )
                self.assertEqual(
                    reason == "answered_with_validated_citation",
                    valid,
                )

    def test_empty_context_avoids_model_request(self):
        with patch.object(generator, "complete") as complete:
            result = generator.generate_answer(
                "Question?", [], return_diagnostics=True
            )
        complete.assert_not_called()
        self.assertEqual(result[1], "no_retrieved_context")

    def test_low_relevance_avoids_model_request(self):
        hit = {
            **self.hit,
            "rerank_score": generator.MIN_RERANK_SCORE - 1,
        }
        with patch.object(generator, "complete") as complete:
            result = generator.generate_answer(
                "Unrelated?", [hit], return_diagnostics=True
            )
        complete.assert_not_called()
        self.assertEqual(result[0], generator.REFUSAL)
        self.assertEqual(result[1], "reranker_threshold")

    def test_empty_model_reply_is_handled(self):
        self.assertEqual(
            self.generate("")[1], "empty_model_response"
        )

    def test_model_refusal_is_preserved(self):
        answer, reason, _ = self.generate(generator.REFUSAL)
        self.assertEqual(answer, generator.REFUSAL)
        self.assertEqual(reason, "model_refusal")

    def test_reasoning_marker_is_removed_from_answer_and_diagnostics(self):
        result = self.generate(
            "<think>internal-marker</think>"
            "LIFO. [notes.pdf, p. 2]"
        )
        self.assertEqual(
            result[1], "answered_with_validated_citation"
        )
        for text in [result[0], result[2]]:
            self.assertNotIn("internal-marker", text)
            self.assertNotIn("<think>", text)

    def test_conditional_followup_keeps_function_and_new_condition(self):
        memory = ConversationMemory()
        memory.remember(
            "What does insertAtEnd do when head is NULL?"
        )
        question, clarify = memory.rewrite(
            "And when it is not empty?"
        )
        self.assertEqual(
            question,
            "What does insertAtEnd do when it is not empty?",
        )
        self.assertFalse(clarify)

    def test_followup_uses_latest_topic(self):
        memory = ConversationMemory()
        memory.remember(
            "What does insertAtEnd do when head is NULL?"
        )
        memory.remember(
            "What does push do when the stack is empty?"
        )
        question, _ = memory.rewrite("And when it is full?")
        self.assertEqual(
            question, "What does push do when it is full?"
        )

    def test_clear_and_separate_sessions_do_not_share_questions(self):
        first, second = ConversationMemory(), ConversationMemory()
        first.remember(
            "What does insertAtEnd do when head is NULL?"
        )
        self.assertEqual(second.questions, [])
        first.clear()
        self.assertEqual(first.questions, [])

    def test_private_or_modified_excerpts_are_blocked_before_api_access(self):
        public = sample_records()[0]
        candidates = [
            {**public, "source": "private.pdf"},
            {**public, "text": "PRIVATE TEST EXCERPT"},
            {**public, "page": 99},
        ]
        with (
            patch.object(config, "DEMO_MODE", True),
            patch.object(
                config,
                "setting",
                side_effect=AssertionError(
                    "Key lookup should not happen"
                ),
            ),
            patch.object(model_provider.requests, "post") as post,
        ):
            for hit in candidates:
                with self.subTest(hit=hit):
                    with self.assertRaisesRegex(
                        RuntimeError, "built-in public notes"
                    ):
                        model_provider.complete([], [hit])
            post.assert_not_called()

    def demo_response(self, status=200, finish="stop"):
        return SimpleNamespace(
            status_code=status,
            text="RAW-ERROR-MARKER",
            json=lambda: {
                "choices": [{
                    "finish_reason": finish,
                    "message": {
                        "content":
                            "LIFO means Last In, First Out. "
                            "[Public Study Notes.pdf, p. 1]",
                    },
                }],
            },
        )

    def test_public_demo_request_uses_groq_and_validates_citation(self):
        hit = {**sample_records()[0], "rerank_score": 5.0}
        with (
            patch.object(config, "DEMO_MODE", True),
            patch.object(
                config, "setting", return_value="fake-test-key"
            ),
            patch.object(
                model_provider.requests,
                "post",
                return_value=self.demo_response(),
            ) as post,
        ):
            answer, reason, _ = generator.generate_answer(
                "What does LIFO mean?",
                [hit],
                return_diagnostics=True,
            )
        self.assertEqual(
            reason, "answered_with_validated_citation"
        )
        self.assertIn("Last In, First Out", answer)
        self.assertEqual(
            post.call_args.args[0],
            "https://api.groq.com/openai/v1/chat/completions",
        )
        self.assertIn(
            hit["text"],
            post.call_args.kwargs["json"]["messages"][-1]["content"],
        )

    def test_quota_error_does_not_expose_raw_response_or_key(self):
        with (
            patch.object(config, "DEMO_MODE", True),
            patch.object(
                config, "setting", return_value="fake-test-key"
            ),
            patch.object(
                model_provider.requests,
                "post",
                return_value=self.demo_response(status=429),
            ),
        ):
            with self.assertRaises(RuntimeError) as caught:
                model_provider.complete(
                    [{"role": "system", "content": "Answer from notes."}],
                    sample_records(),
                )
        self.assertIn("429", str(caught.exception))
        self.assertNotIn("RAW-ERROR-MARKER", str(caught.exception))
        self.assertNotIn("fake-test-key", str(caught.exception))

    def test_truncated_reply_is_rejected(self):
        with (
            patch.object(config, "DEMO_MODE", True),
            patch.object(
                config, "setting", return_value="fake-test-key"
            ),
            patch.object(
                model_provider.requests,
                "post",
                return_value=self.demo_response(finish="length"),
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "did not complete"
            ):
                model_provider.complete(
                    [{"role": "system", "content": "Answer from notes."}],
                    sample_records(),
                )


if __name__ == "__main__":
    unittest.main()