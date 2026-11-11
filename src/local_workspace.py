"""Session-owned local uploads. Existing course collections are never mutated."""
from dataclasses import dataclass
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from uuid import uuid4
import zipfile

from src import config


MAX_FILES = 6
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 60 * 1024 * 1024
MAX_PAGES = 300
MAX_CHUNKS = 5000
BATCH_SIZE = 32


@dataclass(frozen=True)
class Upload:
    name: str
    data: bytes


def require_local():
    if config.DEMO_MODE:
        raise ValueError("Document uploads are available only in local Ollama mode.")


def validate_uploads(files):
    require_local()
    files = tuple(files)
    if not 1 <= len(files) <= MAX_FILES:
        raise ValueError(f"Choose between 1 and {MAX_FILES} PDF/PPTX files.")
    names = set()
    total = 0
    for file in files:
        name = file.name
        if (not isinstance(name, str) or not name.strip()
                or name != name.strip()
                or any(c in name for c in '/\\,[]\r\n')
                or Path(name).name != name):
            raise ValueError(
                "Use plain filenames without paths, commas, or square brackets "
                "so citations can identify the document."
            )
        if Path(name).suffix.casefold() not in {".pdf", ".pptx"}:
            raise ValueError(f"{name}: only PDF and PPTX files are supported.")
        if name.casefold() in names:
            raise ValueError(f"Duplicate filename: {name}. Rename one file first.")
        names.add(name.casefold())
        if not isinstance(file.data, bytes) or not file.data:
            raise ValueError(f"{name} is empty. Select a readable document.")
        if len(file.data) > MAX_FILE_BYTES:
            raise ValueError(f"{name} exceeds the 20 MB file limit.")
        total += len(file.data)
    if total > MAX_TOTAL_BYTES:
        raise ValueError("The selected files exceed the 60 MB total limit.")
    return files


def _extract_file(file, remaining_pages):
    """Keep original citation names; delete staging files even after failures."""
    warnings = []
    with TemporaryDirectory(prefix="after_hours_upload_") as directory:
        path = Path(directory) / file.name
        path.write_bytes(file.data)
        if path.suffix.casefold() == ".pdf":
            import pymupdf
            from src.ingest import load_pdf_pages
            with pymupdf.open(path) as pdf:
                if pdf.needs_pass:
                    raise ValueError("Password-protected PDFs are not supported.")
                pages = len(pdf)
            loader = lambda: load_pdf_pages(Path(directory), on_warning=warnings.append)
        else:
            from src.pptx_ingest import load_pptx_slides
            with zipfile.ZipFile(path) as archive:
                pages = sum(bool(re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
                            for name in archive.namelist())
            loader = lambda: load_pptx_slides(path, on_warning=warnings.append)
        if not 1 <= pages <= remaining_pages:
            raise ValueError(f"Choose documents totaling at most {MAX_PAGES} pages/slides.")
        documents = loader()
    if not documents or not any(doc.page_content.strip() for doc in documents):
        raise ValueError("No readable text was found. Scanned content needs working OCR.")
    return documents, warnings, pages


def _split(documents):
    from src.chunking import chunk_pages
    return chunk_pages(documents)


def _embed(model, texts):
    from src.embeddings import embed_texts
    return embed_texts(model, texts)


def _client():
    import chromadb
    from chromadb.config import Settings
    return chromadb.EphemeralClient(Settings(anonymized_telemetry=False))


class LocalWorkspace:
    """Swap only after a full successful build; own only our random collection names.

    Chroma's in-memory client may be process-shared, so every workspace and build
    uses a random name and chat receives only the current session's collection.
    """

    def __init__(self):
        self.collection = None
        self.files = ()
        self.warnings = []
        self._client = None
        self._owned = set()

    def _delete(self, name):
        if name not in self._owned:
            raise ValueError("Cannot delete a collection outside this upload session.")
        self._client.delete_collection(name=name)
        self._owned.remove(name)

    def replace(self, files, model, on_progress=None):
        files = validate_uploads(files)
        progress = on_progress or (lambda value, text: None)
        progress(0.02, "Checking documents…")
        documents, warnings, pages = [], [], 0
        for index, file in enumerate(files):
            progress(0.05 + 0.25 * index / len(files), f"Reading {file.name}…")
            try:
                extracted, notices, count = _extract_file(file, MAX_PAGES - pages)
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "Install the local processing dependencies with "
                    "python -m pip install -r requirements-local.txt."
                ) from exc
            except Exception as exc:
                raise ValueError(f"Could not read {file.name}: {exc}") from exc
            documents.extend(extracted)
            warnings.extend(notices)
            pages += count
        progress(0.35, "Splitting text into searchable passages…")
        chunks = _split(documents)
        if not 1 <= len(chunks) <= MAX_CHUNKS:
            raise ValueError(f"Choose a smaller batch: expected 1–{MAX_CHUNKS} passages.")
        if {doc.metadata.get("source") for doc in chunks} != {f.name for f in files}:
            raise ValueError("Extracted sources do not match the selected files.")
        if self._client is None:
            self._client = _client()
        name = f"uploads_{uuid4().hex}"
        new_collection = self._client.create_collection(
            name=name, metadata={"hnsw:space": "cosine"}, embedding_function=None,
        )
        self._owned.add(name)
        try:
            for start in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[start:start + BATCH_SIZE]
                texts = [doc.page_content for doc in batch]
                vectors = _embed(model, texts)
                new_collection.add(
                    ids=[f"chunk_{i}" for i in range(start, start + len(batch))],
                    documents=texts, metadatas=[doc.metadata for doc in batch],
                    embeddings=vectors.tolist() if hasattr(vectors, "tolist") else vectors,
                )
                progress(0.4 + 0.55 * (start + len(batch)) / len(chunks),
                         f"Indexing passages · {start + len(batch)}/{len(chunks)}")
            if new_collection.count() != len(chunks):
                raise RuntimeError("Index verification failed; the previous batch is still active.")
        except BaseException:
            # Includes interrupted Streamlit runs; never remove the working index.
            try:
                self._delete(name)
            except Exception:
                pass  # Retain ownership so clear()/session cleanup can retry.
            raise
        old = self.collection
        self.collection, self.files = new_collection, files
        self.warnings = list(dict.fromkeys(warnings))
        if old is not None:
            try:
                self._delete(old.name)
            except Exception:
                self.warnings.append("A retired upload index will be cleared when this session closes.")
        progress(1.0, "Ready to chat with your documents.")
        return self.collection

    def remove(self, names, model, on_progress=None):
        require_local()
        names = set(names)
        if not names or not names <= {file.name for file in self.files}:
            raise ValueError("Select uploaded documents to remove.")
        remaining = [file for file in self.files if file.name not in names]
        if remaining:
            return self.replace(remaining, model, on_progress)
        self.clear()
        return None

    def clear(self):
        require_local()
        # Delete only collection names created by this instance.
        for name in tuple(self._owned):
            self._delete(name)
        self.collection, self.files, self.warnings = None, (), []

    def __del__(self):
        # Best effort when Streamlit releases a disconnected session. Nothing is
        # written to chroma_db; a process restart also releases ephemeral indexes.
        for name in tuple(getattr(self, "_owned", ())):
            try:
                self._delete(name)
            except Exception:
                pass
