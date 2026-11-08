import os
from io import BytesIO
from pathlib import Path

from langchain_core.documents import Document
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
import pytesseract


TESSERACT_DIR = Path(
    os.environ.get("TESSERACT_DIR", r"F:\AIModels\Tesseract-OCR")
)
TESSERACT_EXE = TESSERACT_DIR / "tesseract.exe"


def _extract_shape_content(shape, slide_number: int) -> tuple[list[str], int]:
    """Extract text/table content and OCR embedded pictures in a slide shape."""
    extracted: list[str] = []
    ocr_images = 0

    # Keep table rows together so column relationships remain understandable.
    if getattr(shape, "has_table", False):
        for row_number, row in enumerate(shape.table.rows, start=1):
            cells = [" ".join(cell.text.split()) for cell in row.cells]
            if any(cells):
                extracted.append(
                    f"Table row {row_number}: " + " | ".join(cells)
                )

    # Extract normal text boxes, titles, and other text-bearing shapes.
    elif getattr(shape, "has_text_frame", False):
        text = " ".join(shape.text.split())
        if text:
            extracted.append(text)

    # OCR picture shapes. This does not alter or save the original image.
    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        ocr_images = 1
        try:
            image = Image.open(BytesIO(shape.image.blob)).convert("RGB")
            recognized_text = pytesseract.image_to_string(
                image,
                lang="eng",
            ).strip()

            if recognized_text:
                extracted.append(
                    f"Text recognized from slide image {slide_number}:\n"
                    f"{recognized_text}"
                )
        except Exception as exc:
            print(
                f"  Warning: OCR failed for an image on slide "
                f"{slide_number}: {exc}"
            )

    return extracted, ocr_images


def load_pptx_slides(pptx_path: str | Path) -> list[Document]:
    """Extract native text, table rows, and OCR text from a .pptx file."""
    path = Path(pptx_path)

    if not path.exists():
        raise FileNotFoundError(f"PowerPoint file not found: {path}")

    if path.suffix.casefold() != ".pptx":
        raise ValueError(
            f"Expected a .pptx file, but received: {path.name}. "
            "Older .ppt files are not supported."
        )

    if not TESSERACT_EXE.exists():
        raise FileNotFoundError(
            f"Tesseract was not found at {TESSERACT_EXE}. "
            "Set the TESSERACT_DIR environment variable to its folder."
        )

    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)

    presentation = Presentation(str(path))
    documents: list[Document] = []
    ocr_image_count = 0
    ocr_slide_count = 0

    print(f"Reading {path.name} ({len(presentation.slides)} slides)")

    for slide_number, slide in enumerate(presentation.slides, start=1):
        slide_parts: list[str] = []
        slide_ocr_image_count = 0

        for shape in slide.shapes:
            parts, image_count = _extract_shape_content(shape, slide_number)
            slide_parts.extend(parts)
            slide_ocr_image_count += image_count

        ocr_image_count += slide_ocr_image_count
        if slide_ocr_image_count:
            ocr_slide_count += 1

        slide_text = "\n".join(slide_parts).strip()

        if not slide_text:
            print(
                f"  Warning: slide {slide_number} has no extractable text; skipped."
            )
            continue

        extraction_method = (
            "python-pptx+ocr"
            if slide_ocr_image_count
            else "python-pptx"
        )

        documents.append(
            Document(
                page_content=slide_text,
                metadata={
                    "source": path.name,
                    # The current index requires an integer "page" field.
                    # It temporarily stores the slide number too.
                    "page": slide_number,
                    "slide": slide_number,
                    "location_type": "slide",
                    "content_type": "slide",
                    "extraction_method": extraction_method,
                },
            )
        )

    if not documents:
        raise ValueError(
            f"No slide text, table content, or image text could be "
            f"extracted from {path.name}."
        )

    print(f"Slides with extractable text: {len(documents)}")
    print(f"Slides with picture OCR attempted: {ocr_slide_count}")
    print(f"Picture images sent to OCR: {ocr_image_count}")
    return documents
