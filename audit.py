import re
import sys
from dotenv import load_dotenv
load_dotenv()
from clone_test import clone_repo
from scanner import scan_repo
from ast_parser import parse_repo
from chunker import chunk_entities
from vectorstore import index_chunks
from pipeline import run_pipeline


def collection_name_for(github_url: str) -> str:
    # e.g. https://github.com/psf/requests -> "requests" (Chroma allows [a-zA-Z0-9._-])
    repo_name = github_url.rstrip("/").removesuffix(".git").split("/")[-1]
    return re.sub(r"[^a-zA-Z0-9._-]", "_", repo_name).strip("._-") or "repo"


def print_report(judged: dict):
    accepted, rejected = judged["accepted"], judged["rejected"]
    print(f"\n=== ACCEPTED FINDINGS ({len(accepted)}) ===")
    for f in accepted:
        also = f" (also: {', '.join(f['also_reported_by'])})" if f.get("also_reported_by") else ""
        print(f"\n[{str(f.get('severity', '?')).upper()}] {f.get('title')}  <{f['specialist']}{also}>")
        print(f"  {f.get('file_path')}:{f.get('start_line')}-{f.get('end_line')}")
        print(f"  {f.get('explanation')}")
        print(f"  evidence: {f.get('evidence')}")
        print(f"  judge: {f.get('judge_reason')}")
    print(f"\n=== REJECTED ({len(rejected)}) ===")
    for f in rejected:
        print(f"- [{f['specialist']}] {f.get('title')}: {f['rejected_by']}: {f['reason']}")


def audit(github_url: str) -> dict:
    path = clone_repo(github_url)
    files = scan_repo(path)
    entities = parse_repo(files, path)
    chunks = chunk_entities(entities)
    print(f"{len(files)} files, {len(entities)} functions/classes")
    if not chunks:
        return {}

    collection = index_chunks(chunks, collection_name_for(github_url))
    return run_pipeline(collection)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python audit.py <github_url>")
    judged = audit(sys.argv[1])
    if not judged:
        print("No Python functions/classes found to audit.")
    else:
        print_report(judged)
