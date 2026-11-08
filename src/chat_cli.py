import argparse
from src.config import COLLECTION_NAME
from src.course_collections import open_collection
from src.embeddings import load_embedding_model
from src.generator import generate_answer
from src.memory import ConversationMemory
from src.retriever import retrieve_chunks


def main():
    parser = argparse.ArgumentParser(
        description="Chat with one document collection."
    )
    parser.add_argument("--collection", default=COLLECTION_NAME)
    args = parser.parse_args()

    collection = open_collection(args.collection)
    if collection.count() == 0:
        raise ValueError(
            "The index is empty. Check your existing database path."
        )

    print(f"Collection: {collection.name} ({collection.count()} chunks)")
    print("Loading the embedding model on CPU...")
    model = load_embedding_model()
    memory = ConversationMemory()

    print("Chat ready. /clear resets question memory; /exit ends the chat.")
    print("Memory lasts for this session and tracks recent questions.")

    while True:
        try:
            question = input("\nYou: ").strip()

            if question.casefold() in {"/exit", "exit", "quit", "/quit"}:
                break

            if question.casefold() == "/clear":
                memory.clear()
                print("Question memory cleared.")
                continue

            if not question:
                continue

            standalone, clarify = memory.rewrite(question)

            if clarify:
                print(
                    f"Please restate your full question: {standalone}"
                )
                continue

            print(f"Retrieval question: {standalone}")
            hits = retrieve_chunks(standalone, model, collection)

            answer, reason, _ = generate_answer(
                standalone, hits, return_diagnostics=True
            )

            memory.remember(question)
            print(f"\nAssistant: {answer}")
            print(f"\nDiagnostic reason: {reason}")
            print("Retrieved evidence:")

            for rank, hit in enumerate(hits, 1):
                if hit.get("location_type") == "slide":
                    location = f"slide {hit['slide']}"
                else:
                    location = f"page {hit['page']}"

                print(
                    f"\n{rank}. {hit['source']}, {location} "
                    f"| rerank_score={hit.get('rerank_score')}"
                )
                print(hit["text"])

        except (KeyboardInterrupt, EOFError):
            print("\nChat ended.")
            break
        except (RuntimeError, ValueError) as exc:
            print(f"Could not complete this turn: {exc}")


if __name__ == "__main__":
    main()