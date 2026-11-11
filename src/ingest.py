import os
from pathlib import Path
from src.pptx_ingest import load_pptx_slides
import pdfplumber
import pymupdf
from langchain_core.documents import Document

from src.config import DATA_DIR


# Tesseract is installed outside the project on the F: drive.
# Override this location later with the TESSERACT_DIR environment variable.
TESSERACT_DIR = Path(
    os.environ.get("TESSERACT_DIR", r"F:\AIModels\Tesseract-OCR")
)
TESSDATA_DIR = TESSERACT_DIR / "tessdata"

# Try OCR only when a page contains fewer than this many native text characters.
OCR_TEXT_THRESHOLD = 40
OCR_LANGUAGE = "eng"
OCR_DPI = 200

# A conservative filter: require at least three rows with at least two
# non-empty cells per row. This helps reject diagrams and page-layout fragments.
MIN_TABLE_ROWS = 3
MIN_MULTI_CELL_ROW_RATIO = 0.80


def _extract_page_text(page, source_name: str, page_number: int, on_warning=None) -> tuple[str, str]:
    """Use normal PDF text when available; fall back to OCR on sparse pages."""
    text = page.get_text("text").strip()

    if len(text) >= OCR_TEXT_THRESHOLD:
        return text, "native"

    tesseract_exe = TESSERACT_DIR / "tesseract.exe"
    if not tesseract_exe.exists() or not TESSDATA_DIR.exists():
        (on_warning or print)(
            f"  Warning: page {page_number} in {source_name} has little selectable "
            "text, but Tesseract was not found. Keeping any available text."
        )
        return text, "native"

    # Make Tesseract discoverable for this Python process only.
    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(os.pathsep)
    if str(TESSERACT_DIR) not in path_parts:
        os.environ["PATH"] = str(TESSERACT_DIR) + os.pathsep + current_path

    os.environ["TESSDATA_PREFIX"] = str(TESSDATA_DIR)

    try:
        ocr_text_page = page.get_textpage_ocr(
            language=OCR_LANGUAGE,
            dpi=OCR_DPI,
            full=True,
            tessdata=str(TESSDATA_DIR),
        )
        ocr_text = page.get_text("text", textpage=ocr_text_page).strip()

        if ocr_text:
            print(f"  OCR used on page {page_number} in {source_name}")
            return ocr_text, "ocr"

        (on_warning or print)(f"OCR found no text on page {page_number} in {source_name}")
        return text, "native"

    except Exception as exc:
        (on_warning or print)(
            f"  Warning: OCR failed on page {page_number} in {source_name}: {exc}"
        )
        return text, "native"


def _clean_table(table: list[list[str | None]]) -> list[list[str]]:
    """Clean table rows and repair adjacent repeated cells in over-wide rows."""
    cleaned_rows: list[list[str]] = []

    for raw_row in table:
        cells = []
        for raw_cell in raw_row:
            cell = " ".join(str(raw_cell).split()) if raw_cell is not None else ""
            if cell:
                cells.append(cell)

        if cells:
            cleaned_rows.append(cells)

    if len(cleaned_rows) < 2:
        return cleaned_rows

    # Most rows should have the same number of non-empty cells.
    # Use the most common row width as the expected table width.
    width_counts: dict[int, int] = {}
    for row in cleaned_rows:
        width_counts[len(row)] = width_counts.get(len(row), 0) + 1

    expected_width = max(
        width_counts,
        key=lambda width: (width_counts[width], width),
    )

    normalized_rows: list[list[str]] = []

    for original_row in cleaned_rows:
        row = original_row.copy()

        # Only collapse consecutive duplicates when a row has too many cells.
        # This preserves valid repeated values such as O(1) | O(1) in a row
        # whose width is already correct.
        while len(row) > expected_width:
            repeated_pair = next(
                (
                    index
                    for index in range(len(row) - 1)
                    if row[index] == row[index + 1]
                ),
                None,
            )

            if repeated_pair is None:
                # The structure is ambiguous; reject this candidate instead
                # of guessing how its cells should be aligned.
                return []

            row.pop(repeated_pair + 1)

        normalized_rows.append(row)

    return normalized_rows



def _looks_like_real_table(rows: list[list[str]]) -> bool:
    """Reject sparse diagram fragments and keep dense, multi-row tables."""
    if len(rows) < MIN_TABLE_ROWS:
        return False

    multi_cell_rows = sum(1 for row in rows if len(row) >= 2)
    if multi_cell_rows < MIN_TABLE_ROWS:
        return False

    return (multi_cell_rows / len(rows)) >= MIN_MULTI_CELL_ROW_RATIO


def _format_table_rows(rows: list[list[str]]) -> str:
    """Render the table as searchable text while keeping its row relationships."""
    lines = [
        "Structured table extracted from this PDF page.",
        "Cells in each row are separated by |.",
    ]

    for row_number, row in enumerate(rows, start=1):
        lines.append(f"Row {row_number}: " + " | ".join(row))

    return "\n".join(lines)


def load_pdf_pages(data_dir: Path = DATA_DIR, *, on_warning=None) -> list[Document]:
    """Read PDF pages, OCR sparse pages, and add reliable tables with page metadata."""
    pdf_paths = sorted(path for path in data_dir.iterdir() if path.suffix.casefold() == ".pdf")
    if not pdf_paths:
        raise FileNotFoundError(
            f"No PDF files found in {data_dir}. Copy at least one searchable PDF there."
        )

    documents: list[Document] = []
    page_document_count = 0
    ocr_page_count = 0
    table_candidate_count = 0
    table_document_count = 0

    for pdf_path in pdf_paths:
        with pymupdf.open(pdf_path) as pdf, pdfplumber.open(pdf_path) as layout_pdf:
            print(f"Reading {pdf_path.name} ({len(pdf)} pages)")

            for page_number, page in enumerate(pdf, start=1):
                text, extraction_method = _extract_page_text(
                    page,
                    source_name=pdf_path.name,
                    page_number=page_number,
                    on_warning=on_warning,
                )

                if text:
                    documents.append(
                        Document(
                            page_content=text,
                            metadata={
                                "source": pdf_path.name,
                                "page": page_number,
                                "content_type": "page",
                                "extraction_method": extraction_method,
                            },
                        )
                    )
                    page_document_count += 1

                    if extraction_method == "ocr":
                        ocr_page_count += 1
                else:
                    (on_warning or print)(
                        f"  Warning: page {page_number} has no extractable text "
                        "and will be skipped."
                    )

                # Extract structured tables separately so row/column meaning
                # is not lost in the normal page-text extraction.
                if page_number > len(layout_pdf.pages):
                    continue

                try:
                    table_page = layout_pdf.pages[page_number - 1].dedupe_chars()
                    raw_tables = table_page.extract_tables() or []
                except Exception as exc:
                    (on_warning or print)(
                        f"  Warning: table extraction failed on page {page_number} "
                        f"of {pdf_path.name}: {exc}"
                    )
                    continue


                table_candidate_count += len(raw_tables)

                for raw_table in raw_tables:
                    rows = _clean_table(raw_table)
                    if not _looks_like_real_table(rows):
                        continue

                    documents.append(
                        Document(
                            page_content=_format_table_rows(rows),
                            metadata={
                                "source": pdf_path.name,
                                "page": page_number,
                                "content_type": "table",
                                "extraction_method": "pdfplumber_table",
                            },
                        )
                    )
                    table_document_count += 1

    if page_document_count == 0:
        raise ValueError(
            "No text could be extracted from the PDFs. Check that the files are "
            "readable and that Tesseract is installed for scanned pages."
        )

    print(f"Page documents extracted: {page_document_count}")
    print(f"Table candidates detected: {table_candidate_count}")
    print(f"Structured table documents kept: {table_document_count}")
    print(f"Pages processed with OCR: {ocr_page_count}")

    return documents
def load_course_documents(data_dir: Path = DATA_DIR) -> list[Document]:
    """Load PDF pages/tables and PowerPoint slides from the course data folder."""
    pdf_paths = sorted(data_dir.glob("*.pdf"))
    pptx_paths = sorted(data_dir.glob("*.pptx"))

    if not pdf_paths and not pptx_paths:
        raise FileNotFoundError(
            f"No .pdf or .pptx files found in {data_dir}."
        )

    documents: list[Document] = []

    # Keep existing PDF parsing, table extraction, and OCR behavior.
    if pdf_paths:
        documents.extend(load_pdf_pages(data_dir))

    # Add each presentation as slide-level documents.
    for pptx_path in pptx_paths:
        documents.extend(load_pptx_slides(pptx_path))

    print(f"PDF files found: {len(pdf_paths)}")
    print(f"PowerPoint files found: {len(pptx_paths)}")
    print(f"Total page, table, and slide documents: {len(documents)}")

    return documents

