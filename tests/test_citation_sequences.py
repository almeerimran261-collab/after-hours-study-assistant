"""Offline checks for a retrieved-but-unsupported numeric-list citation."""
import os
import unittest
from unittest.mock import patch

os.environ["RAG_MODE"] = "local"
from src import generator
from src.citation_sequences import _lists


VALUES = "40, 20, 60, 10, 30, 50, 70, 5"


def hit(slide, text, source="exercise.pptx"):
    return {"source": source, "page": slide, "slide": slide,
            "location_type": "slide", "text": text, "rerank_score": 5.0}


class NumericCitationTests(unittest.TestCase):
    def setUp(self):
        network = patch("requests.sessions.Session.request", side_effect=AssertionError("Unexpected HTTP"))
        network.start()
        self.addCleanup(network.stop)
        self.hits = [
            hit(29, "Task 2. Insert the IDs in this order: " + VALUES + "."),
            hit(30, "Task 4. Insert the remaining values: 50, 150, 25, 75, 125, 175."),
        ]
        self.wrong = "The ID insertion order is " + VALUES + ". [exercise.pptx, slide 30]"
        self.correct = "The ID insertion order is " + VALUES + ". [exercise.pptx, slide 29]"

    def validate(self, answer, hits=None):
        return generator._clean_and_validate_answer_with_reason(answer, self.hits if hits is None else hits)

    def test_another_retrieved_slide_is_not_enough_to_validate_a_citation(self):
        answer, reason = self.validate(self.wrong)
        self.assertEqual(answer, generator.REFUSAL)
        self.assertEqual(reason, "citation_numeric_sequence_mismatch")

    def test_correct_literal_list_citation_is_accepted(self):
        self.assertEqual(self.validate(self.correct),
                         (self.correct, "answered_with_validated_citation"))

    def test_unique_support_repairs_only_the_label_without_another_model_call(self):
        with patch.object(generator, "complete", return_value=self.wrong) as complete:
            answer, reason, safe = generator.generate_answer(
                "What is the ID insertion order in Task 2?", self.hits, return_diagnostics=True,
            )
        self.assertEqual(complete.call_count, 1)
        self.assertEqual(answer, self.correct)
        self.assertEqual(reason, "answered_with_validated_citation")
        self.assertEqual(complete.call_args.args[1], self.hits)
        self.assertEqual(safe, self.wrong)
        self.assertEqual(generator.CITATION_PATTERN.sub("", answer),
                         generator.CITATION_PATTERN.sub("", self.wrong))

    def test_ambiguous_support_is_refused_without_guessing_or_retrying(self):
        self.hits.append(hit(28, VALUES))
        with patch.object(generator, "complete", return_value=self.wrong) as complete:
            answer, reason, _ = generator.generate_answer("What is the order?", self.hits, return_diagnostics=True)
        self.assertEqual(complete.call_count, 1)
        self.assertEqual(answer, generator.REFUSAL)
        self.assertEqual(reason, "citation_numeric_sequence_mismatch")

    def test_correct_first_answer_needs_no_extra_model_call(self):
        with patch.object(generator, "complete", return_value=self.correct) as complete:
            self.assertEqual(generator.generate_answer("What is the order?", self.hits), self.correct)
        self.assertEqual(complete.call_count, 1)

    def test_user_reported_60_to_6_change_is_impossible_during_repair(self):
        changed = self.correct.replace("60,", "6.0,")
        with patch.object(generator, "complete", side_effect=[self.wrong, changed]) as complete:
            answer, reason, _ = generator.generate_answer(
                "What is the order?", self.hits, return_diagnostics=True,
            )
        self.assertEqual(complete.call_count, 1)
        self.assertEqual(answer, self.correct)
        self.assertEqual(reason, "answered_with_validated_citation")
        self.assertIn("60,", answer)
        self.assertNotIn("6.0,", answer)

    def test_same_values_in_a_different_order_do_not_support_the_citation(self):
        self.hits[1]["text"] = "Another order is 40, 20, 60, 10, 30, 70, 50, 5."
        self.assertEqual(self.validate(self.wrong)[1], "citation_numeric_sequence_mismatch")

    def test_duplicate_values_and_the_last_value_are_checked(self):
        examples = ["7, 7, 9", "7, 9, 7"]
        hits = [hit(1, examples[0]), hit(2, examples[1])]
        answer = examples[0] + ". [exercise.pptx, slide 2]"
        self.assertEqual(self.validate(answer, hits)[1], "citation_numeric_sequence_mismatch")
        self.assertEqual(tuple(map(int, _lists("Values: " + VALUES + ".")[0])),
                         (40, 20, 60, 10, 30, 50, 70, 5))

    def test_decimal_negative_and_inline_code_values_preserve_identity(self):
        hits = [hit(1, "Values: -2, 0.5, 10."), hit(2, "Other values: -2, 0.5, 11.")]
        answer = "Use `-2`, `0.5`, and `10`. [exercise.pptx, slide 1]"
        self.assertEqual(self.validate(answer, hits)[1], "answered_with_validated_citation")
        wrong = answer.replace("slide 1", "slide 2")
        self.assertEqual(self.validate(wrong, hits)[1], "citation_numeric_sequence_mismatch")

    def test_each_claim_uses_its_own_citation_group(self):
        answer = (self.correct + "\n\nOther IDs are 50, 150, 25, 75, 125, 175. "
                  "[exercise.pptx, slide 30]")
        self.assertEqual(self.validate(answer)[1], "answered_with_validated_citation")

    def test_appending_a_correct_citation_does_not_hide_an_unsupported_one(self):
        answer = self.wrong + " [exercise.pptx, slide 29]"
        self.assertEqual(self.validate(answer)[1], "citation_numeric_sequence_mismatch")

    def test_same_list_on_another_source_is_not_the_same_citation(self):
        hits = [hit(29, VALUES), hit(29, "A different list: 1, 2, 3.", source="other.pptx")]
        answer = VALUES + ". [other.pptx, slide 29]"
        self.assertEqual(self.validate(answer, hits)[1], "citation_numeric_sequence_mismatch")

    def test_page_and_slide_locations_remain_distinct(self):
        hits = [hit(29, VALUES), {"source":"exercise.pptx", "page":29,
                                  "text":"Other values: 1, 2, 3.", "rerank_score":5.0}]
        answer = VALUES + ". [exercise.pptx, p. 29]"
        self.assertEqual(self.validate(answer, hits)[1], "citation_numeric_sequence_mismatch")

    def test_unknown_citation_is_still_rejected_before_content_check(self):
        with patch.object(generator, "complete", return_value=self.wrong.replace("slide 30", "slide 99")) as complete:
            _, reason, _ = generator.generate_answer("What is the order?", self.hits, return_diagnostics=True)
        self.assertEqual(reason, "citation_not_in_retrieved_context")
        self.assertEqual(complete.call_count, 1)

    def test_partial_list_match_is_not_enough_for_automatic_repair(self):
        draft = "The first three IDs are 40, 20, 60. [exercise.pptx, slide 30]"
        with patch.object(generator, "complete", return_value=draft) as complete:
            answer, reason, _ = generator.generate_answer("What is the order?", self.hits, return_diagnostics=True)
        self.assertEqual(complete.call_count, 1)
        self.assertEqual((answer, reason), (generator.REFUSAL, "citation_numeric_sequence_mismatch"))

    def test_hidden_reasoning_is_removed_before_repair_and_diagnostics(self):
        with patch.object(generator, "complete", return_value="<think>private draft</think>" + self.wrong) as complete:
            answer, _, safe = generator.generate_answer("What is the order?", self.hits, return_diagnostics=True)
        self.assertEqual(answer, self.correct)
        self.assertEqual(safe, self.wrong)
        self.assertEqual(complete.call_count, 1)
        self.assertNotIn("private draft", str(complete.call_args.args[0]))
        self.assertNotIn("private draft", safe)

    def test_duplicate_chunks_at_one_supporting_location_remain_unambiguous(self):
        self.hits.append(hit(29, "Repeated excerpt: " + VALUES))
        with patch.object(generator, "complete", return_value=self.wrong):
            self.assertEqual(generator.generate_answer("What is the order?", self.hits), self.correct)

    def test_automatic_repair_does_not_cross_documents_or_location_types(self):
        cases = [
            ("other.pptx", "slide 29", hit(29, "Unrelated values: 1, 2, 3.", source="other.pptx")),
            ("exercise.pptx", "p. 29", {"source":"exercise.pptx", "page":29,
                                      "text":"Unrelated values: 1, 2, 3.", "rerank_score":5.0}),
        ]
        for source, location, other in cases:
            with self.subTest(source=source, location=location):
                draft = VALUES + f". [{source}, {location}]"
                with patch.object(generator, "complete", return_value=draft) as complete:
                    answer, reason, _ = generator.generate_answer(
                        "What is the order?", [self.hits[0], other], return_diagnostics=True,
                    )
                self.assertEqual(answer, generator.REFUSAL)
                self.assertEqual(reason, "citation_numeric_sequence_mismatch")
                self.assertEqual(complete.call_count, 1)

    def test_multiple_lists_are_not_repaired_under_a_shared_citation(self):
        draft = ("The first list is " + VALUES + ". The second is "
                 "50, 150, 25, 75, 125, 175. [exercise.pptx, slide 30]")
        with patch.object(generator, "complete", return_value=draft) as complete:
            answer, reason, _ = generator.generate_answer("What are the lists?", self.hits, return_diagnostics=True)
        self.assertEqual(answer, generator.REFUSAL)
        self.assertEqual(reason, "citation_numeric_sequence_mismatch")
        self.assertEqual(complete.call_count, 1)

    def test_repair_uses_the_matching_pdf_page_even_when_it_is_not_ranked_first(self):
        hits = [
            {"source":"notes.pdf", "page":43, "text":"Unrelated values: 1, 2, 3.", "rerank_score":9.0},
            {"source":"notes.pdf", "page":42, "text":VALUES, "rerank_score":2.0},
        ]
        draft = "The IDs are " + VALUES + ". [notes.pdf, p. 43]"
        with patch.object(generator, "complete", return_value=draft) as complete:
            answer = generator.generate_answer("What are the IDs?", hits)
        self.assertEqual(answer, draft.replace("p. 43", "p. 42"))
        self.assertEqual(complete.call_count, 1)

    def test_no_literal_match_is_not_used_to_reassign_a_derived_list(self):
        # Valid arithmetic need not quote its output verbatim from the source.
        hits = [hit(1, "Inputs: 1, 2, 3. Multiply each input by two.")]
        answer = "The doubled values are 2, 4, 6. [exercise.pptx, slide 1]"
        self.assertEqual(self.validate(answer, hits)[1], "answered_with_validated_citation")

    def test_three_value_excerpt_can_be_supported_by_a_longer_ordered_list(self):
        answer = "The first three IDs are 40, 20, 60. [exercise.pptx, slide 29]"
        self.assertEqual(self.validate(answer)[1], "answered_with_validated_citation")

    def test_two_values_do_not_trigger_the_three_value_guard(self):
        self.assertEqual(_lists("There are 10, 20."), [])

    def test_all_valid_literal_supporting_locations_are_allowed(self):
        hits = [hit(29, VALUES), hit(30, VALUES)]
        self.assertEqual(self.validate(self.wrong, hits)[1], "answered_with_validated_citation")


if __name__ == "__main__":
    unittest.main()
