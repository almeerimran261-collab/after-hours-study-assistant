"""Fixed synthetic retrieval benchmark: 40 pages and 40 questions."""
import csv
from hashlib import sha256
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
from statistics import mean
import time
from uuid import uuid4

# Each row: PDF filename, page, heading, original text, question.
# Labels were fixed before measuring retrieval.
CASES = [
    ("Stacks.pdf", 1, "Stack order",
     "A stack follows Last In, First Out (LIFO). Push adds an item at the top, "
     "pop removes the top item, and peek reads the top item without removing it.",
     "In a stack, which inserted item leaves first, and what does LIFO stand for?"),
    ("Stacks.pdf", 2, "Push and overflow",
     "For this array stack, capacity is 5 and top begins at -1. A push when top "
     "is 4 reports overflow and changes nothing. Otherwise increment top and store "
     "the new item at that index.",
     "What should push do if the five-slot array stack already has top equal to 4?"),
    ("Stacks.pdf", 3, "Pop and underflow",
     "The array stack is empty when top is -1. Pop on an empty stack reports "
     "underflow without reading the array. Otherwise pop returns the item at top "
     "and then decrements top.",
     "Which error occurs when removing an item from a stack whose top is -1?"),
    ("Stacks.pdf", 4, "Checking brackets",
     "To check bracket nesting, scan left to right. Push opening brackets. For a "
     "closing bracket, require a matching opening bracket at the stack top and "
     "pop it. Reject a mismatch or an empty stack at a closing bracket. At the "
     "end, accept only if the stack is empty.",
     "In bracket matching, why reject a closing parenthesis when the stack is empty?"),
    ("Stacks.pdf", 5, "Postfix operands",
     "In postfix evaluation, push each numeric operand. At a binary operator, "
     "pop the right operand first and the left operand second. Compute left "
     "operator right, then push the result. This order matters for subtraction "
     "and division.",
     "For postfix subtraction, is the first popped value the left or right operand?"),
    ("Queues.pdf", 1, "Queue order",
     "A queue follows First In, First Out (FIFO). Enqueue inserts at the rear "
     "and dequeue removes from the front. Items with equal priority leave in "
     "their arrival order in this ordinary queue.",
     "Which end is used to insert into an ordinary FIFO queue, and which end removes items?"),
    ("Queues.pdf", 2, "Linear array limitation",
     "In this simple linear array queue, rear only increases and removed cells "
     "are not reused until the queue is reset. If rear reaches the final array "
     "index, another enqueue fails even if earlier positions became free after "
     "dequeues. A circular representation reuses those positions.",
     "Why can a simple linear array queue reject insertion despite free cells near its beginning?"),
    ("Queues.pdf", 3, "Circular array conditions",
     "For this circular queue of capacity 5, front and rear start at -1. Empty "
     "means front is -1. Full means (rear + 1) % 5 equals front. On the first "
     "enqueue set front and rear to 0. Removing the last remaining item resets "
     "both indices to -1.",
     "What formula detects a full circular queue with five array positions?"),
    ("Queues.pdf", 4, "Deque operations",
     "A deque supports insertion and removal at both its front and rear. This "
     "differs from the one-way insertion and removal convention of an ordinary "
     "queue. A doubly linked representation with head and tail pointers can "
     "perform these four end operations in constant time.",
     "Which queue variant permits both insertion and deletion at either end?"),
    ("Queues.pdf", 5, "Priority queue policy",
     "In this priority queue, larger numeric priorities are more urgent. Removal "
     "chooses the greatest priority rather than the earliest arrival. With "
     "priorities 2, 9, and 4, the item of priority 9 is removed first.",
     "If larger numbers mean greater urgency, which priority leaves first among 2, 9, and 4?"),
    ("LinkedLists.pdf", 1, "Singly linked node",
     "A singly linked node stores data and a next pointer. Starting at head, "
     "follow next to visit subsequent nodes. In a non-circular singly linked "
     "list, the last node has next equal to NULL.",
     "What two fields form a singly linked node, and what ends a non-circular traversal?"),
    ("LinkedLists.pdf", 2, "Doubly linked node",
     "A doubly linked node stores data, prev, and next. Prev refers to its "
     "predecessor, while next refers to its successor. A prev link allows "
     "backward traversal without restarting from head.",
     "Which additional pointer lets a doubly linked node move directly to its predecessor?"),
    ("LinkedLists.pdf", 3, "Insertion at the start",
     "To insert at the start of a singly linked list, set newNode->next = head "
     "and then head = newNode. This also works when the old head is NULL. "
     "No traversal to the last node is necessary.",
     "When prepending a singly linked node, which assignment must happen before updating head?"),
    ("LinkedLists.pdf", 4, "Insertion at the end",
     "For insertion at the end of a singly linked list, first set newNode->next "
     "to NULL. If head is NULL, assign head = newNode. Otherwise traverse until "
     "temp->next is NULL, then set temp->next = newNode. The existing head "
     "does not change in the nonempty case.",
     "When appending to a nonempty singly linked list, what stopping condition finds the last node?"),
    ("LinkedLists.pdf", 5, "Circular traversal",
     "In a circular singly linked list, the last node links back to head. A "
     "complete traversal stops after returning to its starting node. Waiting "
     "for NULL would fail to terminate in a correctly formed nonempty ring.",
     "How should traversal stop when the final node leads back to the first node?"),
    ("Recursion.pdf", 1, "Sum to n",
     "The sumTo function adds integers from 1 through a nonnegative n. Its base "
     "case is sumTo(0) = 0. Otherwise return n + sumTo(n - 1). For n = 5, "
     "the result is 15.",
     "What base case and recursive expression compute the sum of integers from 1 through n?"),
    ("Recursion.pdf", 2, "Counting decimal digits",
     "For a nonnegative integer, countDigits returns 1 if n is less than 10. "
     "This includes zero, which has one decimal digit. Otherwise return "
     "1 + countDigits(n / 10), using integer division to remove the last digit.",
     "Why must countDigits return one for input zero rather than zero?"),
    ("Recursion.pdf", 3, "Ascending recursive printing",
     "To print 1 through n in ascending order, stop when n is 0. First call "
     "printOneToN(n - 1), then print n. Printing before the recursive call "
     "would reverse the order for positive n.",
     "For recursive printing from 1 to n, should n be printed before or after the smaller recursive call?"),
    ("Recursion.pdf", 4, "Recursive integer power",
     "For a nonnegative exponent, power(x, 0) returns 1. Otherwise return "
     "x * power(x, n - 1). This version makes one recursive call per exponent "
     "step and takes linear time in n. Inputs must keep the integer result in range.",
     "What does the recursive power function return for exponent zero?"),
    ("Recursion.pdf", 5, "Counting Hanoi moves",
     "The minimum Hanoi move count for zero disks is 0. For n positive disks, "
     "moves(n) = 2 * moves(n - 1) + 1, giving 2^n - 1 moves. Three disks "
     "require 7 moves. Computing this count makes one recursive call per "
     "level; actually printing all moves is a different operation.",
     "Which recurrence counts minimum Tower of Hanoi moves, and how many are needed for three disks?"),
    ("Trees.pdf", 1, "Binary search tree ordering",
     "In a binary search tree with distinct keys, every key in a node's left "
     "subtree is smaller than the node key, and every key in its right subtree "
     "is larger. The same ordering rule applies recursively to each subtree.",
     "Where must keys smaller than a node be placed in a distinct-key binary search tree?"),
    ("Trees.pdf", 2, "Inorder traversal",
     "Inorder traversal visits the left subtree, then the root, then the right "
     "subtree. Applied to a binary search tree with distinct keys, it lists "
     "the keys in ascending sorted order.",
     "Which binary-tree traversal produces sorted keys from a binary search tree?"),
    ("Trees.pdf", 3, "Preorder traversal",
     "Preorder traversal visits the root before recursively visiting its left "
     "and right subtrees. The order is root, left, right. With explicit markers "
     "for missing children, this order can serialize a binary tree's structure.",
     "What is the root-left-right traversal called?"),
    ("Trees.pdf", 4, "Postorder traversal",
     "Postorder traversal processes the left subtree, then the right subtree, "
     "and finally the root. This children-before-parent order is useful when "
     "freeing an entire tree, since children are handled before their parent.",
     "Which traversal processes both children before their parent when deleting a tree?"),
    ("Trees.pdf", 5, "Level order traversal",
     "Level order visits all binary-tree nodes at one depth before moving to "
     "the next depth. A FIFO queue holds pending nodes. Remove a node from "
     "the front, visit it, then enqueue its existing left and right children.",
     "Which data structure supports visiting a binary tree one depth at a time?"),
    ("Sorting.pdf", 1, "Bubble sort",
     "Bubble sort compares neighboring items and swaps an adjacent pair when "
     "they are out of order. A full ascending-order pass moves the largest "
     "remaining item to the end of the unsorted region. A pass with no swaps "
     "permits an early stop.",
     "Which sorting method repeatedly swaps out-of-order neighboring elements?"),
    ("Sorting.pdf", 2, "Selection sort",
     "Selection sort scans the unsorted region to find its smallest item, "
     "then swaps that item into the first unsorted position. It expands the "
     "sorted region by one position on each pass. The usual swapping version "
     "does not preserve equal items' original order.",
     "Which sort searches the remaining region for its minimum before placing one item?"),
    ("Sorting.pdf", 3, "Insertion sort",
     "Insertion sort maintains a sorted prefix. For the next item, shift "
     "larger prefix items one position right and insert the item into the "
     "gap. Shifting only strictly larger items preserves the order of equal keys.",
     "Which sorting algorithm grows a sorted prefix by shifting larger items to make a gap?"),
    ("Sorting.pdf", 4, "Merge sort",
     "Merge sort divides the sequence into halves, recursively sorts both "
     "halves, and merges the two sorted sequences. Standard array merge sort "
     "takes O(n log n) time and O(n) auxiliary storage. Taking from the left "
     "half first when keys are equal makes the merge stable.",
     "Which divide-and-conquer sort combines two already sorted halves using extra array storage?"),
    ("Sorting.pdf", 5, "Quicksort partition",
     "Quicksort chooses a pivot and partitions the remaining items around "
     "that pivot before recursively sorting the partitions. Balanced splits "
     "give O(n log n) time; repeatedly extreme splits can give O(n squared) "
     "time. It does not use merge sort's combine-two-sorted-halves step.",
     "Which sorting algorithm partitions around a pivot and can become quadratic with extreme splits?"),
    ("Hashing.pdf", 1, "Modulo hashing",
     "A simple integer hash-table index is key modulo bucket_count. With "
     "13 buckets numbered 0 through 12, key 42 maps to index 3, because "
     "42 = 3 * 13 + 3. A collision means two keys map to the same bucket.",
     "Using key modulo 13, which bucket receives integer key 42?"),
    ("Hashing.pdf", 2, "Separate chaining",
     "Separate chaining keeps a collection of entries at each bucket. Keys "
     "that collide are stored together in that bucket's chain rather than "
     "occupying alternative positions in the main table. A linked list can "
     "represent a chain.",
     "How does separate chaining store multiple keys that hash to the same bucket?"),
    ("Hashing.pdf", 3, "Linear probing",
     "Linear probing handles a collision by checking consecutive table "
     "positions: h(key), (h(key) + 1) % capacity, then (h(key) + 2) % capacity, "
     "and so on. It wraps at the end and can form long primary clusters.",
     "After a collision, what sequence of slots does linear probing inspect?"),
    ("Hashing.pdf", 4, "Tombstone deletion",
     "In an open-addressed hash table, mark a removed entry with a tombstone. "
     "A search continues past tombstones, since another colliding key may "
     "lie farther along the probe sequence. Treating that slot as never used "
     "could incorrectly stop the search early.",
     "Why use a tombstone instead of a never-used empty marker when deleting an open-addressed entry?"),
    ("Hashing.pdf", 5, "Load factor and resizing",
     "Hash-table load factor is stored_entries divided by bucket_count. "
     "A table with 15 entries and 20 buckets has load factor 0.75. When "
     "resizing changes the bucket count, recompute indices for the entries; "
     "their old bucket positions generally cannot be kept unchanged.",
     "What is the load factor for 15 entries in 20 buckets?"),
    ("Graphs.pdf", 1, "Breadth-first search",
     "For an unweighted graph, breadth-first search explores vertices by "
     "distance in number of edges from its start. It uses a FIFO queue and "
     "can find minimum-edge paths. Mark a vertex visited when enqueuing it "
     "to prevent duplicate enqueues.",
     "Which graph search finds paths using the fewest edges when all edges are unweighted?"),
    ("Graphs.pdf", 2, "Depth-first search",
     "Depth-first search follows a branch as far as possible before "
     "backtracking. Its pending path can be represented by the recursive "
     "call stack or an explicit stack. Mark each vertex visited before "
     "exploring its unvisited neighbors to avoid revisiting cycles.",
     "Which graph traversal follows one branch deeply and then backtracks?"),
    ("Graphs.pdf", 3, "Undirected degrees",
     "For a finite undirected graph, the sum of all vertex degrees equals "
     "twice the number of edges. Each edge contributes one incidence at "
     "each endpoint; a self-loop contributes two. Thus a graph with 10 "
     "edges has degree sum 20.",
     "What is the total vertex degree of an undirected graph containing ten edges?"),
    ("Graphs.pdf", 4, "Adjacency matrix",
     "An adjacency matrix for V vertices has V rows and V columns and "
     "uses O(V squared) storage. It checks whether a specified edge exists "
     "by reading one cell in O(1) time. This can waste space for a sparse "
     "graph compared with adjacency lists.",
     "Which graph representation uses quadratic space but checks a specific edge in constant time?"),
    ("Graphs.pdf", 5, "Dijkstra edge requirement",
     "Dijkstra's shortest-path algorithm assumes nonnegative edge weights. "
     "It repeatedly chooses the smallest tentative distance using a "
     "min-priority queue. Negative-weight edges invalidate its usual "
     "greedy correctness guarantee.",
     "What restriction on edge weights is required by Dijkstra's shortest-path algorithm?"),
]


def score_result(ids, gold):
    limited = ids[:5]
    rank = limited.index(gold) + 1 if gold in limited else 0
    return {
        "rank_at_5": rank,
        "hit_at_1": int(rank == 1),
        "hit_at_5": int(rank > 0),
        "mrr_at_5": 1 / rank if rank else 0,
    }


def summarize(rows):
    latency = sorted(r["latency_ms"] for r in rows)
    return {
        "hit_at_1": mean(r["hit_at_1"] for r in rows),
        "hit_at_5": mean(r["hit_at_5"] for r in rows),
        "mrr_at_5": mean(r["mrr_at_5"] for r in rows),
        "mean_latency_ms": mean(latency),
        "p95_latency_ms": latency[math.ceil(0.95 * len(latency)) - 1],
    }


def main():
    os.environ["RAG_MODE"] = "local"
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")

    import chromadb
    import pymupdf
    from src import config
    from src.embeddings import embed_texts, load_embedding_model
    from src.retriever import (
        BM25_CANDIDATE_K,
        RERANKER_MODEL_NAME,
        RRF_K,
        load_reranker,
        retrieve_chunks,
    )

    keys = [(r[0], r[1]) for r in CASES]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate source/page labels.")

    for source in {r[0] for r in CASES}:
        pages = [r[1] for r in CASES if r[0] == source]
        if pages != list(range(1, len(pages) + 1)):
            raise ValueError("Pages must be consecutive within each PDF.")

    dataset_hash = sha256(
        json.dumps(CASES, separators=(",", ":")).encode()
    ).hexdigest()

    output = (
        Path(__file__).resolve().parent
        / "benchmark_results"
        / uuid4().hex[:8]
    )
    notes = output / "notes"
    notes.mkdir(parents=True)

    documents = []
    for source in sorted({row[0] for row in CASES}):
        with pymupdf.open() as pdf:
            for _, page_number, heading, body, _ in [
                r for r in CASES if r[0] == source
            ]:
                page = pdf.new_page()
                remaining = page.insert_textbox(
                    pymupdf.Rect(50, 60, 545, 780),
                    heading + "\n\n" + body,
                    fontsize=12,
                )
                if remaining < 0:
                    raise ValueError(
                        f"Text exceeds page size: {source}:{page_number}"
                    )
            pdf.save(notes / source)

        with pymupdf.open(notes / source) as pdf:
            for page_number, page in enumerate(pdf, 1):
                documents.append({
                    "source": source,
                    "page": page_number,
                    "text": page.get_text().strip(),
                })

    print(
        f"Corpus: {len(documents)} passages; questions: {len(CASES)}",
        flush=True,
    )
    print("Loading CPU models...", flush=True)

    model = load_embedding_model()
    reranker = load_reranker()
    client = chromadb.EphemeralClient()
    collection = client.create_collection(
        name="benchmark_" + uuid4().hex[:12],
        metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )
    collection.add(
        ids=[f"{d['source']}:{d['page']}" for d in documents],
        documents=[d["text"] for d in documents],
        metadatas=[
            {
                "source": d["source"],
                "page": d["page"],
                "location_type": "page",
            }
            for d in documents
        ],
        embeddings=embed_texts(
            model, [d["text"] for d in documents]
        ).tolist(),
    )
    initial_count = collection.count()

    def vector_only(question):
        vector = embed_texts(model, [question])[0].tolist()
        result = collection.query(
            query_embeddings=[vector],
            n_results=5,
            include=["metadatas"],
        )
        return result["ids"][0]

    def hybrid(question):
        return [
            h["id"]
            for h in retrieve_chunks(
                question,
                model,
                collection,
                top_k=5,
                reranker=reranker,
            )
        ]

    # Warm-up calls are excluded from retrieval timings.
    vector_only(CASES[0][4])
    hybrid(CASES[0][4])

    rows = []
    for number, (source, page, _, _, question) in enumerate(CASES, 1):
        gold = f"{source}:{page}"
        ranks = []

        for name, search in [
            ("vector_only", vector_only),
            ("hybrid_reranked", hybrid),
        ]:
            start = time.perf_counter()
            ids = search(question)
            elapsed = (time.perf_counter() - start) * 1000
            scores = score_result(ids, gold)
            rank = scores["rank_at_5"]

            rows.append({
                "question_id": f"Q{number:02}",
                "question": question,
                "gold": gold,
                "pipeline": name,
                **scores,
                "latency_ms": round(elapsed, 3),
                "top_5": " | ".join(ids[:5]),
            })
            ranks.append(f"{name} rank={rank or 'miss'}")

        print(
            f"Q{number:02}: " + "; ".join(ranks),
            flush=True,
        )

    if collection.count() != initial_count:
        raise RuntimeError("The benchmark collection changed.")

    summary = {}
    for name in ["vector_only", "hybrid_reranked"]:
        selected = [r for r in rows if r["pipeline"] == name]
        summary[name] = summarize(selected)

    def revision(obj):
        return getattr(
            getattr(obj, "config", None), "_commit_hash", None
        )

    result = {
        "dataset": "original_public_development_v1",
        "dataset_sha256": dataset_hash,
        "questions": len(CASES),
        "passages": initial_count,
        "pdfs": len({r[0] for r in CASES}),
        "embedding_model": config.EMBEDDING_MODEL_NAME,
        "reranker_model": RERANKER_MODEL_NAME,
        "embedding_revision": revision(model[0].auto_model),
        "reranker_revision": revision(reranker.model),
        "python": platform.python_version(),
        "system": platform.system(),
        "versions": {
            p: version(p)
            for p in [
                "sentence-transformers", "transformers",
                "torch", "chromadb", "PyMuPDF",
            ]
        },
        "retrieval_settings": {
            "top_k": 5,
            "candidate_k": BM25_CANDIDATE_K,
            "rrf_k": RRF_K,
        },
        "scope":
            "Retrieval only on a fixed synthetic development set; "
            "no answer, citation, or refusal accuracy scores.",
        "timing":
            "CPU; model loading/index construction and one warm-up "
            "per pipeline excluded; vector then hybrid for each query.",
        "summary": summary,
    }

    (output / "summary.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )

    with (output / "questions.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Public retrieval development benchmark",
        "",
        result["scope"],
        "",
        f"Corpus: {initial_count} authored PDF pages; "
        f"questions: {len(CASES)}.",
        f"Dataset SHA256: `{dataset_hash}`",
        "",
        "| Pipeline | Hit@1 | Hit@5 | MRR@5 | Mean ms | p95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for name, scores in summary.items():
        lines.append(
            f"| {name} | {scores['hit_at_1']:.1%} | "
            f"{scores['hit_at_5']:.1%} | "
            f"{scores['mrr_at_5']:.3f} | "
            f"{scores['mean_latency_ms']:.1f} | "
            f"{scores['p95_latency_ms']:.1f} |"
        )

    lines += [
        "",
        "Hit@k is the fraction of questions with the labeled page "
        "in the first k results.",
        "MRR@5 averages reciprocal labeled-page rank; "
        "misses contribute zero.",
        "Each question has one labeled page. "
        "The source PDFs are included in notes/.",
        "Scores use exact labeled pages; other returned pages "
        "may still contain useful information.",
        "This small authored set is for development checks; "
        "it does not establish performance on unseen courses.",
        "No retriever settings were tuned during this run. "
        "Corpus preparation is outside the retrieval timing.",
        "Model IDs, resolved revisions where available, and package "
        "versions are recorded in summary.json.",
        "",
    ]

    (output / "REPORT.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    print(json.dumps(result, indent=2))
    print(f"Saved results to: {output}")
    client.delete_collection(collection.name)


if __name__ == "__main__":
    main()