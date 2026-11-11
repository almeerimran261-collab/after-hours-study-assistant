"""Native-file integration checks, enabled when local dependencies are installed."""
import importlib.util
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ["RAG_MODE"] = "local"
from src.local_workspace import Upload, _extract_file

LOCAL_DEPENDENCIES = all(importlib.util.find_spec(name) is not None for name in
                         ["pymupdf", "pdfplumber", "pptx", "pytesseract", "PIL",
                          "langchain_core", "langchain_text_splitters"])


@unittest.skipUnless(LOCAL_DEPENDENCIES, "Install requirements-local.txt for file integration checks")
class LocalDocumentTests(unittest.TestCase):
    def test_uppercase_pdf_preserves_pages_and_source(self):
        import pymupdf
        with pymupdf.open() as pdf:
            for number in [1, 2]:
                pdf.new_page().insert_text((50, 70), f"Page {number}. A stack follows Last In, First Out order.")
            data = pdf.tobytes()
        documents, warnings, pages = _extract_file(Upload("My Notes.PDF", data), 300)
        self.assertEqual(pages, 2)
        self.assertEqual({d.metadata["page"] for d in documents}, {1, 2})
        self.assertEqual({d.metadata["source"] for d in documents}, {"My Notes.PDF"})
        self.assertEqual(warnings, [])

    def test_native_pptx_and_table_work_without_tesseract_and_keep_slide_numbers(self):
        from pptx import Presentation
        from pptx.util import Inches
        from src import pptx_ingest
        slides = Presentation()
        slide = slides.slides.add_slide(slides.slide_layouts[6])
        slide.shapes.add_textbox(Inches(1), Inches(1), Inches(7), Inches(1)).text = "Stack overflow"
        table = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(5), Inches(2)).table
        table.cell(0, 0).text, table.cell(0, 1).text = "Operation", "Condition"
        table.cell(1, 0).text, table.cell(1, 1).text = "Push", "Overflow"
        stream = BytesIO()
        slides.save(stream)
        with TemporaryDirectory() as directory, patch.object(pptx_ingest, "TESSERACT_EXE", Path(directory) / "missing.exe"):
            documents, warnings, pages = _extract_file(Upload("Lecture.PPTX", stream.getvalue()), 300)
        self.assertEqual(pages, 1)
        self.assertIn("Push | Overflow", documents[0].page_content)
        self.assertEqual(documents[0].metadata["location_type"], "slide")
        self.assertEqual(documents[0].metadata["slide"], 1)
        self.assertEqual(documents[0].metadata["source"], "Lecture.PPTX")
        self.assertEqual(warnings, [])

    def test_missing_picture_ocr_is_reported_while_native_text_remains(self):
        from PIL import Image
        from pptx import Presentation
        from pptx.util import Inches
        from src import pptx_ingest
        slides = Presentation()
        slide = slides.slides.add_slide(slides.slide_layouts[6])
        slide.shapes.add_textbox(Inches(1), Inches(1), Inches(7), Inches(1)).text = "Native lecture text"
        picture = BytesIO()
        Image.new("RGB", (100, 30), "white").save(picture, format="PNG")
        picture.seek(0)
        slide.shapes.add_picture(picture, Inches(1), Inches(2))
        stream = BytesIO()
        slides.save(stream)
        with TemporaryDirectory() as directory, patch.object(pptx_ingest, "TESSERACT_EXE", Path(directory) / "missing.exe"):
            documents, warnings, _ = _extract_file(Upload("Pictures.pptx", stream.getvalue()), 300)
        self.assertIn("Native lecture text", documents[0].page_content)
        self.assertTrue(any("image OCR skipped" in warning for warning in warnings))

    def test_blank_damaged_and_password_protected_pdfs_are_rejected(self):
        import pymupdf
        with pymupdf.open() as pdf:
            pdf.new_page()
            blank = pdf.tobytes()
            locked = pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256,
                                 owner_pw="owner", user_pw="student")
        for data in [blank, b"not a PDF", locked]:
            with self.subTest(size=len(data)):
                with self.assertRaises(Exception):
                    _extract_file(Upload("unreadable.pdf", data), 300)

    def test_page_limit_is_checked_before_parsing_text(self):
        import pymupdf
        with pymupdf.open() as pdf:
            pdf.new_page()
            data = pdf.tobytes()
        with patch("src.ingest.load_pdf_pages") as loader:
            with self.assertRaisesRegex(ValueError, "at most 300"):
                _extract_file(Upload("notes.pdf", data), 0)
            loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
