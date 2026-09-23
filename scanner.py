from pathlib import Path

IGNORE_DIRS = {".git", "node_modules", "venv", ".venv", "env", "__pycache__",
               "dist", "build", "migrations", ".idea", ".vscode",
               "tests", "test", "docs"}   
SUPPORTED_EXTENSIONS = {".py"}
MAX_FILE_SIZE_BYTES = 500_000

def scan_repo(repo_path: Path) -> list[Path]:
    files = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.suffix not in SUPPORTED_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
    return files