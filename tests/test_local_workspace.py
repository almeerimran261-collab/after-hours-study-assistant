"""Upload lifecycle checks without models, Chroma, OCR, or network access."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ["RAG_MODE"] = "local"
from src import config, local_workspace as uploads


def document(source, text="A readable passage."):
    return SimpleNamespace(page_content=text, metadata={"source": source, "page": 1})


class Collection:
    def __init__(self, name):
        self.name, self.rows = name, []

    def add(self, **records):
        self.rows.extend(zip(records["documents"], records["metadatas"]))

    def count(self):
        return len(self.rows)


class Client:
    def __init__(self):
        self.collections = {"course_notes": Collection("course_notes")}
        self.deleted = []

    def create_collection(self, name, **kwargs):
        if name in self.collections:
            raise AssertionError("Collection overwritten")
        result = self.collections[name] = Collection(name)
        return result

    def delete_collection(self, name):
        self.deleted.append(name)
        del self.collections[name]


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        patches = [
            patch.object(config, "DEMO_MODE", False),
            patch.object(uploads, "_client", return_value=self.client),
            patch.object(uploads, "_extract_file", side_effect=lambda file, limit:
                         ([document(file.name)], [], 1)),
            patch.object(uploads, "_split", side_effect=lambda docs: docs),
            patch.object(uploads, "_embed", side_effect=lambda model, texts: [[1., 0.]] * len(texts)),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.workspace = uploads.LocalWorkspace()
        self.addCleanup(self.workspace.clear)
        self.files = [uploads.Upload("notes.pdf", b"PDF content"),
                      uploads.Upload("lecture.pptx", b"PPTX content")]

    def test_replacement_retires_only_previous_upload_index(self):
        first = self.workspace.replace(self.files, object())
        second = self.workspace.replace(self.files[:1], object())
        self.assertNotEqual(first.name, second.name)
        self.assertEqual(self.client.deleted, [first.name])
        self.assertIn("course_notes", self.client.collections)
        self.assertEqual(self.workspace.files, tuple(self.files[:1]))

    def test_failed_extraction_preserves_previous_batch(self):
        old = self.workspace.replace(self.files, object())
        with patch.object(uploads, "_extract_file", side_effect=ValueError("Damaged PDF")):
            with self.assertRaisesRegex(ValueError, "Damaged PDF"):
                self.workspace.replace(self.files[:1], object())
        self.assertIs(self.workspace.collection, old)
        self.assertEqual(self.workspace.files, tuple(self.files))
        self.assertEqual(self.client.deleted, [])

    def test_failed_embedding_removes_partial_index_and_keeps_previous_batch(self):
        old = self.workspace.replace(self.files, object())
        with patch.object(uploads, "_embed", side_effect=RuntimeError("Embedding failed")):
            with self.assertRaisesRegex(RuntimeError, "Embedding failed"):
                self.workspace.replace(self.files[:1], object())
        self.assertIs(self.workspace.collection, old)
        self.assertEqual(set(self.client.collections), {"course_notes", old.name})
        self.assertNotIn(old.name, self.client.deleted)

    def test_interruption_also_removes_partial_index(self):
        with patch.object(uploads, "_embed", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.workspace.replace(self.files, object())
        self.assertIsNone(self.workspace.collection)
        self.assertEqual(set(self.client.collections), {"course_notes"})

    def test_count_mismatch_does_not_commit_partial_build(self):
        old = self.workspace.replace(self.files, object())
        with patch.object(Collection, "add"):
            with self.assertRaisesRegex(RuntimeError, "verification failed"):
                self.workspace.replace(self.files[:1], object())
        self.assertIs(self.workspace.collection, old)

    def test_two_sessions_and_saved_collection_remain_isolated(self):
        other = uploads.LocalWorkspace()
        self.addCleanup(other.clear)
        first = self.workspace.replace(self.files, object())
        second = other.replace(self.files[:1], object())
        self.workspace.clear()
        self.assertNotIn(first.name, self.client.collections)
        self.assertIn(second.name, self.client.collections)
        self.assertIn("course_notes", self.client.collections)
        with self.assertRaises(ValueError):
            self.workspace._delete(second.name)

    def test_remove_rebuilds_only_remaining_sources_and_last_removal_clears(self):
        self.workspace.replace(self.files, object())
        remaining = self.workspace.remove(["notes.pdf"], object())
        self.assertEqual({meta["source"] for _, meta in remaining.rows}, {"lecture.pptx"})
        self.workspace.remove(["lecture.pptx"], object())
        self.assertIsNone(self.workspace.collection)
        self.assertEqual(self.workspace.files, ())
        self.assertEqual(set(self.client.collections), {"course_notes"})

    def test_progress_finishes_after_index_verification(self):
        events = []
        result = self.workspace.replace(self.files, object(), lambda value, text: events.append((value, text)))
        self.assertEqual(result.count(), 2)
        self.assertEqual(events[-1][0], 1.0)
        self.assertEqual([v for v, _ in events], sorted(v for v, _ in events))

    def test_bad_selections_are_rejected_before_extraction(self):
        cases = [[], [uploads.Upload("empty.pdf", b"")],
                 [uploads.Upload("old.ppt", b"x")],
                 [uploads.Upload("../outside.pdf", b"x")],
                 [uploads.Upload("C:\\secret.pdf", b"x")],
                 [uploads.Upload("bad,name.pdf", b"x")],
                 [uploads.Upload("bad[name].pdf", b"x")],
                 [uploads.Upload("same.pdf", b"x"), uploads.Upload("SAME.PDF", b"y")],
                 self.files * 4]
        for files in cases:
            with self.subTest(names=[f.name for f in files]):
                with patch.object(uploads, "_extract_file") as extract:
                    with self.assertRaises(ValueError):
                        self.workspace.replace(files, object())
                    extract.assert_not_called()
        valid = [uploads.Upload("My lecture.PDF", b"x")]
        self.assertEqual(uploads.validate_uploads(valid), tuple(valid))

    def test_size_limits_are_enforced(self):
        with patch.object(uploads, "MAX_FILE_BYTES", 2):
            with self.assertRaisesRegex(ValueError, "file limit"):
                uploads.validate_uploads([uploads.Upload("big.pdf", b"abc")])
        with patch.object(uploads, "MAX_TOTAL_BYTES", 2):
            with self.assertRaisesRegex(ValueError, "total limit"):
                uploads.validate_uploads([uploads.Upload("a.pdf", b"ab"), uploads.Upload("b.pdf", b"c")])

    def test_demo_blocks_upload_and_delete_before_dependencies_are_loaded(self):
        with patch.object(config, "DEMO_MODE", True), patch.object(uploads, "_client") as client:
            for operation in [lambda: self.workspace.replace(self.files, object()),
                              self.workspace.clear,
                              lambda: self.workspace.remove(["notes.pdf"], object())]:
                with self.assertRaisesRegex(ValueError, "only in local"):
                    operation()
            client.assert_not_called()

    def test_wrong_source_metadata_fails_before_index_creation(self):
        with patch.object(uploads, "_extract_file", return_value=([document("other.pdf")], [], 1)):
            with self.assertRaisesRegex(ValueError, "sources do not match"):
                self.workspace.replace(self.files[:1], object())
        self.assertEqual(set(self.client.collections), {"course_notes"})

    def test_unknown_remove_selection_preserves_active_batch(self):
        old = self.workspace.replace(self.files, object())
        with self.assertRaises(ValueError):
            self.workspace.remove(["missing.pdf"], object())
        self.assertIs(self.workspace.collection, old)


if __name__ == "__main__":
    unittest.main()
