import argparse

from src.chunking import chunk_pages
from src.config import DATA_DIR
from src.embeddings import load_embedding_model
from src.generator import generate_answer
from src.ingest import load_course_documents
from src.retriever import retrieve_chunks
from src.vectorstore import get_collection, rebuild_index


def ingest_command() -> None:
    documents = load_course_documents()
    chunks = chunk_pages(documents)
    print(f"Loaded {len(documents)} page, table, and slide documents.")
    print(f"Created {len(chunks)} chunks (about 900 characters each).")
    print("Loading the embedding model on CPU; the first run downloads it once...")
    model = load_embedding_model()
    total = rebuild_index(chunks, model)
    print(f"Index ready: {total} chunks stored in {DATA_DIR.parent / 'chroma_db'}.")



def ask_command(question: str) -> None:
    collection = get_collection()
    if collection.count() == 0:
        raise ValueError("The index is empty. First run: python -m src.phase1_cli ingest")

    print("Loading the embedding model on CPU...")
    model = load_embedding_model()
    hits = retrieve_chunks(question, model, collection)
    answer = generate_answer(question, hits)

    print("\nANSWER\n")
    print(answer)
    print("\nRETRIEVED PASSAGES (retrieval diagnostics; answer citations are validated)\n")
    for rank, hit in enumerate(hits, start=1):
        if hit.get("location_type") == "slide":
            location = f"slide {int(hit['slide'])}"
        else:
            location = f"page {int(hit['page'])}"

        print(
            f"{rank}. {hit['source']}, {location} "
            f"(cosine distance {hit['distance']:.4f})"
        )
        print(hit["text"][:400].replace("\n", " "))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local PDF RAG prototype: index PDFs or ask a question."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ingest", help="Read PDFs in data/ and rebuild the local index")
    ask_parser = subparsers.add_parser("ask", help="Ask a question about the indexed PDFs")
    ask_parser.add_argument("question", nargs="+", help="Question in quotation marks")
    args = parser.parse_args()

    if args.command == "ingest":
        ingest_command()
    else:
        ask_command(" ".join(args.question))


if __name__ == "__main__":
    main()
