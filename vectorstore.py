import chromadb
from pathlib import Path
from chunker import Chunk
from embedder import embed_texts

CHROMA_DIR = Path("chroma_db")

def get_collection(collection_name: str):
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    return client.create_collection(collection_name)


def index_chunks(chunks: list[Chunk], collection_name: str = "code_chunks"):
    collection = get_collection(collection_name)
    texts = [c.text for c in chunks]
    embeddings = embed_texts(texts)
    collection.add(
        ids=[c.id for c in chunks],
        embeddings=embeddings,
        documents=[c.code for c in chunks],
        metadatas=[c.to_metadata() for c in chunks],
    )
    print(f"Indexed {len(chunks)} chunks into '{collection_name}'")
    return collection


def semantic_search(collection, query: str, n_results: int = 5) -> list[dict]:
    query_embedding = embed_texts([query])[0]
    results = collection.query(query_embeddings=[query_embedding], n_results=n_results)
    hits = []
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        hits.append({
            "file_path": meta["file_path"],
            "name": meta["name"],
            "kind": meta["kind"],
            "start_line": meta["start_line"],
            "end_line": meta["end_line"],
            "code": doc,
            "similarity_score": round(1 - dist, 4),
        })
    return hits


def symbol_search(collection, name: str, n_results: int = 5) -> list[dict]:
    # Accepts "func", "Class" or "Class.method"; case-insensitive.
    # Exact name matches rank first, then partial (substring) matches.
    query = name.strip().lower()
    wanted_class = None
    if "." in query:
        wanted_class, query = query.rsplit(".", 1)

    results = collection.get(include=["documents", "metadatas"])
    exact, partial = [], []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        entity_name = meta["name"].lower()
        if wanted_class and meta["parent_class"].lower() != wanted_class:
            continue
        if entity_name == query:
            match = "exact"
        elif query in entity_name:
            match = "partial"
        else:
            continue
        hit = {
            "file_path": meta["file_path"],
            "name": meta["name"],
            "kind": meta["kind"],
            "parent_class": meta["parent_class"],
            "start_line": meta["start_line"],
            "end_line": meta["end_line"],
            "code": doc,
            "match": match,
        }
        (exact if match == "exact" else partial).append(hit)
    return (exact + partial)[:n_results]


def _same_path(a: str, b: str) -> bool:
    # Index stores OS-style paths (src\flask\app.py); models may write src/flask/app.py
    return a.replace("\\", "/").strip("/").lower() == b.replace("\\", "/").strip("/").lower()


def code_at_lines(collection, file_path: str, start_line: int, end_line: int) -> tuple[str, str] | None:
    # Returns (code at exactly those lines, code of the whole enclosing entity),
    # or None if no indexed function/class in that file covers those lines.
    results = collection.get(include=["documents", "metadatas"])
    candidates = [
        (doc, meta) for doc, meta in zip(results["documents"], results["metadatas"])
        if _same_path(meta["file_path"], file_path)
        and meta["start_line"] <= end_line and meta["end_line"] >= start_line
    ]
    if not candidates:
        return None
    # Prefer the smallest entity that fully contains the range (a method, not its whole class)
    containing = [c for c in candidates if c[1]["start_line"] <= start_line and c[1]["end_line"] >= end_line]
    doc, meta = min(containing or candidates, key=lambda c: c[1]["end_line"] - c[1]["start_line"])
    lines = doc.splitlines()
    first = max(start_line, meta["start_line"]) - meta["start_line"]
    last = min(end_line, meta["end_line"]) - meta["start_line"]
    return "\n".join(lines[first:last + 1]), doc


def _location(meta: dict) -> dict:
    # Location only, no code: keeps graph results small. The agent can
    # fetch code for anything interesting with symbol_search.
    return {
        "file_path": meta["file_path"],
        "name": meta["name"],
        "kind": meta["kind"],
        "parent_class": meta["parent_class"],
        "start_line": meta["start_line"],
        "end_line": meta["end_line"],
    }


def graph_traversal(collection, name: str, direction: str = "callees", n_results: int = 20) -> dict:
    # direction="callees": what does `name` call?
    # direction="callers": what calls `name`?
    # Calls were recorded by bare name only (self.foo() -> "foo"), so matches
    # are by name and may include same-named functions from other classes.
    query = name.strip().lower()
    wanted_class = None
    if "." in query:
        wanted_class, query = query.rsplit(".", 1)

    metas = collection.get(include=["metadatas"])["metadatas"]
    definitions = [
        m for m in metas
        if m["name"].lower() == query
        and (not wanted_class or m["parent_class"].lower() == wanted_class)
    ]

    if direction == "callers":
        callers = [
            _location(m) for m in metas
            if query in m.get("calls", "").lower().split(",")
        ]
        return {
            "symbol": name,
            "direction": "callers",
            "definitions": [_location(m) for m in definitions],
            "callers": callers[:n_results],
            "total_callers": len(callers),
        }

    if direction != "callees":
        raise ValueError(f"direction must be 'callers' or 'callees', got {direction!r}")
    if not definitions:
        return {"symbol": name, "direction": "callees", "error": "No definition found in the indexed code."}

    by_name: dict[str, list[dict]] = {}
    for m in metas:
        by_name.setdefault(m["name"].lower(), []).append(m)

    results = []
    for d in definitions:
        calls = [c for c in d.get("calls", "").split(",") if c]
        resolved, external = [], []
        for call in calls:
            if call.lower() in by_name:
                resolved.extend(_location(m) for m in by_name[call.lower()])
            else:
                external.append(call)  # builtins / third-party / not indexed
        results.append({
            "definition": _location(d),
            "calls_in_repo": resolved[:n_results],
            "calls_external": external,
        })
    return {"symbol": name, "direction": "callees", "results": results}