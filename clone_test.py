from repo import clone_repo
from scanner import scan_repo
from ast_parser import parse_repo
from chunker import chunk_entities
from embedder import embed_texts
from vectorstore import index_chunks, semantic_search
from dotenv import load_dotenv
load_dotenv()

if __name__ == "__main__":
    path = clone_repo("https://github.com/pallets/flask")
    files = scan_repo(path)
    entities = parse_repo(files, path)
    print("Total entities extracted:", len(entities))
    print("Sample entity:")
    e = entities[0]
    print("  name:", e.name, "| kind:", e.kind, "| file:", e.file_path, "| lines:", e.start_line, "-", e.end_line)
    print("  calls:", e.calls[:5])
    chunks = chunk_entities(entities)
    print("Total chunks:", len(chunks))
    print("Sample chunk id:", chunks[0].id)
    print("Sample chunk text (what gets embedded):")
    print(chunks[0].text) 
    sample_texts = [c.text for c in chunks[:5]]
    vectors = embed_texts(sample_texts)
    print("Number of vectors:", len(vectors))
    print("Vector dimension:", len(vectors[0]))
    print("First 5 values of first vector:", vectors[0][:5])

    collection = index_chunks(chunks)  # indexes ALL 431 chunks now, will take a bit longer

    results = semantic_search(collection, "session and cookie handling", n_results=5)
    print("\nTop results for 'session and cookie handling':")
    for r in results:
        print(f"  [{r['similarity_score']}] {r['file_path']} :: {r['name']} (lines {r['start_line']}-{r['end_line']})")
