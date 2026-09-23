import chromadb
from pathlib import Path
from vectorstore import semantic_search
from dotenv import load_dotenv
load_dotenv()
from agent import run_agent, DEFAULT_TASK

CHROMA_DIR = Path("chroma_db")

client = chromadb.PersistentClient(path=str(CHROMA_DIR))

collection = client.get_collection("code_chunks")

# query = "How does Flask handle HTTP requests?"

# results = semantic_search(
#     collection,
#     query,
#     n_results=5
# )

# for result in results:
#     print(
#         f"[{result['similarity_score']}] "
#         f"{result['file_path']} :: "
#         f"{result['name']} "
#         f"(lines {result['start_line']}-{result['end_line']})"
#     )

findings = run_agent(DEFAULT_TASK, collection)
print("\n=== FINDINGS ===\n")
print(findings)