"""Hand-checked metric examples; no models or API calls."""
import unittest

from eval.public_retrieval_benchmark import score_result, summarize


class RetrievalMetricTests(unittest.TestCase):
    def test_first_place_counts_as_top_one_hit(self):
        scores = score_result(["gold", "other"], "gold")
        self.assertEqual(scores["rank_at_5"], 1)
        self.assertEqual(scores["hit_at_1"], 1)
        self.assertEqual(scores["mrr_at_5"], 1)

    def test_second_place_uses_one_based_reciprocal_rank(self):
        scores = score_result(["other", "gold"], "gold")
        self.assertEqual(scores["hit_at_1"], 0)
        self.assertEqual(scores["hit_at_5"], 1)
        self.assertEqual(scores["rank_at_5"], 2)
        self.assertEqual(scores["mrr_at_5"], 0.5)

    def test_sixth_place_is_a_miss_at_five(self):
        scores = score_result(
            ["a", "b", "c", "d", "e", "gold"], "gold"
        )
        self.assertEqual(scores["hit_at_5"], 0)
        self.assertEqual(scores["rank_at_5"], 0)
        self.assertEqual(scores["mrr_at_5"], 0)

    def test_misses_remain_in_the_average(self):
        rows = []
        examples = [
            (["gold"], 10),
            (["other", "gold"], 20),
            (["other"], 30),
        ]
        for ids, latency in examples:
            rows.append({
                **score_result(ids, "gold"),
                "latency_ms": latency,
            })

        result = summarize(rows)
        self.assertAlmostEqual(result["hit_at_1"], 1 / 3)
        self.assertAlmostEqual(result["hit_at_5"], 2 / 3)
        self.assertAlmostEqual(result["mrr_at_5"], 0.5)
        self.assertEqual(result["mean_latency_ms"], 20)
        self.assertEqual(result["p95_latency_ms"], 30)


if __name__ == "__main__":
    unittest.main()