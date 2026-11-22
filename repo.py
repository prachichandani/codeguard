import os
import shutil
import stat
import tempfile
from pathlib import Path
from git import Repo


def clone_repo(github_url: str) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="code_auditor_"))
    Repo.clone_from(github_url, temp_dir, depth=1)
    return temp_dir


def remove_clone(path: Path):
    # Git marks object files read-only, which makes rmtree fail on Windows
    def make_writable_and_retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onexc=make_writable_and_retry)
