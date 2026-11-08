"""Original public sample content; never reads the local course database."""
from hashlib import sha256

from src.config import COLLECTION_NAME, DATABASE_DIR, DEMO_MODE, PROJECT_ROOT

SOURCE = "Public Study Notes.pdf"
PAGES = (
    ("Stack operations", "A stack follows Last In, First Out (LIFO): the last item "
     "added is the first item removed. Push adds an item at the top. Pop removes "
     "the top item. Peek reads the top item without removing it."),
    ("Array stack: insertion", "Consider an array stack with capacity 5 and a "
     "top index initially equal to -1. The stack is full when top is 4. "
     "When the stack is full, push reports overflow and leaves the stack unchanged. "
     "When the stack is not full, push increments top and stores the new item "
     "at that index."),
    ("Array stack: removal", "The array stack is empty when top is -1. "
     "When the stack is empty, pop reports underflow and leaves the stack unchanged. "
     "When the stack is not empty, pop returns the item at top and decrements top."),
    ("Doubly linked lists", "A doubly linked list node has three fields: data, "
     "prev, and next. The prev pointer refers to the previous node; next refers "
     "to the following node. These pointers support traversal in both directions. "
     "In this non-circular list, the first node's prev and the last node's next "
     "are NULL."),
    ("insertAtEnd", "The insertAtEnd operation appends a new node to a non-circular "
     "doubly linked list. First set newNode->prev and newNode->next to NULL. "
     "When head is NULL, assign head = newNode and return. When the list is not "
     "empty, move temp from head to the last node, set temp->next = newNode, "
     "and set newNode->prev = temp. The head remains unchanged in this case."),
)


def sample_records():
    return [
        {"source": SOURCE, "page": page, "text": f"{title}\n\n{text}"}
        for page, (title, text) in enumerate(PAGES, 1)
    ]


def require_public_hits(hits):
    """Reject excerpts that are not exactly from this authored sample."""
    allowed = {(r["source"], r["page"], r["text"]) for r in sample_records()}
    if not hits or any(
        h.get("location_type", "page") != "page"
        or (h.get("source"), h.get("page"), h.get("text")) not in allowed
        for h in hits
    ):
        raise RuntimeError("Groq demo requests may use only the built-in public notes.")


def ensure_public_demo(model):
    """Create the separate sample PDF and index; safe to call again."""
    if not DEMO_MODE or DATABASE_DIR != PROJECT_ROOT / "demo_chroma_db":
        raise RuntimeError("Public sample setup requires RAG_MODE=demo.")
    import chromadb
    import fitz
    from src.embeddings import embed_texts

    rows = sample_records()
    fingerprint = sha256(repr(rows).encode()).hexdigest()
    folder = PROJECT_ROOT / "demo_data"
    folder.mkdir(exist_ok=True)
    with fitz.open() as pdf:
        for row in rows:
            page = pdf.new_page()
            remaining = page.insert_textbox(
                fitz.Rect(50, 60, 545, 780), row["text"], fontsize=12,
            )
            if remaining < 0:
                raise RuntimeError("Sample text exceeds its PDF page.")
        pdf.save(folder / SOURCE)

    client = chromadb.PersistentClient(path=str(DATABASE_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "public_sample_sha256": fingerprint},
    )
    expected = {f"public-page-{r['page']}": r for r in rows}
    stored = collection.get(include=["documents", "metadatas"])
    for key, text, meta in zip(stored["ids"], stored["documents"], stored["metadatas"]):
        if (key not in expected or text != expected[key]["text"]
                or meta.get("source") != SOURCE
                or meta.get("page") != expected[key]["page"]):
            raise RuntimeError("The demo index differs from the built-in public notes.")
    if (collection.metadata or {}).get("public_sample_sha256") != fingerprint:
        raise RuntimeError("The demo index uses a different sample version.")
    missing = [r for key, r in expected.items() if key not in stored["ids"]]
    if missing:
        vectors = embed_texts(model, [r["text"] for r in missing])
        collection.upsert(
            ids=[f"public-page-{r['page']}" for r in missing],
            documents=[r["text"] for r in missing],
            metadatas=[{"source": SOURCE, "page": r["page"], "location_type": "page"}
                       for r in missing],
            embeddings=vectors.tolist(),
        )
    if collection.count() != len(rows):
        raise RuntimeError("The demo index is incomplete.")
    return len(rows)
