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