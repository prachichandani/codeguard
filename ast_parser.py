import ast
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class CodeEntity:
    file_path: str
    name: str
    kind: str
    start_line: int
    end_line: int
    source: str
    docstring: str | None = None
    parent_class: str | None = None
    calls: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


#Extract all function calls from an AST node.
def _get_calls(node: ast.AST) -> list[str]:
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                calls.append(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                calls.append(child.func.attr)
    return calls

#Look through the Python file and give me a list of all the modules it imports.
def _get_imports(tree: ast.Module) -> list[str]:
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


#Parse a Python file and extract all functions, classes, and methods with their source code.
def parse_file(file_path: Path, repo_root: Path) -> list[CodeEntity]:
    try:
        source_text = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source_text, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"Skipping {file_path}: {e}")
        return []

    lines = source_text.splitlines()
    imports = _get_imports(tree)
    rel_path = str(file_path.relative_to(repo_root))
    entities: list[CodeEntity] = []

    def extract(node, parent_class=None):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start, end = child.lineno, child.end_lineno or child.lineno
                entities.append(CodeEntity(
                    file_path=rel_path, name=child.name,
                    kind="method" if parent_class else "function",
                    start_line=start, end_line=end,
                    source="\n".join(lines[start - 1:end]),
                    docstring=ast.get_docstring(child),
                    parent_class=parent_class,
                    calls=_get_calls(child), imports=imports,
                ))
            elif isinstance(child, ast.ClassDef):
                start, end = child.lineno, child.end_lineno or child.lineno
                entities.append(CodeEntity(
                    file_path=rel_path, name=child.name, kind="class",
                    start_line=start, end_line=end,
                    source="\n".join(lines[start - 1:end]),
                    docstring=ast.get_docstring(child),
                    parent_class=None, calls=[], imports=imports,
                ))
                extract(child, parent_class=child.name)

    extract(tree)
    return entities


#Parse all Python files in a repository and return a list of CodeEntity objects.
def parse_repo(file_paths: list[Path], repo_root: Path) -> list[CodeEntity]:
    all_entities: list[CodeEntity] = []
    for fp in file_paths:
        all_entities.extend(parse_file(fp, repo_root))
    return all_entities