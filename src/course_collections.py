import argparse
import re
from collections import Counter
from pathlib import Path

import chromadb

from src.config import COLLECTION_NAME, DATABASE_DIR


def get_client():
    database = Path(DATABASE_DIR)
    if not (database / "chroma.sqlite3").is_file():
        raise FileNotFoundError(
            f"Existing database not found: {database}"
        )
    return chromadb.PersistentClient(path=str(database))


def open_collection(name=COLLECTION_NAME):
    collection = get_client().get_collection(name=name)
    expected = (collection.metadata or {}).get(
        "phase6b_expected_count"
    )
    if expected is not None and collection.count() != expected:
        raise ValueError(
            f"Collection {name} is incomplete or has changed."
        )
    return collection


def show_collections():
    client = get_client()
    for item in client.list_collections():
        name = item if isinstance(item, str) else item.name
        collection = client.get_collection(name=name)
        records = collection.get(include=["metadatas"])
        counts = Counter(
            meta["source"] for meta in records["metadatas"]
        )
        print(f"\n{name}: {collection.count()} chunks")
        for source, count in sorted(counts.items()):
            print(f"  {source}: {count}")


def create_course(name, sources):
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,62}", name):
        raise ValueError(
            "Use 3-63 lowercase letters, digits, or underscores; "
            "start with a letter."
        )
    if name == COLLECTION_NAME:
        raise ValueError(
            "Choose a new name; the original collection is protected."
        )

    sources = sorted(set(sources))
    if not sources:
        raise ValueError("Select at least one source filename.")

    client = get_client()
    original = client.get_collection(name=COLLECTION_NAME)
    original_count = original.count()

    records = original.get(
        where={"source": {"$in": sources}},
        include=["documents", "metadatas", "embeddings"],
    )
    found = {
        meta["source"] for meta in records["metadatas"]
    }
    missing = set(sources) - found
    if missing:
        raise ValueError(
            f"Files absent from the original index: {sorted(missing)}"
        )

    space = (original.metadata or {}).get("hnsw:space", "l2")
    if space != "cosine":
        raise ValueError(
            "Expected the original cosine collection. "
            "Check the index first."
        )

    ids = records["ids"]
    target = client.create_collection(
        name=name,
        metadata={
            "hnsw:space": "cosine",
            "phase6b_expected_count": len(ids),
            "phase6b_parent": COLLECTION_NAME,
        },
    )

    try:
        for start in range(0, len(ids), 64):
            vectors = records["embeddings"][start:start + 64]
            target.add(
                ids=ids[start:start + 64],
                documents=records["documents"][start:start + 64],
                metadatas=records["metadatas"][start:start + 64],
                embeddings=(
                    vectors.tolist()
                    if hasattr(vectors, "tolist")
                    else vectors
                ),
            )

        if (
            target.count() != len(ids)
            or original.count() != original_count
        ):
            raise RuntimeError(
                "Collection counts changed unexpectedly during copying."
            )
    except Exception:
        # Remove only the new target if its copy failed.
        client.delete_collection(name=name)
        raise

    print(f"Created {name}: {target.count()} chunks.")
    print(
        f"Original {COLLECTION_NAME}: {original.count()} chunks."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Copy indexed files into separate local collections."
    )
    commands = parser.add_subparsers(
        dest="command", required=True
    )
    commands.add_parser("list")

    create = commands.add_parser("create")
    create.add_argument("name")
    create.add_argument("--source", action="append", required=True)

    args = parser.parse_args()
    if args.command == "list":
        show_collections()
    else:
        create_course(args.name, args.source)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"Collection command failed: {exc}")